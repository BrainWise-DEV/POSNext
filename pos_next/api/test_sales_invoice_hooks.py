# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from pos_next.api.sales_invoice_hooks import (
	auto_assign_loyalty_program_on_invoice,
	sync_return_loyalty_program,
)
from pos_next.overrides.sales_invoice import CustomSalesInvoice


def _invoice(**kwargs):
	doc = Mock()
	defaults = {
		"is_return": 0,
		"is_pos": 1,
		"pos_profile": "POS-A",
		"customer": "CUST-1",
		"loyalty_program": None,
		"return_against": None,
	}
	defaults.update(kwargs)
	doc.configure_mock(**defaults)
	doc.get.side_effect = lambda key, default=None: defaults.get(key, default)
	return doc


class TestSyncReturnLoyaltyProgram(unittest.TestCase):
	def test_noop_when_not_a_return(self):
		doc = _invoice(is_return=0, loyalty_program="LP-FROM-CUSTOMER")

		sync_return_loyalty_program(doc)

		self.assertEqual(doc.loyalty_program, "LP-FROM-CUSTOMER")

	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_clears_program_when_original_invoice_has_none(self, mock_frappe):
		mock_frappe.db.get_value.return_value = None
		doc = _invoice(
			is_return=1,
			return_against="SINV-0001",
			loyalty_program="LP-FROM-CUSTOMER",
		)

		sync_return_loyalty_program(doc)

		mock_frappe.db.get_value.assert_called_once_with(
			"Sales Invoice", "SINV-0001", "loyalty_program"
		)
		self.assertIsNone(doc.loyalty_program)

	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_copies_program_from_original_invoice(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "LP-ORIGINAL"
		doc = _invoice(
			is_return=1,
			return_against="SINV-0001",
			loyalty_program="LP-FROM-CUSTOMER",
		)

		sync_return_loyalty_program(doc)

		self.assertEqual(doc.loyalty_program, "LP-ORIGINAL")

	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_prod_credit_note_clears_fetched_test_program(self, mock_frappe):
		"""ACC-SINV-2026-40386 against ACC-SINV-2026-32482: customer fetch set Test."""
		mock_frappe.db.get_value.return_value = None
		doc = _invoice(
			is_return=1,
			is_pos=0,
			pos_profile=None,
			is_consolidated=0,
			redeem_loyalty_points=0,
			customer="CUST-2026-44860",
			return_against="ACC-SINV-2026-32482",
			loyalty_program="Test",
		)

		sync_return_loyalty_program(doc)

		self.assertIsNone(doc.loyalty_program)
		mock_frappe.db.get_value.assert_called_once_with(
			"Sales Invoice", "ACC-SINV-2026-32482", "loyalty_program"
		)


class TestAutoAssignLoyaltyProgramOnInvoice(unittest.TestCase):
	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_skips_returns(self, mock_frappe):
		doc = _invoice(is_return=1, return_against="SINV-0001")

		auto_assign_loyalty_program_on_invoice(doc)

		mock_frappe.db.get_value.assert_not_called()
		self.assertIsNone(doc.loyalty_program)

	@patch("pos_next.integrations.registry.is_external_loyalty_mode", return_value=True)
	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_skips_magento_loyalty_mode(self, mock_frappe, _mock_magento):
		doc = _invoice()

		auto_assign_loyalty_program_on_invoice(doc)

		mock_frappe.db.get_value.assert_not_called()

	@patch("pos_next.integrations.registry.is_external_loyalty_mode", return_value=False)
	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_stamps_invoice_when_customer_already_enrolled(self, mock_frappe, _mock_magento):
		mock_frappe.db.get_value.return_value = "LP-CUSTOMER"
		doc = _invoice(loyalty_program=None)

		auto_assign_loyalty_program_on_invoice(doc)

		self.assertEqual(doc.loyalty_program, "LP-CUSTOMER")
		mock_frappe.db.get_value.assert_called_once_with("Customer", "CUST-1", "loyalty_program")


class TestMakeLoyaltyPointEntryGuard(unittest.TestCase):
	@patch.object(SalesInvoice, "make_loyalty_point_entry")
	def test_skips_super_when_program_is_missing(self, mock_super):
		invoice = CustomSalesInvoice.__new__(CustomSalesInvoice)
		invoice.loyalty_program = None

		invoice.make_loyalty_point_entry()

		mock_super.assert_not_called()

	@patch.object(SalesInvoice, "make_loyalty_point_entry")
	def test_calls_super_when_program_is_set(self, mock_super):
		invoice = CustomSalesInvoice.__new__(CustomSalesInvoice)
		invoice.loyalty_program = "LP-1"

		invoice.make_loyalty_point_entry()

		mock_super.assert_called_once_with()

	@patch.object(SalesInvoice, "set_loyalty_program_tier")
	def test_skips_tier_update_when_program_is_missing(self, mock_super):
		invoice = CustomSalesInvoice.__new__(CustomSalesInvoice)
		invoice.loyalty_program = None

		invoice.set_loyalty_program_tier()

		mock_super.assert_not_called()

	@patch.object(SalesInvoice, "on_submit")
	@patch("pos_next.api.sales_invoice_hooks.frappe")
	def test_on_submit_clears_test_program_before_erpnext_loyalty(self, mock_frappe, mock_super):
		mock_frappe.db.get_value.return_value = None
		invoice = CustomSalesInvoice.__new__(CustomSalesInvoice)
		invoice.is_return = 1
		invoice.return_against = "ACC-SINV-2026-32482"
		invoice.loyalty_program = "Test"

		invoice.on_submit()

		self.assertIsNone(invoice.loyalty_program)
		mock_super.assert_called_once_with()
