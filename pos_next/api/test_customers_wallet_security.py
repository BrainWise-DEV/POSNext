# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import customers, wallet
from pos_next.pos_next.doctype.wallet import wallet as wallet_dt
from pos_next.pos_next.doctype.wallet_transaction import wallet_transaction as wt_dt


class TestCustomersAndWalletSecurity(FrappeTestCase):
	def test_get_customers_caps_limit_zero_and_large_limit(self):
		with (
			patch("pos_next.api.customers.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.customers.ensure_pos_user", return_value="cashier@example.com"),
			patch("pos_next.api.customers.frappe.has_permission", return_value=True),
			patch("pos_next.api.customers.frappe.get_cached_doc", return_value=frappe._dict()),
			patch("pos_next.api.customers.frappe.get_all", return_value=[]) as mock_get_all,
		):
			customers.get_customers(pos_profile="Main POS", limit=0)
			self.assertEqual(mock_get_all.call_args.kwargs["limit"], customers.MAX_CUSTOMERS_LIMIT)

			customers.get_customers(pos_profile="Main POS", limit=999999)
			self.assertEqual(mock_get_all.call_args.kwargs["limit"], customers.MAX_CUSTOMERS_LIMIT)

			customers.get_customers(pos_profile="Main POS", limit=15)
			self.assertEqual(mock_get_all.call_args.kwargs["limit"], 15)

	def test_get_customers_enforces_pos_profile_and_customer_read_permission(self):
		with (
			patch("pos_next.api.customers.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.customers.ensure_pos_user",
				side_effect=frappe.PermissionError("No access"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				customers.get_customers(pos_profile="Other POS")

		with (
			patch("pos_next.api.customers.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.customers.frappe.has_permission", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				customers.get_customers()

	def test_get_customer_details_enforces_permission_and_filters_fields(self):
		full_doc = frappe._dict(
			name="CUST-001",
			customer_name="Jane Doe",
			mobile_no="123456",
			email_id="jane@example.com",
			disabled=0,
			tax_id="SECRET-TAX-999",
			credit_limits=[{"credit_limit": 50000}],
			accounts=[{"account": "Secret AR"}],
			owner="Administrator",
		)
		with (
			patch("pos_next.api.customers.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.customers.frappe.has_permission", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				customers.get_customer_details("CUST-001")

		with (
			patch("pos_next.api.customers.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.customers.frappe.has_permission", return_value=True),
			patch("pos_next.api.customers.frappe.get_doc", return_value=full_doc),
		):
			result = customers.get_customer_details("CUST-001")
			self.assertEqual(result["name"], "CUST-001")
			self.assertEqual(result["customer_name"], "Jane Doe")
			self.assertNotIn("tax_id", result)
			self.assertNotIn("credit_limits", result)
			self.assertNotIn("accounts", result)
			self.assertNotIn("owner", result)

	def test_wallet_endpoints_enforce_profile_and_customer_permissions(self):
		with (
			patch("pos_next.api.wallet.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.wallet.ensure_pos_user", side_effect=frappe.PermissionError("Denied")),
		):
			with self.assertRaises(frappe.PermissionError):
				wallet.get_customer_wallet_balance("CUST-1", pos_profile="Other POS")
			with self.assertRaises(frappe.PermissionError):
				wallet.get_wallet_info("CUST-1", "Test Co", pos_profile="Other POS")
			with self.assertRaises(frappe.PermissionError):
				wallet.get_wallet_payment_methods("Other POS")

		with (
			patch("pos_next.api.wallet.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.wallet.frappe.has_permission",
				side_effect=frappe.PermissionError("No Customer read"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				wallet.get_customer_wallet("CUST-1")
			with self.assertRaises(frappe.PermissionError):
				wallet.get_or_create_wallet("CUST-1", "Test Co")

	def test_wallet_doctype_and_transaction_endpoints_enforce_permissions(self):
		with (
			patch("pos_next.pos_next.doctype.wallet.wallet.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.pos_next.doctype.wallet.wallet.frappe.has_permission",
				side_effect=frappe.PermissionError("Denied"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				wallet_dt.create_customer_wallet("CUST-1", "Test Co")

		with (
			patch(
				"pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.ensure_desk_user",
				return_value="cashier@example.com",
			),
			patch(
				"pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.frappe.has_permission",
				side_effect=frappe.PermissionError("Denied"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				wt_dt.create_wallet_credit("WAL-1", 1000)
			with self.assertRaises(frappe.PermissionError):
				wt_dt.credit_loyalty_points_to_wallet("CUST-1", "Test Co", 500)
