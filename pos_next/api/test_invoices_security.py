# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import invoices


class TestInvoicesSecurity(FrappeTestCase):
	def test_update_invoice_rejects_arbitrary_doctype(self):
		payload = json.dumps(
			{
				"doctype": "Journal Entry",
				"pos_profile": "Main POS",
				"company": "Test Co",
			}
		)
		with self.assertRaises(frappe.PermissionError):
			invoices.update_invoice(payload)

	def test_submit_invoice_rejects_arbitrary_doctype(self):
		payload = json.dumps(
			{
				"doctype": "Payment Entry",
				"pos_profile": "Main POS",
			}
		)
		with self.assertRaises(frappe.PermissionError):
			invoices.submit_invoice(invoice=payload, data="{}")

	def test_update_invoice_rejects_unassigned_pos_profile(self):
		payload = json.dumps(
			{
				"doctype": "Sales Invoice",
				"pos_profile": "Secret POS",
				"customer": "Walk-in",
				"items": [],
			}
		)
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch(
				"pos_next.api.invoices.ensure_pos_user",
				side_effect=frappe.PermissionError("You do not have access to POS Profile Secret POS"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.update_invoice(payload)

	def test_update_invoice_blocks_editing_another_cashiers_draft(self):
		other_draft = SimpleNamespace(
			name="SINV-DRAFT-1",
			docstatus=0,
			owner="cashier_b@example.com",
			pos_profile="Main POS",
			get=lambda k, d=None: {"pos_profile": "Main POS"}.get(k, d),
		)
		payload = json.dumps(
			{
				"doctype": "Sales Invoice",
				"name": "SINV-DRAFT-1",
				"pos_profile": "Main POS",
				"items": [],
			}
		)
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
			patch("pos_next.api.invoices.frappe.get_doc", return_value=other_draft),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.update_invoice(payload)

	def test_submit_invoice_blocks_submitting_another_cashiers_draft(self):
		other_draft = SimpleNamespace(
			name="SINV-DRAFT-2",
			docstatus=0,
			owner="cashier_b@example.com",
			pos_profile="Main POS",
			customer="Walk-in",
			get=lambda k, d=None: {"pos_profile": "Main POS"}.get(k, d),
		)
		payload = json.dumps(
			{
				"doctype": "Sales Invoice",
				"name": "SINV-DRAFT-2",
				"pos_profile": "Main POS",
			}
		)
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
			patch.object(frappe.db, "exists", return_value="SINV-DRAFT-2"),
			patch.object(frappe.db, "get_value", return_value="Main POS"),
			patch("pos_next.api.invoices.frappe.get_doc", return_value=other_draft),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.submit_invoice(invoice=payload, data="{}")

	def test_ensure_invoice_draft_access_blocks_submitted_invoice(self):
		submitted = SimpleNamespace(
			name="SINV-SUB-1",
			docstatus=1,
			owner="cashier_a@example.com",
			pos_profile="Main POS",
			get=lambda k, d=None: {"pos_profile": "Main POS"}.get(k, d),
		)
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.frappe.get_doc", return_value=submitted),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices._ensure_invoice_draft_access("SINV-SUB-1", pos_profile="Main POS")

	def test_ensure_invoice_draft_access_allows_supervisor_on_other_cashier_draft(self):
		other_draft = SimpleNamespace(
			name="SINV-DRAFT-3",
			docstatus=0,
			owner="cashier_b@example.com",
			pos_profile="Main POS",
			get=lambda k, d=None: {"pos_profile": "Main POS"}.get(k, d),
		)
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="manager@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", return_value="manager@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=True),
			patch("pos_next.api.invoices.frappe.get_doc", return_value=other_draft),
		):
			doc = invoices._ensure_invoice_draft_access("SINV-DRAFT-3", pos_profile="Main POS")
			self.assertEqual(doc.name, "SINV-DRAFT-3")

	def test_sanitize_invoice_payload_allowlist_strips_dangerous_fields(self):
		raw = {
			"doctype": "Sales Invoice",
			"pos_profile": "Main POS",
			"customer": "Cust A",
			"owner": "Administrator",
			"docstatus": 1,
			"status": "Paid",
			"debit_to": "Hacked Account",
			"against_income_account": "Evil",
			"packed_items": [{"item_code": "X"}],
			"pos_closing_entry": "PCS-1",
			"items": [
				{
					"item_code": "ITEM-1",
					"qty": 2,
					"rate": 50,
					"income_account": "Injected Account",
					"cost_center": "Injected CC",
				}
			],
			"payments": [
				{
					"mode_of_payment": "Cash",
					"amount": 100,
					"account": "Injected Cash Account",
				}
			],
		}
		cleaned = invoices._strip_server_managed_fields(raw)
		self.assertEqual(cleaned["doctype"], "Sales Invoice")
		self.assertEqual(cleaned["pos_profile"], "Main POS")
		for forbidden in ("owner", "docstatus", "status", "debit_to", "against_income_account", "packed_items", "pos_closing_entry"):
			self.assertNotIn(forbidden, cleaned)
		self.assertNotIn("income_account", cleaned["items"][0])
		self.assertNotIn("cost_center", cleaned["items"][0])
		self.assertNotIn("account", cleaned["payments"][0])
		self.assertEqual(cleaned["payments"][0]["mode_of_payment"], "Cash")

	def test_delete_invoice_blocks_other_cashiers_draft(self):
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
			patch.object(frappe.db, "exists", return_value="SINV-DRAFT-9"),
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(
					docstatus=0, owner="cashier_b@example.com", pos_profile="Main POS", is_pos=1
				),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.delete_invoice("SINV-DRAFT-9")

	def test_get_draft_invoices_blocks_other_cashiers_shift_and_invalid_doctype(self):
		with self.assertRaises(frappe.PermissionError):
			invoices.get_draft_invoices("POSA-OS-1", doctype="User")

		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(user="cashier_b@example.com", pos_profile="Main POS"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.get_draft_invoices("POSA-OS-1")

	def test_validate_return_items_rejects_arbitrary_doctype(self):
		with self.assertRaises(frappe.PermissionError):
			invoices.validate_return_items("SINV-1", [], doctype="User")
