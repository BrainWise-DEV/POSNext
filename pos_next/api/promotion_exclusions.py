# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Shared promotion exclusion helpers for POS Next.

Item-Level Discount (Type 4) and manual cashier discounts mark cart lines as
``already discounted``. Auto Discount (Type 3) and Coupon (Type 5) consult the
Promotion Interaction Matrix before applying additional discounts. GWP (Types 1–2)
is unaffected.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import cstr, flt

PROMOTION_TYPE_ITEM_LEVEL = "Item Level Discount"
PROMOTION_TYPE_AUTO = "Auto Discount"
PROMOTION_TYPE_GWP = "GWP"

PROMOTION_TARGET_GWP = "gwp"
PROMOTION_TARGET_AUTO = "auto_discount"
PROMOTION_TARGET_COUPON = "coupon"

ITEM_STATE_ALREADY_DISCOUNTED = "already_discounted"
ITEM_STATE_EXCLUDED_BRAND = "excluded_brand"
ITEM_STATE_ELIGIBLE = "eligible"
# An Item Level Discount running in Accumulative mode. Unlike a plain item-level
# promotion it is designed to stack with Auto Discount — the two percentages sum
# on the same line — while still shutting coupons out.
ITEM_STATE_ACCUMULATIVE = "accumulative"
# Phase 2 stubs — detection not wired yet
ITEM_STATE_XY_TRIGGER = "xy_trigger"
ITEM_STATE_ROUTINE_TRIGGER = "routine_trigger"

INTERACTION_MATRIX: dict[tuple[str, str], bool] = {
	(ITEM_STATE_ALREADY_DISCOUNTED, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_ALREADY_DISCOUNTED, PROMOTION_TARGET_AUTO): False,
	(ITEM_STATE_ALREADY_DISCOUNTED, PROMOTION_TARGET_COUPON): False,
	(ITEM_STATE_EXCLUDED_BRAND, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_EXCLUDED_BRAND, PROMOTION_TARGET_AUTO): True,
	(ITEM_STATE_EXCLUDED_BRAND, PROMOTION_TARGET_COUPON): False,
	(ITEM_STATE_ELIGIBLE, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_ELIGIBLE, PROMOTION_TARGET_AUTO): True,
	(ITEM_STATE_ELIGIBLE, PROMOTION_TARGET_COUPON): True,
	(ITEM_STATE_ACCUMULATIVE, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_ACCUMULATIVE, PROMOTION_TARGET_AUTO): True,
	(ITEM_STATE_ACCUMULATIVE, PROMOTION_TARGET_COUPON): False,
	# Phase 2 — XY / Routine trigger rows
	(ITEM_STATE_XY_TRIGGER, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_XY_TRIGGER, PROMOTION_TARGET_AUTO): False,
	(ITEM_STATE_XY_TRIGGER, PROMOTION_TARGET_COUPON): False,
	(ITEM_STATE_ROUTINE_TRIGGER, PROMOTION_TARGET_GWP): True,
	(ITEM_STATE_ROUTINE_TRIGGER, PROMOTION_TARGET_AUTO): False,
	(ITEM_STATE_ROUTINE_TRIGGER, PROMOTION_TARGET_COUPON): False,
}

DISCOUNT_SOURCE_ITEM_LEVEL = "item_level_promotion"
DISCOUNT_SOURCE_ACCUMULATIVE = "accumulative_promotion"
DISCOUNT_SOURCE_MANUAL = "manual_discount"
DISCOUNT_SOURCE_AUTO = "auto_discount"
DISCOUNT_SOURCE_GWP = "gwp"
DISCOUNT_SOURCE_FREE_ITEM = "free_item"
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


def is_accumulative_line(item) -> bool:
	"""Whether an Accumulative rule has claimed this line.

	Set by the accumulative pass in :mod:`pos_next.promotions.engine`, which runs
	before the Auto Discount pass so the flag is in place by the time the matrix
	is consulted.
	"""
	return bool(item.get("is_accumulative_discount"))


def is_already_discounted(item, rule_type_map: dict[str, str] | None = None) -> bool:
	"""Whether the line is excluded from Auto Discount (narrow Type 4 + manual)."""
	if is_accumulative_line(item):
		# Accumulative deliberately stacks with Auto Discount — see the matrix.
		return False
	if item.get("is_already_discounted"):
		return True
	if item.get("is_free_item"):
		return False
	if has_item_level_promotion_rule(item, rule_type_map):
		return True
	return has_manual_item_discount(item)


def is_coupon_broad_discounted(item, rule_type_map: dict[str, str] | None = None) -> bool:
	"""Broader discount detection for Coupon (includes auto-discount pricing rules)."""
	if is_accumulative_line(item):
		# Stacks with Auto Discount but never with a coupon.
		return True
	if is_already_discounted(item, rule_type_map):
		return True
	if item.get("is_free_item"):
		return False
	if flt(item.get("discount_percentage") or 0) > 0:
		return True
	if flt(item.get("discount_amount") or 0) > 0:
		return True
	if _parse_pricing_rules(item.get("pricing_rules")):
		return True
	price_list_rate = flt(item.get("price_list_rate") or 0)
	rate = flt(item.get("rate") or 0)
	if price_list_rate > 0 and rate > 0 and rate < price_list_rate:
		return True
	return False


