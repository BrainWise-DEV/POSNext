# Copyright (c) 2021, Youssef Restom and Contributors
# See license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
	_get_customer_coupon_usage_count,
	_get_per_customer_use_limit,
	apply_coupon_to_items,
	get_coupon_eligible_items,
)


def _coupon(**kwargs):
	defaults = {
		"coupon_code": "SAVE10",
		"discount_type": "Percentage",
		"discount_percentage": 10,
		"discount_amount": 0,
		"apply_scope": "All Eligible Items",
		"applicable_brand": None,
		"applicable_item_group": None,
		"excluded_brands": [],
		"min_amount": None,
		"max_amount": None,
		"one_use": 0,
		"maximum_use_per_customer": 0,
	}
	defaults.update(kwargs)
	return SimpleNamespace(**defaults)


class TestPOSCoupon(unittest.TestCase):
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.get_meta")
	@patch("pos_next.pos_next.doctype.pos_coupon.pos_coupon.frappe.db")
	def test_one_use_coupon_counts_sales_invoice_and_pos_invoice(self, mock_db, mock_get_meta):
		def table_exists(doctype):
			return doctype in {"Sales Invoice", "POS Invoice"}

		def count(doctype, filters=None):
			counts = {"Sales Invoice": 1, "POS Invoice": 2}
			return counts[doctype]

		mock_db.table_exists = Mock(side_effect=table_exists)
		mock_db.count = Mock(side_effect=count)
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
		mock_db.table_exists = Mock(return_value=True)
		mock_db.count = Mock(return_value=4)
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

	def test_per_customer_limit_from_maximum_use_per_customer(self):
		self.assertEqual(_get_per_customer_use_limit(_coupon(maximum_use_per_customer=3)), 3)

	def test_per_customer_limit_one_use_fallback(self):
		self.assertEqual(_get_per_customer_use_limit(_coupon(one_use=1, maximum_use_per_customer=0)), 1)

	def test_per_customer_limit_unlimited(self):
		self.assertEqual(_get_per_customer_use_limit(_coupon(one_use=0, maximum_use_per_customer=0)), 0)

	def test_eligible_items_exclude_discounted_free_and_excluded_brand(self):
		coupon = _coupon(
			excluded_brands=[{"brand": "BrandX"}],
		)
		items = [
			{
				"item_code": "A",
				"brand": "BrandA",
				"item_group": "Group1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			},
			{
				"item_code": "B",
				"brand": "BrandA",
				"item_group": "Group1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
				"discount_percentage": 5,
			},
			{
				"item_code": "C",
				"brand": "BrandA",
				"item_group": "Group1",
				"qty": 1,
				"price_list_rate": 0,
				"rate": 0,
				"is_free_item": 1,
			},
			{
				"item_code": "D",
				"brand": "BrandX",
				"item_group": "Group1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			},
			{
				"item_code": "E",
				"brand": "BrandA",
				"item_group": "Group1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
				"pricing_rules": ["PR-1"],
			},
		]

		eligible = get_coupon_eligible_items(coupon, items)
		self.assertEqual([i["item_code"] for i in eligible], ["A"])

	def test_scope_brand_and_item_group(self):
		brand_coupon = _coupon(apply_scope="Brand", applicable_brand="Nike")
		group_coupon = _coupon(apply_scope="Item Group", applicable_item_group="Shoes")
		items = [
			{
				"item_code": "NIKE-1",
				"brand": "Nike",
				"item_group": "Apparel",
				"qty": 1,
				"price_list_rate": 50,
				"rate": 50,
			},
			{
				"item_code": "SHOE-1",
				"brand": "Adidas",
				"item_group": "Shoes",
				"qty": 1,
				"price_list_rate": 80,
				"rate": 80,
			},
		]

		self.assertEqual(
			[i["item_code"] for i in get_coupon_eligible_items(brand_coupon, items)],
			["NIKE-1"],
		)
		self.assertEqual(
			[i["item_code"] for i in get_coupon_eligible_items(group_coupon, items)],
			["SHOE-1"],
		)

	def test_percentage_line_discount(self):
		coupon = _coupon(discount_type="Percentage", discount_percentage=20)
		items = [
			{
				"item_code": "A",
				"brand": "B1",
				"item_group": "G1",
				"qty": 2,
				"price_list_rate": 100,
				"rate": 100,
				"idx": 1,
			},
			{
				"item_code": "B",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 50,
				"rate": 50,
				"idx": 2,
			},
		]

		result = apply_coupon_to_items(coupon, items)
		self.assertTrue(result["valid"])
		self.assertEqual(result["total_discount"], 50)  # 20% of 250
		self.assertEqual(len(result["line_updates"]), 2)
		self.assertEqual(result["line_updates"][0]["discount_percentage"], 20)
		# line_key must be 0-based cart index (not 1-based idx)
		self.assertEqual(result["line_updates"][0]["line_key"], 0)
		self.assertEqual(result["line_updates"][1]["line_key"], 1)

	def test_first_cart_item_gets_line_key_zero(self):
		"""Regression: first item must use line_key 0 so UI does not skip it."""
		coupon = _coupon(discount_type="Percentage", discount_percentage=10)
		items = [
			{
				"item_code": "laptop",
				"brand": "B1",
				"item_group": "G1",
				"qty": 2,
				"price_list_rate": 5000,
				"rate": 5000,
				"idx": 1,
			},
			{
				"item_code": "cocacola",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1000,
				"price_list_rate": 10,
				"rate": 10,
				"idx": 2,
			},
		]
		result = apply_coupon_to_items(coupon, items)
		self.assertTrue(result["valid"])
		keys = [u["line_key"] for u in result["line_updates"]]
		self.assertEqual(keys, [0, 1])
		self.assertEqual(result["line_updates"][0]["item_code"], "laptop")

	def test_fixed_amount_distributed_and_max_cap(self):
		coupon = _coupon(
			discount_type="Amount",
			discount_amount=100,
			max_amount=30,
		)
		items = [
			{
				"item_code": "A",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
				"idx": 1,
			},
			{
				"item_code": "B",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
				"idx": 2,
			},
		]

		result = apply_coupon_to_items(coupon, items)
		self.assertTrue(result["valid"])
		self.assertEqual(result["total_discount"], 30)
		allocated = sum(u["discount_amount"] for u in result["line_updates"])
		self.assertAlmostEqual(allocated, 30, places=4)

	def test_percentage_with_max_amount_uses_absolute_amounts(self):
		"""max_amount must cap total and use discount_amount so qty bumps cannot exceed cap."""
		coupon = _coupon(
			discount_type="Percentage",
			discount_percentage=50,
			max_amount=40,
		)
		items = [
			{
				"item_code": "A",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			},
			{
				"item_code": "B",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			},
		]
		result = apply_coupon_to_items(coupon, items)
		self.assertTrue(result["valid"])
		self.assertEqual(result["total_discount"], 40)
		for update in result["line_updates"]:
			self.assertEqual(update["discount_percentage"], 0)
			self.assertGreater(update["discount_amount"], 0)
		self.assertAlmostEqual(
			sum(u["discount_amount"] for u in result["line_updates"]), 40, places=4
		)

	def test_percentage_with_max_amount_under_cap_still_uses_amounts(self):
		coupon = _coupon(
			discount_type="Percentage",
			discount_percentage=10,
			max_amount=100,
		)
		items = [
			{
				"item_code": "A",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			}
		]
		result = apply_coupon_to_items(coupon, items)
		self.assertTrue(result["valid"])
		self.assertEqual(result["total_discount"], 10)
		self.assertEqual(result["line_updates"][0]["discount_percentage"], 0)
		self.assertEqual(result["line_updates"][0]["discount_amount"], 10)

	def test_no_eligible_items_returns_invalid(self):
		coupon = _coupon(apply_scope="Brand", applicable_brand="Missing")
		items = [
			{
				"item_code": "A",
				"brand": "Other",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			}
		]
		result = apply_coupon_to_items(coupon, items)
		self.assertFalse(result["valid"])
		self.assertEqual(result["line_updates"], [])

	def test_min_amount_on_eligible_subtotal(self):
		coupon = _coupon(min_amount=500, discount_percentage=10)
		items = [
			{
				"item_code": "A",
				"brand": "B1",
				"item_group": "G1",
				"qty": 1,
				"price_list_rate": 100,
				"rate": 100,
			}
		]
		result = apply_coupon_to_items(coupon, items)
		self.assertFalse(result["valid"])
		self.assertIn("Minimum eligible amount", result["message"])


if __name__ == "__main__":
	unittest.main()
