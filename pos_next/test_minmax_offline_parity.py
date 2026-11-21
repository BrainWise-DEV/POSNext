"""Pins posnext_promotions' Min/Max pass, which the offline cart mirrors (G7).

Offline, posnext_promotions' Min/Max strategy (public/pos/offer-strategies.js) picks
the line a Min/Max Price rule discounts (the cheapest for Min, the dearest for Max,
across the rule's scope), discounts ``min_or_max_discount_qty_limit`` of its units as
one blended percentage, and the cart prices that line at its 2-dp unit rate (G6). The
vitest fixture ``fixtures-minmax-offline.json`` holds the apply_offers answers
nexus.local gave for each cart; this test runs the server's own Min/Max pass
(``apply_min_max_price_discounts``) on the same carts and checks it still gives them,
so a server change shows up here as well as in the cart.

Read-only: the rule is handed to the pass in memory; no documents are written.

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.test_minmax_offline_parity'}"
"""

import json
import os
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import flt

FIXTURE = os.path.join(
	os.path.dirname(__file__), "..", "POS", "src", "stores", "__tests__", "fixtures-minmax-offline.json"
)


def _rule(offer):
	"""The Pricing Rule fields the Min/Max pass reads, from the offer get_offers built."""
	return frappe._dict(
		name=offer["name"],
		price_or_product_discount="Price",
		apply_discount_on_price=offer["apply_discount_on_price"],
		min_or_max_discount_qty_limit=offer["min_or_max_discount_qty_limit"],
		rate_or_discount=offer["discount_type"],
		rate=offer["rate"],
		discount_percentage=offer["discount_percentage"],
		discount_amount=offer["discount_amount"],
		for_price_list=None,
	)


class TestMinMaxOfflineParity(unittest.TestCase):
	def setUp(self):
		if "posnext_promotions" not in frappe.get_installed_apps():
			self.skipTest("posnext_promotions is not installed")
		self.min_max = frappe.get_attr(
			"posnext_promotions.overrides.pricing_rule.apply_min_max_price_discounts"
		)
		with open(FIXTURE) as f:
			self.fixture = json.load(f)

	def run_pass(self, offer, lines):
		"""The server's Min/Max pass over `lines` tagged as apply_offers tags them."""
		rule = _rule(offer)
		items = [
			frappe._dict(
				item_code=line["item_code"],
				qty=line["qty"],
				price_list_rate=line["price_list_rate"],
				rate=line["price_list_rate"],
				discount_percentage=0,
				pricing_rules=line["pricing_rules"] or "",
			)
			for line in lines
		]
		doc = frappe._dict(items=items, selling_price_list="Standard Selling")
		real = frappe.get_cached_doc

		def cached_doc(doctype, name=None, *args, **kwargs):
			if doctype == "Pricing Rule" and name == rule.name:
				return rule
			return real(doctype, name, *args, **kwargs)

		with patch("frappe.get_cached_doc", side_effect=cached_doc):
			self.min_max(doc)
		return items

	def test_the_fixture_is_what_the_server_gives(self):
		cases = 0
		for title, data in self.fixture["rules"].items():
			for case in data["cases"]:
				items = self.run_pass(data["offer"], case["lines"])
				for item, want in zip(items, case["lines"], strict=True):
					msg = f"{title} {case['cart']} {want['item_code']}"
					self.assertAlmostEqual(
						flt(item.discount_percentage), want["discount_percentage"], places=9, msg=msg
					)
					self.assertAlmostEqual(flt(item.rate), want["rate"], places=9, msg=msg)
					self.assertAlmostEqual(flt(item.rate * item.qty, 2), want["amount"], places=9, msg=msg)
				cases += 1
		self.assertEqual(cases, 16)

	def test_min_and_max_pick_opposite_lines(self):
		offers = {t: d["offer"] for t, d in self.fixture["rules"].items()}
		lines = [
			{"item_code": "A", "qty": 2, "price_list_rate": 50, "pricing_rules": "R"},
			{"item_code": "B", "qty": 2, "price_list_rate": 80, "pricing_rules": "R"},
		]
		low = self.run_pass({**offers["_PNXT_G7_MinAB"], "name": "R"}, lines)
		high = self.run_pass({**offers["_PNXT_G7_MaxAB"], "name": "R"}, lines)
		self.assertEqual([flt(i.rate) for i in low], [25, 80])
		self.assertEqual([flt(i.rate) for i in high], [50, 40])