def classify_item_state(
	item,
	*,
	rule_type_map: dict[str, str] | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
	target: str = PROMOTION_TARGET_AUTO,
	exclude_discounted: bool = True,
) -> str:
	"""Return the item's primary state for Promotion Interaction Matrix lookup."""
	if item.get("is_free_item"):
		return ITEM_STATE_ELIGIBLE

	# Checked before the discounted/brand states: an accumulative line is
	# discounted, but the matrix treats it differently from a plain one.
	if is_accumulative_line(item):
		return ITEM_STATE_ACCUMULATIVE

	brand_exclusions = excluded_brands or frozenset()

	if exclude_discounted:
		if target == PROMOTION_TARGET_COUPON:
			if is_coupon_broad_discounted(item, rule_type_map):
				return ITEM_STATE_ALREADY_DISCOUNTED
		elif is_already_discounted(item, rule_type_map):
			return ITEM_STATE_ALREADY_DISCOUNTED

	if target == PROMOTION_TARGET_COUPON:
		brand = item.get("brand")
		if brand and brand in brand_exclusions:
			return ITEM_STATE_EXCLUDED_BRAND

	return ITEM_STATE_ELIGIBLE


def is_eligible_for_promotion(
	item,
	target: str,
	*,
	rule_type_map: dict[str, str] | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
	exclude_discounted: bool = True,
) -> bool:
	"""Whether a cart line may receive the given promotion target per the matrix."""
	if item.get("is_free_item"):
		return False
	if target == PROMOTION_TARGET_GWP:
		return True

	state = classify_item_state(
		item,
		rule_type_map=rule_type_map,
		excluded_brands=excluded_brands,
		target=target,
		exclude_discounted=exclude_discounted,
	)
	return INTERACTION_MATRIX.get((state, target), True)


def filter_items_for_promotion(
	items,
	target: str,
	*,
	rule_type_map: dict[str, str] | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
	exclude_discounted: bool = True,
):
	return [
		item
		for item in (items or [])
		if is_eligible_for_promotion(
			item,
			target,
			rule_type_map=rule_type_map,
			excluded_brands=excluded_brands,
			exclude_discounted=exclude_discounted,
		)
	]


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


def filter_eligible_items(
	items,
	*,
	exclude_discounted: bool = True,
	rule_type_map: dict[str, str] | None = None,
	promotion_target: str | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
):
	if promotion_target:
		return filter_items_for_promotion(
			items,
			promotion_target,
			rule_type_map=rule_type_map,
			excluded_brands=excluded_brands,
			exclude_discounted=exclude_discounted,
		)
	if not exclude_discounted:
		return list(items or [])
	return [item for item in (items or []) if not is_already_discounted(item, rule_type_map)]


def get_eligible_subtotal(
	items,
	*,
	exclude_discounted: bool = True,
	rule_type_map: dict[str, str] | None = None,
	promotion_target: str | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
) -> float:
	eligible = filter_eligible_items(
		items,
		exclude_discounted=exclude_discounted,
		rule_type_map=rule_type_map,
		promotion_target=promotion_target,
		excluded_brands=excluded_brands,
	)
	return sum(get_line_net_amount(item) for item in eligible)


def get_excluded_subtotal(
	items,
	*,
	rule_type_map: dict[str, str] | None = None,
	promotion_target: str | None = None,
	excluded_brands: set[str] | frozenset[str] | None = None,
	exclude_discounted: bool = True,
) -> float:
	if promotion_target:
		eligible_keys = {
			id(item)
			for item in filter_items_for_promotion(
				items,
				promotion_target,
				rule_type_map=rule_type_map,
				excluded_brands=excluded_brands,
				exclude_discounted=exclude_discounted,
			)
		}
		excluded = [item for item in (items or []) if id(item) not in eligible_keys and not item.get("is_free_item")]
	else:
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

		# Preserve bundled free-item / GWP stamps so the POS cart can show
		# "N free items" instead of falling back to a derived "%".
		existing_source = item.get("discount_source")
		if existing_source in (DISCOUNT_SOURCE_FREE_ITEM, DISCOUNT_SOURCE_GWP):
			item.is_already_discounted = 1
			continue
		if flt(item.get("free_qty")) > 0:
			item.discount_source = DISCOUNT_SOURCE_FREE_ITEM
			item.is_already_discounted = 1
			continue
		if flt(item.get("gwp_free_qty")) > 0:
			item.discount_source = DISCOUNT_SOURCE_GWP
			item.is_already_discounted = 1
			continue

		if is_accumulative_line(item):
			# Discounted for reporting and for coupons, but the matrix still lets
			# Auto Discount through — see ITEM_STATE_ACCUMULATIVE.
			item.is_already_discounted = 1
			item.discount_source = DISCOUNT_SOURCE_ACCUMULATIVE
		elif has_item_level_promotion_rule(item, type_map):
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
