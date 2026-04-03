# Copyright (c) 2021, Youssef Restom and Contributors
# See license.txt

import unittest
from unittest.mock import patch

from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
	decrement_coupon_usage,
	rollback_coupon_usage,
)


class TestPOSCoupon(unittest.TestCase):
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
	def test_rollback_coupon_usage_locks_and_updates_without_commit(self, mock_db):
		mock_db.sql.return_value = [{"name": "PROMO-0001", "used": 2}]

		result = rollback_coupon_usage("promo10")

		self.assertEqual(result["used"], 1)
		mock_db.sql.assert_called_once()
		mock_db.set_value.assert_called_once_with(
			"POS Coupon",
			"PROMO-0001",
			"used",
			1,
			update_modified=False,
		)
		self.assertFalse(mock_db.commit.called)

	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.rollback_coupon_usage")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.log_error")
	def test_decrement_coupon_usage_re_raises_failures(self, mock_log_error, mock_rollback):
		mock_rollback.side_effect = RuntimeError("boom")

		with self.assertRaises(RuntimeError):
			decrement_coupon_usage("promo10")

		mock_log_error.assert_called_once()
