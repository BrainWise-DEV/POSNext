# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pos_next.api import wallet as api_wallet
from pos_next.pos_next.doctype.wallet import wallet as wallet_doctype


class TestWalletAPI(unittest.TestCase):
	@patch("pos_next.api.wallet.frappe.db")
	@patch("pos_next.api.wallet.frappe.get_all")
	def test_get_pending_wallet_payments_only_counts_draft_wallet_payments_in_same_company(
		self,
		mock_get_all,
		mock_db,
	):
		mock_get_all.side_effect = [
			[
				SimpleNamespace(name="DRAFT-SAME"),
				SimpleNamespace(name="EXCLUDED-DRAFT"),
			],
			[
				SimpleNamespace(mode_of_payment="Wallet", amount=40),
				SimpleNamespace(mode_of_payment="Cash", amount=10),
			],
		]
		mock_db.get_value.side_effect = lambda doctype, name, field: 1 if name == "Wallet" else 0

		result = api_wallet.get_pending_wallet_payments(
			"Guest",
			exclude_invoice="EXCLUDED-DRAFT",
			company="Sonex",
		)

		self.assertEqual(result, 40)
		self.assertEqual(mock_get_all.call_count, 2)
		self.assertEqual(
			mock_get_all.call_args_list[0].kwargs["filters"],
			{
				"customer": "Guest",
				"docstatus": 0,
				"outstanding_amount": [">", 0],
				"is_pos": 1,
				"company": "Sonex",
			},
		)

	@patch("pos_next.pos_next.doctype.wallet.wallet.get_pending_wallet_payments")
	def test_wallet_get_available_balance_passes_company_to_pending_reservations(self, mock_pending):
		mock_pending.return_value = 25
		wallet = Mock()
		wallet.customer = "Guest"
		wallet.company = "Sonex"
		wallet.get_balance.return_value = 100

		result = wallet_doctype.Wallet.get_available_balance(wallet)

		self.assertEqual(result, 75)
		mock_pending.assert_called_once_with("Guest", company="Sonex")

	@patch("pos_next.pos_next.doctype.wallet.wallet.frappe.db")
	@patch("pos_next.pos_next.doctype.wallet.wallet.frappe.get_all")
	def test_doctype_pending_wallet_payments_uses_draft_only_and_company_scope(
		self,
		mock_get_all,
		mock_db,
	):
		mock_get_all.side_effect = [
			[SimpleNamespace(name="DRAFT-SAME")],
			[SimpleNamespace(mode_of_payment="Wallet", amount=55)],
		]
		mock_db.get_value.return_value = 1

		result = wallet_doctype.get_pending_wallet_payments("Guest", company="Sonex")

		self.assertEqual(result, 55)
		self.assertEqual(
			mock_get_all.call_args_list[0].kwargs["filters"],
			{
				"customer": "Guest",
				"docstatus": 0,
				"outstanding_amount": [">", 0],
				"is_pos": 1,
				"company": "Sonex",
			},
		)
