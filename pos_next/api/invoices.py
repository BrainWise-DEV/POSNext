# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, nowtime, get_datetime, cstr
from erpnext.stock.doctype.batch.batch import get_batch_qty, get_batch_no
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

try:
    from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
        apply_pricing_rule as erpnext_apply_pricing_rule,
    )
    from erpnext.accounts.doctype.pricing_rule.utils import (
        get_applied_pricing_rules as erpnext_get_applied_pricing_rules,
    )
except Exception:  # pragma: no cover - ERPNext not installed in some environments
    erpnext_apply_pricing_rule = None
    erpnext_get_applied_pricing_rules = None


# ==========================================
# Helper Functions
# ==========================================


def get_payment_account(mode_of_payment, company):
    """
    Get account for mode of payment.
    Tries multiple fallback methods to find a suitable account.
    """
    # Try 1: Mode of Payment Account table
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )
    if account:
        return {"account": account}

    # Try 2: POS Payment Method from POS Profile
    account = frappe.db.sql(
        """
		SELECT ppm.default_account
		FROM `tabPOS Payment Method` ppm
		INNER JOIN `tabPOS Profile` pp ON ppm.parent = pp.name
		WHERE ppm.mode_of_payment = %s
		AND pp.company = %s
		AND ppm.default_account IS NOT NULL
		LIMIT 1
	""",
        (mode_of_payment, company),
        as_dict=1,
    )

    if account and account[0].default_account:
        return {"account": account[0].default_account}

    # Try 3: Company default cash account (for cash payments)
    if "cash" in mode_of_payment.lower():
        account = frappe.get_value("Company", company, "default_cash_account")
        if account:
            return {"account": account}

    # Try 4: Company default bank account
    account = frappe.get_value("Company", company, "default_bank_account")
    if account:
        return {"account": account}

    # Try 5: Any Cash/Bank account for the company
    account = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0},
        "name",
    )
    if account:
        return {"account": account}

    # No account found - throw error
    frappe.throw(
        _(
            "Please set default Cash or Bank account in Mode of Payment {0} or set default accounts in Company {1}"
        ).format(mode_of_payment, company),
        title=_("Missing Account"),
    )


# ==========================================
# Stock Validation Functions
# ==========================================


def _get_available_stock(item):
    """Return available stock qty for an item row."""
    warehouse = item.get("warehouse")
    batch_no = item.get("batch_no")
    item_code = item.get("item_code")

    if not item_code or not warehouse:
        return 0

    if batch_no:
        return get_batch_qty(batch_no, warehouse) or 0

    # Get stock from Bin
    bin_qty = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    )
    return flt(bin_qty) or 0


def _collect_stock_errors(items):
    """Return list of items exceeding available stock."""
    errors = []
    for d in items:
        if flt(d.get("qty")) < 0:
            continue

        available = _get_available_stock(d)
        requested = flt(
            d.get("stock_qty")
            or (flt(d.get("qty")) * flt(d.get("conversion_factor") or 1))
        )

        if requested > available:
            errors.append(
                {
                    "item_code": d.get("item_code"),
                    "warehouse": d.get("warehouse"),
                    "requested_qty": requested,
                    "available_qty": available,
                }
            )

    return errors


def _should_block(pos_profile):
    """Check if sale should be blocked for insufficient stock."""
    # First check global ERPNext Stock Settings
    allow_negative = cint(
        frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
    )
    if allow_negative:
        return False

    # Check POS Settings for the specific profile
    if pos_profile:
        # Check if POS Settings allows negative stock
        pos_settings_allow_negative = cint(
            frappe.db.get_value(
                "POS Settings",
                {"pos_profile": pos_profile},
                "allow_negative_stock"
            ) or 0
        )
        if pos_settings_allow_negative:
            return False

        # Try to get custom field (may not exist in vanilla ERPNext)
        block_sale = cint(
            frappe.db.get_value(
                "POS Profile", pos_profile, "posa_block_sale_beyond_available_qty"
            )
            or 1
        )
        return bool(block_sale)

    # Default to blocking if no profile specified
    return True


def _validate_stock_on_invoice(invoice_doc):
    """Validate stock availability before submission."""
    if invoice_doc.doctype == "Sales Invoice" and not cint(
        getattr(invoice_doc, "update_stock", 0)
    ):
        return

    # Collect all stock items to check
    items_to_check = [d.as_dict() for d in invoice_doc.items if d.get("is_stock_item")]

    # Include packed items if present
    if hasattr(invoice_doc, "packed_items"):
        items_to_check.extend([d.as_dict() for d in invoice_doc.packed_items])

    # Check for stock errors
    errors = _collect_stock_errors(items_to_check)

    # Throw error if stock insufficient and blocking is enabled
    if errors and _should_block(invoice_doc.pos_profile):
        frappe.throw(frappe.as_json({"errors": errors}), frappe.ValidationError)


def _auto_set_return_batches(invoice_doc):
    """Assign batch numbers for return invoices without a source invoice.

    When an item requires a batch number, this function allocates the first
    available batch in FIFO order. If no batches exist in the selected
    warehouse, an informative error is raised.
    """
    if not invoice_doc.get("is_return") or invoice_doc.get("return_against"):
        return

    for d in invoice_doc.items:
        if not d.get("item_code") or not d.get("warehouse"):
            continue

        has_batch = frappe.db.get_value("Item", d.item_code, "has_batch_no")
        if has_batch and not d.get("batch_no"):
            batch_list = (
                get_batch_qty(item_code=d.item_code, warehouse=d.warehouse) or []
            )
            batch_list = [b for b in batch_list if flt(b.get("qty")) > 0]

            if batch_list:
                # FIFO: batches are already sorted by posting/expiry in ERPNext
                d.batch_no = batch_list[0].get("batch_no")
            else:
                frappe.throw(
                    _("No batches available in {0} for {1}.").format(
                        d.warehouse, d.item_code
                    )
                )


# ==========================================
# Validation Functions
# ==========================================


@frappe.whitelist()
def validate_cart_items(items, pos_profile=None):
    """Validate cart items for available stock.

    Returns a list of item dicts where requested quantity exceeds availability.
    This can be used on the front-end for pre-submission checks.
    """
    if isinstance(items, str):
        items = json.loads(items)

    if pos_profile and not frappe.db.exists("POS Profile", pos_profile):
        pos_profile = None

    if not _should_block(pos_profile):
        return []

    errors = _collect_stock_errors(items)
    if not errors:
        return []

    return errors


