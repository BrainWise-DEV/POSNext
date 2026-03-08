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


@frappe.whitelist()
def get_customer_balance(customer, company=None):
	"""
	Get customer balance from Sales Invoices.

	Calculates the net balance from:
	- Regular invoices: Only positive outstanding_amount (what customer owes)
	- Return invoices: Only negative outstanding_amount (credit added to customer balance)

	Credit ONLY comes from return invoices where "Add to Customer Credit" was selected:
	- Cash refund given: outstanding_amount = 0 → NOT counted as credit
	- Added to customer credit: outstanding_amount < 0 → counted as credit

	Note: Negative outstanding on regular invoices (from linked returns) is NOT counted
	as credit to avoid double-counting - the credit is tracked on the return invoice.

	Args:
		customer: Customer ID
		company: Company (optional filter)

	Returns:
		dict: {
			'total_outstanding': float (positive = customer owes),
			'total_credit': float (positive = customer has credit from returns),
			'net_balance': float (positive = customer owes, negative = customer has credit)
		}
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	try:
		from frappe.query_builder import DocType
		from frappe.query_builder.functions import Sum, Abs, Coalesce
		from pypika import Case

		SalesInvoice = DocType("Sales Invoice")

		# Build base filters
		base_filters = (
			(SalesInvoice.customer == customer) &
			(SalesInvoice.docstatus == 1)
		)
		if company:
			base_filters = base_filters & (SalesInvoice.company == company)

		# Query for regular invoices (non-returns)
		# Only count positive outstanding (what customer owes)
		# Negative outstanding on regular invoices comes from returns linked to them,
		# so we don't count it here to avoid double-counting (credit comes from returns only)
		regular_query = (
			frappe.qb.from_(SalesInvoice)
			.select(
				Coalesce(
					Sum(
						Case()
						.when(SalesInvoice.outstanding_amount > 0, SalesInvoice.outstanding_amount)
						.else_(0)
					),
					0
				).as_("total_outstanding")
			)
			.where(base_filters & (SalesInvoice.is_return == 0))
		)

		# Query for return invoices
		# Only count returns where outstanding_amount < 0 (not refunded in cash)
		# If cash refund was given, outstanding_amount = 0 and should NOT count as credit
		# If no cash refund (added to customer credit), outstanding_amount < 0
		return_query = (
			frappe.qb.from_(SalesInvoice)
			.select(
				Coalesce(Sum(Abs(SalesInvoice.outstanding_amount)), 0).as_("return_credit")
			)
			.where(
				base_filters &
				(SalesInvoice.is_return == 1) &
				(SalesInvoice.outstanding_amount < 0)
			)
		)

		# Execute queries
		regular_result = regular_query.run(as_dict=True)
		return_result = return_query.run(as_dict=True)

		# Calculate totals
		total_outstanding = flt(regular_result[0].total_outstanding) if regular_result else 0.0
		# Credit only comes from return invoices where no cash refund was given
		total_credit = flt(return_result[0].return_credit) if return_result else 0.0

		# Net balance: positive = owes, negative = has credit
		net_balance = total_outstanding - total_credit

		return {
			"total_outstanding": total_outstanding,
			"total_credit": total_credit,
			"net_balance": net_balance
		}

	except Exception as e:
		frappe.log_error(
			title="Customer Balance Error",
			message=f"Customer: {customer}, Company: {company}, Error: {str(e)}\n{frappe.get_traceback()}"
		)
		return {
			"total_outstanding": 0.0,
			"total_credit": 0.0,
			"net_balance": 0.0
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


@frappe.whitelist()
def get_available_credit(customer, company, pos_profile=None):
	"""
	Get list of available credit sources for a customer.
	Includes:
	1. Outstanding invoices with negative outstanding (overpaid/returns)
	2. Unallocated advance payment entries

	Returns fresh data with modified timestamp for optimistic locking.
	The frontend should re-fetch before redemption to ensure data is current.

	Args:
		customer: Customer ID
		company: Company
		pos_profile: POS Profile (optional, for checking if feature is enabled)

	Returns:
		list: Available credit sources with amounts and modified timestamps
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	if not company:
		frappe.throw(_("Company is required"))

	total_credit = []

	# Get invoices with negative outstanding (customer has overpaid or returns)
	# Include modified timestamp for optimistic locking
	outstanding_invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"outstanding_amount": ["<", 0],
			"docstatus": 1,
			"customer": customer,
			"company": company,
		},
		fields=["name", "outstanding_amount", "is_return", "posting_date", "grand_total", "modified"],
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
				"modified": row.modified,  # For optimistic locking
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
		fields=["name", "unallocated_amount", "posting_date", "paid_amount", "mode_of_payment", "modified"],
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
			"modified": row.modified,  # For optimistic locking
		})

	return total_credit


