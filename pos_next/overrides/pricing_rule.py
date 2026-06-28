# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Pricing Rule Override
Adds POS-only filtering to ERPNext's pricing rule conditions.

When a Pricing Rule has pos_only=1, it should only apply to POS transactions
(Sales Invoice with is_pos=1, or POS Invoice). Non-POS documents like
Quotations, Sales Orders, Delivery Notes, and regular Sales Invoices
will have these rules excluded from matching.

Min/Max Price Discounts
-----------------------
A Price-type Pricing Rule may set ``apply_discount_on_price`` to ``Min`` or
``Max`` so the discount lands only on the cheapest (Min) or most expensive
(Max) item(s) carrying that rule, capped by ``min_or_max_discount_qty_limit``.
ERPNext's per-item engine cannot rank items against each other, so we suppress
its application of these rules (``apply_price_discount_rule`` below) and apply
them in a single bulk pass (``apply_min_max_price_discounts``) instead.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	apply_price_discount_rule as _original_apply_price_discount_rule,
)
from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules

# Values of the ``apply_discount_on_price`` custom field that trigger ranking.
MIN_MAX_OPTIONS = ("Min", "Max")


def _has_pos_only_column():
	"""Check whether the current site's Pricing Rule table has the pos_only column.

	The monkey-patch in __init__.py is process-wide and affects ALL sites on the
	bench, but only sites with POS Next installed have the pos_only custom field.
	This guard prevents 'Unknown column' errors on sites that share the bench
	but don't have POS Next.

	Cached per-site per-worker so the DB introspection runs only once.
	"""
	if not hasattr(_has_pos_only_column, "_cache"):
		_has_pos_only_column._cache = {}

	site = getattr(frappe.local, "site", None)
	if site in _has_pos_only_column._cache:
		return _has_pos_only_column._cache[site]

	try:
		result = frappe.db.has_column("Pricing Rule", "pos_only")
	except Exception:
		result = False

	_has_pos_only_column._cache[site] = result
	return result


def sync_pos_only_to_pricing_rules(doc, method=None):
	"""Sync POS Next custom flags from Promotional Scheme to its generated Pricing Rules.

	Called via doc_events on_update hook, which runs after ERPNext's
	PromotionalScheme.on_update() has already created/updated the Pricing Rules.

	Propagates both ``pos_only`` and ``one_time_per_customer`` so a scheme acts as
	the single source of truth for the rules it generates.
	"""
	frappe.db.set_value(
		"Pricing Rule",
		{"promotional_scheme": doc.name},
		{
			"pos_only": doc.get("pos_only") or 0,
			"one_time_per_customer": doc.get("one_time_per_customer") or 0,
		},
		update_modified=False,
	)


def patch_get_other_conditions(pr_utils):
	"""Monkey-patch get_other_conditions to filter pos_only pricing rules.

	No Frappe hook exists for non-whitelisted module-level functions,
	so monkey-patching is the only option for this SQL condition injection.
	"""
	_original_get_other_conditions = pr_utils.get_other_conditions

	def _patched_get_other_conditions(conditions, values, args):
		conditions = _original_get_other_conditions(conditions, values, args)

		if not _has_pos_only_column():
			return conditions

		doctype = args.get("doctype", "")
		# POS Invoice doctype — always POS, all rules apply
		if doctype in ("POS Invoice", "POS Invoice Item"):
			pass
		# Sales Invoice — check is_pos flag
		elif doctype in ("Sales Invoice", "Sales Invoice Item"):
			if not args.get("is_pos"):
				conditions += " and ifnull(`tabPricing Rule`.pos_only, 0) = 0"
		# All other doctypes (Quotation, SO, DN, Purchase docs) — exclude POS-only
		else:
			conditions += " and ifnull(`tabPricing Rule`.pos_only, 0) = 0"

		return conditions

	pr_utils.get_other_conditions = _patched_get_other_conditions


# ---------------------------------------------------------------------------
# Min/Max price discounts
# ---------------------------------------------------------------------------


def enforce_min_max_pricing_config(doc, method=None):
	"""Validate-time guard for Min/Max price rules.

	A Min/Max ("cheapest / most expensive item") discount only makes sense when the
	engine evaluates the whole document together, so we force ``mixed_conditions``
	on (ERPNext otherwise gates each line independently and a one-of-each cart never
	qualifies). We also reject a non-positive quantity limit, which would mean
	"discount nothing".

	Wired as a ``validate`` doc_event for both **Promotional Scheme** (Min/Max lives
	on the price-discount slabs and the generated rules inherit ``mixed_conditions``)
	and **Pricing Rule** (standalone or scheme-generated).
	"""
	if doc.doctype == "Promotional Scheme":
		min_max_slabs = [
			slab
			for slab in (doc.get("price_discount_slabs") or [])
			if slab.get("apply_discount_on_price") in MIN_MAX_OPTIONS
		]
		if not min_max_slabs:
			return
		doc.mixed_conditions = 1
		for slab in min_max_slabs:
			if flt(slab.get("min_or_max_discount_qty_limit")) < 1:
				frappe.throw(
					_(
						"Set <b>Min/Max Discount Qty Limit</b> to at least 1 on the price "
						"discount row using <b>{0}</b> discount."
					).format(slab.get("apply_discount_on_price"))
				)
		return

	# Pricing Rule
	if doc.get("apply_discount_on_price") not in MIN_MAX_OPTIONS:
		return
	doc.mixed_conditions = 1
	if flt(doc.get("min_or_max_discount_qty_limit")) < 1:
		frappe.throw(
			_(
				"Set <b>Min/Max Discount Qty Limit</b> to at least 1 when "
				"<b>Apply Discount On</b> is <b>{0}</b>."
			).format(doc.get("apply_discount_on_price"))
		)


