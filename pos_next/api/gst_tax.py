# -*- coding: utf-8 -*-
# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

"""
GST Tax Utilities for POS Next
Handles place of supply determination, inter-state detection, and tax template selection
Similar to India Compliance's GST handling but integrated into POS Next
"""

from __future__ import unicode_literals
import frappe
from frappe import _


def get_place_of_supply(customer, company, shipping_address=None):
	"""
	Determine Place of Supply for a sales transaction.
	
	Logic:
	1. For registered customers: Use GSTIN state code (first 2 digits)
	2. For unregistered customers: Use customer address state
	3. Format: "27-Maharashtra" (state_code-state_name)
	
	Args:
		customer: Customer name
		company: Company name
		shipping_address: Optional shipping address name
		
	Returns:
		str: Place of supply in format "XX-State Name" or None
	"""
	try:
		if not customer or not company:
			return None
		
		# Get customer details using db.get_value to avoid document locks
		customer_data = frappe.db.get_value(
			"Customer",
			customer,
			["gstin", "gst_category"],
			as_dict=True
		)
		
		if not customer_data:
			return None
		
		customer_gstin = customer_data.get("gstin")
		customer_gst_category = customer_data.get("gst_category") or "Unregistered"
		
		# Handle overseas customers
		if customer_gst_category == "Overseas":
			return get_overseas_place_of_supply(shipping_address)
		
		# Get customer address (billing or shipping)
		customer_address = None
		if shipping_address:
			customer_address = shipping_address
		else:
			# Get default billing address - use optimized SQL to avoid locks
			try:
				customer_address = frappe.db.sql("""
					SELECT a.name 
					FROM `tabAddress` a
					INNER JOIN `tabDynamic Link` dl ON dl.parent = a.name
					WHERE dl.link_doctype = 'Customer'
					AND dl.link_name = %s
					AND dl.parenttype = 'Address'
					AND a.is_primary_address = 1
					LIMIT 1
				""", (customer,), as_dict=True)
				customer_address = customer_address[0].name if customer_address else None
			except Exception:
				# If query fails, continue without address
				customer_address = None
		
		# For registered customers with GSTIN: Use GSTIN state code
		if customer_gstin and len(customer_gstin) >= 2:
			state_code = customer_gstin[:2]
			state_name = get_state_name(state_code)
			if state_name:
				return f"{state_code}-{state_name}"
		
		# For unregistered customers or when GSTIN is missing: Use address state
		if customer_address:
			try:
				address_data = frappe.db.get_value(
					"Address",
					customer_address,
					["gst_state_number", "gst_state"],
					as_dict=True
				)
				
				if address_data:
					gst_state_number = address_data.get("gst_state_number")
					gst_state = address_data.get("gst_state")
					
					if gst_state_number and gst_state:
						return f"{gst_state_number}-{gst_state}"
			except Exception:
				# If address lookup fails, continue to fallback
				pass
		
		# Fallback: Use company GSTIN state
		company_gstin = frappe.db.get_value("Company", company, "gstin")
		if company_gstin and len(company_gstin) >= 2:
			state_code = company_gstin[:2]
			state_name = get_state_name(state_code)
			if state_name:
				return f"{state_code}-{state_name}"
		
		return None
	except Exception as e:
		# Log error but don't break invoice creation
		frappe.log_error(f"Error in get_place_of_supply: {str(e)}", "GST Tax Error")
		return None


def get_overseas_place_of_supply(shipping_address):
	"""
	Determine place of supply for overseas customers.
	
	If shipping address is in India, use that state.
	Otherwise, use "96-Other Countries"
	"""
	if not shipping_address:
		return "96-Other Countries"
	
	address_data = frappe.db.get_value(
		"Address",
		shipping_address,
		["country", "gst_state_number", "gst_state"],
		as_dict=True
	)
	
	if not address_data:
		return "96-Other Countries"
	
	country = address_data.get("country")
	gst_state_number = address_data.get("gst_state_number")
	gst_state = address_data.get("gst_state")
	
	if country == "India" and gst_state_number and gst_state:
		return f"{gst_state_number}-{gst_state}"
	
	return "96-Other Countries"


def get_source_state_code(company):
	"""
	Get the state code of the company (source state).
	
	Args:
		company: Company name
		
	Returns:
		str: State code (first 2 digits of company GSTIN) or None
	"""
	company_gstin = frappe.db.get_value("Company", company, "gstin")
	if company_gstin and len(company_gstin) >= 2:
		return company_gstin[:2]
	return None


