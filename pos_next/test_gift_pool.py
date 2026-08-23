# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api.gift_pool import (
	PROMOTION_TYPE_GIFT_POOL,
	allocate_gift_pool_free_items,
	gift_pool_item_query,
	group_gift_pool_free_qty,
	group_gift_pool_items,
)
from pos_next.api.invoices import apply_offers
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_B,
	ITEM_C,
	_cart_payload,
	_ctx,
	_line,
	_resolve_company,
	_resolve_item_group,
)


class TestGiftPoolHelpers(unittest.TestCase):
	def test_group_preserves_order_and_uniques(self):
		self.assertEqual(
			group_gift_pool_items(
				[
					{"item_group": "Snacks", "item_code": "A"},
					{"item_group": "Snacks", "item_code": "B"},
					{"item_group": "Drinks", "item_code": "C"},
					{"item_group": "Snacks", "item_code": "A"},
				]
			),
			{"Snacks": ["A", "B"], "Drinks": ["C"]},
		)

	def test_allocate_one_free_item_regardless_of_paid_qty(self):
		self.assertEqual(allocate_gift_pool_free_items(1, ["A", "B", "C"]), {"A": 1})
		self.assertEqual(allocate_gift_pool_free_items(2, ["A", "B", "C"]), {"A": 1})
		self.assertEqual(allocate_gift_pool_free_items(4, ["A", "B"]), {"A": 1})
		self.assertEqual(allocate_gift_pool_free_items(0, ["A"]), {})
		self.assertEqual(allocate_gift_pool_free_items(3, []), {})

	def test_allocate_uses_configured_free_qty(self):
		self.assertEqual(allocate_gift_pool_free_items(1, ["A", "B"], 3), {"A": 2, "B": 1})
		self.assertEqual(allocate_gift_pool_free_items(5, ["A"], 2), {"A": 2})
		self.assertEqual(allocate_gift_pool_free_items(1, ["A"], 0), {"A": 1})

	def test_allocate_spreads_total_across_item_codes(self):
		self.assertEqual(allocate_gift_pool_free_items(1, ["A", "B", "C"], 3), {"A": 1, "B": 1, "C": 1})
		self.assertEqual(allocate_gift_pool_free_items(1, ["A", "B"], 5), {"A": 3, "B": 2})
		self.assertEqual(allocate_gift_pool_free_items(1, ["A", "B", "C"], 2), {"A": 1, "B": 1})

	def test_group_free_qty_uses_first_row(self):
		self.assertEqual(
			group_gift_pool_free_qty(
				[
					{"item_group": "Snacks", "item_code": "A", "free_qty": 3},
					{"item_group": "Snacks", "item_code": "B", "free_qty": 9},
					{"item_group": "Drinks", "item_code": "C"},
				]
			),
			{"Snacks": 3, "Drinks": 1},
		)


