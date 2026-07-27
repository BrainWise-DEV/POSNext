# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The POS discount pipeline — ordered, composable, idempotent.

``pos_next.api.invoices.apply_offers`` is the *only* engine that runs for a POS
cart. ``update_invoice`` sets ``ignore_pricing_rule = 1`` and clears every
line's ``pricing_rules`` before saving, so ERPNext never recomputes and whatever
this pipeline produces is what gets persisted. Non-POS documents are untouched
by this module: they go through ERPNext's own engine plus the Min/Max
``validate`` hook in :mod:`pos_next.overrides.pricing_rule`.

Why an accumulator
------------------
Each pass used to *assign* ``discount_percentage``, so whichever ran last won
and discounts could never combine. Passes here instead contribute a **named
percentage part** to each line:

    baseline (whatever ERPNext's per-item engine already produced)
      + part["auto_discount"]
      + part["accumulative"]        (added in a later stage)
      = discount_percentage

Parts are keyed by source, so a second contribution from the *same* pass
replaces its earlier value (matching how a single pass has always behaved)
while contributions from *different* passes sum. Every part is rebuilt from
scratch on each run, so running the pipeline twice over the same cart yields
the same numbers rather than compounding them.
"""

from __future__ import annotations

import frappe
from frappe.utils import cstr, flt

from pos_next.api.promotion_exclusions import (
	DISCOUNT_SOURCE_AUTO,
	PROMOTION_TARGET_AUTO,
	PROMOTION_TYPE_AUTO,
	PROMOTION_TYPE_ITEM_LEVEL,
	get_pre_discount_subtotal,
	get_rule_promotion_types,
	is_eligible_for_promotion,
	mark_item_discount_flags,
)
from pos_next.promotions.scope import (
	get_item_group_with_descendants,
	get_scope_config,
	get_scope_keys,
	item_matches_rule_scope,
)

# Named contributions. One key per pass.
PART_AUTO_DISCOUNT = "auto_discount"
PART_ACCUMULATIVE = "accumulative"

# Stashed on the line dict; stripped before the payload goes back to the client.
_BASE_ATTR = "_pos_discount_base"
_PARTS_ATTR = "_pos_discount_parts"
_CAP_ATTR = "_pos_discount_cap"

MIN_MAX_OPTIONS = ("Min", "Max")
ACCUMULATIVE_MODE = "Accumulative"

# Modes whose discount the per-item engine defers to a later pass. Re-deriving
# their percentage from the rule would double-apply it.
CROSS_CART_MODES = (*MIN_MAX_OPTIONS, ACCUMULATIVE_MODE)


# ---------------------------------------------------------------------------
# Per-line accumulator
# ---------------------------------------------------------------------------


def begin_line_discounts(items) -> None:
	"""Snapshot the engine-derived discount as the baseline and clear all parts.

	Called once before the passes run. The baseline is whatever ERPNext's
	per-item engine already wrote onto the line; passes add on top of it.
	"""
	for item in items or []:
		item[_BASE_ATTR] = flt(item.get("discount_percentage") or 0)
		item[_PARTS_ATTR] = {}
		item.pop(_CAP_ATTR, None)


def add_line_part(item, source: str, percentage) -> None:
	"""Record ``source``'s contribution to this line, replacing any earlier one."""
	parts = item.get(_PARTS_ATTR)
	if parts is None:
		parts = {}
		item[_PARTS_ATTR] = parts
	parts[source] = flt(percentage)


def get_line_parts(item) -> dict:
	return item.get(_PARTS_ATTR) or {}


def get_line_total_percentage(item) -> float:
	"""Baseline plus every recorded part, before clamping."""
	return flt(item.get(_BASE_ATTR) or 0) + sum(flt(v) for v in get_line_parts(item).values())


def finalize_line_discounts(items, cap_resolver=None) -> None:
	"""Materialise ``discount_percentage`` / ``discount_amount`` / ``rate``.

	Lines that received no contribution are left exactly as the earlier engine
	pass wrote them — this pipeline only owns lines it actually touched.

	``cap_resolver(item)`` may return a maximum percentage for a line (used from
	a later stage to honour the rule cap and ``Item.max_discount``); the default
	is a plain 0–100 clamp.
	"""
	for item in items or []:
		parts = get_line_parts(item)
		if not parts:
			_strip_pipeline_state(item)
			continue

		total = get_line_total_percentage(item)
		cap = 100.0
		if cap_resolver is not None:
			resolved = cap_resolver(item)
			if resolved is not None:
				cap = flt(resolved)

		total = max(0.0, min(total, cap, 100.0))
		_materialize_line(item, total)
		_strip_pipeline_state(item)


def _materialize_line(item, discount_percentage: float) -> None:
	"""Write the blended percentage back onto the line.

	``discount_amount`` is the **line** total (qty included), which is the
	convention the POS payload and ``apply_offers`` already use — note this
	differs from ``overrides.pricing_rule``, where it is per unit.
	"""
	qty = flt(item.get("qty") or item.get("quantity") or 0)
	price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
	if qty <= 0 or price_list_rate <= 0:
		return

	item.discount_percentage = discount_percentage
	item.discount_amount = price_list_rate * qty * discount_percentage / 100
	item.rate = price_list_rate * (1 - discount_percentage / 100)


def _strip_pipeline_state(item) -> None:
	"""Drop the bookkeeping keys so they never reach the API response."""
	item.pop(_BASE_ATTR, None)
	item.pop(_PARTS_ATTR, None)
	item.pop(_CAP_ATTR, None)


def set_line_cap(item, cap) -> None:
	"""Record a rule-level ceiling for this line; the lowest one set wins."""
	cap = flt(cap)
	if cap <= 0:
		return
	existing = flt(item.get(_CAP_ATTR) or 0)
	item[_CAP_ATTR] = min(existing, cap) if existing > 0 else cap


def default_cap_resolver(item):
	"""Ceiling for a line: the rule cap, further clamped by ``Item.max_discount``.

	Only applied to lines an Accumulative rule touched — plain Auto Discount
	lines keep their historical behaviour of ignoring ``Item.max_discount``.
	Returns ``None`` when nothing constrains the line.
	"""
	caps = []

	rule_cap = flt(item.get(_CAP_ATTR) or 0)
	if rule_cap > 0:
		caps.append(rule_cap)

	if PART_ACCUMULATIVE in get_line_parts(item):
		item_code = item.get("item_code")
		if item_code:
			max_discount = flt(frappe.get_cached_value("Item", item_code, "max_discount") or 0)
			if max_discount > 0:
				caps.append(max_discount)

	return min(caps) if caps else None


# ---------------------------------------------------------------------------
# Shared rule helpers
# ---------------------------------------------------------------------------


def rule_promotion_type(rule_details) -> str:
	if not rule_details:
		return ""
	if hasattr(rule_details, "get"):
		return cstr(rule_details.get("promotion_type") or "")
	return cstr(getattr(rule_details, "promotion_type", "") or "")


def append_pricing_rule(item, rule_name: str) -> None:
	"""Add a rule name to the line's comma-separated ``pricing_rules``."""
	existing = item.get("pricing_rules") or ""
	names = []
	if existing:
		if isinstance(existing, str):
			names = [part.strip() for part in existing.split(",") if part.strip()]
		elif isinstance(existing, list | tuple | set):
			names = [cstr(part) for part in existing if cstr(part)]
	if rule_name in names:
		return
	names.append(rule_name)
	item.pricing_rules = ",".join(names)


def pricing_rule_line_percentage(item, rule) -> float:
	"""The discount percentage ``rule`` grants this line, as a percentage of list price.

	Pure — it reads the line but never writes to it, so callers can route the
	result through the accumulator instead of clobbering ``discount_percentage``.
	"""
	qty = flt(item.get("qty") or item.get("quantity") or 0)
	price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
	if qty <= 0 or price_list_rate <= 0:
		return 0.0

	rate_or_discount = rule.get("rate_or_discount")

	if rate_or_discount == "Discount Percentage" and rule.get("discount_percentage"):
		return flt(rule.get("discount_percentage"))

	if rate_or_discount == "Discount Amount" and rule.get("discount_amount"):
		line_discount = flt(rule.get("discount_amount")) * qty
		return line_discount / (price_list_rate * qty) * 100

	if rate_or_discount == "Rate" and rule.get("rate"):
		# Express the target rate as a discount off list price, so the finalizer
		# lands exactly on rule.rate.
		target_rate = flt(rule.get("rate"))
		if target_rate >= price_list_rate:
			return 0.0
		return (price_list_rate - target_rate) / price_list_rate * 100

	return 0.0


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------


def apply_auto_discount_rules(items, rule_map, selected_offer_names=None, type_map=None) -> set:
	"""Auto Discount (promotion_type) rules, per eligible line.

	Lines already carrying an Item Level Discount or a manual cashier discount
	are skipped by the Promotion Interaction Matrix. Contributes to
	``PART_AUTO_DISCOUNT``; when several Auto Discount rules match one line the
	last one evaluated wins, which is the behaviour this pass has always had.
	"""
	if not items or not rule_map:
		return set()

	if type_map is None:
		type_map = get_rule_promotion_types(list(rule_map.keys()))

	mark_item_discount_flags(items, type_map)
	pre_subtotal = get_pre_discount_subtotal(items)
	applied = set()

	for rule_name, details in rule_map.items():
		if selected_offer_names and rule_name not in selected_offer_names:
			continue
		if rule_promotion_type(details) != PROMOTION_TYPE_AUTO:
			continue

		rule = frappe.get_cached_doc("Pricing Rule", rule_name)
		if rule.disable or rule.price_or_product_discount != "Price":
			continue
		if rule.get("apply_discount_on_price") in MIN_MAX_OPTIONS:
			continue

		min_amt = flt(rule.min_amt)
		if min_amt and pre_subtotal < min_amt:
			continue

		max_amt = flt(rule.max_amt)
		if max_amt and pre_subtotal > max_amt:
			continue

		# Expand the rule's scope once — item group rows resolve through the
		# nested set, which we don't want to repeat for every cart line.
		scope_keys = get_scope_keys(rule)

		rule_applied = False
		for item in items:
			if item.get("is_free_item") or not is_eligible_for_promotion(
				item, PROMOTION_TARGET_AUTO, rule_type_map=type_map
			):
				continue
			if not item_matches_rule_scope(item, rule, scope_keys=scope_keys):
				continue

			percentage = pricing_rule_line_percentage(item, rule)
			if percentage <= 0:
				continue

			add_line_part(item, PART_AUTO_DISCOUNT, percentage)
			append_pricing_rule(item, rule_name)
			item.discount_source = DISCOUNT_SOURCE_AUTO
			rule_applied = True

		if rule_applied:
			applied.add(rule_name)

	return applied


def get_accumulative_rule_names(rule_names) -> set[str]:
	"""Which of these Pricing Rules run in Accumulative mode."""
	names = [cstr(name) for name in (rule_names or []) if cstr(name)]
	if not names:
		return set()
	if not frappe.db.has_column("Pricing Rule", "apply_discount_on_price"):
		return set()

	return set(
		frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", names], "apply_discount_on_price": ACCUMULATIVE_MODE},
			pluck="name",
		)
	)


