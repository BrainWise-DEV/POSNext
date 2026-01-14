# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Suite for Coupon Validation (offers.py)

This module tests the coupon validation functionality including:
- get_active_coupons - Retrieve available gift cards
- validate_coupon - Validate and retrieve coupon details

Run with: bench --site [site] run-tests --app pos_next --module pos_next.tests.test_coupon_validation
"""

import frappe
import unittest
from frappe.utils import nowdate, add_months, add_days, flt
from pos_next.api.offers import get_active_coupons, validate_coupon
from pos_next.api.gift_cards import create_gift_card_manual, _update_gift_card_balance


class TestGetActiveCoupons(unittest.TestCase):
	"""Test get_active_coupons function"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Get or create a test customer
		customers = frappe.get_all("Customer", limit=1)
		if customers:
			cls.test_customer = customers[0].name
		else:
			cls.test_customer = None

		# Create test gift cards
		# 1. Gift card with balance, no customer (anonymous)
		result1 = create_gift_card_manual(
			amount=100,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result1.get("name"))
		cls.gc_anonymous = result1.get("coupon_code")

		# 2. Gift card with balance, assigned to customer
		result2 = create_gift_card_manual(
			amount=75,
			company=cls.test_company,
			customer=cls.test_customer,
			validity_months=12
		)
		cls.created_coupons.append(result2.get("name"))
		cls.gc_customer_assigned = result2.get("coupon_code")

		# 3. Gift card with zero balance
		result3 = create_gift_card_manual(
			amount=50,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result3.get("name"))
		cls.gc_zero_balance = result3.get("coupon_code")

		# Set balance to zero
		coupon3 = frappe.get_doc("Coupon Code", result3.get("name"))
		_update_gift_card_balance(coupon3.name, 0, coupon3.pricing_rule)

		# Track pricing rules for cleanup
		for name in cls.created_coupons:
			coupon = frappe.get_doc("Coupon Code", name)
			if coupon.pricing_rule:
				cls.created_pricing_rules.append(coupon.pricing_rule)

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for coupon_name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", coupon_name, force=True)
			except Exception:
				pass

		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_get_anonymous_gift_cards(self):
		"""Test that anonymous gift cards are returned"""
		cards = get_active_coupons(customer=None, company=self.test_company)
		codes = [c["coupon_code"] for c in cards]

		self.assertIn(self.gc_anonymous, codes)

	def test_get_customer_gift_cards(self):
		"""Test that customer-specific gift cards are returned"""
		if not self.test_customer:
			self.skipTest("No test customer available")

		cards = get_active_coupons(customer=self.test_customer, company=self.test_company)
		codes = [c["coupon_code"] for c in cards]

		# Should include both anonymous and customer-assigned
		self.assertIn(self.gc_anonymous, codes)
		self.assertIn(self.gc_customer_assigned, codes)

	def test_exclude_zero_balance(self):
		"""Test that gift cards with zero balance are excluded"""
		cards = get_active_coupons(customer=None, company=self.test_company)
		codes = [c["coupon_code"] for c in cards]

		self.assertNotIn(self.gc_zero_balance, codes)

	def test_returned_fields(self):
		"""Test that all expected fields are returned"""
		cards = get_active_coupons(company=self.test_company)

		if not cards:
			self.skipTest("No gift cards returned")

		card = cards[0]
		expected_fields = [
			"name", "coupon_code", "coupon_name", "customer",
			"gift_card_amount", "balance", "valid_from", "valid_upto"
		]

		for field in expected_fields:
			self.assertIn(field, card, f"Missing field: {field}")


