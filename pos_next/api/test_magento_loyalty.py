# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

import frappe

from pos_next.api.magento_loyalty import (
	add_magento_lp_on_submit,
	redeem_magento_lp_after_submit,
	redeem_magento_lp_for_invoice,
)
from pos_next.api.wallet import get_customer_wallet_balance, get_wallet_info, validate_wallet_payment


class TestMagentoLoyalty(unittest.TestCase):
	@patch("pos_next.api.wallet.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.wallet.get_lp_balance")
	def test_get_customer_wallet_balance_uses_magento_balance(self, mock_get_lp_balance, _mock_mode):
		mock_get_lp_balance.return_value = {"balance_iqd": 150, "balance_points": 1500}

		balance = get_customer_wallet_balance("CUST-1", "Company A", pos_profile="POS-1")

		self.assertEqual(balance, 150.0)
		mock_get_lp_balance.assert_called_once_with("CUST-1")

	@patch("pos_next.api.wallet.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.wallet.get_pos_settings")
	@patch("pos_next.api.wallet.get_lp_balance")
	def test_get_wallet_info_returns_magento_balance(
		self, mock_get_lp_balance, mock_get_pos_settings, _mock_mode
	):
		mock_get_pos_settings.return_value = {"enable_loyalty_program": 1}
		mock_get_lp_balance.return_value = {"balance_iqd": 75, "balance_points": 750}

		result = get_wallet_info("CUST-1", "Company A", pos_profile="POS-1")

		self.assertTrue(result["wallet_enabled"])
		self.assertTrue(result["magento_loyalty"])
		self.assertEqual(result["wallet_balance"], 75.0)
		self.assertEqual(result["balance_points"], 750.0)

	@patch("pos_next.api.wallet.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.wallet.get_lp_balance")
	def test_validate_wallet_payment_checks_magento_balance(self, mock_get_lp_balance, _mock_mode):
		mock_get_lp_balance.return_value = {"balance_iqd": 50, "balance_points": 500}

		doc = Mock()
		doc.is_pos = 1
		doc.customer = "CUST-1"
		doc.company = "Company A"
		doc.pos_profile = "POS-1"
		doc.name = "SINV-1"
		doc.payments = [Mock(mode_of_payment="Loyalty Points", amount=60)]

		with patch("pos_next.api.wallet.get_wallet_amount_from_payments", return_value=60):
			with patch("pos_next.api.wallet.frappe.db.get_value", return_value=1):
				with self.assertRaises(frappe.ValidationError):
					validate_wallet_payment(doc)

	@patch("pos_next.api.magento_loyalty.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.magento_loyalty.add_lp_points")
	@patch("pos_next.api.magento_loyalty._has_field", return_value=True)
	@patch("pos_next.api.magento_loyalty.frappe.db.get_value", return_value=None)
	@patch("pos_next.api.magento_loyalty.frappe.db.set_value")
	def test_add_magento_lp_on_submit_stores_transaction(
		self,
		mock_set_value,
		_mock_get_value,
		_mock_has_field,
		mock_add_lp_points,
		_mock_mode,
	):
		mock_add_lp_points.return_value = {
			"transaction_id": "TXN-ADD-1",
			"points_added": 12,
			"value_iqd": 100,
		}

		doc = Mock()
		doc.is_pos = 1
		doc.is_return = 0
		doc.customer = "CUST-1"
		doc.pos_profile = "POS-1"
		doc.name = "SINV-1"
		doc.grand_total = 100
		doc.get = Mock(side_effect=lambda key, default=None: {"payments": []}.get(key, default))

		add_magento_lp_on_submit(doc)

		mock_add_lp_points.assert_called_once_with("CUST-1", 100)
		mock_set_value.assert_called_once()

	@patch("pos_next.api.magento_loyalty.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.magento_loyalty.add_lp_points")
	@patch("pos_next.api.magento_loyalty._has_field", return_value=True)
	@patch("pos_next.api.magento_loyalty.frappe.db.get_value", return_value=None)
	@patch("pos_next.api.magento_loyalty.get_wallet_amount_from_payments", return_value=40)
	@patch("pos_next.api.magento_loyalty.frappe.db.set_value")
	def test_add_magento_lp_on_submit_excludes_wallet_payments(
		self,
		mock_set_value,
		_mock_wallet_amount,
		_mock_get_value,
		_mock_has_field,
		mock_add_lp_points,
		_mock_mode,
	):
		mock_add_lp_points.return_value = {
			"transaction_id": "TXN-ADD-1",
			"points_added": 6,
			"value_iqd": 60,
		}

		doc = Mock()
		doc.is_pos = 1
		doc.is_return = 0
		doc.customer = "CUST-1"
		doc.pos_profile = "POS-1"
		doc.name = "SINV-1"
		doc.grand_total = 100
		doc.get = Mock(return_value=[])

		add_magento_lp_on_submit(doc)

		mock_add_lp_points.assert_called_once_with("CUST-1", 60)

	@patch("pos_next.api.magento_loyalty.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.magento_loyalty.add_lp_points")
	@patch("pos_next.api.magento_loyalty._has_field", return_value=True)
	@patch("pos_next.api.magento_loyalty.frappe.db.get_value", return_value="TXN-EXISTING")
	@patch("pos_next.api.magento_loyalty.get_wallet_amount_from_payments", return_value=0)
	def test_add_magento_lp_on_submit_is_idempotent(
		self,
		_mock_wallet_amount,
		_mock_get_value,
		_mock_has_field,
		mock_add_lp_points,
		_mock_mode,
	):
		doc = Mock()
		doc.is_pos = 1
		doc.is_return = 0
		doc.customer = "CUST-1"
		doc.pos_profile = "POS-1"
		doc.name = "SINV-1"
		doc.grand_total = 100
		doc.get = Mock(return_value=[])

		add_magento_lp_on_submit(doc)

		mock_add_lp_points.assert_not_called()

	@patch("pos_next.api.magento_loyalty.is_magento_loyalty_mode", return_value=True)
	@patch("pos_next.api.magento_loyalty.redeem_lp_points")
	@patch("pos_next.api.magento_loyalty.get_wallet_amount_for_sales_invoice", return_value=25)
	@patch("pos_next.api.magento_loyalty._has_field", return_value=True)
	@patch("pos_next.api.magento_loyalty.frappe.db.get_value", return_value=None)
	@patch("pos_next.api.magento_loyalty.frappe.db.set_value")
	def test_redeem_magento_lp_after_submit(
		self,
		mock_set_value,
		_mock_get_value,
		_mock_has_field,
		_mock_wallet_amount,
		mock_redeem_lp_points,
		_mock_mode,
	):
		mock_redeem_lp_points.return_value = {"transaction_id": "TXN-REDEEM-1"}

		invoice_doc = Mock()
		invoice_doc.is_pos = 1
		invoice_doc.is_return = 0
		invoice_doc.customer = "CUST-1"
		invoice_doc.pos_profile = "POS-1"
		invoice_doc.name = "SINV-1"
		invoice_doc.get = Mock(return_value=[])

		redeem_magento_lp_for_invoice(invoice_doc)

		mock_redeem_lp_points.assert_called_once_with("CUST-1", 25)
		mock_set_value.assert_called_once()
