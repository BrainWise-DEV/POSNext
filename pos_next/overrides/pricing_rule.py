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
``Max`` so the discount lands only on the single cheapest (Min) or most
expensive (Max) line carrying that rule. ``min_or_max_discount_qty_limit`` caps
how many units of that one line are discounted (``0`` = every unit of the line).
ERPNext's per-item engine cannot rank items against each other, so we suppress
its application of these rules (``apply_price_discount_rule`` below) and apply
them in a single bulk pass (``apply_min_max_price_discounts``) instead.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, flt

from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	apply_price_discount_rule as _original_apply_price_discount_rule,
)
from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules

from pos_next.promotions.scope import (
	APPLY_ON_CHILD_DOCTYPE,
	SCOPE_PERCENTAGE_FIELD,
	get_scope_config,
)

# Values of the ``apply_discount_on_price`` custom field that trigger ranking.
MIN_MAX_OPTIONS = ("Min", "Max")

# Sums per-scope percentages across the cart instead of ranking lines. Applied by
# pos_next.promotions.engine during apply_offers, not by this module.
ACCUMULATIVE_MODE = "Accumulative"

# Every cross-cart mode the ``apply_discount_on_price`` field can hold.
CROSS_CART_MODES = (*MIN_MAX_OPTIONS, ACCUMULATIVE_MODE)

PROMOTION_TYPE_ITEM_LEVEL = "Item Level Discount"


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


def sync_promotion_fields_to_pricing_rules(doc, method=None):
	"""Sync POS Next custom flags from Promotional Scheme to its generated Pricing Rules.

	Called via doc_events on_update hook, which runs after ERPNext's
	PromotionalScheme.on_update() has already created/updated the Pricing Rules.

	Propagates ``pos_only``, ``one_time_per_customer``, and ``promotion_type`` so a
	scheme acts as the single source of truth for the rules it generates.
	Also syncs GWP slab field ``gwp_paid_qty_basis``.
	"""
	values = {
		"pos_only": doc.get("pos_only") or 0,
		"one_time_per_customer": doc.get("one_time_per_customer") or 0,
	}
	if frappe.db.has_column("Pricing Rule", "promotion_type"):
		values["promotion_type"] = doc.get("promotion_type") or ""

	frappe.db.set_value(
		"Pricing Rule",
		{"promotional_scheme": doc.name},
		values,
		update_modified=False,
	)

	sync_scope_percentages_to_pricing_rules(doc)

	# GWP rules discount the purchased line(s), so same_item must stay 1.
	# Non-GWP product discounts must keep the slab's same_item / free_item as configured.
	if frappe.db.has_column("Pricing Rule", "gwp_paid_qty_basis"):
		from pos_next.api.gwp import GWP_BASIS_MAX

		is_gwp = doc.get("promotion_type") == "GWP"
		for slab in doc.get("product_discount_slabs") or []:
			values = {
				"gwp_paid_qty_basis": slab.get("gwp_paid_qty_basis") or GWP_BASIS_MAX,
			}
			if is_gwp:
				values["same_item"] = 1
			frappe.db.set_value(
				"Pricing Rule",
				{"promotional_scheme_id": slab.name},
				values,
				update_modified=False,
			)


def sync_scope_percentages_to_pricing_rules(doc):
	"""Copy per-scope ``pos_discount_percentage`` rows from Scheme to its Pricing Rules.

	ERPNext rebuilds each rule's scope table with
	``pr.append(field, {apply_on: d.get(apply_on), "uom": d.uom})``
	(promotional_scheme.py), so custom columns on those rows are dropped every
	time the scheme is saved. We re-apply them here, matching rows by their scope
	value, which is unique within a rule.
	"""
	scope = get_scope_config(doc.get("apply_on"))
	if not scope:
		return

	table_field, row_field = scope
	child_doctype = APPLY_ON_CHILD_DOCTYPE[doc.get("apply_on")]

	if not frappe.db.has_column(child_doctype, SCOPE_PERCENTAGE_FIELD):
		return

	percentages = {
		row.get(row_field): flt(row.get(SCOPE_PERCENTAGE_FIELD))
		for row in (doc.get(table_field) or [])
		if row.get(row_field)
	}
	if not any(percentages.values()):
		return

	rule_names = frappe.get_all("Pricing Rule", filters={"promotional_scheme": doc.name}, pluck="name")
	if not rule_names:
		return

	for row in frappe.get_all(
		child_doctype,
		filters={"parent": ["in", rule_names], "parenttype": "Pricing Rule"},
		fields=["name", row_field],
	):
		percentage = percentages.get(row.get(row_field))
		if percentage is None:
			continue
		frappe.db.set_value(
			child_doctype, row.name, SCOPE_PERCENTAGE_FIELD, percentage, update_modified=False
		)


