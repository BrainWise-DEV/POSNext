# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import authorization, invoices, items, offers, pos_profile, promotions, shifts
from pos_next.pos_next.doctype.pos_settings import pos_settings


class TestProfileCatalogSecurity(FrappeTestCase):
	def test_pos_profile_read_endpoints_enforce_profile_membership(self):
		with (
			patch("pos_next.api.pos_profile.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.pos_profile.ensure_pos_user",
				side_effect=frappe.PermissionError("Denied"),
			),
		):
			for fn in (
				pos_profile.get_pos_profile_data,
				pos_profile.get_pos_settings,
				pos_profile.get_payment_methods,
				pos_profile.get_receivable_accounts,
				pos_profile.get_taxes,
				pos_profile.get_warehouses,
				pos_profile.get_default_customer,
				pos_profile.get_sales_persons,
			):
				with self.assertRaises(frappe.PermissionError):
					fn("Other POS")

	def test_update_warehouse_and_update_pos_settings_reject_plain_cashier(self):
		with (
			patch("pos_next.api.pos_profile.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.pos_profile.is_pos_supervisor", return_value=False),
			patch("pos_next.api.pos_profile.frappe.has_permission", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				pos_profile.update_warehouse("Main POS", "WH-1")
			with self.assertRaises(frappe.PermissionError):
				pos_profile.delete_pos_profile("Main POS")

		with (
			patch("pos_next.pos_next.doctype.pos_settings.pos_settings.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.pos_next.doctype.pos_settings.pos_settings.is_pos_supervisor", return_value=False),
			patch("pos_next.pos_next.doctype.pos_settings.pos_settings.frappe.has_permission", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				pos_settings.update_pos_settings("Main POS", {"allow_credit_sale": 1})

	def test_items_endpoints_enforce_pos_profile_access(self):
		with (
			patch("pos_next.api.items.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.items.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				items.search_by_barcode("12345", "Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_item_variants("TMPL-1", "Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_items("Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_items_bulk("Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_items_count("Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_item_details("ITEM-1", "Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_item_groups("Other POS")
			with self.assertRaises(frappe.PermissionError):
				items.get_brands("Other POS")

	def test_offers_endpoints_enforce_profile_and_customer_permission(self):
		with patch("pos_next.api.offers.ensure_pos_user", side_effect=frappe.PermissionError("Denied")):
			with self.assertRaises(frappe.PermissionError):
				offers.get_offers("Other POS")

		with (
			patch("pos_next.api.offers.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.offers.frappe.db.table_exists", return_value=True),
			patch(
				"pos_next.api.offers.frappe.has_permission",
				side_effect=frappe.PermissionError("No Customer read"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				offers.get_customer_one_time_redemptions("CUST-1")
			with self.assertRaises(frappe.PermissionError):
				offers.get_active_coupons("CUST-1", "Test Co")
			with self.assertRaises(frappe.PermissionError):
				offers.validate_coupon("SAVE10", "Test Co", customer="CUST-1")

	def test_other_profile_scoped_endpoints(self):
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.validate_cart_items([], pos_profile="Other POS")

		with (
			patch("pos_next.api.promotions.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.promotions.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				promotions.get_promotions(pos_profile="Other POS")
			with self.assertRaises(frappe.PermissionError):
				promotions.search_items("shirt", pos_profile="Other POS")

		with (
			patch("pos_next.api.authorization.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.authorization.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				authorization.get_authorization_policy("Other POS")
			with self.assertRaises(frappe.PermissionError):
				authorization.get_authorizers("return", pos_profile="Other POS")

		with (
			patch("pos_next.api.shifts.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.shifts.frappe.has_permission", return_value=True),
			patch("pos_next.api.shifts.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				shifts.get_shift_history(pos_profile="Other POS")
