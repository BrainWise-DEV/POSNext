# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Sales Invoice Hooks
Event handlers for Sales Invoice document events
"""

import frappe
from frappe import _
from frappe.utils import cint


def validate(doc, method=None):
	"""
	Validate hook for Sales Invoice.
	Apply tax inclusive settings based on POS Profile configuration.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	apply_tax_inclusive(doc)


def apply_tax_inclusive(doc):
	"""
	Mark taxes as inclusive based on POS Profile setting.

	This function reads the tax_inclusive setting from POS Settings
	and applies it to all taxes in the invoice (except Actual charge type).
	Also checks the custom field from frontend as a fallback.

	This replicates ERPNext's behavior for tax-inclusive mode in POS.

	Args:
		doc: Sales Invoice document
	"""
	if not doc.pos_profile:
		return

	# First check custom field (from frontend), then POS Settings
	tax_inclusive = 0
	if hasattr(doc, 'custom_is_this_tax_included_in_basic_rate'):
		tax_inclusive = cint(doc.custom_is_this_tax_included_in_basic_rate)
	
	# Fallback to POS Settings if custom field not set
	if not tax_inclusive:
		try:
			# Get POS Settings for this profile
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
		return

	# Ensure taxes are loaded from template if not already loaded
	# This is critical - taxes must be loaded before we can set included_in_print_rate
	if not doc.get("taxes") and doc.taxes_and_charges:
		try:
			doc.set_taxes()
			frappe.log_error(f"Loaded taxes from template: {doc.taxes_and_charges}", "POS Tax Debug")
		except Exception as e:
			frappe.log_error(f"Error loading taxes: {str(e)}", "POS Tax Error")
	
	# CRITICAL: Filter out RCM (Reverse Charge Mechanism) taxes if is_reverse_charge is not set
	# This prevents India Compliance validation error: "Cannot use Reverse Charge Account"
	if doc.get("taxes") and not cint(doc.get("is_reverse_charge", 0)):
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
		
		if rcm_taxes_removed:
			doc.set("taxes", taxes_to_keep)
			frappe.log_error(
				f"validate hook: Filtered out {len(rcm_taxes_removed)} RCM taxes: {rcm_taxes_removed}",
				"POS Tax Debug"
			)

	# Set included_in_print_rate = 1 on all taxes (except Actual)
	has_changes = False
	taxes_before = [(t.account_head, t.included_in_print_rate) for t in doc.get("taxes", [])]
	
	for tax in doc.get("taxes", []):
		# Skip Actual charge type - these can't be inclusive
		if tax.charge_type == "Actual":
			if tax.included_in_print_rate:
				tax.included_in_print_rate = 0
				has_changes = True
			continue

		# Apply tax inclusive setting - MUST be 1 for tax extraction to work
		if not tax.included_in_print_rate:
			tax.included_in_print_rate = 1
			has_changes = True

	taxes_after = [(t.account_head, t.included_in_print_rate) for t in doc.get("taxes", [])]
	if has_changes:
		frappe.log_error(
			f"Set included_in_print_rate=1. Before: {taxes_before}, After: {taxes_after}",
			"POS Tax Debug"
		)

	# ALWAYS recalculate in tax-inclusive mode, even if no changes
	# This ensures taxes are extracted from item rates
	# ERPNext's calculate_taxes_and_totals() will:
	# 1. Calculate item amounts from tax-inclusive rates
	# 2. Extract tax from item amounts using determine_exclusive_rate()
	# 3. Calculate net amounts and tax amounts
	if tax_inclusive:
		# Ensure item amounts are set before calculation
		from frappe.utils import flt
		for item in doc.get("items", []):
			if not item.amount:
				item.amount = flt(item.rate or item.price_list_rate or 0) * flt(item.qty or 1)
			if not item.base_amount:
				item.base_amount = item.amount * flt(doc.conversion_rate or 1)
		
		# Log before calculation
		items_before = [(i.item_code, i.rate, i.amount) for i in doc.get("items", [])]
		frappe.log_error(
			f"Before calculate_taxes_and_totals - Items: {items_before}, Taxes: {taxes_after}",
			"POS Tax Debug"
		)
		
		# Calculate taxes - this will extract tax from item rates
		# This is the EXACT same logic ERPNext uses for tax-inclusive mode
		doc.calculate_taxes_and_totals()
		
		# Log after calculation
		taxes_after_calc = [(t.account_head, t.rate, t.included_in_print_rate, t.tax_amount) for t in doc.get("taxes", [])]
		total_tax = sum(flt(tax.tax_amount or 0) for tax in doc.get("taxes", []))
		frappe.log_error(
			f"After calculate_taxes_and_totals - Total Tax: {total_tax}, Taxes: {taxes_after_calc}",
			"POS Tax Debug"
		)
		
		# Warn if taxes are still 0
		if total_tax == 0:
			frappe.log_error(
				f"WARNING: Tax-inclusive mode but tax amount is 0 after calculation. "
				f"Invoice: {doc.name if hasattr(doc, 'name') else 'NEW'}, "
				f"Items: {items_before}, "
				f"Taxes: {taxes_after_calc}",
				"POS Tax Inclusive Warning"
			)


