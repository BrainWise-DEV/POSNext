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

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	apply_tax_inclusive(doc)
	auto_assign_loyalty_program_on_invoice(doc)


def apply_tax_inclusive(doc):
	"""
	Mark taxes as inclusive based on POS Profile setting.

	This function reads the tax_inclusive setting from POS Settings
	and applies it to all taxes in the invoice (except Actual charge type).

	Args:
		doc: Sales Invoice document
	"""
	if not doc.pos_profile:
		return

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


def auto_assign_loyalty_program_on_invoice(doc):
	"""
	Auto-assign loyalty program to customer if loyalty is enabled in POS Settings
	but customer doesn't have a loyalty program yet.

	This ensures customers created before loyalty was enabled can still earn points.

	Args:
		doc: Sales Invoice document
	"""
	if not doc.is_pos or not doc.pos_profile or not doc.customer:
		return

	# Check if customer already has a loyalty program
	customer_loyalty = frappe.db.get_value("Customer", doc.customer, "loyalty_program")
	if customer_loyalty:
		return

	# Get POS Settings
	pos_settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": doc.pos_profile},
		["enable_loyalty_program", "default_loyalty_program"],
		as_dict=True
	)

	if not pos_settings:
		return

	if not cint(pos_settings.get("enable_loyalty_program")):
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


def validate_coupon_on_invoice(doc, method=None):
	"""
	Validate coupon code on Sales Invoice (like Sales Order does).
	This enables native ERPNext coupon validation for Sales Invoice.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	if not doc.coupon_code:
		return

	try:
		from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code
		validate_coupon_code(doc.coupon_code)
	except Exception as e:
		frappe.log_error(
			"Coupon Validation Error",
			f"Invoice: {doc.name}, Coupon: {doc.coupon_code}, Error: {str(e)}"
		)
		raise


def update_coupon_usage_on_submit(doc, method=None):
	"""
	Increment coupon usage counter on submit.
	This mirrors the behavior in Sales Order for ERPNext coupon tracking.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	if not doc.coupon_code:
		return

	try:
		from erpnext.accounts.doctype.pricing_rule.utils import update_coupon_code_count
		update_coupon_code_count(doc.coupon_code, "used")
	except Exception as e:
		frappe.log_error(
			"Coupon Usage Update Error",
			f"Invoice: {doc.name}, Coupon: {doc.coupon_code}, Action: used, Error: {str(e)}"
		)
		# Don't block invoice submission if coupon update fails


def update_coupon_usage_on_cancel(doc, method=None):
	"""
	Decrement coupon usage counter on cancel.
	This mirrors the behavior in Sales Order for ERPNext coupon tracking.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	if not doc.coupon_code:
		return

	try:
		from erpnext.accounts.doctype.pricing_rule.utils import update_coupon_code_count
		update_coupon_code_count(doc.coupon_code, "cancelled")
	except Exception as e:
		frappe.log_error(
			"Coupon Usage Update Error",
			f"Invoice: {doc.name}, Coupon: {doc.coupon_code}, Action: cancelled, Error: {str(e)}"
		)
