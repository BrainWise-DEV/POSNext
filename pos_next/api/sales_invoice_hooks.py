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
			"POS Settings", {"pos_profile": doc.pos_profile}, ["tax_inclusive"], as_dict=True
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
		as_dict=True,
	)

	if not pos_settings:
		return

	if not cint(pos_settings.get("enable_loyalty_program")):
		return

	loyalty_program = pos_settings.get("default_loyalty_program")
	if not loyalty_program:
		return

	# Assign loyalty program to customer
	frappe.db.set_value("Customer", doc.customer, "loyalty_program", loyalty_program, update_modified=False)


def record_one_time_offer_usage(doc, method=None):
	"""Record redemption of one-time-per-customer Pricing Rules on submit.

	The applied one-time rules are read from ``pos_applied_one_time_rules`` (a
	JSON list stamped by update_invoice before item.pricing_rules is cleared —
	the cleared field can't be read back here). Inserts a
	``One Time Customer Offer Usage`` row per (customer, rule); the doctype's
	composite name ({customer}::{pricing_rule}) makes a duplicate insert raise
	DuplicateEntryError, so it stays idempotent and race-safe.
	"""
	import json

	if doc.get("is_return") or not doc.get("customer"):
		return

	raw = doc.get("pos_applied_one_time_rules")
	if not raw:
		return
	try:
		rule_names = json.loads(raw)
	except (ValueError, TypeError):
		return
	if not rule_names:
		return

	from frappe.utils import now

	for rule in rule_names:
		try:
			frappe.get_doc(
				{
					"doctype": "One Time Customer Offer Usage",
					"customer": doc.customer,
					"pricing_rule": rule,
					"sales_invoice": doc.name,
					"redemption_date": now(),
				}
			).insert(ignore_permissions=True, ignore_if_duplicate=True)
		except frappe.DuplicateEntryError:
			# Customer already recorded for this rule — one-time guard intact.
			pass


def release_one_time_offer_usage(doc, method=None):
	"""Release one-time redemptions on cancel so the customer can redeem again."""
	frappe.db.delete("One Time Customer Offer Usage", {"sales_invoice": doc.name})


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
			message=f"Invoice: {doc.name}, Error: {e!s}\n{frappe.get_traceback()}",
		)
		# Don't block invoice cancellation if JE cancellation fails
		frappe.msgprint(
			_("Warning: Some credit journal entries may not have been cancelled. Please check manually."),
			alert=True,
			indicator="orange",
		)