class TestGiftPoolScheme(FrappeTestCase):
	SCHEME_NAME = "_PNXT_TEST_GIFT_POOL"

	def setUp(self):
		super().setUp()
		self.ctx = _ctx()
		self._align_item_groups()
		self._delete_scheme()

	def _align_item_groups(self):
		item_group = self._item_group()
		for item_code in (ITEM_A, ITEM_B, ITEM_C):
			if (
				frappe.db.exists("Item", item_code)
				and frappe.db.get_value("Item", item_code, "item_group") != item_group
			):
				frappe.db.set_value("Item", item_code, "item_group", item_group)
				frappe.clear_document_cache("Item", item_code)

	def tearDown(self):
		self._delete_scheme()
		super().tearDown()

	def _delete_scheme(self):
		if frappe.db.exists("Promotional Scheme", self.SCHEME_NAME):
			frappe.delete_doc(
				"Promotional Scheme",
				self.SCHEME_NAME,
				force=True,
				ignore_permissions=True,
			)
			frappe.db.commit()

	def _skip_if_uninstalled(self):
		if not frappe.db.exists("DocType", "POS Gift Pool Item"):
			self.skipTest("POS Gift Pool Item is not installed")
		if not frappe.db.has_column("Promotional Scheme", "promotion_type"):
			self.skipTest("promotion_type custom field is not installed")

	def _item_group(self):
		return frappe.db.get_value("Item", ITEM_A, "item_group") or _resolve_item_group()

	def _make_scheme(self, pool_items, item_group=None, free_qty=1):
		self._skip_if_uninstalled()
		item_group = item_group or self._item_group()
		scheme = frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": self.SCHEME_NAME,
				"company": _resolve_company(),
				"apply_on": "Item Group",
				"selling": 1,
				"promotion_type": PROMOTION_TYPE_GIFT_POOL,
				"item_groups": [{"item_group": item_group}],
				"gift_pool_items": [
					{"item_group": item_group, "item_code": code, "free_qty": free_qty}
					for code in pool_items
				],
			}
		)
		scheme.insert(ignore_permissions=True)
		frappe.db.commit()
		return scheme

	def _rule_name(self):
		return frappe.db.get_value(
			"Pricing Rule", {"promotional_scheme": self.SCHEME_NAME, "disable": 0}, "name"
		)

	def test_item_query_returns_dicts_for_multiselect(self):
		rows = gift_pool_item_query(
			"Item",
			"",
			"name",
			0,
			20,
			{"item_group": self._item_group()},
			as_dict=True,
		)
		self.assertTrue(rows)
		self.assertIsInstance(rows[0], dict)
		self.assertIn("name", rows[0])
		self.assertIn("item_name", rows[0])
		self.assertIn("item_group", rows[0])

	def test_item_query_returns_lists_for_link_search(self):
		rows = gift_pool_item_query(
			"Item",
			"",
			"name",
			0,
			20,
			{"item_group": self._item_group()},
			as_dict=False,
		)
		self.assertTrue(rows)
		self.assertIsInstance(rows[0], (list, tuple))
		self.assertGreaterEqual(len(rows[0]), 3)

	def test_buy_paid_item_gets_first_pool_item(self):
		self._make_scheme([ITEM_B, ITEM_C])
		rule = self._rule_name()
		self.assertTrue(rule)

		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		free_items = resp.get("free_items") or []
		self.assertEqual(len(free_items), 1)
		self.assertEqual(free_items[0].get("item_code"), ITEM_B)
		self.assertEqual(flt(free_items[0].get("qty")), 1)

	def test_two_paid_units_still_get_one_free_item(self):
		self._make_scheme([ITEM_B, ITEM_C])
		rule = self._rule_name()
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=2)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		free_items = resp.get("free_items") or []
		self.assertEqual(len(free_items), 1)
		self.assertEqual(free_items[0].get("item_code"), ITEM_B)
		self.assertEqual(flt(free_items[0].get("qty")), 1)

	def test_configured_free_qty_is_granted(self):
		self._make_scheme([ITEM_B, ITEM_C], free_qty=2)
		rule = self._rule_name()
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		free_items = resp.get("free_items") or []
		by_code = {row.get("item_code"): flt(row.get("qty")) for row in free_items}
		self.assertEqual(by_code, {ITEM_B: 1, ITEM_C: 1})
		self.assertEqual(sum(by_code.values()), 2)

	def test_pool_item_does_not_trigger_gift(self):
		self._make_scheme([ITEM_B, ITEM_C])
		rule = self._rule_name()
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_B, qty=1)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		self.assertEqual(resp.get("free_items") or [], [])

	def test_free_item_must_belong_to_group(self):
		self._skip_if_uninstalled()
		item_group = self._item_group()
		other_group = frappe.db.get_value(
			"Item Group",
			{"name": ["not in", [item_group, "All Item Groups"]], "is_group": 0},
			"name",
		)
		if not other_group:
			self.skipTest("No alternate item group available")

		scheme = frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": self.SCHEME_NAME,
				"company": _resolve_company(),
				"apply_on": "Item Group",
				"selling": 1,
				"promotion_type": PROMOTION_TYPE_GIFT_POOL,
				"item_groups": [{"item_group": other_group}],
				"gift_pool_items": [{"item_group": other_group, "item_code": ITEM_A}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			scheme.insert(ignore_permissions=True)


if __name__ == "__main__":
	unittest.main()
