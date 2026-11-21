# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""A GWP across two different items backs its free row (D-R2-08).

The cart evaluates offers with the rules it applied (``selected_offers``); a mixed-SKU
GWP (buy A + B, 2 in all, get A free) is only granted that way, because ERPNext's
per-item lookup reads min_qty on each item alone (1 < 2). The free-row backing check
now evaluates with the rule names the cart's rows carry, but only those the server's
own rule lookup finds for this cart: a forged free row is still refused.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_mixed_gwp'}"
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, cint, flt, nowdate

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.optional_apps import promotions_installed
from pos_next.api.test_ff_markers import enable_ff
from pos_next.test_promotions import (
	_cart_payload,
	_ctx,
	_make_rule,
	_resolve_company,
	_resolve_customer_group,
	_resolve_item_group,
	_resolve_territory,
)

# Every name carries the prefix, so the refusals' Error Logs can be found and deleted.
PREFIX = "_PNXT_G1_"
ITEM_A = f"{PREFIX}GWP1"  # 30, the gift (cheapest, Max Price basis)
ITEM_B = f"{PREFIX}GWP2"  # 45
ITEM_C = f"{PREFIX}OTHER_ITEM"  # 20, in no GWP of a cart here
PRICES = {ITEM_A: 30.0, ITEM_B: 45.0, ITEM_C: 20.0}
CUSTOMER = f"{PREFIX}CUSTOMER"
OTHER_CUSTOMER = f"{PREFIX}OTHER"
SCHEME = f"{PREFIX}SCHEME"
EMAIL_DOMAIN = "g1gwp.example"
FNF = "friends_and_family"
NOT_BACKED = "not backed by an offer"


def _ensure_customer(name):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": _resolve_customer_group(),
				"territory": _resolve_territory(),
				"customer_type": "Individual",
			}
		).insert(ignore_permissions=True)


