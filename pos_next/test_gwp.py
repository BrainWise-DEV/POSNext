# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

import unittest

from pos_next.api.gwp import (
	GWP_BASIS_MAX,
	GWP_BASIS_MIN,
	calculate_gwp_discount_amount,
	calculate_gwp_discount_percentage,
	distribute_gwp_free_units_by_price,
	distribute_gwp_free_units_for_basis,
	get_gwp_slab_free_qty,
	is_gwp_total_qty_eligible,
	item_matches_pricing_rule_apply_on,
	normalize_gwp_paid_qty_basis,
	should_aggregate_gwp_quantities,
)


class TestGwpDiscount(unittest.TestCase):
	def test_basic_ratio(self):
		self.assertEqual(calculate_gwp_discount_percentage(2, 4), 50)

	def test_exact_discount_amount(self):
		self.assertEqual(calculate_gwp_discount_amount(2, 5000), 10000)

	def test_eligibility_range(self):
		self.assertTrue(is_gwp_total_qty_eligible(4, 4, 4))
		self.assertFalse(is_gwp_total_qty_eligible(3, 4, 4))
		self.assertFalse(is_gwp_total_qty_eligible(5, 4, 4))

	def test_slab_free_qty(self):
		self.assertEqual(get_gwp_slab_free_qty(2, 4, 4, 4), 2)
		self.assertEqual(get_gwp_slab_free_qty(2, 3, 4, 4), 0)

	def test_distribute_max_basis_on_cheapest(self):
		self.assertEqual(
			distribute_gwp_free_units_for_basis([2, 2], [50, 80], 2, GWP_BASIS_MAX),
			[2, 0],
		)

	def test_distribute_min_basis_on_expensive(self):
		self.assertEqual(
			distribute_gwp_free_units_for_basis([2, 2], [50, 80], 2, GWP_BASIS_MIN),
			[0, 2],
		)

	def test_normalize_legacy_basis_labels(self):
		self.assertEqual(normalize_gwp_paid_qty_basis("Min Qty"), GWP_BASIS_MIN)
		self.assertEqual(normalize_gwp_paid_qty_basis("Max Qty"), GWP_BASIS_MAX)
		self.assertEqual(normalize_gwp_paid_qty_basis(None), GWP_BASIS_MAX)

	def test_distribute_by_price_expensive_first(self):
		self.assertEqual(
			distribute_gwp_free_units_by_price([2, 2], [50, 80], 2, expensive_first=True),
			[0, 2],
		)

	def test_should_aggregate(self):
		self.assertTrue(should_aggregate_gwp_quantities("Item Group", 0))
		self.assertTrue(should_aggregate_gwp_quantities("Item Code", 3))
		self.assertFalse(should_aggregate_gwp_quantities("Item Code", 1))

	def test_item_group_matching_uses_child_table(self):
		rule = {
			"apply_on": "Item Group",
			"item_groups": [{"item_group": "Products"}],
		}
		self.assertTrue(
			item_matches_pricing_rule_apply_on({"item_group": "Products"}, rule)
		)
		self.assertFalse(
			item_matches_pricing_rule_apply_on({"item_group": "Services"}, rule)
		)

	def test_mixed_item_code_matching(self):
		rule = {
			"apply_on": "Item Code",
			"mixed_conditions": 1,
			"items": [{"item_code": "A"}, {"item_code": "B"}],
		}
		self.assertTrue(item_matches_pricing_rule_apply_on({"item_code": "A"}, rule))
		self.assertFalse(item_matches_pricing_rule_apply_on({"item_code": "C"}, rule))
