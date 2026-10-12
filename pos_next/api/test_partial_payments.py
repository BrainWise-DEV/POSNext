# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import partial_payments


class TestPaymentJoinsTheCashiersShift(unittest.TestCase):
	def pay(self, open_shift, payments):
		with (
			patch.object(partial_payments.frappe, "has_permission", return_value=True),
			patch.object(
				partial_payments.frappe, "get_doc", return_value=SimpleNamespace(outstanding_amount=500)
			),
			patch.object(partial_payments.frappe.db, "get_value", return_value=open_shift),
			patch.object(partial_payments, "create_payment_entry", return_value="PE-1") as create,
			patch.object(partial_payments, "get_partial_payment_details", return_value={}),
		):
			partial_payments.add_payment_to_partial_invoice("SINV-1", payments)
		return [call.kwargs["reference_no"] for call in create.call_args_list]

	def test_reference_is_the_open_shift_so_its_closing_counts_the_money(self):
		cash = {"mode_of_payment": "Cash", "amount": 100}
		self.assertEqual(self.pay("POSA-OS-1", [cash]), ["POSA-OS-1"])

	def test_a_reference_typed_by_the_cashier_is_kept(self):
		transfer = {"mode_of_payment": "Bank", "amount": 100, "reference_no": "TRF-9"}
		self.assertEqual(self.pay("POSA-OS-1", [transfer]), ["TRF-9"])

	def test_without_an_open_shift_nothing_is_linked(self):
		cash = {"mode_of_payment": "Cash", "amount": 100}
		self.assertEqual(self.pay(None, [cash]), [None])
