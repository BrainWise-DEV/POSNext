# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""A capped F&F line saves the per-unit rate the POS cart mirrors (D-7).

The cart's ``cappedUnitValues`` (POS/src/utils/friendsAndFamily.js) must give the
values a saved invoice row gets, or the payment-open check sees a different total.
Pinned through pos_next's own unpaid draft save (``update_invoice``), so the
optional promotions app is reached only through its document hooks, never an
import: the net unit rate is rounded UP to the currency unit, so the line never
saves more than its allowance (cap 40 on 3 × 50 → 36.67 a unit, saving 39.99).

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_ff_capped_unit_rate'}"
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import update_invoice
from pos_next.api.test_ff_markers import enable_ff
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_TEST_FFCAP_"
PRICE = ITEM_PRICES[ITEM_A]  # 50


class TestCappedUnitRate(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.customer = (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"{PREFIX}{token}",
					"customer_group": _resolve_customer_group(),
					"territory": _resolve_territory(),
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.domain = f"ffcap{token}.example"

	def _draft_row(self, qty, cap):
		enable_ff(self, self.customer, self.domain, max_discount_per_order=cap)
		line = _line(self.ctx, ITEM_A, qty=qty)
		line["posnext_discount_source"] = invoices.FNF_DISCOUNT_SOURCE
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		result = update_invoice(json.dumps(payload))
		self.addCleanup(frappe.delete_doc, "Sales Invoice", result["name"], force=True, ignore_permissions=True)
		row = frappe.get_doc("Sales Invoice", result["name"]).items[0]
		block = (result.get("friends_and_family") or {}).get("items") or []
		return row, block

	def _assert(self, qty, cap, rate, saving):
		row, block = self._draft_row(qty, cap)
		self.assertAlmostEqual(flt(row.rate), rate, places=9)
		self.assertAlmostEqual(flt(row.discount_amount), round(PRICE - rate, 2), places=9)
		self.assertAlmostEqual(flt(PRICE - row.rate) * qty, saving, places=6)
		self.assertLessEqual(saving, cap)
		# The F&F block the POS adopts carries the same unit-basis values.
		self.assertTrue(block and block[0].get("capped"))
		self.assertAlmostEqual(flt(block[0].get("rate")), rate, places=9)

	def test_cap_40_on_3_x_50_is_36_67_a_unit(self):
		self._assert(3, 40, 36.67, 39.99)

	def test_cap_50_on_7_x_50_is_42_86_a_unit(self):
		self._assert(7, 50, 42.86, 49.98)