class TestMixedGwp(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		if not frappe.db.has_column("Pricing Rule", "promotion_type"):
			raise unittest.SkipTest("promotions' GWP fields are not installed")
		cls.ctx = _ctx()
		_ensure_customer(CUSTOMER)
		_ensure_customer(OTHER_CUSTOMER)
		for code, price in PRICES.items():
			if not frappe.db.exists("Item", code):
				item = frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": _resolve_item_group(),
						"stock_uom": "Nos",
						"is_stock_item": 0,
					}
				)
				item.flags.from_integration = True
				item.insert(ignore_permissions=True)
			if not frappe.db.exists("Item Price", {"item_code": code, "price_list": cls.ctx.price_list}):
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": code,
						"price_list": cls.ctx.price_list,
						"price_list_rate": price,
					}
				).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		# The refusals' Error Logs are deferred inserts that outlive the rollback.
		from frappe.deferred_insert import save_to_db

		frappe.db.rollback()
		save_to_db()
		for name in frappe.get_all(
			"Error Log", filters={"error": ["like", f"%{PREFIX}%"]}, pluck="name"
		):
			frappe.delete_doc("Error Log", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	# ---- helpers -----------------------------------------------------------

	def _gwp_rule(self, title="GWP", customer=CUSTOMER, **fields):
		"""UIT-PR-GWP's shape: buy ITEM_A / ITEM_B, 2 in all, get ITEM_A free."""
		defaults = {
			"apply_on": "Item Code",
			"items": [{"item_code": ITEM_A}, {"item_code": ITEM_B}],
			"price_or_product_discount": "Product",
			"rate_or_discount": "Discount Percentage",
			"same_item": 0,
			"free_item": ITEM_A,
			"free_qty": 1,
			"free_item_uom": "Nos",
			"free_item_rate": 0,
			"min_qty": 2,
			"promotion_type": "GWP",
			"gwp_paid_qty_basis": "Max Price",
			"applicable_for": "Customer",
			"customer": customer,
		}
		name = _make_rule(f"{PREFIX}{title}", **{**defaults, **fields})
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def _gwp_scheme(self):
		"""The same GWP as a Promotional Scheme; returns its generated Pricing Rule."""
		if not frappe.db.has_column("Promotional Scheme", "promotion_type"):
			self.skipTest("promotions' Promotional Scheme fields are not installed")
		if frappe.db.exists("Promotional Scheme", SCHEME):
			frappe.delete_doc("Promotional Scheme", SCHEME, force=True, ignore_permissions=True)
		company = _resolve_company()
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": SCHEME,
				"company": company,
				"currency": frappe.get_cached_value("Company", company, "default_currency"),
				"apply_on": "Item Code",
				"selling": 1,
				"valid_from": nowdate(),
				"valid_upto": add_days(nowdate(), 30),
				"promotion_type": "GWP",
				"items": [{"item_code": ITEM_A, "uom": "Nos"}, {"item_code": ITEM_B, "uom": "Nos"}],
				"applicable_for": "Customer",
				"customer": [{"customer": CUSTOMER}],
				"product_discount_slabs": [
					{
						"rule_description": SCHEME,
						"min_qty": 2,
						"free_item": ITEM_A,
						"free_qty": 1,
						"free_item_uom": "Nos",
						"same_item": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Promotional Scheme", SCHEME, force=True, ignore_permissions=True)
		return frappe.db.get_value("Pricing Rule", {"promotional_scheme": SCHEME, "disable": 0}, "name")

	def _line(self, code, qty=1, price=None):
		price = PRICES[code] if price is None else price
		return {
			"item_code": code,
			"qty": qty,
			"rate": price,
			"uom": "Nos",
			"warehouse": self.ctx.warehouse,
			"conversion_factor": 1,
			"price_list_rate": price,
			"discount_percentage": 0,
			"discount_amount": 0,
		}

	def _cart(self, paid, free, rule, free_qty=1, customer=CUSTOMER):
		"""Paid lines (item codes, or (code, qty)) carrying ``rule``, as the cart stamps
		them, and a free row."""
		lines = []
		for entry in paid:
			code, qty = entry if isinstance(entry, tuple) else (entry, 1)
			line = self._line(code, qty)
			line["pricing_rules"] = rule
			lines.append(line)
		free_row = self._line(free, qty=free_qty, price=0)
		free_row.update({"is_free_item": 1, "pricing_rules": rule})
		payload = _cart_payload(self.ctx, [*lines, free_row])
		payload["customer"] = customer
		return payload

	def _submit(self, payload):
		paid = sum(
			flt(row["rate"]) * flt(row["qty"]) for row in payload["items"] if not row.get("is_free_item")
		)
		payload = dict(payload, payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": paid}])
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", result["name"])

	def _cart_offers(self, payload, selected):
		"""What the cart gets from the evaluator (it always sends its selected offers)."""
		return invoices._offer_evaluator()(
			json.dumps(payload), selected_offers=json.dumps(selected) if selected else None
		)

	@staticmethod
	def _free_rows(doc):
		return [(row.item_code, flt(row.qty), row.pricing_rules) for row in doc.items if cint(row.is_free_item)]

	def assertRefused(self, call):
		with self.assertRaises(frappe.ValidationError) as caught:
			call()
		self.assertIn(NOT_BACKED, str(caught.exception))

	# ---- the mechanism ------------------------------------------------------

	def test_engine_grants_mixed_gwp_only_with_selected_offer(self):
		"""Confirms D-R2-08's cause: without the rule selected no free row is granted."""
		rule = self._gwp_rule()
		payload = _cart_payload(self.ctx, [self._line(ITEM_A), self._line(ITEM_B)])
		payload["customer"] = CUSTOMER
		without = self._cart_offers(payload, None).get("free_items") or []
		with_rule = self._cart_offers(payload, [rule]).get("free_items") or []
		self.assertEqual([f for f in without if f.get("pricing_rules") == rule], [])
		self.assertEqual(
			[(f.get("item_code"), flt(f.get("qty"))) for f in with_rule if f.get("pricing_rules") == rule],
			[(ITEM_A, 1)],
		)

	# ---- sales --------------------------------------------------------------

	def test_mixed_gwp_sale_submits_with_its_free_row(self):
		rule = self._gwp_rule()
		doc = self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule))
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(self._free_rows(doc), [(ITEM_A, 1, rule)])

	def test_mixed_gwp_draft_saves(self):
		rule = self._gwp_rule()
		draft = update_invoice(json.dumps(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))
		self.addCleanup(frappe.delete_doc, "Sales Invoice", draft["name"], force=True, ignore_permissions=True)
		self.assertEqual(self._free_rows(frappe.get_doc("Sales Invoice", draft["name"])), [(ITEM_A, 1, rule)])

	def test_mixed_gwp_named_only_on_the_free_row_submits(self):
		"""The rule name on the gift alone is enough: the server verifies it, then evaluates."""
		rule = self._gwp_rule()
		payload = self._cart([ITEM_A, ITEM_B], ITEM_A, rule)
		for row in payload["items"]:
			if not row.get("is_free_item"):
				row["pricing_rules"] = ""
		self.assertEqual(self._free_rows(self._submit(payload)), [(ITEM_A, 1, rule)])

	def test_same_item_gwp_still_works(self):
		rule = self._gwp_rule()
		doc = self._submit(self._cart([(ITEM_B, 2)], ITEM_B, rule))
		self.assertEqual(self._free_rows(doc), [(ITEM_B, 1, rule)])

	def test_promotional_scheme_mixed_gwp_submits(self):
		rule = self._gwp_scheme()
		self.assertTrue(rule)
		doc = self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule))
		self.assertEqual(self._free_rows(doc), [(ITEM_A, 1, rule)])

	# ---- forged free rows ---------------------------------------------------

	def test_forged_same_item_free_row_refused(self):
		"""One paid ITEM_A does not reach the GWP's 2: its ITEM_A free row is forged."""
		rule = self._gwp_rule()
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A], ITEM_A, rule)))

	def test_excess_mixed_gwp_free_qty_refused(self):
		rule = self._gwp_rule()
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule, free_qty=2)))

	def test_rule_of_another_customer_not_trusted(self):
		rule = self._gwp_rule("OTHER", customer=OTHER_CUSTOMER)
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))

	def test_disabled_rule_not_trusted(self):
		rule = self._gwp_rule()
		frappe.db.set_value("Pricing Rule", rule, "disable", 1)
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))

	def test_expired_rule_not_trusted(self):
		rule = self._gwp_rule()
		frappe.db.set_value(
			"Pricing Rule", rule, {"valid_from": add_days(nowdate(), -10), "valid_upto": add_days(nowdate(), -1)}
		)
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))

	def test_rule_for_other_items_not_trusted(self):
		"""A GWP on items not in this cart backs nothing, whatever its name on the rows."""
		rule = self._gwp_rule(items=[{"item_code": ITEM_C}])
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))

	# ---- the cart as the POS builds it, plain and F&F ------------------------

	def _evaluated_cart(self, rule, customer=CUSTOMER):
		"""ITEM_A + ITEM_B priced by the cart's evaluator with ``rule`` selected, as the
		POS stamps the answer (rates, discounts, sources, rules, free rows)."""
		payload = _cart_payload(self.ctx, [self._line(ITEM_A), self._line(ITEM_B)])
		payload["customer"] = customer
		response = self._cart_offers(payload, [rule])
		for target, line in zip(payload["items"], response.get("items") or [], strict=False):
			price = flt(line.get("price_list_rate") or target["price_list_rate"])
			discount = flt(line.get("discount_amount"))
			qty = flt(target["qty"])
			target.update(
				{
					"price_list_rate": price,
					"discount_percentage": flt(line.get("discount_percentage")),
					"discount_amount": discount,
					"rate": (price * qty - discount) / qty,
					"pricing_rules": line.get("pricing_rules") or "",
					"posnext_discount_source": line.get("posnext_discount_source")
					or line.get("discount_source")
					or "",
				}
			)
		for free in response.get("free_items") or []:
			row = self._line(free.get("item_code"), qty=flt(free.get("qty")), price=0)
			row.update({"is_free_item": 1, "pricing_rules": free.get("pricing_rules") or ""})
			payload["items"].append(row)
		return payload

	def test_plain_customer_cart_submits(self):
		rule = self._gwp_rule()
		doc = self._submit(self._evaluated_cart(rule))
		self.assertEqual(self._free_rows(doc), [(ITEM_A, 1, rule)])

	def test_ff_customer_gift_allowed_submits(self):
		"""U-22 (ii): F&F on the GWP lines and the free row, gifts allowed with F&F."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN, allow_free_gift_with_ff=1)
		rule = self._gwp_rule()
		payload = self._evaluated_cart(rule)
		sources = [row.get("posnext_discount_source") for row in payload["items"] if not row.get("is_free_item")]
		self.assertEqual(sources, [FNF, FNF])
		doc = self._submit(payload)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(self._free_rows(doc), [(ITEM_A, 1, rule)])
		paid = [row for row in doc.items if not cint(row.is_free_item)]
		self.assertEqual([row.posnext_discount_source for row in paid], [FNF, FNF])
		self.assertEqual([flt(row.rate, 2) for row in paid], [21, 31.5])

	def test_ff_customer_gift_not_allowed_refused(self):
		"""Gifts not allowed with F&F: the F&F lines' GWP gift is backed by nothing."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN, allow_free_gift_with_ff=0)
		rule = self._gwp_rule()
		payload = self._evaluated_cart(rule)
		self.assertFalse([row for row in payload["items"] if row.get("is_free_item")])
		payload["items"].append(dict(self._line(ITEM_A, price=0), is_free_item=1, pricing_rules=rule))
		self.assertRefused(lambda: self._submit(payload))

	# ---- Ruling 148: a named rule counts only if it wins ERPNext's selection ---

	def _same_item_gwp(self, title, priority, free_qty):
		return self._gwp_rule(
			title, items=[{"item_code": ITEM_B}], free_item=ITEM_B, priority=str(priority), free_qty=free_qty
		)

	def test_lower_priority_gwp_alone_refused(self):
		"""Review p1a: the higher-priority GWP wins; the lower one's bigger gift is not due."""
		self._same_item_gwp("P1_HI", 5, 1)
		low = self._same_item_gwp("P1_LO", 1, 3)
		payload = self._cart([(ITEM_B, 2)], ITEM_B, low, free_qty=3)
		self.assertRefused(lambda: self._submit(payload))

	def test_lower_priority_gwp_stacked_refused(self):
		"""Review p1b: the winner's gift plus the loser's is refused."""
		high = self._same_item_gwp("P1_HI", 5, 1)
		low = self._same_item_gwp("P1_LO", 1, 3)
		payload = self._cart([(ITEM_B, 2)], ITEM_B, high)
		extra = dict(self._line(ITEM_B, qty=3, price=0), is_free_item=1, pricing_rules=low)
		payload["items"].append(extra)
		self.assertRefused(lambda: self._submit(payload))

	def test_winning_gwp_of_two_still_sells(self):
		high = self._same_item_gwp("P1_HI", 5, 1)
		self._same_item_gwp("P1_LO", 1, 3)
		self.assertEqual(self._free_rows(self._submit(self._cart([(ITEM_B, 2)], ITEM_B, high))), [(ITEM_B, 1, high)])

	def _price_rule_on_b(self):
		name = _make_rule(
			f"{PREFIX}P2_PRICE",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=10,
			priority="5",
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def test_gwp_excluded_by_price_rule_refused_on_top_of_it(self):
		"""Review p2a: a higher-priority 10% rule wins; its line cannot also earn the GWP."""
		price = self._price_rule_on_b()
		gwp = self._same_item_gwp("P2_GWP", 1, 1)
		payload = self._cart([(ITEM_B, 2)], ITEM_B, gwp)
		payload["items"][0].update(
			{"rate": 40.5, "discount_percentage": 10, "discount_amount": 9, "pricing_rules": f"{price},{gwp}"}
		)
		self.assertRefused(lambda: self._submit(payload))

	def test_gwp_excluded_by_price_rule_refused_at_full_price(self):
		"""Review p2b."""
		self._price_rule_on_b()
		gwp = self._same_item_gwp("P2_GWP", 1, 1)
		self.assertRefused(lambda: self._submit(self._cart([(ITEM_B, 2)], ITEM_B, gwp)))

	def _other_price_list(self):
		name = f"{PREFIX}PL"
		if not frappe.db.exists("Price List", name):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": name,
					"selling": 1,
					"currency": self.ctx.currency,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		for code, price in PRICES.items():
			if not frappe.db.exists("Item Price", {"item_code": code, "price_list": name}):
				frappe.get_doc(
					{"doctype": "Item Price", "item_code": code, "price_list": name, "price_list_rate": price}
				).insert(ignore_permissions=True)
		return name

	def test_rule_of_client_price_list_not_trusted(self):
		"""Review p4b: the price list is the POS Profile's, never the client's."""
		other = self._other_price_list()
		rule = self._gwp_rule("P4", for_price_list=other)
		payload = self._cart([ITEM_A, ITEM_B], ITEM_A, rule)
		payload["selling_price_list"] = other
		self.assertRefused(lambda: self._submit(payload))

	def test_redeemed_one_time_gwp_refused(self):
		rule = self._gwp_rule("P5", one_time_per_customer=1)
		first = self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule))
		self.assertEqual(self._free_rows(first), [(ITEM_A, 1, rule)])
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A, ITEM_B], ITEM_A, rule)))
		payload = self._cart([ITEM_A, ITEM_B], ITEM_A, rule)
		for row in payload["items"]:
			if not row.get("is_free_item"):
				row["pricing_rules"] = ""
		self.assertRefused(lambda: self._submit(payload))

	def _gift_pool(self, min_qty):
		"""A Gift Pool on ITEM_A's group: paid ITEM_A earns ITEM_C (in the pool)."""
		if not frappe.db.exists("DocType", "POS Gift Pool Item"):
			self.skipTest("Gift Pool is not installed")
		name = f"{PREFIX}GIFT_POOL"
		if frappe.db.exists("Promotional Scheme", name):
			frappe.delete_doc("Promotional Scheme", name, force=True, ignore_permissions=True)
		group = frappe.db.get_value("Item", ITEM_A, "item_group")
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": name,
				"company": _resolve_company(),
				"apply_on": "Item Group",
				"selling": 1,
				"promotion_type": "Gift Pool",
				"item_groups": [{"item_group": group}],
				"applicable_for": "Customer",
				"customer": [{"customer": CUSTOMER}],
				"product_discount_slabs": [{"min_qty": min_qty, "free_qty": 1}],
				"gift_pool_items": [{"item_group": group, "item_code": ITEM_C, "free_qty": 1}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Promotional Scheme", name, force=True, ignore_permissions=True)
		return frappe.db.get_value("Pricing Rule", {"promotional_scheme": name, "disable": 0}, "name")

	def test_gift_pool_below_min_qty_refused(self):
		"""Not POS-only, so ERPNext's lookup finds it on any sale: min_qty still holds
		(promotions' Gift Pool pass grants a selected rule whatever the quantity)."""
		rule = self._gift_pool(min_qty=2)
		frappe.db.set_value("Pricing Rule", rule, "pos_only", 0)
		frappe.clear_document_cache("Pricing Rule", rule)
		self.assertRefused(lambda: self._submit(self._cart([ITEM_A], ITEM_C, rule)))

	def test_gift_pool_at_min_qty_sells(self):
		rule = self._gift_pool(min_qty=2)
		doc = self._submit(self._cart([(ITEM_A, 2)], ITEM_C, rule))
		self.assertEqual(self._free_rows(doc), [(ITEM_C, 1, rule)])
