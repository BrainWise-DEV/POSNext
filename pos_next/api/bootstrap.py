# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Bootstrap API - Optimized initial data loading

This endpoint combines multiple API calls into a single request to reduce
initial page load time. Instead of making 5+ sequential API calls, the
frontend can fetch all initial data in one request.

Performance improvement: ~300-500ms faster initial load
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_initial_data():
	"""
	Get all initial data needed for POS application startup.

	Combines the following into a single API call:
	- User language preference
	- Current open shift (if any)
	- POS Profile data (if shift is open)
	- POS Settings (if shift is open)
	- Payment methods (if shift is open)

	Returns:
		dict: Combined initial data for POS startup
	"""
	# Check authentication
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	result = {
		"success": True,
		"locale": get_user_language(),
		"shift": None,
		"pos_profile": None,
		"pos_settings": None,
		"payment_methods": [],
	}

	# Check for open shift
	shift_data = check_opening_shift()

	if shift_data:
		result["shift"] = {
			"name": shift_data["pos_opening_shift"].name,
			"pos_profile": shift_data["pos_opening_shift"].pos_profile,
			"period_start_date": str(shift_data["pos_opening_shift"].period_start_date),
			"status": shift_data["pos_opening_shift"].status,
		}

		pos_profile_name = shift_data["pos_opening_shift"].pos_profile

		# Get POS Profile data
		result["pos_profile"] = get_pos_profile_data(pos_profile_name)

		# Get POS Settings
		result["pos_settings"] = get_pos_settings(pos_profile_name)

		# Get Payment Methods
		result["payment_methods"] = get_payment_methods(pos_profile_name)

	return result


def get_user_language():
	"""Get the language preference for the current user"""
	language = frappe.db.get_value("User", frappe.session.user, "language") or "en"
	return language.lower()


def check_opening_shift():
	"""Check if user has an open shift"""
	user = frappe.session.user

	open_shifts = frappe.db.get_all(
		"POS Opening Shift",
		filters={
			"user": user,
			"pos_closing_shift": ["is", "not set"],
			"docstatus": 1,
			"status": "Open",
		},
		fields=["name", "pos_profile", "period_start_date"],
		order_by="period_start_date desc",
	)

	if not open_shifts:
		return None

	# Get the latest open shift
	shift_data = open_shifts[0]
	data = {}
	data["pos_opening_shift"] = frappe.get_doc("POS Opening Shift", shift_data["name"])
	data["pos_profile"] = frappe.get_doc("POS Profile", shift_data["pos_profile"])
	data["company"] = frappe.get_doc("Company", data["pos_profile"].company)

	return data


def get_pos_profile_data(pos_profile):
	"""Get POS Profile data as dict"""
	if not pos_profile:
		return None

	profile_doc = frappe.get_doc("POS Profile", pos_profile)

	return {
		"name": profile_doc.name,
		"company": profile_doc.company,
		"currency": profile_doc.currency,
		"warehouse": profile_doc.warehouse,
		"selling_price_list": profile_doc.selling_price_list,
		"customer": profile_doc.customer,
		"write_off_account": profile_doc.write_off_account,
		"write_off_cost_center": profile_doc.write_off_cost_center,
		"print_format": profile_doc.get("print_format"),
		"auto_print": profile_doc.get("print_receipt_on_order_complete", 0),
		"country": profile_doc.get("country"),
	}


def get_pos_settings(pos_profile):
	"""Get POS Settings for a given POS Profile"""
	from pos_next.api.constants import POS_SETTINGS_FIELDS, DEFAULT_POS_SETTINGS

	if not pos_profile:
		return DEFAULT_POS_SETTINGS.copy()

	try:
		pos_settings = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile, "enabled": 1},
			POS_SETTINGS_FIELDS,
			as_dict=True
		)

		if not pos_settings:
			return DEFAULT_POS_SETTINGS.copy()

		return pos_settings
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Get POS Settings Error")
		return DEFAULT_POS_SETTINGS.copy()


def get_payment_methods(pos_profile):
	"""Get available payment methods from POS Profile with a single optimized query"""
	if not pos_profile:
		return []

	try:
		from frappe.query_builder import DocType
		from frappe.query_builder.functions import Coalesce

		POSPaymentMethod = DocType("POS Payment Method")
		ModeOfPayment = DocType("Mode of Payment")

		# Single JOIN query instead of N+1 queries
		query = (
			frappe.qb.from_(POSPaymentMethod)
			.left_join(ModeOfPayment)
			.on(POSPaymentMethod.mode_of_payment == ModeOfPayment.name)
			.select(
				POSPaymentMethod.mode_of_payment,
				POSPaymentMethod.default,
				POSPaymentMethod.allow_in_returns,
				Coalesce(ModeOfPayment.type, "Cash").as_("type")
			)
			.where(POSPaymentMethod.parent == pos_profile)
			.orderby(POSPaymentMethod.idx)
		)

		payment_methods = query.run(as_dict=True)
		return payment_methods
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Get Payment Methods Error")
		return []
