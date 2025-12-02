# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Credit Sales API
Handles credit sale operations including:
- Getting available customer credit
- Credit redemption and allocation
- Journal Entry creation for GL posting
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, today, cint, get_datetime


# REVIEW: GIG QUESTION: Why do we use @frappe.whitelist??!!

# REVIEW: This function mixes multiple concerns:
# 1. Calculating outstanding invoices
# 2. Calculating negative credits
# 3. Calculating unallocated advances
# RECOMMENDATIONS: breaking into helper functions like:
# - _get_customer_outstanding()
# - _get_customer_credits()
# - _get_customer_advances()
# Also, it's not good to write raw SQL queries.
@frappe.whitelist()
def get_customer_balance(customer, company=None):
	"""
	Get customer outstanding balance from Sales Invoices.

	Args:
		customer: Customer ID
		company: Company (optional filter)

	Returns:
		dict: {
			'total_outstanding': float (positive = customer owes),
			'total_credit': float (positive = customer has credit),
			'net_balance': float (positive = customer owes, negative = customer has credit)
		}
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	filters = {
		"customer": customer,
		"docstatus": 1
	}

	if company:
		filters["company"] = company

	# Get total outstanding (positive outstanding = customer owes)
	total_outstanding = frappe.db.sql("""
		SELECT SUM(outstanding_amount) AS total
		FROM `tabSales Invoice`
		WHERE customer = %(customer)s
			AND docstatus = %(docstatus)s
			AND outstanding_amount > 0
			{company_condition}
	""".format(
		company_condition="AND company = %(company)s" if company else ""
	), filters, as_dict=True)

	outstanding = flt(total_outstanding[0].get("total", 0) if total_outstanding else 0)

	# Get total credit (negative outstanding = customer has credit)
	total_credit = frappe.db.sql("""
		SELECT SUM(ABS(outstanding_amount)) AS total
		FROM `tabSales Invoice`
		WHERE customer = %(customer)s
			AND docstatus = %(docstatus)s
			AND outstanding_amount < 0
			{company_condition}
	""".format(
		company_condition="AND company = %(company)s" if company else ""
	), filters, as_dict=True)

	credit = flt(total_credit[0].get("total", 0) if total_credit else 0)

	# Get unallocated advances
	advance_filters = {
		"party": customer,
		"docstatus": 1,
		"payment_type": "Receive"
	}
	if company:
		advance_filters["company"] = company

	advances = frappe.db.sql("""
		SELECT SUM(unallocated_amount) AS total
		FROM `tabPayment Entry`
		WHERE party = %(party)s
			AND docstatus = %(docstatus)s
			AND payment_type = %(payment_type)s
			AND unallocated_amount > 0
			{company_condition}
	""".format(
		company_condition="AND company = %(company)s" if company else ""
	), advance_filters, as_dict=True)

	advance_credit = flt(advances[0].get("total", 0) if advances else 0)

	# Total credit includes both negative outstanding and advances
	total_credit_available = credit + advance_credit

	# Net balance: positive = owes, negative = has credit
	net_balance = outstanding - total_credit_available

	return {
		"total_outstanding": outstanding,
		"total_credit": total_credit_available,
		"net_balance": net_balance
	}


def check_credit_sale_enabled(pos_profile):
	"""
	Check if credit sale is enabled for the POS Profile.

	Args:
		pos_profile: POS Profile name

	Returns:
		bool: True if credit sale is enabled
	"""
	if not pos_profile:
		return False

	# Get POS Settings for the profile
	pos_settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile},
		"allow_credit_sale",
		as_dict=False
	)

	return bool(pos_settings)


# REVIEW: 
# Suggestions:
# - Break into _get_negative_invoices() and _get_unallocated_advances()
# - DRY: negative outstanding conversion occurs multiple times.
# - Consider performance with large datasets (pagination or filters)
@frappe.whitelist()
def get_available_credit(customer, company, pos_profile=None):
	"""
	Get list of available credit sources for a customer.
	Includes:
	1. Outstanding invoices with negative outstanding (overpaid/returns)
	2. Unallocated advance payment entries

	Args:
		customer: Customer ID
		company: Company
		pos_profile: POS Profile (optional, for checking if feature is enabled)

	Returns:
		list: Available credit sources with amounts
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	if not company:
		frappe.throw(_("Company is required"))

	# Check if credit sale is enabled (if pos_profile is provided)
	if pos_profile and not check_credit_sale_enabled(pos_profile):
		frappe.throw(_("Credit sale is not enabled for this POS Profile"))

	total_credit = []

	# Get invoices with negative outstanding (customer has overpaid or returns)
	outstanding_invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"outstanding_amount": ["<", 0],
			"docstatus": 1,
			"customer": customer,
			"company": company,
		},
		fields=["name", "outstanding_amount", "is_return", "posting_date", "grand_total"],
		order_by="posting_date desc"
	)

	for row in outstanding_invoices:
		# Outstanding is negative, so make it positive for display
		available_credit = -flt(row.outstanding_amount)

		if available_credit > 0:
			total_credit.append({
				"type": "Invoice",
				"credit_origin": row.name,
				"total_credit": available_credit,
				"available_credit": available_credit,
				"source_type": "Sales Return" if row.is_return else "Sales Invoice",
				"posting_date": row.posting_date,
				"reference_amount": row.grand_total,
				"credit_to_redeem": 0,  # User will set this
			})

	# Get unallocated advance payments
	advances = frappe.get_all(
		"Payment Entry",
		filters={
			"unallocated_amount": [">", 0],
			"party": customer,
			"company": company,
			"docstatus": 1,
			"payment_type": "Receive",
		},
		fields=["name", "unallocated_amount", "posting_date", "paid_amount", "mode_of_payment"],
		order_by="posting_date desc"
	)

	for row in advances:
		total_credit.append({
			"type": "Advance",
			"credit_origin": row.name,
			"total_credit": flt(row.unallocated_amount),
			"available_credit": flt(row.unallocated_amount),
			"source_type": "Payment Entry",
			"posting_date": row.posting_date,
			"reference_amount": row.paid_amount,
			"mode_of_payment": row.mode_of_payment,
			"credit_to_redeem": 0,  # User will set this
		})

	return total_credit


