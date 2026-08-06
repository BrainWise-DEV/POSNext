# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""Integration tests for POS Next's promotion engine.

These tests drive the full apply_offers → update_invoice → submit_invoice
pipeline through every Pricing Rule shape POS Next claims to support, and
assert the saved invoice ends up at the expected grand_total / paid_amount /
status.

The suite locks in two related fixes:

1. Partial-paid regression — `pos_next/api/invoices.py:_process_invoice` now
   clears `item.pricing_rules` before save when `ignore_pricing_rule=1`, to
   avoid ERPNext's `get_pricing_rule_for_item` removal branch silently
   zeroing `discount_percentage` / `discount_amount` / `rate` on the second
   save (the "submit" step). See `test_partial_paid_regression`.

2. Transaction-level discount harvesting — `_evaluate_transaction_offers`
   now snapshots `additional_discount_percentage` / `discount_amount` /
   `apply_discount_on` after running ERPNext's transaction engine and
   surfaces them in the `apply_offers` response. See
   `test_transaction_level_discount`.

All test data is prefixed with `_PNXT_TEST_` so it can be cleaned up safely.
Tests do not assume any pre-existing items, customers, or pricing rules —
they construct their own setup against whatever Company / Warehouse the
running site has configured.
"""

from types import SimpleNamespace
import unittest

import frappe
from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

import pos_next  # noqa: F401 — ensure app hooks load.
from pos_next.api.invoices import apply_offers, submit_invoice, update_invoice
from pos_next.promotions import engine
from pos_next.promotions.scope import get_scope_keys, item_matches_rule_scope

ITEM_A = "_PNXT_TEST_ITEM_A"  # Standard Selling: 50
ITEM_B = "_PNXT_TEST_ITEM_B"  # Standard Selling: 80
ITEM_C = "_PNXT_TEST_ITEM_C"  # Standard Selling: 20

TEST_BRAND = "_PNXT_TEST_BRAND"  # stamped onto ITEM_C only
TEST_PARENT_GROUP = "_PNXT_TEST_PARENT_GROUP"  # is_group=1
TEST_CHILD_GROUP = "_PNXT_TEST_CHILD_GROUP"  # leaf under TEST_PARENT_GROUP

# Real-site matrix QA item (brainwise.dev / manual POS testing)
MATRIX_ITEM_14214 = "14214"
MATRIX_COMPANION_14214 = "4124124"
MATRIX_TEST_BRAND_14214 = "MatrixTest"

ITEM_PRICES = {ITEM_A: 50.0, ITEM_B: 80.0, ITEM_C: 20.0}

CUSTOMER = "_PNXT_TEST_CUSTOMER"


def _resolve_company():
	"""Pick the test Company. Prefer ERPNext test fixture, else the default."""
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"
	default = frappe.defaults.get_global_default("company")
	if default:
		return default
	return frappe.db.get_value("Company", {"name": ["!=", ""]}, "name")


def _resolve_warehouse(company):
	"""Pick a non-group, non-disabled warehouse for the company."""
	# Prefer ERPNext's test warehouse if it matches the company
	if company == "_Test Company" and frappe.db.exists("Warehouse", "_Test Warehouse - _TC"):
		return "_Test Warehouse - _TC"
	wh = frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
		order_by="creation asc",
	)
	if not wh:
		frappe.throw(f"No warehouse for company {company}.")
	return wh


def _resolve_price_list(company):
	# Standard Selling exists on every Frappe/ERPNext site
	if frappe.db.exists("Price List", "Standard Selling"):
		return "Standard Selling"
	return frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")


def _resolve_cost_center(company):
	return frappe.db.get_value(
		"Cost Center",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
		order_by="creation asc",
	)


def _resolve_mode_of_payment(company):
	"""Find a Mode of Payment with an account configured for `company`.

	On a fresh CI test_site, no Mode of Payment Account rows exist by default,
	so we wire one up for Cash pointing at the company's default cash account.
	"""
	# Already-configured mode for this company wins
	mop_with_account = frappe.db.sql(
		"""
		SELECT DISTINCT parent FROM `tabMode of Payment Account`
		WHERE company = %s LIMIT 1
		""",
		(company,),
	)
	if mop_with_account:
		return mop_with_account[0][0]

	# Wire up Cash → company's default cash account
	if not frappe.db.exists("Mode of Payment", "Cash"):
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": "Cash",
				"type": "Cash",
				"enabled": 1,
			}
		).insert(ignore_permissions=True)

	default_cash_account = frappe.get_cached_value("Company", company, "default_cash_account")
	if not default_cash_account:
		# Find any cash-type account for the company
		default_cash_account = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Cash", "is_group": 0},
			"name",
			order_by="creation asc",
		)
	if not default_cash_account:
		# Last resort: any non-group leaf account on the company
		default_cash_account = frappe.db.get_value(
			"Account",
			{"company": company, "is_group": 0},
			"name",
			order_by="creation asc",
		)

	mop_doc = frappe.get_doc("Mode of Payment", "Cash")
	mop_doc.append(
		"accounts",
		{"company": company, "default_account": default_cash_account},
	)
	mop_doc.save(ignore_permissions=True)
	return "Cash"


def _resolve_item_group():
	"""Pick a non-group Item Group. Same root-vs-leaf gotcha as Customer Group."""
	for candidate in ("_Test Item Group", "Products"):
		if frappe.db.exists("Item Group", candidate):
			ig = frappe.get_cached_doc("Item Group", candidate)
			if not ig.is_group:
				return candidate
	leaf = frappe.db.get_value(
		"Item Group",
		{"is_group": 0},
		"name",
		order_by="creation asc",
	)
	if leaf:
		return leaf
	ig = frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "_PNXT_TEST_ITEM_GROUP",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return ig.name


def _ensure_test_brand():
	"""Create a Brand and stamp it on ITEM_C so Brand-scoped rules have a target.

	Only ITEM_C carries it, which gives every Brand test a built-in negative case
	(ITEM_A / ITEM_B must stay untouched).
	"""
	if not frappe.db.exists("Brand", TEST_BRAND):
		frappe.get_doc({"doctype": "Brand", "brand": TEST_BRAND}).insert(ignore_permissions=True)

	if frappe.db.get_value("Item", ITEM_C, "brand") != TEST_BRAND:
		frappe.db.set_value("Item", ITEM_C, "brand", TEST_BRAND)
		frappe.clear_document_cache("Item", ITEM_C)

	return TEST_BRAND


def _ensure_group_tree():
	"""Create a parent Item Group with one leaf child.

	Item groups match by lineage, so a rule on the parent must also cover items
	sitting in the child. Nothing is filed under the child — the tree itself is
	what the scope helpers are asserted against.
	"""
	if not frappe.db.exists("Item Group", TEST_PARENT_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": TEST_PARENT_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 1,
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Item Group", TEST_CHILD_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": TEST_CHILD_GROUP,
				"parent_item_group": TEST_PARENT_GROUP,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

	return TEST_PARENT_GROUP, TEST_CHILD_GROUP


def _ensure_test_items(company, warehouse, price_list):
	"""Create the three test items with prices and stock if they don't exist."""
	item_group = _resolve_item_group()
	for item_code, price in ITEM_PRICES.items():
		if not frappe.db.exists("Item", item_code):
			# Insert via frappe.get_doc directly so we can set
			# flags.from_integration=True, which short-circuits any
			# after_insert hooks from optional ecommerce apps (e.g.
			# ecommerce_integrations' Shopify uploader, which has a
			# pre-existing bug calling `doc.hasattr(...)`).
			item = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_code.replace("_PNXT_TEST_", ""),
					"item_group": item_group,
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			)
			item.flags.from_integration = True
			item.insert(ignore_permissions=True)

		# Ensure Item Price exists
		ip_filters = {"item_code": item_code, "price_list": price_list}
		if not frappe.db.exists("Item Price", ip_filters):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item_code,
					"price_list": price_list,
					"price_list_rate": price,
				}
			).insert(ignore_permissions=True)

	# Top up stock at the POS warehouse so scenarios don't run out
	for item_code in ITEM_PRICES:
		current = (
			frappe.db.get_value(
				"Bin",
				{"item_code": item_code, "warehouse": warehouse},
				"actual_qty",
			)
			or 0
		)
		if current < 50:
			try:
				make_stock_entry(
					item_code=item_code,
					target=warehouse,
					qty=100,
					rate=ITEM_PRICES[item_code] / 2,
					company=company,
				)
			except Exception:
				# Stock entry failure shouldn't abort the test setup; the
				# individual test will surface the real cause.
				frappe.db.rollback()


def _resolve_customer_group():
	"""Pick a non-group Customer Group. 'All Customer Groups' is a group node
	on stock Frappe/ERPNext installs and Customer.validate rejects it.
	"""
	# Prefer ERPNext's standard test fixture when present
	if frappe.db.exists("Customer Group", "_Test Customer Group"):
		return "_Test Customer Group"
	leaf = frappe.db.get_value(
		"Customer Group",
		{"is_group": 0},
		"name",
		order_by="creation asc",
	)
	if leaf:
		return leaf
	# Last resort: create a leaf under the root
	cg = frappe.get_doc(
		{
			"doctype": "Customer Group",
			"customer_group_name": "_PNXT_TEST_CG",
			"parent_customer_group": "All Customer Groups",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return cg.name


def _resolve_territory():
	"""Pick a non-group Territory. Same gotcha as Customer Group."""
	if frappe.db.exists("Territory", "_Test Territory"):
		return "_Test Territory"
	leaf = frappe.db.get_value(
		"Territory",
		{"is_group": 0},
		"name",
		order_by="creation asc",
	)
	if leaf:
		return leaf
	t = frappe.get_doc(
		{
			"doctype": "Territory",
			"territory_name": "_PNXT_TEST_TERRITORY",
			"parent_territory": "All Territories",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return t.name


def _ensure_customer():
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": CUSTOMER,
				"customer_group": _resolve_customer_group(),
				"territory": _resolve_territory(),
				"customer_type": "Individual",
			}
		).insert(ignore_permissions=True)


def _ensure_pos_profile(company, warehouse, price_list, mode_of_payment):
	"""Create a deterministic POS Profile for promotion tests.

	Importantly, `disable_rounded_total=1` so SAR's whole-number rounding
	doesn't introduce a half-SAR rounding_adjustment that would inflate
	outstanding_amount and turn 100%-paid invoices into "Partly Paid"
	(unrelated to the promotion logic under test).
	"""
	profile_name = f"_PNXT_TEST_POS_PROFILE_{company}"
	if frappe.db.exists("POS Profile", profile_name):
		# Re-patch fields each run so prior mutations don't leak across tests.
		profile = frappe.get_doc("POS Profile", profile_name)
		profile.warehouse = warehouse
		profile.selling_price_list = price_list
		profile.ignore_pricing_rule = 0
		profile.disable_rounded_total = 1
		profile.payments = []
		profile.append(
			"payments",
			{"mode_of_payment": mode_of_payment, "default": 1, "amount": 0},
		)
		profile.save(ignore_permissions=True)
		return profile.name

	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": profile_name,
			"company": company,
			"warehouse": warehouse,
			"selling_price_list": price_list,
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"customer": CUSTOMER,
			"write_off_account": frappe.get_cached_value("Company", company, "write_off_account"),
			"write_off_cost_center": _resolve_cost_center(company),
			"ignore_pricing_rule": 0,
			"disable_rounded_total": 1,
			"disabled": 0,
		}
	)
	profile.append(
		"payments",
		{"mode_of_payment": mode_of_payment, "default": 1, "amount": 0},
	)
	profile.insert(ignore_permissions=True)
	return profile.name


