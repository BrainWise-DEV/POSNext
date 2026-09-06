# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from pos_next.api.product_management import (
	_save_uom_conversions,
	_validate_pos_profile_access,
	get_item_groups,
	save_product,
)

PROFILE = "Test POS Profile"


def _payload(**overrides) -> str:
	base = {
		"item_name": "Test Product",
		"item_group": "Beverages",
		"stock_uom": "Nos",
	}
	base.update(overrides)
	return json.dumps(base)


class TestPOSProfileAccess(unittest.TestCase):
	"""The POS Profile argument is caller-supplied and decides which item groups
	the caller may touch, so it must be validated on every endpoint. An
	unvalidated profile name lets a caller pick one with no group restriction,
	which disables the scoping entirely."""

	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_unassigned_user_without_profile_write_is_rejected(self, mock_db, mock_perm):
		mock_db.exists.return_value = None  # not in POS Profile User
		mock_perm.return_value = False  # cannot administer POS Profiles

		with self.assertRaises(frappe.ValidationError):
			_validate_pos_profile_access(PROFILE)

	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_assigned_user_is_allowed(self, mock_db, mock_perm):
		mock_db.exists.return_value = "POS Profile User Row"
		mock_perm.return_value = False

		_validate_pos_profile_access(PROFILE)  # must not raise

	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_profile_administrator_is_allowed_without_assignment(self, mock_db, mock_perm):
		mock_db.exists.return_value = None
		mock_perm.return_value = True  # has POS Profile write

		_validate_pos_profile_access(PROFILE)  # must not raise

	def test_empty_profile_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_validate_pos_profile_access("")


class TestGetItemGroupsPermissions(unittest.TestCase):
	@patch("pos_next.api.product_management.frappe.has_permission")
	def test_requires_item_read(self, mock_perm):
		mock_perm.return_value = False

		with self.assertRaises(frappe.ValidationError):
			get_item_groups(PROFILE)


class TestSaveProductScoping(unittest.TestCase):
	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_rejects_profile_the_user_is_not_assigned_to(self, mock_db, mock_perm):
		"""Regression: without this check a caller could name any POS Profile,
		including one with no item_groups rows, and bypass group scoping."""
		mock_db.exists.return_value = None

		def perms(doctype, ptype=None, *args, **kwargs):
			# Has Item rights (the feature requires them) but no POS Profile write.
			return doctype == "Item"

		mock_perm.side_effect = perms

		with self.assertRaises(frappe.ValidationError):
			save_product(PROFILE, _payload())

	@patch("pos_next.api.product_management._get_pos_profile_allowed_item_groups")
	@patch("pos_next.api.product_management.frappe.get_doc")
	@patch("pos_next.api.product_management.frappe.get_cached_doc")
	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_rejects_item_whose_current_group_is_out_of_scope(
		self, mock_db, mock_perm, mock_cached_doc, mock_get_doc, mock_groups
	):
		"""Regression: only the incoming item_group was checked, so an item could
		be pulled out of a disallowed group and into an allowed one."""
		mock_db.exists.return_value = "POS Profile User Row"
		mock_perm.return_value = True
		mock_cached_doc.return_value = frappe._dict({"selling_price_list": "Standard Selling"})
		mock_groups.return_value = ["Beverages"]

		existing = MagicMock()
		existing.item_group = "Electronics"  # outside this profile's scope
		mock_get_doc.return_value = existing

		with self.assertRaises(frappe.ValidationError):
			save_product(PROFILE, _payload(item_code="ITEM-OUT-OF-SCOPE"))

		existing.save.assert_not_called()

	@patch("pos_next.api.product_management._get_pos_profile_allowed_item_groups")
	@patch("pos_next.api.product_management.frappe.get_cached_doc")
	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_rejects_incoming_group_outside_scope(self, mock_db, mock_perm, mock_cached_doc, mock_groups):
		mock_db.exists.return_value = "POS Profile User Row"
		mock_perm.return_value = True
		mock_cached_doc.return_value = frappe._dict({"selling_price_list": "Standard Selling"})
		mock_groups.return_value = ["Beverages"]

		with self.assertRaises(frappe.ValidationError):
			save_product(PROFILE, _payload(item_group="Electronics"))

	@patch("pos_next.api.product_management._get_pos_profile_allowed_item_groups")
	@patch("pos_next.api.product_management.frappe.new_doc")
	@patch("pos_next.api.product_management.frappe.get_cached_doc")
	@patch("pos_next.api.product_management.frappe.has_permission")
	@patch("pos_next.api.product_management.frappe.db", new_callable=MagicMock)
	def test_rejects_external_image_url(self, mock_db, mock_perm, mock_cached_doc, mock_new_doc, mock_groups):
		"""item.image is rendered by the POS, so only Frappe file paths are accepted."""
		mock_db.exists.return_value = "POS Profile User Row"
		mock_perm.return_value = True
		mock_cached_doc.return_value = frappe._dict({"selling_price_list": None})
		mock_groups.return_value = []
		mock_new_doc.return_value = MagicMock()

		with self.assertRaises(frappe.ValidationError):
			save_product(PROFILE, _payload(image="https://example.com/tracker.png"))


class TestSaveUomConversions(unittest.TestCase):
	def _item(self, stock_uom="Nos"):
		item = MagicMock()
		item.stock_uom = stock_uom
		item.appended = []
		item.append.side_effect = lambda table, row: item.appended.append(row)
		return item

	def test_skips_stock_uom_duplicates_and_non_positive_factors(self):
		item = self._item()
		_save_uom_conversions(
			item,
			[
				{"uom": "Nos", "conversion_factor": 1},  # stock uom, skipped
				{"uom": "Box", "conversion_factor": 12},
				{"uom": "Box", "conversion_factor": 24},  # duplicate, skipped
				{"uom": "Case", "conversion_factor": 0},  # non-positive, skipped
				{"uom": "", "conversion_factor": 5},  # blank, skipped
			],
		)

		item.set.assert_called_once_with("uoms", [])
		self.assertEqual(item.appended, [{"uom": "Box", "conversion_factor": 12.0}])