@frappe.whitelist()
def redeem_customer_credit(invoice_name, customer_credit_dict):
	"""
	Redeem customer credit by creating Journal Entries.
	This allocates credit from previous invoices/advances to the new invoice.

	Uses row-level locking (SELECT FOR UPDATE) to prevent race conditions
	when multiple users try to redeem the same credit simultaneously.

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

	# Process each credit source with locking to prevent race conditions
	for credit_row in customer_credit_dict:
		credit_to_redeem = flt(credit_row.get("credit_to_redeem", 0))

		if credit_to_redeem <= 0:
			continue

		credit_type = credit_row.get("type")
		credit_origin = credit_row.get("credit_origin")

		if credit_type == "Invoice":
			# Validate and lock the credit source before creating JE
			_validate_and_lock_invoice_credit(credit_origin, credit_to_redeem)

			# Create JE to allocate credit from original invoice to new invoice
			je_name = _create_credit_allocation_journal_entry(
				invoice_doc,
				credit_origin,
				credit_to_redeem
			)
			created_journal_entries.append(je_name)

		elif credit_type == "Advance":
			# Validate and lock the advance payment before allocation
			_validate_and_lock_advance_credit(credit_origin, credit_to_redeem)

			# Create Payment Entry to allocate advance payment
			pe_name = _create_payment_entry_from_advance(
				invoice_doc,
				credit_origin,
				credit_to_redeem
			)
			created_journal_entries.append(pe_name)

	return created_journal_entries


def _validate_and_lock_invoice_credit(invoice_name, amount_to_redeem):
	"""
	Validate and lock invoice credit using SELECT FOR UPDATE.
	This prevents race conditions when multiple users try to use the same credit.

	Args:
		invoice_name: Source invoice name with credit
		amount_to_redeem: Amount being redeemed

	Raises:
		frappe.ValidationError: If insufficient credit available
	"""
	from frappe.query_builder import DocType

	SalesInvoice = DocType("Sales Invoice")

	# Use SELECT FOR UPDATE to lock the row
	# This blocks other transactions from reading/modifying until we commit
	query = (
		frappe.qb.from_(SalesInvoice)
		.select(SalesInvoice.name, SalesInvoice.outstanding_amount)
		.where(
			(SalesInvoice.name == invoice_name) &
			(SalesInvoice.docstatus == 1)
		)
		.for_update()
	)

	result = query.run(as_dict=True)

	if not result:
		frappe.throw(_("Credit source invoice {0} not found or not submitted").format(invoice_name))

	current_outstanding = flt(result[0].outstanding_amount)
	available_credit = -current_outstanding  # Credit is negative outstanding

	if available_credit < amount_to_redeem:
		frappe.throw(
			_("Insufficient credit available from {0}. Available: {1}, Requested: {2}").format(
				invoice_name,
				frappe.format_value(available_credit, {"fieldtype": "Currency"}),
				frappe.format_value(amount_to_redeem, {"fieldtype": "Currency"})
			)
		)


def _validate_and_lock_advance_credit(payment_entry_name, amount_to_redeem):
	"""
	Validate and lock advance payment using SELECT FOR UPDATE.
	This prevents race conditions when multiple users try to use the same advance.

	Args:
		payment_entry_name: Payment Entry name with unallocated amount
		amount_to_redeem: Amount being allocated

	Raises:
		frappe.ValidationError: If insufficient unallocated amount
	"""
	from frappe.query_builder import DocType

	PaymentEntry = DocType("Payment Entry")

	# Use SELECT FOR UPDATE to lock the row
	query = (
		frappe.qb.from_(PaymentEntry)
		.select(PaymentEntry.name, PaymentEntry.unallocated_amount)
		.where(
			(PaymentEntry.name == payment_entry_name) &
			(PaymentEntry.docstatus == 1)
		)
		.for_update()
	)

	result = query.run(as_dict=True)

	if not result:
		frappe.throw(_("Payment Entry {0} not found or not submitted").format(payment_entry_name))

	available_amount = flt(result[0].unallocated_amount)

	if available_amount < amount_to_redeem:
		frappe.throw(
			_("Insufficient unallocated amount in {0}. Available: {1}, Requested: {2}").format(
				payment_entry_name,
				frappe.format_value(available_amount, {"fieldtype": "Currency"}),
				frappe.format_value(amount_to_redeem, {"fieldtype": "Currency"})
			)
		)


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