class TestValidateCoupon(unittest.TestCase):
	"""Test validate_coupon function"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Get test customer
		customers = frappe.get_all("Customer", limit=1)
		cls.test_customer = customers[0].name if customers else None

		# 1. Valid gift card with balance
		result1 = create_gift_card_manual(
			amount=100,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result1.get("name"))
		cls.gc_valid = result1.get("coupon_code")

		# 2. Gift card with zero balance
		result2 = create_gift_card_manual(
			amount=50,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result2.get("name"))
		cls.gc_exhausted = result2.get("coupon_code")

		coupon2 = frappe.get_doc("Coupon Code", result2.get("name"))
		_update_gift_card_balance(coupon2.name, 0, coupon2.pricing_rule)

		# 3. Gift card assigned to specific customer
		if cls.test_customer:
			result3 = create_gift_card_manual(
				amount=75,
				company=cls.test_company,
				customer=cls.test_customer,
				validity_months=12
			)
			cls.created_coupons.append(result3.get("name"))
			cls.gc_customer_specific = result3.get("coupon_code")
			cls.gc_customer_specific_name = result3.get("name")

		# Track pricing rules
		for name in cls.created_coupons:
			coupon = frappe.get_doc("Coupon Code", name)
			if coupon.pricing_rule:
				cls.created_pricing_rules.append(coupon.pricing_rule)

		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for coupon_name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", coupon_name, force=True)
			except Exception:
				pass

		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_validate_valid_coupon(self):
		"""Test validating a valid gift card"""
		result = validate_coupon(
			coupon_code=self.gc_valid,
			company=self.test_company
		)

		self.assertTrue(result.get("valid"))
		self.assertIn("coupon", result)
		self.assertEqual(result["coupon"]["coupon_code"], self.gc_valid)

	def test_validate_case_insensitive(self):
		"""Test that validation is case insensitive"""
		result = validate_coupon(
			coupon_code=self.gc_valid.lower(),
			company=self.test_company
		)

		self.assertTrue(result.get("valid"))

	def test_validate_invalid_code(self):
		"""Test validating an invalid coupon code"""
		result = validate_coupon(
			coupon_code="INVALID-CODE-9999",
			company=self.test_company
		)

		self.assertFalse(result.get("valid"))
		self.assertIn("message", result)

	def test_validate_exhausted_gift_card(self):
		"""Test validating a gift card with zero balance"""
		result = validate_coupon(
			coupon_code=self.gc_exhausted,
			company=self.test_company
		)

		self.assertFalse(result.get("valid"))
		self.assertIn("balance", result.get("message", "").lower())

	def test_validate_customer_restriction(self):
		"""Test that customer-specific coupons reject other customers"""
		if not self.test_customer or not hasattr(self, 'gc_customer_specific'):
			self.skipTest("No customer-specific gift card available")

		# Should fail for different customer
		result = validate_coupon(
			coupon_code=self.gc_customer_specific,
			customer="Some-Other-Customer",
			company=self.test_company
		)

		self.assertFalse(result.get("valid"))

	def test_validate_customer_restriction_correct_customer(self):
		"""Test that customer-specific coupons accept correct customer"""
		if not self.test_customer or not hasattr(self, 'gc_customer_specific'):
			self.skipTest("No customer-specific gift card available")

		result = validate_coupon(
			coupon_code=self.gc_customer_specific,
			customer=self.test_customer,
			company=self.test_company
		)

		self.assertTrue(result.get("valid"))

	def test_validate_returns_balance(self):
		"""Test that validation returns balance for gift cards"""
		result = validate_coupon(
			coupon_code=self.gc_valid,
			company=self.test_company
		)

		self.assertTrue(result.get("valid"))
		coupon = result.get("coupon", {})
		self.assertIn("gift_card_amount", coupon)
		self.assertGreater(flt(coupon.get("gift_card_amount")), 0)


class TestCouponValidityDates(unittest.TestCase):
	"""Test coupon validity date handling"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for coupon_name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", coupon_name, force=True)
			except Exception:
				pass

		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_expired_coupon(self):
		"""Test that expired coupons are rejected"""
		# Create a gift card that's already expired
		result = create_gift_card_manual(
			amount=100,
			company=self.test_company,
			validity_months=1
		)
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Manually set expiry to past date
		past_date = add_days(nowdate(), -30)
		frappe.db.set_value("Coupon Code", coupon.name, "valid_upto", past_date)
		frappe.db.commit()

		# Validate should fail
		validation_result = validate_coupon(
			coupon_code=result.get("coupon_code"),
			company=self.test_company
		)

		self.assertFalse(validation_result.get("valid"))
		self.assertIn("expired", validation_result.get("message", "").lower())

	def test_future_valid_from(self):
		"""Test that coupons with future valid_from are rejected"""
		result = create_gift_card_manual(
			amount=100,
			company=self.test_company,
			validity_months=12
		)
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Set valid_from to future date
		future_date = add_days(nowdate(), 30)
		frappe.db.set_value("Coupon Code", coupon.name, "valid_from", future_date)
		frappe.db.commit()

		# Validate should fail
		validation_result = validate_coupon(
			coupon_code=result.get("coupon_code"),
			company=self.test_company
		)

		self.assertFalse(validation_result.get("valid"))
		self.assertIn("not yet valid", validation_result.get("message", "").lower())


def run_coupon_validation_tests():
	"""Run all coupon validation tests and return results"""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	suite.addTests(loader.loadTestsFromTestCase(TestGetActiveCoupons))
	suite.addTests(loader.loadTestsFromTestCase(TestValidateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestCouponValidityDates))

	runner = unittest.TextTestRunner(verbosity=2)
	return runner.run(suite)


if __name__ == "__main__":
	run_coupon_validation_tests()
