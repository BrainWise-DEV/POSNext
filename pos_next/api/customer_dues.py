# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Customer Dues API

Provides a full account statement for a customer and FIFO lump-sum payment.
Reuses enrich_invoice_with_payment_history and create_payment_entry from
partial_payments.py and get_customer_balance from credit_sales.py.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from pos_next.api.credit_sales import get_customer_balance
from pos_next.api.partial_payments import (
	AMOUNT_TOLERANCE,
	create_payment_entry,
	enrich_invoice_with_payment_history,
)

# Fields fetched for due invoices (enriched with payment history)
_DUE_FIELDS = [
	"name",
	"posting_date",
	"posting_time",
	"customer",
	"customer_name",
	"grand_total",
	"outstanding_amount",
	"status",
	"currency",
	"is_return",
	"return_against",
]

# Fields fetched for settled/return invoices (no payment-ledger enrichment)
_SETTLED_FIELDS = [
	"name",
	"posting_date",
	"posting_time",
	"customer",
	"customer_name",
	"grand_total",
	"outstanding_amount",
	"status",
	"currency",
	"is_return",
	"return_against",
]


@frappe.whitelist()
def get_customer_due_statement(customer, pos_profile=None, company=None, limit=100):
	"""
	Return a complete account statement for *customer*.

	Args:
		customer: Customer ID
		pos_profile: Optional POS Profile name — used to resolve company when company is omitted
		company: Optional Company filter; resolved from pos_profile when absent
		limit: Max rows for settled/return invoices (default 100)

	Returns:
		{
		    summary: {total_outstanding, total_credit, net_balance,
		              due_count, settled_count},
		    due_invoices: [...],     # outstanding > 0, oldest first; enriched with payment history
		    settled_invoices: [...], # outstanding <= 0 or is_return, recent first; capped
		    currency: str,
		}
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} does not exist").format(customer))

	# Resolve company
	if not company and pos_profile:
		company = frappe.db.get_value("POS Profile", pos_profile, "company")

	# ── Summary ──────────────────────────────────────────────────────────────
	balance = get_customer_balance(customer, company)
	summary = {
		"total_outstanding": balance["total_outstanding"],
		"total_credit": balance["total_credit"],
		"net_balance": balance["net_balance"],
	}

	# ── Due invoices (oldest first = FIFO display order) ─────────────────────
	due_filters = {
		"customer": customer,
		"docstatus": 1,
		"is_return": 0,
		"outstanding_amount": [">", 0],
	}
	if company:
		due_filters["company"] = company

	due_invoices = frappe.get_all(
		"Sales Invoice",
		filters=due_filters,
		fields=_DUE_FIELDS,
		order_by="posting_date asc, creation asc",
	)

	# Enrich with payment history (payment ledger = source of truth)
	for inv in due_invoices:
		enrich_invoice_with_payment_history(inv)

	# ── Settled / return invoices (recent first, capped) ─────────────────────
	settled_filters = {
		"customer": customer,
		"docstatus": 1,
	}
	if company:
		settled_filters["company"] = company

	settled_invoices = frappe.get_all(
		"Sales Invoice",
		filters=settled_filters,
		fields=_SETTLED_FIELDS,
		order_by="posting_date desc, creation desc",
		limit=int(limit),
		or_filters={
			"outstanding_amount": ["<=", 0],
			"is_return": 1,
		},
	)

	# ── Batch-fetch items for all invoices (avoids N+1) ─────────────────────
	all_names = [inv["name"] for inv in due_invoices] + [inv["name"] for inv in settled_invoices]
	if all_names:
		rows = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", all_names]},
			fields=["parent", "item_code", "item_name", "qty", "rate", "amount", "uom"],
		)
		items_by_invoice = {}
		for row in rows:
			items_by_invoice.setdefault(row["parent"], []).append(row)
		for inv in due_invoices + settled_invoices:
			inv["items"] = items_by_invoice.get(inv["name"], [])

	# ── Currency (from first invoice or company default) ─────────────────────
	currency = (
		(due_invoices or settled_invoices or [{}])[0].get("currency")
		or frappe.db.get_value("Company", company, "default_currency")
		or "USD"
	)

	summary["due_count"] = len(due_invoices)
	summary["settled_count"] = len(settled_invoices)

	return {
		"summary": summary,
		"due_invoices": due_invoices,
		"settled_invoices": settled_invoices,
		"currency": currency,
	}


@frappe.whitelist()
def get_credit_customers_summary(pos_profile=None, company=None):
	"""
	Aggregate "who owes the shop money" across all company customers.

	Mirrors the math in credit_sales.get_customer_balance but GROUP BY customer:
	- regular (is_return=0) positive outstanding_amount → total_outstanding
	- return  (is_return=1) outstanding_amount < 0      → Abs summed as total_credit
	- net_balance = total_outstanding - total_credit

	Only customers with net_balance > 0 are returned, sorted by net_balance desc.

	Args:
		pos_profile: Optional POS Profile — used to resolve company when company is omitted
		company: Optional Company filter; resolved from pos_profile when absent

	Returns:
		{
		    customers: [{customer, customer_name, total_outstanding,
		                 total_credit, net_balance, due_count}, ...],
		    totals: {net_balance, customer_count},
		    currency: str,
		}
	"""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Resolve company
	if not company and pos_profile:
		company = frappe.db.get_value("POS Profile", pos_profile, "company")

	try:
		from frappe.query_builder import DocType
		from frappe.query_builder.functions import Abs, Coalesce, Sum
		from pypika import Case

		SalesInvoice = DocType("Sales Invoice")

		base_filters = SalesInvoice.docstatus == 1
		if company:
			base_filters = base_filters & (SalesInvoice.company == company)

		# Regular invoices: positive outstanding (what customer owes) + due count
		regular_query = (
			frappe.qb.from_(SalesInvoice)
			.select(
				SalesInvoice.customer,
				SalesInvoice.customer_name,
				Coalesce(
					Sum(
						Case()
						.when(SalesInvoice.outstanding_amount > 0, SalesInvoice.outstanding_amount)
						.else_(0)
					),
					0,
				).as_("total_outstanding"),
				Coalesce(
					Sum(Case().when(SalesInvoice.outstanding_amount > 0, 1).else_(0)),
					0,
				).as_("due_count"),
			)
			.where(base_filters & (SalesInvoice.is_return == 0))
			.groupby(SalesInvoice.customer, SalesInvoice.customer_name)
		)

		# Return invoices: only negative outstanding counts as credit (no cash refund)
		return_query = (
			frappe.qb.from_(SalesInvoice)
			.select(
				SalesInvoice.customer,
				Coalesce(Sum(Abs(SalesInvoice.outstanding_amount)), 0).as_("total_credit"),
			)
			.where(
				base_filters
				& (SalesInvoice.is_return == 1)
				& (SalesInvoice.outstanding_amount < 0)
			)
			.groupby(SalesInvoice.customer)
		)

		regular_rows = regular_query.run(as_dict=True)
		return_rows = return_query.run(as_dict=True)

		credit_by_customer = {r.customer: flt(r.total_credit) for r in return_rows}

		customers = []
		for r in regular_rows:
			total_outstanding = flt(r.total_outstanding)
			total_credit = credit_by_customer.get(r.customer, 0.0)
			net_balance = total_outstanding - total_credit
			if net_balance > 0:
				customers.append(
					{
						"customer": r.customer,
						"customer_name": r.customer_name or r.customer,
						"total_outstanding": total_outstanding,
						"total_credit": total_credit,
						"net_balance": net_balance,
						"due_count": int(r.due_count or 0),
					}
				)

		customers.sort(key=lambda c: c["net_balance"], reverse=True)

		net_total = sum(c["net_balance"] for c in customers)

		currency = (
			(frappe.db.get_value("Company", company, "default_currency") if company else None)
			or frappe.db.get_default("currency")
			or "USD"
		)

		return {
			"customers": customers,
			"totals": {"net_balance": net_total, "customer_count": len(customers)},
			"currency": currency,
		}

	except Exception:
		frappe.log_error(
			title="Credit Customers Summary Error",
			message=f"pos_profile: {pos_profile}, company: {company}\n{frappe.get_traceback()}",
		)
		return {
			"customers": [],
			"totals": {"net_balance": 0.0, "customer_count": 0},
			"currency": "USD",
		}


@frappe.whitelist()
def pay_customer_due(
	customer,
	payments,
	pos_profile=None,
	pos_opening_shift=None,
	company=None,
):
	"""
	FIFO lump-sum payment across a customer's outstanding invoices.

	payments: JSON list [{mode_of_payment, amount, account?}]

	Returns:
		{
		    success: bool,
		    payment_entries_created: int,
		    allocations: [{invoice, mode_of_payment, amount}],
		    summary: <fresh get_customer_balance result>,
		}
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	if not frappe.has_permission("Sales Invoice", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# Parse payments
	if isinstance(payments, str):
		try:
			payments = json.loads(payments)
		except json.JSONDecodeError:
			frappe.throw(_("Invalid payments payload: malformed JSON"))

	if not isinstance(payments, list) or not payments:
		frappe.throw(_("At least one payment is required"))

	# Resolve company
	if not company and pos_profile:
		company = frappe.db.get_value("POS Profile", pos_profile, "company")

	# Fetch outstanding invoices oldest-first (FIFO)
	due_filters = {
		"customer": customer,
		"docstatus": 1,
		"is_return": 0,
		"outstanding_amount": [">", 0],
	}
	if company:
		due_filters["company"] = company

	due_invoices = frappe.get_all(
		"Sales Invoice",
		filters=due_filters,
		fields=["name", "outstanding_amount"],
		order_by="posting_date asc, creation asc",
	)

	if not due_invoices:
		frappe.throw(_("No outstanding invoices found for customer {0}").format(customer))

	# Total payment vs total outstanding
	total_payment = sum(flt(p.get("amount", 0)) for p in payments)
	total_outstanding = sum(flt(inv["outstanding_amount"]) for inv in due_invoices)

	if total_payment > total_outstanding + AMOUNT_TOLERANCE:
		frappe.throw(
			_("Total payment {0} exceeds total outstanding {1}").format(
				frappe.format_value(total_payment, {"fieldtype": "Currency"}),
				frappe.format_value(total_outstanding, {"fieldtype": "Currency"}),
			)
		)

	# Savepoint-backed batch
	savepoint = "pay_customer_due_batch"
	allocations = []
	payment_entries_created = 0

	# Track remaining outstanding per invoice across payment modes
	inv_remaining = {inv["name"]: flt(inv["outstanding_amount"]) for inv in due_invoices}
	inv_order = [inv["name"] for inv in due_invoices]

	try:
		frappe.db.savepoint(savepoint)

		for payment in payments:
			mode = payment.get("mode_of_payment", "Cash")
			account = payment.get("account")
			remaining_mode = flt(payment.get("amount", 0))

			if remaining_mode <= 0:
				continue

			for inv_name in inv_order:
				if remaining_mode <= AMOUNT_TOLERANCE:
					break
				inv_due = inv_remaining.get(inv_name, 0)
				if inv_due <= AMOUNT_TOLERANCE:
					continue

				alloc_amount = min(remaining_mode, inv_due)
				pe_name = create_payment_entry(
					invoice_name=inv_name,
					amount=alloc_amount,
					mode_of_payment=mode,
					payment_account=account,
					pos_opening_shift=pos_opening_shift,
				)
				allocations.append(
					{"invoice": inv_name, "mode_of_payment": mode, "amount": alloc_amount}
				)
				payment_entries_created += 1
				inv_remaining[inv_name] = inv_due - alloc_amount
				remaining_mode -= alloc_amount

	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	fresh_summary = get_customer_balance(customer, company)

	return {
		"success": True,
		"payment_entries_created": payment_entries_created,
		"allocations": allocations,
		"summary": fresh_summary,
	}
