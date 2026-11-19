"""Regression checks for shift-tagged invoice payments."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from pos_next.api.partial_payments import create_payment_entry
from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import get_payments_entries


class TestShiftTaggedPartialPayments(unittest.TestCase):
	def setUp(self):
		self.invoice = MagicMock(
			docstatus=1,
			outstanding_amount=500,
			posting_date="2026-01-01",
			company="Test Company",
		)
		self.payment_entry = MagicMock(name="PAY-1")
		self.payment_entry.name = "PAY-1"
		self.frappe_patch = patch("pos_next.api.partial_payments.frappe")
		self.mock_frappe = self.frappe_patch.start()
		self.addCleanup(self.frappe_patch.stop)
		self.mock_frappe.DoesNotExistError = frappe.DoesNotExistError
		self.mock_frappe.ValidationError = frappe.ValidationError
		self.mock_frappe.get_doc.return_value = self.invoice
		self.mock_frappe.session.user = "cashier@example.com"
		self.mock_frappe.throw.side_effect = lambda message: self.fail(message)
		self.payment_patch = patch(
			"erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
			return_value=self.payment_entry,
		)
		self.get_payment_entry = self.payment_patch.start()
		self.addCleanup(self.payment_patch.stop)

	def pay(self, shift, shift_record):
		def exists(doctype, filters):
			if doctype == "POS Opening Shift":
				return shift_record and all(shift_record.get(key) == value for key, value in filters.items())
			return True

		self.mock_frappe.db.exists.side_effect = exists
		return create_payment_entry(
			"INV-1", 100, payment_account="Cash Account", posting_date="2026-01-02", pos_opening_shift=shift
		)

	def test_open_cashier_shift_is_found_by_closing(self):
		shift = "SHIFT-1"
		result = self.pay(
			shift, {"name": shift, "user": "cashier@example.com", "status": "Open", "docstatus": 1}
		)
		self.assertEqual(result, "PAY-1")
		self.assertEqual(self.payment_entry.reference_no, shift)
		self.get_payment_entry.assert_called_once()
		self.payment_entry.insert.assert_called_once()
		self.payment_entry.submit.assert_called_once()

		with patch(
			"pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift.frappe.get_all",
			return_value=[self.payment_entry],
		) as get_all:
			self.assertEqual(get_payments_entries(shift), [self.payment_entry])
			self.assertEqual(
				get_all.call_args.kwargs["filters"]["reference_no"], self.payment_entry.reference_no
			)

	def test_invalid_shifts_are_rejected_before_creating_payment_entry(self):
		valid = {"name": "SHIFT-1", "user": "cashier@example.com", "status": "Open", "docstatus": 1}
		for record in (
			None,
			{**valid, "status": "Closed"},
			{**valid, "user": "other@example.com"},
			{**valid, "docstatus": 0},
		):
			with self.subTest(record=record):

				def reject(message):
					raise ValueError(message)

				self.mock_frappe.throw.side_effect = reject
				with self.assertRaisesRegex(ValueError, "Reload POS and try again"):
					self.pay("SHIFT-1", record)
				self.get_payment_entry.assert_not_called()

	def test_no_shift_keeps_invoice_reference(self):
		result = self.pay(None, None)
		self.assertEqual(result, "PAY-1")
		self.assertEqual(self.payment_entry.reference_no, "POS-INV-1")