def _ctx():
	"""Resolve everything an integration test needs in one shot."""
	company = _resolve_company()
	warehouse = _resolve_warehouse(company)
	price_list = _resolve_price_list(company)
	mode_of_payment = _resolve_mode_of_payment(company)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	_ensure_customer()
	_ensure_test_items(company, warehouse, price_list)
	pos_profile = _ensure_pos_profile(company, warehouse, price_list, mode_of_payment)
	return SimpleNamespace(
		company=company,
		warehouse=warehouse,
		price_list=price_list,
		mode_of_payment=mode_of_payment,
		currency=currency,
		customer=CUSTOMER,
		pos_profile=pos_profile,
	)


def _make_rule(title, **fields):
	"""Idempotently create a Pricing Rule. Deletes any prior rule with same title."""
	existing = frappe.db.get_value("Pricing Rule", {"title": title}, "name")
	if existing:
		frappe.delete_doc("Pricing Rule", existing, force=True, ignore_permissions=True)

	defaults = {
		"doctype": "Pricing Rule",
		"title": title,
		"selling": 1,
		"buying": 0,
		"company": _resolve_company(),
		"currency": frappe.get_cached_value("Company", _resolve_company(), "default_currency"),
		"valid_from": nowdate(),
		"priority": "1",
		"disable": 0,
		"min_qty": 1,
	}
	defaults.update(fields)
	doc = frappe.get_doc(defaults).insert(ignore_permissions=True)
	return doc.name


def _cart_payload(ctx, items_in):
	"""Build a Sales Invoice payload mirroring what the frontend sends."""
	return {
		"doctype": "Sales Invoice",
		"is_pos": 1,
		"pos_profile": ctx.pos_profile,
		"company": ctx.company,
		"currency": ctx.currency,
		"customer": ctx.customer,
		"selling_price_list": ctx.price_list,
		"posting_date": nowdate(),
		"items": items_in,
		"payments": [],
	}


def _line(ctx, item_code, qty=1, price_list_rate=None):
	if price_list_rate is None:
		price_list_rate = ITEM_PRICES[item_code]
	return {
		"item_code": item_code,
		"qty": qty,
		"rate": price_list_rate,
		"uom": "Nos",
		"warehouse": ctx.warehouse,
		"conversion_factor": 1,
		"price_list_rate": price_list_rate,
		"discount_percentage": 0,
		"discount_amount": 0,
	}


def _apply_offers_and_stamp(payload, selected_offers):
	"""Run apply_offers and stamp the response back onto the cart payload, mirroring
	the frontend's applyDiscountsFromServer + recalculateItem + formatItemsForSubmission
	+ applyHeaderDiscountFromServer chain.
	"""
	import json

	resp = apply_offers(
		invoice_data=json.dumps(payload),
		selected_offers=json.dumps(selected_offers) if selected_offers else None,
	)
	response_items = resp.get("items") or []

	for idx, ri in enumerate(response_items):
		if idx >= len(payload["items"]):
			break
		target = payload["items"][idx]
		price_list_rate = flt(ri.get("price_list_rate") or target.get("price_list_rate"))
		discount_percentage = flt(ri.get("discount_percentage") or 0)
		per_line_discount = flt(ri.get("discount_amount") or 0)
		qty = flt(target.get("qty") or 1)
		# Mirror useInvoice.js#computeBackendRate (tax-exclusive): rate = amount/qty.
		base_amount = price_list_rate * qty
		net_amount = base_amount - per_line_discount
		rate_to_send = net_amount / qty if qty else price_list_rate

		target.update(
			{
				"rate": rate_to_send,
				"price_list_rate": price_list_rate,
				"discount_percentage": discount_percentage,
				"discount_amount": per_line_discount,
				"pricing_rules": ri.get("pricing_rules") or "",
				"discount_source": ri.get("discount_source") or "",
				"free_qty": flt(ri.get("free_qty") or 0),
				"gwp_free_qty": flt(ri.get("gwp_free_qty") or 0),
			}
		)

		fq = flt(ri.get("free_qty") or 0)
		if ri.get("discount_source") == "free_item" and fq > 0:
			total_qty = flt(target.get("qty") or 1)
			target["qty"] = max(0, total_qty - fq)
			payload["items"].append(
				{
					"item_code": target.get("item_code"),
					"qty": fq,
					"rate": 0,
					"price_list_rate": 0,
					"uom": target.get("uom") or target.get("stock_uom") or "Nos",
					"warehouse": target.get("warehouse"),
					"conversion_factor": target.get("conversion_factor") or 1,
					"discount_percentage": 0,
					"discount_amount": 0,
					"pricing_rules": ri.get("pricing_rules") or "",
					"is_free_item": 1,
				}
			)

	for fi in resp.get("free_items") or []:
		payload["items"].append(
			{
				"item_code": fi.get("item_code"),
				"qty": flt(fi.get("qty") or 0),
				"rate": 0,
				"price_list_rate": 0,
				"uom": fi.get("uom") or fi.get("stock_uom") or "Nos",
				"warehouse": payload["items"][0].get("warehouse"),
				"conversion_factor": fi.get("conversion_factor") or 1,
				"discount_percentage": 0,
				"discount_amount": 0,
				"pricing_rules": fi.get("pricing_rules") or "",
				"is_free_item": 1,
			}
		)

	header_addl_pct = flt(resp.get("additional_discount_percentage") or 0)
	header_discount_amt = flt(resp.get("discount_amount") or 0)
	if header_addl_pct or header_discount_amt:
		if header_discount_amt:
			payload["discount_amount"] = header_discount_amt
		if header_addl_pct:
			payload["additional_discount_percentage"] = header_addl_pct
		apply_on = resp.get("apply_discount_on")
		if apply_on:
			payload["apply_discount_on"] = apply_on

	return resp


def _make_pos_coupon(code, **fields):
	"""Idempotently create a POS Coupon for exclusion tests."""
	company = _resolve_company()
	coupon_name = f"_PNXT_TEST_COUPON_{code}"
	if frappe.db.exists("POS Coupon", coupon_name):
		frappe.delete_doc("POS Coupon", coupon_name, force=True, ignore_permissions=True)

	defaults = {
		"doctype": "POS Coupon",
		"coupon_name": coupon_name,
		"coupon_type": "Promotional",
		"coupon_code": code,
		"discount_type": "Percentage",
		"discount_percentage": 10,
		"company": company,
		"apply_on": "Net Total",
		"apply_scope": "All Eligible Items",
		"exclude_already_discounted_items": 1,
	}
	defaults.update(fields)
	doc = frappe.get_doc(defaults)
	doc.insert(ignore_permissions=True)
	return doc


def _submit_invoice(ctx, payload, paid_amount):
	"""Push the payload through update_invoice → submit_invoice and return the final doc."""
	import json

	payload["payments"] = [{"mode_of_payment": ctx.mode_of_payment, "amount": flt(paid_amount)}]

	draft = update_invoice(json.dumps(payload))
	inv_name = draft["name"]

	submit_invoice(
		invoice=json.dumps(draft, default=str),
		data=json.dumps({"change_amount": 0, "write_off_amount": 0}),
	)

	return frappe.get_doc("Sales Invoice", inv_name)


