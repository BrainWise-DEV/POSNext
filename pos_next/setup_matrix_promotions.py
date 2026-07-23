# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Idempotent Promotion Interaction Matrix fixtures for manual POS QA.

Creates **Promotional Schemes** (not standalone Pricing Rules) so offers appear
in POS Promotion Management and auto-generate linked Pricing Rules.

Usage:
    bench --site <site> execute pos_next.setup_matrix_promotions.setup
    bench --site <site> execute pos_next.setup_matrix_promotions.teardown
    bench --site <site> execute pos_next.setup_matrix_promotions.print_guide
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, cstr, flt, nowdate

MATRIX_ITEM = "14214"
MATRIX_COMPANION = "4124124"
MATRIX_FREE_ITEM = "gift1"
MATRIX_TEST_BRAND = "MatrixTest"
MATRIX_COUPON_CODE = "MATRIX10"
MATRIX_COMPANION_COUPON_CODE = "MATRIXCOMP10"

SCHEME_PREFIX = "_MATRIX_14214_"
SCHEME_ITEM_LEVEL = f"{SCHEME_PREFIX}ItemLevel"
SCHEME_AUTO = f"{SCHEME_PREFIX}AutoDiscount"
SCHEME_GWP = f"{SCHEME_PREFIX}GWP"
COUPON_NAME = f"{SCHEME_PREFIX}Coupon"
COMPANION_COUPON_NAME = f"{SCHEME_PREFIX}CompanionCoupon"


def _resolve_company():
	if frappe.db.exists("Company", "Brainwise"):
		return "Brainwise"
	default = frappe.defaults.get_global_default("company")
	if default:
		return default
	return frappe.db.get_value("Company", {"name": ["!=", ""]}, "name")


def _delete_scheme(name: str) -> None:
	if frappe.db.exists("Promotional Scheme", name):
		frappe.delete_doc("Promotional Scheme", name, force=True, ignore_permissions=True)


def _delete_orphan_rules(title: str) -> None:
	"""Remove legacy standalone rules from older setup versions."""
	existing = frappe.db.get_value("Pricing Rule", {"title": title}, "name")
	if existing:
		frappe.delete_doc("Pricing Rule", existing, force=True, ignore_permissions=True)


def _scheme_pricing_rules(scheme_name: str) -> list[str]:
	return frappe.get_all(
		"Pricing Rule",
		filters={"promotional_scheme": scheme_name},
		pluck="name",
		order_by="creation asc",
	)


def _make_promotional_scheme(
	name: str,
	*,
	apply_on: str,
	promotion_type: str,
	item_codes: list[str] | None = None,
	price_slab: dict | None = None,
	product_slab: dict | None = None,
	priority: str = "1",
) -> dict:
	"""Create a Promotional Scheme; ERPNext auto-generates Pricing Rules on save."""
	_delete_scheme(name)
	_delete_orphan_rules(name)

	company = _resolve_company()
	currency = frappe.get_cached_value("Company", company, "default_currency")

	scheme = frappe.new_doc("Promotional Scheme")
	scheme.update(
		{
			"name": name,
			"company": company,
			"currency": currency,
			"apply_on": apply_on,
			"selling": 1,
			"buying": 0,
			"valid_from": nowdate(),
			"valid_upto": add_days(nowdate(), 365),
			"disable": 0,
			"pos_only": 1,
		}
	)
	if frappe.db.has_column("Promotional Scheme", "promotion_type"):
		scheme.promotion_type = promotion_type

	for item_code in item_codes or []:
		scheme.append("items", {"item_code": item_code, "uom": "Nos"})

	if price_slab:
		slab = scheme.append("price_discount_slabs", {})
		slab.rule_description = price_slab.get("rule_description") or name
		slab.min_qty = flt(price_slab.get("min_qty", 0))
		slab.max_qty = flt(price_slab.get("max_qty", 0))
		slab.min_amount = flt(price_slab.get("min_amt", 0))
		slab.max_amount = flt(price_slab.get("max_amt", 0))
		slab.rate_or_discount = price_slab.get("rate_or_discount", "Discount Percentage")
		if slab.rate_or_discount == "Discount Percentage":
			slab.discount_percentage = flt(price_slab.get("discount_percentage", 0))
		else:
			slab.discount_amount = flt(price_slab.get("discount_amount", 0))
		slab.priority = cstr(price_slab.get("priority") or priority)

	if product_slab:
		slab = scheme.append("product_discount_slabs", {})
		slab.rule_description = product_slab.get("rule_description") or name
		slab.min_qty = flt(product_slab.get("min_qty", 0))
		slab.max_qty = flt(product_slab.get("max_qty", 0))
		slab.min_amount = flt(product_slab.get("min_amt", 0))
		slab.max_amount = flt(product_slab.get("max_amt", 0))
		slab.free_item = product_slab.get("free_item")
		slab.free_qty = flt(product_slab.get("free_qty", 1))
		slab.free_item_uom = product_slab.get("free_item_uom") or "Nos"
		slab.same_item = cint(product_slab.get("same_item", 0))
		slab.priority = cstr(product_slab.get("priority") or priority)

	scheme.insert(ignore_permissions=True)

	return {
		"scheme": scheme.name,
		"pricing_rules": _scheme_pricing_rules(scheme.name),
	}


