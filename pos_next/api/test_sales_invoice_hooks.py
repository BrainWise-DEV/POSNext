# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.api.sales_invoice_hooks import on_cancel, rollback_coupon_usage


class TestSalesInvoiceHooks(unittest.TestCase):
	@patch("pos_next.api.sales_invoice_hooks.frappe.db")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.decrement_coupon_usage")
	def test_rollback_coupon_usage_for_cancelled_invoice(self, mock_decrement, mock_db):
		doc = Mock()
		doc.get.side_effect = lambda key, default=None: {
			"is_return": 0,
			"coupon_code": "SAVE10",
		}.get(key, default)
		doc.name = "ACC-SINV-0001"
		mock_db.table_exists.return_value = True

		rollback_coupon_usage(doc)

		mock_decrement.assert_called_once_with("SAVE10")

	@patch("pos_next.api.sales_invoice_hooks.frappe.db")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.decrement_coupon_usage")
	def test_rollback_coupon_usage_skips_invoices_without_coupon(self, mock_decrement, mock_db):
		doc = Mock()
		doc.get.side_effect = lambda key, default=None: {
			"is_return": 0,
			"coupon_code": None,
		}.get(key, default)

		rollback_coupon_usage(doc)

		mock_db.table_exists.assert_not_called()
		mock_decrement.assert_not_called()

	@patch("pos_next.api.sales_invoice_hooks.frappe.db")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.decrement_coupon_usage")
	def test_rollback_coupon_usage_skips_return_invoices(self, mock_decrement, mock_db):
		doc = Mock()
		doc.get.side_effect = lambda key, default=None: {
			"is_return": 1,
			"coupon_code": "SAVE10",
		}.get(key, default)

		rollback_coupon_usage(doc)

		mock_db.table_exists.assert_not_called()
		mock_decrement.assert_not_called()

	@patch("pos_next.api.sales_invoice_hooks.frappe.db")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.decrement_coupon_usage")
	def test_rollback_coupon_usage_skips_when_coupon_table_missing(self, mock_decrement, mock_db):
		doc = Mock()
		doc.get.side_effect = lambda key, default=None: {
			"is_return": 0,
			"coupon_code": "SAVE10",
		}.get(key, default)
		mock_db.table_exists.return_value = False

		rollback_coupon_usage(doc)

		mock_decrement.assert_not_called()

	@patch("pos_next.api.sales_invoice_hooks.rollback_coupon_usage")
	def test_on_cancel_delegates_to_coupon_rollback(self, mock_rollback):
		doc = Mock()

		on_cancel(doc)

		mock_rollback.assert_called_once_with(doc)
