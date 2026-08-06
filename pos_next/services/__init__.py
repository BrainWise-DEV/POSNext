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
from pos_next.services.miraaya_loyalty import (
	add_lp_points,
	get_lp_balance,
	is_magento_loyalty_mode,
	is_miraaya_loyalty_available,
	redeem_lp_points,
	register_customer_pos,
)

__all__ = [
	"add_lp_points",
	"compute_resolved_item_data",
	"get_lp_balance",
	"is_barcode_resolver_available",
	"is_magento_loyalty_mode",
	"is_miraaya_loyalty_available",
	"redeem_lp_points",
	"register_customer_pos",
	"resolve_barcode",
]