def apply_price_discount_rule(pricing_rule, item_details, args):
	"""Override of ERPNext's ``apply_price_discount_rule`` (installed via monkey-patch).

	For ``Min``/``Max`` rules we *defer* the discount: the per-item engine cannot
	know which items are the cheapest/most expensive across the whole cart, so we
	suppress application here and let :func:`apply_min_max_price_discounts` apply
	it later. We still mirror the original's bookkeeping (``pricing_rule_for`` and
	margin handling) so nothing else downstream changes.

	All non-Min/Max rules fall through to ERPNext's original implementation.
	"""
	if (pricing_rule.get("apply_discount_on_price") or "") in MIN_MAX_OPTIONS:
		# Keep parity with the original function's side effects.
		item_details.pricing_rule_for = pricing_rule.get("rate_or_discount")

		margin_type = pricing_rule.get("margin_type")
		if (
			margin_type in ["Amount", "Percentage"]
			and pricing_rule.get("currency") == args.get("currency")
		) or margin_type == "Percentage":
			item_details.margin_type = margin_type
			item_details.has_margin = True
			if (
				pricing_rule.get("apply_multiple_pricing_rules")
				and item_details.get("margin_rate_or_amount") is not None
			):
				item_details.margin_rate_or_amount += pricing_rule.get("margin_rate_or_amount")
			else:
				item_details.margin_rate_or_amount = pricing_rule.get("margin_rate_or_amount")

		# Return None: skip the standard discount application for this rule.
		return None

	return _original_apply_price_discount_rule(pricing_rule, item_details, args)


def apply_min_max_price_discounts(doc, method=None, allowed_rules=None):
	"""Apply ``Min``/``Max`` price rules across the whole cart.

	Used both as a ``doc_events`` ``validate`` hook (real documents) and from the
	POS ``apply_offers`` API (lightweight mock document). For each Min/Max rule it
	ranks the items carrying that rule by price and discounts only those within the
	configured quantity limit; items that do not qualify are left untouched so any
	discount applied by *other* rules survives.

	Limitation: on an item that *wins* the Min/Max ranking, the blended Min/Max
	percentage replaces (does not stack on top of) any discount another rule gave
	that same item. Combining ``apply_multiple_pricing_rules`` with Min/Max on the
	same item is therefore not supported.

	Args:
		doc: Document (or ``frappe._dict`` mock) exposing ``items`` and price-list info.
		method: Unused hook signature argument.
		allowed_rules: Optional iterable of rule names; when given, only those rules
			are applied (used by the POS UI to honour explicitly selected offers).
	"""
	try:
		rule_items, pricing_rules = _collect_min_max_rule_items(doc)
		if not rule_items:
			return

		doc_price_list = (
			doc.get("selling_price_list") or doc.get("buying_price_list") or doc.get("price_list")
		)

		for pr_name, items in rule_items.items():
			if allowed_rules is not None and pr_name not in allowed_rules:
				continue

			pr = pricing_rules.get(pr_name)
			if not pr:
				continue

			# A rule scoped to a specific price list must not bleed onto other lists.
			if pr.get("for_price_list") and pr.get("for_price_list") != doc_price_list:
				continue

			# Min => cheapest first (ascending); Max => most expensive first (descending).
			reverse = pr.get("apply_discount_on_price") == "Max"
			items.sort(key=lambda i: flt(i.get("price_list_rate")), reverse=reverse)

			# Number of units to discount among the ranked items. Empty/0 is
			# meaningless for a "cheapest/most-expensive item" discount, so it
			# defaults to a single unit (an unlimited limit would discount every
			# unit of every matching item, i.e. an ordinary discount).
			qty_limit = flt(pr.get("min_or_max_discount_qty_limit") or 0)
			if qty_limit <= 0:
				qty_limit = 1.0

			remaining_qty = qty_limit
			for item in items:
				if remaining_qty <= 0:
					break
				eligible_qty = min(_item_qty(item), remaining_qty)
				if eligible_qty <= 0:
					continue
				_apply_discount(pr, item, eligible_qty)
				remaining_qty -= eligible_qty

		# Real documents must recalculate: our validate hook runs *after* the
		# controller's calculate_taxes_and_totals(), so totals are stale until we
		# refresh them. The POS mock has no such method (values are materialised in
		# _apply_discount instead).
		if hasattr(doc, "calculate_taxes_and_totals") and callable(doc.calculate_taxes_and_totals):
			doc.calculate_taxes_and_totals()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Min/Max Pricing Rule Failed")
		if not frappe.flags.in_test:
			frappe.msgprint(
				_("Some Min/Max pricing rules could not be applied. Please review the cart discounts."),
				indicator="orange",
			)


