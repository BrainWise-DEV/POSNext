# Copyright (c) 2021, Youssef Restom and Contributors
# See license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
	_get_customer_coupon_usage_count,
	customer_coupon_usage_query,
)

MODULE = "pos_next.pos_next.doctype.pos_coupon.pos_coupon"


class TestPOSCoupon(unittest.TestCase):
	def test_usage_query_filters(self):
		sql = str(customer_coupon_usage_query("Customer A", "save10", exclude_name="ACC-SINV-1"))

		self.assertIn("`tabSales Invoice`", sql)
		self.assertNotIn("POS Invoice", sql)
		self.assertIn("`customer`='Customer A'", sql)
		self.assertIn("UPPER(`coupon_code`)='SAVE10'", sql)
		self.assertIn("`docstatus`=1", sql)
		self.assertIn("`is_return`=0", sql)
		self.assertIn("`name`<>'ACC-SINV-1'", sql)
		self.assertNotIn("FOR UPDATE", sql)

	def test_usage_query_without_exclusion_and_locked(self):
		sql = str(customer_coupon_usage_query("Customer A", "SAVE10", lock=True))

		self.assertNotIn("`name`<>", sql)
		self.assertTrue(sql.rstrip().endswith("FOR UPDATE"), sql)

	@patch(f"{MODULE}.frappe.get_meta")
	def test_usage_count_is_zero_before_the_field_exists(self, mock_get_meta):
		mock_get_meta.return_value = Mock(has_field=Mock(return_value=False))

		with patch(f"{MODULE}.customer_coupon_usage_query") as mock_query:
			self.assertEqual(_get_customer_coupon_usage_count("Customer A", "SAVE10"), 0)
		mock_query.assert_not_called()
