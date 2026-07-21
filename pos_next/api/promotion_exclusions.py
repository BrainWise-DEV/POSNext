# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Shared promotion exclusion helpers for POS Next.

Item-Level Discount (Type 4) and manual cashier discounts mark cart lines as
``already discounted``. Auto Discount (Type 3) and Coupon (Type 5) consult these
flags before applying additional discounts. GWP (Types 1–2) is unaffected.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import cstr, flt

PROMOTION_TYPE_ITEM_LEVEL = "Item Level Discount"
PROMOTION_TYPE_AUTO = "Auto Discount"
PROMOTION_TYPE_GWP = "GWP"

DISCOUNT_SOURCE_ITEM_LEVEL = "item_level_promotion"
DISCOUNT_SOURCE_MANUAL = "manual_discount"
DISCOUNT_SOURCE_AUTO = "auto_discount"
DISCOUNT_SOURCE_GWP = "gwp"
DISCOUNT_SOURCE_LEGACY = "pricing_rule"


def _parse_pricing_rules(value) -> list[str]:
	if not value:
		return []
	if isinstance(value, list | tuple | set):
		return [cstr(v) for v in value if cstr(v)]
	if isinstance(value, str):
		raw = value.strip()
		if not raw:
			return []
		if raw.startswith("["):
			try:
				parsed = json.loads(raw)
				if isinstance(parsed, list):
					return [cstr(v) for v in parsed if cstr(v)]
			except ValueError:
				pass
		return [part.strip() for part in raw.split(",") if part.strip()]
	return []


def get_rule_promotion_types(rule_names: list[str] | None) -> dict[str, str]:
	"""Return a map of pricing rule name -> promotion_type."""
	names = [cstr(name) for name in (rule_names or []) if cstr(name)]
	if not names:
		return {}

	if not frappe.db.has_column("Pricing Rule", "promotion_type"):
		return {name: "" for name in names}

	records = frappe.get_all(
		"Pricing Rule",
		filters={"name": ["in", names]},
		fields=["name", "promotion_type"],
	)
	return {record.name: cstr(record.promotion_type or "") for record in records}


def has_item_level_promotion_rule(item, rule_type_map: dict[str, str] | None = None) -> bool:
	rule_names = _parse_pricing_rules(item.get("pricing_rules"))
	if not rule_names:
		return False

	type_map = rule_type_map or get_rule_promotion_types(rule_names)
	return any(type_map.get(name) == PROMOTION_TYPE_ITEM_LEVEL for name in rule_names)


def has_manual_item_discount(item) -> bool:
	"""True when cashier applied a line discount not driven by pricing rules."""
	if item.get("discount_source") == DISCOUNT_SOURCE_MANUAL:
		return True

	if item.get("is_free_item"):
		return False

	has_rules = bool(_parse_pricing_rules(item.get("pricing_rules")))
	discount_pct = flt(item.get("discount_percentage"))
	discount_amt = flt(item.get("discount_amount"))

	return not has_rules and (discount_pct > 0 or discount_amt > 0)


def is_already_discounted(item, rule_type_map: dict[str, str] | None = None) -> bool:
	"""Whether the line should be excluded from Auto Discount and Coupon stacking."""
	if item.get("is_already_discounted"):
		return True
	if item.get("is_free_item"):
		return False
	if has_item_level_promotion_rule(item, rule_type_map):
		return True
	return has_manual_item_discount(item)


def get_line_net_amount(item) -> float:
	"""Net line amount after item-level discounts, before coupon/header discount."""
	qty = flt(item.get("qty") or item.get("quantity") or 0)
	if qty <= 0:
		return 0

	if item.get("amount") is not None and flt(item.get("amount")) >= 0:
		return flt(item.get("amount"))

	price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
	discount_pct = flt(item.get("discount_percentage"))
	discount_amt = flt(item.get("discount_amount"))

	base = price_list_rate * qty
	if discount_pct:
		return max(base - base * discount_pct / 100, 0)
	if discount_amt:
		return max(base - discount_amt, 0)
	return max(base, 0)


def get_pre_discount_subtotal(items) -> float:
	"""Cart subtotal using list prices before any line discounts."""
	total = 0
	for item in items or []:
		if item.get("is_free_item"):
			continue
		qty = flt(item.get("qty") or item.get("quantity") or 0)
		if qty <= 0:
			continue
		rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
		total += rate * qty
	return total


def filter_eligible_items(items, *, exclude_discounted: bool = True, rule_type_map: dict[str, str] | None = None):
	if not exclude_discounted:
		return list(items or [])
	return [item for item in (items or []) if not is_already_discounted(item, rule_type_map)]


def get_eligible_subtotal(items, *, exclude_discounted: bool = True, rule_type_map: dict[str, str] | None = None) -> float:
	eligible = filter_eligible_items(items, exclude_discounted=exclude_discounted, rule_type_map=rule_type_map)
	return sum(get_line_net_amount(item) for item in eligible)


def get_excluded_subtotal(items, *, rule_type_map: dict[str, str] | None = None) -> float:
	excluded = [item for item in (items or []) if is_already_discounted(item, rule_type_map)]
	return sum(get_line_net_amount(item) for item in excluded)


def mark_item_discount_flags(items, rule_type_map: dict[str, str] | None = None) -> None:
	"""Set is_already_discounted and discount_source on each cart line."""
	all_rule_names: list[str] = []
	for item in items or []:
		all_rule_names.extend(_parse_pricing_rules(item.get("pricing_rules")))

	type_map = rule_type_map or get_rule_promotion_types(list(set(all_rule_names)))

	for item in items or []:
		if item.get("is_free_item"):
			item.is_already_discounted = 0
			continue

		if has_item_level_promotion_rule(item, type_map):
			item.is_already_discounted = 1
			item.discount_source = DISCOUNT_SOURCE_ITEM_LEVEL
		elif has_manual_item_discount(item):
			item.is_already_discounted = 1
			item.discount_source = DISCOUNT_SOURCE_MANUAL
		else:
			item.is_already_discounted = 0
			if not item.get("discount_source"):
				if _parse_pricing_rules(item.get("pricing_rules")):
					applied_types = {
						type_map.get(name)
						for name in _parse_pricing_rules(item.get("pricing_rules"))
						if type_map.get(name)
					}
					if PROMOTION_TYPE_AUTO in applied_types:
						item.discount_source = DISCOUNT_SOURCE_AUTO
					elif PROMOTION_TYPE_GWP in applied_types:
						item.discount_source = DISCOUNT_SOURCE_GWP
					else:
						item.discount_source = DISCOUNT_SOURCE_LEGACY
