# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, nowdate, today, cint, get_datetime


@frappe.whitelist()
def get_customer_balance(customer, company=None):
    """
    Get customer balance info including:
    - Outstanding amount (sales invoices)
    - Credit balance (return invoices/CNs)
    - Advance payments (unallocated payment entries)

    If company is provided, results are filtered by company.
    """
    if not company:
        company = frappe.defaults.get_user_default("Company")

    total_outstanding = _get_customer_outstanding(customer, company)
    total_credit = _get_customer_credits(customer, company)
    advance_balance = _get_customer_advances(customer, company)

    # Calculate net balance (what the customer actually owes)
    # Net Balance = Outstanding - (Returns + Advances)
    net_balance = total_outstanding - (total_credit + advance_balance)

    return {
        "total_outstanding": total_outstanding, # Restored original key
        "outstanding_amount": total_outstanding, # New alias
        "total_credit": total_credit, # Restored original key
        "credit_balance": total_credit, # New alias
        "advance_balance": advance_balance,
        "net_balance": net_balance # Restored original key
    }

def _get_customer_outstanding(customer, company):
    """
    Calculate total outstanding amount for a customer in a specific company.
    Uses Sales Invoice outstanding amount sum instead of Customer.total_unpaid (which is global).
    """
    outstanding = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "outstanding_amount": [">", 0]
        },
        fields=["SUM(outstanding_amount) as amount"]
    )
    return flt(outstanding[0].amount) if outstanding and outstanding[0].amount else 0.0

def _get_customer_credits(customer, company):
    """
    Calculate total credit balance (Negative Outstanding from Returns/CNs).
    """
    # Sum of outstanding amounts from Credit Notes (negative outstanding)
    credit_notes = frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "outstanding_amount": ["<", 0],
            "is_return": 1
        },
        fields=["SUM(outstanding_amount) as amount"]
    )

    # Negative outstanding means credit to customer, so we flip sign to return positive credit value
    return abs(flt(credit_notes[0].amount)) if credit_notes and credit_notes[0].amount else 0.0

def _get_customer_advances(customer, company):
    """
    Calculate total unallocated advance payments.
    """
    # Sum of unallocated payment entries
    advances = frappe.get_all(
        "Payment Entry",
        filters={
            "party_type": "Customer",
            "party": customer,
            "company": company,
            "docstatus": 1,
            "payment_type": "Receive",
            "unallocated_amount": [">", 0]
        },
        fields=["SUM(unallocated_amount) as amount"]
    )
    return flt(advances[0].amount) if advances and advances[0].amount else 0.0


@frappe.whitelist()
def check_credit_sale_enabled(pos_profile):
    """Check if credit sales are allowed for this POS Profile"""
    pos_settings = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile, "allow_credit_sale": 1},
        "name"
    )
    return bool(pos_settings)


@frappe.whitelist()
def get_available_credit(customer, company, pos_profile=None):
    """
    Get available credit details to be used for payment.
    Returns a list of credit sources (Return Invoices and Unallocated Advances).
    Ensures backward compatibility with frontend expecting specific keys.
    """
    # Restored check for credit sale setting
    if pos_profile and not check_credit_sale_enabled(pos_profile):
        return []

    credits = []

    # 1. Get Credit Notes (Negative Outstanding)
    negative_invoices = _get_negative_invoices(customer, company)
    for inv in negative_invoices:
        credits.append({
            "type": "Invoice", # Backward compat
            "doctype": "Sales Invoice",
            "name": inv.name,
            "credit_origin": inv.name, # Backward compat
            "amount": abs(flt(inv.outstanding_amount)),
            "total_credit": abs(flt(inv.outstanding_amount)), # Backward compat
            "posting_date": inv.posting_date,
            "reference_name": inv.name
        })

    # 2. Get Unallocated Advances
    unallocated_advances = _get_unallocated_advances(customer, company)
    for adv in unallocated_advances:
        credits.append({
            "type": "Payment Entry", # Backward compat
            "doctype": "Payment Entry",
            "name": adv.name,
            "credit_origin": adv.name, # Backward compat
            "amount": flt(adv.unallocated_amount),
            "total_credit": flt(adv.unallocated_amount), # Backward compat
            "posting_date": adv.posting_date,
            "reference_name": adv.name
        })

    return credits

def _get_negative_invoices(customer, company):
    return frappe.get_all(
        "Sales Invoice",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "outstanding_amount": ["<", 0],
            "is_return": 1
        },
        fields=["name", "outstanding_amount", "posting_date", "grand_total"]
    )

def _get_unallocated_advances(customer, company):
    return frappe.get_all(
        "Payment Entry",
        filters={
            "party_type": "Customer",
            "party": customer,
            "company": company,
            "docstatus": 1,
            "payment_type": "Receive",
            "unallocated_amount": [">", 0]
        },
        fields=["name", "unallocated_amount", "posting_date", "paid_amount"]
    )


