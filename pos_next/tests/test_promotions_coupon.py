# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Suite for Promotions API Coupon Functions

This module tests the coupon CRUD operations in promotions.py including:
- create_coupon - Create new coupons (ERPNext Coupon Code)
- update_coupon - Update existing coupons
- delete_coupon - Delete coupons
- get_referral_details - Get referral code details

Run with: bench --site [site] run-tests --app pos_next --module pos_next.tests.test_promotions_coupon
"""

import frappe
import unittest
from frappe.utils import nowdate, add_months, flt
import json
from pos_next.api.promotions import (
	create_coupon,
	update_coupon,
	delete_coupon,
	get_referral_details,
)
from pos_next.pos_next.doctype.referral_code.referral_code import create_referral_code


class TestCreateCoupon(unittest.TestCase):
	"""Test create_coupon function"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_coupons = []
		cls.created_pricing_rules = []

		# Get test customer
		customers = frappe.get_all("Customer", limit=1)
		cls.test_customer = customers[0].name if customers else None

	def tearDown(self):
		"""Roll back after each test"""
		frappe.db.rollback()

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		for name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", name, force=True)
			except Exception:
				pass

		for name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_create_promotional_coupon_percentage(self):
		"""Test creating a promotional coupon with percentage discount"""
		data = {
			"coupon_name": f"Test Promo {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Percentage",
			"discount_percentage": 10,
			"company": self.test_company,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 3),
			"maximum_use": 100,
		}

		result = create_coupon(json.dumps(data))

		self.assertTrue(result.get("success"))
		self.assertIn("coupon_code", result)
		self.created_coupons.append(result.get("name"))

		# Verify coupon
		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		self.assertEqual(coupon.coupon_type, "Promotional")

		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)
			pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
			self.assertEqual(pr.rate_or_discount, "Discount Percentage")
			self.assertEqual(flt(pr.discount_percentage), 10)

	def test_create_promotional_coupon_amount(self):
		"""Test creating a promotional coupon with fixed amount discount"""
		data = {
			"coupon_name": f"Test Amount Promo {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Amount",
			"discount_amount": 50,
			"company": self.test_company,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 3),
			"maximum_use": 50,
		}

		result = create_coupon(json.dumps(data))

		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)
			pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
			self.assertEqual(pr.rate_or_discount, "Discount Amount")
			self.assertEqual(flt(pr.discount_amount), 50)

	def test_create_coupon_with_customer(self):
		"""Test creating a coupon assigned to specific customer"""
		if not self.test_customer:
			self.skipTest("No test customer available")

		data = {
			"coupon_name": f"Customer Coupon {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Percentage",
			"discount_percentage": 15,
			"company": self.test_company,
			"customer": self.test_customer,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 1),
			"maximum_use": 1,
		}

		result = create_coupon(json.dumps(data))

		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		self.assertEqual(coupon.customer, self.test_customer)

		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)


class TestUpdateCoupon(unittest.TestCase):
	"""Test update_coupon function"""

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
		for name in cls.created_coupons:
			try:
				frappe.delete_doc("Coupon Code", name, force=True)
			except Exception:
				pass

		for name in cls.created_pricing_rules:
			try:
				frappe.delete_doc("Pricing Rule", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_update_coupon_discount(self):
		"""Test updating coupon discount amount"""
		# Create coupon first
		data = {
			"coupon_name": f"Update Test {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Percentage",
			"discount_percentage": 10,
			"company": self.test_company,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 3),
			"maximum_use": 100,
		}

		result = create_coupon(json.dumps(data))
		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Update discount
		update_data = {
			"name": result.get("name"),
			"discount_type": "Percentage",
			"discount_percentage": 20,  # Changed from 10 to 20
		}

		update_result = update_coupon(json.dumps(update_data))
		self.assertTrue(update_result.get("success"))

		# Verify update
		if coupon.pricing_rule:
			updated_pr = frappe.get_doc("Pricing Rule", coupon.pricing_rule)
			self.assertEqual(flt(updated_pr.discount_percentage), 20)

	def test_update_coupon_validity(self):
		"""Test updating coupon validity dates"""
		data = {
			"coupon_name": f"Validity Test {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Amount",
			"discount_amount": 30,
			"company": self.test_company,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 1),
			"maximum_use": 50,
		}

		result = create_coupon(json.dumps(data))
		self.assertTrue(result.get("success"))
		self.created_coupons.append(result.get("name"))

		coupon = frappe.get_doc("Coupon Code", result.get("name"))
		if coupon.pricing_rule:
			self.created_pricing_rules.append(coupon.pricing_rule)

		# Update validity
		new_valid_upto = add_months(nowdate(), 6)
		update_data = {
			"name": result.get("name"),
			"valid_upto": str(new_valid_upto),
		}

		update_result = update_coupon(json.dumps(update_data))
		self.assertTrue(update_result.get("success"))

		# Verify update
		updated_coupon = frappe.get_doc("Coupon Code", result.get("name"))
		self.assertEqual(str(updated_coupon.valid_upto), str(new_valid_upto))


