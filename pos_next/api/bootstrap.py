# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Bootstrap API - POS Application Startup Data

This module provides a single API endpoint that fetches all data needed
to initialize the POS application. Instead of making 5+ sequential API calls,
the frontend fetches everything in one request.

Data Returned:
    - locale: User's language preference (e.g., "en", "ar")
    - precision: Number formatting settings from System Settings
        - currency: Decimal places for totals (default: 2)
        - float: Decimal places for rates/quantities (default: 3)
        - rounding_method: "Banker's Rounding" or "Commercial Rounding"
        - number_format: Pattern like "#,###.##"
    - shift: Current open POS Opening Shift (if any)
    - pos_profile: POS Profile configuration
    - pos_settings: POS-specific settings
    - payment_methods: Available payment methods

Performance: ~300-500ms faster than multiple API calls
"""

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Coalesce

from pos_next.api.constants import POS_SETTINGS_FIELDS, DEFAULT_POS_SETTINGS


@frappe.whitelist()
def get_initial_data():
	"""
	Fetch all initial data needed for POS application startup.

	This is the main bootstrap endpoint called when the POS app loads.
	It combines multiple data sources into a single response.

	Returns:
		dict: {
			success: bool,
			locale: str,
			precision: dict,
			shift: dict | None,
			pos_profile: dict | None,
			pos_settings: dict | None,
			payment_methods: list
		}

	Raises:
		AuthenticationError: If user is not logged in (Guest)
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	result = {
		"success": True,
		"locale": _get_user_language(),
		"precision": _get_precision_settings(),
		"shift": None,
		"pos_profile": None,
		"pos_settings": None,
		"payment_methods": [],
	}

	# Get open shift - if no shift, return early with defaults
	shift = _get_open_shift()
	if not shift:
		return result

	pos_profile = shift["pos_profile_doc"]
	pos_profile_name = pos_profile.name

	result["shift"] = {
		"name": shift["name"],
		"pos_profile": pos_profile_name,
		"period_start_date": str(shift["period_start_date"]),
		"status": shift["status"],
	}

	result["pos_profile"] = {
		"name": pos_profile.name,
		"company": pos_profile.company,
		"currency": pos_profile.currency,
		"warehouse": pos_profile.warehouse,
		"selling_price_list": pos_profile.selling_price_list,
		"customer": pos_profile.customer,
		"write_off_account": pos_profile.write_off_account,
		"write_off_cost_center": pos_profile.write_off_cost_center,
		"write_off_limit": pos_profile.write_off_limit or 0,
		"print_format": pos_profile.get("print_format"),
		"auto_print": pos_profile.get("print_receipt_on_order_complete", 0),
		"country": pos_profile.get("country"),
	}

	result["pos_settings"] = _get_pos_settings(pos_profile)
	result["payment_methods"] = _get_payment_methods(pos_profile_name)

	return result


# =============================================================================
# Private Helper Functions
# =============================================================================

def _get_user_language():
	"""
	Get user's language preference from User doctype.

	Returns:
		str: Language code in lowercase (e.g., "en", "ar", "de")
	"""
	lang = frappe.db.get_value("User", frappe.session.user, "language")
	return (lang or "en").lower()


def _get_precision_settings():
	"""
	Get precision and formatting settings from System Settings.

	Fetches all settings in a single query for performance.
	These settings ensure frontend calculations match ERPNext exactly.

	Returns:
		dict: {
			currency: int - Decimal places for currency totals (default: 2)
			float: int - Decimal places for rates/quantities (default: 3)
			rounding_method: str - "Banker's Rounding" or "Commercial Rounding"
			number_format: str - Number format pattern (e.g., "#,###.##")
		}
	"""
	settings = frappe.db.get_value(
		"System Settings",
		"System Settings",
		["currency_precision", "float_precision", "rounding_method", "number_format"],
		as_dict=True
	)

	return {
		"currency": int(settings.currency_precision) if settings.currency_precision else 2,
		"float": int(settings.float_precision) if settings.float_precision else 3,
		"rounding_method": settings.rounding_method,
		"number_format": settings.number_format,
	}


def _get_open_shift():
	"""
	Get user's currently open POS shift.

	Finds the most recent open shift for the current user and fetches
	the associated POS Profile document for reuse in other functions.

	Returns:
		dict | None: Shift data with 'pos_profile_doc' attached, or None if no open shift
			{
				name: str,
				pos_profile: str,
				period_start_date: datetime,
				status: str,
				pos_profile_doc: Document
			}
	"""
	shift = frappe.db.get_value(
		"POS Opening Shift",
		{
			"user": frappe.session.user,
			"pos_closing_shift": ["is", "not set"],
			"docstatus": 1,
			"status": "Open",
		},
		["name", "pos_profile", "period_start_date", "status"],
		as_dict=True,
		order_by="period_start_date desc",
	)

	if not shift:
		return None

	# Fetch POS Profile once, reuse throughout bootstrap
	shift["pos_profile_doc"] = frappe.get_doc("POS Profile", shift["pos_profile"])
	return shift


def _get_pos_settings(pos_profile_doc):
	"""
	Get POS Settings for the given POS Profile.

	Some settings are derived from POS Profile (single source of truth):
	- allow_write_off_change: Based on write_off_account and write_off_limit
	- disable_rounded_total: Directly from POS Profile

	Args:
		pos_profile_doc: POS Profile document object

	Returns:
		dict: POS Settings with derived values
	"""
	try:
		settings = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile_doc.name, "enabled": 1},
			POS_SETTINGS_FIELDS,
			as_dict=True
		) or DEFAULT_POS_SETTINGS.copy()

		# Derive from POS Profile (single source of truth)
		settings["allow_write_off_change"] = 1 if (
			pos_profile_doc.write_off_account and (pos_profile_doc.write_off_limit or 0) > 0
		) else 0
		settings["disable_rounded_total"] = pos_profile_doc.disable_rounded_total or 0

		return settings
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Get POS Settings Error")
		return DEFAULT_POS_SETTINGS.copy()


def _get_payment_methods(pos_profile_name):
	"""
	Get available payment methods for the POS Profile.

	Uses a single JOIN query to fetch payment methods with their types
	from Mode of Payment, avoiding N+1 query problem.

	Args:
		pos_profile_name: Name of the POS Profile

	Returns:
		list[dict]: Payment methods with fields:
			- mode_of_payment: str
			- default: int (0 or 1)
			- allow_in_returns: int (0 or 1)
			- type: str ("Cash", "Bank", etc.)
	"""
	try:
		POSPaymentMethod = DocType("POS Payment Method")
		ModeOfPayment = DocType("Mode of Payment")

		return (
			frappe.qb.from_(POSPaymentMethod)
			.left_join(ModeOfPayment)
			.on(POSPaymentMethod.mode_of_payment == ModeOfPayment.name)
			.select(
				POSPaymentMethod.mode_of_payment,
				POSPaymentMethod.default,
				POSPaymentMethod.allow_in_returns,
				Coalesce(ModeOfPayment.type, "Cash").as_("type")
			)
			.where(POSPaymentMethod.parent == pos_profile_name)
			.orderby(POSPaymentMethod.idx)
			.run(as_dict=True)
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Get Payment Methods Error")
		return []
