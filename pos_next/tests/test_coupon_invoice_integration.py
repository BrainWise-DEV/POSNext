# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Suite for Coupon Code Integration with Sales Invoice

This module tests the native ERPNext coupon_code field integration on Sales Invoice:
- Coupon validation on invoice validate
- Coupon usage counter increment on submit
- Coupon usage counter decrement on cancel

Run with: bench --site [site] run-tests --app pos_next --module pos_next.tests.test_coupon_invoice_integration
"""

import frappe
import unittest
from frappe.utils import nowdate, add_months, flt


class TestCouponInvoiceIntegration(unittest.TestCase):
	"""Test coupon_code field integration with Sales Invoice"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		# Get test company
		cls.test_company = frappe.get_all("Company", limit=1)[0].name

		# Get test customer
		customers = frappe.get_all("Customer", limit=1)
		cls.test_customer = customers[0].name if customers else None

		# Get test item
		items = frappe.get_all("Item", filters={"is_sales_item": 1}, limit=1)
		cls.test_item = items[0].name if items else None

		# Get default income account
		cls.income_account = frappe.db.get_value(
			"Company", cls.test_company, "default_income_account"
		)

		# Track created docs for cleanup
		cls.created_coupons = []
		cls.created_pricing_rules = []
		cls.created_invoices = []

		# Create a test Pricing Rule and Coupon Code
		cls._create_test_coupon()

	@classmethod
	def _create_test_coupon(cls):
		"""Create a test coupon for testing"""
		# Create Pricing Rule
		pricing_rule = frappe.get_doc({
			"doctype": "Pricing Rule",
			"title": "Test Coupon PR",
			"apply_on": "Transaction",
			"price_or_product_discount": "Price",
			"rate_or_discount": "Discount Amount",
			"discount_amount": 10,
			"selling": 1,
			"company": cls.test_company,
			"currency": frappe.get_cached_value("Company", cls.test_company, "default_currency"),
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 12),
			"coupon_code_based": 1,
		})
		pricing_rule.insert(ignore_permissions=True)
		cls.created_pricing_rules.append(pricing_rule.name)

		# Create Coupon Code
		cls.test_coupon_code = "TESTCOUPON2024"
		coupon = frappe.get_doc({
			"doctype": "Coupon Code",
			"coupon_name": "Test Coupon",
			"coupon_type": "Promotional",
			"coupon_code": cls.test_coupon_code,
			"pricing_rule": pricing_rule.name,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 12),
			"maximum_use": 100,
			"used": 0,
		})
		coupon.insert(ignore_permissions=True)
		cls.created_coupons.append(coupon.name)
		cls.test_coupon_name = coupon.name

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		# Cancel and delete invoices first
		for invoice_name in cls.created_invoices:
			try:
				invoice = frappe.get_doc("Sales Invoice", invoice_name)
				if invoice.docstatus == 1:
					invoice.cancel()
				frappe.delete_doc("Sales Invoice", invoice_name, force=True)
			except Exception:
				pass

		# Delete coupons
		for coupon_name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", coupon_name, force=True)
			except Exception:
				pass

		# Delete pricing rules
		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def _create_invoice_with_coupon(self, coupon_code, submit=False):
		"""Helper to create a Sales Invoice with coupon_code"""
		if not self.test_customer or not self.test_item:
			self.skipTest("Missing test customer or item")

		invoice = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.test_customer,
			"company": self.test_company,
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"coupon_code": coupon_code,
			"items": [{
				"item_code": self.test_item,
				"qty": 1,
				"rate": 100,
				"income_account": self.income_account,
			}],
		})

		invoice.insert(ignore_permissions=True)
		self.created_invoices.append(invoice.name)

		if submit:
			invoice.submit()

		return invoice

	def test_coupon_code_field_exists(self):
		"""Test that coupon_code custom field exists on Sales Invoice"""
		# Check if the field exists in the doctype
		has_field = frappe.db.exists("Custom Field", {
			"dt": "Sales Invoice",
			"fieldname": "coupon_code"
		})

		self.assertTrue(has_field, "coupon_code custom field should exist on Sales Invoice")

	def test_coupon_code_is_link_field(self):
		"""Test that coupon_code is a Link field to Coupon Code"""
		field = frappe.get_doc("Custom Field", "Sales Invoice-coupon_code")

		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Coupon Code")

	def test_validate_coupon_on_invoice(self):
		"""Test that valid coupon passes validation"""
		# This should not raise an exception
		invoice = self._create_invoice_with_coupon(self.test_coupon_name)

		self.assertEqual(invoice.coupon_code, self.test_coupon_name)

	def test_coupon_usage_increment_on_submit(self):
		"""Test that coupon usage counter increments on invoice submit"""
		# Get initial usage count
		initial_used = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")

		# Create and submit invoice with coupon
		invoice = self._create_invoice_with_coupon(self.test_coupon_name, submit=True)

		# Check usage count increased
		new_used = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")
		self.assertEqual(new_used, initial_used + 1, "Coupon usage should increment on submit")

	def test_coupon_usage_decrement_on_cancel(self):
		"""Test that coupon usage counter decrements on invoice cancel"""
		# Create and submit invoice with coupon
		invoice = self._create_invoice_with_coupon(self.test_coupon_name, submit=True)

		# Get usage count after submit
		used_after_submit = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")

		# Cancel the invoice
		invoice.cancel()

		# Check usage count decreased
		used_after_cancel = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")
		self.assertEqual(
			used_after_cancel, used_after_submit - 1,
			"Coupon usage should decrement on cancel"
		)

	def test_no_increment_without_coupon(self):
		"""Test that usage doesn't change for invoices without coupon"""
		# Get initial usage count
		initial_used = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")

		# Create invoice WITHOUT coupon
		if not self.test_customer or not self.test_item:
			self.skipTest("Missing test customer or item")

		invoice = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.test_customer,
			"company": self.test_company,
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": [{
				"item_code": self.test_item,
				"qty": 1,
				"rate": 100,
				"income_account": self.income_account,
			}],
		})
		invoice.insert(ignore_permissions=True)
		self.created_invoices.append(invoice.name)
		invoice.submit()

		# Check usage count unchanged
		new_used = frappe.db.get_value("Coupon Code", self.test_coupon_name, "used")
		self.assertEqual(new_used, initial_used, "Coupon usage should not change for invoices without coupon")

		# Cleanup
		invoice.cancel()


