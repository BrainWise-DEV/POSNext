# Copyright (c) 2026, MT
# See license.txt

import unittest

from pos_next.api.invoices import (
    _restore_invoice_payments,
    _snapshot_invoice_payments,
    _sync_invoice_payment_amounts,
)


class _FakePayment(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

    def as_dict(self):
        return dict(self)


class _FakeInvoice:
    def __init__(self, payments=None, conversion_rate=1):
        self.payments = [_FakePayment(payment) for payment in (payments or [])]
        self.conversion_rate = conversion_rate
        self.paid_amount = 0
        self.base_paid_amount = 0

    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        if key == "payments":
            self.payments = [_FakePayment(payment) for payment in value]
        else:
            setattr(self, key, value)

    def append(self, key, value):
        if key != "payments":
            raise AssertionError("Only payments are supported in this fake doc")
        self.payments.append(_FakePayment(value))


class TestInvoicePayments(unittest.TestCase):
    def test_payment_snapshot_and_restore_preserve_amounts(self):
        invoice = _FakeInvoice(
            payments=[
                {
                    "name": "row-1",
                    "mode_of_payment": "Cash",
                    "amount": 200,
                    "base_amount": 200,
                    "account": "1110 - Cash - S",
                    "parent": "ACC-SINV-0001",
                    "doctype": "Sales Invoice Payment",
                }
            ]
        )

        snapshot = _snapshot_invoice_payments(invoice)

        invoice.set(
            "payments",
            [
                {
                    "mode_of_payment": "Cash",
                    "amount": 0,
                    "base_amount": 0,
                },
                {
                    "mode_of_payment": "mBok",
                    "amount": 0,
                    "base_amount": 0,
                },
            ],
        )

        _restore_invoice_payments(invoice, snapshot)

        assert len(invoice.payments) == 1
        assert invoice.payments[0].mode_of_payment == "Cash"
        assert invoice.payments[0].amount == 200
        assert invoice.payments[0].base_amount == 200
        assert invoice.payments[0].account == "1110 - Cash - S"
        assert "parent" not in invoice.payments[0]
        assert "doctype" not in invoice.payments[0]

    def test_sync_invoice_payment_amounts_uses_conversion_rate(self):
        invoice = _FakeInvoice(
            payments=[
                {"mode_of_payment": "Cash", "amount": 100},
                {"mode_of_payment": "Card", "amount": 50, "base_amount": 110},
            ],
            conversion_rate=2,
        )

        _sync_invoice_payment_amounts(invoice)

        assert invoice.payments[0].base_amount == 200
        assert invoice.payments[1].base_amount == 110
        assert invoice.paid_amount == 150
        assert invoice.base_paid_amount == 310