# REVIEW: 
# Suggestions:
# - Validation of input dict should be stricter.
# - Transactional safety: consider wrapping all allocations in a single transaction.
# - Could extract allocation logic to a CreditAllocationService class for scalability.
@frappe.whitelist()
def redeem_customer_credit(invoice_name, customer_credit_dict):
	"""
	Redeem customer credit by creating Journal Entries.
	This allocates credit from previous invoices/advances to the new invoice.

	Args:
		invoice_name: Sales Invoice name
		customer_credit_dict: List of credit redemption entries

	Returns:
		list: Created journal entry names
	"""
	import json

	if isinstance(customer_credit_dict, str):
		customer_credit_dict = json.loads(customer_credit_dict)

	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not customer_credit_dict:
		return []

	# Get invoice document
	invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)

	if invoice_doc.docstatus != 1:
		frappe.throw(_("Invoice must be submitted to redeem credit"))

	created_journal_entries = []

	# Process each credit source
	for credit_row in customer_credit_dict:
		credit_to_redeem = flt(credit_row.get("credit_to_redeem", 0))

		if credit_to_redeem <= 0:
			continue

		credit_type = credit_row.get("type")
		credit_origin = credit_row.get("credit_origin")

		if credit_type == "Invoice":
			# Create JE to allocate credit from original invoice to new invoice
			je_name = _create_credit_allocation_journal_entry(
				invoice_doc,
				credit_origin,
				credit_to_redeem
			)
			created_journal_entries.append(je_name)

		elif credit_type == "Advance":
			# Create Payment Entry to allocate advance payment
			pe_name = _create_payment_entry_from_advance(
				invoice_doc,
				credit_origin,
				credit_to_redeem
			)
			created_journal_entries.append(pe_name)

	return created_journal_entries


# REVIEW:
# - Directly submits JE, which can fail mid-process — consider transaction/atomic commit.
# - Consider extracting debit/credit creation into a helper for DRY.
# - Cost center retrieval should default more safely if not set.
# - Could add logging/debug info for audit.
def _create_credit_allocation_journal_entry(invoice_doc, original_invoice_name, amount):
	"""
	Create Journal Entry to allocate credit from one invoice to another.

	GL Entries Created:
	- Debit: Original Invoice Receivable Account (reduces its outstanding)
	- Credit: New Invoice Receivable Account (reduces its outstanding)

	Args:
		invoice_doc: New Sales Invoice document
		original_invoice_name: Original invoice with credit
		amount: Amount to allocate

	Returns:
		str: Journal Entry name
	"""
	# Get original invoice
	original_invoice = frappe.get_doc("Sales Invoice", original_invoice_name)

	# Get cost center
	cost_center = invoice_doc.get("cost_center") or frappe.get_cached_value(
		"Company", invoice_doc.company, "cost_center"
	)

	# Create Journal Entry
	jv_doc = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"posting_date": today(),
		"company": invoice_doc.company,
		"user_remark": get_credit_redeem_remark(invoice_doc.name),
	})

	# Debit Entry - Original Invoice (reduces outstanding)
	debit_row = jv_doc.append("accounts", {})
	debit_row.update({
		"account": original_invoice.debit_to,
		"party_type": "Customer",
		"party": invoice_doc.customer,
		"reference_type": "Sales Invoice",
		"reference_name": original_invoice.name,
		"debit_in_account_currency": amount,
		"credit_in_account_currency": 0,
		"cost_center": cost_center,
	})

	# Credit Entry - New Invoice (reduces outstanding)
	credit_row = jv_doc.append("accounts", {})
	credit_row.update({
		"account": invoice_doc.debit_to,
		"party_type": "Customer",
		"party": invoice_doc.customer,
		"reference_type": "Sales Invoice",
		"reference_name": invoice_doc.name,
		"debit_in_account_currency": 0,
		"credit_in_account_currency": amount,
		"cost_center": cost_center,
	})

	jv_doc.flags.ignore_permissions = True
	jv_doc.save()
	jv_doc.submit()

	frappe.msgprint(
		_("Journal Entry {0} created for credit redemption").format(jv_doc.name),
		alert=True
	)

	return jv_doc.name


