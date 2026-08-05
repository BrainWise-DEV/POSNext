# Copyright (c) 2026, POS Next and contributors

"""Tests for recursive product discounts (same-item included free + item-group aggregate)."""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api.invoices import apply_offers
from pos_next.api.product_free import (
	compute_additional_recursive_free_qty,
	compute_included_recursive_free_qty,
	compute_product_recursive_free_qty,
	should_aggregate_product_quantities,
)
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_B,
	ITEM_C,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_item_group,
)

_RECURSIVE_TEST_PREFIX = "_PNXT_TEST_Recursive"


def _cleanup_recursive_test_rules():
	for name in frappe.get_all(
		"Pricing Rule",
		filters={"title": ["like", f"{_RECURSIVE_TEST_PREFIX}%"]},
		pluck="name",
	):
		frappe.delete_doc("Pricing Rule", name, force=True, ignore_permissions=True)


def _disable_conflicting_product_rules():
	"""Avoid MultiplePricingRuleConflict with site fixtures during apply_offers."""
	names = frappe.get_all(
		"Pricing Rule",
		filters={
			"disable": 0,
			"selling": 1,
			"price_or_product_discount": "Product",
			"title": ["not like", f"{_RECURSIVE_TEST_PREFIX}%"],
		},
		pluck="name",
	)
	disabled = []
	for name in names:
		frappe.db.set_value("Pricing Rule", name, "disable", 1, update_modified=False)
		disabled.append(name)
	return disabled


def _restore_product_rules(names):
	for name in names:
		if frappe.db.exists("Pricing Rule", name):
			frappe.db.set_value("Pricing Rule", name, "disable", 0, update_modified=False)


class TestProductFreeHelpers(FrappeTestCase):
	def test_included_recursive_free_qty(self):
		# Buy 2 get 1 free from purchased qty → cycle of 3
		self.assertEqual(compute_included_recursive_free_qty(2, 1, 2), 0)
		self.assertEqual(compute_included_recursive_free_qty(3, 1, 2), 1)
		self.assertEqual(compute_included_recursive_free_qty(5, 1, 2), 1)
		self.assertEqual(compute_included_recursive_free_qty(6, 1, 2), 2)

	def test_additional_recursive_free_qty(self):
		self.assertEqual(compute_additional_recursive_free_qty(6, 1, 2), 3)
		self.assertEqual(compute_additional_recursive_free_qty(5, 1, 2), 2)
		self.assertEqual(compute_additional_recursive_free_qty(2, 1, 2), 1)

	def test_product_recursive_dispatch(self):
		self.assertEqual(
			compute_product_recursive_free_qty(
				6, 1, 2, same_item=True, is_recursive=True, min_qty=2
			),
			2,
		)
		self.assertEqual(
			compute_product_recursive_free_qty(
				3, 1, 2, same_item=True, is_recursive=True, min_qty=2
			),
			1,
		)
		self.assertEqual(
			compute_product_recursive_free_qty(
				2, 1, 2, same_item=True, is_recursive=True, min_qty=2
			),
			0,
		)
		self.assertEqual(
			compute_product_recursive_free_qty(
				6, 1, 2, same_item=False, is_recursive=True, min_qty=2
			),
			3,
		)

	def test_should_aggregate_scopes(self):
		self.assertTrue(should_aggregate_product_quantities("Item Group"))
		self.assertTrue(should_aggregate_product_quantities("Brand"))
		# Item Code is always per-SKU — even with multiple codes on the scheme
		self.assertFalse(should_aggregate_product_quantities("Item Code", 2))
		self.assertFalse(should_aggregate_product_quantities("Item Code", 1))