# Backwards-compatible alias for any external references.
sync_pos_only_to_pricing_rules = sync_promotion_fields_to_pricing_rules


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


def validate_unique_promotion_type_per_item(doc, method=None):
	"""Block duplicate promotion_type for the same item on active Promotional Schemes."""
	if doc.doctype != "Promotional Scheme":
		return
	if doc.get("disable"):
		return
	if not frappe.db.has_column("Promotional Scheme", "promotion_type"):
		return

	promotion_type = (doc.get("promotion_type") or "").strip()
	if not promotion_type:
		return
	if doc.get("apply_on") != "Item Code":
		return

	item_codes = list({row.item_code for row in (doc.get("items") or []) if row.get("item_code")})
	if not item_codes:
		return

	scheme = frappe.qb.DocType("Promotional Scheme")
	item_table = frappe.qb.DocType("Pricing Rule Item Code")

	query = (
		frappe.qb.from_(scheme)
		.join(item_table)
		.on(item_table.parent == scheme.name)
		.select(scheme.name, item_table.item_code)
		.where(scheme.disable == 0)
		.where(scheme.promotion_type == promotion_type)
		.where(scheme.company == doc.company)
		.where(scheme.apply_on == "Item Code")
		.where(item_table.item_code.isin(item_codes))
	)

	if doc.name and not doc.is_new():
		query = query.where(scheme.name != doc.name)

	conflicts = query.run(as_dict=True)
	if not conflicts:
		return

	seen = set()
	lines = []
	for row in conflicts:
		key = (row.item_code, row.name)
		if key in seen:
			continue
		seen.add(key)
		lines.append(
			_("{0} already has promotion type {1} in scheme {2}").format(
				frappe.bold(row.item_code),
				frappe.bold(promotion_type),
				frappe.bold(row.name),
			)
		)

	frappe.throw(
		_("A promotion with the same type already exists for the following item(s):<br><br>")
		+ "<br>".join(lines),
		title=_("Duplicate Promotion"),
	)


# Slab fields an Accumulative scheme authors on the parent instead. Parent
# fieldname -> slab fieldname (they differ for the amount pair).
ACCUMULATIVE_PARENT_TO_SLAB = {
	"min_qty": "min_qty",
	"max_qty": "max_qty",
	"min_amount": "min_amount",
	"max_amount": "max_amount",
	"max_accumulated_discount_percentage": "max_accumulated_discount_percentage",
	"min_scopes_required": "min_scopes_required",
}


def normalize_accumulative_scheme(doc, method=None):
	"""Derive the canonical price discount slab from the parent's accumulative config.

	``pos_is_accumulative`` is an *authoring* control only. ``apply_discount_on_price``
	on the generated Pricing Rule stays the single source of truth for the engine,
	the offer payload and the interaction matrix — this function projects the
	checkbox onto it. Running on every ``validate`` means the two can never drift,
	and a scheme created through the API, a fixture or ``create_promotion`` ends up
	exactly as correct as one built in the form.

	ERPNext generates Pricing Rules *from the slabs* (``get_pricing_rules`` skips an
	empty child table), so a hidden slab table must still contain a row or the
	scheme would save clean and silently discount nothing.

	Wired to ``before_validate``: ERPNext's own ``PromotionalScheme.validate()``
	rejects a scheme with no discount slabs, and that class method runs ahead of
	every hooked ``validate``, so the row must already exist by then.
	"""
	if doc.doctype != "Promotional Scheme":
		return
	if not frappe.db.has_column("Promotional Scheme", "pos_is_accumulative"):
		return
	if not doc.get("pos_is_accumulative"):
		return

	slab = _resolve_accumulative_slab(doc)

	# Injected because each value is *true* for this mode, not to dodge validation:
	# it is a price discount, expressed as a percentage, whose percentage lives on
	# the scope rows. rule_description is the slab's only mandatory field.
	slab.apply_discount_on_price = ACCUMULATIVE_MODE
	slab.rate_or_discount = "Discount Percentage"
	slab.rate = 0
	slab.discount_amount = 0
	slab.discount_percentage = 0
	if not slab.get("rule_description"):
		slab.rule_description = _("Accumulative discount")

	for parent_field, slab_field in ACCUMULATIVE_PARENT_TO_SLAB.items():
		slab.set(slab_field, doc.get(parent_field) or 0)

	if flt(slab.min_scopes_required) < 1:
		slab.min_scopes_required = 1

	doc.mixed_conditions = 1
	doc.pos_only = 1
	if not doc.get("promotion_type"):
		doc.promotion_type = PROMOTION_TYPE_ITEM_LEVEL


