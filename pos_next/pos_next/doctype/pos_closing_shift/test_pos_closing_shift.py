# Copyright (c) 2020, Youssef Restom and Contributors
# See license.txt

import unittest

import frappe

from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import _process_invoice


def _invoice(name, grand_total, paid_amount, net_total=None, qty=1, is_return=0, payments=None):
    """Build a minimal Sales Invoice as_dict() shape for _process_invoice()."""
    return frappe._dict({
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
        "change_amount": 0,
        "base_change_amount": 0,
        "taxes": [],
        "payments": payments or [],
    })


def _empty_summary():
    return {
        "grand_total": 0, "net_total": 0, "total_quantity": 0,
        "returns_total": 0, "returns_count": 0,
        "sales_total": 0, "sales_count": 0,
    }


class TestPOSClosingShift(unittest.TestCase):
    def test_closing_total_reflects_collected_money(self):
        """Net Sales must equal money actually collected, not the full invoice value."""
        summary = _empty_summary()
        payments, taxes = [], []

        # (a) fully-paid sale: 100 collected
        full = _invoice(
            "INV-FULL", grand_total=100, paid_amount=100,
            payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 100, "base_amount": 100})],
        )
        # (b) pure credit sale (Pay-on-Account): nothing collected
        credit = _invoice("INV-CREDIT", grand_total=200, paid_amount=0, payments=[])
        # (c) partial sale: 120 down-payment on a 300 invoice
        partial = _invoice(
            "INV-PARTIAL", grand_total=300, paid_amount=120,
            payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 120, "base_amount": 120})],
        )

        txn_full = _process_invoice(full, "sales_invoice", "USD", "Cash", payments, taxes, summary)
        txn_credit = _process_invoice(credit, "sales_invoice", "USD", "Cash", payments, taxes, summary)
        txn_partial = _process_invoice(partial, "sales_invoice", "USD", "Cash", payments, taxes, summary)

        # Net Sales == collected (100 + 0 + 120), NOT the full 600.
        self.assertEqual(summary["grand_total"], 220)
        self.assertEqual(summary["sales_total"], 220)
        self.assertEqual(summary["sales_count"], 3)
        # Quantity is still the full goods sold (3 lines x 1).
        self.assertEqual(summary["total_quantity"], 3)

        # Cash reconciliation only reflects real payment rows (credit has none).
        cash = next(p for p in payments if p.mode_of_payment == "Cash")
        self.assertEqual(cash.expected_amount, 220)

        # Per-row transaction: grand_total = collected, full value + unpaid preserved.
        self.assertEqual(txn_full["grand_total"], 100)
        self.assertEqual(txn_full["outstanding_amount"], 0)

        self.assertEqual(txn_credit["grand_total"], 0)
        self.assertEqual(txn_credit["invoice_total"], 200)
        self.assertEqual(txn_credit["outstanding_amount"], 200)
        self.assertEqual(txn_credit["transaction_amount"], 200)

        self.assertEqual(txn_partial["grand_total"], 120)
        self.assertEqual(txn_partial["outstanding_amount"], 180)
        self.assertEqual(txn_partial["invoice_total"], 300)

        # Per-row collected amounts sum to the header total (EOD print stays consistent).
        self.assertEqual(
            txn_full["grand_total"] + txn_credit["grand_total"] + txn_partial["grand_total"],
            summary["grand_total"],
        )

    def test_net_total_stays_proportional_to_collected(self):
        """net_total tracks the paid ratio so it never exceeds collected takings."""
        summary = _empty_summary()
        payments, taxes = [], []

        # Half paid on a sale whose net_total differs from grand_total (tax inclusive).
        partial = _invoice(
            "INV-HALF", grand_total=100, paid_amount=50, net_total=90,
            payments=[frappe._dict({"mode_of_payment": "Cash", "amount": 50, "base_amount": 50})],
        )
        _process_invoice(partial, "sales_invoice", "USD", "Cash", payments, taxes, summary)

        self.assertEqual(summary["grand_total"], 50)
        self.assertEqual(summary["net_total"], 45)  # 90 * (50/100)

    def test_credit_return_is_unaffected(self):
        """Credit returns with no payment rows still contribute nothing and skip early."""
        summary = _empty_summary()
        payments, taxes = [], []

        credit_return = _invoice(
            "INV-RET", grand_total=-100, paid_amount=0, is_return=1, payments=[],
        )
        credit_return["return_against"] = "INV-FULL"

        txn = _process_invoice(credit_return, "sales_invoice", "USD", "Cash", payments, taxes, summary)

        self.assertEqual(txn["grand_total"], 0)
        self.assertEqual(summary["grand_total"], 0)
        self.assertEqual(summary["returns_total"], 0)
