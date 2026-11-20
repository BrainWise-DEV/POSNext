# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Return Without Invoice support for POSNext.

Standalone POS returns are server-priced using the active POS Profile and are
submitted through the normal Sales Invoice flow. Authorization is handled by
POSNext's generic ``Sales Return Without Invoice`` authorization action.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt


def _as_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value) if value else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            frappe.throw(_("Invalid return data."))

    if not isinstance(value, dict):
        frappe.throw(_("Invalid return data."))

    return frappe._dict(value)


def _get_return_settings(pos_profile):
    return frappe.db.get_value(
        "POS Settings",
        {
            "pos_profile": pos_profile,
            "enabled": 1,
        },
        [
            "allow_return",
            "allow_return_without_invoice",
        ],
        as_dict=True,
    ) or frappe._dict()


def _validate_shift(pos_opening_shift, pos_profile):
    """Require the current user's active shift for this POS Profile."""
    if not pos_opening_shift:
        frappe.throw(_("An open POS shift is required."))

    shift = frappe.db.get_value(
        "POS Opening Shift",
        pos_opening_shift,
        [
            "name",
            "pos_profile",
            "docstatus",
            "status",
            "user",
            "pos_closing_shift",
        ],
        as_dict=True,
    )

    if not shift:
        frappe.throw(
            _("POS Opening Shift {0} was not found.").format(pos_opening_shift)
        )

    if shift.pos_profile != pos_profile:
        frappe.throw(
            _("The POS shift does not belong to the selected POS Profile.")
        )

    if shift.user != frappe.session.user:
        frappe.throw(
            _("This POS shift belongs to another cashier."),
            frappe.PermissionError,
        )

    if (
        cint(shift.docstatus) != 1
        or (shift.status or "").lower() != "open"
        or bool(shift.pos_closing_shift)
    ):
        frappe.throw(_("The POS shift is not open."))


def _conversion_factor(item_code, stock_uom, uom):
    if not uom or not stock_uom or uom == stock_uom:
        return 1.0

    return flt(
        frappe.db.get_value(
            "UOM Conversion Detail",
            {
                "parent": item_code,
                "uom": uom,
            },
            "conversion_factor",
        )
        or 0
    )


def _get_server_item_detail(item_code, pos_profile, uom=None):
    """Resolve the return item from the active POS Profile.

    The browser-supplied rate is never authoritative. The active POS Profile
    selling price list and normal POS catalogue are used to resolve the rate.
    """

    from pos_next.api.items import _fetch_item_uom_prices, get_items

    item_code = (item_code or "").strip()
    if not item_code:
        frappe.throw(_("Item is required."))

    profile = frappe.get_cached_doc("POS Profile", pos_profile)

    if not profile.selling_price_list:
        frappe.throw(
            _("Selling Price List is not set in POS Profile {0}.").format(
                pos_profile
            )
        )

    if not profile.warehouse:
        frappe.throw(
            _("Warehouse is not set in POS Profile {0}.").format(pos_profile)
        )

    item_row = frappe.db.get_value(
        "Item",
        item_code,
        [
            "item_name",
            "stock_uom",
            "has_serial_no",
            "has_batch_no",
            "is_sales_item",
            "disabled",
        ],
        as_dict=True,
    )

    if not item_row or cint(item_row.disabled):
        frappe.throw(_("Item {0} was not found or is disabled.").format(item_code))

    if not cint(item_row.is_sales_item):
        frappe.throw(_("Item {0} is not a sales item.").format(item_code))

    # Use the same normal POS catalogue as the sale screen whenever possible.
    normal_rows = get_items(
        pos_profile=pos_profile,
        search_term=item_code,
        start=0,
        limit=30,
        include_variants=1,
        show_variants_as_items=0,
    ) or []

    normal = next(
        (row for row in normal_rows if row.get("item_code") == item_code),
        None,
    ) or {}

    stock_uom = item_row.stock_uom or normal.get("stock_uom")
    target_uom = uom or normal.get("uom") or stock_uom

    conversion_factor = _conversion_factor(
        item_code,
        stock_uom,
        target_uom,
    )

    if (
        target_uom
        and stock_uom
        and target_uom != stock_uom
        and conversion_factor <= 0
    ):
        frappe.throw(
            _("UOM {0} is not configured for item {1}.").format(
                target_uom,
                item_code,
            )
        )

    prices = (
        normal.get("uom_prices")
        or _fetch_item_uom_prices(
            item_code,
            profile.selling_price_list,
        )
        or {}
    )

    rate = 0.0

    if target_uom and target_uom in prices:
        rate = flt(prices.get(target_uom) or 0)

    elif stock_uom and stock_uom in prices:
        stock_rate = flt(prices.get(stock_uom) or 0)
        rate = (
            stock_rate * (conversion_factor or 1)
            if target_uom and target_uom != stock_uom
            else stock_rate
        )

    elif "" in prices:
        stock_rate = flt(prices.get("") or 0)
        rate = (
            stock_rate * (conversion_factor or 1)
            if target_uom and target_uom != stock_uom
            else stock_rate
        )

    else:
        rate = flt(
            normal.get("rate")
            or normal.get("price_list_rate")
            or 0
        )

    return frappe._dict(
        {
            "item_code": item_code,
            "item_name": item_row.item_name or normal.get("item_name") or item_code,
            "stock_uom": stock_uom,
            "uom": target_uom or stock_uom,
            "conversion_factor": conversion_factor or 1,
            "warehouse": profile.warehouse,
            "has_serial_no": cint(item_row.has_serial_no),
            "has_batch_no": cint(item_row.has_batch_no),
            "rate": rate,
            "price_list_rate": rate,
            "selling_price_list": profile.selling_price_list,
        }
    )


