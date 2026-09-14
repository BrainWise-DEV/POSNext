# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Pricing Rule Override
Adds POS-only filtering to ERPNext's pricing rule conditions.

When a Pricing Rule has pos_only=1, it should only apply to POS transactions
(Sales Invoice with is_pos=1, or POS Invoice). Non-POS documents like
Quotations, Sales Orders, Delivery Notes, and regular Sales Invoices
will have these rules excluded from matching.
"""

import frappe


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


def set_batch_title(doc, method=None):
	"""Keep the Pricing Rule title in sync with its item/batch on every save.

	Item Code pricing rules created for POS Next (see custom_batch on
	Pricing Rule Item Code) are single-item, batch-specific rules, so the
	title is derived automatically ("Item Name - Item Code - Batch") instead
	of being hand-typed and left to drift whenever the item or batch changes.
	"""
	if doc.apply_on != "Item Code" or not doc.get("items"):
		return

	labels = []
	for row in doc.items:
		if not row.item_code:
			continue

		item_name = frappe.get_cached_value("Item", row.item_code, "item_name") or row.item_code
		label = f"{item_name} - {row.item_code}"
		if row.get("custom_batch"):
			label += f" - {row.custom_batch}"
		labels.append(label)

	if labels:
		doc.title = ", ".join(labels)


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


def _has_custom_batch_column():
	"""Check whether the current site's Pricing Rule Item Code table has the custom_batch column.

	Same rationale as ``_has_pos_only_column`` above: the monkey-patch is
	process-wide across the bench, but only sites with POS Next installed
	have this custom field.
	"""
	if not hasattr(_has_custom_batch_column, "_cache"):
		_has_custom_batch_column._cache = {}

	site = getattr(frappe.local, "site", None)
	if site in _has_custom_batch_column._cache:
		return _has_custom_batch_column._cache[site]

	try:
		result = frappe.db.has_column("Pricing Rule Item Code", "custom_batch")
	except Exception:
		result = False

	_has_custom_batch_column._cache[site] = result
	return result


def patch_get_pricing_rules_batch_filter(pr_utils):
	"""Monkey-patch _get_pricing_rules to filter Item Code rules by batch.

	When a Pricing Rule Item Code row has ``custom_batch`` set, that rule
	should only match transaction lines with the same batch_no. Rows with
	no custom_batch set stay universally applicable, so non-batch-specific
	pricing rules are unaffected.
	"""
	_original_get_pricing_rules = pr_utils._get_pricing_rules

	def _patched_get_pricing_rules(apply_on, args, values):
		pricing_rules = _original_get_pricing_rules(apply_on, args, values)

		if apply_on != "Item Code" or not args.get("batch_no") or not pricing_rules:
			return pricing_rules

		if not _has_custom_batch_column():
			return pricing_rules

		batch_map = {
			r.parent: r.custom_batch
			for r in frappe.get_all(
				"Pricing Rule Item Code",
				filters={
					"parent": ["in", [pr.name for pr in pricing_rules]],
					"item_code": args.get("item_code"),
				},
				fields=["parent", "custom_batch"],
			)
		}

		return [
			pr
			for pr in pricing_rules
			if not batch_map.get(pr.name) or batch_map.get(pr.name) == args.get("batch_no")
		]

	pr_utils._get_pricing_rules = _patched_get_pricing_rules


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