@frappe.whitelist()
def validate_return_items(original_invoice_name, return_items, doctype="Sales Invoice"):
    """Ensure that return items do not exceed the quantity from the original invoice."""
    original_invoice = frappe.get_doc(doctype, original_invoice_name)
    original_item_qty = {}

    for item in original_invoice.items:
        original_item_qty[item.item_code] = (
            original_item_qty.get(item.item_code, 0) + item.qty
        )

    # Get all returned items from this invoice
    returned_items = frappe.get_all(
        doctype,
        filters={
            "return_against": original_invoice_name,
            "docstatus": 1,
            "is_return": 1,
        },
        fields=["name"],
    )

    for returned_invoice in returned_items:
        ret_doc = frappe.get_doc(doctype, returned_invoice.name)
        for item in ret_doc.items:
            if item.item_code in original_item_qty:
                original_item_qty[item.item_code] -= abs(item.qty)

    # Validate new return items
    for item in return_items:
        item_code = item.get("item_code")
        return_qty = abs(item.get("qty", 0))
        if item_code in original_item_qty and return_qty > original_item_qty[item_code]:
            return {
                "valid": False,
                "message": _(
                    "You are trying to return more quantity for item {0} than was sold."
                ).format(item_code),
            }

    return {"valid": True}


# ==========================================
# Invoice Management (Two-Step Flow)
# ==========================================


@frappe.whitelist()
def update_invoice(data):
    """Create or update invoice draft (Step 1)."""
    try:
        data = json.loads(data) if isinstance(data, str) else data

        pos_profile = data.get("pos_profile")
        doctype = data.get("doctype", "Sales Invoice")

        # Ensure the document type is set
        data.setdefault("doctype", doctype)

        # Create or update invoice
        if data.get("name"):
            invoice_doc = frappe.get_doc(doctype, data.get("name"))
            invoice_doc.update(data)
        else:
            invoice_doc = frappe.get_doc(data)

        pos_profile_doc = None
        if pos_profile:
            try:
                pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
            except Exception:
                frappe.throw(_("Unable to load POS Profile {0}").format(pos_profile))

            invoice_doc.pos_profile = pos_profile

            if pos_profile_doc:
                if pos_profile_doc.company and not invoice_doc.get("company"):
                    invoice_doc.company = pos_profile_doc.company
                if pos_profile_doc.currency and not invoice_doc.get("currency"):
                    invoice_doc.currency = pos_profile_doc.currency

                # Copy accounting dimensions from POS Profile
                if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
                    invoice_doc.branch = pos_profile_doc.branch
                    # Also set branch on all items for GL entries
                    for item in invoice_doc.get("items", []):
                        item.branch = pos_profile_doc.branch

        company = invoice_doc.get("company") or (
            pos_profile_doc.company if pos_profile_doc else None
        )

        if company and invoice_doc.get("payments") and doctype == "Sales Invoice":
            for payment in invoice_doc.payments:
                mode_of_payment = payment.get("mode_of_payment")
                if mode_of_payment and not payment.get("account"):
                    try:
                        account_info = get_payment_account(
                            mode_of_payment, company
                        )
                        if account_info:
                            payment["account"] = account_info.get("account")
                    except Exception:
                        pass  # Will be handled during save

        # Validate return items if this is a return invoice
        if (data.get("is_return") or invoice_doc.get("is_return")) and invoice_doc.get(
            "return_against"
        ):
            validation = validate_return_items(
                invoice_doc.return_against,
                [d.as_dict() for d in invoice_doc.items],
                doctype=invoice_doc.doctype,
            )
            if not validation.get("valid"):
                frappe.throw(validation.get("message"))

        # Ensure customer exists
        customer_name = invoice_doc.get("customer")
        if customer_name and not frappe.db.exists("Customer", customer_name):
            try:
                cust = frappe.get_doc(
                    {
                        "doctype": "Customer",
                        "customer_name": customer_name,
                        "customer_group": "All Customer Groups",
                        "territory": "All Territories",
                        "customer_type": "Individual",
                    }
                )
                cust.flags.ignore_permissions = True
                cust.insert()
                invoice_doc.customer = cust.name
                invoice_doc.customer_name = cust.customer_name
            except Exception as e:
                frappe.log_error(f"Failed to create customer {customer_name}: {e}")

        # Disable automatic pricing rules (we handle discounts manually from POS)
        invoice_doc.ignore_pricing_rule = 1
        invoice_doc.flags.ignore_pricing_rule = True

        # ========================================================================
        # DISCOUNT CALCULATION - CRITICAL LOGIC
        # ========================================================================
        # Problem: Frontend sends rate (discounted) and discount_percentage
        # Solution: Reverse-calculate price_list_rate (original price) to avoid double discount
        #
        # Formula: rate = price_list_rate * (1 - discount_percentage/100)
        # Reverse: price_list_rate = rate / (1 - discount_percentage/100)
        # ========================================================================
        for item in invoice_doc.get("items", []):
            item_rate = flt(item.rate or 0)
            discount_pct = flt(item.discount_percentage or 0)

            # If item has a discount, reverse-calculate the original price_list_rate
            if discount_pct > 0 and discount_pct < 100:
                if item_rate > 0:
                    # Reverse calculation to get original price
                    item.price_list_rate = item_rate / (1 - discount_pct / 100)
                elif not item.get("price_list_rate"):
                    # Fallback: if rate is 0 but discount exists (edge case)
                    item.price_list_rate = item_rate
            elif not item.get("price_list_rate"):
                # No discount or price_list_rate not set - use rate as is
                item.price_list_rate = item_rate

            # Ensure price_list_rate is never less than rate (data integrity)
            if flt(item.price_list_rate) < item_rate:
                item.price_list_rate = item_rate

            # IMPORTANT: Keep the rate from frontend (do NOT set to 0)
            # ERPNext will recalculate if needed, but preserving frontend rate
            # prevents rounding issues and ensures UI matches invoice

        # Set invoice flags BEFORE calculations
        if doctype == "Sales Invoice":
            invoice_doc.is_pos = 1
            invoice_doc.update_stock = 1

        # ========================================================================
        # ROUNDING CONFIGURATION
        # ========================================================================
        # Load rounding preference from POS Settings
        # When disabled (0): ERPNext rounds to nearest whole number
        # When enabled (1): Shows exact amount without rounding
        # ========================================================================
        disable_rounded = 1  # Default: disable rounding for POS (show exact amounts)

        if pos_profile:
            try:
                pos_settings_value = frappe.db.get_value(
                    "POS Settings",
                    {"pos_profile": pos_profile},
                    "disable_rounded_total"
                )
                if pos_settings_value is not None:
                    disable_rounded = cint(pos_settings_value)
            except Exception as e:
                # Log error but continue with default
                frappe.log_error(f"Error loading rounding setting: {str(e)}", "POS Invoice Creation")

        invoice_doc.disable_rounded_total = disable_rounded

        # Populate missing fields (company, currency, accounts, etc.)
        invoice_doc.set_missing_values()

        # Calculate totals and apply discounts (with rounding disabled)
        invoice_doc.calculate_taxes_and_totals()
        if invoice_doc.grand_total is None:
            invoice_doc.grand_total = 0.0
        if invoice_doc.base_grand_total is None:
            invoice_doc.base_grand_total = 0.0

        # Set accounts for payment methods before saving
        for payment in invoice_doc.payments:
            mode_of_payment = payment.get("mode_of_payment")
            if mode_of_payment and not payment.get("account"):
                try:
                    account_info = get_payment_account(
                        mode_of_payment, invoice_doc.company
                    )
                    if account_info:
                        payment.account = account_info.get("account")
                except Exception:
                    pass  # Will be handled during save

        # For return invoices, ensure payments are negative
        if invoice_doc.get("is_return"):
            # Return handling is primarily for Sales Invoice
            if doctype == "Sales Invoice" and invoice_doc.get("payments"):
                for payment in invoice_doc.payments:
                    payment.amount = -abs(payment.amount)
                    if payment.base_amount:
                        payment.base_amount = -abs(payment.base_amount)

                invoice_doc.paid_amount = flt(sum(p.amount for p in invoice_doc.payments))
                invoice_doc.base_paid_amount = flt(
                    sum(p.base_amount or 0 for p in invoice_doc.payments)
                )

        # Validate and track POS Coupon if coupon_code is provided
        coupon_code = data.get("coupon_code")
        if coupon_code:
            # Validate POS Coupon exists and is valid
            if frappe.db.table_exists("POS Coupon"):
                from pos_next.pos_next.doctype.pos_coupon.pos_coupon import check_coupon_code

                coupon_result = check_coupon_code(
                    coupon_code,
                    customer=invoice_doc.customer,
                    company=invoice_doc.company
                )

                if not coupon_result or not coupon_result.get("valid"):
                    error_msg = coupon_result.get("msg", "Invalid coupon code") if coupon_result else "Invalid coupon code"
                    frappe.throw(_(error_msg))

                # Store coupon code on invoice for tracking
                invoice_doc.coupon_code = coupon_code

        # Save as draft
        invoice_doc.flags.ignore_permissions = True
        frappe.flags.ignore_account_permission = True
        invoice_doc.docstatus = 0
        invoice_doc.save()

        return invoice_doc.as_dict()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Invoice Error")
        raise


