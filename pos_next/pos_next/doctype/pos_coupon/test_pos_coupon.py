# Copyright (c) 2021, Youssef Restom and Contributors
# See license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
    _get_customer_coupon_usage_count,
)


class TestPOSCoupon(unittest.TestCase):
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.get_meta")
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
    def test_one_use_coupon_counts_sales_invoice_and_pos_invoice(self, mock_db, mock_get_meta):
        def table_exists(doctype):
            return doctype in {"Sales Invoice", "POS Invoice"}

        def count(doctype, filters=None):
            counts = {"Sales Invoice": 1, "POS Invoice": 2}
            return counts[doctype]

        mock_db.table_exists.side_effect = table_exists
        mock_db.count.side_effect = count
        mock_get_meta.return_value = Mock(has_field=Mock(return_value=True))

        used_count = _get_customer_coupon_usage_count("Customer A", "SAVE10")

        self.assertEqual(used_count, 3)
        mock_db.count.assert_any_call(
            "Sales Invoice",
            filters={"customer": "Customer A", "coupon_code": "SAVE10", "docstatus": 1},
        )
        mock_db.count.assert_any_call(
            "POS Invoice",
            filters={"customer": "Customer A", "coupon_code": "SAVE10", "docstatus": 1},
        )

    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.get_meta")
    @patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
    def test_one_use_coupon_skips_doctypes_without_coupon_field(self, mock_db, mock_get_meta):
        mock_db.table_exists.return_value = True
        mock_db.count.return_value = 4
        mock_get_meta.side_effect = [
            Mock(has_field=Mock(return_value=True)),
            Mock(has_field=Mock(return_value=False)),
        ]

        used_count = _get_customer_coupon_usage_count("Customer A", "SAVE10")

        self.assertEqual(used_count, 4)
        mock_db.count.assert_called_once_with(
            "Sales Invoice",
            filters={"customer": "Customer A", "coupon_code": "SAVE10", "docstatus": 1},
        )
