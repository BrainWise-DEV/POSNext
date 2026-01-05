# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from pos_next.api.utilities import check_user_company
from pos_next.api.utilities import _parse_list_parameter

from pos_next.pos_next.doctype.pos_settings.pos_settings import is_item_name_customization_enabled_for_user

@frappe.whitelist()
def get_pos_profiles():
	"""Get all POS Profiles accessible by current user"""
	pos_profiles = frappe.db.sql(
		"""
		SELECT DISTINCT p.name, p.company, p.currency, p.warehouse,
			p.selling_price_list, p.write_off_account, p.write_off_cost_center
		FROM `tabPOS Profile` p
		INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
		WHERE p.disabled = 0 AND u.user = %s
		ORDER BY p.name
		""",
		frappe.session.user,
		as_dict=1,
	)

	return pos_profiles


@frappe.whitelist()
def get_pos_profile_data(pos_profile):
	"""Get detailed POS Profile data"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	# Check if user has access to this POS Profile
	has_access = frappe.db.exists(
		"POS Profile User",
		{"parent": pos_profile, "user": frappe.session.user}
	)

	if not has_access:
		frappe.throw(_("You don't have access to this POS Profile"))

	profile_doc = frappe.get_doc("POS Profile", pos_profile)
	company_doc = frappe.get_doc("Company", profile_doc.company)

	# Get POS Settings for this profile
	pos_settings = get_pos_settings(pos_profile)

	return {
		"pos_profile": profile_doc,
		"company": company_doc,
		"pos_settings": pos_settings,
		"print_settings": {
			"auto_print": profile_doc.get("print_receipt_on_order_complete", 0),
			"print_format": profile_doc.get("print_format"),
			"letter_head": profile_doc.get("letter_head"),
		}
	}


@frappe.whitelist()
def get_pos_settings(pos_profile):
	"""Get POS Settings for a given POS Profile"""
	if not pos_profile:
		return {}

	try:
		# Get POS Settings linked to this POS Profile
		pos_settings = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile, "enabled": 1},
			[
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
				"decimal_precision",
				"allow_negative_stock",
				"enable_sales_persons",
				"allow_sales_order",
				"allow_select_sales_order",
				"create_only_sales_order",
				"allow_custom_item_name_in_cart"
			],
			as_dict=True
		)

		# Return settings or defaults if not found
		if not pos_settings:
			return {
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
				"decimal_precision": "2",
				"allow_negative_stock": 0,
				"enable_sales_persons": "Disabled",
				"allow_sales_order": 0,
				"allow_select_sales_order": 0,
				"create_only_sales_order": 0,
				"allow_custom_item_name_in_cart": 0
			}
		
		pos_settings["allow_custom_item_name_in_cart"] = is_item_name_customization_enabled_for_user(pos_settings)

		return pos_settings
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get POS Settings Error")
		return {}


@frappe.whitelist()
def get_payment_methods(pos_profile):
	"""Get available payment methods from POS Profile"""
	try:
		# Validate pos_profile parameter
		if not pos_profile:
			frappe.throw(_("POS Profile is required"))

		payment_methods = frappe.get_list(
			"POS Payment Method",
			filters={"parent": pos_profile},
			fields=["mode_of_payment", "default", "allow_in_returns"],
			order_by="idx",
			ignore_permissions=True
		)

		# Get payment type for each method
		for method in payment_methods:
			payment_type = frappe.db.get_value(
				"Mode of Payment",
				method["mode_of_payment"],
				"type"
			)
			method["type"] = payment_type or "Cash"

		return payment_methods
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Payment Methods Error")
		frappe.throw(_("Error fetching payment methods: {0}").format(str(e)))


@frappe.whitelist()
def get_taxes(pos_profile):
	"""Get tax configuration from POS Profile"""
	try:
		if not pos_profile:
			return []

		# Get the POS Profile
		profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
		taxes_and_charges = getattr(profile_doc, 'taxes_and_charges', None)

		if not taxes_and_charges:
			return []

		# Get the tax template
		template_doc = frappe.get_cached_doc("Sales Taxes and Charges Template", taxes_and_charges)

		# Extract tax rows
		taxes = []
		for tax_row in template_doc.taxes:
			taxes.append({
				"account_head": tax_row.account_head,
				"charge_type": tax_row.charge_type,
				"rate": tax_row.rate,
				"description": tax_row.description,
				"included_in_print_rate": getattr(tax_row, 'included_in_print_rate', 0),
				"idx": tax_row.idx
			})

		return taxes
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Taxes Error")
		# Return empty array instead of throwing - taxes are optional
		return []


@frappe.whitelist()
def get_warehouses(pos_profile):
	"""Get all warehouses for the company in POS Profile"""
	try:
		if not pos_profile:
			return []

		# Get the company from POS Profile
		company = frappe.db.get_value("POS Profile", pos_profile, "company")

		if not company:
			return []

		# Get all active warehouses for the company
		warehouses = frappe.get_list(
			"Warehouse",
			filters={
				"company": company,
				"disabled": 0,
				"is_group": 0
			},
			fields=["name", "warehouse_name"],
			order_by="warehouse_name",
			limit_page_length=0
		)

		# Return warehouses with human-readable names
		return warehouses
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Warehouses Error")
		return []


@frappe.whitelist()
def get_default_customer(pos_profile):
	"""Get the default customer configured in POS Profile"""
	try:
		if not pos_profile:
			return {"customer": None}

		# Get the default customer from POS Profile
		default_customer = frappe.db.get_value("POS Profile", pos_profile, "customer")

		if default_customer:
			# Get customer details
			customer_doc = frappe.get_doc("Customer", default_customer)
			return {
				"customer": default_customer,
				"customer_name": customer_doc.customer_name,
				"customer_group": customer_doc.customer_group,
			}

		return {"customer": None}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Default Customer Error")
		return {"customer": None}


@frappe.whitelist()
def update_warehouse(pos_profile, warehouse):
	"""Update warehouse in POS Profile"""
	try:
		if not pos_profile:
			frappe.throw(_("POS Profile is required"))

		if not warehouse:
			frappe.throw(_("Warehouse is required"))

		# Check if user has access to this POS Profile
		has_access = frappe.db.exists(
			"POS Profile User",
			{"parent": pos_profile, "user": frappe.session.user}
		)

		if not has_access and not frappe.has_permission("POS Profile", "write"):
			frappe.throw(_("You don't have permission to update this POS Profile"))

		# Get POS Profile to check company
		profile_doc = frappe.get_doc("POS Profile", pos_profile)

		# Validate warehouse exists and is active
		warehouse_doc = frappe.get_doc("Warehouse", warehouse)
		if warehouse_doc.disabled:
			frappe.throw(_("Warehouse {0} is disabled").format(warehouse))

		# Validate warehouse belongs to same company
		if warehouse_doc.company != profile_doc.company:
			frappe.throw(_(
				"Warehouse {0} belongs to {1}, but POS Profile belongs to {2}"
			).format(warehouse, warehouse_doc.company, profile_doc.company))

		# Update the POS Profile
		profile_doc.warehouse = warehouse
		profile_doc.save()

		return {
			"success": True,
			"message": _("Warehouse updated successfully"),
			"warehouse": warehouse
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Update Warehouse Error")
		frappe.throw(_("Error updating warehouse: {0}").format(str(e)))


@frappe.whitelist()
def get_sales_persons(pos_profile=None):
	"""Get all active individual sales persons (not groups) for POS"""
	try:
		filters = {
			"enabled": 1,
			"is_group": 0  # Only get individual sales persons, not group nodes
		}

		# If company is specified via POS Profile, filter by company (if Sales Person has company field)
		if pos_profile:
			company = frappe.db.get_value("POS Profile", pos_profile, "company")
			# Check if Sales Person doctype has a company field
			if frappe.db.has_column("Sales Person", "company") and company:
				filters["company"] = company

		sales_persons = frappe.get_list(
			"Sales Person",
			filters=filters,
			fields=["name", "sales_person_name", "commission_rate", "employee"],
			order_by="sales_person_name",
			limit_page_length=0
		)

		return sales_persons
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Sales Persons Error")
		return []

@frappe.whitelist()
def get_create_pos_profile(*args, **kwargs):
	"""
	Get selection data for creating POS Profile
	
	Returns:
		- warehouses: Available warehouses for user's company
		- customers: Available customers
		- currencies: Available currencies
		- payments: Available payment methods (Mode of Payment)
		- write_off_accounts: Available accounts for write-off
		- write_off_cost_centers: Available cost centers
		- applicable_for_users: Available users
		- posa_cash_mode_of_payment: Cash payment methods
		- item_groups: Available item groups
		- customer_groups: Available customer groups
	"""
	try:
		user_company = check_user_company()
		user_company = user_company.get("company")
		if not user_company:
			frappe.throw(_("User must have a company assigned"))

		warehouses = frappe.get_list(
			"Warehouse",
			filters={"disabled": 0, "is_group": 0, "company": user_company},
			fields=["name"],
			order_by="name"
		)
		customers = frappe.get_list(
			"Customer",
			filters={"disabled": 0},
		)
		
		currencies = frappe.get_list(
			"Currency",
			filters={"enabled": 1},
			fields=["name", "currency_name", "symbol"],
		)
		
		payments = frappe.get_list("Mode of Payment")
		
		posa_cash_mode_of_payment = payments
	
		write_off_accounts = frappe.get_list(
			"Account",
			filters={
				"report_type": "Profit and Loss",
				"disabled": 0,
				"is_group": 0,
				"company": user_company
			},
		)

		write_off_cost_centers = frappe.get_list(
			"Cost Center",
			filters={
				"is_group": 0,
				"disabled": 0,
				"company": user_company
			},
		)

		applicable_for_users = frappe.get_list(
			"User",
			filters={
				"enabled": 1,
			},
			fields=["name", "full_name"],
			order_by="full_name"
		)
		item_groups = frappe.get_list(
			"Item Group",
			filters={"is_group": 0},
		)
		
		customer_groups = frappe.get_list(
			"Customer Group",
			filters={"is_group": 0},
		)
		
		data = {
			"warehouses": warehouses,
			"customers": customers,
			"currencies": currencies,
			"payments": payments,
			"write_off_accounts": write_off_accounts,
			"write_off_cost_centers": write_off_cost_centers,
			"applicable_for_users": applicable_for_users,
			"posa_cash_mode_of_payment": posa_cash_mode_of_payment,
			"item_groups": item_groups,
			"customer_groups": customer_groups,
			"apply_discount_on_options": [
				{"value": "Grand Total", "label": "Grand Total"},
				{"value": "Net Total", "label": "Net Total"},
			]
		}
		return data
		
	except Exception as e:
		frappe.throw(_("Error getting create POS profile: {0}").format(str(e)))

@frappe.whitelist()
def create_pos_profile(*arg ,**parameters):
	"""
	Create a new POS Profile
	
	Required fields:
		- __newname: POS Profile name
		- currency: Currency code
		- warehouse: Warehouse name
		- payments: List of payment methods
		- write_off_account: Account name for write-off
		- write_off_cost_center: Cost center name
		- write_off_limit: Write-off limit amount
	
	Optional fields:
		- customer: Default customer
		- applicable_for_users: List of users
		- posa_cash_mode_of_payment: Cash payment method
		- item_groups: List of item groups (filters)
		- customer_groups: List of customer groups (filters)
		- apply_discount_on: Discount application method
	"""


		# Extract list parameters 
	payments = parameters.pop("payments", [])
	applicable_for_users = parameters.pop("applicable_for_users", [])
	item_groups = parameters.pop("item_groups", [])
	customer_groups = parameters.pop("customer_groups", [])
	
	# parse list parameters
	payments = _parse_list_parameter(payments, "payments")
	applicable_for_users = _parse_list_parameter(applicable_for_users, "applicable_for_users")
	item_groups = _parse_list_parameter(item_groups, "item_groups")
	customer_groups = _parse_list_parameter(customer_groups, "customer_groups")
	
	# Get user's company
	user_company_data = check_user_company()
	user_company = user_company_data.get("company")
	
	if not user_company:
		frappe.throw(_("User must have a company assigned"))

	pos_profile = frappe.new_doc("POS Profile")
	pos_profile.company = user_company

	pos_profile.update(parameters)

	# Child tables
	if not payments or len(payments) == 0:
		frappe.throw(_("At least one payment method is required"))
	
	for payment in payments:
		if isinstance(payment, dict):
			pos_profile.append("payments", {
				"mode_of_payment": payment.get("mode_of_payment"),
				"default": payment.get("default", 0),
				"allow_in_returns": payment.get("allow_in_returns", 0),
			})
		elif isinstance(payment, str) and payment != "":
			pos_profile.append("payments", {"mode_of_payment": payment})

	if isinstance(applicable_for_users, list) and len(applicable_for_users) > 0:
		for user in applicable_for_users:
			if isinstance(user, dict):
				pos_profile.append("applicable_for_users", {
					"user": user.get("user"),
					"default": user.get("default", 0),
				})
			elif isinstance(user, str) and user != "":
				pos_profile.append("applicable_for_users", {"user": user})

	if isinstance(item_groups, list) and len(item_groups) > 0:
		for item_group in item_groups:
			item_group_name = item_group if isinstance(item_group, str) else item_group.get("item_group")
			pos_profile.append("item_groups", {"item_group": item_group_name})

	if isinstance(customer_groups, list) and len(customer_groups) > 0:
		for customer_group in customer_groups:
			customer_group_name = customer_group if isinstance(customer_group, str) else customer_group.get("customer_group")
			pos_profile.append("customer_groups", {"customer_group": customer_group_name})

	pos_profile.insert()
	return pos_profile

@frappe.whitelist()		
def update_pos_profile(*args, **parameters):
	"""
		Update an existing POS Profile
		
		Args:
			pos_profile: POS Profile name
			parameters: Update parameters (all optional)
	"""
	# Extract child table parameters BEFORE prepare_query_parameters filters them
	payments = parameters.pop("payments", None)
	applicable_for_users = parameters.pop("applicable_for_users", None)
	item_groups = parameters.pop("item_groups", None)
	customer_groups = parameters.pop("customer_groups", None)
	pos_profile_name = parameters.pop("pos_profile_name", None)
	# parse list parameters
	payments = _parse_list_parameter(payments, "payments")
	applicable_for_users = _parse_list_parameter(applicable_for_users, "applicable_for_users")
	item_groups = _parse_list_parameter(item_groups, "item_groups")
	customer_groups = _parse_list_parameter(customer_groups, "customer_groups")
	
	pos_profile = frappe.get_doc("POS Profile", pos_profile_name)
	
	# Update main fields
	if parameters:
		pos_profile.update(parameters)

	if payments is not None:
		pos_profile.payments = []		
		for payment in payments:
			if isinstance(payment, dict):
				mode_of_payment = payment.get("mode_of_payment")
				if mode_of_payment:
					pos_profile.append("payments", {
						"mode_of_payment": mode_of_payment,
						"default": payment.get("default", 0),
						"allow_in_returns": payment.get("allow_in_returns", 0)
					})
			elif isinstance(payment, str) and payment:
				pos_profile.append("payments", {"mode_of_payment": payment})
					
	
	if applicable_for_users is not None:
		pos_profile.applicable_for_users = []
		for user in applicable_for_users:
			if isinstance(user, dict):
				user_name = user.get("user") or user.get("name")
				if user_name:			
					pos_profile.append("applicable_for_users", {
						"user": user_name,
						"default": user.get("default", 0)
					})
			elif isinstance(user, str):
				pos_profile.append("applicable_for_users", {"user": user, "default": 0})
	
	if item_groups is not None:
		pos_profile.item_groups = []
		for item_group in item_groups:
			item_group_name = item_group if isinstance(item_group, str) else item_group.get("item_group") or item_group.get("name")
			if item_group_name:
				pos_profile.append("item_groups", {"item_group": item_group_name})

	
	if customer_groups is not None:
		pos_profile.customer_groups = []
		for customer_group in customer_groups:
			customer_group_name = customer_group if isinstance(customer_group, str) else customer_group.get("customer_group") or customer_group.get("name")
			if customer_group_name:
				pos_profile.append("customer_groups", {"customer_group": customer_group_name})
		
	pos_profile.save()
	return pos_profile
	
@frappe.whitelist()
def delete_pos_profile(pos_profile):
	"""
		Delete a POS Profile
		
		Args:
			pos_profile: POS Profile name
	"""
	pos_profile = frappe.get_doc("POS Profile", pos_profile)
	pos_profile.delete()