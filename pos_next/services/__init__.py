"""
Services module for external app integrations.

This module provides clean interfaces to optional external apps,
with graceful fallbacks when they're not installed.
"""

from pos_next.services.barcode import (
    resolve_barcode,
    is_barcode_resolver_available,
    compute_resolved_item_data,
)

__all__ = ["resolve_barcode", "is_barcode_resolver_available", "compute_resolved_item_data"]
