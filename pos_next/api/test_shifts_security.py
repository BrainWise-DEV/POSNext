# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import shifts
from pos_next.pos_next.doctype.pos_closing_shift import pos_closing_shift as pcs


class TestClosingShiftSecurity(FrappeTestCase):
	def test_submit_closing_shift_rejects_arbitrary_doctype(self):
		payload = json.dumps(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": "Test Co",
			}
		)
		with self.assertRaises(frappe.PermissionError):
			pcs.submit_closing_shift(payload)

		with self.assertRaises(frappe.PermissionError):
			shifts.submit_closing_shift(payload)

	def test_submit_closing_shift_rejects_closing_another_users_shift(self):
		opening = SimpleNamespace(
			name="POSA-OS-001",
			user="cashier_b@example.com",
			pos_profile="Main POS",
			company="Test Co",
			period_start_date="2026-11-24 08:00:00",
			status="Open",
			docstatus=1,
		)
		payload = json.dumps(
			{
				"doctype": "POS Closing Shift",
				"pos_opening_shift": "POSA-OS-001",
				"user": "cashier_a@example.com",
			}
		)
		with (
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.is_pos_supervisor", return_value=False),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.get_doc", return_value=opening),
		):
			with self.assertRaises(frappe.PermissionError):
				pcs.submit_closing_shift(payload)

	def test_submit_closing_shift_allows_supervisor_to_close_cashier_shift_with_authoritative_fields(self):
		opening = SimpleNamespace(
			name="POSA-OS-002",
			user="cashier_b@example.com",
			pos_profile="Real Profile",
			company="Real Company",
			period_start_date="2026-11-24 08:00:00",
			status="Open",
			docstatus=1,
		)
		computed = {
			"period_end_date": "2026-11-24 16:00:00",
			"grand_total": 500,
			"net_total": 500,
			"collected_amount": 500,
			"outstanding_total": 0,
			"total_quantity": 5,
			"total_pos_expenses": 0,
			"pos_transactions": [],
			"payment_reconciliation": [
				{"mode_of_payment": "Cash", "opening_amount": 100, "expected_amount": 600}
			],
			"taxes": [],
			"pos_payments": [],
			"pos_expenses": [],
		}
		fake_doc = MagicMock()
		fake_doc.name = "POSA-CS-001"

		# Attacker tries to spoof user, pos_profile, company, and expected_amount
		payload = json.dumps(
			{
				"doctype": "POS Closing Shift",
				"pos_opening_shift": "POSA-OS-002",
				"posting_date": "2026-11-24",
				"user": "spoofed@example.com",
				"pos_profile": "Spoofed Profile",
				"company": "Spoofed Co",
				"payment_reconciliation": [
					{"mode_of_payment": "Cash", "expected_amount": 0, "closing_amount": 595}
				],
			}
		)

		with (
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.ensure_desk_user", return_value="supervisor@example.com"),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.is_pos_supervisor", return_value=True),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.get_doc", return_value=opening),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.make_closing_shift_from_opening", return_value=computed),
			patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.new_doc", return_value=fake_doc),
		):
			result = pcs.submit_closing_shift(payload)

		self.assertEqual(result, "POSA-CS-001")
		update_args = fake_doc.update.call_args[0][0]
		self.assertEqual(update_args["user"], "cashier_b@example.com")
		self.assertEqual(update_args["pos_profile"], "Real Profile")
		self.assertEqual(update_args["company"], "Real Company")
		# Verify expected_amount stayed 600 (server-computed), while closing_amount came from caller (595)
		recon_calls = [c for c in fake_doc.set.call_args_list if c[0][0] == "payment_reconciliation"]
		self.assertEqual(len(recon_calls), 1)
		self.assertEqual(recon_calls[0][0][1][0]["expected_amount"], 600.0)
		self.assertEqual(recon_calls[0][0][1][0]["closing_amount"], 595.0)
		fake_doc.insert.assert_called_once_with()
		fake_doc.submit.assert_called_once_with()

	def test_validate_enforces_owner_and_overwrites_spoofed_fields(self):
		opening = frappe._dict(
			name="POSA-OS-003",
			user="cashier_b@example.com",
			pos_profile="Real Profile",
			company="Real Company",
			period_start_date="2026-11-24 08:00:00",
			status="Open",
			docstatus=1,
		)
		doc = pcs.POSClosingShift.__new__(pcs.POSClosingShift)
		doc.name = "POSA-CS-NEW"
		doc.pos_opening_shift = "POSA-OS-003"
		doc.user = "spoofed@example.com"
		doc.pos_profile = "Spoofed Profile"
		doc.company = "Spoofed Co"
		doc.payment_reconciliation = []

		# Non-owner non-supervisor rejected
		orig_user = frappe.session.user
		try:
			frappe.session.user = "cashier_a@example.com"
			with (
				patch.object(frappe.db, "get_value", return_value=opening),
				patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.is_pos_supervisor", return_value=False),
			):
				with self.assertRaises(frappe.PermissionError):
					doc.validate()

			# Supervisor allowed, and spoofed user/profile/company are overwritten from opening shift
			frappe.session.user = "manager@example.com"
			with (
				patch.object(frappe.db, "get_value", return_value=opening),
				patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.is_pos_supervisor", return_value=True),
				patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.get_all", return_value=[]),
			):
				doc.validate()
		finally:
			frappe.session.user = orig_user

		self.assertEqual(doc.user, "cashier_b@example.com")
		self.assertEqual(doc.pos_profile, "Real Profile")
		self.assertEqual(doc.company, "Real Company")

	def test_check_opening_shift_blocks_non_supervisor_querying_other_user(self):
		with (
			patch("pos_next.api.shifts.ensure_desk_user", return_value="cashier_a@example.com"),
			patch("pos_next.api.shifts.is_pos_supervisor", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				shifts.check_opening_shift(user="cashier_b@example.com")

	def test_check_opening_shift_allows_supervisor_querying_other_user(self):
		with (
			patch("pos_next.api.shifts.ensure_desk_user", return_value="manager@example.com"),
			patch("pos_next.api.shifts.is_pos_supervisor", return_value=True),
			patch("pos_next.api.shifts.frappe.db.get_all", return_value=[]),
		):
			self.assertIsNone(shifts.check_opening_shift(user="cashier_b@example.com"))

	def test_get_pos_invoices_rejects_invalid_doctype(self):
		opening = SimpleNamespace(name="POSA-OS-004", user="Administrator")
		with patch("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.get_doc", return_value=opening):
			with self.assertRaises(frappe.PermissionError):
				pcs.get_pos_invoices("POSA-OS-004", doctype="Sales Invoice` WHERE 1=1 --")
