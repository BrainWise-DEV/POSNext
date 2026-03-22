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
	Auto-assign loyalty program to customer if enabled.
	Ensure POS invoices are linked to an opening shift.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	if not doc.is_pos or not doc.pos_profile:
		return

	validate_pos_opening_shift(doc)

	# Fetch POS Settings once for all downstream validations
	pos_settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": doc.pos_profile},
		["tax_inclusive", "enable_loyalty_program", "default_loyalty_program"],
		as_dict=True,
	) or {}

	apply_tax_inclusive(doc, pos_settings)
	auto_assign_loyalty_program_on_invoice(doc, pos_settings)


def validate_pos_opening_shift(doc):
	"""
	Ensure POS invoices are linked to a POS Opening Shift.
	This is a backstop for invoices created via desk or any path
	that bypasses the POS Next frontend/API guards.

	If an opening shift is missing, attempt to auto-resolve from the
	user's current open shift. If no open shift exists, block submission.

	Args:
		doc: Sales Invoice document
	"""
	if not doc.is_pos or not doc.pos_profile:
		return

	if doc.get("posa_pos_opening_shift"):
		return

	# Auto-resolve: find user's current open shift for this profile
	open_shift = frappe.db.get_value(
		"POS Opening Shift",
		{
			"user": doc.owner,
			"pos_profile": doc.pos_profile,
			"pos_closing_shift": ["is", "not set"],
			"docstatus": 1,
			"status": "Open",
		},
		"name",
		order_by="period_start_date desc",
	)

	if open_shift:
		doc.posa_pos_opening_shift = open_shift
		frappe.msgprint(
			_("POS Opening Shift was missing. Auto-linked to {0}.").format(open_shift),
			alert=True,
			indicator="orange",
		)
	else:
		frappe.throw(
			_("This POS invoice is not linked to any POS Opening Shift and no active shift was found "
			  "for user {0} on profile {1}. "
			  "Please open a shift before creating POS invoices.").format(doc.owner, doc.pos_profile),
			title=_("Missing POS Opening Shift"),
		)


def apply_tax_inclusive(doc, pos_settings=None):
	"""
	Mark taxes as inclusive based on POS Profile setting.

	This function reads the tax_inclusive setting from POS Settings
	and applies it to all taxes in the invoice (except Actual charge type).

	Args:
		doc: Sales Invoice document
		pos_settings: Pre-fetched POS Settings dict (avoids redundant DB query)
	"""
	if not doc.pos_profile:
		return

	tax_inclusive = cint(pos_settings.get("tax_inclusive")) if pos_settings else 0

	has_changes = False
	for tax in doc.get("taxes", []):
		# Skip Actual charge type - these can't be inclusive
		if tax.charge_type == "Actual":
			if tax.included_in_print_rate:
				tax.included_in_print_rate = 0
				has_changes = True
			continue

		# Apply tax inclusive setting
		if tax_inclusive and not tax.included_in_print_rate:
			tax.included_in_print_rate = 1
			has_changes = True
		elif not tax_inclusive and tax.included_in_print_rate:
			tax.included_in_print_rate = 0
			has_changes = True

	# Recalculate if we made changes
	if has_changes:
		doc.calculate_taxes_and_totals()


def auto_assign_loyalty_program_on_invoice(doc, pos_settings=None):
	"""
	Auto-assign loyalty program to customer if loyalty is enabled in POS Settings
	but customer doesn't have a loyalty program yet.

	This ensures customers created before loyalty was enabled can still earn points.

	Args:
		doc: Sales Invoice document
		pos_settings: Pre-fetched POS Settings dict (avoids redundant DB query)
	"""
	if not doc.is_pos or not doc.pos_profile or not doc.customer:
		return

	if not pos_settings:
		return

	if not cint(pos_settings.get("enable_loyalty_program")):
		return

	# Check if customer already has a loyalty program
	customer_loyalty = frappe.db.get_value("Customer", doc.customer, "loyalty_program")
	if customer_loyalty:
		return

	loyalty_program = pos_settings.get("default_loyalty_program")
	if not loyalty_program:
		return

	# Assign loyalty program to customer
	frappe.db.set_value(
		"Customer",
		doc.customer,
		"loyalty_program",
		loyalty_program,
		update_modified=False
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