@frappe.whitelist()
def redeem_customer_credit(invoice_name, credit_data):
    """
    Redeem available credit against a sales invoice.

    Args:
        invoice_name: Name of the Sales Invoice to pay
        credit_data: List of dicts or JSON string of credits to use.
    """
    import json
    if isinstance(credit_data, str):
        credit_data = json.loads(credit_data)

    invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
    created_docs = []

    sales_invoices = []
    payment_entries = []

    # Normalize input format (Handle both list and dict for backward compatibility)
    if isinstance(credit_data, dict):
        sales_invoices = credit_data.get("sales_invoices", [])
        payment_entries = credit_data.get("payment_entries", [])
    elif isinstance(credit_data, list):
        for credit in credit_data:
            # Handle frontend sending "credit_origin" instead of "name"
            credit_name = credit.get("name") or credit.get("credit_origin")
            credit_doctype = credit.get("doctype") or credit.get("type")

            # Map legacy types
            if credit_doctype == "Invoice":
                credit_doctype = "Sales Invoice"

            if credit_doctype == "Sales Invoice":
                # Ensure we have the name
                if credit_name:
                    sales_invoices.append({
                        "name": credit_name,
                        "amount": credit.get("amount")
                    })
            elif credit_doctype == "Payment Entry":
                if credit_name:
                    payment_entries.append({
                        "name": credit_name,
                        "amount": credit.get("amount")
                    })

    # 1. Apply Credit Notes (Return Invoices) -> Create Journal Entry
    for credit_inv in sales_invoices:
        je = _create_credit_allocation_journal_entry(
            invoice_doc,
            credit_inv["name"],
            credit_inv["amount"]
        )
        created_docs.append(je)

    # 2. Apply Advances (Payment Entries) -> Reconcile Payment Entry
    for advance in payment_entries:
        pe = _reconcile_payment_entry(
            invoice_doc,
            advance["name"],
            advance["amount"]
        )
        created_docs.append(pe)

    return created_docs


def _create_credit_allocation_journal_entry(invoice_doc, original_invoice_name, amount):
    """
    Create Journal Entry to allocate credit from one invoice to another.
    """
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Credit Note"
    je.company = invoice_doc.company
    je.posting_date = nowdate()

    # Debit the Customer (reduce credit balance) - Linked to Return Invoice
    je.append("accounts", {
        "account": invoice_doc.debit_to,
        "party_type": "Customer",
        "party": invoice_doc.customer,
        "debit_in_account_currency": amount,
        "reference_type": "Sales Invoice",
        "reference_name": original_invoice_name,
        "cost_center": invoice_doc.cost_center or frappe.get_cached_value('Company', invoice_doc.company, 'cost_center')
    })

    # Credit the Customer (reduce debit balance) - Linked to New Invoice
    je.append("accounts", {
        "account": invoice_doc.debit_to,
        "party_type": "Customer",
        "party": invoice_doc.customer,
        "credit_in_account_currency": amount,
        "reference_type": "Sales Invoice",
        "reference_name": invoice_doc.name,
        "cost_center": invoice_doc.cost_center or frappe.get_cached_value('Company', invoice_doc.company, 'cost_center')
    })

    je.save()
    je.submit()
    return je.name


def _reconcile_payment_entry(invoice_doc, payment_entry_name, amount):
    """
    Allocate payment entry amount to the invoice
    """
    pe = frappe.get_doc("Payment Entry", payment_entry_name)

    # Append invoice to references
    pe.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": invoice_doc.name,
        "total_amount": invoice_doc.grand_total,
        "outstanding_amount": invoice_doc.outstanding_amount,
        "allocated_amount": amount
    })

    pe.save()
    pe.submit()
    return pe.name


def cancel_credit_journal_entries(invoice_name):
    """
    Cancel any credit journal entries linked to a Sales Invoice when it is cancelled.
    Restored logic to prevent accounting discrepancies.
    """
    # Find Journal Entries where this invoice is referenced in credit side (payment application)
    # The Journal Entry would have been created by _create_credit_allocation_journal_entry
    # It links to the invoice in "reference_name" of one of the rows.

    # We look for submitted Journal Entries
    jes = frappe.db.sql("""
        SELECT parent
        FROM `tabJournal Entry Account`
        WHERE reference_type = "Sales Invoice"
        AND reference_name = %s
        AND docstatus = 1
    """, (invoice_name,), as_dict=1)

    cancelled_count = 0
    for row in jes:
        je_name = row.parent
        # Verify if this is indeed a credit allocation JE (optional check)
        if frappe.db.get_value("Journal Entry", je_name, "voucher_type") == "Credit Note":
            try:
                je = frappe.get_doc("Journal Entry", je_name)
                je.cancel()
                cancelled_count += 1
            except Exception as e:
                frappe.log_error(f"Failed to cancel credit JE {je_name} for invoice {invoice_name}: {str(e)}")

    return cancelled_count


@frappe.whitelist()
def get_credit_sale_summary(pos_profile):
    """
    Get summary of credit sales for a POS Profile.
    Returns total outstanding amount and count of unpaid invoices.
    """
    filters = {
        "outstanding_amount": [">", 0],
        "docstatus": 1,
        "is_pos": 1
    }

    if pos_profile:
        filters["pos_profile"] = pos_profile

    summary = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["count(name) as count", "sum(outstanding_amount) as total"]
    )

    return {
        "total_outstanding": summary[0].total if summary else 0.0,
        "invoice_count": summary[0].count if summary else 0
    }


@frappe.whitelist()
def get_credit_invoices(pos_profile, limit=100):
    """
    Get list of outstanding credit invoices for this POS Profile's customers.
    """
    # Refactored from raw SQL to ORM for better security and maintainability
    filters = {
        "outstanding_amount": [">", 0],
        "docstatus": 1,
        "is_pos": 1
    }

    if pos_profile:
        filters["pos_profile"] = pos_profile

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["name", "customer", "posting_date", "grand_total", "outstanding_amount", "due_date"],
        order_by="posting_date desc",
        limit=limit
    )

    return invoices