def _resolve_accumulative_slab(doc):
	"""The one price discount row an Accumulative scheme owns, created if absent.

	Kept to exactly one row: several would generate several identical Pricing
	Rules, which ERPNext then reports as a MultiplePricingRuleConflict at the till.
	"""
	slabs = doc.get("price_discount_slabs") or []

	conflicting = [s for s in slabs if s.get("apply_discount_on_price") in MIN_MAX_OPTIONS]
	if conflicting:
		frappe.throw(
			_(
				"A scheme cannot be <b>Accumulative</b> and use a <b>Min/Max</b> discount at "
				"the same time. Remove the Min/Max price discount row, or clear "
				"<b>Accumulative Discount</b>."
			),
			title=_("Conflicting Discount Modes"),
		)

	if len(slabs) > 1:
		frappe.throw(
			_(
				"An <b>Accumulative</b> scheme uses a single price discount row, but this "
				"scheme has {0}. Remove the extra rows — the qty and amount limits are set "
				"on the scheme itself."
			).format(len(slabs)),
			title=_("Too Many Price Discount Rows"),
		)

	if slabs:
		return slabs[0]

	return doc.append("price_discount_slabs", {})


def enforce_cross_cart_pricing_config(doc, method=None):
	"""Validate-time guard for every cross-cart price mode.

	All of them (``Min``, ``Max``, ``Accumulative``) need the engine to evaluate
	the whole document together, so ``mixed_conditions`` is forced on — ERPNext
	otherwise gates each line independently and a one-of-each cart never
	qualifies.

	Wired as a ``validate`` doc_event for both **Promotional Scheme** (the mode
	lives on the price-discount slabs and the generated rules inherit
	``mixed_conditions``) and **Pricing Rule** (standalone or scheme-generated).
	"""
	if doc.doctype == "Promotional Scheme":
		slabs = [
			slab
			for slab in (doc.get("price_discount_slabs") or [])
			if slab.get("apply_discount_on_price") in CROSS_CART_MODES
		]
		if slabs:
			doc.mixed_conditions = 1
			for slab in slabs:
				mode = slab.get("apply_discount_on_price")
				if mode in MIN_MAX_OPTIONS:
					_validate_min_max_qty_limit(slab.get("min_or_max_discount_qty_limit"), mode, on_slab=True)
				else:
					_validate_accumulative_slab(slab)

			if any(s.get("apply_discount_on_price") == ACCUMULATIVE_MODE for s in slabs):
				_validate_accumulative_scope(doc)
				doc.pos_only = 1

		many_items_gwp = (
			doc.get("apply_on") == "Item Group"
			or (doc.get("apply_on") == "Item Code" and len(doc.get("items") or []) > 1)
		) and doc.get("promotion_type") == "GWP" and (doc.get("product_discount_slabs") or [])
		if many_items_gwp:
			doc.mixed_conditions = 1
		return

	# Pricing Rule
	mode = doc.get("apply_discount_on_price")
	if mode not in CROSS_CART_MODES:
		return

	doc.mixed_conditions = 1
	if mode in MIN_MAX_OPTIONS:
		_validate_min_max_qty_limit(doc.get("min_or_max_discount_qty_limit"), mode, on_slab=False)
		return

	_validate_accumulative_slab(doc)

	# Scope is validated on the *source* only. A scheme-generated rule is a
	# derived artifact: ERPNext rebuilds its scope table from the scheme with
	# only {value, uom}, dropping the percentages, and it saves the rule during
	# the scheme's own on_update — before sync_scope_percentages_to_pricing_rules
	# can put them back. Re-checking the copy here would reject every valid
	# accumulative scheme. The scheme itself was already validated at its save.
	if not doc.get("promotional_scheme"):
		_validate_accumulative_scope(doc)

	doc.pos_only = 1


# Kept so any external reference to the old name keeps working.
enforce_min_max_pricing_config = enforce_cross_cart_pricing_config


def _validate_min_max_qty_limit(value, mode, on_slab):
	if flt(value) >= 0:
		return
	if on_slab:
		frappe.throw(
			_(
				"<b>Min/Max Discount Qty Limit</b> cannot be negative on the price "
				"discount row using <b>{0}</b> discount. Use 0 for no limit."
			).format(mode)
		)
	frappe.throw(
		_(
			"<b>Min/Max Discount Qty Limit</b> cannot be negative when "
			"<b>Apply Discount On</b> is <b>{0}</b>. Use 0 for no limit."
		).format(mode)
	)