def _create_payment_entry_from_advance(invoice_doc, payment_entry_name, amount):
	"""
	Allocate existing advance Payment Entry to invoice.
	Updates the Payment Entry to add reference to the invoice.

	Args:
		invoice_doc: Sales Invoice document
		payment_entry_name: Payment Entry with unallocated amount
		amount: Amount to allocate

	Returns:
		str: Payment Entry name
	"""
	# Get payment entry
	payment_entry = frappe.get_doc("Payment Entry", payment_entry_name)

	# Check if already allocated
	if payment_entry.unallocated_amount < amount:
		frappe.throw(
			_("Payment Entry {0} has insufficient unallocated amount").format(
				payment_entry_name
			)
		)

	# Add reference to invoice
	payment_entry.append("references", {
		"reference_doctype": "Sales Invoice",
		"reference_name": invoice_doc.name,
		"total_amount": invoice_doc.grand_total,
		"outstanding_amount": invoice_doc.outstanding_amount,
		"allocated_amount": amount,
	})

	# Recalculate unallocated amount
	payment_entry.set_amounts()

	payment_entry.flags.ignore_permissions = True
	payment_entry.flags.ignore_validate_update_after_submit = True
	payment_entry.save()

	frappe.msgprint(
		_("Payment Entry {0} allocated to invoice").format(payment_entry.name),
		alert=True
	)

	return payment_entry.name


def get_credit_redeem_remark(invoice_name):
	"""Get remark for credit redemption journal entry."""
	return f"POS Next credit redemption for invoice {invoice_name}"


@frappe.whitelist()
def cancel_credit_journal_entries(invoice_name):
	"""
	Cancel journal entries created for credit redemption when invoice is cancelled.

	Args:
		invoice_name: Sales Invoice name
	"""
	remark = get_credit_redeem_remark(invoice_name)

	# Find linked journal entries
	linked_journal_entries = frappe.get_all(
		"Journal Entry",
		filters={
			"docstatus": 1,
			"user_remark": remark
		},
		pluck="name"
	)

	cancelled_count = 0
	for journal_entry_name in linked_journal_entries:
		try:
			je_doc = frappe.get_doc("Journal Entry", journal_entry_name)

			# Verify it references this invoice
			has_reference = any(
				d.reference_type == "Sales Invoice" and d.reference_name == invoice_name
				for d in je_doc.accounts
			)

			if not has_reference:
				continue

			je_doc.flags.ignore_permissions = True
			je_doc.cancel()
			cancelled_count += 1
		except Exception as e:
			frappe.log_error(
				f"Failed to cancel Journal Entry {journal_entry_name}: {str(e)}",
				"Credit Sale JE Cancellation"
			)

	if cancelled_count > 0:
		frappe.msgprint(
			_("Cancelled {0} credit redemption journal entries").format(cancelled_count),
			alert=True
		)

	return cancelled_count


@frappe.whitelist()
def get_credit_sale_summary(pos_profile):
	"""
	Get summary of credit sales for a POS Profile.

	Args:
		pos_profile: POS Profile name

	Returns:
		dict: Summary statistics
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	# Get credit sales (outstanding > 0)
	summary = frappe.db.sql("""
		SELECT
			COUNT(*) as count,
			SUM(outstanding_amount) as total_outstanding,
			SUM(grand_total) as total_amount,
			SUM(paid_amount) as total_paid
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
			AND outstanding_amount > 0
			AND is_return = 0
	""", {"pos_profile": pos_profile}, as_dict=True)

	return summary[0] if summary else {
		"count": 0,
		"total_outstanding": 0,
		"total_amount": 0,
		"total_paid": 0
	}


# REVIEW: Retrieves credit invoices.
# - Access control is manual; consider central permission check for POS Profiles.
# - Could refactor SQL query into a helper for reuse.
# - It's not good to write raw SQL queries.
@frappe.whitelist()
def get_credit_invoices(pos_profile, limit=100):
	"""
	Get list of credit sale invoices (with outstanding amount).

	Args:
		pos_profile: POS Profile name
		limit: Maximum number of invoices to return

	Returns:
		list: Credit sale invoices
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	# Check if user has access to this POS Profile
	has_access = frappe.db.exists(
		"POS Profile User",
		{"parent": pos_profile, "user": frappe.session.user}
	)

	if not has_access and not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("You don't have access to this POS Profile"))

	# Query for credit invoices
	invoices = frappe.db.sql("""
		SELECT
			name,
			customer,
			customer_name,
			posting_date,
			posting_time,
			grand_total,
			paid_amount,
			outstanding_amount,
			status,
			docstatus
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
			AND outstanding_amount > 0
			AND is_return = 0
		ORDER BY
			posting_date DESC,
			posting_time DESC
		LIMIT %(limit)s
	""", {
		"pos_profile": pos_profile,
		"limit": limit
	}, as_dict=True)

	return invoices