PENDING_TIMEOUT_MINUTES = 5  # Pending records older than this are considered stale


def _is_pending_expired(modified_time):
    """Check if a pending record has expired based on modified time."""
    if not modified_time:
        return True  # No timestamp means treat as expired
    age_minutes = (frappe.utils.now_datetime() - modified_time).total_seconds() / 60
    return age_minutes > PENDING_TIMEOUT_MINUTES


def _reuse_sync_record(sync_record_name):
    """Reset an existing sync record to Pending status for retry."""
    sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
    sync_doc.status = "Pending"
    sync_doc.synced_at = None
    sync_doc.flags.ignore_permissions = True
    sync_doc.save()
    return {"already_synced": False, "sync_record_name": sync_record_name}


def _handle_offline_deduplication(offline_id, pos_profile=None, customer=None):
    """
    Handle offline invoice deduplication with race condition protection.

    Uses a reservation pattern:
    1. Check if a sync record exists (with row-level lock)
    2. If synced with valid invoice, return existing invoice
    3. If synced but invoice deleted/invalid, allow retry
    4. If pending but expired (>5 min), allow retry
    5. If pending and active, reject (another request processing)
    6. If failed, allow retry
    7. If not exists, create pending reservation

    Args:
        offline_id: The unique offline ID from the client
        pos_profile: POS Profile name
        customer: Customer name

    Returns:
        dict with:
        - already_synced (bool): True if invoice was already synced
        - invoice_data (dict): Existing invoice data if already_synced
        - sync_record_name (str): Name of the sync record for this attempt
    """
    # Acquire row-level lock to prevent race conditions
    existing_sync = frappe.db.get_value(
        "Offline Invoice Sync",
        {"offline_id": offline_id},
        ["name", "sales_invoice", "status", "modified"],
        as_dict=True,
        for_update=True
    )

    if existing_sync:
        sync_status = existing_sync.get("status")
        sync_record_name = existing_sync.name

        # Handle Pending status
        if sync_status == "Pending":
            if _is_pending_expired(existing_sync.get("modified")):
                # Expired pending - allow retry
                return _reuse_sync_record(sync_record_name)
            else:
                # Active pending - reject with specific error code
                frappe.throw(
                    _("This invoice is currently being processed. Please wait."),
                    exc=frappe.ValidationError,
                    title="SYNC_IN_PROGRESS"
                )

        # Handle Failed status - allow retry
        if sync_status == "Failed":
            return _reuse_sync_record(sync_record_name)

        # Handle Synced status - verify invoice still valid
        if sync_status == "Synced" and existing_sync.sales_invoice:
            if frappe.db.exists("Sales Invoice", existing_sync.sales_invoice):
                existing_invoice = frappe.get_doc("Sales Invoice", existing_sync.sales_invoice)
                if existing_invoice.docstatus == 1:
                    return {
                        "already_synced": True,
                        "invoice_data": {
                            "name": existing_invoice.name,
                            "status": existing_invoice.docstatus,
                            "grand_total": existing_invoice.grand_total,
                            "total": existing_invoice.total,
                            "net_total": existing_invoice.net_total,
                            "outstanding_amount": getattr(existing_invoice, "outstanding_amount", 0),
                            "paid_amount": getattr(existing_invoice, "paid_amount", 0),
                            "change_amount": getattr(existing_invoice, "change_amount", 0),
                            "duplicate_prevented": True,
                            "offline_id": offline_id,
                        }
                    }

            # Synced record points to deleted/invalid invoice - allow retry
            return _reuse_sync_record(sync_record_name)

        # Unknown status or synced without invoice - allow retry
        return _reuse_sync_record(sync_record_name)

    # No existing record - create pending reservation
    try:
        pending_sync = frappe.get_doc({
            "doctype": "Offline Invoice Sync",
            "offline_id": offline_id,
            "sales_invoice": "",
            "pos_profile": pos_profile,
            "customer": customer,
            "status": "Pending",
        })
        pending_sync.flags.ignore_permissions = True
        pending_sync.insert()

        return {
            "already_synced": False,
            "sync_record_name": pending_sync.name
        }
    except frappe.DuplicateEntryError:
        # Race condition: another request just created the record
        # Retry the check to get the new record
        return _handle_offline_deduplication(offline_id, pos_profile, customer)


def _complete_offline_sync(sync_record_name, invoice_name):
    """
    Mark an offline sync record as completed after successful invoice submission.

    Args:
        sync_record_name: Name of the Offline Invoice Sync record
        invoice_name: Name of the submitted Sales Invoice
    """
    if not sync_record_name:
        return

    try:
        sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
        sync_doc.sales_invoice = invoice_name
        sync_doc.status = "Synced"
        sync_doc.synced_at = frappe.utils.now_datetime()
        sync_doc.flags.ignore_permissions = True
        sync_doc.save()
    except Exception as error:
        frappe.log_error(
            title="Offline Sync Completion Error",
            message=f"Failed to complete sync record {sync_record_name} for invoice {invoice_name}: {str(error)}"
        )