class TestDeleteCoupon(unittest.TestCase):
	"""Test delete_coupon function"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name

	def test_delete_coupon(self):
		"""Test deleting a coupon"""
		# Create coupon first
		data = {
			"coupon_name": f"Delete Test {frappe.generate_hash()[:6]}",
			"coupon_type": "Promotional",
			"discount_type": "Percentage",
			"discount_percentage": 5,
			"company": self.test_company,
			"valid_from": nowdate(),
			"valid_upto": add_months(nowdate(), 1),
			"maximum_use": 10,
		}

		result = create_coupon(json.dumps(data))
		self.assertTrue(result.get("success"))

		coupon_name = result.get("name")
		coupon = frappe.get_doc("Coupon Code", coupon_name)
		pricing_rule_name = coupon.pricing_rule

		# Delete coupon
		delete_result = delete_coupon(coupon_name)
		self.assertTrue(delete_result.get("success"))

		# Verify deletion
		self.assertFalse(frappe.db.exists("Coupon Code", coupon_name))

		# Pricing rule should also be deleted
		if pricing_rule_name:
			self.assertFalse(frappe.db.exists("Pricing Rule", pricing_rule_name))


class TestGetReferralDetails(unittest.TestCase):
	"""Test get_referral_details function"""

	@classmethod
	def setUpClass(cls):
		"""Set up test fixtures"""
		cls.test_company = frappe.get_all("Company", limit=1)[0].name
		cls.created_referral_codes = []
		cls.created_coupons = []

		# Get test customers
		customers = frappe.get_all("Customer", limit=2)
		if len(customers) >= 2:
			cls.referrer_customer = customers[0].name
			cls.referee_customer = customers[1].name
		else:
			cls.referrer_customer = None
			cls.referee_customer = None

	@classmethod
	def tearDownClass(cls):
		"""Clean up test data"""
		# Clean up coupons first
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

		# Clean up referral codes
		for name in cls.created_referral_codes:
			try:
				frappe.delete_doc("Referral Code", name, force=True)
			except Exception:
				pass

		frappe.db.commit()

	def test_get_referral_details_basic(self):
		"""Test getting referral details"""
		if not self.referrer_customer:
			self.skipTest("No test customer available")

		# Create referral code
		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Percentage",
			referrer_discount_percentage=10,
			referee_discount_type="Percentage",
			referee_discount_percentage=15
		)
		self.created_referral_codes.append(referral.name)
		frappe.db.commit()

		# Get details
		details = get_referral_details(referral.name)

		self.assertIsNotNone(details)
		self.assertEqual(details.get("name"), referral.name)
		self.assertEqual(details.get("customer"), self.referrer_customer)
		self.assertIn("generated_coupons", details)
		self.assertIn("total_coupons_generated", details)

	def test_get_referral_details_with_coupons(self):
		"""Test getting referral details after coupons are generated"""
		if not self.referrer_customer or not self.referee_customer:
			self.skipTest("No test customers available")

		from pos_next.pos_next.doctype.referral_code.referral_code import apply_referral_code

		# Create referral code
		referral = create_referral_code(
			company=self.test_company,
			customer=self.referrer_customer,
			referrer_discount_type="Amount",
			referrer_discount_amount=20,
			referee_discount_type="Amount",
			referee_discount_amount=20
		)
		self.created_referral_codes.append(referral.name)
		frappe.db.commit()

		# Apply referral code (generates coupons)
		result = apply_referral_code(
			referral_code=referral.referral_code,
			referee_customer=self.referee_customer
		)

		if result.get("referrer_coupon"):
			self.created_coupons.append(result["referrer_coupon"]["name"])
		if result.get("referee_coupon"):
			self.created_coupons.append(result["referee_coupon"]["name"])

		frappe.db.commit()

		# Get details
		details = get_referral_details(referral.name)

		self.assertGreater(details.get("total_coupons_generated"), 0)
		self.assertIsInstance(details.get("generated_coupons"), list)

		# Verify coupon details are populated
		for coupon in details.get("generated_coupons", []):
			self.assertIn("coupon_code", coupon)
			self.assertIn("coupon_type", coupon)

	def test_get_referral_details_invalid(self):
		"""Test getting details for invalid referral code"""
		with self.assertRaises(frappe.exceptions.ValidationError):
			get_referral_details("INVALID-REFERRAL-CODE")


def run_promotions_coupon_tests():
	"""Run all promotions coupon tests and return results"""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	suite.addTests(loader.loadTestsFromTestCase(TestCreateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestUpdateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestDeleteCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestGetReferralDetails))

	runner = unittest.TextTestRunner(verbosity=2)
	return runner.run(suite)


if __name__ == "__main__":
	run_promotions_coupon_tests()
