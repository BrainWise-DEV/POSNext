"""Pins posnext_promotions' Min/Max per-unit rate, which the POS cart mirrors (G6).

A Min/Max rule spreads its free or discounted units over the line as one blended
percentage, and apply_offers prices the line at a per-unit rate at currency precision:
one free unit in six at 50 is 41.67 a unit, so the line is 250.02. A row is saved at a
per-unit rate too (the rate the cart sends, which the paid-row check holds to the
offer), so the cart's ``unitRateLineDiscount`` (POS/src/utils/currency.js) prices the
line the same way, or the screen, the amount collected and the invoice differ by cents.

The vitest fixture ``fixtures-minmax-buy-one.json`` holds the apply_offers answers and
the invoices nexus.local saved for "buy one" carts; this test checks the server's own
algorithm still gives them. Read-only: no documents are written.

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.test_minmax_unit_rate'}"
"""

import json
import os
import unittest

import frappe
from frappe.utils import flt

FIXTURE = os.path.join(
	os.path.dirname(__file__), "..", "POS", "src", "stores", "__tests__", "fixtures-minmax-buy-one.json"
)

# "buy one": 100% off one unit of the cheapest line (Min, discounted-qty limit 1).
BUY_ONE = {"rate_or_discount": "Discount Percentage", "discount_percentage": 100}


class TestMinMaxUnitRate(unittest.TestCase):
	def setUp(self):
		if "posnext_promotions" not in frappe.get_installed_apps():
			self.skipTest("posnext_promotions is not installed")
		from posnext_promotions.overrides.pricing_rule import _apply_discount

		self.apply = _apply_discount

	def line(self, price, qty, eligible_qty=1, rule=BUY_ONE):
		item = frappe._dict(price_list_rate=price, qty=qty)
		self.apply(rule, item, eligible_qty)
		return item

	def test_the_fixture_is_what_the_server_saves(self):
		with open(FIXTURE) as f:
			fixture = json.load(f)
		self.assertEqual([case["qty"] for case in fixture["cases"]], [2, 3, 4, 6, 7])
		for case in fixture["cases"]:
			expected = case["line"]
			item = self.line(expected["price_list_rate"], case["qty"])
			msg = f"qty {case['qty']}"
			self.assertAlmostEqual(item.discount_percentage, expected["discount_percentage"], places=9, msg=msg)
			self.assertAlmostEqual(item.rate, expected["rate"], places=9, msg=msg)
			self.assertAlmostEqual(item.amount, expected["amount"], places=9, msg=msg)
			self.assertAlmostEqual(item.rate, case["invoice"]["rate"], places=9, msg=msg)
			self.assertAlmostEqual(item.amount, case["invoice"]["grand_total"], places=9, msg=msg)

	def test_one_free_in_six_at_50_is_41_67_a_unit(self):
		item = self.line(50, 6)
		self.assertAlmostEqual(item.rate, 41.67, places=9)
		self.assertAlmostEqual(item.amount, 250.02, places=9)

	def test_the_rate_follows_the_unrounded_percentage(self):
		# 80 × 6: 16.666…% gives 66.67 a unit (400.02). The 2-dp 16.67% would give
		# 66.66, so the cart prices from the server's own, unrounded percentage.
		item = self.line(80, 6)
		self.assertAlmostEqual(item.rate, 66.67, places=9)
		self.assertAlmostEqual(item.amount, 400.02, places=9)
		self.assertNotAlmostEqual(flt(80 * (1 - 16.67 / 100), 2), item.rate, places=9)

	def test_the_drift_can_go_down(self):
		# 80 × 7: 68.57 a unit, 479.99, a cent under the exact 480.
		item = self.line(80, 7)
		self.assertAlmostEqual(item.rate, 68.57, places=9)
		self.assertAlmostEqual(item.amount, 479.99, places=9)

	def test_a_part_percentage_rule_drifts_too(self):
		# 50% off one unit of three at 50: 125 / 3 → 41.67 a unit, 125.01.
		item = self.line(50, 3, rule={"rate_or_discount": "Discount Percentage", "discount_percentage": 50})
		self.assertAlmostEqual(item.rate, 41.67, places=9)
		self.assertAlmostEqual(item.amount, 125.01, places=9)