def normalize_no_invoice_return(invoice_doc):
    """Server-enforce a POS Return Without Invoice.

    This is also called by the generic invoice APIs so a caller cannot bypass
    the feature setting, active-shift validation, price validation, warehouse,
    or settlement policy by posting directly to ``submit_invoice``.
    """

    if not invoice_doc or invoice_doc.doctype != "Sales Invoice":
        return invoice_doc

    if not cint(invoice_doc.get("is_return")):
        return invoice_doc

    if invoice_doc.get("return_against"):
        return invoice_doc

    # Only apply this policy to POS documents.
    if not invoice_doc.get("is_pos") and not invoice_doc.get("pos_profile"):
        return invoice_doc

    pos_profile = (invoice_doc.get("pos_profile") or "").strip()
    if not pos_profile:
        frappe.throw(_("POS Profile is required for Return Without Invoice."))

    customer = (invoice_doc.get("customer") or "").strip()
    if not customer:
        frappe.throw(_("Customer is required for Return Without Invoice."))

    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} was not found.").format(customer))

    remarks = (invoice_doc.get("remarks") or "").strip()
    if not remarks:
        frappe.throw(_("Return reason is required."))

    settings = _get_return_settings(pos_profile)

    if not cint(settings.get("allow_return")):
        frappe.throw(
            _("Returns are disabled in POS Settings for this POS Profile."),
            frappe.PermissionError,
        )

    if not cint(settings.get("allow_return_without_invoice")):
        frappe.throw(
            _("Return Without Invoice is disabled in POS Settings."),
            frappe.PermissionError,
        )

    pos_opening_shift = (
        invoice_doc.get("posa_pos_opening_shift") or ""
    ).strip()

    _validate_shift(
        pos_opening_shift,
        pos_profile,
    )

    profile = frappe.get_cached_doc("POS Profile", pos_profile)

    if not profile.warehouse:
        frappe.throw(
            _("Warehouse is not set in POS Profile {0}.").format(pos_profile)
        )

    if not profile.selling_price_list:
        frappe.throw(
            _("Selling Price List is not set in POS Profile {0}.").format(
                pos_profile
            )
        )

    items = invoice_doc.get("items") or []
    if not items:
        frappe.throw(_("Add at least one item to return."))

    for row in items:
        item_code = (row.get("item_code") or "").strip()
        qty = abs(flt(row.get("qty") or 0))

        if not item_code or qty <= 0:
            frappe.throw(
                _(
                    "Every return item must have an item code and quantity greater than zero."
                )
            )

        detail = _get_server_item_detail(
            item_code,
            pos_profile,
            uom=row.get("uom"),
        )

        if cint(detail.has_serial_no) or cint(detail.has_batch_no):
            frappe.throw(
                _(
                    "Return Without Invoice does not support serialized or batched item {0}. "
                    "Use Return With Invoice so ERPNext can preserve the original stock identity."
                ).format(item_code)
            )

        # Server owns quantity sign, price and receiving warehouse.
        row.qty = -qty
        row.rate = flt(detail.rate)
        row.price_list_rate = flt(detail.price_list_rate)
        row.warehouse = profile.warehouse
        row.uom = detail.uom
        row.conversion_factor = flt(detail.conversion_factor) or 1

        # A standalone return always uses the current POS price. Browser-side
        # discounts/rate overrides must not change the credit amount.
        if row.meta.has_field("discount_percentage"):
            row.discount_percentage = 0
        if row.meta.has_field("discount_amount"):
            row.discount_amount = 0
        if row.meta.has_field("pricing_rules"):
            row.pricing_rules = ""
        if row.meta.has_field("is_rate_manually_edited"):
            row.is_rate_manually_edited = 0
        if row.meta.has_field("original_rate"):
            row.original_rate = flt(detail.rate)

    invoice_doc.pos_profile = pos_profile
    invoice_doc.company = profile.company
    invoice_doc.selling_price_list = profile.selling_price_list
    invoice_doc.is_return = 1
    invoice_doc.is_pos = 1
    invoice_doc.update_stock = 1

    # Unlike a linked credit note, a standalone return carries its own negative
    # outstanding amount on the return invoice.
    if invoice_doc.meta.has_field("update_outstanding_for_self"):
        invoice_doc.update_outstanding_for_self = 1

    if invoice_doc.meta.has_field("set_warehouse"):
        invoice_doc.set_warehouse = profile.warehouse

    # PR scope: settlement is customer-account credit only.
    invoice_doc.set("payments", [])

    for fieldname in (
        "paid_amount",
        "base_paid_amount",
        "write_off_amount",
        "base_write_off_amount",
        "change_amount",
        "base_change_amount",
    ):
        if invoice_doc.meta.has_field(fieldname):
            invoice_doc.set(fieldname, 0)

    return invoice_doc


