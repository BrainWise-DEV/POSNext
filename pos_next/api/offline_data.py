"""
POS Next — Offline cache bootstrap endpoints.

These whitelisted methods return reference data (taxes, UOMs, loyalty
programs) that the frontend caches in IndexedDB so the POS keeps working
when the network is down. They are intended for *bulk* offline seeding,
not ad-hoc lookups.
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_taxes(pos_profile=None, company=None):
	"""Return Sales Taxes and Charges Templates relevant to a POS Profile.

	Each row includes the full child-table breakdown so the frontend can
	apply taxes offline without another round-trip.

	Args:
		pos_profile: Filter to the company of this profile. Optional.
		company: Override company filter. Optional.

	Returns:
		list[dict]: ``[{name, title, company, disabled, is_default, taxes: [...]}]``
	"""
	resolved_company = company
	if pos_profile and not resolved_company:
		resolved_company = frappe.get_cached_value("POS Profile", pos_profile, "company")

	filters = {"disabled": 0}
	if resolved_company:
		filters["company"] = resolved_company

	templates = frappe.get_all(
		"Sales Taxes and Charges Template",
		filters=filters,
		fields=["name", "title", "company", "disabled", "is_default"],
		order_by="is_default desc, title asc",
	)

	if not templates:
		return []

	template_names = [row.name for row in templates]
	rows = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": ["in", template_names], "parenttype": "Sales Taxes and Charges Template"},
		fields=[
			"parent",
			"idx",
			"charge_type",
			"row_id",
			"account_head",
			"description",
			"included_in_print_rate",
			"included_in_paid_amount",
			"cost_center",
			"rate",
			"account_currency",
		],
		order_by="parent asc, idx asc",
	)

	rows_by_parent = {}
	for r in rows:
		rows_by_parent.setdefault(r.parent, []).append(r)

	return [
		{
			**tpl,
			"taxes": rows_by_parent.get(tpl.name, []),
		}
		for tpl in templates
	]


@frappe.whitelist()
def get_uoms():
	"""Return all enabled UOMs for offline UOM dropdowns and conversions."""
	return frappe.get_all(
		"UOM",
		filters={"enabled": 1},
		fields=["name", "uom_name", "must_be_whole_number"],
		order_by="uom_name asc",
		limit=0,
	)


@frappe.whitelist()
def get_loyalty_programs(company=None):
	"""Return loyalty programs (and their tier rules) for offline display.

	Args:
		company: Filter by company. Optional.

	Returns:
		list[dict]: Loyalty programs with collection rules and tiers.
	"""
	filters = {}
	if company:
		filters["company"] = company

	# Frappe Loyalty Program may not have `disabled` consistently — use a
	# safer cached doc fetch per program, but list-step keeps it cheap.
	programs = frappe.get_all(
		"Loyalty Program",
		filters=filters,
		fields=[
			"name",
			"loyalty_program_name",
			"loyalty_program_type",
			"customer_group",
			"customer_territory",
			"company",
			"from_date",
			"to_date",
			"expiry_duration",
			"conversion_factor",
			"expense_account",
			"cost_center",
			"auto_opt_in",
		],
		limit=0,
	)
	if not programs:
		return []

	program_names = [p.name for p in programs]

	collection_rules = frappe.get_all(
		"Loyalty Program Collection",
		filters={"parent": ["in", program_names]},
		fields=[
			"parent",
			"idx",
			"tier_name",
			"collection_factor",
			"min_spent",
		],
		order_by="parent asc, idx asc",
	)

	rules_by_parent = {}
	for r in collection_rules:
		rules_by_parent.setdefault(r.parent, []).append(r)

	return [
		{
			**p,
			"collection_rules": rules_by_parent.get(p.name, []),
		}
		for p in programs
	]


@frappe.whitelist()
def get_offline_bundle(pos_profile, company=None):
	"""One-shot endpoint that returns taxes + UOMs + loyalty in a single call.

	Lets the frontend seed offline reference data with one round-trip
	on shift start, instead of three.
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	resolved_company = company or frappe.get_cached_value(
		"POS Profile", pos_profile, "company"
	)

	return {
		"taxes": get_taxes(pos_profile=pos_profile, company=resolved_company),
		"uoms": get_uoms(),
		"loyalty_programs": get_loyalty_programs(company=resolved_company),
	}