def _cleanup_failed_sync(sync_record_name):
    """
    Mark a sync record as failed when invoice submission fails.

    Instead of deleting, we mark as 'failed' to:
    1. Preserve audit trail of sync attempts
    2. Allow manual investigation of failures
    3. Enable retry logic based on failure count

    Args:
        sync_record_name: Name of the Offline Invoice Sync record
    """
    if not sync_record_name:
        return

    try:
        sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
        sync_doc.status = "Failed"
        sync_doc.synced_at = frappe.utils.now_datetime()
        sync_doc.flags.ignore_permissions = True
        sync_doc.save()
    except Exception as error:
        frappe.log_error(
            title="Offline Sync Cleanup Error",
            message=f"Failed to mark sync record {sync_record_name} as failed: {str(error)}"
        )


@frappe.whitelist()
def check_offline_invoice_synced(offline_id):
    """
    Check if an offline invoice has already been synced.

    This endpoint is called by the frontend before attempting to sync
    an offline invoice, preventing duplicate submissions.

    Args:
        offline_id: The unique offline ID to check

    Returns:
        dict with 'synced' (bool) and 'sales_invoice' (str or None)
    """
    from pos_next.pos_next.doctype.offline_invoice_sync.offline_invoice_sync import (
        OfflineInvoiceSync,
    )

    result = OfflineInvoiceSync.is_synced(offline_id)

    # Defensive check - ensure result is a dict
    if not result or not isinstance(result, dict):
        return {"synced": False, "sales_invoice": None}

    # Additionally verify the sales invoice still exists and is submitted
    if result.get("synced") and result.get("sales_invoice"):
        if frappe.db.exists("Sales Invoice", result["sales_invoice"]):
            docstatus = frappe.db.get_value(
                "Sales Invoice", result["sales_invoice"], "docstatus"
            )
            if docstatus == 1:  # Submitted
                return result

        # Invoice was deleted or not submitted, clear the sync record
        return {"synced": False, "sales_invoice": None}

    return result


@frappe.whitelist()
def submit_invoice(invoice=None, data=None):
    """Submit the invoice (Step 2)."""
    # Handle different calling conventions
    if invoice is None:
        if data:
            # Check if data is a JSON string containing both params
            data_parsed = json.loads(data) if isinstance(data, str) else data

            # frappe-ui might send all params nested in data
            if isinstance(data_parsed, dict):
                if "invoice" in data_parsed:
                    invoice = data_parsed.get("invoice")
                    data = data_parsed.get("data", {})
                elif "name" in data_parsed or "doctype" in data_parsed:
                    # Data itself might be the invoice
                    invoice = data_parsed
                    data = {}
                else:
                    frappe.throw(
                        _("Missing invoice parameter. Received data: {0}").format(
                            json.dumps(data_parsed, default=str)
                        )
                    )
            else:
                frappe.throw(_("Missing invoice parameter"))
        else:
            frappe.throw(_("Both invoice and data parameters are missing"))

    # Parse JSON strings if needed
    if isinstance(data, str):
        data = json.loads(data) if data and data != "{}" else {}
    if isinstance(invoice, str):
        invoice = json.loads(invoice)

    # Ensure invoice and data are dicts
    if not isinstance(invoice, dict):
        frappe.throw(_("Invalid invoice format"))
        return  # Never reached, but helps type checker
    if not isinstance(data, dict):
        data = {}

    pos_profile = invoice.get("pos_profile")
    doctype = invoice.get("doctype", "Sales Invoice")

    # ========================================================================
    # OFFLINE INVOICE DEDUPLICATION
    # ========================================================================
    # Prevents duplicate invoice creation when the same offline invoice is
    # submitted multiple times (e.g., network retry, multiple tabs).
    # Uses a reservation pattern: create a "pending" record first, then
    # update to "synced" after successful submission.
    # ========================================================================
    offline_id = invoice.get("offline_id") or data.get("offline_id")
    sync_record_name = None

    if offline_id:
        dedup_result = _handle_offline_deduplication(
            offline_id=offline_id,
            pos_profile=pos_profile,
            customer=invoice.get("customer")
        )

        if dedup_result and dedup_result.get("already_synced"):
            # Invoice was already synced - return the existing invoice details
            return dedup_result.get("invoice_data", {})

        # Store the sync record name for later update
        sync_record_name = dedup_result.get("sync_record_name") if dedup_result else None

    # Track whether invoice was successfully submitted
    invoice_submitted = False

    try:
        invoice_name = invoice.get("name")

        # Get or create invoice
        if not invoice_name or not frappe.db.exists(doctype, invoice_name):
            created = update_invoice(json.dumps(invoice))
            if not created or not isinstance(created, dict):
                frappe.throw(_("Failed to create invoice draft"))
            invoice_name = created.get("name")
            if not invoice_name:
                frappe.throw(_("Failed to get invoice name from draft"))
            invoice_doc = frappe.get_doc(doctype, invoice_name)
        else:
            invoice_doc = frappe.get_doc(doctype, invoice_name)
            invoice_doc.update(invoice)

        # Ensure update_stock is set for Sales Invoice
        if doctype == "Sales Invoice":
            invoice_doc.update_stock = 1

        # Copy accounting dimensions from POS Profile if not already set
        if pos_profile and not invoice_doc.get("branch"):
            try:
                pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
                if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
                    invoice_doc.branch = pos_profile_doc.branch
                    # Also set branch on all items for GL entries
                    for item in invoice_doc.get("items", []):
                        if not item.get("branch"):
                            item.branch = pos_profile_doc.branch
            except Exception:
                pass  # Branch is optional, continue without it

        # Set accounts for all payment methods before saving
        if doctype == "Sales Invoice" and hasattr(invoice_doc, "payments"):
            for payment in invoice_doc.payments:
                if payment.mode_of_payment:
                    account_info = get_payment_account(
                        payment.mode_of_payment, invoice_doc.company
                    )
                    if account_info:
                        payment.account = account_info.get("account")

        # Handle sales team (multiple sales persons)
        sales_team_data = invoice.get("sales_team") or data.get("sales_team")
        if sales_team_data and isinstance(sales_team_data, list):
            # Clear existing sales team entries
            invoice_doc.sales_team = []

            # Add new sales team entries
            for member in sales_team_data:
                if member and isinstance(member, dict):
                    invoice_doc.append("sales_team", {
                        "sales_person": member.get("sales_person"),
                        "allocated_percentage": member.get("allocated_percentage", 0),
                    })

        # Handle POS Coupon if coupon_code is provided
        coupon_code = invoice.get("coupon_code") or data.get("coupon_code")
        if coupon_code:
            # Increment usage counter for POS Coupon
            if frappe.db.table_exists("POS Coupon"):
                try:
                    from pos_next.pos_next.doctype.pos_coupon.pos_coupon import increment_coupon_usage
                    increment_coupon_usage(coupon_code)
                except Exception as e:
                    frappe.log_error(
                        title="Failed to increment coupon usage",
                        message=f"Coupon: {coupon_code}, Error: {str(e)}"
                    )

        # Auto-set batch numbers for returns
        _auto_set_return_batches(invoice_doc)

        # Check if POS Settings allows negative stock
        pos_settings_allow_negative = False
        if pos_profile:
            pos_settings_allow_negative = cint(
                frappe.db.get_value(
                    "POS Settings",
                    {"pos_profile": pos_profile},
                    "allow_negative_stock"
                ) or 0
            )

        # Validate stock availability only if negative stock is not allowed
        if not pos_settings_allow_negative:
            _validate_stock_on_invoice(invoice_doc)

        # Save before submit
        invoice_doc.flags.ignore_permissions = True
        frappe.flags.ignore_account_permission = True
        invoice_doc.save()

        # Submit invoice
        invoice_doc.submit()
        invoice_submitted = True

        # Complete the offline sync record
        if sync_record_name:
            _complete_offline_sync(sync_record_name, invoice_doc.name)

        # Handle credit redemption after successful submission
        customer_credit_dict = data.get("customer_credit_dict") or invoice.get("customer_credit_dict")
        redeemed_customer_credit = data.get("redeemed_customer_credit") or invoice.get("redeemed_customer_credit")

        if redeemed_customer_credit and customer_credit_dict:
            try:
                from pos_next.api.credit_sales import redeem_customer_credit
                redeem_customer_credit(invoice_doc.name, customer_credit_dict)
            except Exception as credit_error:
                frappe.log_error(
                    title="Credit Redemption Error",
                    message=f"Invoice: {invoice_doc.name}, Error: {str(credit_error)}\n{frappe.get_traceback()}"
                )
                # Don't fail the entire transaction, just log the error
                frappe.msgprint(
                    _("Invoice submitted successfully but credit redemption failed. Please contact administrator."),
                    alert=True,
                    indicator="orange"
                )

        # Return complete invoice details
        result = {
            "name": invoice_doc.name,
            "status": invoice_doc.docstatus,
            "grand_total": invoice_doc.grand_total,
            "total": invoice_doc.total,
            "net_total": invoice_doc.net_total,
            "outstanding_amount": getattr(invoice_doc, "outstanding_amount", 0),
            "paid_amount": getattr(invoice_doc, "paid_amount", 0),
            "change_amount": getattr(invoice_doc, "change_amount", 0),
        }

        # Include offline_id in response for client-side tracking
        if offline_id:
            result["offline_id"] = offline_id

        return result

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Submit Invoice Error")
        raise

    finally:
        # Cleanup sync record if invoice was not successfully submitted
        if sync_record_name and not invoice_submitted:
            _cleanup_failed_sync(sync_record_name)


