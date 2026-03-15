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
	"""Monkey-patch get_other_conditions to filter pricing rules.

	No Frappe hook exists for non-whitelisted module-level functions,
	so monkey-patching is the only option for this SQL condition injection.
	"""
	_original_get_other_conditions = pr_utils.get_other_conditions

	def _patched_get_other_conditions(conditions, values, args):
		conditions = _original_get_other_conditions(conditions, values, args)

		conditions = _add_pos_only_condition(conditions, values, args)
		conditions = _add_pos_profile_condition(conditions, values, args)
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
	"""Filter rules based on Promotion Scheme POS Profile restrictions.
	
	Optimized to avoid correlated subqueries by pre-filtering promotional schemes
	and using IN clauses. Uses request-level caching to avoid re-querying for
	each item in the same request.
	"""
	pos_profile = args.get("pos_profile")
	if not pos_profile:
		return conditions

	# Cache key for request-level caching
	cache_key = f"_pos_profile_schemes_{pos_profile}"
	
	# Check if we've already computed this for this request
	if not hasattr(frappe.local, cache_key):
		# Pre-query: Get all promotional schemes that have POS Profile restrictions
		# (schemes with any rows in the child table)
		restricted_schemes = frappe.db.sql_list("""
			SELECT DISTINCT parent
			FROM `tabPromotion Scheme POS Profile`
		""")
		
		# Pre-query: Get all promotional schemes that allow this specific pos_profile
		allowed_schemes = frappe.db.sql_list("""
			SELECT DISTINCT parent
			FROM `tabPromotion Scheme POS Profile`
			WHERE pos_profile = %s
		""", (pos_profile,))
		
		# Store in request cache
		frappe.local[cache_key] = {
			"restricted": set(restricted_schemes) if restricted_schemes else set(),
			"allowed": set(allowed_schemes) if allowed_schemes else set()
		}
	
	scheme_data = frappe.local[cache_key]
	restricted_schemes = scheme_data["restricted"]
	allowed_schemes = scheme_data["allowed"]
	
	# Build condition using IN clauses instead of correlated subqueries
	# Include rule if:
	# 1. Rule has no promotional_scheme (standalone rule), OR
	# 2. Parent scheme has NO rows in Promotion Scheme POS Profile (apply to all), OR
	# 3. Current pos_profile IS in the scheme's POS Profile list
	if not restricted_schemes:
		# No schemes have restrictions, so all promotional schemes apply
		# No additional filtering needed beyond NULL/empty check (which is already handled)
		# This means all rules are included, so we don't need to add any condition
		pass
	else:
		# Build IN clause for allowed schemes
		if allowed_schemes:
			allowed_list = list(allowed_schemes)
			conditions += """ AND (
				`tabPricing Rule`.promotional_scheme IS NULL
				OR `tabPricing Rule`.promotional_scheme = ''
				OR `tabPricing Rule`.promotional_scheme NOT IN %(restricted_schemes)s
				OR `tabPricing Rule`.promotional_scheme IN %(allowed_schemes)s
			)"""
			values["restricted_schemes"] = list(restricted_schemes)
			values["allowed_schemes"] = allowed_list
		else:
			# No schemes allow this pos_profile, so exclude all restricted schemes
			conditions += """ AND (
				`tabPricing Rule`.promotional_scheme IS NULL
				OR `tabPricing Rule`.promotional_scheme = ''
				OR `tabPricing Rule`.promotional_scheme NOT IN %(restricted_schemes)s
			)"""
			values["restricted_schemes"] = list(restricted_schemes)

	return conditions
