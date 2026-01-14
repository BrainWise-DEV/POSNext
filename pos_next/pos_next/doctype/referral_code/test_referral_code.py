# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Suite for Referral Code functionality

This module tests the referral code system including:
- Referral code creation
- Coupon generation for referrer and referee (using ERPNext Coupon Code)
- Application of referral codes
- Duplicate usage prevention

Run with: bench --site [site] run-tests --app pos_next --module pos_next.pos_next.doctype.referral_code.test_referral_code
"""

import frappe
import unittest
from frappe.utils import nowdate, add_days, flt
from pos_next.pos_next.doctype.referral_code.referral_code import (
	create_referral_code,
	apply_referral_code,
	generate_referrer_coupon,
	generate_referee_coupon,
)


class TestReferralCodeCreation(unittest.TestCase):
	"""Test referral code document creation"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_referral_codes = []

		# Get or create test customers
		customers = frappe.get_all("Customer", limit=2)
		if len(customers) >= 2:
			cls.referrer_customer = customers[0].name
			cls.referee_customer = customers[1].name
		else:
			cls.referrer_customer = None
			cls.referee_customer = None

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for name in cls.created_referral_codes:
			try:
				# Delete associated coupons
				coupons = frappe.get_all("Coupon Code", filters={"referral_code": name})
				for coupon in coupons:
					coupon_doc = frappe.get_doc("Coupon Code", coupon.name)
					if coupon_doc.pricing_rule:
						try:
							frappe.delete_doc("Pricing Rule", coupon_doc.pricing_rule, force=True)
						except Exception:
							pass
					frappe.delete_doc("Coupon Code", coupon.name, force=True)

				# Delete referral code
				frappe.delete_doc("Referral Code", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_create_referral_code_percentage(self):
		"""Test creating a referral code with percentage discount"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Percentage",
			referrer_discount_percentage=10,
			referee_discount_type="Percentage",
			referee_discount_percentage=15
		)

		self.assertIsNotNone(referral)
		self.created_referral_codes.append(referral.name)

		self.assertEqual(referral.company, self.test_company)
		self.assertEqual(referral.customer, self.referrer_customer)
		self.assertEqual(referral.referrer_discount_type, "Percentage")
		self.assertEqual(flt(referral.referrer_discount_percentage), 10)

	def test_create_referral_code_amount(self):
		"""Test creating a referral code with fixed amount discount"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Amount",
			referrer_discount_amount=20,
			referee_discount_type="Amount",
			referee_discount_amount=25
		)

		self.assertIsNotNone(referral)
		self.created_referral_codes.append(referral.name)

		self.assertEqual(referral.referrer_discount_type, "Amount")
		self.assertEqual(flt(referral.referrer_discount_amount), 20)

	def test_referral_code_auto_generated(self):
		"""Test that referral code is auto-generated"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Percentage",
			referrer_discount_percentage=10,
			referee_discount_type="Percentage",
			referee_discount_percentage=10
		)

		self.assertIsNotNone(referral.referral_code)
		self.assertGreater(len(referral.referral_code), 0)
		self.created_referral_codes.append(referral.name)


class TestReferralCouponGeneration(unittest.TestCase):
	"""Test coupon generation from referral codes"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_referral_codes = []
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Get test customers
		customers = frappe.get_all("Customer", limit=2)
		if len(customers) >= 2:
			cls.referrer_customer = customers[0].name
			cls.referee_customer = customers[1].name
		else:
			cls.referrer_customer = None
			cls.referee_customer = None

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		# Clean up coupons
		for name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", name, force=True)
			except Exception:
				pass

		# Clean up pricing rules
		for name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", name, force=True)
			except Exception:
				pass

		# Clean up referral codes
		for name in cls.created_referral_codes:
			try:
				frappe.delete_doc("Referral Code", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_generate_referrer_coupon(self):
		"""Test generating a coupon for the referrer"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		# Create referral code
		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Amount",
			referrer_discount_amount=50,
			referee_discount_type="Percentage",
			referee_discount_percentage=10
		)
		self.created_referral_codes.append(referral.name)

		# Generate referrer coupon
		coupon = generate_referrer_coupon(referral)

		self.assertIsNotNone(coupon)
		self.created_coupons.append(coupon.name)

		# Verify coupon properties
		self.assertEqual(coupon.doctype, "Coupon Code")
		self.assertTrue(coupon.coupon_code.startswith("REF-"))
		self.assertEqual(coupon.referral_code, referral.name)
		self.assertEqual(coupon.customer, self.referrer_customer)

		# Verify pricing rule was created
		self.assertIsNotNone(coupon.pricing_rule)
		self.created_pricing_rules.append(coupon.pricing_rule)

		pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
		self.assertEqual(pr.rate_or_discount, "Discount Amount")
		self.assertEqual(flt(pr.discount_amount), 50)

	def test_generate_referee_coupon(self):
		"""Test generating a coupon for the referee"""
		if not self.referrer_customer or not self.referee_customer:
			self.skipTest("No test customers available")

		# Create referral code
		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Percentage",
			referrer_discount_percentage=10,
			referee_discount_type="Percentage",
			referee_discount_percentage=20
		)
		self.created_referral_codes.append(referral.name)

		# Generate referee coupon
		coupon = generate_referee_coupon(referral, self.referee_customer)

		self.assertIsNotNone(coupon)
		self.created_coupons.append(coupon.name)

		# Verify coupon properties
		self.assertTrue(coupon.coupon_code.startswith("WELCOME-"))
		self.assertEqual(coupon.coupon_type, "Promotional")
		self.assertEqual(coupon.referral_code, referral.name)
		self.assertEqual(coupon.customer, self.referee_customer)

		# Verify pricing rule
		self.assertIsNotNone(coupon.pricing_rule)
		self.created_pricing_rules.append(coupon.pricing_rule)

		pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
		self.assertEqual(pr.rate_or_discount, "Discount Percentage")
		self.assertEqual(flt(pr.discount_percentage), 20)

	def test_coupon_validity_period(self):
		"""Test that coupon has correct validity period"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		# Create referral with 60 day validity
		referral = frappe.new_doc("Referral Code")
		referral.company = self.test_company
		referral.customer = self.referrer_customer
		referral.referrer_discount_type = "Amount"
		referral.referrer_discount_amount = 30
		referral.referrer_coupon_valid_days = 60
		referral.referee_discount_type = "Amount"
		referral.referee_discount_amount = 30
		referral.insert()
		self.created_referral_codes.append(referral.name)

		# Generate coupon
		coupon = generate_referrer_coupon(referral)
		self.created_coupons.append(coupon.name)

		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Check validity
		expected_upto = add_days(nowdate(), 60)
		self.assertEqual(str(coupon.valid_upto), str(expected_upto))


class TestApplyReferralCode(unittest.TestCase):
	"""Test applying referral codes"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_referral_codes = []
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Get test customers
		customers = frappe.get_all("Customer", limit=3)
		if len(customers) >= 3:
			cls.referrer_customer = customers[0].name
			cls.referee_customer1 = customers[1].name
			cls.referee_customer2 = customers[2].name
		else:
			cls.referrer_customer = None
			cls.referee_customer1 = None
			cls.referee_customer2 = None

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for name in cls.created_coupons:
			try:
				coupon = frappe.get_doc("Coupon Code", name)
				if coupon.pricing_rule:
					try:
						frappe.delete_doc("Pricing Rule", coupon.pricing_rule, force=True)
					except Exception:
						pass
				frappe.delete_doc("Coupon Code", name, force=True)
			except Exception:
				pass

		for name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", name, force=True)
			except Exception:
				pass

		for name in cls.created_referral_codes:
			try:
				frappe.delete_doc("Referral Code", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_apply_referral_code_success(self):
		"""Test successfully applying a referral code"""
		if not self.referrer_customer or not self.referee_customer1:
			self.skipTest("No test customers available")

		# Create referral code
		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Amount",
			referrer_discount_amount=25,
			referee_discount_type="Amount",
			referee_discount_amount=25
		)
		self.created_referral_codes.append(referral.name)
		frappe.db.commit()

		# Apply referral code
		result = apply_referral_code(
			referral_code=referral.referral_code,
			referee_customer=self.referee_customer1
		)

		self.assertIsNotNone(result)
		self.assertIn("referrer_coupon", result)
		self.assertIn("referee_coupon", result)

		# Track created coupons for cleanup
		if result.get("referrer_coupon"):
			self.created_coupons.append(result["referrer_coupon"]["name"])
		if result.get("referee_coupon"):
			self.created_coupons.append(result["referee_coupon"]["name"])

		# Verify referrer coupon
		self.assertIsNotNone(result.get("referrer_coupon"))
		self.assertEqual(result["referrer_coupon"]["customer"], self.referrer_customer)

		# Verify referee coupon
		self.assertIsNotNone(result.get("referee_coupon"))
		self.assertEqual(result["referee_coupon"]["customer"], self.referee_customer1)

	def test_apply_invalid_referral_code(self):
		"""Test applying an invalid referral code"""
		if not self.referee_customer1:
			self.skipTest("No test customer available")

		with self.assertRaises(frappe.exceptions.ValidationError):
			apply_referral_code(
				referral_code="INVALID-CODE-12345",
				referee_customer=self.referee_customer1
			)

	def test_apply_referral_code_case_insensitive(self):
		"""Test that referral code is case insensitive"""
		if not self.referrer_customer or not self.referee_customer1:
			self.skipTest("No test customers available")

		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Percentage",
			referrer_discount_percentage=10,
			referee_discount_type="Percentage",
			referee_discount_percentage=10
		)
		self.created_referral_codes.append(referral.name)
		frappe.db.commit()

		# Apply with lowercase
		result = apply_referral_code(
			referral_code=referral.referral_code.lower(),
			referee_customer=self.referee_customer1
		)

		self.assertIsNotNone(result)

		if result.get("referrer_coupon"):
			self.created_coupons.append(result["referrer_coupon"]["name"])
		if result.get("referee_coupon"):
			self.created_coupons.append(result["referee_coupon"]["name"])

	def test_referral_code_increments_count(self):
		"""Test that applying a referral increments the usage count"""
		if not self.referrer_customer or not self.referee_customer1:
			self.skipTest("No test customers available")

		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Amount",
			referrer_discount_amount=20,
			referee_discount_type="Amount",
			referee_discount_amount=20
		)
		self.created_referral_codes.append(referral.name)

		initial_count = referral.referrals_count or 0
		frappe.db.commit()

		result = apply_referral_code(
			referral_code=referral.referral_code,
			referee_customer=self.referee_customer1
		)

		if result.get("referrer_coupon"):
			self.created_coupons.append(result["referrer_coupon"]["name"])
		if result.get("referee_coupon"):
			self.created_coupons.append(result["referee_coupon"]["name"])

		# Reload and check count
		referral.reload()
		self.assertEqual(referral.referrals_count, initial_count + 1)


class TestReferralCodeValidation(unittest.TestCase):
	"""Test referral code validation rules"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name

		customers = frappe.get_all("Customer", limit=1)
		cls.test_customer = customers[0].name if customers else None

	def test_validate_referrer_percentage_required(self):
		"""Test that referrer percentage is required when type is Percentage"""
		if not self.test_customer:
			self.skipTest("No test customer available")

		referral = frappe.new_doc("Referral Code")
		referral.company = self.test_company
		referral.customer = self.test_customer
		referral.referrer_discount_type = "Percentage"
		referral.referrer_discount_percentage = None  # Missing
		referral.referee_discount_type = "Percentage"
		referral.referee_discount_percentage = 10

		with self.assertRaises(frappe.exceptions.ValidationError):
			referral.validate()

	def test_validate_referrer_amount_required(self):
		"""Test that referrer amount is required when type is Amount"""
		if not self.test_customer:
			self.skipTest("No test customer available")

		referral = frappe.new_doc("Referral Code")
		referral.company = self.test_company
		referral.customer = self.test_customer
		referral.referrer_discount_type = "Amount"
		referral.referrer_discount_amount = None  # Missing
		referral.referee_discount_type = "Amount"
		referral.referee_discount_amount = 10

		with self.assertRaises(frappe.exceptions.ValidationError):
			referral.validate()

	def test_validate_percentage_range(self):
		"""Test that percentage must be between 0 and 100"""
		if not self.test_customer:
			self.skipTest("No test customer available")

		referral = frappe.new_doc("Referral Code")
		referral.company = self.test_company
		referral.customer = self.test_customer
		referral.referrer_discount_type = "Percentage"
		referral.referrer_discount_percentage = 150  # Invalid
		referral.referee_discount_type = "Percentage"
		referral.referee_discount_percentage = 10

		with self.assertRaises(frappe.exceptions.ValidationError):
			referral.validate()


def run_referral_code_tests():
	"""Run all referral code tests and return results"""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	suite.addTests(loader.loadTestsFromTestCase(TestReferralCodeCreation))
	suite.addTests(loader.loadTestsFromTestCase(TestReferralCouponGeneration))
	suite.addTests(loader.loadTestsFromTestCase(TestApplyReferralCode))
	suite.addTests(loader.loadTestsFromTestCase(TestReferralCodeValidation))

	runner = unittest.TextTestRunner(verbosity=2)
	return runner.run(suite)


if __name__ == "__main__":
	run_referral_code_tests()