# ==========================================
# Invoice History Management
# ==========================================


@frappe.whitelist()
def get_invoice(invoice_name):
	"""
	Get a single invoice with all details for POS.

	Args:
		invoice_name: Sales Invoice name

	Returns:
		Complete invoice document with items and payments
	"""
	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

	# Check permissions
	if not frappe.has_permission("Sales Invoice", "read", invoice_name):
		frappe.throw(_("You don't have permission to view this invoice"))

	# Get invoice document
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	return invoice.as_dict()


@frappe.whitelist()
def get_invoices(pos_profile, limit=100):
	"""
	Get list of invoices for a POS Profile.

	Args:
		pos_profile: POS Profile name
		limit: Maximum number of invoices to return (default 100)

	Returns:
		List of invoices with details
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

	# Query for invoices
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
			docstatus,
			is_return,
			return_against
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
		ORDER BY
			posting_date DESC,
			posting_time DESC
		LIMIT %(limit)s
	""", {
		"pos_profile": pos_profile,
		"limit": limit
	}, as_dict=True)

	# Load items for each invoice for filtering purposes
	for invoice in invoices:
		items = frappe.db.sql("""
			SELECT
				item_code,
				item_name,
				qty,
				rate,
				amount
			FROM
				`tabSales Invoice Item`
			WHERE
				parent = %(invoice_name)s
			ORDER BY
				idx
		""", {
			"invoice_name": invoice.name
		}, as_dict=True)
		invoice.items = items

	return invoices


# ==========================================
# Draft Invoice Management
# ==========================================


@frappe.whitelist()
def get_draft_invoices(pos_opening_shift, doctype="Sales Invoice"):
    """Get all draft invoices for a POS opening shift."""
    filters = {
        "docstatus": 0,
    }

    # Add pos_opening_shift filter if the field exists
    if frappe.db.has_column(doctype, "pos_opening_shift"):
        filters["pos_opening_shift"] = pos_opening_shift

    # Performance: Get all invoice names first
    invoices_list = frappe.get_list(
        doctype,
        filters=filters,
        fields=["name"],
        limit_page_length=0,
        order_by="modified desc",
    )

    # Performance: Batch load all documents at once using get_cached_doc
    # This leverages Frappe's internal caching and is faster than individual queries
    data = []
    for invoice in invoices_list:
        data.append(frappe.get_cached_doc(doctype, invoice["name"]))

    return data


@frappe.whitelist()
def delete_invoice(invoice):
    """Delete draft invoice."""
    doctype = "Sales Invoice"

    if not frappe.db.exists(doctype, invoice):
        frappe.throw(_("Invoice {0} does not exist").format(invoice))

    # Check if it's a draft
    if frappe.db.get_value(doctype, invoice, "docstatus") != 0:
        frappe.throw(_("Cannot delete submitted invoice {0}").format(invoice))

    frappe.delete_doc(doctype, invoice, force=1)
    return _("Invoice {0} Deleted").format(invoice)


@frappe.whitelist()
def cleanup_old_drafts(pos_profile=None, max_age_hours=24):
    """
    Clean up old draft invoices to prevent stock reservation issues.
    Deletes drafts older than max_age_hours (default 24 hours).
    """
    from datetime import datetime, timedelta

    doctype = "Sales Invoice"
    cutoff_time = datetime.now() - timedelta(hours=int(max_age_hours))

    filters = {
        "docstatus": 0,  # Draft only
        "modified": ["<", cutoff_time.strftime("%Y-%m-%d %H:%M:%S")],
    }

    # Optionally filter by POS profile
    if pos_profile:
        filters["pos_profile"] = pos_profile

    # Get old drafts
    old_drafts = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name", "modified"],
        limit_page_length=100,  # Safety limit
    )

    deleted_count = 0
    for draft in old_drafts:
        try:
            frappe.delete_doc(
                doctype, draft["name"], force=True, ignore_permissions=True
            )
            deleted_count += 1
        except Exception as e:
            frappe.log_error(
                f"Failed to delete draft {draft['name']}: {str(e)}",
                "Draft Cleanup Error",
            )

    return {
        "deleted": deleted_count,
        "message": f"Cleaned up {deleted_count} old draft invoices",
    }


