# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import invoices, pricing


class _FakeDoc(frappe._dict):
	"""frappe._dict whose ``items`` attribute returns the child list rather than dict.items()."""

	@property
	def items(self):
		return self["items"]


def _make_invoice_doc(
	items,
	pos_profile="Main POS",
	company="Test Co",
	customer="Walk-in",
	is_return=0,
	return_against=None,
	discount_amount=0,
	additional_discount_percentage=0,
	coupon_code=None,
):
	return _FakeDoc(
		pos_profile=pos_profile,
		company=company,
		customer=customer,
		posting_date="2026-11-24",
		selling_price_list="Standard Selling",
		is_return=is_return,
		return_against=return_against,
		discount_amount=discount_amount,
		additional_discount_percentage=additional_discount_percentage,
		coupon_code=coupon_code,
		items=[frappe._dict(i) for i in items],
	)


class TestServerSidePricing(FrappeTestCase):
	def setUp(self):
		self.profile_doc = frappe._dict(
			name="Main POS",
			company="Test Co",
			selling_price_list="Standard Selling",
		)
		self.strict_settings = {
			"allow_user_to_edit_rate": 0,
			"allow_user_to_edit_item_discount": 0,
			"allow_user_to_edit_additional_discount": 0,
			"max_discount_allowed": 0,
		}

	def test_online_price_tampering_rejected(self):
		doc = _make_invoice_doc([{"item_code": "ITEM-1", "qty": 1, "rate": 1.0, "price_list_rate": 1.0}])
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					doc,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
					is_offline_sync=False,
					validate_manual_rate_edit_fn=invoices.validate_manual_rate_edit,
				)

	def test_online_exact_catalog_price_succeeds_and_pins_price_list_rate(self):
		doc = _make_invoice_doc([{"item_code": "ITEM-1", "qty": 2, "rate": 100.0, "price_list_rate": 50.0}])
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			pricing.enforce_server_side_pricing(
				doc,
				pos_profile="Main POS",
				pos_profile_doc=self.profile_doc,
				pos_settings_cache=self.strict_settings,
				is_offline_sync=False,
				validate_manual_rate_edit_fn=invoices.validate_manual_rate_edit,
			)
		self.assertEqual(doc.items[0].price_list_rate, 100.0)
		self.assertEqual(doc.items[0].rate, 100.0)
		self.assertEqual(doc.items[0].discount_amount, 0.0)

	def test_manual_rate_edit_uses_server_price_not_client_original_rate(self):
		# Attacker sends original_rate=10 and rate=9 to sneak past 10% max_discount_allowed on a 100 item
		doc = _make_invoice_doc(
			[
				{
					"item_code": "ITEM-1",
					"qty": 1,
					"rate": 9.0,
					"original_rate": 10.0,
					"is_rate_manually_edited": 1,
				}
			]
		)
		settings = {
			"allow_user_to_edit_rate": 1,
			"allow_user_to_edit_item_discount": 0,
			"allow_user_to_edit_additional_discount": 0,
			"max_discount_allowed": 10,
		}
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					doc,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=settings,
					is_offline_sync=False,
					validate_manual_rate_edit_fn=invoices.validate_manual_rate_edit,
				)
		self.assertEqual(doc.items[0].original_rate, 100.0)

	def test_manual_rate_edit_within_limit_succeeds(self):
		doc = _make_invoice_doc(
			[
				{
					"item_code": "ITEM-1",
					"qty": 1,
					"rate": 92.0,
					"is_rate_manually_edited": 1,
				}
			]
		)
		settings = {
			"allow_user_to_edit_rate": 1,
			"allow_user_to_edit_item_discount": 0,
			"allow_user_to_edit_additional_discount": 0,
			"max_discount_allowed": 10,
		}
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			pricing.enforce_server_side_pricing(
				doc,
				pos_profile="Main POS",
				pos_profile_doc=self.profile_doc,
				pos_settings_cache=settings,
				is_offline_sync=False,
				validate_manual_rate_edit_fn=invoices.validate_manual_rate_edit,
			)
		self.assertEqual(doc.items[0].price_list_rate, 100.0)
		self.assertEqual(doc.items[0].rate, 92.0)

	def test_forged_free_item_rejected_and_valid_promo_free_item_allowed(self):
		forged = _make_invoice_doc([{"item_code": "ITEM-FREE", "qty": 1, "rate": 0, "is_free_item": 1}])
		with (
			patch("pos_next.api.pricing._is_valid_free_item_rule", return_value=False),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					forged,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
				)

		valid = _make_invoice_doc(
			[{"item_code": "ITEM-FREE", "qty": 1, "rate": 0, "is_free_item": 1, "pricing_rules": '["BOGO-1"]'}]
		)
		with (
			patch("pos_next.api.pricing._is_valid_free_item_rule", return_value=True),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			pricing.enforce_server_side_pricing(
				valid,
				pos_profile="Main POS",
				pos_profile_doc=self.profile_doc,
				pos_settings_cache=self.strict_settings,
			)
		self.assertEqual(valid.items[0].rate, 0)

	def test_active_pricing_rule_discount_allowed_and_excess_discount_rejected(self):
		valid = _make_invoice_doc(
			[
				{
					"item_code": "ITEM-1",
					"qty": 1,
					"rate": 80.0,
					"discount_percentage": 20,
					"pricing_rules": '["PROMO-20"]',
				}
			]
		)
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._max_pricing_rule_discount_amount", return_value=20.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			pricing.enforce_server_side_pricing(
				valid,
				pos_profile="Main POS",
				pos_profile_doc=self.profile_doc,
				pos_settings_cache=self.strict_settings,
			)
		self.assertEqual(valid.items[0].rate, 80.0)
		self.assertEqual(valid.items[0].price_list_rate, 100.0)

		tampered = _make_invoice_doc(
			[
				{
					"item_code": "ITEM-1",
					"qty": 1,
					"rate": 50.0,
					"discount_percentage": 50,
					"pricing_rules": '["PROMO-20"]',
				}
			]
		)
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._max_pricing_rule_discount_amount", return_value=20.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					tampered,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
				)

	def test_offline_sync_tolerance_allows_small_price_drift_and_rejects_abuse(self):
		# Price went from 95 -> 100 while terminal was offline (5% drift <= 15% default tolerance)
		small_drift = _make_invoice_doc([{"item_code": "ITEM-1", "qty": 1, "rate": 95.0}])
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing.get_offline_price_tolerance_pct", return_value=15.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			pricing.enforce_server_side_pricing(
				small_drift,
				pos_profile="Main POS",
				pos_profile_doc=self.profile_doc,
				pos_settings_cache=self.strict_settings,
				is_offline_sync=True,
			)
		self.assertEqual(small_drift.items[0].rate, 95.0)

		# Abusive tampering pretending to be offline (90% drop > 15% tolerance) -> rejected
		abusive = _make_invoice_doc([{"item_code": "ITEM-1", "qty": 1, "rate": 10.0}])
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing.get_offline_price_tolerance_pct", return_value=15.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					abusive,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
					is_offline_sync=True,
				)

	def test_return_invoice_rate_cannot_exceed_original_invoice_rate(self):
		orig_rows = [frappe._dict(name="ROW-1", item_code="ITEM-1", rate=80.0, price_list_rate=100.0, net_rate=80.0)]
		bad_return = _make_invoice_doc(
			[{"item_code": "ITEM-1", "sales_invoice_item": "ROW-1", "qty": -1, "rate": 150.0}],
			is_return=1,
			return_against="SINV-ORIG-1",
		)
		with patch("pos_next.api.pricing.frappe.get_all", return_value=orig_rows):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(bad_return, pos_profile="Main POS")

		good_return = _make_invoice_doc(
			[{"item_code": "ITEM-1", "sales_invoice_item": "ROW-1", "qty": -1, "rate": 80.0}],
			is_return=1,
			return_against="SINV-ORIG-1",
		)
		with patch("pos_next.api.pricing.frappe.get_all", return_value=orig_rows):
			pricing.enforce_server_side_pricing(good_return, pos_profile="Main POS")
		self.assertEqual(good_return.items[0].price_list_rate, 100.0)

	def test_unauthorized_additional_discount_rejected(self):
		doc = _make_invoice_doc(
			[{"item_code": "ITEM-1", "qty": 1, "rate": 100.0}],
			discount_amount=25.0,
		)
		with (
			patch("pos_next.api.pricing.resolve_server_item_price", return_value=100.0),
			patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0),
		):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					doc,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
				)

	def test_draft_pricing_matches_db_detects_step2_tampering(self):
		existing = _make_invoice_doc([{"item_code": "ITEM-1", "uom": "Nos", "qty": 1, "rate": 80.0}])
		unchanged = {
			"items": [{"item_code": "ITEM-1", "uom": "Nos", "qty": 1, "rate": 80.0}],
			"discount_amount": 0,
		}
		tampered = {
			"items": [{"item_code": "ITEM-1", "uom": "Nos", "qty": 1, "rate": 1.0}],
			"discount_amount": 0,
		}
		self.assertTrue(pricing._draft_pricing_matches_db(existing, unchanged))
		self.assertFalse(pricing._draft_pricing_matches_db(existing, tampered))

	def test_negative_quantity_on_non_return_sale_rejected(self):
		doc = _make_invoice_doc([{"item_code": "ITEM-1", "qty": -2, "rate": 100.0}])
		with patch("pos_next.api.pricing._has_active_friends_and_family_discount", return_value=0.0):
			with self.assertRaises(frappe.ValidationError):
				pricing.enforce_server_side_pricing(
					doc,
					pos_profile="Main POS",
					pos_profile_doc=self.profile_doc,
					pos_settings_cache=self.strict_settings,
				)

	def test_resolve_server_item_price_scales_by_db_uom_conversion_factor(self):
		with (
			patch.object(
				frappe.db,
				"get_value",
				side_effect=[
					frappe._dict(stock_uom="Nos", standard_rate=0),
					12.0,  # UOM Conversion Detail: 1 Box = 12 Nos
				],
			),
			patch(
				"pos_next.api.pricing.frappe.get_all",
				return_value=[frappe._dict(price_list_rate=10.0, uom="Nos", customer="", valid_from=None, valid_upto=None)],
			),
		):
			rate = pricing.resolve_server_item_price(
				"ITEM-1", "Standard Selling", uom="Box", posting_date="2026-11-24"
			)
		self.assertEqual(rate, 120.0)
