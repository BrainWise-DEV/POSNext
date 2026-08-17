# Copyright (c) 2026, POS Next and contributors

"""Out-of-stock free gifts must be omitted so paid checkout can continue."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api.invoices import (
	_filter_out_of_stock_free_items,
	_free_item_row_names_blocked_by_stock,
	_strip_out_of_stock_free_items_from_invoice,
	apply_offers,
)
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_B,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_item_group,
)

ITEM_OOS = "_PNXT_TEST_ITEM_OOS"


def _ensure_oos_item():
	if frappe.db.exists("Item", ITEM_OOS):
		return ITEM_OOS
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM_OOS,
			"item_name": "Out Of Stock Gift",
			"item_group": _resolve_item_group(),
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
	)
	item.flags.from_integration = True
	item.insert(ignore_permissions=True)
	return ITEM_OOS


class _Row:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

	def get(self, key, default=None):
		return getattr(self, key, default)


class _Invoice:
	def __init__(self, items, packed_items=None):
		self.items = list(items)
		self.packed_items = list(packed_items or [])

	def get(self, key, default=None):
		return getattr(self, key, default)

	def remove(self, row):
		if row in self.items:
			self.items.remove(row)
		if row in self.packed_items:
			self.packed_items.remove(row)


class TestFilterOutOfStockFreeItems(FrappeTestCase):
	def test_drops_oos_gift_and_keeps_in_stock(self):
		free_items_map = {
			("OOS", "RULE1"): frappe._dict({"item_code": "OOS", "item_name": "OOS", "qty": 1}),
			("OK", "RULE2"): frappe._dict({"item_code": "OK", "item_name": "OK", "qty": 1}),
		}
		applied = {"RULE1", "RULE2"}
		rule_map = {
			"RULE1": frappe._dict(price_or_product_discount="Product"),
			"RULE2": frappe._dict(price_or_product_discount="Product"),
		}

		def stock(item):
			return 0 if item.get("item_code") == "OOS" else 10

		with (
			patch("pos_next.api.invoices._should_block", return_value=True),
			patch("pos_next.api.invoices._item_is_stock_item", return_value=True),
			patch("pos_next.api.invoices._get_item_negative_stock_allow_set", return_value=set()),
			patch("pos_next.api.invoices._get_available_stock", side_effect=stock),
		):
			skipped = _filter_out_of_stock_free_items(
				free_items_map,
				"WH",
				[],
				"PROFILE",
				rule_map=rule_map,
				applied_rules=applied,
			)

		self.assertEqual(list(free_items_map.keys()), [("OK", "RULE2")])
		self.assertEqual(skipped[0]["item_code"], "OOS")
		self.assertNotIn("RULE1", applied)
		self.assertIn("RULE2", applied)

	def test_paid_qty_consumes_stock_before_gift(self):
		free_items_map = {
			("MOUSE", "RULE1"): frappe._dict({"item_code": "MOUSE", "qty": 1}),
		}
		paid = [{"item_code": "MOUSE", "qty": 1, "warehouse": "WH", "conversion_factor": 1}]

		with (
			patch("pos_next.api.invoices._should_block", return_value=True),
			patch("pos_next.api.invoices._item_is_stock_item", return_value=True),
			patch("pos_next.api.invoices._get_item_negative_stock_allow_set", return_value=set()),
			patch("pos_next.api.invoices._get_available_stock", return_value=1),
		):
			skipped = _filter_out_of_stock_free_items(
				free_items_map, "WH", paid, "PROFILE"
			)

		self.assertEqual(free_items_map, {})
		self.assertEqual(skipped[0]["item_code"], "MOUSE")

	def test_does_not_filter_when_negative_stock_allowed(self):
		free_items_map = {
			("OOS", "RULE1"): frappe._dict({"item_code": "OOS", "qty": 1}),
		}
		with patch("pos_next.api.invoices._should_block", return_value=False):
			skipped = _filter_out_of_stock_free_items(free_items_map, "WH", [], "PROFILE")
		self.assertEqual(len(free_items_map), 1)
		self.assertEqual(skipped, [])


class TestStripOutOfStockFreeItems(FrappeTestCase):
	def test_identifies_free_row_from_stock_error(self):
		free = _Row(name="row-free", item_code="mouse bad", is_free_item=1)
		paid = _Row(name="row-paid", item_code="laptop", is_free_item=0)
		doc = _Invoice([paid, free])
		names = _free_item_row_names_blocked_by_stock(
			doc,
			[{"item_code": "mouse bad", "available_qty": 0, "requested_qty": 1}],
		)
		self.assertEqual(names, {"row-free"})

	def test_identifies_free_bundle_from_packed_component_error(self):
		free = _Row(name="row-free", item_code="BUNDLE", is_free_item=1)
		packed = _Row(item_code="MOUSE", parent_detail_docname="row-free")
		doc = _Invoice([free], packed_items=[packed])
		names = _free_item_row_names_blocked_by_stock(
			doc, [{"item_code": "MOUSE"}]
		)
		self.assertEqual(names, {"row-free"})

	def test_strips_only_free_rows(self):
		free = _Row(name="row-free", item_code="mouse bad", is_free_item=1)
		paid = _Row(name="row-paid", item_code="laptop", is_free_item=0)
		doc = _Invoice([paid, free])
		removed = _strip_out_of_stock_free_items_from_invoice(
			doc, [{"item_code": "mouse bad"}]
		)
		self.assertEqual(removed, ["mouse bad"])
		self.assertEqual([row.name for row in doc.items], ["row-paid"])


class TestApplyOffersSkipsOosFreeItem(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		_ensure_oos_item()

	def test_oos_different_item_gift_is_skipped(self):
		rule = _make_rule(
			"_PNXT_TEST_FreeOOS",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_OOS,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])

		def stock(item):
			if item.get("item_code") == ITEM_OOS:
				return 0
			return 100

		with (
			patch("pos_next.api.invoices._should_block", return_value=True),
			patch("pos_next.api.invoices._get_available_stock", side_effect=stock),
		):
			resp = apply_offers(
				invoice_data=json.dumps(payload),
				selected_offers=json.dumps([rule]),
			)

		self.assertEqual(resp.get("free_items") or [], [])
		skipped_codes = [row.get("item_code") for row in resp.get("skipped_free_items") or []]
		self.assertIn(ITEM_OOS, skipped_codes)
		self.assertEqual(flt_paid_qty(resp), 1)

	def test_in_stock_different_item_gift_still_applies(self):
		rule = _make_rule(
			"_PNXT_TEST_FreeInStock",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_A,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_B, qty=1)])

		with (
			patch("pos_next.api.invoices._should_block", return_value=True),
			patch("pos_next.api.invoices._get_available_stock", return_value=50),
		):
			resp = apply_offers(
				invoice_data=json.dumps(payload),
				selected_offers=json.dumps([rule]),
			)

		free_codes = [row.get("item_code") for row in resp.get("free_items") or []]
		self.assertIn(ITEM_A, free_codes)
		self.assertEqual(resp.get("skipped_free_items") or [], [])


def flt_paid_qty(resp):
	items = resp.get("items") or []
	return sum(
		float(row.get("qty") or row.get("quantity") or 0)
		for row in items
		if not row.get("is_free_item")
	)


if __name__ == "__main__":
	unittest.main()
