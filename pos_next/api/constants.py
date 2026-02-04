# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Shared constants for POS Next API modules.

This module contains shared constants, field lists, and default values
used across multiple API modules to maintain DRY principles.

Note: Some settings are derived from POS Profile as single source of truth:
- allow_write_off_change: derived from POS Profile (write_off_account + write_off_limit > 0)
- disable_rounded_total: uses POS Profile value directly
"""

# Fields to fetch from POS Settings
# Used by both bootstrap.py and pos_profile.py
POS_SETTINGS_FIELDS = [
	"name",
	"enabled",
	"tax_inclusive",
	"allow_user_to_edit_additional_discount",
	"allow_user_to_edit_item_discount",
	"use_percentage_discount",
	"max_discount_allowed",
	"allow_credit_sale",
	"allow_customer_credit_payment",
	"allow_return",
	"allow_partial_payment",
	"use_exact_amount",
	"decimal_precision",
	"allow_negative_stock",
	"enable_sales_persons",
	"silent_print",
	"allow_sales_order",
	"allow_select_sales_order",
	"create_only_sales_order",
]

# Default POS Settings values
# Used when no POS Settings found or on error
DEFAULT_POS_SETTINGS = {
	"enabled": 0,
	"tax_inclusive": 0,
	"allow_user_to_edit_additional_discount": 0,
	"allow_user_to_edit_item_discount": 1,
	"use_percentage_discount": 0,
	"max_discount_allowed": 0,
	"disable_rounded_total": 0,  # Derived from POS Profile
	"allow_credit_sale": 0,
	"allow_customer_credit_payment": 0,
	"allow_return": 0,
	"allow_write_off_change": 0,  # Derived from POS Profile
	"allow_partial_payment": 0,
	"use_exact_amount": 0,
	"decimal_precision": "2",
	"allow_negative_stock": 0,
	"enable_sales_persons": "Disabled",
	"silent_print": 0,
	"allow_sales_order": 0,
	"allow_select_sales_order": 0,
	"create_only_sales_order": 0,
}