def _ensure_item_brand(item_code: str, brand: str) -> None:
	if not frappe.db.exists("Item", item_code):
		frappe.throw(f"Item {item_code} does not exist on this site.")
	if not frappe.db.exists("Brand", brand):
		frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)
	frappe.db.set_value("Item", item_code, "brand", brand, update_modified=False)


def _ensure_item_price(item_code: str, rate: float = 5000) -> None:
	price_list = "Standard Selling"
	if not frappe.db.exists("Price List", price_list):
		return
	filters = {"item_code": item_code, "price_list": price_list, "selling": 1}
	if frappe.db.exists("Item Price", filters):
		frappe.db.set_value("Item Price", filters, "price_list_rate", rate, update_modified=False)
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"selling": 1,
			}
		).insert(ignore_permissions=True)


def _ensure_pos_profiles_allow_pricing_rules(company: str) -> list[str]:
	"""POS profiles with ignore_pricing_rule=1 never load offers in POS."""
	updated = []
	profiles = frappe.get_all(
		"POS Profile",
		filters={"company": company, "disabled": 0, "ignore_pricing_rule": 1},
		pluck="name",
	)
	for profile_name in profiles:
		frappe.db.set_value("POS Profile", profile_name, "ignore_pricing_rule", 0, update_modified=False)
		updated.append(profile_name)
	return updated


def setup(item_code: str = MATRIX_ITEM, companion_item: str = MATRIX_COMPANION):
	"""Create Promotional Schemes + coupon for Promotion Interaction Matrix QA."""
	frappe.only_for("System Manager")

	if not frappe.db.exists("Item", item_code):
		frappe.throw(f"Item {item_code} not found. Create the item first or pass another item_code.")

	_ensure_item_brand(item_code, MATRIX_TEST_BRAND)
	_ensure_item_price(item_code)

	item_level = _make_promotional_scheme(
		SCHEME_ITEM_LEVEL,
		apply_on="Item Code",
		promotion_type="Item Level Discount",
		item_codes=[item_code],
		price_slab={
			"min_qty": 0,
			"min_amt": 0,
			"discount_percentage": 20,
			"priority": "3",
		},
	)

	auto_discount = _make_promotional_scheme(
		SCHEME_AUTO,
		apply_on="Transaction",
		promotion_type="Auto Discount",
		price_slab={
			"min_amt": 3000,
			"discount_percentage": 10,
			"priority": "2",
		},
	)

	gwp_product_slab = {
		"min_qty": 2,
		"free_qty": 1,
		"free_item_uom": "Nos",
		"priority": "1",
	}
	if frappe.db.exists("Item", MATRIX_FREE_ITEM):
		gwp_product_slab["free_item"] = MATRIX_FREE_ITEM

	gwp = _make_promotional_scheme(
		SCHEME_GWP,
		apply_on="Item Code",
		promotion_type="GWP",
		item_codes=[item_code],
		product_slab=gwp_product_slab,
	)

	if frappe.db.exists("POS Coupon", COUPON_NAME):
		frappe.delete_doc("POS Coupon", COUPON_NAME, force=True, ignore_permissions=True)
	if frappe.db.exists("POS Coupon", COMPANION_COUPON_NAME):
		frappe.delete_doc("POS Coupon", COMPANION_COUPON_NAME, force=True, ignore_permissions=True)

	company = _resolve_company()
	coupon = frappe.get_doc(
		{
			"doctype": "POS Coupon",
			"coupon_name": COUPON_NAME,
			"coupon_type": "Promotional",
			"coupon_code": MATRIX_COUPON_CODE,
			"discount_type": "Percentage",
			"discount_percentage": 10,
			"company": company,
			"apply_on": "Net Total",
			"apply_scope": "All Eligible Items",
			"exclude_already_discounted_items": 1,
			"excluded_brands": [{"brand": MATRIX_TEST_BRAND}],
			"description": "Matrix test: excludes brand MatrixTest (item 14214) and already-discounted lines",
		}
	)
	coupon.insert(ignore_permissions=True)

	companion_coupon = frappe.get_doc(
		{
			"doctype": "POS Coupon",
			"coupon_name": COMPANION_COUPON_NAME,
			"coupon_type": "Promotional",
			"coupon_code": MATRIX_COMPANION_COUPON_CODE,
			"discount_type": "Percentage",
			"discount_percentage": 10,
			"company": company,
			"apply_on": "Net Total",
			"apply_scope": "All Eligible Items",
			"exclude_already_discounted_items": 1,
			"excluded_brands": [],
			"description": f"Matrix test: use on normal eligible item {companion_item} (no brand exclusion)",
		}
	)
	companion_coupon.insert(ignore_permissions=True)

	profiles_fixed = _ensure_pos_profiles_allow_pricing_rules(company)

	frappe.db.commit()

	result = {
		"item_code": item_code,
		"companion_item": companion_item,
		"test_brand": MATRIX_TEST_BRAND,
		"schemes": {
			"item_level": item_level,
			"auto_discount": auto_discount,
			"gwp": gwp,
		},
		"coupon": {"name": coupon.name, "code": MATRIX_COUPON_CODE},
		"companion_coupon": {
			"name": companion_coupon.name,
			"code": MATRIX_COMPANION_COUPON_CODE,
		},
		"pos_profiles_fixed": profiles_fixed,
	}
	print_guide(result)
	return result


