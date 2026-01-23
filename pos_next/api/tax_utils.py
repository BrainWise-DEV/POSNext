# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Tax Utilities for POS Next

Centralized utility functions for tax handling to avoid code duplication.
"""

import frappe
from frappe.utils import cint, flt


def filter_rcm_taxes(doc):
	"""
	Filter out RCM (Reverse Charge Mechanism) taxes if is_reverse_charge is not set.
	
	RCM taxes should only be used when is_reverse_charge = 1.
	India Compliance validates this and throws error if RCM accounts are used without reverse charge.
	
	Args:
		doc: Sales Invoice document
		
	Returns:
		tuple: (filtered_taxes_list, rcm_taxes_removed_list)
	"""
	if not doc.get("taxes") or cint(doc.get("is_reverse_charge", 0)):
		return doc.get("taxes", []), []
	
	rcm_taxes_removed = []
	taxes_to_keep = []
	
	# Get list of RCM accounts if India Compliance is installed
	rcm_accounts = set()
	try:
		from india_compliance.gst_india.utils import get_gst_accounts_by_type
		sales_rcm_accounts = get_gst_accounts_by_type(
			doc.company, "Sales Reverse Charge", throw=False
		)
		if sales_rcm_accounts:
			rcm_accounts.update(sales_rcm_accounts.values())
	except Exception:
		# India Compliance not installed or error - use pattern matching
		pass
	
	# Filter taxes - remove RCM taxes
	for tax in doc.get("taxes", []):
		is_rcm = False
		
		# Check if account is in RCM accounts list (India Compliance method)
		if tax.account_head in rcm_accounts:
			is_rcm = True
		# Fallback: Check if account name contains "RCM" (pattern matching)
		elif "RCM" in (tax.account_head or "").upper():
			is_rcm = True
		
		if is_rcm:
			rcm_taxes_removed.append(tax.account_head)
		else:
			taxes_to_keep.append(tax)
	
	# Apply filtered taxes if any RCM taxes were removed
	if rcm_taxes_removed:
		doc.set("taxes", taxes_to_keep)
	
	return taxes_to_keep, rcm_taxes_removed


def ensure_taxes_loaded(doc):
	"""
	Ensure taxes are loaded from template if taxes_and_charges is set.
	
	Args:
		doc: Sales Invoice document
		
	Returns:
		bool: True if taxes were loaded, False otherwise
	"""
	if not doc.taxes_and_charges or doc.get("taxes"):
		return False
	
	try:
		doc.set_taxes()
		return True
	except Exception as e:
		frappe.log_error(f"Error loading taxes from template {doc.taxes_and_charges}: {str(e)}", "POS Tax Error")
		return False


def apply_tax_inclusive_settings(doc, tax_inclusive=None):
	"""
	Apply tax-inclusive settings to document.
	
	Sets included_in_print_rate = 1 on all applicable taxes and ensures
	item amounts are set before tax calculation.
	
	Args:
		doc: Sales Invoice document
		tax_inclusive: Boolean or None (will be determined from doc if None)
		
	Returns:
		bool: True if tax-inclusive mode is active and settings were applied
	"""
	# Determine tax-inclusive mode
	if tax_inclusive is None:
		tax_inclusive = 0
		if hasattr(doc, 'custom_is_this_tax_included_in_basic_rate'):
			tax_inclusive = cint(doc.custom_is_this_tax_included_in_basic_rate)
		
		# Fallback to POS Settings if custom field not set
		if not tax_inclusive and doc.pos_profile:
			try:
				pos_settings = frappe.db.get_value(
					"POS Settings",
					{"pos_profile": doc.pos_profile},
					["tax_inclusive"],
					as_dict=True
				)
				tax_inclusive = pos_settings.get("tax_inclusive", 0) if pos_settings else 0
			except Exception:
				tax_inclusive = 0
	
	if not tax_inclusive:
		return False
	
	# Ensure taxes are loaded
	if not doc.get("taxes") and doc.taxes_and_charges:
		ensure_taxes_loaded(doc)
	
	# Filter RCM taxes first
	filter_rcm_taxes(doc)
	
	# Set included_in_print_rate = 1 on all taxes (except Actual)
	for tax in doc.get("taxes", []):
		# Skip Actual charge type - these can't be inclusive
		if tax.charge_type == "Actual":
			if tax.included_in_print_rate:
				tax.included_in_print_rate = 0
			continue
		
		# MUST set to 1 for tax extraction to work
		if not tax.included_in_print_rate:
			tax.included_in_print_rate = 1
	
	# Ensure item amounts are set (tax-inclusive amounts)
	for item in doc.get("items", []):
		if not item.amount:
			item.amount = flt(item.rate or item.price_list_rate or 0) * flt(item.qty or 1)
		if not item.base_amount:
			item.base_amount = item.amount * flt(doc.conversion_rate or 1)
	
	return True


def calculate_taxes_if_needed(doc, force=False):
	"""
	Calculate taxes and totals if tax-inclusive mode is active.
	
	Args:
		doc: Sales Invoice document
		force: If True, calculate even if not tax-inclusive
		
	Returns:
		bool: True if calculation was performed
	"""
	if not force:
		tax_inclusive = apply_tax_inclusive_settings(doc)
		if not tax_inclusive:
			return False
	
	# Calculate taxes - this will extract tax from item rates in tax-inclusive mode
	doc.calculate_taxes_and_totals()
	
	return True