def before_save(doc, method=None):
	"""
	Before Save hook for Sales Invoice.
	This runs AFTER validate() and ensures taxes are calculated correctly.
	
	This is critical because set_missing_values() might be called during save,
	which could reload taxes from template and reset included_in_print_rate.
	
	This is the FINAL opportunity to set taxes correctly before save.
	
	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	# Only apply if this is a POS invoice with tax-inclusive mode
	if not doc.pos_profile:
		return
	
	# Check if tax-inclusive mode is enabled
	tax_inclusive = 0
	if hasattr(doc, 'custom_is_this_tax_included_in_basic_rate'):
		tax_inclusive = cint(doc.custom_is_this_tax_included_in_basic_rate)
	
	if not tax_inclusive:
		return
	
	# CRITICAL: Ensure taxes are loaded from template
	# This must happen FIRST
	if not doc.get("taxes") and doc.taxes_and_charges:
		try:
			doc.set_taxes()
			frappe.log_error(f"before_save: Loaded taxes from template {doc.taxes_and_charges}", "POS Tax Debug")
		except Exception as e:
			frappe.log_error(f"before_save: Error loading taxes: {str(e)}", "POS Tax Error")
	
	# CRITICAL: Filter out RCM (Reverse Charge Mechanism) taxes if is_reverse_charge is not set
	# This prevents India Compliance validation error: "Cannot use Reverse Charge Account"
	# RCM taxes should only be used when is_reverse_charge = 1
	if doc.get("taxes") and not cint(doc.get("is_reverse_charge", 0)):
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
		
		if rcm_taxes_removed:
			doc.set("taxes", taxes_to_keep)
			frappe.log_error(
				f"before_save hook: Filtered out {len(rcm_taxes_removed)} RCM taxes: {rcm_taxes_removed}",
				"POS Tax Debug"
			)
	
	# CRITICAL: Set included_in_print_rate = 1 on ALL taxes (except Actual)
	# This is REQUIRED for determine_exclusive_rate() to work
	# Without this, taxes will NOT be extracted from item rates
	has_changes = False
	taxes_before = [(t.account_head, t.included_in_print_rate, t.tax_amount) for t in doc.get("taxes", [])]
	
	for tax in doc.get("taxes", []):
		# Skip Actual charge type - these can't be inclusive
		if tax.charge_type == "Actual":
			if tax.included_in_print_rate:
				tax.included_in_print_rate = 0
				has_changes = True
			continue
		
		# MUST set to 1 - this is the KEY requirement
		if not tax.included_in_print_rate:
			tax.included_in_print_rate = 1
			has_changes = True
	
	taxes_after_set = [(t.account_head, t.included_in_print_rate) for t in doc.get("taxes", [])]
	if has_changes:
		frappe.log_error(
			f"before_save: Set included_in_print_rate=1. Before: {taxes_before}, After: {taxes_after_set}",
			"POS Tax Debug"
		)
	
	# CRITICAL: Ensure item amounts are set (tax-inclusive amounts)
	# This is REQUIRED for calculate_taxes_and_totals() to work
	from frappe.utils import flt
	items_before = [(i.item_code, i.rate, i.amount) for i in doc.get("items", [])]
	
	for item in doc.get("items", []):
		# Item rate is tax-inclusive (from frontend: 84000)
		# Calculate amount = rate * qty
		if not item.amount:
			item.amount = flt(item.rate or item.price_list_rate or 0) * flt(item.qty or 1)
		if not item.base_amount:
			item.base_amount = item.amount * flt(doc.conversion_rate or 1)
	
	# CRITICAL: Call calculate_taxes_and_totals()
	# This will:
	# 1. Call determine_exclusive_rate() which checks if any tax has included_in_print_rate = 1
	# 2. If yes, extract tax from item.amount: net_amount = amount / (1 + tax_fraction)
	# 3. Calculate tax_amount = amount - net_amount
	# 4. Set tax.tax_amount on each tax row
	doc.calculate_taxes_and_totals()
	
	# Verify taxes were calculated
	taxes_after_calc = [(t.account_head, t.rate, t.included_in_print_rate, t.tax_amount) for t in doc.get("taxes", [])]
	total_tax = sum(flt(tax.tax_amount or 0) for tax in doc.get("taxes", []))
	
	frappe.log_error(
		f"before_save: After calculate_taxes_and_totals - Total Tax: {total_tax}, "
		f"Items: {items_before}, Taxes: {taxes_after_calc}",
		"POS Tax Debug"
	)
	
	# Final check - if taxes are still 0, something is wrong
	if total_tax == 0 and tax_inclusive:
		frappe.log_error(
			f"ERROR: Tax-inclusive mode but tax amount is 0 after calculation! "
			f"Invoice: {doc.name if hasattr(doc, 'name') else 'NEW'}, "
			f"Items: {items_before}, "
			f"Taxes before: {taxes_before}, "
			f"Taxes after: {taxes_after_calc}",
			"POS Tax Calculation Error"
		)


def before_cancel(doc, method=None):
	"""
	Before Cancel hook for Sales Invoice.
	Cancel any credit redemption journal entries.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	try:
		from pos_next.api.credit_sales import cancel_credit_journal_entries
		cancel_credit_journal_entries(doc.name)
	except Exception as e:
		frappe.log_error(
			title="Credit Sale JE Cancellation Error",
			message=f"Invoice: {doc.name}, Error: {str(e)}\n{frappe.get_traceback()}"
		)
		# Don't block invoice cancellation if JE cancellation fails
		frappe.msgprint(
			_("Warning: Some credit journal entries may not have been cancelled. Please check manually."),
			alert=True,
			indicator="orange"
		)
