"""
Barcode resolver service for POS Next.

This module provides an optional integration with the barcode_resolver app.
When barcode_resolver is installed, it enables advanced barcode parsing
for weighted and priced barcodes. When not installed, it gracefully
returns None.

Usage:
    from pos_next.services import resolve_barcode, is_barcode_resolver_available

    # Check if feature is available
    if is_barcode_resolver_available():
        result = resolve_barcode("2001234001234")
        if result:
            print(result["item_barcode"], result["qty"])

    # Or simply call resolve_barcode (returns None if app not installed)
    result = resolve_barcode("2001234001234")
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, TypedDict

import frappe
from erpnext.stock.get_item_details import get_conversion_factor


class BarcodeResult(TypedDict, total=False):
    """Type definition for barcode resolution result."""

    item_barcode: str  # The barcode from Item Barcodes table
    integer_value: str  # Integer part of the encoded value
    decimal_value: str  # Decimal part of the encoded value
    barcode_type: str  # "Weighted" or "Priced"
    uom: str | None  # UOM from Item Barcodes table
    qty: float | None  # Quantity (only for weighted barcodes)


class ResolvedItemData(TypedDict, total=False):
    """Type definition for resolved item data to be applied to cart."""

    resolved_qty: float | None
    resolved_uom: str | None
    resolved_price: float | None
    resolved_barcode_type: str | None


@lru_cache(maxsize=1)
def is_barcode_resolver_available() -> bool:
    """
    Check if the barcode_resolver app is installed.

    Returns:
        bool: True if barcode_resolver is available, False otherwise.

    Note:
        Result is cached for performance. Server restart clears the cache.
    """
    return "barcode_resolver" in frappe.get_installed_apps()


def resolve_barcode(barcode: str, pos_profile: str) -> BarcodeResult | None:
    """
    Resolve a barcode using the barcode_resolver app if available.

    This function attempts to parse special barcode formats (weighted/priced)
    using configurable rules from the barcode_resolver app.

    Args:
        barcode: The barcode string to resolve.

    Returns:
        BarcodeResult dict if the barcode matches a rule, None otherwise.
        Also returns None if barcode_resolver app is not installed.

    Example:
        >>> result = resolve_barcode("2001234001500")
        >>> if result:
        ...     print(f"Item: {result['item_barcode']}, Qty: {result['qty']}")
    """
    if not is_barcode_resolver_available():
        return None

    try:
        from barcode_resolver.barcode_resolver.doctype.barcode_rule.utils import (
            resolve_barcode as _resolve_barcode,
        )
    except ImportError:
        is_barcode_resolver_available.cache_clear()
        return None

    barcode_rules = _get_barcode_rules_for_profile(pos_profile)

    try:
        return _resolve_barcode(barcode, barcode_rules)
    except Exception:
        frappe.log_error(
            title="Barcode Resolver Error",
            message=f"Error resolving barcode {barcode!r} for profile {pos_profile!r}\n\n{frappe.get_traceback()}",
        )
        return None


def _get_barcode_rules_for_profile(pos_profile: str) -> list[str] | None:
    """Return enabled Barcode Rule names for the given POS Profile.

    Returns None when no per-profile configuration exists, which signals
    the resolver to consider every active Barcode Rule. This keeps the
    resolver functional on sites that have not yet migrated to the
    POS Next `POS Settings` doctype (which adds `pos_profile` +
    `barcode_rules`).
    """
    settings_name = frappe.db.get_value(
        "POS Settings", {"pos_profile": pos_profile}, "name"
    )
    if not settings_name:
        return None

    try:
        settings_doc = frappe.get_cached_doc("POS Settings", settings_name)
    except Exception:
        return None

    rules_table = getattr(settings_doc, "barcode_rules", None) or []
    return [row.barcode_rule for row in rules_table if not row.disable]


def compute_resolved_item_data(
    resolved_barcode: BarcodeResult | None,
    item,
) -> ResolvedItemData | None:
    """
    Compute qty and uom from resolved barcode data.

    For weighted barcodes: uses qty directly from the barcode.
    For priced barcodes: computes qty = encoded_price / item_rate.

    Args:
        resolved_barcode: The result from resolve_barcode().
        item_rate: The item's unit price (required for priced barcodes).

    Returns:
        ResolvedItemData with resolved_qty, resolved_uom, and resolved_barcode_type,
        or None if no valid resolution.

    Example:
        >>> resolved = resolve_barcode("2001234001500")
        >>> if resolved:
        ...     item_data = compute_resolved_item_data(resolved, item_rate=10.0)
        ...     print(f"Qty: {item_data['resolved_qty']}, UOM: {item_data['resolved_uom']}")
    """
    if not resolved_barcode or not is_barcode_resolver_available():
        return None

    from barcode_resolver.barcode_resolver.doctype.barcode_rule.utils import BarcodeTypes

    barcode_type = resolved_barcode.get("barcode_type")
    barcode_uom = resolved_barcode.get("uom")
    # If barcode resolver didn't provide a UOM, fall back to item's stock UOM
    if not barcode_uom:
        barcode_uom = item.get("uom")
    uom_prices = item.get("uom_prices", {})
    barcode_uom_price = uom_prices.get(barcode_uom)
    item_uom = item.get("uom")
    item_price = item.get("rate")
    item_name = item.get("item_code")
    if item_name is None:
        frappe.log_error(
            title="Barcode Resolver Error",
            message=f"Item code is missing in item data: {item}",
        )
        return None

    # Upstream barcode_resolver returns parsed values directly (qty for weighted,
    # price for priced) and no longer exposes raw integer/decimal segments.
    encoded_qty = resolved_barcode.get("qty")
    encoded_price = resolved_barcode.get("price")
    if barcode_type == BarcodeTypes.WEIGHTED.value:
        if encoded_qty is None:
            return None
        qty = float(encoded_qty)
        uom = barcode_uom
        price = barcode_uom_price
        if barcode_uom not in uom_prices:
            conversion_factor = get_conversion_factor(item_name, barcode_uom).get("conversion_factor", 1)
            qty *= conversion_factor
            uom = item_uom
            price = item_price

        return {
            "resolved_qty": qty,
            "resolved_uom": uom,
            "resolved_price": price,
            "resolved_barcode_type": barcode_type,
        }
    elif barcode_type == BarcodeTypes.PRICED.value:
        if encoded_price is None:
            return None
        encoded_price = float(encoded_price)
        if barcode_uom in uom_prices:
            barcode_uom_price = uom_prices.get(barcode_uom)
            price = barcode_uom_price
            uom = barcode_uom
            qty = encoded_price / price if price and price > 0 else None
        else:
            conversion_factor = get_conversion_factor(item_name, barcode_uom).get("conversion_factor", 1)
            uom = barcode_uom
            price = conversion_factor * item_price
            # Add the calculated price as this barcode_uom price
            uom_prices[barcode_uom] = price
            qty = encoded_price / price if price and price > 0 else None
        return {
            "resolved_qty": qty,
            "resolved_uom": uom,
            "resolved_price": encoded_price,
            "resolved_barcode_type": barcode_type,
        }

    return None
