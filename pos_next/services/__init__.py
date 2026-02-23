"""
Services module for external app integrations.

This module provides clean interfaces to optional external apps,
with graceful fallbacks when they're not installed.
"""

from pos_next.services.barcode import (
    compute_resolved_item_data,
    is_barcode_resolver_available,
    resolve_barcode,
)

__all__ = ["compute_resolved_item_data", "is_barcode_resolver_available", "resolve_barcode"]
