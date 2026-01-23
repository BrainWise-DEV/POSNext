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
	if not pos_profile:
		return get_default_pos_settings()

	try:
		pos_settings = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile, "enabled": 1},
			[
				"name",
				"enabled",
				"tax_inclusive",
				"allow_user_to_edit_additional_discount",
				"allow_user_to_edit_item_discount",
				"use_percentage_discount",
				"max_discount_allowed",
				"disable_rounded_total",
				"allow_credit_sale",
				"allow_return",
				"allow_write_off_change",
				"allow_partial_payment",
				"use_exact_amount",
				"decimal_precision",
				"allow_negative_stock",
				"enable_sales_persons",
				"silent_print",
				"allow_sales_order",
				"allow_select_sales_order",
				"create_only_sales_order"
			],
			as_dict=True
		)

		if not pos_settings:
			return get_default_pos_settings()

		return pos_settings
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Get POS Settings Error")
		return get_default_pos_settings()


def get_default_pos_settings():
	"""Return default POS Settings"""
	return {
		"enabled": 0,
		"tax_inclusive": 0,
		"allow_user_to_edit_additional_discount": 0,
		"allow_user_to_edit_item_discount": 1,
		"use_percentage_discount": 0,
		"max_discount_allowed": 0,
		"disable_rounded_total": 1,
		"allow_credit_sale": 0,
		"allow_return": 0,
		"allow_write_off_change": 0,
		"allow_partial_payment": 0,
		"use_exact_amount": 0,
		"decimal_precision": "2",
		"allow_negative_stock": 0,
		"enable_sales_persons": "Disabled",
		"silent_print": 0,
		"allow_sales_order": 0,
		"allow_select_sales_order": 0,
		"create_only_sales_order": 0
	}


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