class TestPromotions(FrappeTestCase):
	"""Validate every supported promotion shape through the full submit pipeline."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Resolve context once; per-test calls re-resolve so missing fixtures are
		# surfaced where they're actually consumed.
		cls.ctx = _ctx()

	def tearDown(self):
		"""Disable any test pricing rule created during this test method.

		We disable rather than delete so we don't churn Pricing Rule history
		(disabled rules are skipped by the engine, which is what we want).
		"""
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule",
			filters={"title": ["like", "_PNXT_TEST_%"]},
			pluck="name",
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	# -------------------------------------------------------------------
	# Main offer types (the 7 from the matrix)
	# -------------------------------------------------------------------

	def test_discount_percentage(self):
		"""15% off a single item line — most common cart discount."""
		rule = _make_rule(
			"_PNXT_TEST_DiscPct",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=42.5)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 42.5, places=2)
		self.assertAlmostEqual(flt(final.outstanding_amount), 0, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 42.5, places=2)
		self.assertAlmostEqual(flt(final.items[0].discount_percentage), 15, places=2)
		self.assertAlmostEqual(flt(final.items[0].discount_amount), 7.5, places=2)

	def test_discount_amount(self):
		"""Fixed-amount discount per line (10 SAR off a 50 SAR item)."""
		rule = _make_rule(
			"_PNXT_TEST_DiscAmt",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Amount",
			price_or_product_discount="Price",
			discount_amount=10,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=40)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 40, places=2)
		self.assertAlmostEqual(flt(final.outstanding_amount), 0, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 40, places=2)
		self.assertAlmostEqual(flt(final.items[0].discount_amount), 10, places=2)

	def test_rate_override(self):
		"""Rate-type rule overrides the price (item sold at 30 instead of 50)."""
		rule = _make_rule(
			"_PNXT_TEST_RateOverride",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Rate",
			price_or_product_discount="Price",
			rate=30,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=30)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 30, places=2)
		self.assertAlmostEqual(flt(final.outstanding_amount), 0, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 30, places=2)

	def test_free_same_item(self):
		"""Buy 2 get 1 free where free = bought item (bundled on the paid line)."""
		rule = _make_rule(
			"_PNXT_TEST_FreeSame",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=2,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=2)])
		resp = _apply_offers_and_stamp(payload, [rule])
		self.assertEqual(resp.get("free_items"), [])
		self.assertEqual(flt(resp["items"][0].get("free_qty")), 1)

		final = _submit_invoice(self.ctx, payload, paid_amount=100)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 100, places=2)

		paid_lines = [it for it in final.items if not it.is_free_item]
		free_lines = [it for it in final.items if it.is_free_item]
		self.assertEqual(len(paid_lines), 1)
		self.assertAlmostEqual(flt(paid_lines[0].qty), 1, places=2)
		self.assertEqual(len(free_lines), 1)
		self.assertEqual(free_lines[0].item_code, ITEM_A)
		self.assertAlmostEqual(flt(free_lines[0].qty), 1, places=2)
		self.assertAlmostEqual(flt(free_lines[0].rate), 0, places=2)

	def test_free_different_item(self):
		"""Buy ITEM_B get a free ITEM_C."""
		rule = _make_rule(
			"_PNXT_TEST_FreeDiff",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_C,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_B, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=80)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 80, places=2)

		free_lines = [it for it in final.items if it.is_free_item]
		self.assertEqual(len(free_lines), 1)
		self.assertEqual(free_lines[0].item_code, ITEM_C)

	def test_gwp_many_items_max_basis(self):
		"""Buy 4 across two items; 2 free on cheapest lines when Max basis."""
		rule = _make_rule(
			"_PNXT_TEST_GWP_ManyMax",
			apply_on="Item Code",
			mixed_conditions=1,
			items=[{"item_code": ITEM_A}, {"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=1,
			min_qty=4,
			max_qty=4,
			free_qty=2,
			gwp_paid_qty_basis="Max Price",
			promotion_type="GWP",
		)
		payload = _cart_payload(
			self.ctx,
			[
				_line(self.ctx, ITEM_A, qty=2),
				_line(self.ctx, ITEM_B, qty=2),
			],
		)
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=160)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 160, places=2)

		by_code = {it.item_code: it for it in final.items if not it.is_free_item}
		line_a = by_code[ITEM_A]
		self.assertAlmostEqual(
			flt(line_a.discount_amount) * flt(line_a.qty), 100, places=2
		)
		self.assertAlmostEqual(flt(by_code[ITEM_B].discount_amount), 0, places=2)
		self.assertEqual(len([it for it in final.items if it.is_free_item]), 0)

	def test_transaction_level_discount(self):
		"""10% off entire cart when total ≥ 100; cart of 130 → grand_total 117."""
		rule = _make_rule(
			"_PNXT_TEST_TxnLevel",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=100,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		resp = _apply_offers_and_stamp(payload, [rule])

		# Regression assertion #1: response includes the harvested header discount
		self.assertAlmostEqual(flt(resp.get("additional_discount_percentage")), 10, places=2)
		self.assertAlmostEqual(flt(resp.get("discount_amount")), 13, places=2)
		self.assertEqual(resp.get("apply_discount_on"), "Grand Total")
		self.assertIn(rule, resp.get("applied_pricing_rules") or [])

		final = _submit_invoice(self.ctx, payload, paid_amount=117)

		# Regression assertion #2: saved invoice carries the header discount
		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 117, places=2)
		self.assertAlmostEqual(flt(final.discount_amount), 13, places=2)
		self.assertAlmostEqual(flt(final.outstanding_amount), 0, places=2)

	def test_mixed_multi_item(self):
		"""Offer on one line, other line untouched."""
		rule = _make_rule(
			"_PNXT_TEST_Mixed",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=2)],
		)
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=42.5 + 160)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 202.5, places=2)

		by_code = {it.item_code: it for it in final.items}
		self.assertAlmostEqual(flt(by_code[ITEM_A].rate), 42.5, places=2)
		self.assertAlmostEqual(flt(by_code[ITEM_B].rate), 80, places=2)
		self.assertAlmostEqual(flt(by_code[ITEM_B].discount_amount), 0, places=2)

	# -------------------------------------------------------------------
	# Edge cases
	# -------------------------------------------------------------------

	def test_full_100_percent_discount(self):
		"""100% off — invoice should still post with grand_total = 0."""
		rule = _make_rule(
			"_PNXT_TEST_Full100",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=100,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=0)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 0, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 0, places=2)

	def test_discount_equal_to_price(self):
		"""Discount Amount = price — final rate goes to 0 cleanly."""
		rule = _make_rule(
			"_PNXT_TEST_DiscEqPrice",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Amount",
			price_or_product_discount="Price",
			discount_amount=50,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=0)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 0, places=2)

	def test_multi_qty_percentage(self):
		"""Discount Percentage with qty > 1: total discount must scale."""
		rule = _make_rule(
			"_PNXT_TEST_MultiQty",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=3)])
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=127.5)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 127.5, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 42.5, places=2)
		self.assertAlmostEqual(flt(final.items[0].qty), 3, places=2)

	def test_stacked_line_and_transaction(self):
		"""Per-line discount + cart-wide discount stack correctly."""
		line_rule = _make_rule(
			"_PNXT_TEST_StackedLine",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		txn_rule = _make_rule(
			"_PNXT_TEST_StackedTxn",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=100,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		_apply_offers_and_stamp(payload, [line_rule, txn_rule])
		# 50 * 0.85 + 80 = 122.5 ; minus 10% on 122.5 = 12.25 ; final = 110.25
		final = _submit_invoice(self.ctx, payload, paid_amount=110.25)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 110.25, places=2)
		self.assertAlmostEqual(flt(final.discount_amount), 12.25, places=2)

	def test_plain_invoice_no_offer(self):
		"""Sanity: plain invoice with no offer should still submit cleanly.

		Confirms that clearing item.pricing_rules (the partial-paid fix) doesn't
		affect the non-offer path.
		"""
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		# Don't call apply_offers — skip the offer engine entirely
		final = _submit_invoice(self.ctx, payload, paid_amount=50)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 50, places=2)
		self.assertAlmostEqual(flt(final.outstanding_amount), 0, places=2)

	# -------------------------------------------------------------------
	# Explicit regression canaries
	# -------------------------------------------------------------------

	def test_partial_paid_regression(self):
		"""Canary for the ERPNext `remove_pricing_rule_for_item` interaction.

		With `ignore_pricing_rule=1` set on the doc (as POS Next always does)
		AND `item.pricing_rules` non-empty AND the doc already exists in DB,
		ERPNext's `get_pricing_rule_for_item` previously took a branch that
		zeroed `discount_percentage` / `discount_amount` / `rate` on the next
		save — silently turning paid invoices into Partly Paid ones.

		This test drives the full apply_offers → update_invoice →
		submit_invoice flow (two saves) and asserts the discount survives.
		"""
		rule = _make_rule(
			"_PNXT_TEST_PartialPaidCanary",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		_apply_offers_and_stamp(payload, [rule])
		# Cashier pays only the discounted amount; this is exactly the
		# pattern that produced the original "Partly Paid" bug report.
		final = _submit_invoice(self.ctx, payload, paid_amount=42.5)

		self.assertEqual(
			final.status,
			"Paid",
			msg=(
				"Invoice fell back to Partly Paid — the ERPNext removal branch "
				"likely re-fired and zeroed discount_percentage on submit."
			),
		)
		self.assertAlmostEqual(flt(final.grand_total), 42.5, places=2)
		self.assertAlmostEqual(flt(final.items[0].discount_percentage), 15, places=2)
		self.assertAlmostEqual(flt(final.items[0].discount_amount), 7.5, places=2)
		self.assertAlmostEqual(flt(final.items[0].rate), 42.5, places=2)
		# POS Next clears item.pricing_rules pre-save to avoid the ERPNext
		# removal branch; the rule is still effectively applied via the
		# discount fields.
		self.assertFalse(final.items[0].pricing_rules)

	def test_transaction_harvest_response(self):
		"""Canary for the transaction-level harvest fix.

		`_evaluate_transaction_offers` must surface
		`additional_discount_percentage` / `discount_amount` / `apply_discount_on`
		from the post-engine doc into the `apply_offers` response.
		"""
		rule = _make_rule(
			"_PNXT_TEST_TxnHarvest",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=100,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)

		self.assertIn(rule, resp.get("applied_pricing_rules") or [])
		self.assertAlmostEqual(flt(resp.get("additional_discount_percentage")), 10, places=2)
		self.assertAlmostEqual(flt(resp.get("discount_amount")), 13, places=2)
		self.assertEqual(resp.get("apply_discount_on"), "Grand Total")

	# -------------------------------------------------------------------
	# Negative tests — confirm offers DON'T apply when they shouldn't
	# -------------------------------------------------------------------

	def test_disabled_rule_not_applied(self):
		"""Disabled rules must not affect cart pricing even when selected."""
		rule = _make_rule(
			"_PNXT_TEST_NegDisabled",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
			disable=1,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)

		# The disabled rule should never appear in applied_pricing_rules
		self.assertNotIn(rule, resp.get("applied_pricing_rules") or [])
		# And the response items should have no discount applied
		self.assertEqual(flt(resp["items"][0].get("discount_percentage") or 0), 0)

	def test_expired_rule_not_applied(self):
		"""Rules with valid_upto in the past must not apply."""
		yesterday = add_days(nowdate(), -1)
		two_days_ago = add_days(nowdate(), -2)
		rule = _make_rule(
			"_PNXT_TEST_NegExpired",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
			valid_from=two_days_ago,
			valid_upto=yesterday,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)

		self.assertNotIn(rule, resp.get("applied_pricing_rules") or [])
		self.assertEqual(flt(resp["items"][0].get("discount_percentage") or 0), 0)

	def test_wrong_item_scope(self):
		"""Rule scoped to ITEM_B must not affect a cart with only ITEM_A."""
		rule = _make_rule(
			"_PNXT_TEST_NegWrongItem",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)

		self.assertNotIn(rule, resp.get("applied_pricing_rules") or [])
		self.assertEqual(flt(resp["items"][0].get("discount_percentage") or 0), 0)

	def test_txn_rule_below_min_amt_not_applied(self):
		"""Transaction rule with min_amt=100 must not fire on a cart of 50."""
		rule = _make_rule(
			"_PNXT_TEST_NegTxnBelowMin",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=100,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])  # 50 < 100
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)

		self.assertNotIn(rule, resp.get("applied_pricing_rules") or [])
		self.assertEqual(flt(resp.get("additional_discount_percentage") or 0), 0)
		self.assertEqual(flt(resp.get("discount_amount") or 0), 0)

	# -------------------------------------------------------------------
	# Transaction-scoped rules must key off the *discounted* subtotal
	# -------------------------------------------------------------------

	def test_txn_rule_min_amt_uses_discounted_subtotal(self):
		"""A cart pushed below min_amt by item discounts must not fire the rule.

		ITEM_A(50) + ITEM_B(80) grosses 130, but a 50% item rule on ITEM_A drops
		the real subtotal to 105. A min_amt=120 transaction rule therefore must
		not fire — this is what ERPNext's desk flow does, since it gates on the
		post-discount `doc.total`.
		"""
		item_rule = _make_rule(
			"_PNXT_TEST_TxnBaseItemDisc",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
		)
		txn_rule = _make_rule(
			"_PNXT_TEST_TxnBaseAboveGross",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=120,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, txn_rule]),
		)

		self.assertIn(item_rule, resp.get("applied_pricing_rules") or [])
		self.assertNotIn(
			txn_rule,
			resp.get("applied_pricing_rules") or [],
			msg=(
				"Transaction rule fired on the gross 130 instead of the discounted "
				"105 — pricing_items was not synced with item-level discounts."
			),
		)
		self.assertEqual(flt(resp.get("discount_amount") or 0), 0)

	def test_txn_rule_percentage_uses_discounted_subtotal(self):
		"""When the rule legitimately fires, its base is the discounted subtotal.

		Same cart as above (gross 130, discounted 105) with min_amt=100, so the
		rule qualifies. 10% must come off 105 (= 10.5), not off 130 (= 13).
		"""
		item_rule = _make_rule(
			"_PNXT_TEST_TxnPctItemDisc",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
		)
		txn_rule = _make_rule(
			"_PNXT_TEST_TxnPctBase",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=100,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, txn_rule]),
		)

		self.assertIn(txn_rule, resp.get("applied_pricing_rules") or [])
		self.assertAlmostEqual(
			flt(resp.get("discount_amount")),
			10.5,
			places=2,
			msg="Transaction discount was sized off the gross total, not the discounted subtotal.",
		)

	def test_txn_rule_base_includes_min_max_discounts(self):
		"""Min/Max discounts must land in the base before transaction rules run.

		The Min rule discounts the cheapest line (ITEM_A 50 -> 25), taking the
		cart from 130 to 105. A min_amt=120 transaction rule must therefore not
		fire. This only holds if the Min/Max pass runs *before* the
		transaction-scoped engine.
		"""
		min_rule = _make_rule(
			"_PNXT_TEST_TxnBaseMinRule",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}, {"item_code": ITEM_B}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=50,
			apply_discount_on_price="Min",
		)
		txn_rule = _make_rule(
			"_PNXT_TEST_TxnBaseAfterMinMax",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_amt=120,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		import json

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([min_rule, txn_rule]),
		)

		# The Min rule discounted only the cheapest line.
		by_code = {it.get("item_code"): it for it in resp["items"]}
		self.assertAlmostEqual(flt(by_code[ITEM_A].get("discount_percentage")), 50, places=2)
		self.assertEqual(flt(by_code[ITEM_B].get("discount_percentage") or 0), 0)

		self.assertNotIn(
			txn_rule,
			resp.get("applied_pricing_rules") or [],
			msg=(
				"Transaction rule fired on 130 — the Min/Max pass still runs after "
				"the transaction engine, so its discount is missing from the base."
			),
		)
		self.assertEqual(flt(resp.get("discount_amount") or 0), 0)

	# -------------------------------------------------------------------
	# Transaction-scoped Price rules must honour the cashier's selection
	# -------------------------------------------------------------------

	def test_txn_price_rule_not_selected_yields_no_header_discount(self):
		"""An unselected transaction Price rule must not discount the header.

		ERPNext's apply_pricing_rule_on_transaction runs its own SQL over every
		enabled transaction rule and never consults `selected_offers`. Free item
		rows coming back from it are filtered against the selection, so without
		the same filter on the header the two halves of one scheme disagree —
		and a rule the UI never offered can still discount the sale.
		"""
		import json

		txn_rule = _make_rule(
			"_PNXT_TEST_TxnUnselectedPrice",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=25,
			apply_discount_on="Grand Total",
		)
		other_rule = _make_rule(
			"_PNXT_TEST_TxnUnselectedOther",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			# Deliberately omits txn_rule.
			selected_offers=json.dumps([other_rule]),
		)

		self.assertNotIn(txn_rule, resp.get("applied_pricing_rules") or [])
		self.assertEqual(
			flt(resp.get("discount_amount") or 0),
			0,
			msg=(
				"An unselected transaction Price rule still pushed its discount onto "
				"the header — ERPNext's own SQL bypassed the selection filter."
			),
		)
		self.assertEqual(flt(resp.get("additional_discount_percentage") or 0), 0)

	def test_txn_price_rule_selected_still_applies(self):
		"""The selection filter must not suppress a legitimately chosen rule."""
		import json

		txn_rule = _make_rule(
			"_PNXT_TEST_TxnSelectedPrice",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=25,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)

		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([txn_rule]),
		)

		self.assertIn(txn_rule, resp.get("applied_pricing_rules") or [])
		# 25% of the undiscounted 130 cart.
		self.assertAlmostEqual(flt(resp.get("discount_amount")), 32.5, places=2)

	def test_txn_free_item_and_header_discount_share_one_gate(self):
		"""Both halves of a transaction scheme respond to selection alike.

		Mirrors a Promotional Scheme that carries a price slab and a product
		slab: selecting neither must apply neither, selecting both must apply
		both. The regression this guards is the asymmetric case — free item
		suppressed while the header discount goes through anyway.
		"""
		import json

		price_rule = _make_rule(
			"_PNXT_TEST_TxnPairPrice",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=25,
			apply_discount_on="Grand Total",
		)
		product_rule = _make_rule(
			"_PNXT_TEST_TxnPairProduct",
			apply_on="Transaction",
			price_or_product_discount="Product",
			free_item=ITEM_C,
			free_qty=1,
		)
		# Something real to select instead, so `rule_map` stays non-empty and
		# apply_offers reaches the transaction engine at all — selecting only a
		# name that does not exist short-circuits before it. Scoped to an item
		# the cart does not contain, and gated behind an unreachable min_qty, so
		# it cannot perturb the totals under test.
		decoy_rule = _make_rule(
			"_PNXT_TEST_TxnPairDecoy",
			apply_on="Item Code",
			items=[{"item_code": ITEM_C}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_qty=5,
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)

		neither = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([decoy_rule]),
		)
		self.assertEqual(flt(neither.get("discount_amount") or 0), 0)
		self.assertEqual(neither.get("free_items") or [], [])

		both = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([price_rule, product_rule]),
		)
		self.assertAlmostEqual(flt(both.get("discount_amount")), 32.5, places=2)
		self.assertEqual(
			[f.get("item_code") for f in both.get("free_items") or []],
			[ITEM_C],
		)

	# -------------------------------------------------------------------
	# Item-Level Discount (Type 4) interaction matrix
	# -------------------------------------------------------------------

	def test_item_level_discount_sets_already_discounted_flag(self):
		"""SKU promotion marks the line and applies the configured discount."""
		import json

		rule = _make_rule(
			"_PNXT_TEST_ItemLevelFlag",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=20,
			promotion_type="Item Level Discount",
			min_qty=0,
		)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A, qty=1)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		item = resp["items"][0]
		self.assertAlmostEqual(flt(item.get("discount_percentage")), 20, places=2)
		self.assertTrue(item.get("is_already_discounted"))
		self.assertEqual(item.get("discount_source"), "item_level_promotion")

	def test_auto_discount_excludes_already_discounted_line(self):
		"""Auto Discount applies only to eligible lines when another SKU has item-level promo."""
		import json

		item_rule = _make_rule(
			"_PNXT_TEST_ItemLevelMix",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=20,
			promotion_type="Item Level Discount",
			min_qty=0,
		)
		auto_rule = _make_rule(
			"_PNXT_TEST_AutoExcl",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_amt=50,
			apply_discount_on="Grand Total",
		)
		payload = _cart_payload(
			self.ctx,
			[
				_line(self.ctx, ITEM_A, qty=1),
				_line(self.ctx, ITEM_B, qty=1),
			],
		)
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, auto_rule]),
		)
		item_a, item_b = resp["items"][0], resp["items"][1]
		self.assertTrue(item_a.get("is_already_discounted"))
		self.assertAlmostEqual(flt(item_a.get("discount_percentage")), 20, places=2)
		self.assertAlmostEqual(flt(item_b.get("discount_percentage")), 10, places=2)
		self.assertFalse(item_b.get("is_already_discounted"))

	def test_coupon_excludes_already_discounted_items(self):
		"""Coupon with exclusion enabled discounts only eligible line amounts."""
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import apply_coupon_discount

		coupon = _make_pos_coupon(
			"EXCL10",
			discount_percentage=10,
			exclude_already_discounted_items=1,
		)
		items = [
			frappe._dict(
				{
					"item_code": ITEM_A,
					"qty": 1,
					"price_list_rate": 50,
					"rate": 40,
					"discount_percentage": 20,
					"discount_amount": 10,
					"amount": 40,
					"is_already_discounted": 1,
					"discount_source": "item_level_promotion",
				}
			),
			frappe._dict(
				{
					"item_code": ITEM_B,
					"qty": 1,
					"price_list_rate": 80,
					"rate": 80,
					"discount_percentage": 0,
					"discount_amount": 0,
					"amount": 80,
					"is_already_discounted": 0,
				}
			),
		]
		result = apply_coupon_discount(coupon, cart_total=120, net_total=120, items=items)
		self.assertTrue(result["valid"])
		self.assertAlmostEqual(flt(result["eligible_subtotal"]), 80, places=2)
		self.assertAlmostEqual(flt(result["excluded_subtotal"]), 40, places=2)
		self.assertAlmostEqual(flt(result["discount"]), 8, places=2)

	def test_matrix_engine_classify_states(self):
		"""Unit tests for Promotion Interaction Matrix state classification."""
		from pos_next.api.promotion_exclusions import (
			ITEM_STATE_ALREADY_DISCOUNTED,
			ITEM_STATE_ELIGIBLE,
			ITEM_STATE_EXCLUDED_BRAND,
			PROMOTION_TARGET_AUTO,
			PROMOTION_TARGET_COUPON,
			classify_item_state,
			is_eligible_for_promotion,
		)

		discounted = frappe._dict({"is_already_discounted": 1, "brand": "Nike"})
		self.assertEqual(
			classify_item_state(discounted, target=PROMOTION_TARGET_AUTO),
			ITEM_STATE_ALREADY_DISCOUNTED,
		)
		self.assertFalse(
			is_eligible_for_promotion(discounted, PROMOTION_TARGET_AUTO)
		)
		self.assertFalse(
			is_eligible_for_promotion(discounted, PROMOTION_TARGET_COUPON)
		)

		excluded_brand_item = frappe._dict(
			{"brand": "BrandX", "price_list_rate": 100, "rate": 100}
		)
		self.assertEqual(
			classify_item_state(
				excluded_brand_item,
				excluded_brands={"BrandX"},
				target=PROMOTION_TARGET_COUPON,
			),
			ITEM_STATE_EXCLUDED_BRAND,
		)
		self.assertTrue(
			is_eligible_for_promotion(
				excluded_brand_item,
				PROMOTION_TARGET_AUTO,
				excluded_brands={"BrandX"},
			)
		)
		self.assertFalse(
			is_eligible_for_promotion(
				excluded_brand_item,
				PROMOTION_TARGET_COUPON,
				excluded_brands={"BrandX"},
			)
		)

		normal_item = frappe._dict(
			{"brand": "BrandA", "price_list_rate": 100, "rate": 100}
		)
		self.assertEqual(
			classify_item_state(normal_item, target=PROMOTION_TARGET_COUPON),
			ITEM_STATE_ELIGIBLE,
		)
		self.assertTrue(
			is_eligible_for_promotion(normal_item, PROMOTION_TARGET_COUPON)
		)

	def test_matrix_auto_discount_allows_excluded_brand_line(self):
		"""Excluded brand (coupon) × Auto Discount = eligible per interaction matrix."""
		import json

		auto_rule = _make_rule(
			"_PNXT_TEST_AutoExcludedBrand",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_amt=50,
			apply_discount_on="Grand Total",
		)
		line_a = _line(self.ctx, ITEM_A, qty=1)
		line_a["brand"] = "ExcludedBrand"
		payload = _cart_payload(
			self.ctx,
			[
				line_a,
				_line(self.ctx, ITEM_B, qty=1),
			],
		)
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([auto_rule]),
		)
		item_a = resp["items"][0]
		self.assertAlmostEqual(flt(item_a.get("discount_percentage")), 10, places=2)

	def test_gwp_still_applies_with_item_level_discount(self):
		"""GWP (product discount) is unaffected by item-level discount on another cart line."""
		import json

		item_rule = _make_rule(
			"_PNXT_TEST_ItemLevelGWP",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Item Level Discount",
			min_qty=0,
			priority="2",
		)
		gwp_rule = _make_rule(
			"_PNXT_TEST_GWPWithItemLevel",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			free_item=ITEM_C,
			min_qty=2,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			promotion_type="GWP",
			priority="1",
		)
		payload = _cart_payload(
			self.ctx,
			[
				_line(self.ctx, ITEM_A, qty=1),
				_line(self.ctx, ITEM_B, qty=2),
			],
		)
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, gwp_rule]),
		)
		self.assertTrue(resp["items"][0].get("is_already_discounted"))
		item_b = next(it for it in resp["items"] if it.get("item_code") == ITEM_B)
		self.assertGreater(flt(item_b.get("gwp_free_qty") or item_b.get("discount_amount") or 0), 0)


class TestPromotionMatrix14214(FrappeTestCase):
	"""Promotion Interaction Matrix tests using real item 14214 (when present on site)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Item", MATRIX_ITEM_14214):
			raise unittest.SkipTest(f"Item {MATRIX_ITEM_14214} not on this site")
		cls.ctx = _ctx()

	@classmethod
	def tearDownClass(cls):
		for title in (
			"_MATRIX_TEST_14214_ItemLevel",
			"_MATRIX_TEST_14214_Auto",
			"_MATRIX_TEST_14214_GWP",
		):
			existing = frappe.db.get_value("Pricing Rule", {"title": title}, "name")
			if existing:
				frappe.delete_doc("Pricing Rule", existing, force=True, ignore_permissions=True)
		if frappe.db.exists("POS Coupon", "_MATRIX_TEST_14214_Coupon"):
			frappe.delete_doc("POS Coupon", "_MATRIX_TEST_14214_Coupon", force=True, ignore_permissions=True)
		super().tearDownClass()

	def _item_rate(self, item_code: str) -> float:
		rate = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": self.ctx.price_list, "selling": 1},
			"price_list_rate",
		)
		return flt(rate) or ITEM_PRICES.get(item_code) or 1000

	def _line_14214(self, item_code: str, qty=1, **extra):
		line = _line(self.ctx, item_code, qty=qty, price_list_rate=self._item_rate(item_code))
		line.update(extra)
		return line

	def test_14214_item_level_marks_already_discounted(self):
		"""Matrix row: Already discounted — item-level promo on 14214."""
		import json

		rule = _make_rule(
			"_MATRIX_TEST_14214_ItemLevel",
			apply_on="Item Code",
			items=[{"item_code": MATRIX_ITEM_14214}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=20,
			promotion_type="Item Level Discount",
			min_qty=0,
		)
		payload = _cart_payload(self.ctx, [self._line_14214(MATRIX_ITEM_14214)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule]),
		)
		item = resp["items"][0]
		self.assertEqual(item.get("item_code"), MATRIX_ITEM_14214)
		self.assertAlmostEqual(flt(item.get("discount_percentage")), 20, places=2)
		self.assertTrue(item.get("is_already_discounted"))

	def test_14214_auto_discount_skips_discounted_companion(self):
		"""Matrix: 14214 already discounted, companion gets auto discount."""
		import json

		item_rule = _make_rule(
			"_MATRIX_TEST_14214_ItemLevel",
			apply_on="Item Code",
			items=[{"item_code": MATRIX_ITEM_14214}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=20,
			promotion_type="Item Level Discount",
			min_qty=0,
		)
		auto_rule = _make_rule(
			"_MATRIX_TEST_14214_Auto",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_amt=1000,
			apply_discount_on="Grand Total",
		)
		companion = MATRIX_COMPANION_14214
		if not frappe.db.exists("Item", companion):
			companion = ITEM_B
		payload = _cart_payload(
			self.ctx,
			[
				self._line_14214(MATRIX_ITEM_14214),
				self._line_14214(companion),
			],
		)
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, auto_rule]),
		)
		item_14214, item_other = resp["items"][0], resp["items"][1]
		self.assertTrue(item_14214.get("is_already_discounted"))
		self.assertAlmostEqual(flt(item_14214.get("discount_percentage")), 20, places=2)
		self.assertAlmostEqual(flt(item_other.get("discount_percentage")), 10, places=2)
		self.assertFalse(item_other.get("is_already_discounted"))

	def test_14214_coupon_excludes_discounted_line(self):
		"""Matrix: coupon excludes already-discounted 14214, discounts companion."""
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import apply_coupon_discount

		coupon = _make_pos_coupon(
			"MAT14214",
			coupon_name="_MATRIX_TEST_14214_Coupon",
			exclude_already_discounted_items=1,
		)
		rate_14214 = self._item_rate(MATRIX_ITEM_14214)
		companion = MATRIX_COMPANION_14214 if frappe.db.exists("Item", MATRIX_COMPANION_14214) else ITEM_B
		rate_companion = self._item_rate(companion)
		items = [
			frappe._dict(
				{
					"item_code": MATRIX_ITEM_14214,
					"qty": 1,
					"price_list_rate": rate_14214,
					"rate": rate_14214 * 0.8,
					"discount_percentage": 20,
					"amount": rate_14214 * 0.8,
					"is_already_discounted": 1,
					"discount_source": "item_level_promotion",
				}
			),
			frappe._dict(
				{
					"item_code": companion,
					"qty": 1,
					"price_list_rate": rate_companion,
					"rate": rate_companion,
					"discount_percentage": 0,
					"amount": rate_companion,
					"is_already_discounted": 0,
				}
			),
		]
		result = apply_coupon_discount(
			coupon,
			cart_total=rate_14214 * 0.8 + rate_companion,
			net_total=rate_14214 * 0.8 + rate_companion,
			items=items,
		)
		self.assertTrue(result["valid"])
		self.assertAlmostEqual(flt(result["eligible_subtotal"]), rate_companion, places=2)
		self.assertAlmostEqual(flt(result["discount"]), rate_companion * 0.1, places=2)

	def test_14214_gwp_stacks_with_item_level_on_other_line(self):
		"""Matrix: GWP still applies when 14214 has item-level discount on another line."""
		import json

		companion = MATRIX_COMPANION_14214 if frappe.db.exists("Item", MATRIX_COMPANION_14214) else ITEM_B
		free_item = ITEM_C if frappe.db.exists("Item", ITEM_C) else MATRIX_ITEM_14214
		item_rule = _make_rule(
			"_MATRIX_TEST_14214_ItemLevel",
			apply_on="Item Code",
			items=[{"item_code": MATRIX_ITEM_14214}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Item Level Discount",
			min_qty=0,
			priority="2",
		)
		gwp_rule = _make_rule(
			"_MATRIX_TEST_14214_GWP",
			apply_on="Item Code",
			items=[{"item_code": companion}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			free_item=free_item,
			min_qty=2,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			promotion_type="GWP",
			priority="1",
		)
		payload = _cart_payload(
			self.ctx,
			[
				self._line_14214(MATRIX_ITEM_14214, qty=1),
				self._line_14214(companion, qty=2),
			],
		)
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([item_rule, gwp_rule]),
		)
		self.assertTrue(resp["items"][0].get("is_already_discounted"))
		companion_line = next(it for it in resp["items"] if it.get("item_code") == companion)
		self.assertGreater(
			flt(companion_line.get("gwp_free_qty") or companion_line.get("discount_amount") or 0), 0
		)


class TestPricingRuleScope(FrappeTestCase):
	"""Scope resolution for Pricing Rules — `pos_next.promotions.scope`.

	Pricing Rule keeps its targets in the ``items`` / ``item_groups`` / ``brands``
	child tables. It has **no** scalar ``item_code`` / ``item_group`` / ``brand``
	field, so reading one raises AttributeError — which is exactly what the old
	`_item_matches_pricing_rule` did, taking the whole cart's offers down with it.
	"""

	def test_pricing_rule_has_no_scalar_scope_fields(self):
		"""Pins the reason the child-table helpers exist."""
		rule_name = _make_rule(
			"_PNXT_TEST_ScopeNoScalar",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=5,
		)
		rule = frappe.get_cached_doc("Pricing Rule", rule_name)

		for fieldname in ("item_code", "item_group", "brand"):
			with self.assertRaises(AttributeError):
				getattr(rule, fieldname)

		# The helper reads the child table instead, so it works regardless.
		self.assertTrue(item_matches_rule_scope({"item_code": ITEM_A}, rule))
		self.assertFalse(item_matches_rule_scope({"item_code": ITEM_B}, rule))

	def test_item_group_scope_expands_to_descendants(self):
		"""A rule on a parent group covers items filed under its children."""
		parent, child = _ensure_group_tree()
		rule = frappe._dict(
			{"apply_on": "Item Group", "item_groups": [frappe._dict({"item_group": parent})]}
		)

		keys = get_scope_keys(rule)
		self.assertIn(parent, keys)
		self.assertIn(child, keys)

		self.assertTrue(item_matches_rule_scope({"item_group": child}, rule))
		self.assertTrue(item_matches_rule_scope({"item_group": parent}, rule))
		self.assertFalse(item_matches_rule_scope({"item_group": "All Item Groups"}, rule))

	def test_item_code_and_brand_scopes_match_exactly(self):
		"""Item codes and brands are exact matches — no tree walking."""
		code_rule = frappe._dict(
			{"apply_on": "Item Code", "items": [frappe._dict({"item_code": ITEM_A})]}
		)
		self.assertEqual(get_scope_keys(code_rule), {ITEM_A})
		self.assertTrue(item_matches_rule_scope({"item_code": ITEM_A}, code_rule))
		self.assertFalse(item_matches_rule_scope({"item_code": ITEM_B}, code_rule))

		brand_rule = frappe._dict(
			{"apply_on": "Brand", "brands": [frappe._dict({"brand": TEST_BRAND})]}
		)
		self.assertTrue(item_matches_rule_scope({"brand": TEST_BRAND}, brand_rule))
		self.assertFalse(item_matches_rule_scope({"brand": "Some Other Brand"}, brand_rule))

	def test_transaction_scope_matches_every_line_and_empty_scope_matches_none(self):
		txn_rule = frappe._dict({"apply_on": "Transaction"})
		self.assertTrue(item_matches_rule_scope({"item_code": ITEM_A}, txn_rule))
		self.assertEqual(get_scope_keys(txn_rule), set())

		# Scope table empty, and a line missing the attribute entirely.
		empty_rule = frappe._dict({"apply_on": "Item Group", "item_groups": []})
		self.assertFalse(item_matches_rule_scope({"item_group": TEST_CHILD_GROUP}, empty_rule))

		group_rule = frappe._dict(
			{"apply_on": "Item Group", "item_groups": [frappe._dict({"item_group": TEST_PARENT_GROUP})]}
		)
		self.assertFalse(item_matches_rule_scope({"item_code": ITEM_A}, group_rule))


class TestAutoDiscountScopes(FrappeTestCase):
	"""Auto Discount rules across every apply_on scope.

	Every pre-existing Auto Discount test used ``apply_on="Transaction"``, which
	short-circuits scope matching before it touches a child table — so the
	Item Code / Item Group / Brand paths had no coverage at all.

	These also cover the catalog backfill: the cart payload carries no
	``item_group`` / ``brand``, so a rule scoped to either only matches if
	``apply_offers`` enriches the line from the Item record first.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		_ensure_test_brand()

	def tearDown(self):
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule",
			filters={"title": ["like", "_PNXT_TEST_%"]},
			pluck="name",
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	def _run(self, rule_name, lines):
		import json

		payload = _cart_payload(self.ctx, lines)
		return apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps([rule_name]),
		)

	def test_auto_discount_apply_on_item_code(self):
		"""Regression: this used to raise AttributeError and fail the whole cart."""
		rule = _make_rule(
			"_PNXT_TEST_AutoScopeItemCode",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		item_a, item_b = resp["items"][0], resp["items"][1]
		self.assertAlmostEqual(flt(item_a.get("discount_percentage")), 10, places=2)
		self.assertAlmostEqual(flt(item_b.get("discount_percentage")), 0, places=2)
		self.assertIn(rule, resp.get("applied_pricing_rules") or [])

	def test_auto_discount_apply_on_item_group(self):
		"""Item Group scope, with item_group backfilled from the Item record."""
		item_group = _resolve_item_group()
		rule = _make_rule(
			"_PNXT_TEST_AutoScopeItemGroup",
			apply_on="Item Group",
			item_groups=[{"item_group": item_group}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
		)
		line = _line(self.ctx, ITEM_A)
		self.assertNotIn("item_group", line)  # the cart never sends it

		resp = self._run(rule, [line])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 10, places=2)
		self.assertEqual(resp["items"][0].get("item_group"), item_group)

	def test_auto_discount_apply_on_brand(self):
		"""Brand scope discounts only the branded line; brand is backfilled too."""
		rule = _make_rule(
			"_PNXT_TEST_AutoScopeBrand",
			apply_on="Brand",
			brands=[{"brand": TEST_BRAND}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=25,
			promotion_type="Auto Discount",
			min_qty=0,
		)
		line_c = _line(self.ctx, ITEM_C)
		self.assertNotIn("brand", line_c)

		resp = self._run(rule, [_line(self.ctx, ITEM_A), line_c])

		item_a, item_c = resp["items"][0], resp["items"][1]
		self.assertAlmostEqual(flt(item_c.get("discount_percentage")), 25, places=2)
		self.assertEqual(item_c.get("brand"), TEST_BRAND)
		self.assertAlmostEqual(flt(item_a.get("discount_percentage")), 0, places=2)

	def test_auto_discount_item_group_matches_descendant_items(self):
		"""A rule on an ancestor group covers items filed further down the tree."""
		item_group = _resolve_item_group()
		ancestor = frappe.db.get_value("Item Group", item_group, "parent_item_group")
		if not ancestor:
			self.skipTest(f"{item_group} has no parent group to scope the rule to")

		rule = _make_rule(
			"_PNXT_TEST_AutoScopeGroupTree",
			apply_on="Item Group",
			item_groups=[{"item_group": ancestor}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 10, places=2)


class TestDiscountPipeline(FrappeTestCase):
	"""The per-line accumulator in `pos_next.promotions.engine`.

	Passes contribute *named parts* instead of assigning discount_percentage, so
	two different passes sum on one line while a repeat contribution from the
	same pass replaces its earlier value.
	"""

	def _line_dict(self, price=100.0, qty=1):
		return frappe._dict(
			{"item_code": ITEM_A, "qty": qty, "price_list_rate": price, "rate": price}
		)

	def test_parts_from_different_sources_sum(self):
		item = self._line_dict()
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 10)
		engine.add_line_part(item, engine.PART_ACCUMULATIVE, 8)
		engine.finalize_line_discounts([item])

		self.assertAlmostEqual(flt(item.discount_percentage), 18, places=4)
		self.assertAlmostEqual(flt(item.rate), 82, places=4)
		self.assertAlmostEqual(flt(item.discount_amount), 18, places=4)

	def test_same_source_replaces_rather_than_accumulates(self):
		item = self._line_dict()
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 10)
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 25)
		engine.finalize_line_discounts([item])

		self.assertAlmostEqual(flt(item.discount_percentage), 25, places=4)

	def test_baseline_from_earlier_engine_pass_is_preserved(self):
		"""Whatever ERPNext's per-item engine wrote is the floor, not overwritten."""
		item = self._line_dict()
		item.discount_percentage = 5  # as if the ERPNext pass had set it
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 10)
		engine.finalize_line_discounts([item])

		self.assertAlmostEqual(flt(item.discount_percentage), 15, places=4)

	def test_untouched_lines_are_left_exactly_as_found(self):
		item = self._line_dict()
		item.discount_percentage = 7
		item.rate = 93
		engine.begin_line_discounts([item])
		engine.finalize_line_discounts([item])

		self.assertAlmostEqual(flt(item.discount_percentage), 7, places=4)
		self.assertAlmostEqual(flt(item.rate), 93, places=4)

	def test_total_is_clamped_and_cap_resolver_is_honoured(self):
		item = self._line_dict()
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 80)
		engine.add_line_part(item, engine.PART_ACCUMULATIVE, 60)
		engine.finalize_line_discounts([item])
		self.assertAlmostEqual(flt(item.discount_percentage), 100, places=4)

		capped = self._line_dict()
		engine.begin_line_discounts([capped])
		engine.add_line_part(capped, engine.PART_AUTO_DISCOUNT, 40)
		engine.finalize_line_discounts([capped], cap_resolver=lambda _item: 15)
		self.assertAlmostEqual(flt(capped.discount_percentage), 15, places=4)

	def test_bookkeeping_keys_never_survive_finalize(self):
		"""The accumulator's scratch keys must not leak into the API response."""
		item = self._line_dict()
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, 10)
		engine.finalize_line_discounts([item])

		self.assertNotIn("_pos_discount_parts", item)
		self.assertNotIn("_pos_discount_base", item)

	def test_rate_rule_lands_exactly_on_the_target_rate(self):
		"""A `Rate` rule should price the line at rule.rate, not discount it twice."""
		item = self._line_dict(price=100.0, qty=2)
		rule = frappe._dict({"rate_or_discount": "Rate", "rate": 80})

		pct = engine.pricing_rule_line_percentage(item, rule)
		engine.begin_line_discounts([item])
		engine.add_line_part(item, engine.PART_AUTO_DISCOUNT, pct)
		engine.finalize_line_discounts([item])

		self.assertAlmostEqual(flt(item.rate), 80, places=4)


