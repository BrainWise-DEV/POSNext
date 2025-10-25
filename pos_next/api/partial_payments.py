# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_partial_paid_invoices(pos_profile, limit=50):
	"""
	Get list of partially paid invoices for a POS Profile

	Args:
		pos_profile: POS Profile name
		limit: Maximum number of invoices to return (default 50)

	Returns:
		List of partially paid invoices with payment details
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

	# Query for partial paid invoices
	invoices = frappe.db.sql("""
		SELECT
			pi.name,
			pi.customer,
			pi.customer_name,
			pi.posting_date,
			pi.posting_time,
			pi.grand_total,
			pi.paid_amount,
			pi.outstanding_amount,
			pi.status,
			pi.is_return,
			pi.docstatus
		FROM
			`tabSales Invoice` pi
		WHERE
			pi.pos_profile = %(pos_profile)s
			AND pi.docstatus = 1
			AND pi.is_pos = 1
			AND pi.outstanding_amount > 0
			AND pi.outstanding_amount < pi.grand_total
			AND pi.is_return = 0
		ORDER BY
			pi.posting_date DESC,
			pi.posting_time DESC
		LIMIT %(limit)s
	""", {
		"pos_profile": pos_profile,
		"limit": limit
	}, as_dict=True)

	# Get payment entries for each invoice
	for invoice in invoices:
		invoice.payments = frappe.db.sql("""
			SELECT
				mode_of_payment,
				amount,
				type
			FROM
				`tabSales Invoice Payment`
			WHERE
				parent = %(invoice)s
			ORDER BY
				idx
		""", {"invoice": invoice.name}, as_dict=True)

	return invoices


@frappe.whitelist()
def get_partial_payment_details(invoice_name):
	"""
	Get detailed payment information for a partially paid invoice

	Args:
		invoice_name: Sales Invoice name

	Returns:
		Invoice details with payment breakdown
	"""
	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	# Check permission
	if not frappe.has_permission("Sales Invoice", "read", invoice_name):
		frappe.throw(_("You don't have permission to view this invoice"))

	# Get invoice details
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	# Get payment entries
	payments = frappe.db.sql("""
		SELECT
			mode_of_payment,
			amount,
			type,
			idx
		FROM
			`tabSales Invoice Payment`
		WHERE
			parent = %(invoice)s
		ORDER BY
			idx
	""", {"invoice": invoice_name}, as_dict=True)

	return {
		"name": invoice.name,
		"customer": invoice.customer,
		"customer_name": invoice.customer_name,
		"posting_date": invoice.posting_date,
		"posting_time": invoice.posting_time,
		"grand_total": invoice.grand_total,
		"paid_amount": invoice.paid_amount,
		"outstanding_amount": invoice.outstanding_amount,
		"status": invoice.status,
		"payments": payments,
		"items": [
			{
				"item_code": item.item_code,
				"item_name": item.item_name,
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
			}
			for item in invoice.items
		]
	}


@frappe.whitelist()
def add_payment_to_partial_invoice(invoice_name, payments):
	"""
	Add additional payment to a partially paid invoice

	Args:
		invoice_name: Sales Invoice name
		payments: List of payment entries [{"mode_of_payment": "Cash", "amount": 100}]

	Returns:
		Updated invoice details
	"""
	import json

	if isinstance(payments, str):
		payments = json.loads(payments)

	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not payments or len(payments) == 0:
		frappe.throw(_("Payment entries are required"))

	# Check permission
	if not frappe.has_permission("Sales Invoice", "write", invoice_name):
		frappe.throw(_("You don't have permission to modify this invoice"))

	# Get invoice
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	# Validate invoice is partially paid
	if invoice.outstanding_amount <= 0:
		frappe.throw(_("Invoice is already fully paid"))

	if invoice.docstatus != 1:
		frappe.throw(_("Invoice must be submitted to add payments"))

	# Calculate total payment amount
	total_payment = sum(float(p.get("amount", 0)) for p in payments)

	if total_payment <= 0:
		frappe.throw(_("Payment amount must be greater than zero"))

	if total_payment > invoice.outstanding_amount:
		frappe.throw(_("Payment amount cannot exceed outstanding amount"))

	# Add payment entries
	for payment in payments:
		invoice.append("payments", {
			"mode_of_payment": payment.get("mode_of_payment"),
			"amount": payment.get("amount"),
			"type": payment.get("type", "Cash"),
		})

	# Update paid amount
	invoice.paid_amount = (invoice.paid_amount or 0) + total_payment
	invoice.outstanding_amount = invoice.grand_total - invoice.paid_amount

	# Update status if fully paid
	if invoice.outstanding_amount <= 0.01:  # Allow for rounding errors
		invoice.outstanding_amount = 0
		invoice.status = "Paid"

	# Save invoice
	invoice.flags.ignore_validate_update_after_submit = True
	invoice.save(ignore_permissions=True)

	frappe.db.commit()

	return get_partial_payment_details(invoice_name)


@frappe.whitelist()
def get_partial_payment_summary(pos_profile):
	"""
	Get summary statistics for partial payments

	Args:
		pos_profile: POS Profile name

	Returns:
		Summary with count and total outstanding amount
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

	summary = frappe.db.sql("""
		SELECT
			COUNT(*) as count,
			SUM(outstanding_amount) as total_outstanding,
			SUM(paid_amount) as total_paid
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
			AND outstanding_amount > 0
			AND outstanding_amount < grand_total
			AND is_return = 0
	""", {"pos_profile": pos_profile}, as_dict=True)

	return summary[0] if summary else {
		"count": 0,
		"total_outstanding": 0,
		"total_paid": 0
	}