def _apply_discount(pr, item, eligible_qty):
	"""Discount ``eligible_qty`` units of ``item`` under pricing rule ``pr``.

	We set *only* the blended ``discount_percentage`` (plus ``price_list_rate``)
	and let ERPNext's ``calculate_item_values`` derive ``rate``/``amount``/
	``discount_amount`` from it (taxes_and_totals.py). This keeps all the money
	math owned by core and identical across every document type. The same formula
	is materialised inline for the POS mock, which has no recalculation step.

	``price_list_rate`` (never the already-discounted ``rate``) is the basis, so
	re-running validate is idempotent rather than compounding.
	"""
	base_rate = flt(item.get("price_list_rate"))
	qty = _item_qty(item)
	if base_rate <= 0 or qty <= 0 or eligible_qty <= 0:
		return

	rate_or_discount = pr.get("rate_or_discount")
	if rate_or_discount == "Rate":
		total_discount = (base_rate - flt(pr.get("rate"))) * eligible_qty
	elif rate_or_discount == "Discount Percentage":
		total_discount = base_rate * flt(pr.get("discount_percentage")) / 100.0 * eligible_qty
	elif rate_or_discount == "Discount Amount":
		total_discount = flt(pr.get("discount_amount")) * eligible_qty
	else:
		return

	line_value = base_rate * qty
	# Clamp: never negative (e.g. a Rate higher than base) and never beyond the line.
	total_discount = min(max(total_discount, 0.0), line_value)
	if total_discount <= 0:
		return

	# Per-unit-equivalent percentage: reproduces the right line total even when
	# only part of the quantity is eligible (e.g. 4 units, limit 2).
	blended_pct = total_discount / line_value * 100.0

	item.price_list_rate = base_rate
	item.discount_percentage = blended_pct
	_materialize_rate(item, base_rate, blended_pct, qty)


def _materialize_rate(item, base_rate, discount_percentage, qty):
	"""Fill ``rate``/``amount``/``discount_amount`` using ERPNext's own formula.

	Mirrors ``calculate_item_values`` (taxes_and_totals.py): ``rate`` is
	``price_list_rate`` less the blended percentage and ``discount_amount`` is
	per-unit. Needed for the POS path (no recalc); harmless on real documents
	because ``calculate_taxes_and_totals`` recomputes the same values afterwards.
	"""
	precision = _rate_precision(item)
	rate = flt(base_rate * (1.0 - discount_percentage / 100.0), precision)
	item.rate = rate
	item.discount_amount = flt(base_rate - rate, precision)
	item.amount = flt(rate * qty, precision)


def _rate_precision(item):
	"""Best-effort currency precision for ``rate``; defaults to 2 for plain dicts."""
	getter = getattr(item, "precision", None)
	if callable(getter):
		try:
			return getter("rate") or 2
		except Exception:
			return 2
	return 2


def _item_qty(item):
	"""Quantity for an item, tolerating the POS payload's ``quantity`` alias."""
	return flt(item.get("qty") or item.get("quantity") or 0)


def _collect_min_max_rule_items(doc):
	"""Group cart items by the Min/Max Price rule(s) applied to them.

	Returns a tuple ``(rule_items, pricing_rules_cache)`` where ``rule_items`` maps
	a rule name to the list of items carrying it, and ``pricing_rules_cache`` caches
	the resolved Pricing Rule docs (``None`` for rules that are not Price-type
	Min/Max, so they are evaluated only once).
	"""
	rule_items = defaultdict(list)
	pricing_rules_cache = {}

	for item in doc.get("items") or []:
		if item.get("is_free_item") or _item_qty(item) <= 0 or not item.get("pricing_rules"):
			continue

		for pr_name in get_applied_pricing_rules(item.get("pricing_rules")):
			if pr_name not in pricing_rules_cache:
				pr = frappe.get_cached_doc("Pricing Rule", pr_name)
				if (
					pr.get("price_or_product_discount") == "Price"
					and pr.get("apply_discount_on_price") in MIN_MAX_OPTIONS
				):
					pricing_rules_cache[pr_name] = pr
				else:
					pricing_rules_cache[pr_name] = None

			if pricing_rules_cache[pr_name]:
				rule_items[pr_name].append(item)

	return rule_items, pricing_rules_cache
