# Copyright (c) 2026, BrainWise and contributors
"""Shared test fixtures: tests create what they need instead of skipping."""

import frappe


def ensure_pos_profile(name):
	"""Return the POS Profile `name`, creating it from the site's company data if missing."""
	if frappe.db.exists("POS Profile", name):
		return name
	from pos_next import test_promotions as tp

	company = tp._resolve_company()
	tp._ensure_customer()
	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": name,
			"company": company,
			"warehouse": tp._resolve_warehouse(company),
			"selling_price_list": tp._resolve_price_list(company),
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"customer": tp.CUSTOMER,
			"write_off_account": frappe.get_cached_value("Company", company, "write_off_account"),
			"write_off_cost_center": tp._resolve_cost_center(company),
			"disabled": 0,
		}
	)
	profile.append(
		"payments", {"mode_of_payment": tp._resolve_mode_of_payment(company), "default": 1, "amount": 0}
	)
	profile.insert(ignore_permissions=True)
	return name
