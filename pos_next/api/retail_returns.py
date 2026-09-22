"""Retail return / exchange helpers for POSNext.

Payment Hub is intentionally not modified by this module. Invoice-linked
provider refunds remain owned by ReturnInvoiceDialog + the existing Payment Hub
integration. Return Without Invoice uses POS Profile pricing and controlled
Customer Credit / Cash settlement.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt


def _as_dict(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    return value if isinstance(value, list) else []


def _get_return_settings(pos_profile: str) -> dict:
    settings = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile},
        [
            "allow_return",
            "allow_return_without_invoice",
            "allow_exchange",
            "allow_user_to_edit_rate",
            "require_manager_pin_no_invoice_return",
            "require_manager_pin_cash_refund",
            "require_manager_pin_rate_override",
        ],
        as_dict=True,
    ) or {}

    def enabled(field: str, default=1):
        value = settings.get(field)
        return cint(default if value is None else value)

    return {
        "allow_return": enabled("allow_return", 0),
        "allow_return_without_invoice": enabled("allow_return_without_invoice", 0),
        "allow_exchange": enabled("allow_exchange", 1),
        "allow_user_to_edit_rate": cint(settings.get("allow_user_to_edit_rate") or 0),
        "require_manager_pin_no_invoice_return": enabled(
            "require_manager_pin_no_invoice_return", 1
        ),
        "require_manager_pin_cash_refund": enabled("require_manager_pin_cash_refund", 1),
        "require_manager_pin_rate_override": enabled("require_manager_pin_rate_override", 1),
    }


def _verify_manager_pin(pin: str | None) -> dict:
    """Resolve a manager from an enabled POS User PIN without requesting a username.

    POS PINs are stored in Frappe Password fields, so the value is encrypted in
    ``__Auth`` rather than stored as plain text in the DocType table.
    """
    pin = (pin or "").strip()
    if not pin:
        frappe.throw(_("Manager POS PIN is required."))
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        frappe.throw(_("Manager POS PIN must contain 4 to 6 digits."))

    rows = frappe.get_all(
        "POS User PIN",
        filters={"enabled": 1, "can_approve_returns": 1},
        fields=["name", "user"],
        order_by="modified desc",
    )

    matches = []
    for row in rows:
        if not row.user or not frappe.db.get_value("User", row.user, "enabled"):
            continue
        try:
            doc = frappe.get_doc("POS User PIN", row.name)
            stored = doc.get_password("pos_pin", raise_exception=False)
        except TypeError:
            # Compatibility with Frappe versions whose get_password does not
            # expose the raise_exception keyword.
            try:
                stored = doc.get_password("pos_pin")
            except Exception:
                stored = None
        except Exception:
            stored = None

        if stored and secrets.compare_digest(str(stored), pin):
            matches.append(row.user)

    if not matches:
        frappe.throw(_("Manager authorization failed. Check the POS PIN."))
    if len(matches) > 1:
        frappe.throw(
            _(
                "This POS PIN is assigned to more than one approver. Ask an administrator to assign unique PINs."
            )
        )

    return {"approver": matches[0]}


def _validate_shift(pos_opening_shift: str | None, pos_profile: str) -> None:
    if not pos_opening_shift:
        frappe.throw(_("An open POS shift is required."))

    shift = frappe.db.get_value(
        "POS Opening Shift",
        pos_opening_shift,
        ["name", "pos_profile", "docstatus", "status", "user", "pos_closing_shift"],
        as_dict=True,
    )
    if not shift:
        frappe.throw(_("POS Opening Shift {0} was not found.").format(pos_opening_shift))
    if shift.pos_profile != pos_profile:
        frappe.throw(_("The POS shift does not belong to the selected POS Profile."))
    if shift.user != frappe.session.user:
        frappe.throw(_("This POS shift belongs to another cashier."), frappe.PermissionError)
    if (
        int(shift.docstatus or 0) != 1
        or (shift.status or "").lower() != "open"
        or bool(shift.pos_closing_shift)
    ):
        frappe.throw(_("The POS shift is not open."))


def _profile_cash_modes(pos_profile_doc) -> set[str]:
    names = [row.mode_of_payment for row in (pos_profile_doc.payments or []) if row.mode_of_payment]
    if not names:
        return set()

    rows = frappe.get_all(
        "Mode of Payment",
        filters={"name": ["in", names]},
        fields=["name", "type"],
    )
    return {row.name for row in rows if (row.type or "").lower() == "cash"}


def _conversion_factor(item_code: str, stock_uom: str | None, uom: str | None) -> float:
    if not uom or not stock_uom or uom == stock_uom:
        return 1.0
    return flt(
        frappe.db.get_value(
            "UOM Conversion Detail",
            {"parent": item_code, "uom": uom},
            "conversion_factor",
        )
        or 0
    )


def _get_server_item_detail(
    item_code: str,
    pos_profile: str,
    customer: str | None,
    qty: float,
    uom=None,
):
    """Price a return item from the same POS Profile selling-price source as normal POS.

    The normal product browser's ``get_items`` endpoint is treated as the first
    source of truth for the displayed retail price. ERPNext ``get_item_details``
    is still used for stock/UOM/item metadata, but cannot silently replace the
    POS Profile Item Price with zero.
    """
    from pos_next.api.items import _fetch_item_uom_prices, get_item_details, get_items

    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    if not profile.selling_price_list:
        frappe.throw(_("Selling Price List is not set in POS Profile {0}.").format(pos_profile))
    if not profile.warehouse:
        frappe.throw(_("Warehouse is not set in POS Profile {0}.").format(pos_profile))

    detail = get_item_details(
        item_code=item_code,
        pos_profile=pos_profile,
        customer=customer,
        qty=qty,
        uom=uom,
    ) or {}

    # Use the exact same normal-POS catalog endpoint so Return / Exchange sees
    # the same Item Price as the sale screen.
    normal_rows = get_items(
        pos_profile=pos_profile,
        search_term=item_code,
        start=0,
        limit=30,
        include_variants=1,
        show_variants_as_items=0,
    ) or []
    normal = next((row for row in normal_rows if row.get("item_code") == item_code), None) or {}

    item_row = frappe.db.get_value(
        "Item",
        item_code,
        ["item_name", "stock_uom", "has_serial_no", "has_batch_no", "is_stock_item"],
        as_dict=True,
    ) or {}
    stock_uom = item_row.get("stock_uom") or detail.get("stock_uom") or normal.get("stock_uom")
    target_uom = uom or detail.get("uom") or normal.get("uom") or stock_uom
    prices = normal.get("uom_prices") or _fetch_item_uom_prices(
        item_code, profile.selling_price_list
    ) or {}

    rate = 0.0
    pricing_source = "normal_pos_catalog"

    # Explicit target-UOM Item Price wins, exactly as normal UOM selection does.
    if target_uom and target_uom in prices:
        rate = flt(prices.get(target_uom) or 0)
    elif stock_uom and stock_uom in prices:
        stock_rate = flt(prices.get(stock_uom) or 0)
        cf = _conversion_factor(item_code, stock_uom, target_uom)
        rate = stock_rate * (cf or 1) if target_uom and target_uom != stock_uom else stock_rate
    elif "" in prices:
        stock_rate = flt(prices.get("") or 0)
        cf = _conversion_factor(item_code, stock_uom, target_uom)
        rate = stock_rate * (cf or 1) if target_uom and target_uom != stock_uom else stock_rate
    else:
        normal_rate = flt(normal.get("rate") or normal.get("price_list_rate") or 0)
        if normal_rate > 0:
            rate = normal_rate
        else:
            # Last fallback is ERPNext's sale detail result. This is still
            # authoritative server data, never a browser-supplied amount.
            rate = flt(detail.get("rate") or detail.get("price_list_rate") or 0)
            pricing_source = "erpnext_item_detail_fallback"

    cf = _conversion_factor(item_code, stock_uom, target_uom) or flt(
        detail.get("conversion_factor") or 1
    ) or 1

    merged = {
        **normal,
        **detail,
        "item_code": item_code,
        "item_name": detail.get("item_name")
        or normal.get("item_name")
        or item_row.get("item_name")
        or item_code,
        "stock_uom": stock_uom,
        "uom": target_uom or stock_uom,
        "conversion_factor": cf,
        # Retail return/exchange stock is physically received at the active POS
        # store. Never inherit an Item/default warehouse (for example Main
        # Warehouse) into a return staged from another store.
        "warehouse": profile.warehouse,
        "has_serial_no": cint(detail.get("has_serial_no") or item_row.get("has_serial_no") or 0),
        "has_batch_no": cint(detail.get("has_batch_no") or item_row.get("has_batch_no") or 0),
        "is_stock_item": cint(detail.get("is_stock_item") or item_row.get("is_stock_item") or 0),
        "rate": rate,
        "price_list_rate": rate,
        "price_list_rate_price_uom": rate,
        "uom_prices": prices,
        "pricing_source": pricing_source,
        "selling_price_list": profile.selling_price_list,
    }
    return merged


@frappe.whitelist()
def get_no_invoice_return_options(pos_profile: str):
    if not pos_profile:
        frappe.throw(_("POS Profile is required."))
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    settings = _get_return_settings(pos_profile)
    return {
        "company": profile.company,
        "warehouse": profile.warehouse,
        "selling_price_list": profile.selling_price_list,
        "cash_modes": sorted(_profile_cash_modes(profile)),
        **settings,
    }


@frappe.whitelist()
def search_return_items(search_term: str, pos_profile: str, limit: int = 20):
    """Search sales items without hiding zero-stock return candidates."""
    term = (search_term or "").strip()
    if len(term) < 2:
        return []
    if not pos_profile:
        frappe.throw(_("POS Profile is required."))

    limit = max(1, min(int(limit or 20), 30))
    like = f"%{term}%"
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            i.name AS item_code,
            i.item_name,
            i.stock_uom
        FROM `tabItem` i
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
        WHERE i.disabled = 0
          AND i.is_sales_item = 1
          AND (
                i.name LIKE %(like)s
             OR i.item_name LIKE %(like)s
             OR ib.barcode = %(exact)s
             OR ib.barcode LIKE %(like)s
          )
        ORDER BY
            CASE WHEN i.name = %(exact)s OR ib.barcode = %(exact)s THEN 0 ELSE 1 END,
            i.item_name,
            i.name
        LIMIT %(limit)s
        """,
        {"like": like, "exact": term, "limit": limit},
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_return_item_details(
    item_code: str,
    pos_profile: str,
    customer: str | None = None,
    qty=1,
    uom=None,
):
    if not item_code:
        frappe.throw(_("Item is required."))
    return _get_server_item_detail(
        item_code,
        pos_profile,
        customer,
        abs(flt(qty)) or 1,
        uom=uom,
    )