@frappe.whitelist()
def search_return_items(search_term, pos_profile, limit=20):
    """Search return candidates without hiding zero-stock items."""

    term = (search_term or "").strip()
    if len(term) < 2:
        return []

    if not pos_profile:
        frappe.throw(_("POS Profile is required."))

    # Ensure the profile itself is valid before exposing item search.
    frappe.get_cached_doc("POS Profile", pos_profile)

    limit = max(1, min(cint(limit) or 20, 30))
    like = f"%{term}%"

    return frappe.db.sql(
        """
        SELECT DISTINCT
            i.name AS item_code,
            i.item_name,
            i.stock_uom
        FROM `tabItem` i
        LEFT JOIN `tabItem Barcode` ib
            ON ib.parent = i.name
        WHERE i.disabled = 0
          AND i.is_sales_item = 1
          AND (
                i.name LIKE %(like)s
             OR i.item_name LIKE %(like)s
             OR ib.barcode = %(exact)s
             OR ib.barcode LIKE %(like)s
          )
        ORDER BY
            CASE
                WHEN i.name = %(exact)s OR ib.barcode = %(exact)s
                THEN 0
                ELSE 1
            END,
            i.item_name,
            i.name
        LIMIT %(limit)s
        """,
        {
            "like": like,
            "exact": term,
            "limit": limit,
        },
        as_dict=True,
    )


@frappe.whitelist()
def get_return_item_details(
    item_code,
    pos_profile,
    qty=1,
    uom=None,
):
    if not pos_profile:
        frappe.throw(_("POS Profile is required."))

    return _get_server_item_detail(
        item_code,
        pos_profile,
        uom=uom,
    )


