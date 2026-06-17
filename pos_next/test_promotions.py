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

import frappe
from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

import pos_next  # noqa: F401 — ensure app hooks load.
from pos_next.api.invoices import apply_offers, submit_invoice, update_invoice

ITEM_A = "_PNXT_TEST_ITEM_A"  # Standard Selling: 50
ITEM_B = "_PNXT_TEST_ITEM_B"  # Standard Selling: 80
ITEM_C = "_PNXT_TEST_ITEM_C"  # Standard Selling: 20

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

	def test_applied_promotional_scheme_stamped(self):
		"""A line discounted by a Promotional Scheme links to that scheme; an
		undiscounted line stays blank."""
		scheme_name = "_PNXT_TEST_Scheme"
		if frappe.db.exists("Promotional Scheme", scheme_name):
			frappe.delete_doc("Promotional Scheme", scheme_name, force=True, ignore_permissions=True)
		scheme = frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"__newname": scheme_name,
				"apply_on": "Item Code",
				"selling": 1,
				"company": _resolve_company(),
				"currency": frappe.get_cached_value("Company", _resolve_company(), "default_currency"),
				"valid_from": nowdate(),
				"items": [{"item_code": ITEM_A}],
				"price_discount_slabs": [
					{
						"rule_description": "_PNXT_TEST_Scheme slab",
						"rate_or_discount": "Discount Percentage",
						"discount_percentage": 15,
						"min_qty": 1,
						"disable": 0,
					}
				],
			}
		).insert(ignore_permissions=True)

		scheme_rules = frappe.get_all(
			"Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name"
		)
		self.assertTrue(scheme_rules, "scheme should generate a Pricing Rule")

		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		_apply_offers_and_stamp(payload, scheme_rules)
		paid = sum(flt(i["rate"]) * flt(i["qty"]) for i in payload["items"])
		final = _submit_invoice(self.ctx, payload, paid_amount=paid)

		line_a = next(i for i in final.items if i.item_code == ITEM_A)
		line_b = next(i for i in final.items if i.item_code == ITEM_B)

		self.assertEqual(line_a.pos_applied_promotional_scheme, scheme.name)
		self.assertFalse(line_b.pos_applied_promotional_scheme)
		self.assertEqual((line_a.pricing_rules or ""), "")

		frappe.delete_doc("Promotional Scheme", scheme.name, force=True, ignore_permissions=True)

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
		"""Buy 2 get 1 free where free = bought item."""
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
		_apply_offers_and_stamp(payload, [rule])
		final = _submit_invoice(self.ctx, payload, paid_amount=100)

		self.assertEqual(final.status, "Paid")
		self.assertAlmostEqual(flt(final.grand_total), 100, places=2)

		paid_lines = [it for it in final.items if not it.is_free_item]
		free_lines = [it for it in final.items if it.is_free_item]
		self.assertEqual(len(paid_lines), 1)
		self.assertAlmostEqual(flt(paid_lines[0].qty), 2, places=2)
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


def run_all():
	"""Run every test in TestPromotions via unittest. Returns the unittest result.

	Designed for invocation via `bench --site <site> execute
	pos_next.test_promotions.run_all` on a dev site where `bench run-tests`
	would wipe data. In CI, `bench run-tests --app pos_next` picks the same
	tests up automatically.
	"""
	import unittest

	loader = unittest.TestLoader()
	suite = loader.loadTestsFromTestCase(TestPromotions)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	return {
		"tests_run": result.testsRun,
		"failures": [str(f[0]) for f in result.failures],
		"errors": [str(e[0]) for e in result.errors],
		"was_successful": result.wasSuccessful(),
	}
