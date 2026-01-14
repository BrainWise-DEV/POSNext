# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Suite for Gift Cards API

This module tests the gift card functionality including:
- Gift card code generation
- Gift card creation (manual and from invoice)
- Gift card application
- Gift card balance updates (splitting)
- Gift card cancellation/refund handling

Run with: bench --site [site] run-tests --app pos_next --module pos_next.tests.test_gift_cards
"""

import frappe
import unittest
from frappe.utils import nowdate, add_months, flt, getdate
from pos_next.api.gift_cards import (
	generate_gift_card_code,
	create_gift_card_manual,
	apply_gift_card,
	get_gift_cards_with_balance,
	_create_gift_card,
	_create_pricing_rule_for_gift_card,
	_update_gift_card_balance,
)


class TestGiftCardCodeGeneration(unittest.TestCase):
	"""Test gift card code generation"""

	def test_code_format(self):
		"""Test that generated code matches expected format GC-XXXX-XXXX"""
		code = generate_gift_card_code()
		self.assertIsNotNone(code)
		self.assertTrue(code.startswith("GC-"))
		parts = code.split("-")
		self.assertEqual(len(parts), 3)
		self.assertEqual(len(parts[1]), 4)
		self.assertEqual(len(parts[2]), 4)

	def test_code_uniqueness(self):
		"""Test that generated codes are unique"""
		codes = set()
		for _ in range(50):
			code = generate_gift_card_code()
			self.assertNotIn(code, codes, "Duplicate code generated")
			codes.add(code)

	def test_code_characters(self):
		"""Test that code contains only uppercase letters and digits"""
		code = generate_gift_card_code()
		# Remove the prefix and hyphens
		clean_code = code.replace("GC-", "").replace("-", "")
		for char in clean_code:
			self.assertTrue(
				char.isupper() or char.isdigit(),
				f"Invalid character '{char}' in code"
			)


class TestManualGiftCardCreation(unittest.TestCase):
	"""Test manual gift card creation from ERPNext UI"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

	def tearDown(self):
		"""Clean up after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		# Delete test coupons
		for coupon_name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", coupon_name, force=True)
			except Exception:
				pass

		# Delete test pricing rules
		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_create_gift_card_basic(self):
		"""Test basic gift card creation"""
		result = create_gift_card_manual(
			amount=100,
			company=self.test_company,
			validity_months=12
		)

		self.assertTrue(result.get("success"))
		self.assertIn("coupon_code", result)
		self.assertEqual(result.get("amount"), 100)

		# Track for cleanup
		self.created_coupons.append(result.get("name"))

		# Verify coupon was created in database
		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		self.assertEqual(coupon.coupon_type, "Gift Card")
		self.assertEqual(coupon.pos_next_gift_card, 1)
		self.assertEqual(flt(coupon.gift_card_amount), 100)
		self.assertEqual(flt(coupon.original_gift_card_amount), 100)

		# Track pricing rule for cleanup
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

	def test_create_gift_card_with_customer(self):
		"""Test gift card creation with customer assignment"""
		# Get a test customer
		customer = frappe.get_all("Customer", limit=1)
		if not customer:
			self.skipTest("No customer found for testing")

		result = create_gift_card_manual(
			amount=50,
			company=self.test_company,
			customer=customer[0].name,
			validity_months=6
		)

		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		# Verify validity period
		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		expected_upto = add_months(nowdate(), 6)
		self.assertEqual(str(coupon.valid_upto), str(expected_upto))

		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

	def test_create_gift_card_pricing_rule(self):
		"""Test that pricing rule is created correctly"""
		result = create_gift_card_manual(
			amount=75,
			company=self.test_company,
			validity_months=12
		)

		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		self.assertIsNotNone(coupon.pricing_rule)

		# Verify pricing rule
		pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
		self.assertEqual(pr.rate_or_discount, "Discount Amount")
		self.assertEqual(flt(pr.discount_amount), 75)
		self.assertEqual(pr.company, self.test_company)
		self.assertEqual(pr.coupon_code_based, 1)

		self.created_pricing_rules.append(coupon.pricing_rule)

	def test_create_gift_card_zero_validity(self):
		"""Test gift card with unlimited validity (0 months)"""
		result = create_gift_card_manual(
			amount=200,
			company=self.test_company,
			validity_months=0
		)

		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		# With 0 validity months, valid_upto should be None or empty
		self.assertFalse(coupon.valid_upto)

		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)


class TestGiftCardApplication(unittest.TestCase):
	"""Test gift card application to invoices"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Create a test gift card
		result = create_gift_card_manual(
			amount=100,
			company=cls.test_company,
			validity_months=12
		)
		cls.test_gift_card_code = result.get("coupon_code")
		cls.test_gift_card_name = result.get("name")
		cls.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			cls.created_pricing_rules.append(coupon.pricing_rule)

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

	def test_apply_gift_card_partial(self):
		"""Test applying gift card with amount less than balance"""
		result = apply_gift_card(
			coupon_code=self.test_gift_card_code,
			invoice_total=60,
			company=self.test_company
		)

		self.assertTrue(result.get("success"))
		self.assertEqual(result.get("discount_amount"), 60)
		self.assertEqual(result.get("available_balance"), 100)
		self.assertTrue(result.get("will_split"))
		self.assertEqual(result.get("remaining_balance"), 40)

	def test_apply_gift_card_full(self):
		"""Test applying gift card with amount equal to balance"""
		result = apply_gift_card(
			coupon_code=self.test_gift_card_code,
			invoice_total=100,
			company=self.test_company
		)

		self.assertTrue(result.get("success"))
		self.assertEqual(result.get("discount_amount"), 100)
		self.assertFalse(result.get("will_split"))
		self.assertEqual(result.get("remaining_balance"), 0)

	def test_apply_gift_card_exceeds_balance(self):
		"""Test applying gift card with invoice greater than balance"""
		result = apply_gift_card(
			coupon_code=self.test_gift_card_code,
			invoice_total=150,
			company=self.test_company
		)

		self.assertTrue(result.get("success"))
		self.assertEqual(result.get("discount_amount"), 100)  # Only balance amount
		self.assertFalse(result.get("will_split"))

	def test_apply_nonexistent_gift_card(self):
		"""Test applying non-existent gift card"""
		result = apply_gift_card(
			coupon_code="INVALID-CODE-9999",
			invoice_total=50,
			company=self.test_company
		)

		self.assertFalse(result.get("success"))
		self.assertIn("not found", result.get("message", "").lower())

	def test_apply_gift_card_case_insensitive(self):
		"""Test that gift card codes are case insensitive"""
		result = apply_gift_card(
			coupon_code=self.test_gift_card_code.lower(),
			invoice_total=50,
			company=self.test_company
		)

		self.assertTrue(result.get("success"))