class TestLegacyPosaCouponCodeCompatibility(unittest.TestCase):
	"""Test backwards compatibility with posa_coupon_code field"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		customers = frappe.get_all("Customer", limit=1)
		cls.test_customer = customers[0].name if customers else None

	def test_posa_coupon_code_field_exists(self):
		"""Test that legacy posa_coupon_code field still exists"""
		has_field = frappe.db.exists("Custom Field", {
			"dt": "Sales Invoice",
			"fieldname": "posa_coupon_code"
		})

		self.assertTrue(has_field, "posa_coupon_code field should exist for backwards compatibility")

	def test_gift_cards_can_read_both_fields(self):
		"""Test that gift_cards.py logic handles both fields"""
		# This tests the getattr pattern used in gift_cards.py
		from pos_next.api.gift_cards import process_gift_card_on_submit

		# Create a mock invoice object
		class MockInvoice:
			def __init__(self):
				self.posa_coupon_code = None
				self.coupon_code = "TEST123"
				self.is_return = False
				self.doctype = "Sales Invoice"

		invoice = MockInvoice()

		# Test the pattern used in gift_cards.py
		coupon_code = getattr(invoice, 'posa_coupon_code', None) or getattr(invoice, 'coupon_code', None)
		self.assertEqual(coupon_code, "TEST123")

		# Test with posa_coupon_code set
		invoice.posa_coupon_code = "LEGACY456"
		coupon_code = getattr(invoice, 'posa_coupon_code', None) or getattr(invoice, 'coupon_code', None)
		self.assertEqual(coupon_code, "LEGACY456")


def run_coupon_invoice_integration_tests():
	"""Run all coupon invoice integration tests and return results"""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	suite.addTests(loader.loadTestsFromTestCase(TestCouponInvoiceIntegration))
	suite.addTests(loader.loadTestsFromTestCase(TestLegacyPosaCouponCodeCompatibility))

	runner = unittest.TextTestRunner(verbosity=2)
	return runner.run(suite)


if __name__ == "__main__":
	run_coupon_invoice_integration_tests()
