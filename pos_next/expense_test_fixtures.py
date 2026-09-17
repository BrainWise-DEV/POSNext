# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Shared fixtures for POS expense integration tests (T1 / T4).

Builds company / accounts / cost center / POS Profile without relying on
leftover records from an unrelated module run. Reuses the promotions helpers
for Mode of Payment wiring and the deterministic ``_PNXT_TEST_POS_PROFILE_*``
profile name.
"""

from types import SimpleNamespace

import frappe


def _ensure_test_company():
	"""Prefer ERPNext's ``_Test Company``; create it when the site has none."""
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"

	# Avoid colliding with an existing ``_TC`` abbreviation on another company.
	if frappe.db.exists("Company", {"abbr": "_TC"}):
		from pos_next.test_promotions import _resolve_company

		return _resolve_company()

	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test Company",
			"abbr": "_TC",
			"default_currency": "INR",
			"country": "India",
			"chart_of_accounts": "Standard",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def _ensure_cost_center(company):
	"""Return a leaf cost center for ``company``, creating ``Main`` if needed."""
	from pos_next.test_promotions import _resolve_cost_center

	existing = _resolve_cost_center(company)
	if existing:
		return existing

	abbr = frappe.get_cached_value("Company", company, "abbr")
	parent = frappe.db.get_value(
		"Cost Center",
		{"company": company, "is_group": 1},
		"name",
		order_by="lft asc",
	)
	cc = frappe.get_doc(
		{
			"doctype": "Cost Center",
			"cost_center_name": "Main",
			"company": company,
			"parent_cost_center": parent,
			"is_group": 0,
		}
	)
	cc.insert(ignore_permissions=True)
	# Prefer the Standard-chart name when present.
	main_name = f"Main - {abbr}"
	if frappe.db.exists("Cost Center", main_name):
		return main_name
	return cc.name


def _ensure_expense_account(company):
	"""Return ``Travel Expenses - {abbr}``, creating it under Indirect Expenses."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"Travel Expenses - {abbr}"
	if frappe.db.exists("Account", name):
		return name

	by_account_name = frappe.db.get_value(
		"Account",
		{"company": company, "account_name": "Travel Expenses", "is_group": 0},
		"name",
	)
	if by_account_name:
		return by_account_name

	parent = frappe.db.get_value(
		"Account",
		{"company": company, "account_name": "Indirect Expenses", "is_group": 1},
		"name",
	) or frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Expense", "is_group": 1},
		"name",
		order_by="lft asc",
	)
	if not parent:
		frappe.throw(f"No expense parent account for company {company}")

	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Travel Expenses",
			"parent_account": parent,
			"company": company,
			"is_group": 0,
		}
	)
	account.insert(ignore_permissions=True)
	return account.name


def ensure_pos_expense_fixtures():
	"""Create (or reuse) everything T1/T4 need and commit so tearDown rollbacks keep it.

	Returns a namespace with company, pos_profile, mode_of_payment, cost_center,
	expense_account, and payment_account.
	"""
	from pos_next.test_promotions import (
		_ensure_customer,
		_ensure_pos_profile,
		_resolve_mode_of_payment,
		_resolve_price_list,
		_resolve_warehouse,
	)

	company = _ensure_test_company()
	warehouse = _resolve_warehouse(company)
	price_list = _resolve_price_list(company)
	mode_of_payment = _resolve_mode_of_payment(company)
	_ensure_customer()
	# Profile only — skip promotion items/stock; expense tests do not need them.
	pos_profile = _ensure_pos_profile(company, warehouse, price_list, mode_of_payment)

	cost_center = _ensure_cost_center(company)
	expense_account = _ensure_expense_account(company)
	frappe.db.set_value("POS Profile", pos_profile, "cost_center", cost_center)

	payment_account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)

	frappe.db.commit()
	return SimpleNamespace(
		company=company,
		pos_profile=pos_profile,
		mode_of_payment=mode_of_payment,
		cost_center=cost_center,
		expense_account=expense_account,
		payment_account=payment_account,
	)