class TestGiftCardBalanceUpdate(unittest.TestCase):
	"""Test gift card balance updates"""

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

	def test_update_balance_partial_usage(self):
		"""Test updating balance after partial usage"""
		# Create a test gift card
		result = create_gift_card_manual(
			amount=100,
			company=self.test_company,
			validity_months=12
		)
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Update balance
		_update_gift_card_balance(
			coupon_name=coupon.name,
			new_balance=40,
			pricing_rule=coupon.pricing_rule
		)

		# Verify balance was updated
		updated_coupon = frappe.get_doc("Coupon Code", coupon.name)
		self.assertEqual(flt(updated_coupon.gift_card_amount), 40)

		# Verify pricing rule was updated
		if coupon.pricing_rule:
			updated_pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
			self.assertEqual(flt(updated_pr.discount_amount), 40)

	def test_update_balance_exhausted(self):
		"""Test updating balance to zero (fully used)"""
		result = create_gift_card_manual(
			amount=50,
			company=self.test_company,
			validity_months=12
		)
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Update balance to zero
		_update_gift_card_balance(
			coupon_name=coupon.name,
			new_balance=0,
			pricing_rule=coupon.pricing_rule
		)

		# Verify balance is zero
		updated_coupon = frappe.get_doc("Coupon Code", coupon.name)
		self.assertEqual(flt(updated_coupon.gift_card_amount), 0)
		self.assertEqual(updated_coupon.used, 1)