class TestRecursiveSameItemFree(FrappeTestCase):
	def setUp(self):
		_cleanup_recursive_test_rules()
		self._disabled_rules = _disable_conflicting_product_rules()

	def tearDown(self):
		_cleanup_recursive_test_rules()
		_restore_product_rules(getattr(self, "_disabled_rules", []))

	def test_same_item_recursive_uses_included_free_qty(self):
		"""Buy 2 get 1 free from qty: need 3 for 1 free; qty 6 → 2 free."""
		rule = _make_rule(
			f"{_RECURSIVE_TEST_PREFIX}SameIncluded",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=2,
			max_qty=10,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			is_recursive=1,
			recurse_for=2,
			round_free_qty=1,
			priority="20",
		)
		ctx = _ctx()

		# qty 2: eligible by min_qty but no free yet — must not stay Applied
		resp2 = apply_offers(
			invoice_data=json.dumps(_cart_payload(ctx, [_line(ctx, ITEM_A, qty=2)])),
			selected_offers=json.dumps([rule]),
		)
		item2 = resp2["items"][0]
		self.assertEqual(flt(item2.get("free_qty") or 0), 0)
		self.assertEqual(flt(item2.get("discount_amount") or 0), 0)
		self.assertNotIn(rule, resp2.get("applied_pricing_rules") or [])
		self.assertEqual(resp2.get("free_items"), [])

		# qty 3: 1 free (pay 2)
		resp3 = apply_offers(
			invoice_data=json.dumps(_cart_payload(ctx, [_line(ctx, ITEM_A, qty=3)])),
			selected_offers=json.dumps([rule]),
		)
		item3 = resp3["items"][0]
		self.assertEqual(item3.get("discount_source"), "free_item")
		self.assertEqual(flt(item3.get("free_qty")), 1)
		self.assertAlmostEqual(flt(item3.get("discount_amount")), 50, places=2)
		self.assertEqual(flt(item3.get("discount_percentage") or 0), 0)
		self.assertIn(rule, resp3.get("applied_pricing_rules") or [])

		resp6 = apply_offers(
			invoice_data=json.dumps(_cart_payload(ctx, [_line(ctx, ITEM_A, qty=6)])),
			selected_offers=json.dumps([rule]),
		)
		item6 = resp6["items"][0]
		self.assertEqual(item6.get("discount_source"), "free_item")
		self.assertEqual(flt(item6.get("free_qty")), 2)
		self.assertAlmostEqual(flt(item6.get("discount_amount")), 100, places=2)
		self.assertEqual(resp6.get("free_items"), [])

	def test_item_group_same_item_per_sku(self):
		"""Same-item on Item Group: each SKU that meets cycle gets its own free."""
		item_group = _resolve_item_group()
		frappe.db.set_value("Item", ITEM_A, "item_group", item_group)
		frappe.db.set_value("Item", ITEM_B, "item_group", item_group)

		rule = _make_rule(
			f"{_RECURSIVE_TEST_PREFIX}GroupSame",
			apply_on="Item Group",
			item_groups=[{"item_group": item_group}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=2,
			max_qty=10,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			is_recursive=1,
			recurse_for=2,
			round_free_qty=1,
			priority="20",
		)
		ctx = _ctx()
		# 3 + 3 → 1 free on each line (not 2 free dumped on cheapest)
		resp = apply_offers(
			invoice_data=json.dumps(
				_cart_payload(ctx, [_line(ctx, ITEM_A, qty=3), _line(ctx, ITEM_B, qty=3)])
			),
			selected_offers=json.dumps([rule]),
		)
		by_code = {it["item_code"]: it for it in resp["items"]}
		self.assertEqual(flt(by_code[ITEM_A].get("free_qty")), 1)
		self.assertEqual(by_code[ITEM_A].get("discount_source"), "free_item")
		self.assertEqual(flt(by_code[ITEM_B].get("free_qty")), 1)
		self.assertEqual(by_code[ITEM_B].get("discount_source"), "free_item")
		self.assertEqual(resp.get("free_items"), [])

		# 1 + 2: neither line completes a cycle of 3 → no free, not Applied
		resp2 = apply_offers(
			invoice_data=json.dumps(
				_cart_payload(ctx, [_line(ctx, ITEM_A, qty=1), _line(ctx, ITEM_B, qty=2)])
			),
			selected_offers=json.dumps([rule]),
		)
		for it in resp2["items"]:
			self.assertEqual(flt(it.get("free_qty") or 0), 0)
			self.assertEqual(flt(it.get("discount_amount") or 0), 0)
		self.assertNotIn(rule, resp2.get("applied_pricing_rules") or [])

	def test_item_group_recursive_qty_two_not_applied(self):
		"""1+1 total 2: no free yet and must not show as Applied."""
		item_group = _resolve_item_group()
		frappe.db.set_value("Item", ITEM_A, "item_group", item_group)
		frappe.db.set_value("Item", ITEM_B, "item_group", item_group)

		rule = _make_rule(
			f"{_RECURSIVE_TEST_PREFIX}GroupOnePlusOne",
			apply_on="Item Group",
			item_groups=[{"item_group": item_group}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=2,
			max_qty=10,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			is_recursive=1,
			recurse_for=2,
			round_free_qty=1,
			priority="20",
		)
		ctx = _ctx()
		resp = apply_offers(
			invoice_data=json.dumps(
				_cart_payload(ctx, [_line(ctx, ITEM_A, qty=1), _line(ctx, ITEM_B, qty=1)])
			),
			selected_offers=json.dumps([rule]),
		)
		for it in resp["items"]:
			self.assertEqual(flt(it.get("free_qty") or 0), 0)
			self.assertEqual(flt(it.get("discount_amount") or 0), 0)
		self.assertNotIn(rule, resp.get("applied_pricing_rules") or [])
		self.assertEqual(resp.get("free_items"), [])

	def test_item_group_recursive_other_item_aggregates(self):
		"""1+1 in group with other free item → 1 free gift (additional), not per-SKU."""
		item_group = _resolve_item_group()
		frappe.db.set_value("Item", ITEM_A, "item_group", item_group)
		frappe.db.set_value("Item", ITEM_B, "item_group", item_group)

		rule = _make_rule(
			f"{_RECURSIVE_TEST_PREFIX}GroupOther",
			apply_on="Item Group",
			item_groups=[{"item_group": item_group}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_C,
			min_qty=2,
			max_qty=10,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			is_recursive=1,
			recurse_for=2,
			round_free_qty=1,
			priority="20",
		)
		ctx = _ctx()
		resp = apply_offers(
			invoice_data=json.dumps(
				_cart_payload(ctx, [_line(ctx, ITEM_A, qty=1), _line(ctx, ITEM_B, qty=1)])
			),
			selected_offers=json.dumps([rule]),
		)
		free_items = resp.get("free_items") or []
		self.assertEqual(len(free_items), 1)
		self.assertEqual(free_items[0].get("item_code"), ITEM_C)
		self.assertEqual(flt(free_items[0].get("qty")), 1)

	def test_item_code_recursive_other_item_per_sku(self):
		"""Multi Item Code: each SKU earns its own free gift (3+3 → 2, not 3)."""
		rule = _make_rule(
			f"{_RECURSIVE_TEST_PREFIX}MultiCodeOther",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}, {"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_C,
			min_qty=2,
			max_qty=10,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			is_recursive=1,
			recurse_for=2,
			round_free_qty=1,
			priority="20",
		)
		ctx = _ctx()
		resp = apply_offers(
			invoice_data=json.dumps(
				_cart_payload(ctx, [_line(ctx, ITEM_A, qty=3), _line(ctx, ITEM_B, qty=3)])
			),
			selected_offers=json.dumps([rule]),
		)
		free_items = resp.get("free_items") or []
		self.assertEqual(len(free_items), 1)
		self.assertEqual(free_items[0].get("item_code"), ITEM_C)
		# floor(3/2)+floor(3/2) = 1+1 = 2 — not floor(6/2)=3
		self.assertEqual(flt(free_items[0].get("qty")), 2)


if __name__ == "__main__":
	unittest.main()