def build_matrix_type_map(rule_map) -> dict:
	"""Promotion types for the matrix, with Accumulative rules neutralised.

	An Accumulative rule carries ``promotion_type = "Item Level Discount"``, and
	ERPNext tags it onto the very lines it is meant to discount. Left as-is, the
	matrix would read those lines as already-discounted and the rule would lock
	itself out of its own scope. Accumulative lines get their own matrix state
	(``ITEM_STATE_ACCUMULATIVE``) once the pass flags them, so they do not need
	the item-level classification at all.
	"""
	if not rule_map:
		return {}

	type_map = get_rule_promotion_types(list(rule_map.keys()))
	accumulative = get_accumulative_rule_names(rule_map.keys())
	if not accumulative:
		return type_map

	return {
		name: ("" if name in accumulative and value == PROMOTION_TYPE_ITEM_LEVEL else value)
		for name, value in type_map.items()
	}


def _scope_row_keys(row_field: str, value: str) -> set[str]:
	"""Every cart value this scope row covers (item groups include descendants)."""
	if row_field == "item_group":
		return set(get_item_group_with_descendants(value))
	return {value}


def apply_accumulative_discount_rules(items, rule_map, selected_offer_names=None, type_map=None) -> set:
	"""Accumulative rules — sum the percentages of every scope row present in the cart.

	A rule lists scopes (item codes, item groups or brands) each carrying its own
	``pos_discount_percentage``. Every row represented in the cart contributes its
	percentage, and the **total** is applied uniformly to each eligible line, so a
	cart spanning more scopes earns a bigger discount on everything in it.

	A row only counts when a line that will actually *receive* the discount
	matches it. A line excluded by the Promotion Interaction Matrix (a manual
	cashier discount, or a different item-level promotion) therefore cannot
	inflate the total for everyone else.

	Contributes to ``PART_ACCUMULATIVE`` and flags the line so the matrix lets
	Auto Discount stack on top; the two percentages sum at finalize.
	"""
	if not items or not rule_map:
		return set()

	if type_map is None:
		type_map = get_rule_promotion_types(list(rule_map.keys()))

	pre_subtotal = get_pre_discount_subtotal(items)
	applied = set()

	for rule_name, details in rule_map.items():
		if selected_offer_names and rule_name not in selected_offer_names:
			continue

		rule = frappe.get_cached_doc("Pricing Rule", rule_name)
		if rule.get("apply_discount_on_price") != ACCUMULATIVE_MODE:
			continue
		if rule.disable or rule.price_or_product_discount != "Price":
			continue

		scope = get_scope_config(rule.get("apply_on"))
		if not scope:
			# Transaction scope has no per-row percentages to accumulate.
			continue
		table_field, row_field = scope

		min_amt = flt(rule.min_amt)
		if min_amt and pre_subtotal < min_amt:
			continue
		max_amt = flt(rule.max_amt)
		if max_amt and pre_subtotal > max_amt:
			continue

		eligible = [
			item
			for item in items
			if not item.get("is_free_item")
			and is_eligible_for_promotion(item, PROMOTION_TARGET_AUTO, rule_type_map=type_map)
			and item_matches_rule_scope(item, rule, scope_keys=get_scope_keys(rule))
		]
		if not eligible:
			continue

		total_percentage = 0.0
		scopes_present = 0
		for row in rule.get(table_field) or []:
			value = row.get(row_field)
			if not value:
				continue
			covered = _scope_row_keys(row_field, value)
			if not any(item.get(row_field) in covered for item in eligible):
				continue
			scopes_present += 1
			total_percentage += flt(row.get("pos_discount_percentage"))

		min_scopes = max(int(flt(rule.get("min_scopes_required") or 1)), 1)
		if scopes_present < min_scopes or total_percentage <= 0:
			continue

		rule_cap = flt(rule.get("max_accumulated_discount_percentage") or 0)
		for item in eligible:
			add_line_part(item, PART_ACCUMULATIVE, total_percentage)
			set_line_cap(item, rule_cap)
			item.is_accumulative_discount = 1
			append_pricing_rule(item, rule_name)

		applied.add(rule_name)

	return applied