class TestGetGiftCardsWithBalance(unittest.TestCase):
	"""Test retrieving gift cards with balance"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Create gift cards with different states
		# 1. Gift card with full balance
		result1 = create_gift_card_manual(
			amount=100,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result1.get("name"))
		cls.gc_full_balance = result1.get("coupon_code")

		# 2. Gift card with partial balance
		result2 = create_gift_card_manual(
			amount=75,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result2.get("name"))
		cls.gc_partial_balance = result2.get("coupon_code")

		# Reduce balance to partial
		coupon2 = frappe.get_doc("Coupon Code", result2.get("name"))
		_update_gift_card_balance(coupon2.name, 25, coupon2.pricing_rule)

		# 3. Exhausted gift card (balance = 0)
		result3 = create_gift_card_manual(
			amount=50,
			company=cls.test_company,
			validity_months=12
		)
		cls.created_coupons.append(result3.get("name"))
		cls.gc_exhausted = result3.get("coupon_code")

		coupon3 = frappe.get_doc("Coupon Code", result3.get("name"))
		_update_gift_card_balance(coupon3.name, 0, coupon3.pricing_rule)

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

	def test_get_cards_with_balance(self):
		"""Test that only cards with balance > 0 are returned"""
		cards = get_gift_cards_with_balance(company=self.test_company)

		# Get codes of returned cards
		returned_codes = [c.coupon_code for c in cards]

		# Full balance should be included
		self.assertIn(self.gc_full_balance, returned_codes)

		# Partial balance should be included
		self.assertIn(self.gc_partial_balance, returned_codes)

		# Exhausted should NOT be included
		self.assertNotIn(self.gc_exhausted, returned_codes)

	def test_returned_balance_field(self):
		"""Test that balance field is correctly populated"""
		cards = get_gift_cards_with_balance(company=self.test_company)

		for card in cards:
			self.assertIn("balance", card)
			self.assertGreater(card.balance, 0)


class TestPricingRuleCreation(unittest.TestCase):
	"""Test pricing rule creation for gift cards"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_pricing_rules = []

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for pr_name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", pr_name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_pricing_rule_basic(self):
		"""Test basic pricing rule creation"""
		code = f"TEST-{frappe.generate_hash()[:8].upper()}"
		pr_name = _create_pricing_rule_for_gift_card(
			amount=100,
			coupon_code=code,
			company=self.test_company
		)

		self.assertIsNotNone(pr_name)
		self.created_pricing_rules.append(pr_name)

		pr = frappe.get_doc("Pricing Rule", pr_name)
		self.assertEqual(pr.apply_on, "Transaction")
		self.assertEqual(pr.price_or_product_discount, "Price")
		self.assertEqual(pr.rate_or_discount, "Discount Amount")
		self.assertEqual(flt(pr.discount_amount), 100)
		self.assertTrue(pr.selling)
		self.assertFalse(pr.buying)
		self.assertTrue(pr.coupon_code_based)

	def test_pricing_rule_with_validity(self):
		"""Test pricing rule with validity dates"""
		code = f"TEST-{frappe.generate_hash()[:8].upper()}"
		valid_from = nowdate()
		valid_upto = add_months(valid_from, 6)

		pr_name = _create_pricing_rule_for_gift_card(
			amount=50,
			coupon_code=code,
			company=self.test_company,
			valid_from=valid_from,
			valid_upto=valid_upto
		)

		self.assertIsNotNone(pr_name)
		self.created_pricing_rules.append(pr_name)

		pr = frappe.get_doc("Pricing Rule", pr_name)
		self.assertEqual(str(pr.valid_from), str(valid_from))
		self.assertEqual(str(pr.valid_upto), str(valid_upto))


def run_gift_card_tests():
	"""Run all gift card tests and return results"""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	# Add test classes
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardCodeGeneration))
	suite.addTests(loader.loadTestsFromTestCase(TestManualGiftCardCreation))
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardApplication))
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardBalanceUpdate))
	suite.addTests(loader.loadTestsFromTestCase(TestGetGiftCardsWithBalance))
	suite.addTests(loader.loadTestsFromTestCase(TestPricingRuleCreation))

	# Run tests
	runner = unittest.TextTestRunner(verbosity=2)
	return runner.run(suite)


if __name__ == "__main__":
	run_gift_card_tests()
