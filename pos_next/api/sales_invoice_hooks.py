# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Sales Invoice Hooks
Event handlers for Sales Invoice document events
"""

import frappe
from frappe import _
from frappe.utils import flt


def validate(doc, method=None):
	"""
	Validate hook for Sales Invoice.
	Apply tax inclusive settings based on POS Profile configuration.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	if not doc.pos_profile:
		return
	
	from pos_next.api.tax_utils import apply_tax_inclusive_settings, calculate_taxes_if_needed
	
	# Apply tax-inclusive settings (filters RCM, sets included_in_print_rate, ensures item amounts)
	if apply_tax_inclusive_settings(doc):
		# Calculate taxes if tax-inclusive mode is active
		calculate_taxes_if_needed(doc, force=True)
		
		# Warn if taxes are still 0 after calculation
		if doc.get("taxes"):
			total_tax = sum(flt(tax.tax_amount or 0) for tax in doc.get("taxes", []))
			if total_tax == 0:
				frappe.log_error(
					f"WARNING: Tax-inclusive mode but tax amount is 0 after calculation. "
					f"Invoice: {doc.name if hasattr(doc, 'name') else 'NEW'}",
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
	if not doc.pos_profile:
		return
	
	from pos_next.api.tax_utils import apply_tax_inclusive_settings, calculate_taxes_if_needed
	
	# Apply tax-inclusive settings (filters RCM, sets included_in_print_rate, ensures item amounts)
	# This is the final safeguard before save
	if apply_tax_inclusive_settings(doc):
		# Calculate taxes if tax-inclusive mode is active
		calculate_taxes_if_needed(doc, force=True)
		
		# Final check - if taxes are still 0, log error
		if doc.get("taxes"):
			total_tax = sum(flt(tax.tax_amount or 0) for tax in doc.get("taxes", []))
			if total_tax == 0:
				frappe.log_error(
					f"ERROR: Tax-inclusive mode but tax amount is 0 after calculation! "
					f"Invoice: {doc.name if hasattr(doc, 'name') else 'NEW'}",
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
