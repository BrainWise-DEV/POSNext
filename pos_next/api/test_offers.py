# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch

from pos_next.api.offers import validate_coupon


class TestValidateCoupon(unittest.TestCase):
	# new_callable=MagicMock: some environments have unittest.mock auto-detect
	# frappe.db as async and substitute an AsyncMock, which returns coroutines
	# instead of the configured values. Force a plain MagicMock explicitly.
	@patch("pos_next.api.offers.frappe.db", new_callable=MagicMock)
	def test_coupons_not_enabled_takes_precedence_over_missing_customer(self, mock_db):
		"""Table-existence must be checked before the customer requirement, so a
		site without POS Coupon set up reports the accurate reason even when no
		customer is selected either."""
		mock_db.table_exists.return_value = False

		result = validate_coupon(coupon_code="SAVE10", company="Test Company", customer=None)

		self.assertFalse(result["valid"])
		self.assertEqual(result["message"], "Coupons are not enabled")
		# Must never reach the coupon lookup (get_value may still be called by
		# unrelated framework internals, e.g. translation lookups for _()).
		for call in mock_db.get_value.call_args_list:
			self.assertNotEqual(call.args[0] if call.args else None, "POS Coupon")

	@patch("pos_next.api.offers.frappe.db", new_callable=MagicMock)
	def test_missing_customer_is_rejected_with_friendly_message(self, mock_db):
		"""No customer selected must return a clean message, not crash on the
		coupon lookup (regression test for PN-77)."""
		mock_db.table_exists.return_value = True

		result = validate_coupon(coupon_code="SAVE10", company="Test Company", customer=None)

		self.assertFalse(result["valid"])
		self.assertEqual(result["message"], "Please choose a customer")
		for call in mock_db.get_value.call_args_list:
			self.assertNotEqual(call.args[0] if call.args else None, "POS Coupon")

	@patch("pos_next.api.offers.frappe.db", new_callable=MagicMock)
	def test_empty_string_customer_is_also_rejected(self, mock_db):
		"""The frontend sends '' rather than omitting the param — must be treated
		the same as no customer at all."""
		mock_db.table_exists.return_value = True

		result = validate_coupon(coupon_code="SAVE10", company="Test Company", customer="")

		self.assertFalse(result["valid"])
		self.assertEqual(result["message"], "Please choose a customer")

	@patch("pos_next.api.offers.frappe.db", new_callable=MagicMock)
	def test_valid_customer_proceeds_to_coupon_lookup(self, mock_db):
		mock_db.table_exists.return_value = True
		mock_db.get_value.return_value = None  # coupon not found

		result = validate_coupon(coupon_code="SAVE10", company="Test Company", customer="Customer A")

		self.assertFalse(result["valid"])
		self.assertEqual(result["message"], "Invalid coupon code")
		mock_db.get_value.assert_any_call(
			"POS Coupon", {"coupon_code": "SAVE10", "company": "Test Company"}, ["*"], as_dict=1
		)
