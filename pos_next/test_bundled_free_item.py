# Copyright (c) 2026, POS Next and contributors

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api.invoices import apply_offers
from pos_next.test_promotions import ITEM_A, _cart_payload, _ctx, _line, _make_rule


class TestBundledSameItemFree(FrappeTestCase):
	def test_same_item_free_bundles_on_paid_line(self):
		rule = _make_rule(
			"_PNXT_TEST_BundledFree",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=4,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(_ctx(), [_line(_ctx(), ITEM_A, qty=4)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		self.assertEqual(resp.get("free_items"), [])
		item = resp["items"][0]
		self.assertEqual(item.get("discount_source"), "free_item")
		self.assertEqual(flt(item.get("free_qty")), 1)
		self.assertGreater(flt(item.get("discount_amount")), 0)

	def test_same_item_free_not_applied_below_min_qty(self):
		rule = _make_rule(
			"_PNXT_TEST_BundledFreeLow",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=4,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(_ctx(), [_line(_ctx(), ITEM_A, qty=3)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		item = resp["items"][0]
		self.assertEqual(flt(item.get("free_qty")), 0)
		self.assertEqual(resp.get("free_items"), [])


if __name__ == "__main__":
	unittest.main()
