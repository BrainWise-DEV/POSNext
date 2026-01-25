# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from pos_next.api.utilities import check_user_company
from pos_next.api.utilities import _parse_list_parameter


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
	from pos_next.api.constants import POS_SETTINGS_FIELDS, DEFAULT_POS_SETTINGS

	if not pos_profile:
		return DEFAULT_POS_SETTINGS.copy()

	try:
		# Get POS Settings linked to this POS Profile
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


@frappe.whitelist()
def get_payment_methods(pos_profile):
	"""Get available payment methods from POS Profile with optimized queries"""
	try:
		# Validate pos_profile parameter
		if not pos_profile:
			frappe.throw(_("POS Profile is required"))

		# Get company from POS Profile
		company = frappe.db.get_value("POS Profile", pos_profile, "company")

		from frappe.query_builder import DocType
		from frappe.query_builder.functions import Coalesce

		POSPaymentMethod = DocType("POS Payment Method")
		ModeOfPayment = DocType("Mode of Payment")
		ModeOfPaymentAccount = DocType("Mode of Payment Account")
		Account = DocType("Account")

		# Single query with JOINs to get payment methods with type and account info
		query = (
			frappe.qb.from_(POSPaymentMethod)
			.left_join(ModeOfPayment)
			.on(POSPaymentMethod.mode_of_payment == ModeOfPayment.name)
			.left_join(ModeOfPaymentAccount)
			.on(
				(ModeOfPaymentAccount.parent == ModeOfPayment.name) &
				(ModeOfPaymentAccount.company == company)
			)
			.left_join(Account)
			.on(Account.name == ModeOfPaymentAccount.default_account)
			.select(
				POSPaymentMethod.mode_of_payment,
				POSPaymentMethod.default,
				POSPaymentMethod.allow_in_returns,
				Coalesce(ModeOfPayment.type, "Cash").as_("type"),
				Coalesce(Account.account_type, "").as_("account_type")
			)
			.where(POSPaymentMethod.parent == pos_profile)
			.orderby(POSPaymentMethod.idx)
		)

		payment_methods = query.run(as_dict=True)
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
def get_wallet_payment_flags(methods):
	"""
	Get is_wallet_payment flags for multiple payment methods in a single query.

	Args:
		methods: List of mode_of_payment names (can be JSON string or list)

	Returns:
		Dict mapping mode_of_payment name to is_wallet_payment flag
	"""
	import json

	if not methods:
		return {}

	# Parse JSON string if needed
	if isinstance(methods, str):
		try:
			methods = json.loads(methods)
		except json.JSONDecodeError:
			return {}

	if not isinstance(methods, list) or len(methods) == 0:
		return {}

	from frappe.query_builder import DocType

	ModeOfPayment = DocType("Mode of Payment")

	query = (
		frappe.qb.from_(ModeOfPayment)
		.select(
			ModeOfPayment.name,
			ModeOfPayment.is_wallet_payment
		)
		.where(ModeOfPayment.name.isin(methods))
	)

	results = query.run(as_dict=True)

	# Return as dict for easy lookup
	return {r["name"]: r["is_wallet_payment"] or 0 for r in results}


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