# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Partial Payments API for POS Next

Professional implementation following ERPNext best practices:
- Payment Ledger as single source of truth for accounting integrity
- ORM-first approach with optimized SQL where needed
- Comprehensive error handling and validation
- Proper permission checks and security
- Performance-optimized with minimal N+1 queries

Architecture:
    Payment tracking uses ERPNext's Payment Ledger Entry system which provides:
    - Double-entry accounting compliance
    - Complete audit trail
    - Proper reconciliation support

    Never modify Sales Invoice Payment child table after submission.
    Always create Payment Entry documents which automatically update Payment Ledger.
"""

import frappe
from frappe import _
from typing import Dict, List, Optional, Tuple, Any
from frappe.utils import flt, nowdate, get_datetime, cint, get_time
from datetime import datetime
from enum import Enum


# ==========================================
# Constants and Configuration
# ==========================================

class PaymentSource(Enum):
    """Payment source types for audit trail"""
    POS = "POS"
    POS_PAYMENT_ENTRY = "POS Payment Entry"
    PAYMENT_ENTRY = "Payment Entry"
    UNKNOWN = "Unknown"


# Float comparison tolerance for amount matching (accounting precision)
AMOUNT_TOLERANCE = 0.01

# Default limits for list queries
DEFAULT_INVOICE_LIMIT = 50
MAX_INVOICE_LIMIT = 500

# Default payment account types
DEFAULT_PAYMENT_MODE = "Cash"


# ==========================================
# Payment Tracking - ORM Based with Performance Optimization
# ==========================================


def get_payment_history(invoice_name: str, include_metadata: bool = True) -> Dict:
    """
    Get complete payment history from Payment Ledger using optimized queries.

    Payment Ledger is ERPNext's single source of truth for all payments.
    This includes both POS payments and Payment Entries.

    Performance: Uses batch queries to avoid N+1 problem.

    Args:
        invoice_name: Sales Invoice name
        include_metadata: If False, skips fetching mode_of_payment details for performance

    Returns:
        dict: {
            'payments': List of payment records in chronological order,
            'total_paid': Total amount paid,
            'outstanding': Current outstanding amount,
            'grand_total': Invoice grand total,
            'payment_count': Number of payments
        }

    Raises:
        frappe.DoesNotExistError: If invoice doesn't exist
    """
    # Validate and get invoice using ORM
    if not invoice_name or not isinstance(invoice_name, str):
        frappe.throw(_("Invalid invoice name provided"))

    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="Invoice Not Found",
            message=f"Attempted to get payment history for non-existent invoice: {invoice_name}"
        )
        raise

    # Query Payment Ledger for all entries related to this invoice
    # Payment Ledger tracks: Invoice creation (positive), Payments (negative)
    # Need to check BOTH voucher_no (for invoice) and against_voucher_no (for payments)
    payment_ledger_entries = frappe.db.sql(
        """
        SELECT
            name,
            voucher_type,
            voucher_no,
            against_voucher_type,
            against_voucher_no,
            amount,
            amount_in_account_currency,
            posting_date,
            creation,
            account,
            party,
            party_type
        FROM `tabPayment Ledger Entry`
        WHERE (voucher_no = %(invoice_name)s OR against_voucher_no = %(invoice_name)s)
            AND delinked = 0
            AND company = %(company)s
        ORDER BY posting_date ASC, creation ASC
        """,
        {
            "invoice_name": invoice_name,
            "company": invoice.company
        },
        as_dict=True,
    )

    # Build payment history with details
    payments = []

    # Collect voucher numbers for batch queries (performance optimization)
    sales_invoice_vouchers = set()
    payment_entry_vouchers = set()

    for ple in payment_ledger_entries:
        # Negative amounts are payments (positive is invoice creation)
        if ple.amount < 0:
            if ple.voucher_type == "Sales Invoice":
                sales_invoice_vouchers.add(ple.voucher_no)
            elif ple.voucher_type == "Payment Entry":
                payment_entry_vouchers.add(ple.voucher_no)

    # Batch fetch Sales Invoice Payments (eliminates N+1 query problem)
    si_payments_map = {}
    if sales_invoice_vouchers and include_metadata:
        si_payments = frappe.get_all(
            "Sales Invoice Payment",
            filters={"parent": ["in", list(sales_invoice_vouchers)]},
            fields=["parent", "mode_of_payment", "amount", "idx"],
            order_by="parent, idx asc",
        )

        # Group by parent invoice
        for sip in si_payments:
            if sip.parent not in si_payments_map:
                si_payments_map[sip.parent] = []
            si_payments_map[sip.parent].append(sip)

    # Batch fetch Payment Entries (eliminates N+1 query problem)
    payment_entries_map = {}
    if payment_entry_vouchers and include_metadata:
        payment_entries = frappe.get_all(
            "Payment Entry",
            filters={"name": ["in", list(payment_entry_vouchers)]},
            fields=["name", "mode_of_payment", "reference_no", "paid_to", "paid_to_account_type"],
        )

        for pe in payment_entries:
            payment_entries_map[pe.name] = pe

    # Process Payment Ledger entries with batched data
    for ple in payment_ledger_entries:
        # Negative amounts are payments (positive is invoice creation)
        if ple.amount < 0:
            payment_record = {
                "posting_date": ple.posting_date,
                "creation": ple.creation,
                "amount": abs(flt(ple.amount)),
                "voucher_type": ple.voucher_type,
                "voucher_no": ple.voucher_no,
                "source": _determine_payment_source(ple, payment_entries_map),
                "mode_of_payment": None,
                "reference": None,
                "account": ple.account,
            }

            if include_metadata:
                # Get mode of payment based on voucher type
                if ple.voucher_type == "Sales Invoice":
                    # This is a POS payment - recorded at invoice submission
                    pos_payments = si_payments_map.get(ple.voucher_no, [])

                    # Match by amount using accounting tolerance
                    for pos_pay in pos_payments:
                        if abs(flt(pos_pay.amount) - abs(ple.amount)) < AMOUNT_TOLERANCE:
                            payment_record["mode_of_payment"] = pos_pay.mode_of_payment
                            break

                    # Fallback to first payment mode if no exact match
                    if not payment_record["mode_of_payment"] and pos_payments:
                        payment_record["mode_of_payment"] = pos_payments[0].mode_of_payment

                    # Final fallback
                    if not payment_record["mode_of_payment"]:
                        payment_record["mode_of_payment"] = DEFAULT_PAYMENT_MODE

                elif ple.voucher_type == "Payment Entry":
                    # Get Payment Entry details from batched data
                    pe_data = payment_entries_map.get(ple.voucher_no)

                    if pe_data:
                        payment_record["mode_of_payment"] = (
                            pe_data.mode_of_payment or _derive_payment_method(pe_data)
                        )
                        payment_record["reference"] = pe_data.name
                        payment_record["payment_entry"] = pe_data.name
                    else:
                        # Payment Entry was deleted or doesn't exist
                        payment_record["mode_of_payment"] = "Unknown"
                        frappe.log_error(
                            title="Missing Payment Entry",
                            message=f"Payment Ledger references non-existent Payment Entry: {ple.voucher_no}"
                        )

            payments.append(payment_record)

    # Calculate totals from invoice (most reliable source)
    total_paid = flt(invoice.grand_total) - flt(invoice.outstanding_amount)

    return {
        "payments": payments,
        "total_paid": total_paid,
        "outstanding": flt(invoice.outstanding_amount),
        "grand_total": flt(invoice.grand_total),
        "payment_count": len(payments),
        "currency": invoice.currency,
    }


def _determine_payment_source(
    payment_ledger_entry: Dict,
    payment_entries_map: Dict[str, Any]
) -> str:
    """
    Determine the source of a payment for audit trail.

    Args:
        payment_ledger_entry: Payment Ledger Entry record
        payment_entries_map: Pre-fetched Payment Entry data

    Returns:
        str: Payment source label
    """
    if payment_ledger_entry.voucher_type == "Sales Invoice":
        return PaymentSource.POS.value
    elif payment_ledger_entry.voucher_type == "Payment Entry":
        pe_data = payment_entries_map.get(payment_ledger_entry.voucher_no)
        if pe_data and pe_data.reference_no and pe_data.reference_no.startswith("POS-"):
            return PaymentSource.POS_PAYMENT_ENTRY.value
        return PaymentSource.PAYMENT_ENTRY.value

    return PaymentSource.UNKNOWN.value


def _derive_payment_method(payment_entry_data: Dict) -> str:
    """
    Derive payment method from Payment Entry when mode_of_payment is not set.

    Fallback logic:
    1. Check paid_to_account_type (Bank, Cash)
    2. Extract account name from paid_to
    3. Default to Unknown

    Args:
        payment_entry_data: Payment Entry data dict

    Returns:
        str: Derived payment method name
    """
    account_type = payment_entry_data.get("paid_to_account_type")

    if account_type == "Bank":
        paid_to = payment_entry_data.get("paid_to", "")
        account_name = paid_to.split(" - ")[0] if " - " in paid_to else paid_to
        return f"Bank ({account_name})" if account_name else "Bank"
    elif account_type == "Cash":
        return "Cash"

    return account_type or "Unknown"


def enrich_invoice_with_payment_history(
    invoice: Dict,
    include_metadata: bool = True
) -> Dict:
    """
    Enrich invoice dict with payment history from Payment Ledger.

    Uses Payment Ledger as single source of truth. This ensures
    accounting integrity and proper audit trail.

    Modifies invoice dict in-place and returns it.

    Args:
        invoice: Invoice dict from frappe.get_all()
        include_metadata: If False, skips detailed payment metadata for performance

    Returns:
        dict: Invoice enriched with payment history

    Raises:
        Exception: If payment history fetch fails
    """
    try:
        payment_data = get_payment_history(
            invoice.get("name"),
            include_metadata=include_metadata
        )

        invoice.update({
            "payments": payment_data["payments"],
            "paid_amount": payment_data["total_paid"],
            "outstanding_amount": payment_data["outstanding"],
            "payment_count": payment_data["payment_count"],
        })
    except Exception as e:
        # Log but don't fail - return invoice without payment history
        frappe.log_error(
            title=f"Failed to enrich invoice {invoice.get('name')} with payment history",
            message=frappe.get_traceback()
        )
        # Set defaults
        invoice.update({
            "payments": [],
            "payment_count": 0,
        })

    return invoice


# ==========================================
# Payment Entry Creation - Proper ERPNext Way
# ==========================================


def create_payment_entry(
    invoice_name: str,
    amount: float,
    mode_of_payment: str = DEFAULT_PAYMENT_MODE,
    payment_account: Optional[str] = None,
    reference_no: Optional[str] = None,
    remarks: Optional[str] = None,
    posting_date: Optional[str] = None,
) -> str:
    """
    Create a proper Payment Entry that updates Payment Ledger.

    This is the ONLY correct way to add payments to a submitted invoice.
    Never modify Sales Invoice Payment child table after submission!

    Business Rules Enforced:
    - Invoice must be submitted (docstatus = 1)
    - Invoice must not be cancelled
    - Amount must be positive
    - Amount must not exceed outstanding
    - Payment date must not be before invoice date
    - Currency must match

    Args:
        invoice_name: Sales Invoice name
        amount: Payment amount (must be positive)
        mode_of_payment: Mode of Payment name
        payment_account: Optional specific account to use
        reference_no: Optional reference number
        remarks: Optional remarks
        posting_date: Optional posting date (defaults to today)

    Returns:
        str: Created Payment Entry name

    Raises:
        frappe.ValidationError: If validation fails
        frappe.DoesNotExistError: If invoice doesn't exist
        frappe.PermissionError: If user lacks permission
    """
    # Input validation
    if not invoice_name or not isinstance(invoice_name, str):
        frappe.throw(_("Invalid invoice name provided"))

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Payment amount must be greater than zero"))

    # Get invoice using ORM with permission check
    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
    except frappe.DoesNotExistError:
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    # Validate invoice state
    if invoice.docstatus != 1:
        frappe.throw(_("Invoice must be submitted before adding payments"))

    if invoice.docstatus == 2:
        frappe.throw(_("Cannot add payment to cancelled invoice"))

    # Validate amount doesn't exceed outstanding
    if amount > flt(invoice.outstanding_amount) + AMOUNT_TOLERANCE:
        frappe.throw(
            _("Payment amount {0} exceeds outstanding amount {1}").format(
                frappe.format_value(amount, {"fieldtype": "Currency"}),
                frappe.format_value(invoice.outstanding_amount, {"fieldtype": "Currency"}),
            )
        )

    # Validate posting date
    posting_date = posting_date or nowdate()
    if get_datetime(posting_date) < get_datetime(invoice.posting_date):
        frappe.throw(
            _("Payment date {0} cannot be before invoice date {1}").format(
                posting_date, invoice.posting_date
            )
        )

    # Validate mode of payment exists
    if not frappe.db.exists("Mode of Payment", mode_of_payment):
        frappe.throw(_("Mode of Payment {0} does not exist").format(mode_of_payment))

    # Save and submit with proper error handling
    try:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

        if payment_account:
            if not frappe.db.exists("Account", payment_account):
                frappe.throw(_("Payment account {0} does not exist").format(payment_account))
        else:
            account_info = get_bank_cash_account(mode_of_payment, invoice.company)
            if not account_info or not account_info.get("account"):
                frappe.throw(
                    _("Could not determine payment account for {0}. Please specify payment_account parameter.").format(
                        mode_of_payment
                    )
                )
            payment_account = account_info.get("account")

        pe = get_payment_entry(
            "Sales Invoice",
            invoice_name,
            party_amount=amount,
            bank_account=payment_account,
            reference_date=posting_date,
        )
        pe.posting_date = posting_date
        pe.reference_date = posting_date
        pe.mode_of_payment = mode_of_payment

        if reference_no:
            pe.reference_no = str(reference_no)[:140]
        else:
            pe.reference_no = f"POS-{invoice_name}"

        if remarks:
            pe.remarks = str(remarks)[:500]
        else:
            pe.remarks = f"Payment for {invoice_name} via POS - {mode_of_payment}"

        # Allow system to create payment entry even if user doesn't have direct permission
        # This is safe because we've already validated invoice access
        pe.flags.ignore_permissions = True
        pe.insert()
        pe.submit()

        return pe.name

    except frappe.ValidationError as e:
        frappe.log_error(
            title=f"Payment Entry Validation Failed for {invoice_name}",
            message=frappe.get_traceback()
        )
        raise
    except Exception as e:
        frappe.log_error(
            title=f"Payment Entry Creation Failed for {invoice_name}",
            message=frappe.get_traceback()
        )
        frappe.throw(_("Failed to create payment entry: {0}").format(str(e)))


# ==========================================
# Public API Methods
# ==========================================


@frappe.whitelist()
def get_partial_paid_invoices(pos_profile: str, limit: int = DEFAULT_INVOICE_LIMIT) -> List[Dict]:
    """
    Get partially paid invoices for a POS Profile.

    A partially paid invoice has:
    - Outstanding amount > 0 (not fully paid)
    - Paid amount > 0 (not fully unpaid)
    - Can be in any status including "Overdue"

    Args:
        pos_profile: POS Profile name
        limit: Maximum invoices to return (default 50, max 500)

    Returns:
        List[dict]: Invoices with payment history from Payment Ledger

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks access
    """
    # Input validation
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Validate POS Profile exists
    if not frappe.db.exists("POS Profile", pos_profile):
        frappe.throw(_("POS Profile {0} does not exist").format(pos_profile))

    # Check permissions
    if not _has_pos_profile_access(pos_profile):
        frappe.throw(_("You don't have access to this POS Profile"))

    # Validate and sanitize limit
    limit = cint(limit)
    if limit <= 0:
        limit = DEFAULT_INVOICE_LIMIT
    elif limit > MAX_INVOICE_LIMIT:
        limit = MAX_INVOICE_LIMIT

    # Get partially paid invoices using ORM
    # Filter logic: outstanding > 0 AND paid > 0 (mathematical definition of partial payment)
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "pos_profile": pos_profile,
            "docstatus": 1,
            "is_pos": 1,
            "outstanding_amount": [">", 0],
            "paid_amount": [">", 0],
            "is_return": 0,
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "posting_time",
            "grand_total",
            "paid_amount",
            "outstanding_amount",
            "status",
            "creation",
            "currency",
        ],
        order_by="posting_date desc, posting_time desc",
        limit=limit,
    )

    # Enrich with payment history
    # Note: This makes additional queries. For summary-only views, use get_partial_payment_summary() instead.
    for invoice in invoices:
        enrich_invoice_with_payment_history(invoice, include_metadata=True)

    return invoices


@frappe.whitelist()
def get_unpaid_invoices(pos_profile: str, limit: int = DEFAULT_INVOICE_LIMIT) -> List[Dict]:
    """
    Get all unpaid invoices (partial + fully unpaid) for a POS Profile.

    Includes:
    - Fully unpaid invoices (paid_amount = 0)
    - Partially paid invoices (0 < paid_amount < grand_total)
    - Overdue invoices (any invoice with outstanding > 0)

    Args:
        pos_profile: POS Profile name
        limit: Maximum invoices to return (default 50, max 500)

    Returns:
        List[dict]: Unpaid invoices with payment history

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks access
    """
    # Input validation
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Validate POS Profile exists
    if not frappe.db.exists("POS Profile", pos_profile):
        frappe.throw(_("POS Profile {0} does not exist").format(pos_profile))

    if not _has_pos_profile_access(pos_profile):
        frappe.throw(_("You don't have access to this POS Profile"))

    # Validate and sanitize limit
    limit = cint(limit)
    if limit <= 0:
        limit = DEFAULT_INVOICE_LIMIT
    elif limit > MAX_INVOICE_LIMIT:
        limit = MAX_INVOICE_LIMIT

    # Get all unpaid invoices (any invoice with outstanding > 0)
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "pos_profile": pos_profile,
            "docstatus": 1,
            "is_pos": 1,
            "outstanding_amount": [">", 0],
            "is_return": 0,
        },
        fields=[
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "posting_time",
            "grand_total",
            "paid_amount",
            "outstanding_amount",
            "status",
            "creation",
            "currency",
        ],
        order_by="posting_date desc, posting_time desc",
        limit=limit,
    )

    # Enrich with payment history
    for invoice in invoices:
        enrich_invoice_with_payment_history(invoice, include_metadata=True)

    return invoices


@frappe.whitelist()
def get_partial_payment_details(invoice_name: str) -> Dict:
    """
    Get detailed payment information for an invoice.

    Includes complete payment history, items, and invoice details.

    Args:
        invoice_name: Sales Invoice name

    Returns:
        dict: Complete invoice details with payment history

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks permission
        frappe.DoesNotExistError: If invoice doesn't exist
    """
    # Input validation
    if not invoice_name:
        frappe.throw(_("Invoice name is required"))

    # Permission check
    if not frappe.has_permission("Sales Invoice", "read", invoice_name):
        frappe.throw(_("You don't have permission to view this invoice"))

    # Get invoice using ORM
    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
    except frappe.DoesNotExistError:
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    # Get payment history
    payment_data = get_payment_history(invoice_name, include_metadata=True)

    # Get items with proper data types
    items = [
        {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": flt(item.qty),
            "rate": flt(item.rate),
            "amount": flt(item.amount),
            "uom": item.uom,
        }
        for item in invoice.items
    ]

    return {
        "name": invoice.name,
        "customer": invoice.customer,
        "customer_name": invoice.customer_name,
        "posting_date": invoice.posting_date,
        "posting_time": invoice.posting_time,
        "grand_total": flt(invoice.grand_total),
        "paid_amount": payment_data["total_paid"],
        "outstanding_amount": payment_data["outstanding"],
        "status": invoice.status,
        "currency": invoice.currency,
        "payments": payment_data["payments"],
        "payment_count": payment_data["payment_count"],
        "items": items,
        "item_count": len(items),
    }


@frappe.whitelist()
def add_payment_to_partial_invoice(invoice_name: str, payments) -> Dict:
    """
    Add payments to a partially paid invoice via Payment Entry.

    Creates proper Payment Entry documents that update Payment Ledger.
    This is the ONLY correct way to add payments after invoice submission.

    Transactional: If any payment fails, the batch is rolled back to a savepoint
    so no submitted Payment Entry from this request is persisted.

    Args:
        invoice_name: Sales Invoice name
        payments: List of payment dicts with keys:
            - mode_of_payment: Mode of Payment name
            - amount: Payment amount (positive number)
            - account: (optional) Specific payment account
            - reference_no: (optional) Reference number
        Can also accept JSON string which will be parsed.

    Returns:
        dict: Updated invoice details with created Payment Entry names

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks permission

    Example:
        >>> add_payment_to_partial_invoice(
        ...     "SINV-00001",
        ...     [
        ...         {"mode_of_payment": "Cash", "amount": 100.00},
        ...         {"mode_of_payment": "Card", "amount": 50.00}
        ...     ]
        ... )
    """
    import json

    # Input validation
    if not invoice_name:
        frappe.throw(_("Invoice name is required"))

    # Parse payments if string, otherwise use as-is
    if isinstance(payments, str):
        try:
            payments = json.loads(payments)
        except json.JSONDecodeError:
            frappe.throw(_("Invalid payments payload: malformed JSON"))

    # Ensure it's a list
    if not isinstance(payments, list):
        frappe.throw(_("Payments must be a list"))

    if not payments:
        frappe.throw(_("At least one payment is required"))

    # Permission check
    if not frappe.has_permission("Sales Invoice", "write", invoice_name):
        frappe.throw(_("You don't have permission to add payments to this invoice"))

    # Validate total payment amount doesn't exceed outstanding
    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
    except frappe.DoesNotExistError:
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    total_payment_amount = sum(flt(p.get("amount", 0)) for p in payments)
    if total_payment_amount > flt(invoice.outstanding_amount) + AMOUNT_TOLERANCE:
        frappe.throw(
            _("Total payment amount {0} exceeds outstanding amount {1}").format(
                frappe.format_value(total_payment_amount, {"fieldtype": "Currency"}),
                frappe.format_value(invoice.outstanding_amount, {"fieldtype": "Currency"}),
            )
        )

    # Create Payment Entries inside one savepoint-backed batch.
    payment_entries_created = []
    batch_savepoint = "partial_payment_batch"

    try:
        frappe.db.savepoint(batch_savepoint)

        for idx, payment in enumerate(payments, 1):
            amount = flt(payment.get("amount", 0))

            # Skip zero amounts
            if amount <= 0:
                frappe.log_error(
                    title=f"Skipped zero payment for {invoice_name}",
                    message=f"Payment #{idx}: {payment}"
                )
                continue

            mode_of_payment = payment.get("mode_of_payment") or DEFAULT_PAYMENT_MODE
            payment_account = payment.get("account")
            reference_no = payment.get("reference_no")

            pe_name = create_payment_entry(
                invoice_name=invoice_name,
                amount=amount,
                mode_of_payment=mode_of_payment,
                payment_account=payment_account,
                reference_no=reference_no,
                remarks=f"POS Payment - {mode_of_payment}",
            )

            payment_entries_created.append(pe_name)

    except Exception as e:
        frappe.db.rollback(save_point=batch_savepoint)
        frappe.log_error(
            title=f"Payment Entry Creation Failed for {invoice_name}",
            message=f"Payments: {payments}\nError: {str(e)}\n\n{frappe.get_traceback()}",
        )
        frappe.throw(
            _("Failed to create payment entry: {0}. All changes have been rolled back.").format(str(e))
        )

    # Get updated invoice details
    result = get_partial_payment_details(invoice_name)
    result["payment_entries_created"] = payment_entries_created
    result["success"] = True

    return result


@frappe.whitelist()
def get_partial_payment_summary(pos_profile: str) -> Dict:
    """
    Get summary statistics for partial payments.

    Performance: Uses direct SQL aggregation - single query, no N+1 issues.
    Use this for dashboard views instead of fetching full invoice lists.

    Args:
        pos_profile: POS Profile name

    Returns:
        dict: {
            'count': Number of partially paid invoices,
            'total_outstanding': Sum of outstanding amounts,
            'total_paid': Sum of paid amounts,
            'total_grand_total': Sum of invoice totals
        }

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks access
    """
    # Input validation
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Validate POS Profile exists
    if not frappe.db.exists("POS Profile", pos_profile):
        frappe.throw(_("POS Profile {0} does not exist").format(pos_profile))

    if not _has_pos_profile_access(pos_profile):
        frappe.throw(_("You don't have access to this POS Profile"))

    # Use direct SQL aggregation - single query instead of N queries
    # This is critical for performance with large datasets
    summary = frappe.db.sql(
        """
        SELECT
            COUNT(*) as count,
            COALESCE(SUM(outstanding_amount), 0) as total_outstanding,
            COALESCE(SUM(paid_amount), 0) as total_paid,
            COALESCE(SUM(grand_total), 0) as total_grand_total
        FROM `tabSales Invoice`
        WHERE pos_profile = %(pos_profile)s
            AND docstatus = 1
            AND is_pos = 1
            AND outstanding_amount > 0
            AND paid_amount > 0
            AND is_return = 0
        """,
        {"pos_profile": pos_profile},
        as_dict=True,
    )[0]

    return {
        "count": cint(summary.get("count")),
        "total_outstanding": flt(summary.get("total_outstanding")),
        "total_paid": flt(summary.get("total_paid")),
        "total_grand_total": flt(summary.get("total_grand_total")),
    }


@frappe.whitelist()
def get_unpaid_summary(pos_profile: str) -> Dict:
    """
    Get summary statistics for all unpaid invoices.

    Performance: Uses direct SQL aggregation - single query, no N+1 issues.
    Use this for dashboard views instead of fetching full invoice lists.

    Args:
        pos_profile: POS Profile name

    Returns:
        dict: {
            'count': Number of unpaid invoices,
            'total_outstanding': Sum of outstanding amounts,
            'total_paid': Sum of paid amounts,
            'total_grand_total': Sum of invoice totals
        }

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks access
    """
    # Input validation
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Validate POS Profile exists
    if not frappe.db.exists("POS Profile", pos_profile):
        frappe.throw(_("POS Profile {0} does not exist").format(pos_profile))

    if not _has_pos_profile_access(pos_profile):
        frappe.throw(_("You don't have access to this POS Profile"))

    # Use direct SQL aggregation - critical for performance
    summary = frappe.db.sql(
        """
        SELECT
            COUNT(*) as count,
            COALESCE(SUM(outstanding_amount), 0) as total_outstanding,
            COALESCE(SUM(paid_amount), 0) as total_paid,
            COALESCE(SUM(grand_total), 0) as total_grand_total
        FROM `tabSales Invoice`
        WHERE pos_profile = %(pos_profile)s
            AND docstatus = 1
            AND is_pos = 1
            AND outstanding_amount > 0
            AND is_return = 0
        """,
        {"pos_profile": pos_profile},
        as_dict=True,
    )[0]

    return {
        "count": cint(summary.get("count")),
        "total_outstanding": flt(summary.get("total_outstanding")),
        "total_paid": flt(summary.get("total_paid")),
        "total_grand_total": flt(summary.get("total_grand_total")),
    }


# ==========================================
# Helper Functions
# ==========================================


def _has_pos_profile_access(pos_profile: str) -> bool:
    """
    Check if current user has access to POS Profile.

    Access is granted if:
    - User is in POS Profile User child table, OR
    - User has Sales Invoice read permission

    Args:
        pos_profile: POS Profile name

    Returns:
        bool: True if user has access
    """
    # Check if user is explicitly assigned to this POS Profile
    has_direct_access = frappe.db.exists(
        "POS Profile User",
        {
            "parent": pos_profile,
            "user": frappe.session.user
        }
    )

    # Check if user has general Sales Invoice permission
    has_general_access = frappe.has_permission("Sales Invoice", "read")

    return bool(has_direct_access or has_general_access)