def filter_auto_discount_from_header(txn_result, rule_map, selected_offer_names=None) -> dict:
	"""Strip header discount that came from Auto Discount transaction rules.

	Those rules are applied per line by :func:`apply_auto_discount_rules`
	instead, so leaving the header discount in place would double-count them.
	"""
	if not txn_result:
		return txn_result

	addl_pct = flt(txn_result.get("additional_discount_percentage") or 0)
	discount_amt = flt(txn_result.get("discount_amount") or 0)
	if not addl_pct and not discount_amt:
		return txn_result

	auto_txn_rules = []
	for rule_name, details in rule_map.items():
		if selected_offer_names and rule_name not in selected_offer_names:
			continue
		if rule_promotion_type(details) != PROMOTION_TYPE_AUTO:
			continue
		if details.get("price_or_product_discount") != "Price":
			continue
		if frappe.db.get_value("Pricing Rule", rule_name, "apply_on") == "Transaction":
			auto_txn_rules.append(rule_name)

	if not auto_txn_rules:
		return txn_result

	applied_rules = set(txn_result.get("applied_rules") or set())
	applied_rules -= set(auto_txn_rules)
	return {
		**txn_result,
		"applied_rules": applied_rules,
		"additional_discount_percentage": 0,
		"discount_amount": 0,
		"apply_discount_on": None,
	}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_line_discount_passes(items, rule_map, selected_offer_names=None, cap_resolver=None) -> set:
	"""Run every line-level discount pass in order and materialise the result.

	Order matters: Accumulative runs first so its lines are flagged before the
	Auto Discount pass consults the Promotion Interaction Matrix — that is what
	lets the two percentages stack rather than the second being turned away.

	Returns the set of Pricing Rule names that contributed. Min/Max rules are
	deliberately not handled here — they are deferred to a cross-cart ranking
	pass that runs afterwards (see :mod:`pos_next.overrides.pricing_rule`).
	"""
	if not items:
		return set()

	type_map = build_matrix_type_map(rule_map)

	begin_line_discounts(items)
	mark_item_discount_flags(items, type_map)

	applied = apply_accumulative_discount_rules(
		items, rule_map, selected_offer_names=selected_offer_names, type_map=type_map
	)
	applied |= apply_auto_discount_rules(
		items, rule_map, selected_offer_names=selected_offer_names, type_map=type_map
	)

	finalize_line_discounts(
		items, cap_resolver=cap_resolver if cap_resolver is not None else default_cap_resolver
	)

	mark_item_discount_flags(items, type_map)
	return applied