class TestDiscountPipelineIdempotency(FrappeTestCase):
	"""Running apply_offers twice over the same cart must not compound discounts."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def tearDown(self):
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule",
			filters={"title": ["like", "_PNXT_TEST_%"]},
			pluck="name",
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	def test_repeated_apply_offers_is_stable(self):
		import json

		rule = _make_rule(
			"_PNXT_TEST_PipelineIdempotent",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
		)

		seen = []
		for _ in range(3):
			payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A)])
			resp = apply_offers(
				invoice_data=json.dumps(payload),
				selected_offers=json.dumps([rule]),
			)
			seen.append(
				(
					flt(resp["items"][0].get("discount_percentage")),
					flt(resp["items"][0].get("rate")),
				)
			)

		self.assertEqual(len(set(seen)), 1, f"discount drifted across runs: {seen}")
		self.assertAlmostEqual(seen[0][0], 10, places=2)


class TestAccumulativeDiscount(FrappeTestCase):
	"""Accumulative discounts — sum the percentage of every scope present in the cart.

	A rule lists scopes (item codes, item groups or brands), each with its own
	``pos_discount_percentage``. Every scope represented in the cart contributes,
	and the total lands uniformly on each eligible line — so a cart spanning more
	scopes earns a larger discount on everything in it.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		_ensure_test_brand()

	def tearDown(self):
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule",
			filters={"title": ["like", "_PNXT_TEST_%"]},
			pluck="name",
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	def _accumulative_rule(self, title, **fields):
		"""Build an Accumulative rule; callers supply the scope table themselves."""
		defaults = {
			"apply_on": "Item Code",
			"rate_or_discount": "Discount Percentage",
			"price_or_product_discount": "Price",
			"discount_percentage": 0,
			"apply_discount_on_price": "Accumulative",
			"promotion_type": "Item Level Discount",
			"min_qty": 0,
		}
		defaults.update(fields)
		return _make_rule(title, **defaults)

	def _run(self, rules, lines):
		import json

		payload = _cart_payload(self.ctx, lines)
		return apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps(rules if isinstance(rules, list) else [rules]),
		)

	def test_single_scope_earns_only_its_own_percentage(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumOneScope",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 5, places=2)

	def test_two_scopes_present_sum_and_apply_to_every_line(self):
		"""The headline behaviour: 5% + 3% = 8% on *both* lines, not 5% and 3%."""
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumTwoScopes",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		for item in resp["items"][:2]:
			self.assertAlmostEqual(flt(item.get("discount_percentage")), 8, places=2)

	def test_absent_scope_contributes_nothing(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumAbsentScope",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
				{"item_code": ITEM_C, "pos_discount_percentage": 40},
			],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 8, places=2)

	def test_accumulates_across_item_groups(self):
		parent, child = _ensure_group_tree()
		item_group = _resolve_item_group()
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumItemGroup",
			apply_on="Item Group",
			item_groups=[
				{"item_group": item_group, "pos_discount_percentage": 5},
				{"item_group": parent, "pos_discount_percentage": 3},
			],
		)
		# Only `item_group` is represented; the parent tree holds no cart lines.
		resp = self._run(rule, [_line(self.ctx, ITEM_A)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 5, places=2)
		self.assertNotEqual(child, item_group)

	def test_accumulates_across_brands(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumBrand",
			apply_on="Brand",
			brands=[{"brand": TEST_BRAND, "pos_discount_percentage": 12}],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_C)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 12, places=2)

	def test_auto_discount_stacks_on_top_of_accumulative(self):
		"""The interaction you asked for: 8% accumulative + 10% auto = 18%."""
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumStackBase",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
		)
		auto = _make_rule(
			"_PNXT_TEST_AccumStackAuto",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
			apply_discount_on="Grand Total",
		)
		resp = self._run([accum, auto], [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		for item in resp["items"][:2]:
			self.assertAlmostEqual(flt(item.get("discount_percentage")), 18, places=2)

	def test_plain_item_level_discount_still_blocks_auto_discount(self):
		"""Only Accumulative stacks — an ordinary item-level promo must not."""
		item_level = _make_rule(
			"_PNXT_TEST_AccumControlItemLevel",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=5,
			promotion_type="Item Level Discount",
			min_qty=0,
		)
		auto = _make_rule(
			"_PNXT_TEST_AccumControlAuto",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
			apply_discount_on="Grand Total",
		)
		resp = self._run([item_level, auto], [_line(self.ctx, ITEM_A)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 5, places=2)

	def test_rule_cap_limits_the_sum(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumCapped",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 30},
				{"item_code": ITEM_B, "pos_discount_percentage": 30},
			],
			max_accumulated_discount_percentage=25,
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 25, places=2)

	def test_item_max_discount_clamps_the_line(self):
		"""ERPNext's own item ceiling wins — validate_max_discount would throw otherwise."""
		frappe.db.set_value("Item", ITEM_A, "max_discount", 6)
		frappe.clear_document_cache("Item", ITEM_A)
		self.addCleanup(frappe.clear_document_cache, "Item", ITEM_A)
		self.addCleanup(frappe.db.set_value, "Item", ITEM_A, "max_discount", 0)

		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumItemMax",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 6, places=2)
		# ITEM_B has no ceiling, so it keeps the full accumulated total.
		self.assertAlmostEqual(flt(resp["items"][1].get("discount_percentage")), 8, places=2)

	def test_min_scopes_required_gates_the_discount(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumMinScopes",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
			min_scopes_required=2,
		)
		alone = self._run(rule, [_line(self.ctx, ITEM_A)])
		self.assertAlmostEqual(flt(alone["items"][0].get("discount_percentage")), 0, places=2)

		both = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		self.assertAlmostEqual(flt(both["items"][0].get("discount_percentage")), 8, places=2)

	def test_line_is_flagged_accumulative_for_the_matrix(self):
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumFlag",
			items=[{"item_code": ITEM_A, "pos_discount_percentage": 5}],
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A)])
		item = resp["items"][0]
		self.assertTrue(item.get("is_accumulative_discount"))
		self.assertEqual(item.get("discount_source"), "accumulative_promotion")

	def test_promotional_scheme_saves_and_applies(self):
		"""Regression: ERPNext strips per-row percentages from the generated rule.

		It rebuilds the rule's scope table as {item_code, uom} and saves it during
		the scheme's own on_update — before sync_scope_percentages_to_pricing_rules
		runs. Validating that copy rejected every accumulative scheme with
		"Set Discount % on at least one Item Code row".
		"""
		import json

		scheme_name = "_PNXT_TEST_AccumScheme"
		if frappe.db.exists("Promotional Scheme", scheme_name):
			frappe.delete_doc("Promotional Scheme", scheme_name, force=True, ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.db.exists("Promotional Scheme", scheme_name)
			and frappe.delete_doc(
				"Promotional Scheme", scheme_name, force=True, ignore_permissions=True
			)
		)

		scheme = frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": scheme_name,
				"company": _resolve_company(),
				"apply_on": "Item Code",
				"selling": 1,
				"buying": 0,
				"valid_from": nowdate(),
				"promotion_type": "Item Level Discount",
				"items": [
					{"item_code": ITEM_A, "pos_discount_percentage": 5},
					{"item_code": ITEM_B, "pos_discount_percentage": 3},
				],
				"price_discount_slabs": [
					{
						"rule_description": "Accumulative scheme",
						"min_qty": 0,
						"rate_or_discount": "Discount Percentage",
						"discount_percentage": 0,
						"apply_discount_on_price": "Accumulative",
						"min_scopes_required": 1,
					}
				],
			}
		)
		scheme.insert(ignore_permissions=True)

		rules = frappe.get_all("Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name")
		self.assertTrue(rules, "scheme generated no pricing rules")

		generated = frappe.get_doc("Pricing Rule", rules[0])
		self.assertEqual(generated.get("apply_discount_on_price"), "Accumulative")
		# The on_update sync must have restored what ERPNext dropped.
		self.assertEqual(
			{row.item_code: flt(row.get("pos_discount_percentage")) for row in generated.items},
			{ITEM_A: 5.0, ITEM_B: 3.0},
		)

		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		resp = apply_offers(
			invoice_data=json.dumps(payload),
			selected_offers=json.dumps(rules),
		)
		for item in resp["items"][:2]:
			self.assertAlmostEqual(flt(item.get("discount_percentage")), 8, places=2)

	def test_rule_level_percentage_is_ignored(self):
		"""Regression: a rule-level discount_percentage used to stack underneath.

		ERPNext's per-item engine applied the rule's own 10%, which became the
		pipeline baseline, and the accumulated 8% landed on top for 18%. Every
		cross-cart mode now defers, so only the per-scope total counts.
		"""
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumIgnoresRulePct",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
			discount_percentage=10,
		)
		resp = self._run(rule, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		for item in resp["items"][:2]:
			self.assertAlmostEqual(flt(item.get("discount_percentage")), 8, places=2)

	def test_targeted_rule_wins_outright_over_accumulative(self):
		"""A rule aimed at one item replaces the accumulated total on that line.

		Regression: the targeted 15% landed in the pipeline baseline and the
		accumulated 5% piled on top for 20%. Other lines keep accumulating.
		"""
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumPrecedence",
			apply_on="Item Group",
			item_groups=[{"item_group": _resolve_item_group(), "pos_discount_percentage": 5}],
			priority="1",
		)
		targeted = _make_rule(
			"_PNXT_TEST_AccumPrecedenceTargeted",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
			min_qty=0,
			priority="5",
		)
		resp = self._run([accum, targeted], [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		item_a, item_b = resp["items"][0], resp["items"][1]
		self.assertAlmostEqual(flt(item_a.get("discount_percentage")), 15, places=2)
		self.assertAlmostEqual(flt(item_b.get("discount_percentage")), 5, places=2)

	def test_unpriced_line_is_not_claimed_or_counted(self):
		"""A line with no price yields 0.00 whatever the percentage.

		Regression: such lines were flagged is_already_discounted / carried the
		rule name / showed discount_source=accumulative_promotion while displaying
		0%, which also blocked coupons and let them contribute their scope.
		"""
		rule = self._accumulative_rule(
			"_PNXT_TEST_AccumUnpriced",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_C, "pos_discount_percentage": 7},
			],
		)
		unpriced = _line(self.ctx, ITEM_C)
		unpriced["rate"] = 0
		unpriced["price_list_rate"] = 0

		resp = self._run(rule, [_line(self.ctx, ITEM_A), unpriced])
		priced_line, unpriced_line = resp["items"][0], resp["items"][1]

		# ITEM_C contributes nothing, so ITEM_A accumulates its own 5% only.
		self.assertAlmostEqual(flt(priced_line.get("discount_percentage")), 5, places=2)

		self.assertAlmostEqual(flt(unpriced_line.get("discount_percentage")), 0, places=2)
		self.assertFalse(unpriced_line.get("is_accumulative_discount"))
		self.assertNotEqual(unpriced_line.get("discount_source"), "accumulative_promotion")
		# Not flagged as discounted, so a coupon can still reach the line.
		self.assertFalse(unpriced_line.get("is_already_discounted"))

	def test_item_scoped_auto_discount_wins_outright(self):
		"""Regression: a targeted Auto Discount stacked instead of replacing.

		It reaches the line as a pipeline *part*, not the baseline, so the earlier
		baseline check could not see it — 5% + 15% came out as 20%.
		"""
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumVsScopedAuto",
			apply_on="Item Group",
			item_groups=[{"item_group": _resolve_item_group(), "pos_discount_percentage": 5}],
			priority="1",
		)
		scoped_auto = _make_rule(
			"_PNXT_TEST_AccumVsScopedAutoRule",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
			promotion_type="Auto Discount",
			min_qty=0,
			priority="5",
		)
		resp = self._run([accum, scoped_auto], [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 15, places=2)
		self.assertAlmostEqual(flt(resp["items"][1].get("discount_percentage")), 5, places=2)

	def test_transaction_auto_discount_still_stacks(self):
		"""The counterpart: a cart-level Auto Discount is orthogonal and still sums."""
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumVsTxnAuto",
			apply_on="Item Group",
			item_groups=[{"item_group": _resolve_item_group(), "pos_discount_percentage": 5}],
			priority="1",
		)
		txn_auto = _make_rule(
			"_PNXT_TEST_AccumVsTxnAutoRule",
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			promotion_type="Auto Discount",
			min_qty=0,
			apply_discount_on="Grand Total",
			priority="7",
		)
		resp = self._run([accum, txn_auto], [_line(self.ctx, ITEM_B)])
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 15, places=2)

	def test_scoped_auto_line_does_not_contribute_its_scope(self):
		"""A line a scoped Auto Discount claims drops out of the accumulation entirely."""
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumScopedAutoScope",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
			priority="1",
		)
		scoped_auto = _make_rule(
			"_PNXT_TEST_AccumScopedAutoScopeRule",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
			promotion_type="Auto Discount",
			min_qty=0,
			priority="5",
		)
		resp = self._run([accum, scoped_auto], [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 15, places=2)
		# ITEM_A's scope contributes nothing: no line is left to receive it.
		self.assertAlmostEqual(flt(resp["items"][1].get("discount_percentage")), 3, places=2)

	def test_targeted_line_does_not_contribute_its_scope(self):
		"""A line that keeps its own rule cannot inflate everyone else's total."""
		parent = _resolve_item_group()
		accum = self._accumulative_rule(
			"_PNXT_TEST_AccumPrecedenceScope",
			items=[
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
			priority="1",
		)
		targeted = _make_rule(
			"_PNXT_TEST_AccumPrecedenceScopeTargeted",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
			min_qty=0,
			priority="5",
		)
		resp = self._run([accum, targeted], [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])

		# ITEM_A keeps its own 15%; ITEM_B accumulates only its own scope (3%),
		# because ITEM_A's scope has no line left that would actually receive it.
		self.assertAlmostEqual(flt(resp["items"][0].get("discount_percentage")), 15, places=2)
		self.assertAlmostEqual(flt(resp["items"][1].get("discount_percentage")), 3, places=2)
		self.assertNotEqual(parent, None)

	def test_standalone_rule_without_percentages_is_still_rejected(self):
		"""The guard must survive the scheme-generated exemption."""
		with self.assertRaises(frappe.ValidationError):
			self._accumulative_rule(
				"_PNXT_TEST_AccumStandaloneNoPct",
				items=[{"item_code": ITEM_A}],
			)

	def test_coupons_are_still_blocked_on_an_accumulative_line(self):
		from pos_next.api.promotion_exclusions import (
			PROMOTION_TARGET_AUTO,
			PROMOTION_TARGET_COUPON,
			is_eligible_for_promotion,
		)

		line = frappe._dict({"item_code": ITEM_A, "qty": 1, "is_accumulative_discount": 1})
		self.assertTrue(is_eligible_for_promotion(line, PROMOTION_TARGET_AUTO))
		self.assertFalse(is_eligible_for_promotion(line, PROMOTION_TARGET_COUPON))


class TestAccumulativeValidation(FrappeTestCase):
	"""Config guards on Pricing Rules using the Accumulative mode."""

	def tearDown(self):
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule", filters={"title": ["like", "_PNXT_TEST_%"]}, pluck="name"
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	def test_transaction_scope_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_make_rule(
				"_PNXT_TEST_AccumBadScope",
				apply_on="Transaction",
				rate_or_discount="Discount Percentage",
				price_or_product_discount="Price",
				apply_discount_on_price="Accumulative",
			)

	def test_scope_rows_without_a_percentage_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_make_rule(
				"_PNXT_TEST_AccumNoPct",
				apply_on="Item Code",
				items=[{"item_code": ITEM_A}],
				rate_or_discount="Discount Percentage",
				price_or_product_discount="Price",
				apply_discount_on_price="Accumulative",
			)

	def test_wrong_promotion_type_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_make_rule(
				"_PNXT_TEST_AccumBadType",
				apply_on="Item Code",
				items=[{"item_code": ITEM_A, "pos_discount_percentage": 5}],
				rate_or_discount="Discount Percentage",
				price_or_product_discount="Price",
				apply_discount_on_price="Accumulative",
				promotion_type="GWP",
			)

	def test_valid_rule_gets_mixed_conditions_and_pos_only_forced(self):
		name = _make_rule(
			"_PNXT_TEST_AccumForced",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A, "pos_discount_percentage": 5}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			apply_discount_on_price="Accumulative",
			promotion_type="Item Level Discount",
		)
		doc = frappe.get_doc("Pricing Rule", name)
		self.assertTrue(doc.mixed_conditions)
		self.assertTrue(doc.pos_only)


class TestAccumulativeSchemeCheckbox(FrappeTestCase):
	"""`pos_is_accumulative` is an authoring control; the slab stays canonical.

	The checkbox hides the price discount table, so the server must materialise
	the single slab ERPNext needs — an empty child table generates no Pricing Rule
	at all and the scheme would save clean while discounting nothing.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def _scheme_doc(self, name, **overrides):
		if frappe.db.exists("Promotional Scheme", name):
			frappe.delete_doc("Promotional Scheme", name, force=True, ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.db.exists("Promotional Scheme", name)
			and frappe.delete_doc("Promotional Scheme", name, force=True, ignore_permissions=True)
		)
		payload = {
			"doctype": "Promotional Scheme",
			"name": name,
			"company": _resolve_company(),
			"apply_on": "Item Code",
			"selling": 1,
			"buying": 0,
			"valid_from": nowdate(),
			"promotion_type": "Item Level Discount",
			"pos_is_accumulative": 1,
			"min_scopes_required": 1,
			"items": [
				{"item_code": ITEM_A, "pos_discount_percentage": 5},
				{"item_code": ITEM_B, "pos_discount_percentage": 3},
			],
		}
		payload.update(overrides)
		return frappe.get_doc(payload)

	def test_checkbox_alone_materialises_the_slab_and_generates_a_rule(self):
		"""No slab supplied at all — the API path a form would never exercise."""
		scheme = self._scheme_doc("_PNXT_TEST_AccumCheckbox")
		self.assertFalse(scheme.get("price_discount_slabs"))
		scheme.insert(ignore_permissions=True)

		slabs = scheme.get("price_discount_slabs") or []
		self.assertEqual(len(slabs), 1, "server must maintain exactly one slab")
		self.assertEqual(slabs[0].apply_discount_on_price, "Accumulative")
		self.assertEqual(slabs[0].rate_or_discount, "Discount Percentage")
		self.assertTrue(slabs[0].rule_description, "slab's only reqd field must be injected")
		self.assertTrue(scheme.mixed_conditions)
		self.assertTrue(scheme.pos_only)

		rules = frappe.get_all("Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name")
		self.assertEqual(len(rules), 1, "an empty slab table would have generated nothing")
		self.assertEqual(
			frappe.db.get_value("Pricing Rule", rules[0], "apply_discount_on_price"), "Accumulative"
		)

	def test_parent_config_is_projected_onto_the_generated_rule(self):
		scheme = self._scheme_doc(
			"_PNXT_TEST_AccumCheckboxCfg",
			min_qty=2,
			min_amount=50,
			max_accumulated_discount_percentage=25,
			min_scopes_required=2,
		)
		scheme.insert(ignore_permissions=True)

		rule = frappe.get_doc(
			"Pricing Rule",
			frappe.get_all("Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name")[0],
		)
		self.assertAlmostEqual(flt(rule.min_qty), 2, places=2)
		self.assertAlmostEqual(flt(rule.min_amt), 50, places=2)
		self.assertAlmostEqual(flt(rule.max_accumulated_discount_percentage), 25, places=2)
		self.assertEqual(int(rule.min_scopes_required), 2)

	def test_toggling_off_and_on_keeps_exactly_one_slab(self):
		"""Idempotency: repeated saves must not append a slab (or a Pricing Rule) each time."""
		scheme = self._scheme_doc("_PNXT_TEST_AccumCheckboxToggle")
		scheme.insert(ignore_permissions=True)

		for _ in range(3):
			scheme.reload()
			scheme.save(ignore_permissions=True)

		scheme.reload()
		self.assertEqual(len(scheme.get("price_discount_slabs") or []), 1)
		self.assertEqual(
			len(frappe.get_all("Pricing Rule", filters={"promotional_scheme": scheme.name})), 1
		)

	def test_accumulative_and_min_max_together_are_rejected(self):
		"""The checkbox re-admits a state the single Select made impossible."""
		scheme = self._scheme_doc(
			"_PNXT_TEST_AccumCheckboxConflict",
			price_discount_slabs=[
				{
					"rule_description": "min/max row",
					"rate_or_discount": "Discount Percentage",
					"discount_percentage": 10,
					"apply_discount_on_price": "Min",
				}
			],
		)
		with self.assertRaises(frappe.ValidationError):
			scheme.insert(ignore_permissions=True)

	def test_multiple_slabs_are_rejected(self):
		"""Several rows would generate several identical rules -> conflict at the till."""
		scheme = self._scheme_doc(
			"_PNXT_TEST_AccumCheckboxMultiSlab",
			price_discount_slabs=[
				{"rule_description": "a", "rate_or_discount": "Discount Percentage", "min_qty": 1},
				{"rule_description": "b", "rate_or_discount": "Discount Percentage", "min_qty": 5},
			],
		)
		with self.assertRaises(frappe.ValidationError):
			scheme.insert(ignore_permissions=True)

	def test_discount_applies_end_to_end_from_the_checkbox(self):
		import json

		scheme = self._scheme_doc("_PNXT_TEST_AccumCheckboxApply")
		scheme.insert(ignore_permissions=True)
		rules = frappe.get_all("Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name")

		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		resp = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps(rules))
		for item in resp["items"][:2]:
			self.assertAlmostEqual(flt(item.get("discount_percentage")), 8, places=2)


class TestAccumulativeOfflinePayload(FrappeTestCase):
	"""`get_offers` must ship enough for the offline engine to reproduce the math.

	Scope values are expanded server-side so `computeAccumulativeDiscount` in
	posCart.js can match with a plain lookup instead of walking the group tree.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def tearDown(self):
		super().tearDown()
		for rule_name in frappe.get_all(
			"Pricing Rule", filters={"title": ["like", "_PNXT_TEST_%"]}, pluck="name"
		):
			try:
				frappe.db.set_value("Pricing Rule", rule_name, "disable", 1)
			except Exception:
				pass
		frappe.db.commit()

	def _offers_by_name(self):
		from pos_next.api.offers import get_offers

		return {offer["name"]: offer for offer in get_offers(self.ctx.pos_profile)}

	def test_payload_carries_expanded_scopes_and_config(self):
		parent, child = _ensure_group_tree()
		leaf = _resolve_item_group()

		rule = _make_rule(
			"_PNXT_TEST_AccumPayload",
			apply_on="Item Group",
			item_groups=[
				{"item_group": parent, "pos_discount_percentage": 5},
				{"item_group": leaf, "pos_discount_percentage": 3},
			],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=0,
			apply_discount_on_price="Accumulative",
			promotion_type="Item Level Discount",
			min_qty=0,
			max_accumulated_discount_percentage=20,
			min_scopes_required=2,
		)

		payload = self._offers_by_name().get(rule)
		self.assertIsNotNone(payload, "accumulative rule missing from get_offers")

		self.assertEqual(payload["apply_discount_on_price"], "Accumulative")
		self.assertEqual(payload["accumulative_scope_field"], "item_group")
		self.assertAlmostEqual(flt(payload["max_accumulated_discount_percentage"]), 20, places=2)
		self.assertEqual(int(payload["min_scopes_required"]), 2)

		scopes = payload["accumulative_scopes"] or []
		self.assertEqual(len(scopes), 2)

		parent_scope = next(s for s in scopes if parent in (s["values"] or []))
		self.assertAlmostEqual(flt(parent_scope["discount_percentage"]), 5, places=2)
		# Pre-expanded: the client never has to resolve the tree itself.
		self.assertIn(child, parent_scope["values"])

	def test_zero_percentage_rows_are_omitted(self):
		leaf = _resolve_item_group()
		rule = _make_rule(
			"_PNXT_TEST_AccumPayloadZero",
			apply_on="Item Group",
			item_groups=[
				{"item_group": leaf, "pos_discount_percentage": 4},
				{"item_group": _ensure_group_tree()[0], "pos_discount_percentage": 0},
			],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=0,
			apply_discount_on_price="Accumulative",
			promotion_type="Item Level Discount",
			min_qty=0,
		)

		payload = self._offers_by_name().get(rule)
		self.assertIsNotNone(payload)
		self.assertEqual(len(payload["accumulative_scopes"] or []), 1)

	def test_eligible_item_groups_are_expanded_to_descendants(self):
		"""The client matches item_group with a plain includes(), so the server
		must hand it the whole subtree — otherwise a rule on a parent group is
		judged ineligible and never sent, though the server would apply it."""
		parent, child = _ensure_group_tree()
		rule = _make_rule(
			"_PNXT_TEST_EligibleGroupTree",
			apply_on="Item Group",
			item_groups=[{"item_group": parent}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_qty=0,
		)

		payload = self._offers_by_name().get(rule)
		self.assertIsNotNone(payload)
		self.assertIn(parent, payload["eligible_item_groups"])
		self.assertIn(child, payload["eligible_item_groups"])

	def test_ordinary_offers_carry_no_accumulative_data(self):
		rule = _make_rule(
			"_PNXT_TEST_AccumPayloadPlain",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			min_qty=0,
		)

		payload = self._offers_by_name().get(rule)
		self.assertIsNotNone(payload)
		self.assertIsNone(payload["accumulative_scopes"])
		self.assertIsNone(payload["accumulative_scope_field"])


def run_all():
	"""Run every test in TestPromotions via unittest. Returns the unittest result.

	Designed for invocation via `bench --site <site> execute
	pos_next.test_promotions.run_all` on a dev site where `bench run-tests`
	would wipe data. In CI, `bench run-tests --app pos_next` picks the same
	tests up automatically.
	"""
	import unittest

	loader = unittest.TestLoader()
	suite = unittest.TestSuite(
		loader.loadTestsFromTestCase(case)
		for case in (
			TestPromotions,
			TestPricingRuleScope,
			TestAutoDiscountScopes,
			TestDiscountPipeline,
			TestDiscountPipelineIdempotency,
			TestAccumulativeDiscount,
			TestAccumulativeValidation,
			TestAccumulativeSchemeCheckbox,
			TestAccumulativeOfflinePayload,
		)
	)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	return {
		"tests_run": result.testsRun,
		"failures": [str(f[0]) for f in result.failures],
		"errors": [str(e[0]) for e in result.errors],
		"was_successful": result.wasSuccessful(),
	}
