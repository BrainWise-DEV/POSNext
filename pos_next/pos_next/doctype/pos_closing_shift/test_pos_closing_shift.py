# Copyright (c) 2020, Youssef Restom and Contributors
# See license.txt

"""Tests for POS Closing Shift invoice aggregation and the expense reconciliation seam.

Run via::

	bench --site <site> run-tests --module pos_next.pos_next.doctype.pos_closing_shift.test_pos_closing_shift
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import expenses
from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import (
	_process_invoice,
	make_closing_shift_from_opening,
)

def _invoice(
	name,
	grand_total,
	paid_amount,
	net_total=None,
	qty=1,
	is_return=0,
	payments=None,
	change_amount=0,
	taxes=None,
):
	"""Build a minimal Sales Invoice as_dict() shape for _process_invoice()."""
	return frappe._dict(
		{
			"name": name,
			"posting_date": "2026-06-12",
			"customer": "Test Customer",
			"currency": "USD",
			"conversion_rate": 1,
			"grand_total": grand_total,
			"base_grand_total": grand_total,
			"net_total": net_total if net_total is not None else grand_total,
			"base_net_total": net_total if net_total is not None else grand_total,
			"paid_amount": paid_amount,
			"base_paid_amount": paid_amount,
			"total_qty": qty,
			"is_return": is_return,
			"change_amount": change_amount,
			"base_change_amount": change_amount,
			"taxes": taxes or [],
			"payments": payments or [],
		}
	)


def _empty_summary():
	return {
		"grand_total": 0,
		"net_total": 0,
		"total_quantity": 0,
		"returns_total": 0,
		"returns_count": 0,
		"sales_total": 0,
		"sales_count": 0,
		"collected_total": 0,
		"outstanding_total": 0,
	}


class TestPOSClosingShift(unittest.TestCase):
	def test_collected_and_invoiced_are_tracked_separately(self):
		"""Credit sales must not inflate collected, and must not shrink invoiced."""
		summary = _empty_summary()
		payments, taxes = [], []

		# (a) fully-paid sale: 100 invoiced, 100 collected
		full = _invoice(
			"INV-FULL",
			grand_total=100,
			paid_amount=100,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 100, "base_amount": 100})],
		)
		# (b) pure credit sale (Pay-on-Account): 200 invoiced, nothing collected
		credit = _invoice("INV-CREDIT", grand_total=200, paid_amount=0, payments=[])
		# (c) partial sale: 120 down-payment on a 300 invoice
		partial = _invoice(
			"INV-PARTIAL",
			grand_total=300,
			paid_amount=120,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 120, "base_amount": 120})],
		)

		txn_full = _process_invoice(full, "sales_invoice", "USD", "Cash", payments, taxes, summary)
		txn_credit = _process_invoice(credit, "sales_invoice", "USD", "Cash", payments, taxes, summary)
		txn_partial = _process_invoice(partial, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		# Invoiced figures keep their accrual meaning — unchanged by this feature.
		self.assertEqual(summary["grand_total"], 600)
		self.assertEqual(summary["net_total"], 600)
		self.assertEqual(summary["sales_total"], 600)
		self.assertEqual(summary["sales_count"], 3)
		self.assertEqual(summary["total_quantity"], 3)

		# Cash-basis figures live alongside them.
		self.assertEqual(summary["collected_total"], 220)
		self.assertEqual(summary["outstanding_total"], 380)

		# The three always reconcile: invoiced == collected + outstanding.
		self.assertEqual(summary["collected_total"] + summary["outstanding_total"], summary["grand_total"])

		# Cash reconciliation only reflects real payment rows (credit has none).
		cash = next(p for p in payments if p.mode_of_payment == "Cash")
		self.assertEqual(cash.expected_amount, 220)

		# Per-row: grand_total stays invoiced, collected/outstanding carry the split.
		self.assertEqual(txn_full["grand_total"], 100)
		self.assertEqual(txn_full["collected_amount"], 100)
		self.assertEqual(txn_full["outstanding_amount"], 0)

		self.assertEqual(txn_credit["grand_total"], 200)
		self.assertEqual(txn_credit["collected_amount"], 0)
		self.assertEqual(txn_credit["outstanding_amount"], 200)
		self.assertEqual(txn_credit["transaction_amount"], 200)

		self.assertEqual(txn_partial["grand_total"], 300)
		self.assertEqual(txn_partial["collected_amount"], 120)
		self.assertEqual(txn_partial["outstanding_amount"], 180)

		# Per-row amounts sum to the header totals (EOD print stays consistent).
		rows = (txn_full, txn_credit, txn_partial)
		self.assertEqual(sum(r["grand_total"] for r in rows), summary["grand_total"])
		self.assertEqual(sum(r["collected_amount"] for r in rows), summary["collected_total"])
		self.assertEqual(sum(r["outstanding_amount"] for r in rows), summary["outstanding_total"])

	def test_net_total_stays_accrual(self):
		"""net_total is never scaled by the paid ratio — it stays GL-comparable."""
		summary = _empty_summary()
		payments, taxes = [], []

		# Half paid on a sale whose net_total differs from grand_total (tax inclusive).
		partial = _invoice(
			"INV-HALF",
			grand_total=100,
			paid_amount=50,
			net_total=90,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 50, "base_amount": 50})],
		)
		_process_invoice(partial, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		self.assertEqual(summary["grand_total"], 100)
		self.assertEqual(summary["net_total"], 90)
		self.assertEqual(summary["collected_total"], 50)
		self.assertEqual(summary["outstanding_total"], 50)

	def test_credit_return_is_unaffected(self):
		"""Credit returns with no payment rows still contribute nothing and skip early."""
		summary = _empty_summary()
		payments, taxes = [], []

		credit_return = _invoice(
			"INV-RET",
			grand_total=-100,
			paid_amount=0,
			is_return=1,
			payments=[],
		)
		credit_return["return_against"] = "INV-FULL"

		txn = _process_invoice(credit_return, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		self.assertEqual(txn["grand_total"], 0)
		self.assertEqual(txn["collected_amount"], 0)
		self.assertEqual(txn["outstanding_amount"], 0)
		self.assertEqual(summary["grand_total"], 0)
		self.assertEqual(summary["collected_total"], 0)
		self.assertEqual(summary["outstanding_total"], 0)
		self.assertEqual(summary["returns_total"], 0)

	def test_refund_return_reduces_collected(self):
		"""A refunded return takes money out of the drawer and out of collected."""
		summary = _empty_summary()
		payments, taxes = [], []

		refund = _invoice(
			"INV-REFUND",
			grand_total=-40,
			paid_amount=-40,
			is_return=1,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": -40, "base_amount": -40})],
		)
		refund["return_against"] = "INV-FULL"

		txn = _process_invoice(refund, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		self.assertEqual(txn["grand_total"], -40)
		self.assertEqual(txn["collected_amount"], -40)
		self.assertEqual(txn["outstanding_amount"], 0)
		self.assertEqual(summary["collected_total"], -40)
		self.assertEqual(summary["returns_total"], 40)
		self.assertEqual(summary["returns_count"], 1)
		self.assertEqual(summary["sales_count"], 0)

	def test_change_amount_is_netted_from_collected(self):
		"""Cash tendered above the invoice total (change given back) must not inflate collected."""
		summary = _empty_summary()
		payments, taxes = [], []

		# $15.50 sale paid with a $20 bill -> $4.50 change. Collected is 15.50, not 20.
		sale = _invoice(
			"INV-CHANGE",
			grand_total=15.50,
			paid_amount=20,
			change_amount=4.50,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 20, "base_amount": 20})],
		)
		txn = _process_invoice(sale, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		self.assertEqual(txn["grand_total"], 15.50)
		self.assertEqual(txn["collected_amount"], 15.50)
		# Change is not an unpaid balance — the sale is settled in full.
		self.assertEqual(txn["outstanding_amount"], 0)
		self.assertEqual(summary["collected_total"], 15.50)
		self.assertEqual(summary["outstanding_total"], 0)

		cash = next(p for p in payments if p.mode_of_payment == "Cash")
		self.assertEqual(cash.expected_amount, 15.50)

	def test_taxes_are_not_scaled_by_payment(self):
		"""Tax stays at the invoiced amount so the table reconciles against the VAT accounts."""
		summary = _empty_summary()
		payments, taxes = [], []

		# Half paid on a 110 invoice (100 net + 10 tax).
		partial = _invoice(
			"INV-TAX-PARTIAL",
			grand_total=110,
			paid_amount=55,
			net_total=100,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 55, "base_amount": 55})],
			taxes=[
				frappe._dict({"account_head": "VAT - T", "rate": 10, "tax_amount": 10, "base_tax_amount": 10})
			],
		)
		_process_invoice(partial, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		vat = next(t for t in taxes if t.account_head == "VAT - T")
		self.assertEqual(vat.amount, 10)  # full invoiced tax, posted to the GL in full
		# The accounting identity holds without any scaling.
		self.assertEqual(summary["net_total"] + vat.amount, summary["grand_total"])
		self.assertEqual(summary["collected_total"], 55)

	def test_return_taxes_are_not_scaled(self):
		"""Returns keep the full tax amount."""
		summary = _empty_summary()
		payments, taxes = [], []

		refund = _invoice(
			"INV-TAX-RET",
			grand_total=-110,
			paid_amount=0,
			net_total=-100,
			is_return=1,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": -110, "base_amount": -110})],
			taxes=[
				frappe._dict(
					{"account_head": "VAT - T", "rate": 10, "tax_amount": -10, "base_tax_amount": -10}
				)
			],
		)
		refund["return_against"] = "INV-FULL"
		_process_invoice(refund, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		vat = next(t for t in taxes if t.account_head == "VAT - T")
		self.assertEqual(vat.amount, -10)

	def test_written_off_invoice_keeps_full_net_and_tax(self):
		"""A write-off leaves a residual balance but must not distort net_total or tax.

		Regression guard for the ratio-scaling approach: with `paid_ratio`
		applied, a 100 invoice settled by 90 cash + 10 write-off would have
		reported net_total 90 and tax 0.9 instead of 100 and 1.
		"""
		summary = _empty_summary()
		payments, taxes = [], []

		written_off = _invoice(
			"INV-WRITEOFF",
			grand_total=100,
			paid_amount=90,
			net_total=99,
			payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 90, "base_amount": 90})],
			taxes=[
				frappe._dict({"account_head": "VAT - T", "rate": 1, "tax_amount": 1, "base_tax_amount": 1})
			],
		)
		txn = _process_invoice(written_off, "sales_invoice", "USD", "Cash", payments, taxes, summary)

		self.assertEqual(txn["grand_total"], 100)
		self.assertEqual(txn["collected_amount"], 90)
		self.assertEqual(txn["outstanding_amount"], 10)

		self.assertEqual(summary["net_total"], 99)
		vat = next(t for t in taxes if t.account_head == "VAT - T")
		self.assertEqual(vat.amount, 1)
		self.assertEqual(summary["net_total"] + vat.amount, summary["grand_total"])


class TestClosingShiftExpenseAggregation(FrappeTestCase):
	"""T4 — expenses meet payment_reconciliation and total_pos_expenses.

	Also guards H4's desync: a JE cancelled while the shift is still open must
	drop out of closing totals so drawer maths and the audit child table agree.
	"""

	COMPANY = "_Test Company"
	EXPENSE_ACCOUNT = "Travel Expenses - _TC"
	COST_CENTER = "Main - _TC"
	MODE_OF_PAYMENT = "Cash"
	PROFILE = "_PNXT_TEST_POS_PROFILE__Test Company"
	PERIOD_START = "2026-09-08 22:00:00"
	OPENING_AMOUNT = 100
	EXPENSE_AMOUNT = 30

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _make_opening_shift(self):
		shift = frappe.get_doc(
			{
				"doctype": "POS Opening Shift",
				"period_start_date": self.PERIOD_START,
				"posting_date": "2026-09-08",
				"company": self.COMPANY,
				"pos_profile": self.PROFILE,
				"user": frappe.session.user,
				"balance_details": [
					{"mode_of_payment": self.MODE_OF_PAYMENT, "amount": self.OPENING_AMOUNT}
				],
			}
		)
		shift.insert()
		shift.submit()
		return shift

	def _create_expense(self, shift, amount, remarks="Fuel"):
		frappe.db.set_value("POS Profile", self.PROFILE, "cost_center", self.COST_CENTER)
		payment_account = expenses._resolve_payment_account(self.MODE_OF_PAYMENT, self.COMPANY)
		return expenses._create_expense_journal_entry(
			company=self.COMPANY,
			expense_account=self.EXPENSE_ACCOUNT,
			payment_account=payment_account,
			amount=amount,
			cost_center=self.COST_CENTER,
			pos_opening_shift=shift.name,
			pos_profile=self.PROFILE,
			mode_of_payment=self.MODE_OF_PAYMENT,
			employee=None,
			remarks=remarks,
			period_start_date=shift.period_start_date,
		)

	def _closing_from(self, shift):
		opening_json = json.dumps(frappe.get_doc("POS Opening Shift", shift.name).as_dict(), default=str)
		return make_closing_shift_from_opening(opening_json)

	def _cash_row(self, closing):
		return next(p for p in closing["payment_reconciliation"] if p["mode_of_payment"] == self.MODE_OF_PAYMENT)

	def test_expenses_reduce_expected_and_drive_totals(self):
		"""Submitted expenses land in pos_expenses, total_pos_expenses, and expected cash."""
		shift = self._make_opening_shift()
		je_name = self._create_expense(shift, self.EXPENSE_AMOUNT)

		closing = self._closing_from(shift)

		self.assertEqual(flt(closing["total_pos_expenses"]), self.EXPENSE_AMOUNT)
		self.assertEqual(flt(closing["expenses_total"]), self.EXPENSE_AMOUNT)
		self.assertEqual(closing["expenses_count"], 1)

		self.assertEqual(len(closing["pos_expenses"]), 1)
		row = closing["pos_expenses"][0]
		self.assertEqual(row["journal_entry"], je_name)
		self.assertEqual(row["expense_account"], self.EXPENSE_ACCOUNT)
		self.assertEqual(flt(row["amount"]), self.EXPENSE_AMOUNT)
		self.assertEqual(flt(row["amount"]), flt(closing["total_pos_expenses"]))

		cash = self._cash_row(closing)
		self.assertEqual(flt(cash["opening_amount"]), self.OPENING_AMOUNT)
		self.assertEqual(flt(cash["expected_amount"]), self.OPENING_AMOUNT - self.EXPENSE_AMOUNT)

	def test_cancelled_expense_excluded_while_shift_open(self):
		"""H4 seam: cancel before close → closing no longer counts the JE."""
		shift = self._make_opening_shift()
		je_name = self._create_expense(shift, self.EXPENSE_AMOUNT)

		# Sanity: expense is present before cancel.
		before = self._closing_from(shift)
		self.assertEqual(flt(before["total_pos_expenses"]), self.EXPENSE_AMOUNT)
		self.assertEqual(flt(self._cash_row(before)["expected_amount"]), self.OPENING_AMOUNT - self.EXPENSE_AMOUNT)

		frappe.get_doc("Journal Entry", je_name).cancel()

		after = self._closing_from(shift)
		self.assertEqual(flt(after["total_pos_expenses"]), 0)
		self.assertEqual(flt(after["expenses_total"]), 0)
		self.assertEqual(after["expenses_count"], 0)
		self.assertEqual(after["pos_expenses"], [])
		self.assertEqual(flt(self._cash_row(after)["expected_amount"]), self.OPENING_AMOUNT)

	def test_multiple_expenses_sum_into_reconciliation(self):
		"""Two submitted expenses aggregate into one total and one expected reduction."""
		shift = self._make_opening_shift()
		self._create_expense(shift, 20, remarks="Fuel")
		self._create_expense(shift, 15, remarks="Parking")

		closing = self._closing_from(shift)

		self.assertEqual(flt(closing["total_pos_expenses"]), 35)
		self.assertEqual(closing["expenses_count"], 2)
		self.assertEqual(len(closing["pos_expenses"]), 2)
		self.assertEqual(sum(flt(r["amount"]) for r in closing["pos_expenses"]), 35)
		self.assertEqual(flt(self._cash_row(closing)["expected_amount"]), self.OPENING_AMOUNT - 35)
