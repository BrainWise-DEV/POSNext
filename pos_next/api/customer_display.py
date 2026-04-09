# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Customer Display API for POS Next.
Handles authentication, cart synchronization, and customer creation
for secondary display screens.
"""

import json
import frappe
from frappe import _
from frappe.utils import cint, flt, now


# Cache key prefix for cart data
CART_CACHE_PREFIX = "pos_next_cart_"
CART_CACHE_TTL = 3600  # 1 hour TTL for cart cache


@frappe.whitelist(allow_guest=True)
def validate_api_key(api_key_string):
    """
    Validate API key and return user information.

    API key format: api_key:api_secret

    Args:
        api_key_string (str): Combined api_key:api_secret string

    Returns:
        dict: User information if valid, error if invalid
    """
    if not api_key_string:
        frappe.throw(_("API key is required"), frappe.AuthenticationError)

    # Split api_key:api_secret
    parts = api_key_string.split(":")
    if len(parts) != 2:
        frappe.throw(_("Invalid API key format. Expected format: api_key:api_secret"), frappe.AuthenticationError)

    api_key, api_secret = parts

    # Find user with this API key
    user = frappe.db.get_value(
        "User",
        {"api_key": api_key, "enabled": 1},
        ["name", "full_name", "email"],
        as_dict=True
    )

    if not user:
        frappe.throw(_("Invalid API key"), frappe.AuthenticationError)

    # Validate API secret
    user_doc = frappe.get_doc("User", user.name)
    if not user_doc.api_secret:
        frappe.throw(_("API secret not configured for this user"), frappe.AuthenticationError)

    # Compare secrets (api_secret is stored encrypted, get_password decrypts it)
    stored_secret = user_doc.get_password("api_secret")
    if stored_secret != api_secret:
        frappe.throw(_("Invalid API secret"), frappe.AuthenticationError)

    # Set session user for subsequent calls
    frappe.set_user(user.name)

    return {
        "success": True,
        "user": user.name,
        "full_name": user.full_name,
        "email": user.email
    }


@frappe.whitelist()
def get_pos_profiles():
    """
    Get list of POS profiles accessible to the current user.

    Returns:
        list: List of POS profiles with name, company, warehouse
    """
    profiles = frappe.db.sql(
        """
        SELECT DISTINCT p.name, p.company, p.warehouse, p.currency
        FROM `tabPOS Profile` p
        INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
        WHERE p.disabled = 0 AND u.user = %s
        ORDER BY p.name
        """,
        frappe.session.user,
        as_dict=True
    )

    return profiles


@frappe.whitelist()
def get_pos_opening_entry(pos_profile):
    """
    Get the active POS Opening Entry for a given POS profile.

    Args:
        pos_profile (str): POS Profile name

    Returns:
        dict: POS Opening Entry details or None if no active session
    """
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Find open shift for this profile (any user)
    open_entry = frappe.db.get_value(
        "POS Opening Shift",
        {
            "pos_profile": pos_profile,
            "docstatus": 1,
            "status": "Open",
            "pos_closing_shift": ["is", "not set"]
        },
        ["name", "user", "pos_profile", "company", "period_start_date"],
        as_dict=True,
        order_by="period_start_date desc"
    )

    if not open_entry:
        return None

    # Get POS profile details
    profile = frappe.get_cached_doc("POS Profile", pos_profile)

    # Get company country for address preselection
    company_country = None
    if open_entry.company:
        company_country = frappe.db.get_value("Company", open_entry.company, "country")

    return {
        "pos_opening_entry": open_entry.name,
        "user": open_entry.user,
        "pos_profile": open_entry.pos_profile,
        "company": open_entry.company,
        "period_start_date": open_entry.period_start_date,
        "currency": profile.currency,
        "warehouse": profile.warehouse,
        "country": company_country
    }


@frappe.whitelist()
def get_display_settings(pos_profile):
    """
    Get customer display settings from POS Settings.

    Args:
        pos_profile (str): POS Profile name

    Returns:
        dict: Display settings
    """
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    # Get POS Settings for this profile
    settings = frappe.db.get_value(
        "POS Settings",
        {"pos_profile": pos_profile, "enabled": 1},
        [
            "enable_customer_display",
            "enable_customer_display_account_creation",
            "customer_display_show_address_fields"
        ],
        as_dict=True
    )

    if not settings:
        # Return defaults if no settings found
        return {
            "enable_customer_display": False,
            "enable_account_creation": False,
            "show_address_fields": False
        }

    return {
        "enable_customer_display": bool(settings.enable_customer_display),
        "enable_account_creation": bool(settings.enable_customer_display_account_creation),
        "show_address_fields": bool(settings.customer_display_show_address_fields)
    }


@frappe.whitelist()
def update_cart_data(pos_opening_entry, cart_data):
    """
    Store cart data in Redis cache and emit realtime event.
    Called by the main POS when cart changes.

    Args:
        pos_opening_entry (str): POS Opening Entry name
        cart_data (str|dict): Cart data JSON

    Returns:
        dict: Success status
    """
    if not pos_opening_entry:
        frappe.throw(_("POS Opening Entry is required"))

    # Parse cart data if string
    if isinstance(cart_data, str):
        cart_data = json.loads(cart_data)

    # Validate POS Opening Entry exists and is open
    entry = frappe.db.get_value(
        "POS Opening Shift",
        pos_opening_entry,
        ["name", "status", "pos_profile"],
        as_dict=True
    )

    if not entry:
        frappe.throw(_("POS Opening Entry not found"))

    if entry.status != "Open":
        frappe.throw(_("POS session is not open"))

    # Add metadata
    cart_data["_updated_at"] = now()
    cart_data["_pos_opening_entry"] = pos_opening_entry

    # Store in Redis cache
    cache_key = f"{CART_CACHE_PREFIX}{pos_opening_entry}"
    frappe.cache().set_value(cache_key, cart_data, expires_in_sec=CART_CACHE_TTL)

    # Emit realtime event to customer display
    frappe.publish_realtime(
        event=f"pos_cart_updated_{pos_opening_entry}",
        message=cart_data,
        user=None,  # Broadcast to all
        after_commit=False  # Emit immediately for responsiveness
    )

    return {"success": True}


@frappe.whitelist()
def get_current_cart(pos_opening_entry):
    """
    Get current cart data from cache.

    Args:
        pos_opening_entry (str): POS Opening Entry name

    Returns:
        dict: Cart data or empty cart structure
    """
    if not pos_opening_entry:
        frappe.throw(_("POS Opening Entry is required"))

    # Try to get from Redis cache
    cache_key = f"{CART_CACHE_PREFIX}{pos_opening_entry}"
    cart_data = frappe.cache().get_value(cache_key)

    if cart_data:
        return cart_data

    # Return empty cart structure if not found
    return {
        "items": [],
        "customer": None,
        "customer_name": None,
        "subtotal": 0,
        "total_tax": 0,
        "discount_amount": 0,
        "grand_total": 0,
        "currency": "EUR",
        "_updated_at": None,
        "_pos_opening_entry": pos_opening_entry
    }


@frappe.whitelist()
def create_customer_from_display(customer_name, pos_opening_entry, email=None, mobile_no=None,
                                  address_line1=None, city=None, pincode=None, country=None):
    """
    Create a new customer from the customer display.
    Optionally creates an address if address fields are provided.
    Notifies the main POS via realtime event.

    Args:
        customer_name (str): Customer name (required)
        pos_opening_entry (str): POS Opening Entry name (required)
        email (str): Email address (optional)
        mobile_no (str): Mobile number (optional)
        address_line1 (str): Street address (optional)
        city (str): City (optional)
        pincode (str): Postal code (optional)
        country (str): Country (optional)

    Returns:
        dict: Created customer data
    """
    if not customer_name:
        frappe.throw(_("Customer name is required"))

    if not pos_opening_entry:
        frappe.throw(_("POS Opening Entry is required"))

    # Check permission
    if not frappe.has_permission("Customer", "create"):
        frappe.throw(_("You don't have permission to create customers"), frappe.PermissionError)

    # Get POS profile to determine company and customer settings
    entry = frappe.db.get_value(
        "POS Opening Shift",
        pos_opening_entry,
        ["pos_profile", "company"],
        as_dict=True
    )

    if not entry:
        frappe.throw(_("POS Opening Entry not found"))

    # Get default customer group and territory from POS profile or system defaults
    profile = frappe.get_cached_doc("POS Profile", entry.pos_profile)

    # Get customer group from profile, or find system default
    customer_group = None
    if hasattr(profile, "customer_group") and profile.customer_group:
        customer_group = profile.customer_group

    if not customer_group:
        # Try to get a valid customer group (prefer "Individual" variants)
        customer_group = frappe.db.get_value(
            "Customer Group",
            {"is_group": 0},
            "name",
            order_by="name"
        )

    if not customer_group:
        frappe.throw(_("No customer group found. Please configure a customer group."))

    # Get territory from selling settings or first available
    territory = frappe.db.get_single_value("Selling Settings", "territory") or frappe.db.get_value(
        "Territory",
        {"is_group": 0},
        "name",
        order_by="name"
    )

    if not territory:
        frappe.throw(_("No territory found. Please configure a territory."))

    # Get default loyalty program
    loyalty_program = None
    if entry.company:
        loyalty_program = frappe.db.get_value(
            "Loyalty Program",
            {"company": entry.company, "auto_opt_in": 1},
            "name"
        )

    # Get default currency from POS profile or company
    default_currency = profile.currency if profile.currency else frappe.db.get_value(
        "Company", entry.company, "default_currency"
    )

    # Create customer
    customer = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": "Individual",
        "customer_group": customer_group,
        "territory": territory,
        "mobile_no": mobile_no or "",
        "email_id": email or "",
        "loyalty_program": loyalty_program,
        "default_currency": default_currency
    })

    customer.insert()

    # Create address if address fields are provided
    address_name = None
    if address_line1 or city or pincode or country:
        try:
            address = frappe.get_doc({
                "doctype": "Address",
                "address_title": customer_name,
                "address_type": "Billing",
                "address_line1": address_line1 or "",
                "city": city or "",
                "pincode": pincode or "",
                "country": country or frappe.db.get_default("country") or "Switzerland",
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }]
            })
            address.insert()
            address_name = address.name

            # Set as primary address
            customer.db_set("customer_primary_address", address.name)
        except Exception as e:
            # Log error but don't fail customer creation
            frappe.log_error("Address creation failed", str(e))

    # Emit realtime event to notify POS
    event_name = f"customer_created_{pos_opening_entry}"
    event_data = {
        "name": customer.name,
        "customer_name": customer.customer_name,
        "mobile_no": customer.mobile_no,
        "email_id": customer.email_id,
        "address": address_name,
        "created_from": "customer_display"
    }
    frappe.logger().info(f"Emitting customer_created event: {event_name} with data: {event_data}")
    frappe.publish_realtime(
        event=event_name,
        message=event_data,
        user=None,
        after_commit=True
    )

    return {
        "success": True,
        "customer": customer.as_dict()
    }


@frappe.whitelist()
def clear_cart_cache(pos_opening_entry):
    """
    Clear cart cache for a POS session.
    Called when shift is closed or cart is cleared.

    Args:
        pos_opening_entry (str): POS Opening Entry name

    Returns:
        dict: Success status
    """
    if not pos_opening_entry:
        frappe.throw(_("POS Opening Entry is required"))

    cache_key = f"{CART_CACHE_PREFIX}{pos_opening_entry}"
    frappe.cache().delete_value(cache_key)

    # Emit event to clear display
    frappe.publish_realtime(
        event=f"pos_cart_updated_{pos_opening_entry}",
        message={
            "items": [],
            "customer": None,
            "customer_name": None,
            "subtotal": 0,
            "total_tax": 0,
            "discount_amount": 0,
            "grand_total": 0,
            "currency": "EUR",
            "_cleared": True,
            "_updated_at": now(),
            "_pos_opening_entry": pos_opening_entry
        },
        user=None,
        after_commit=False
    )

    return {"success": True}


@frappe.whitelist()
def notify_sale_complete(pos_opening_entry, invoice_name=None, grand_total=0):
    """
    Notify customer display that a sale has been completed.
    Shows thank you message on the display.

    Args:
        pos_opening_entry (str): POS Opening Entry name
        invoice_name (str): Sales Invoice name (optional)
        grand_total (float): Total amount paid (optional)

    Returns:
        dict: Success status
    """
    if not pos_opening_entry:
        frappe.throw(_("POS Opening Entry is required"))

    # Emit sale complete event
    frappe.publish_realtime(
        event=f"pos_sale_complete_{pos_opening_entry}",
        message={
            "invoice_name": invoice_name,
            "grand_total": flt(grand_total),
            "timestamp": now()
        },
        user=None,
        after_commit=True
    )

    # Clear cart cache after sale
    clear_cart_cache(pos_opening_entry)

    return {"success": True}