# ==========================================
# Return Invoice Management
# ==========================================


@frappe.whitelist()
def get_returnable_invoices(limit=50):
    """Get list of invoices that have items available for return."""
    # Performance: Use SQL aggregation to calculate returned quantities in one query
    # This eliminates N+1 queries by joining return invoices and aggregating in the database

    query = """
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.grand_total,
            si.status,
            COALESCE(SUM(CASE WHEN ret_item.qty IS NOT NULL THEN ABS(ret_item.qty) ELSE 0 END), 0) as total_returned_qty,
            COALESCE(SUM(CASE WHEN si_item.qty IS NOT NULL THEN si_item.qty ELSE 0 END), 0) as total_original_qty
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Invoice Item` si_item ON si_item.parent = si.name
        LEFT JOIN `tabSales Invoice` ret_si ON ret_si.return_against = si.name
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        LEFT JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
            AND (ret_item.sales_invoice_item = si_item.name OR ret_item.item_code = si_item.item_code)
        WHERE si.docstatus = 1
            AND si.is_return = 0
            AND si.is_pos = 1
        GROUP BY si.name
        HAVING total_original_qty > total_returned_qty
        ORDER BY si.posting_date DESC, si.creation DESC
        LIMIT %s
    """

    returnable_invoices = frappe.db.sql(query, [cint(limit)], as_dict=1)

    return returnable_invoices


@frappe.whitelist()
def get_invoice_for_return(invoice_name):
    """Get invoice with return tracking - calculates remaining qty for each item."""
    if not frappe.db.exists("Sales Invoice", invoice_name):
        frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

    # Get the original invoice
    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    # Performance: Use SQL aggregation to calculate returned quantities in one query
    # This eliminates N+1 queries by aggregating all return items at once
    returned_qty_query = """
        SELECT
            COALESCE(ret_item.sales_invoice_item, ret_item.item_code) as key_field,
            SUM(ABS(ret_item.qty)) as returned_qty
        FROM `tabSales Invoice` ret_si
        INNER JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
        WHERE ret_si.return_against = %s
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        GROUP BY key_field
    """

    returned_qty_results = frappe.db.sql(returned_qty_query, [invoice_name], as_dict=1)
    returned_qty = {row["key_field"]: row["returned_qty"] for row in returned_qty_results}

    # Calculate remaining quantities
    invoice_dict = invoice.as_dict()
    updated_items = []

    for item in invoice_dict.get("items", []):
        # Check how much has been returned using the item's name (row ID)
        already_returned = returned_qty.get(item.name, 0)
        remaining_qty = item.qty - already_returned

        if remaining_qty > 0:
            item_copy = item.copy()
            item_copy["original_qty"] = item.qty
            item_copy["qty"] = remaining_qty
            item_copy["already_returned"] = already_returned
            updated_items.append(item_copy)

    invoice_dict["items"] = updated_items
    return invoice_dict


@frappe.whitelist()
def search_invoices_for_return(
    invoice_name=None,
    company=None,
    customer_name=None,
    customer_id=None,
    mobile_no=None,
    from_date=None,
    to_date=None,
    min_amount=None,
    max_amount=None,
    page=1,
    doctype="Sales Invoice",
):
    """Search for invoices that can be returned with pagination."""
    # Start with base filters - use Any type for frappe filter values
    filters: dict = {
        "docstatus": 1,
        "is_return": 0,
    }

    if company:
        filters["company"] = company

    # Convert page to integer
    if page and isinstance(page, str):
        page = int(page)
    else:
        page = 1

    # Items per page
    page_length = 100
    start = (page - 1) * page_length

    # Add invoice name filter
    if invoice_name:
        filters["name"] = ["like", f"%{invoice_name}%"]

    # Add date range filters
    if from_date:
        filters["posting_date"] = [">=", from_date]

    if to_date:
        if "posting_date" in filters:
            filters["posting_date"] = ["between", [from_date, to_date]]
        else:
            filters["posting_date"] = ["<=", to_date]

    # Add amount filters
    if min_amount:
        filters["grand_total"] = [">=", float(min_amount)]

    if max_amount:
        if "grand_total" in filters and min_amount:
            filters["grand_total"] = ["between", [float(min_amount), float(max_amount)]]
        else:
            filters["grand_total"] = ["<=", float(max_amount)]

    # If any customer search criteria is provided, find matching customers
    customer_ids = []
    if customer_name or customer_id or mobile_no:
        conditions = []
        params = {}

        if customer_name:
            conditions.append("customer_name LIKE %(customer_name)s")
            params["customer_name"] = f"%{customer_name}%"

        if customer_id:
            conditions.append("name LIKE %(customer_id)s")
            params["customer_id"] = f"%{customer_id}%"

        if mobile_no:
            conditions.append("mobile_no LIKE %(mobile_no)s")
            params["mobile_no"] = f"%{mobile_no}%"

        where_clause = " OR ".join(conditions)
        customer_query = f"""
			SELECT name
			FROM `tabCustomer`
			WHERE {where_clause}
			LIMIT 100
		"""

        customers = frappe.db.sql(customer_query, params, as_dict=True)
        customer_ids = [c.name for c in customers]

        if customer_ids:
            filters["customer"] = ["in", customer_ids]
        elif any([customer_name, customer_id, mobile_no]):
            return {"invoices": [], "has_more": False}

    # Count total invoices
    total_count_query = frappe.get_list(
        doctype,
        filters=filters,
        fields=["count(name) as total_count"],
        as_list=False,
    )
    total_count = total_count_query[0].total_count if total_count_query else 0

    # Get invoices with pagination
    invoices_list = frappe.get_list(
        doctype,
        filters=filters,
        fields=["name"],
        limit_start=start,
        limit_page_length=page_length,
        order_by="posting_date desc, name desc",
    )

    if not invoices_list:
        return {"invoices": [], "has_more": False}

    # Performance: Batch query all returned quantities for all invoices at once
    # This eliminates N+1 queries by aggregating return data in a single SQL call
    invoice_names = [inv["name"] for inv in invoices_list]

    returned_qty_query = """
        SELECT
            ret_si.return_against as invoice_name,
            ret_item.item_code,
            SUM(ABS(ret_item.qty)) as returned_qty
        FROM `tabSales Invoice` ret_si
        INNER JOIN `tabSales Invoice Item` ret_item ON ret_item.parent = ret_si.name
        WHERE ret_si.return_against IN %s
            AND ret_si.docstatus = 1
            AND ret_si.is_return = 1
        GROUP BY ret_si.return_against, ret_item.item_code
    """

    returned_qty_results = frappe.db.sql(returned_qty_query, [invoice_names], as_dict=1)

    # Build a map of invoice_name -> {item_code: returned_qty}
    returned_qty_map = {}
    for row in returned_qty_results:
        inv_name = row["invoice_name"]
        if inv_name not in returned_qty_map:
            returned_qty_map[inv_name] = {}
        returned_qty_map[inv_name][row["item_code"]] = row["returned_qty"]

    # Process and return results
    data = []

    for invoice in invoices_list:
        invoice_doc = frappe.get_doc(doctype, invoice.name)
        returned_qty = returned_qty_map.get(invoice.name, {})

        if returned_qty:
            # Filter items with remaining qty
            filtered_items = []
            for item in invoice_doc.items:
                already_returned = returned_qty.get(item.item_code, 0)
                remaining_qty = item.qty - already_returned

                if remaining_qty > 0:
                    new_item = item.as_dict().copy()
                    new_item["qty"] = remaining_qty
                    new_item["amount"] = remaining_qty * item.rate
                    if item.get("stock_qty"):
                        new_item["stock_qty"] = (
                            item.stock_qty / item.qty * remaining_qty
                            if item.qty
                            else remaining_qty
                        )
                    filtered_items.append(frappe._dict(new_item))

            if filtered_items:
                filtered_invoice = frappe.get_doc(doctype, invoice.name)
                filtered_invoice.items = filtered_items
                data.append(filtered_invoice)
        else:
            data.append(invoice_doc)

    # Check if there are more results
    has_more = (start + page_length) < total_count

    return {"invoices": data, "has_more": has_more}


