# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Test Runner for POS Next - ERPNext Coupon Code Integration

This script runs all tests related to the gift card and coupon refactoring.

Usage:
    From bench:
        bench --site [site] execute pos_next.tests.run_all_tests.run_all_tests

    Or run individual test modules:
        bench --site [site] run-tests --app pos_next --module pos_next.tests.test_gift_cards
        bench --site [site] run-tests --app pos_next --module pos_next.tests.test_coupon_validation
        bench --site [site] run-tests --app pos_next --module pos_next.tests.test_promotions_coupon
        bench --site [site] run-tests --app pos_next --module pos_next.pos_next.doctype.referral_code.test_referral_code
"""

import frappe
import unittest
import sys


def run_all_tests():
	"""
	Run all POS Next coupon-related tests.

	Returns:
		bool: True if all tests passed, False otherwise
	"""
	print("\n" + "="*70)
	print("POS NEXT - ERPNext Coupon Code Integration Tests")
	print("="*70 + "\n")

	# Import test modules
	from pos_next.tests.test_gift_cards import (
		TestGiftCardCodeGeneration,
		TestManualGiftCardCreation,
		TestGiftCardApplication,
		TestGiftCardBalanceUpdate,
		TestGetGiftCardsWithBalance,
		TestPricingRuleCreation,
	)
	from pos_next.tests.test_coupon_validation import (
		TestGetActiveCoupons,
		TestValidateCoupon,
		TestCouponValidityDates,
	)
	from pos_next.tests.test_promotions_coupon import (
		TestCreateCoupon,
		TestUpdateCoupon,
		TestDeleteCoupon,
		TestGetReferralDetails,
	)
	from pos_next.pos_next.doctype.referral_code.test_referral_code import (
		TestReferralCodeCreation,
		TestReferralCouponGeneration,
		TestApplyReferralCode,
		TestReferralCodeValidation,
	)

	# Build test suite
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	# Gift Card Tests
	print("Loading Gift Card Tests...")
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardCodeGeneration))
	suite.addTests(loader.loadTestsFromTestCase(TestManualGiftCardCreation))
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardApplication))
	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardBalanceUpdate))
	suite.addTests(loader.loadTestsFromTestCase(TestGetGiftCardsWithBalance))
	suite.addTests(loader.loadTestsFromTestCase(TestPricingRuleCreation))

	# Coupon Validation Tests
	print("Loading Coupon Validation Tests...")
	suite.addTests(loader.loadTestsFromTestCase(TestGetActiveCoupons))
	suite.addTests(loader.loadTestsFromTestCase(TestValidateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestCouponValidityDates))

	# Promotions Coupon Tests
	print("Loading Promotions Coupon Tests...")
	suite.addTests(loader.loadTestsFromTestCase(TestCreateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestUpdateCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestDeleteCoupon))
	suite.addTests(loader.loadTestsFromTestCase(TestGetReferralDetails))

	# Referral Code Tests
	print("Loading Referral Code Tests...")
	suite.addTests(loader.loadTestsFromTestCase(TestReferralCodeCreation))
	suite.addTests(loader.loadTestsFromTestCase(TestReferralCouponGeneration))
	suite.addTests(loader.loadTestsFromTestCase(TestApplyReferralCode))
	suite.addTests(loader.loadTestsFromTestCase(TestReferralCodeValidation))

	print(f"\nTotal tests loaded: {suite.countTestCases()}")
	print("\n" + "-"*70)
	print("Running Tests...")
	print("-"*70 + "\n")

	# Run tests
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)

	# Print summary
	print("\n" + "="*70)
	print("TEST SUMMARY")
	print("="*70)
	print(f"Tests Run: {result.testsRun}")
	print(f"Failures: {len(result.failures)}")
	print(f"Errors: {len(result.errors)}")
	print(f"Skipped: {len(result.skipped)}")
	print("="*70)

	if result.failures:
		print("\nFailed Tests:")
		for test, traceback in result.failures:
			print(f"  - {test}")

	if result.errors:
		print("\nTests with Errors:")
		for test, traceback in result.errors:
			print(f"  - {test}")

	all_passed = len(result.failures) == 0 and len(result.errors) == 0
	print(f"\nOverall Result: {'PASSED ✓' if all_passed else 'FAILED ✗'}")
	print("="*70 + "\n")

	return all_passed


def run_quick_test():
	"""
	Run a quick subset of tests for fast validation.
	"""
	print("\n" + "="*70)
	print("POS NEXT - Quick Test (Code Generation & Basic Validation)")
	print("="*70 + "\n")

	from pos_next.tests.test_gift_cards import TestGiftCardCodeGeneration
	from pos_next.tests.test_coupon_validation import TestValidateCoupon

	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	suite.addTests(loader.loadTestsFromTestCase(TestGiftCardCodeGeneration))

	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)

	return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
	run_all_tests()