@frappe.whitelist()
def resolve_exchange_credit_source(return_invoice: str):
    """Resolve the Sales Invoice reference that actually carries exchange credit.

    ERPNext linked returns created with ``update_outstanding_for_self = 0`` can
    place the negative outstanding balance on the original Sales Invoice instead
    of the return document itself. Standalone/no-invoice returns keep the negative
    outstanding on the return invoice. Exchange checkout must allocate against
    whichever submitted invoice currently owns that negative outstanding amount.
    """
    return_invoice = (return_invoice or "").strip()
    if not return_invoice:
        frappe.throw(_("Return invoice is required."))

    ret = frappe.db.get_value(
        "Sales Invoice",
        return_invoice,
        ["name", "customer", "company", "is_return", "return_against", "outstanding_amount", "docstatus"],
        as_dict=True,
    )
    if not ret or ret.docstatus != 1 or not ret.is_return:
        frappe.throw(_("Return invoice {0} is not a submitted Sales Return.").format(return_invoice))

    candidates = []
    if ret.return_against:
        original = frappe.db.get_value(
            "Sales Invoice",
            ret.return_against,
            ["name", "customer", "company", "is_return", "return_against", "outstanding_amount", "docstatus"],
            as_dict=True,
        )
        if original:
            # Linked ERPNext returns are submitted with
            # update_outstanding_for_self = 0 in POSNext. Their credit therefore
            # belongs to the original invoice reference. Prefer it explicitly;
            # using the return document itself can turn the return positive/Unpaid
            # after the allocation JE.
            candidates.append(original)

    # Standalone/no-invoice returns normally carry their own negative outstanding.
    # Keep this as the fallback for installations where a linked return genuinely
    # owns the credit itself.
    candidates.append(ret)

    credit_source = next(
        (row for row in candidates if row.docstatus == 1 and flt(row.outstanding_amount) < -0.000001),
        None,
    )
    if not credit_source:
        frappe.throw(
            _("Exchange return {0} does not currently have an available credit balance.").format(
                return_invoice
            )
        )

    if credit_source.customer != ret.customer or credit_source.company != ret.company:
        frappe.throw(_("Exchange credit source does not match the return customer/company."))

    available = abs(flt(credit_source.outstanding_amount))
    return {
        "type": "Invoice",
        "credit_origin": credit_source.name,
        "available_credit": available,
        "total_credit": available,
        "source_type": "Exchange Return Credit",
        "return_invoice": ret.name,
        "return_against": ret.return_against,
        "customer": ret.customer,
        "company": ret.company,
    }


