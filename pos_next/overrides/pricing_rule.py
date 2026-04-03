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


def sync_pos_only_to_pricing_rules(doc, method=None):
	"""Sync pos_only from Promotional Scheme to its generated Pricing Rules.

	Called via doc_events on_update hook, which runs after ERPNext's
	PromotionalScheme.on_update() has already created/updated the Pricing Rules.
	"""
	pos_only = doc.get("pos_only") or 0
	frappe.db.set_value(
		"Pricing Rule",
		{"promotional_scheme": doc.name},
		"pos_only",
		pos_only,
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