def _validate_accumulative_slab(source):
	"""Numeric config guards for an Accumulative slab / rule."""
	if flt(source.get("max_accumulated_discount_percentage")) < 0:
		frappe.throw(
			_("<b>Max Accumulated Discount %</b> cannot be negative. Use 0 for no rule-level cap.")
		)
	if flt(source.get("min_scopes_required")) < 0:
		frappe.throw(_("<b>Min Scopes Required</b> cannot be negative."))


def _validate_accumulative_scope(doc):
	"""Scope guards shared by Promotional Scheme and Pricing Rule.

	An Accumulative discount sums a percentage per scope row, so it needs a
	child-table scope (Item Code / Item Group / Brand) carrying at least one
	positive percentage. ``Transaction`` has no rows to accumulate over.
	"""
	scope = get_scope_config(doc.get("apply_on"))
	if not scope:
		frappe.throw(
			_(
				"<b>Accumulative</b> discounts need <b>Apply On</b> set to "
				"Item Code, Item Group or Brand — there is nothing to accumulate "
				"over on a Transaction rule."
			)
		)

	table_field, row_field = scope
	rows = doc.get(table_field) or []
	if not rows:
		frappe.throw(
			_("Add at least one <b>{0}</b> row before using an <b>Accumulative</b> discount.").format(
				doc.get("apply_on")
			)
		)

	percentages = [flt(row.get(SCOPE_PERCENTAGE_FIELD)) for row in rows]
	if any(p < 0 for p in percentages):
		frappe.throw(_("<b>Discount %</b> on a scope row cannot be negative."))
	if not any(p > 0 for p in percentages):
		frappe.throw(
			_(
				"Set <b>Discount %</b> on at least one <b>{0}</b> row - an "
				"<b>Accumulative</b> discount sums those percentages."
			).format(doc.get("apply_on"))
		)

	promotion_type = cstr(doc.get("promotion_type") or "").strip()
	if promotion_type and promotion_type != PROMOTION_TYPE_ITEM_LEVEL:
		frappe.throw(
			_(
				"<b>Accumulative</b> discounts must use promotion type "
				"<b>{0}</b>, not <b>{1}</b>."
			).format(PROMOTION_TYPE_ITEM_LEVEL, promotion_type)
		)


def apply_price_discount_rule(pricing_rule, item_details, args):
	"""Override of ERPNext's ``apply_price_discount_rule`` (installed via monkey-patch).

	Every cross-cart mode *defers* its discount, because the per-item engine cannot
	make the decision on its own:

	- ``Min`` / ``Max`` — it cannot rank items against each other, so the discount
	  is applied later by :func:`apply_min_max_price_discounts`.
	- ``Accumulative`` — the percentage comes from the scope rows present across the
	  whole cart, not from the rule's own ``discount_percentage``. Letting ERPNext
	  apply that field here would stack it underneath the accumulated total (a rule
	  with 10% and rows of 5% + 3% produced 18% instead of 8%). The real percentage
	  is applied by ``pos_next.promotions.engine``.

	We still mirror the original's bookkeeping (``pricing_rule_for`` and margin
	handling) so nothing else downstream changes. All other rules fall through to
	ERPNext's original implementation.
	"""
	if (pricing_rule.get("apply_discount_on_price") or "") in CROSS_CART_MODES:
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
	ranks the items carrying that rule by price, picks the single cheapest (Min) /
	most expensive (Max) line and discounts up to ``min_or_max_discount_qty_limit``
	units of it (``0`` = every unit of that line). It never spills onto the next
	item, and every other item is left untouched so discounts applied by *other*
	rules survive.

	Limitation: on the line that *wins* the Min/Max ranking, the blended Min/Max
	percentage replaces (does not stack on top of) any discount another rule gave
	that same line. Combining ``apply_multiple_pricing_rules`` with Min/Max on the
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

			# The discount targets only the single cheapest (Min; only a negative limit is rejected.) / most expensive
			# (Max) line — we never spill onto the next-ranked item. The qty limit
			# caps how many units of that one line are discounted:
			#   limit > 0  => up to ``limit`` units (rest of the line pays full price);
			#   limit == 0 => every unit of that line (unlimited).
			target = items[0]
			target_qty = _item_qty(target)
			qty_limit = flt(pr.get("min_or_max_discount_qty_limit") or 0)
			eligible_qty = target_qty if qty_limit <= 0 else min(qty_limit, target_qty)
			if eligible_qty > 0:
				_apply_discount(pr, target, eligible_qty)

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
