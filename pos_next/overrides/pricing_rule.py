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
	"""Monkey-patch get_other_conditions to filter pricing rules.

	No Frappe hook exists for non-whitelisted module-level functions,
	so monkey-patching is the only option for this SQL condition injection.
	"""
	_original_get_other_conditions = pr_utils.get_other_conditions

	def _patched_get_other_conditions(conditions, values, args):
		conditions = _original_get_other_conditions(conditions, values, args)

		conditions = _add_pos_only_condition(conditions, values, args)
		conditions = _add_pos_profile_condition(conditions, values, args)

		return conditions

	pr_utils.get_other_conditions = _patched_get_other_conditions

def _add_pos_only_condition(conditions, values, args):
	"""Filter pos_only rules for non-POS documents."""
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


def _add_pos_profile_condition(conditions, values, args):
	"""Filter rules based on Promotion Scheme POS Profile restrictions."""
	pos_profile = args.get("pos_profile")
	if not pos_profile:
		return conditions

	# Include rule if:
	# 1. Rule has no promotional_scheme (standalone rule), OR
	# 2. Parent scheme has NO rows in Promotion Scheme POS Profile (apply to all), OR
	# 3. Current pos_profile IS in the scheme's POS Profile list
	conditions += """ AND (
		`tabPricing Rule`.promotional_scheme IS NULL
		OR `tabPricing Rule`.promotional_scheme = ''
		OR NOT EXISTS (
			SELECT 1 FROM `tabPromotion Scheme POS Profile`
			WHERE parent = `tabPricing Rule`.promotional_scheme
		)
		OR EXISTS (
			SELECT 1 FROM `tabPromotion Scheme POS Profile`
			WHERE parent = `tabPricing Rule`.promotional_scheme
			AND pos_profile = %(pos_profile)s
		)
	)"""
	values["pos_profile"] = pos_profile

	return conditions