@frappe.whitelist()
def prepare_no_invoice_return(payload=None):
    """Create a server-priced draft and return its authoritative amount."""

    payload = _as_dict(payload)

    pos_profile = (payload.get("pos_profile") or "").strip()
    pos_opening_shift = (payload.get("pos_opening_shift") or "").strip()

    customer = payload.get("customer")
    if isinstance(customer, dict):
        customer = customer.get("name")
    customer = (customer or "").strip()

    reason = (payload.get("reason") or "").strip()
    items = payload.get("items") or []

    if not pos_profile:
        frappe.throw(_("POS Profile is required."))

    if not customer:
        frappe.throw(_("Customer is required for Return Without Invoice."))

    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} was not found.").format(customer))

    if not reason:
        frappe.throw(_("Return reason is required."))

    if not isinstance(items, list) or not items:
        frappe.throw(_("Add at least one item to return."))

    settings = _get_return_settings(pos_profile)

    if not cint(settings.get("allow_return")):
        frappe.throw(
            _("Returns are disabled in POS Settings for this POS Profile."),
            frappe.PermissionError,
        )

    if not cint(settings.get("allow_return_without_invoice")):
        frappe.throw(
            _("Return Without Invoice is disabled in POS Settings."),
            frappe.PermissionError,
        )

    _validate_shift(
        pos_opening_shift,
        pos_profile,
    )

    profile = frappe.get_cached_doc("POS Profile", pos_profile)

    if not profile.warehouse:
        frappe.throw(
            _("Warehouse is not set in POS Profile {0}.").format(pos_profile)
        )

    if not profile.selling_price_list:
        frappe.throw(
            _("Selling Price List is not set in POS Profile {0}.").format(
                pos_profile
            )
        )

    invoice_items = []

    for source in items:
        if not isinstance(source, dict):
            continue

        item_code = (source.get("item_code") or "").strip()
        qty = abs(
            flt(
                source.get("qty")
                or source.get("quantity")
                or 0
            )
        )

        if not item_code or qty <= 0:
            frappe.throw(
                _(
                    "Every return item must have an item code and quantity greater than zero."
                )
            )

        detail = _get_server_item_detail(
            item_code,
            pos_profile,
            uom=source.get("uom"),
        )

        if cint(detail.has_serial_no) or cint(detail.has_batch_no):
            frappe.throw(
                _(
                    "Return Without Invoice does not support serialized or batched item {0}. "
                    "Use Return With Invoice so ERPNext can preserve the original stock identity."
                ).format(item_code)
            )

        invoice_items.append(
            {
                "item_code": item_code,
                "item_name": detail.item_name,
                "qty": -qty,
                "rate": flt(detail.rate),
                "price_list_rate": flt(detail.price_list_rate),
                "warehouse": profile.warehouse,
                "uom": detail.uom,
                "conversion_factor": flt(detail.conversion_factor) or 1,
            }
        )

    if not invoice_items:
        frappe.throw(_("No valid return items were supplied."))

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
        "update_outstanding_for_self": 1,
        "items": invoice_items,
        "payments": [],
        "remarks": _(
            "NO-INVOICE RETURN | Reason: {0} | Cashier: {1}"
        ).format(
            reason,
            frappe.session.user,
        ),
    }

    from pos_next.api.invoices import update_invoice

    draft = update_invoice(json.dumps(invoice_data))

    if not draft or not draft.get("name"):
        frappe.throw(_("Failed to prepare Return Without Invoice."))

    refund_amount = abs(flt(draft.get("grand_total") or 0))
    if refund_amount <= 0:
        # Avoid leaving an unusable draft behind.
        try:
            doc = frappe.get_doc("Sales Invoice", draft.get("name"))
            if doc.docstatus == 0:
                doc.flags.ignore_permissions = True
                doc.delete()
        except Exception:
            pass

        frappe.throw(
            _("The calculated return amount must be greater than zero.")
        )

    return {
        "name": draft.get("name"),
        "customer": customer,
        "customer_name": (
            frappe.db.get_value("Customer", customer, "customer_name")
            or customer
        ),
        "grand_total": draft.get("grand_total"),
        "currency": draft.get("currency"),
    }


@frappe.whitelist()
def submit_no_invoice_return(name, authorization_token=None):
    """Submit a prepared standalone return through the normal invoice pipeline."""

    name = (name or "").strip()
    if not name:
        frappe.throw(_("Return draft is required."))

    doc = frappe.get_doc("Sales Invoice", name)

    if doc.docstatus != 0:
        frappe.throw(_("Return draft {0} is no longer editable.").format(name))

    if not cint(doc.is_return) or doc.return_against:
        frappe.throw(
            _("Invoice {0} is not a Return Without Invoice draft.").format(name)
        )

    # Revalidate/reprice immediately before submission.
    normalize_no_invoice_return(doc)

    invoice = doc.as_dict()
    invoice["authorization_token"] = authorization_token or None

    from pos_next.api.invoices import submit_invoice

    result = submit_invoice(
        invoice=invoice,
        data={},
    ) or {}

    result["no_invoice_return"] = True
    result["customer"] = doc.customer
    result["customer_name"] = (
        frappe.db.get_value(
            "Customer",
            doc.customer,
            "customer_name",
        )
        or doc.customer
    )

    return result


@frappe.whitelist()
def discard_no_invoice_return_draft(name):
    """Delete a prepared no-invoice return if authorization is cancelled."""

    name = (name or "").strip()
    if not name or not frappe.db.exists("Sales Invoice", name):
        return {"discarded": False}

    doc = frappe.get_doc("Sales Invoice", name)

    if doc.docstatus != 0:
        return {"discarded": False}

    if not cint(doc.is_return) or doc.return_against:
        frappe.throw(
            _("Invoice {0} is not a Return Without Invoice draft.").format(name)
        )

    if doc.owner != frappe.session.user:
        frappe.throw(
            _("You cannot discard another user's return draft."),
            frappe.PermissionError,
        )

    doc.flags.ignore_permissions = True
    doc.delete()

    return {"discarded": True}