def teardown():
	"""Remove matrix test Promotional Schemes and coupon for item 14214."""
	frappe.only_for("System Manager")

	for name in (SCHEME_ITEM_LEVEL, SCHEME_AUTO, SCHEME_GWP):
		_delete_scheme(name)
		_delete_orphan_rules(name)

	if frappe.db.exists("POS Coupon", COUPON_NAME):
		frappe.delete_doc("POS Coupon", COUPON_NAME, force=True, ignore_permissions=True)
	if frappe.db.exists("POS Coupon", COMPANION_COUPON_NAME):
		frappe.delete_doc("POS Coupon", COMPANION_COUPON_NAME, force=True, ignore_permissions=True)

	frappe.db.commit()
	print("Removed matrix test Promotional Schemes for item 14214.")
	return True


def print_guide(result: dict | None = None):
	"""Print manual QA steps for the Promotion Interaction Matrix."""
	item = (result or {}).get("item_code") or MATRIX_ITEM
	companion = (result or {}).get("companion_item") or MATRIX_COMPANION
	schemes = (result or {}).get("schemes") or {}
	coupon = (result or {}).get("coupon") or {}
	companion_coupon = (result or {}).get("companion_coupon") or {}
	profiles_fixed = (result or {}).get("pos_profiles_fixed") or []

	def _scheme_line(key: str, default_name: str, description: str) -> str:
		entry = schemes.get(key) or {}
		scheme_name = entry.get("scheme") or default_name
		rules = ", ".join(entry.get("pricing_rules") or []) or "(auto-generated on save)"
		return f"  - {scheme_name} — {description}\n    Pricing Rules: {rules}"

	guide = f"""
Promotion Interaction Matrix — Manual QA for item {item}
======================================================

Promotional Schemes (visible in POS → Promotion Management):
{_scheme_line('item_level', SCHEME_ITEM_LEVEL, '20% Item Level Discount on ' + item)}
{_scheme_line('auto_discount', SCHEME_AUTO, '10% Auto Discount when cart >= 3000')}
{_scheme_line('gwp', SCHEME_GWP, 'Buy 2×' + item + ' get free gift')}

Coupon MATRIX10 — 10% off; **rejects item {item}** (brand "{MATRIX_TEST_BRAND}" excluded + already-discounted lines)
Coupon {companion_coupon.get('code', MATRIX_COMPANION_COUPON_CODE)} — 10% off; use on **{companion}** (normal eligible item)
{f"POS profiles updated (ignore_pricing_rule disabled): {', '.join(profiles_fixed)}" if profiles_fixed else ""}

Item {item} brand set to: {MATRIX_TEST_BRAND}
Companion item for mixed cart: {companion} (brand: Computers)

Matrix test scenarios
---------------------
| Scenario              | Cart setup                         | Expected                         |
|-----------------------|------------------------------------|----------------------------------|
| Already discounted    | {item} only (item-level rule on)   | Auto ❌ Coupon ❌ GWP ✅           |
| Excluded brand        | {item} + coupon {MATRIX_COUPON_CODE} | Coupon ❌ on {item}, Auto ✅      |
| Normal eligible       | {companion} only + coupon          | Auto ✅ Coupon ✅                  |
| GWP stacks            | 2×{item} + item-level on           | Free gift + 20% on {item}        |
| Auto + mixed cart     | {item} + {companion}, cart>=3000   | {item} no auto, {companion} 10%  |

Setup command:
  bench --site <site> execute pos_next.setup_matrix_promotions.setup

Run automated matrix tests:
  bench --site <site> run-tests --app pos_next --module pos_next.test_promotions
"""
	print(guide.strip())
	return guide