def is_inter_state_supply(customer, company, shipping_address=None):
	"""
	Determine if the supply is inter-state or intra-state.
	
	Inter-state: Place of supply state != Company state
	Intra-state: Place of supply state == Company state
	
	Args:
		customer: Customer name
		company: Company name
		shipping_address: Optional shipping address name
		
	Returns:
		bool: True if inter-state, False if intra-state
	"""
	try:
		if not customer or not company:
			return False
		
		# Get customer GST category using db.get_value to avoid locks
		customer_gst_category = frappe.db.get_value("Customer", customer, "gst_category") or "Unregistered"
		
		# SEZ is always inter-state
		if customer_gst_category == "SEZ":
			return True
		
		# Get place of supply
		place_of_supply = get_place_of_supply(customer, company, shipping_address)
		if not place_of_supply:
			return False
		
		# Get company state code
		company_state_code = get_source_state_code(company)
		if not company_state_code:
			return False
		
		# Extract state code from place of supply (format: "27-Maharashtra")
		pos_state_code = place_of_supply[:2] if len(place_of_supply) >= 2 else None
		
		# Compare state codes
		return pos_state_code != company_state_code
	except Exception as e:
		# Log error but return False (intra-state) as safe default
		frappe.log_error(f"Error in is_inter_state_supply: {str(e)}", "GST Tax Error")
		return False


def get_gst_tax_template(company, customer=None, shipping_address=None, is_inter_state=None):
	"""
	Get the appropriate GST tax template based on inter-state/intra-state.
	
	This function:
	1. First tries to use Tax Category (if India Compliance is installed)
	2. Falls back to template name patterns
	
	Args:
		company: Company name
		customer: Customer name (optional)
		shipping_address: Shipping address name (optional)
		is_inter_state: Boolean (optional) - if not provided, will be calculated
		
	Returns:
		str: Tax template name or None
	"""
	try:
		if not company:
			return None
		
		# Determine inter-state if not provided
		if is_inter_state is None and customer:
			is_inter_state = is_inter_state_supply(customer, company, shipping_address)
		elif is_inter_state is None:
			is_inter_state = False
		
		# Try to use Tax Category (India Compliance integration)
		tax_template = get_tax_template_from_category(company, is_inter_state)
		if tax_template:
			return tax_template
		
		# Fallback to template name patterns
		return get_tax_template_by_pattern(company, is_inter_state)
	except Exception as e:
		# Log error but return None to allow invoice creation to continue
		frappe.log_error(f"Error in get_gst_tax_template: {str(e)}", "GST Tax Error")
		return None


def get_tax_template_from_category(company, is_inter_state):
	"""
	Get tax template using Tax Category (India Compliance integration).
	
	Args:
		company: Company name
		is_inter_state: Boolean
		
	Returns:
		str: Tax template name or None
	"""
	# Check if Tax Category doctype exists (India Compliance)
	if not frappe.db.exists("DocType", "Tax Category"):
		return None
	
	try:
		# Find Tax Category with matching is_inter_state flag
		tax_categories = frappe.get_all(
			"Tax Category",
			fields=["name"],
			filters={
				"is_inter_state": 1 if is_inter_state else 0,
				"disabled": 0,
			},
			limit=1
		)
		
		if not tax_categories:
			return None
		
		tax_category = tax_categories[0].name
		
		# Find Sales Taxes and Charges Template linked to this Tax Category
		# Exclude RCM templates - they should only be used when is_reverse_charge = 1
		tax_template = frappe.db.get_value(
			"Sales Taxes and Charges Template",
			{
				"company": company,
				"tax_category": tax_category,
				"disabled": 0,
			},
			"name",
			order_by="name"
		)
		
		# If template name contains "RCM", try to find a non-RCM alternative
		if tax_template and "RCM" in tax_template.upper():
			# Try to find a non-RCM template with same tax category
			non_rcm_template = frappe.db.get_value(
				"Sales Taxes and Charges Template",
				{
					"company": company,
					"tax_category": tax_category,
					"disabled": 0,
					"name": ["not like", "%RCM%"]
				},
				"name",
				order_by="name"
			)
			if non_rcm_template:
				return non_rcm_template
			# If no non-RCM template found, return None (will fall back to pattern matching)
			return None
		
		return tax_template
	except Exception:
		# Tax Category might not be configured properly
		return None