# ==========================================
# Legacy/Helper Functions
# ==========================================


@frappe.whitelist()
def apply_offers(invoice_data, selected_offers=None):
    """Calculate and apply promotional offers using ERPNext Pricing Rules.

    Args:
            invoice_data (str | dict): Sales Invoice payload used for offer evaluation.
            selected_offers (str | list | None): Optional collection of Pricing Rule names.
                    When provided, results are filtered to only include these rules.
                    ERPNext handles all conflict resolution based on priority.
    """
    try:
        if isinstance(invoice_data, str):
            invoice_data = json.loads(invoice_data or "{}")

        invoice = frappe._dict(invoice_data or {})
        items = invoice.get("items") or []

        if isinstance(selected_offers, str):
            try:
                selected_offers = json.loads(selected_offers)
            except ValueError:
                selected_offers = [selected_offers]

        if isinstance(selected_offers, (list, tuple, set)):
            selected_offer_names = {
                cstr(name) for name in selected_offers if cstr(name)
            }
        else:
            selected_offer_names = set()

        if not items:
            return {"items": []}

        if not invoice.get("pos_profile") or not erpnext_apply_pricing_rule:
            # Either no POS profile supplied or ERPNext promotional engine unavailable
            return {"items": items}

        profile = frappe.get_cached_doc("POS Profile", invoice.get("pos_profile"))

        # Batch fetch all item details in a single query (reduces N queries to 1)
        item_codes = list({item.get("item_code") for item in items if item.get("item_code")})
        item_details_map = {}
        if item_codes:
            item_records = frappe.get_all(
                "Item",
                filters={"name": ["in", item_codes]},
                fields=["name", "item_name", "item_group", "brand", "stock_uom"],
            )
            item_details_map = {r.name: r for r in item_records}

        pricing_items = []
        index_map = []
        prepared_items = [frappe._dict(row) for row in items]

        for idx, item in enumerate(prepared_items):
            item_code = item.get("item_code")
            qty = flt(item.get("qty") or item.get("quantity") or 0)

            if not item_code or qty <= 0:
                continue

            # Use batch-fetched item details
            cached = item_details_map.get(item_code)

            conversion_factor = flt(item.get("conversion_factor") or 1) or 1
            price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)

            pricing_items.append(
                frappe._dict(
                    {
                        "doctype": "Sales Invoice Item",
                        "name": item.get("name") or f"POS-{idx}",
                        "item_code": item_code,
                        "item_name": (
                            cached.item_name if cached else item.get("item_name")
                        ),
                        "item_group": (
                            cached.item_group if cached else item.get("item_group")
                        ),
                        "brand": (cached.brand if cached else item.get("brand")),
                        "qty": qty,
                        "stock_qty": qty * conversion_factor,
                        "conversion_factor": conversion_factor,
                        "uom": item.get("uom")
                        or item.get("stock_uom")
                        or (cached.stock_uom if cached else None),
                        "stock_uom": item.get("stock_uom")
                        or (cached.stock_uom if cached else None),
                        "price_list_rate": price_list_rate,
                        "base_price_list_rate": price_list_rate,
                        "rate": flt(item.get("rate") or price_list_rate),
                        "base_rate": flt(item.get("rate") or price_list_rate),
                        "discount_percentage": 0,
                        "discount_amount": 0,
                        "warehouse": item.get("warehouse") or profile.warehouse,
                        "parenttype": invoice.get("doctype") or "Sales Invoice",
                    }
                )
            )
            index_map.append(idx)

            # Clear previously applied promotional metadata if the
            # current quantity can no longer satisfy the rule.
            item.discount_percentage = 0
            item.discount_amount = 0
            item.pricing_rules = []
            item.applied_promotional_schemes = []

        if not pricing_items:
            return {"items": items}

        company_currency = frappe.get_cached_value(
            "Company", profile.company, "default_currency"
        )

        # Get customer details if customer is provided
        customer = invoice.get("customer")
        customer_group = invoice.get("customer_group")
        territory = invoice.get("territory")

        if customer and not customer_group:
            # Fetch customer_group from customer
            try:
                customer_data = frappe.get_cached_value(
                    "Customer", customer, ["customer_group", "territory"], as_dict=1
                )
                if customer_data:
                    customer_group = customer_data.get("customer_group")
                    if not territory:
                        territory = customer_data.get("territory")
            except Exception:
                pass

        # If still no customer_group, use default
        if not customer_group:
            customer_group = "All Customer Groups"

        pricing_args = frappe._dict(
            {
                "doctype": invoice.get("doctype") or "Sales Invoice",
                "name": invoice.get("name") or "POS-INVOICE",
                "company": profile.company,
                "transaction_date": invoice.get("posting_date") or nowdate(),
                "posting_date": invoice.get("posting_date") or nowdate(),
                "currency": invoice.get("currency")
                or profile.get("currency")
                or company_currency,
                "conversion_rate": flt(invoice.get("conversion_rate") or 1) or 1,
                "plc_conversion_rate": flt(invoice.get("plc_conversion_rate") or 1)
                or 1,
                "price_list": invoice.get("price_list")
                or profile.get("selling_price_list"),
                "customer": customer,
                "customer_group": customer_group,
                "territory": territory,
                "items": pricing_items,
            }
        )

        # Call ERPNext pricing engine - it handles all conflicts based on priority
        #
        # Why we pass pricing_args twice:
        # - 1st param (args): ERPNext extracts and pops 'items' from this, then processes each item individually
        # - 2nd param (doc): Used by 'mixed_conditions' pricing rules to access the FULL items list
        #                    for quantity accumulation across different items in the same group
        #
        # Example: A rule "Buy 2 from Demo Item Group, get 10% off" with mixed_conditions=1
        # needs to see ALL items (1 Book + 1 Camera) to know total qty=2, not just each item's qty=1
        #
        # See: erpnext/accounts/doctype/pricing_rule/utils.py -> get_qty_and_rate_for_mixed_conditions()
        pricing_results = erpnext_apply_pricing_rule(pricing_args, doc=pricing_args) or []

        if not pricing_results:
            return {"items": items}

        raw_rule_names = set()
        for result in pricing_results:
            if not result:
                continue
            rules = []
            if erpnext_get_applied_pricing_rules:
                rules = erpnext_get_applied_pricing_rules(result.get("pricing_rules"))
            else:
                raw_rules = result.get("pricing_rules") or []
                if isinstance(raw_rules, str):
                    if raw_rules.startswith("["):
                        rules = json.loads(raw_rules)
                    else:
                        rules = [r.strip() for r in raw_rules.split(",") if r.strip()]
                elif isinstance(raw_rules, (list, tuple, set)):
                    rules = list(raw_rules)
            raw_rule_names.update(rules)

        # Build a map of applicable pricing rules from the ERPNext engine results.
        #
        # ERPNext has two types of pricing rules:
        #
        # 1. Promotional Scheme Rules (promotional_scheme is set):
        #    - Created automatically when a Promotional Scheme is saved
        #    - The scheme acts as a "template" that generates one or more Pricing Rules
        #    - Example: "Summer Sale" scheme creates "PRLE-0001", "PRLE-0002" rules
        #
        # 2. Standalone Pricing Rules (promotional_scheme is empty):
        #    - Created directly as Pricing Rule documents
        #    - Not linked to any Promotional Scheme
        #    - Example: A direct "10% off Item X" rule created in Pricing Rule doctype
        #
        # We include BOTH types for POS, but exclude coupon_code_based rules
        # (those require explicit coupon entry and are handled separately).
        #
        rule_map = {}
        if raw_rule_names:
            rule_records = frappe.get_all(
                "Pricing Rule",
                filters={"name": ["in", list(raw_rule_names)]},
                fields=[
                    "name",
                    "promotional_scheme",
                    "coupon_code_based",
                    "promotional_scheme_id",
                    "price_or_product_discount",
                ],
            )
            for record in rule_records:
                # Skip coupon-based rules (require explicit coupon code entry)
                if record.coupon_code_based:
                    continue

                # Include both promotional scheme rules and standalone pricing rules
                rule_map[record.name] = record

        if selected_offer_names:
            # Restrict available rules to the ones explicitly selected from the UI.
            rule_map = {
                name: details
                for name, details in rule_map.items()
                if name in selected_offer_names
            }

        if not rule_map:
            return {"items": items}

        applied_rules = set()
        free_items = []

        for result, item_index in zip(pricing_results, index_map):
            if not result:
                continue

            if erpnext_get_applied_pricing_rules:
                rule_names = erpnext_get_applied_pricing_rules(
                    result.get("pricing_rules")
                )
            else:
                raw_rules = result.get("pricing_rules") or []
                if isinstance(raw_rules, str):
                    if raw_rules.startswith("["):
                        rule_names = json.loads(raw_rules)
                    else:
                        rule_names = [
                            r.strip() for r in raw_rules.split(",") if r.strip()
                        ]
                elif isinstance(raw_rules, (list, tuple, set)):
                    rule_names = list(raw_rules)
                else:
                    rule_names = []

            applicable_rule_names = [
                name for name in rule_names or [] if name in rule_map
            ]

            if not applicable_rule_names:
                continue

            applied_rules.update(applicable_rule_names)

            item_doc = prepared_items[item_index]
            qty = flt(item_doc.get("qty") or item_doc.get("quantity") or 0)
            price_list_rate = flt(
                result.get("price_list_rate")
                or item_doc.get("price_list_rate")
                or item_doc.get("rate")
                or 0
            )

            # Get discount from result or fetch from pricing rule
            discount_percentage = flt(result.get("discount_percentage") or 0)
            per_unit_discount = flt(result.get("discount_amount") or 0)

            # If ERPNext didn't calculate discount (validate_applied_rule=1),
            # we need to fetch and apply it manually
            if (
                not discount_percentage
                and not per_unit_discount
                and applicable_rule_names
            ):
                for rule_name in applicable_rule_names:
                    rule_doc = rule_map.get(rule_name)
                    if not rule_doc:
                        continue

                    # Fetch full pricing rule to get discount values
                    full_rule = frappe.get_cached_doc("Pricing Rule", rule_name)

                    if (
                        full_rule.rate_or_discount == "Discount Percentage"
                        and full_rule.discount_percentage
                    ):
                        discount_percentage += flt(full_rule.discount_percentage)
                    elif (
                        full_rule.rate_or_discount == "Discount Amount"
                        and full_rule.discount_amount
                    ):
                        per_unit_discount += flt(full_rule.discount_amount)
                    elif full_rule.rate_or_discount == "Rate" and full_rule.rate:
                        # Apply fixed rate
                        price_list_rate = flt(full_rule.rate)

            line_discount_amount = 0
            if discount_percentage and qty and price_list_rate:
                line_discount_amount = price_list_rate * qty * discount_percentage / 100
            elif per_unit_discount and qty:
                line_discount_amount = per_unit_discount * qty
            else:
                line_discount_amount = per_unit_discount

            if (
                not discount_percentage
                and line_discount_amount
                and qty
                and price_list_rate
            ):
                base_amount = price_list_rate * qty
                if base_amount:
                    discount_percentage = (line_discount_amount / base_amount) * 100

            item_doc.discount_percentage = discount_percentage
            item_doc.discount_amount = line_discount_amount
            item_doc.price_list_rate = price_list_rate
            item_doc.rate = flt(item_doc.get("rate") or price_list_rate)
            item_doc.pricing_rules = applicable_rule_names

            item_doc.applied_promotional_schemes = list(
                {
                    rule_map[name].promotional_scheme
                    for name in applicable_rule_names
                    if rule_map[name].promotional_scheme
                }
            )

            for free_item in result.get("free_item_data") or []:
                rule_name = free_item.get("pricing_rules")
                if not rule_name or rule_name not in rule_map:
                    continue
                free_item_doc = frappe._dict(free_item)
                free_item_doc.applied_promotional_scheme = rule_map[
                    rule_name
                ].promotional_scheme
                free_items.append(free_item_doc)

        return {
            "items": [dict(item) for item in prepared_items],
            "free_items": [dict(item) for item in free_items],
            "applied_pricing_rules": sorted(applied_rules),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Apply Offers Error")
        frappe.throw(_("Error applying offers: {0}").format(str(e)))