@frappe.whitelist()
@rate_limit(limit=12, seconds=60)
def create_no_invoice_return(payload=None, manager_pin=None):
    """Create a controlled Return Without Invoice / exchange credit.

    Prices are recalculated from the POS Profile Selling Price List. A browser
    rate is accepted only when POS Settings permits rate editing; manager PIN
    requirements are evaluated server-side from POS Settings.
    """
    payload = _as_dict(payload)

    pos_profile = (payload.get("pos_profile") or "").strip()
    pos_opening_shift = (payload.get("pos_opening_shift") or "").strip()
    customer = (payload.get("customer") or "").strip()
    reason = (payload.get("reason") or "").strip()
    refund_type = (payload.get("refund_type") or "credit").strip().lower()
    cash_mode = (payload.get("cash_mode") or "").strip()
    exchange_mode = bool(cint(payload.get("exchange_mode") or 0))
    items = _as_list(payload.get("items"))

    if not pos_profile:
        frappe.throw(_("POS Profile is required."))
    if not customer:
        frappe.throw(_("Customer is required for a no-invoice return."))
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} was not found.").format(customer))
    if not reason:
        frappe.throw(_("Return reason is required."))
    if refund_type not in {"credit", "cash"}:
        frappe.throw(_("Unsupported refund type."))
    if not items:
        frappe.throw(_("Add at least one item to return."))

    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    settings = _get_return_settings(pos_profile)
    if not settings["allow_return"]:
        frappe.throw(_("Returns are disabled in POS Settings for this POS Profile."), frappe.PermissionError)
    if not settings["allow_return_without_invoice"]:
        frappe.throw(_("Return Without Invoice is disabled in POS Settings."), frappe.PermissionError)
    if exchange_mode and not settings["allow_exchange"]:
        frappe.throw(_("Exchange is disabled in POS Settings."), frappe.PermissionError)
    _validate_shift(pos_opening_shift, pos_profile)

    if refund_type == "cash":
        allowed_cash_modes = _profile_cash_modes(profile)
        if not cash_mode or cash_mode not in allowed_cash_modes:
            frappe.throw(
                _(
                    "Cash refunds without an invoice must use a Cash Mode of Payment from this POS Profile."
                )
            )

    invoice_items = []
    rate_overrides = []
    for row in items:
        if not isinstance(row, dict):
            continue
        item_code = (row.get("item_code") or "").strip()
        qty = abs(flt(row.get("qty") or row.get("quantity") or 0))
        uom = row.get("uom") or None
        if not item_code or qty <= 0:
            frappe.throw(_("Every return item must have an item code and quantity greater than zero."))

        detail = _get_server_item_detail(item_code, pos_profile, customer, qty, uom=uom)
        if cint(detail.get("has_serial_no")) or cint(detail.get("has_batch_no")):
            frappe.throw(
                _(
                    "Return Without Invoice does not support serialized or batched item {0}. "
                    "Use Return With Invoice so ERPNext can preserve the original stock identity."
                ).format(item_code)
            )

        current_rate = flt(detail.get("rate") or detail.get("price_list_rate") or 0)
        requested_rate = flt(row.get("rate") if row.get("rate") is not None else current_rate)
        final_rate = current_rate
        changed = abs(requested_rate - current_rate) > 0.000001

        if changed:
            if not settings["allow_user_to_edit_rate"]:
                frappe.throw(
                    _("Rate editing is disabled in POS Settings for item {0}.").format(item_code)
                )
            if requested_rate < 0:
                frappe.throw(_("Return rate cannot be negative for item {0}.").format(item_code))
            final_rate = requested_rate
            rate_overrides.append(
                {
                    "item_code": item_code,
                    "pos_rate": current_rate,
                    "return_rate": requested_rate,
                }
            )

        invoice_items.append(
            {
                "item_code": item_code,
                "item_name": detail.get("item_name") or row.get("item_name") or item_code,
                "qty": -qty,
                "rate": final_rate,
                "price_list_rate": current_rate,
                # Return Without Invoice always receives stock into the active
                # POS Profile warehouse. This is validated again server-side by
                # the generic invoice submit path.
                "warehouse": profile.warehouse,
                "uom": detail.get("uom") or uom or detail.get("stock_uom"),
                "conversion_factor": flt(detail.get("conversion_factor") or 1) or 1,
                "is_rate_manually_edited": 1 if changed else 0,
                "original_rate": current_rate if changed else None,
            }
        )

    if not invoice_items:
        frappe.throw(_("No valid return items were supplied."))

    manager_required = bool(settings["require_manager_pin_no_invoice_return"])
    if refund_type == "cash" and settings["require_manager_pin_cash_refund"]:
        manager_required = True
    if rate_overrides and settings["require_manager_pin_rate_override"]:
        manager_required = True

    manager = _verify_manager_pin(manager_pin) if manager_required else {"approver": "Not Required"}

    override_text = ""
    if rate_overrides:
        override_text = " | Rate overrides: " + ", ".join(
            f"{row['item_code']} {row['pos_rate']}->{row['return_rate']}" for row in rate_overrides
        )
    audit_prefix = "EXCHANGE WITHOUT INVOICE" if exchange_mode else "NO-INVOICE RETURN"
    audit_remarks = _(
        "{0} | Reason: {1} | Approved by: {2} | Cashier: {3}{4}"
    ).format(audit_prefix, reason, manager["approver"], frappe.session.user, override_text)

    invoice_data = {
        "doctype": "Sales Invoice",
        "pos_profile": pos_profile,
        "posa_pos_opening_shift": pos_opening_shift,
        "customer": customer,
        "company": profile.company,
        "selling_price_list": profile.selling_price_list,
        "is_return": 1,
        "is_pos": 1,
        "update_stock": 1,
        "items": invoice_items,
        "payments": [],
        "remarks": audit_remarks,
        "add_to_customer_balance": False,
    }

    frappe.flags.pos_next_no_invoice_return_approved = {
        "approver": manager["approver"],
        "reason": reason,
        "refund_type": refund_type,
    }

    try:
        from pos_next.api.invoices import submit_invoice, update_invoice

        draft = update_invoice(json.dumps(invoice_data))
        if not draft or not draft.get("name"):
            frappe.throw(_("Failed to prepare no-invoice return."))

        refund_amount = abs(flt(draft.get("grand_total") or 0))
        if refund_amount <= 0:
            frappe.throw(_("The calculated return amount must be greater than zero."))

        if refund_type == "cash":
            draft["payments"] = [
                {
                    "mode_of_payment": cash_mode,
                    "amount": -refund_amount,
                }
            ]
        else:
            draft["payments"] = []

        result = submit_invoice(invoice=draft, data={})
    finally:
        frappe.flags.pos_next_no_invoice_return_approved = None

    result = result or {}
    result.update(
        {
            "customer": customer,
            "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
            "refund_type": refund_type,
            "approved_by": manager["approver"],
            "reason": reason,
            "rate_overrides": rate_overrides,
            "no_invoice_return": True,
            "exchange_mode": exchange_mode,
        }
    )
    return result