def get_tax_template_by_pattern(company, is_inter_state):
	"""
	Get tax template by searching for name patterns.
	
	Args:
		company: Company name
		is_inter_state: Boolean
		
	Returns:
		str: Tax template name or None
	"""
	if is_inter_state:
		# Look for inter-state templates (IGST)
		patterns = [
			'Output GST Out-state%',
			'%Out-state%',
			'%Out State%',
			'%IGST%',
			'%Inter-state%',
			'%Inter State%',
		]
	else:
		# Look for intra-state templates (CGST+SGST)
		patterns = [
			'Output GST In-state%',
			'%In-state%',
			'%In State%',
			'%Intra-state%',
			'%Intra State%',
		]
	
	for pattern in patterns:
		template = frappe.db.sql("""
			SELECT name FROM `tabSales Taxes and Charges Template`
			WHERE company = %s
			AND disabled = 0
			AND name LIKE %s
			AND name NOT LIKE '%%RCM%%'
			LIMIT 1
		""", (company, pattern), as_dict=True)
		
		if template:
			return template[0].name
	
	# Fallback: any active non-RCM template
	fallback = frappe.db.sql("""
		SELECT name FROM `tabSales Taxes and Charges Template`
		WHERE company = %s
		AND disabled = 0
		AND name NOT LIKE '%%RCM%%'
		LIMIT 1
	""", (company,), as_dict=True)
	
	return fallback[0].name if fallback else None


def get_state_name(state_code):
	"""
	Get state name from state code.
	
	Uses India Compliance's STATE_NUMBERS if available, otherwise returns None.
	
	Args:
		state_code: State code (2-digit string)
		
	Returns:
		str: State name or None
	"""
	try:
		# Try to use India Compliance's STATE_NUMBERS
		from india_compliance.gst_india.constants import STATE_NUMBERS
		# Reverse lookup: find state name by code
		for state_name, code in STATE_NUMBERS.items():
			if str(code) == str(state_code):
				return state_name
	except ImportError:
		# India Compliance not installed, try to get from Address
		state = frappe.db.get_value(
			"Address",
			{"gst_state_number": state_code},
			"gst_state",
			limit=1
		)
		if state:
			return state
	
	return None


@frappe.whitelist()
def get_gst_details(customer, company, shipping_address=None):
	"""
	Get comprehensive GST details for a customer-company combination.
	
	This is the main API endpoint that returns:
	- place_of_supply
	- is_inter_state
	- tax_template
	- company_state_code
	- customer_state_code
	
	Args:
		customer: Customer name
		company: Company name
		shipping_address: Optional shipping address name
		
	Returns:
		dict: GST details
	"""
	if not customer or not company:
		return {
			"place_of_supply": None,
			"is_inter_state": False,
			"tax_template": None,
			"company_state_code": None,
			"customer_state_code": None,
		}
	
	# Get place of supply
	place_of_supply = get_place_of_supply(customer, company, shipping_address)
	
	# Get company state code
	company_state_code = get_source_state_code(company)
	
	# Get customer state code
	customer_state_code = None
	customer_gstin = frappe.db.get_value("Customer", customer, "gstin")
	if customer_gstin and len(customer_gstin) >= 2:
		customer_state_code = customer_gstin[:2]
	else:
		# Try to get from address - use optimized SQL to avoid locks
		try:
			customer_address = frappe.db.sql("""
				SELECT a.name 
				FROM `tabAddress` a
				INNER JOIN `tabDynamic Link` dl ON dl.parent = a.name
				WHERE dl.link_doctype = 'Customer'
				AND dl.link_name = %s
				AND dl.parenttype = 'Address'
				AND a.is_primary_address = 1
				LIMIT 1
			""", (customer,), as_dict=True)
			
			if customer_address:
				customer_state_code = frappe.db.get_value(
					"Address",
					customer_address[0].name,
					"gst_state_number"
				)
		except Exception:
			# If query fails, customer_state_code remains None
			pass
	
	# Determine inter-state
	is_inter_state = is_inter_state_supply(customer, company, shipping_address)
	
	# Get tax template
	tax_template = get_gst_tax_template(company, customer, shipping_address, is_inter_state)
	
	return {
		"place_of_supply": place_of_supply,
		"is_inter_state": is_inter_state,
		"tax_template": tax_template,
		"company_state_code": company_state_code,
		"customer_state_code": customer_state_code,
	}
