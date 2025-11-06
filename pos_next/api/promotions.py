# -*- coding: utf-8 -*-
# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, cstr, cint
import re


def check_promotion_permissions(action="read"):
	"""
	Check if user has permissions for promotional scheme operations.

	Args:
		action: Type of action - "read", "write", "delete"

	Raises:
		frappe.PermissionError: If user doesn't have required permissions
	"""
	# Check if user has required permissions for Promotional Scheme doctype
	if action == "read":
		if not frappe.has_permission("Promotional Scheme", "read"):
			frappe.throw(_("You don't have permission to view promotions"), frappe.PermissionError)
	elif action == "write":
		if not frappe.has_permission("Promotional Scheme", "write"):
			frappe.throw(_("You don't have permission to create or modify promotions"), frappe.PermissionError)
	elif action == "delete":
		if not frappe.has_permission("Promotional Scheme", "delete"):
			frappe.throw(_("You don't have permission to delete promotions"), frappe.PermissionError)


@frappe.whitelist()
def get_promotions(pos_profile=None, company=None, include_disabled=False):
	"""Get all promotional schemes AND standalone pricing rules for POS with simplified structure."""
	check_promotion_permissions("read")

	filters = {}

	if company:
		filters["company"] = company
	elif pos_profile:
		profile = frappe.get_doc("POS Profile", pos_profile)
		filters["company"] = profile.company

	if not include_disabled:
		filters["disable"] = 0

	# Get all promotional schemes
	schemes = frappe.get_all(
		"Promotional Scheme",
		filters=filters,
		fields=[
			"name", "apply_on", "disable", "selling", "buying",
			"applicable_for", "valid_from", "valid_upto", "company",
			"mixed_conditions", "is_cumulative"
		],
		order_by="modified desc"
	)

	# Enrich with pricing rules count and details
	today = getdate(nowdate())

	for scheme in schemes:
		# Mark as Promotional Scheme
		scheme["source"] = "Promotional Scheme"

		# Get pricing rules count
		scheme["pricing_rules_count"] = frappe.db.count(
			"Pricing Rule",
			{"promotional_scheme": scheme.name}
		)

		# Get discount slabs
		scheme_doc = frappe.get_doc("Promotional Scheme", scheme.name)
		scheme["price_slabs"] = len(scheme_doc.price_discount_slabs or [])
		scheme["product_slabs"] = len(scheme_doc.product_discount_slabs or [])

		# Get items/groups/brands count
		if scheme.apply_on == "Item Code":
			scheme["items_count"] = len(scheme_doc.items or [])
		elif scheme.apply_on == "Item Group":
			scheme["items_count"] = len(scheme_doc.item_groups or [])
		elif scheme.apply_on == "Brand":
			scheme["items_count"] = len(scheme_doc.brands or [])
		else:
			scheme["items_count"] = 0

		# Calculate status based on dates and disable flag
		if scheme.disable:
			scheme["status"] = "Disabled"
		elif scheme.valid_from and getdate(scheme.valid_from) > today:
			scheme["status"] = "Not Started"
		elif scheme.valid_upto and getdate(scheme.valid_upto) < today:
			scheme["status"] = "Expired"
		else:
			scheme["status"] = "Active"

	# Get standalone pricing rules (not associated with promotional schemes)
	pr_filters = filters.copy()
	pr_filters["promotional_scheme"] = ["is", "not set"]

	pricing_rules = frappe.get_all(
		"Pricing Rule",
		filters=pr_filters,
		fields=[
			"name", "title", "apply_on", "disable", "selling", "buying",
			"applicable_for", "valid_from", "valid_upto", "company",
			"rate_or_discount", "discount_percentage", "discount_amount",
			"min_qty", "max_qty", "min_amt", "max_amt", "priority"
		],
		order_by="modified desc"
	)

	# Transform pricing rules to match promotional scheme structure
	for pr in pricing_rules:
		# Mark as Pricing Rule
		pr["source"] = "Pricing Rule"
		pr["pricing_rules_count"] = 1  # Itself
		pr["price_slabs"] = 1
		pr["product_slabs"] = 0

		# Get items/groups/brands count
		pr_doc = frappe.get_doc("Pricing Rule", pr.name)
		if pr.apply_on == "Item Code":
			pr["items_count"] = len(pr_doc.items or [])
		elif pr.apply_on == "Item Group":
			pr["items_count"] = len(pr_doc.item_groups or [])
		elif pr.apply_on == "Brand":
			pr["items_count"] = len(pr_doc.brands or [])
		else:
			pr["items_count"] = 0

		# Calculate status
		if pr.disable:
			pr["status"] = "Disabled"
		elif pr.valid_from and getdate(pr.valid_from) > today:
			pr["status"] = "Not Started"
		elif pr.valid_upto and getdate(pr.valid_upto) < today:
			pr["status"] = "Expired"
		else:
			pr["status"] = "Active"

	# Combine both lists
	all_promotions = schemes + pricing_rules

	return all_promotions


@frappe.whitelist()
def get_promotion_details(scheme_name):
	"""Get detailed information about a promotional scheme OR standalone pricing rule."""
	check_promotion_permissions("read")

	# Check if it's a Promotional Scheme
	if frappe.db.exists("Promotional Scheme", scheme_name):
		scheme = frappe.get_doc("Promotional Scheme", scheme_name)
		data = scheme.as_dict()
		data["source"] = "Promotional Scheme"

		# Get active pricing rules
		data["pricing_rules"] = frappe.get_all(
			"Pricing Rule",
			filters={"promotional_scheme": scheme_name, "disable": 0},
			fields=["name", "title", "priority", "valid_from", "valid_upto"]
		)

		return data

	# Check if it's a standalone Pricing Rule
	elif frappe.db.exists("Pricing Rule", scheme_name):
		pr = frappe.get_doc("Pricing Rule", scheme_name)
		data = pr.as_dict()
		data["source"] = "Pricing Rule"

		# Transform pricing rule to match promotional scheme structure for frontend
		# Map pricing rule fields to promotional scheme fields
		data["items_count"] = len(pr.items or []) + len(pr.item_groups or []) + len(pr.brands or [])

		# Create a synthetic price discount slab from pricing rule fields
		if pr.rate_or_discount in ["Discount Percentage", "Discount Amount"]:
			data["price_discount_slabs"] = [{
				"min_qty": pr.min_qty or 0,
				"max_qty": pr.max_qty or 0,
				"min_amount": pr.min_amt or 0,
				"max_amount": pr.max_amt or 0,
				"discount_percentage": pr.discount_percentage if pr.rate_or_discount == "Discount Percentage" else 0,
				"discount_amount": pr.discount_amount if pr.rate_or_discount == "Discount Amount" else 0,
				"rate_or_discount": pr.rate_or_discount
			}]
		else:
			data["price_discount_slabs"] = []

		data["product_discount_slabs"] = []

		return data

	else:
		frappe.throw(_("Promotion or Pricing Rule {0} not found").format(scheme_name))


@frappe.whitelist()
def create_promotion(data):
	"""
	Create a promotional scheme.

	Simplified input format:
	{
		"name": "Summer Sale 2025",
		"company": "Company Name",
		"apply_on": "Item Group",  # Item Code, Item Group, Brand, Transaction
		"items": [{"item_code": "ITEM-001"}] or [{"item_group": "Electronics"}] or [{"brand": "Apple"}],
		"discount_type": "percentage",  # percentage, amount, or free_item
		"discount_value": 10,  # percentage value or amount
		"free_item": "ITEM-FREE",  # if discount_type is free_item
		"free_qty": 1,  # if discount_type is free_item
		"min_qty": 5,
		"min_amt": 1000,
		"valid_from": "2025-01-01",
		"valid_upto": "2025-12-31",
		"applicable_for": "Customer Group",  # optional
		"customer_group": "Retail"  # if applicable_for is set
	}
	"""
	check_promotion_permissions("write")

	import json
	if isinstance(data, str):
		data = json.loads(data)

	# Validate required fields
	if not data.get("name"):
		frappe.throw(_("Promotion name is required"))
	if not data.get("company"):
		frappe.throw(_("Company is required"))
	if not data.get("apply_on"):
		frappe.throw(_("Apply On is required"))

	try:
		# Create promotional scheme
		scheme = frappe.new_doc("Promotional Scheme")
		scheme.update({
			"name": data.get("name"),
			"company": data.get("company"),
			"apply_on": data.get("apply_on"),
			"selling": 1,  # Always enable selling for POS
			"buying": 0,
			"valid_from": data.get("valid_from") or nowdate(),
			"valid_upto": data.get("valid_upto"),
			"mixed_conditions": cint(data.get("mixed_conditions", 0)),
			"is_cumulative": cint(data.get("is_cumulative", 0)),
		})

		# Set applicable for
		if data.get("applicable_for"):
			scheme.applicable_for = data["applicable_for"]
			applicable_key = frappe.scrub(data["applicable_for"])
			if data.get(applicable_key):
				# Handle both single value and list
				values = data[applicable_key] if isinstance(data[applicable_key], list) else [data[applicable_key]]
				for value in values:
					scheme.append(applicable_key, {applicable_key: value})

		# Add items/groups/brands based on apply_on
		apply_on_key = frappe.scrub(data["apply_on"])
		items_data = data.get("items", [])

		if data["apply_on"] == "Item Code" and items_data:
			for item in items_data:
				scheme.append("items", {
					"item_code": item.get("item_code"),
					"uom": item.get("uom")
				})
		elif data["apply_on"] == "Item Group" and items_data:
			for item in items_data:
				scheme.append("item_groups", {
					"item_group": item.get("item_group"),
					"uom": item.get("uom")
				})
		elif data["apply_on"] == "Brand" and items_data:
			for item in items_data:
				scheme.append("brands", {
					"brand": item.get("brand"),
					"uom": item.get("uom")
				})

		# Add discount slab
		discount_type = data.get("discount_type", "percentage")

		if discount_type in ["percentage", "amount"]:
			# Price discount
			slab = scheme.append("price_discount_slabs", {})
			slab.rule_description = data.get("rule_description") or _("Discount Rule")
			slab.min_qty = flt(data.get("min_qty", 0))
			slab.max_qty = flt(data.get("max_qty", 0))
			slab.min_amount = flt(data.get("min_amt", 0))
			slab.max_amount = flt(data.get("max_amt", 0))

			if discount_type == "percentage":
				slab.rate_or_discount = "Discount Percentage"
				slab.discount_percentage = flt(data.get("discount_value", 0))
			else:
				slab.rate_or_discount = "Discount Amount"
				slab.discount_amount = flt(data.get("discount_value", 0))

			if data.get("priority"):
				slab.priority = cstr(data["priority"])

		elif discount_type == "free_item":
			# Product discount
			slab = scheme.append("product_discount_slabs", {})
			slab.rule_description = data.get("rule_description") or _("Free Item Rule")
			slab.min_qty = flt(data.get("min_qty", 0))
			slab.max_qty = flt(data.get("max_qty", 0))
			slab.min_amount = flt(data.get("min_amt", 0))
			slab.max_amount = flt(data.get("max_amt", 0))
			slab.free_item = data.get("free_item")
			slab.free_qty = flt(data.get("free_qty", 1))
			slab.free_item_uom = data.get("free_item_uom")
			slab.same_item = cint(data.get("same_item", 0))

			if data.get("priority"):
				slab.priority = cstr(data["priority"])

		# Save the scheme (this will auto-generate pricing rules)
		scheme.insert()

		return {
			"success": True,
			"message": _("Promotion {0} created successfully").format(scheme.name),
			"scheme_name": scheme.name
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Promotion Creation Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to create promotion: {0}").format(str(e)))


@frappe.whitelist()
def update_promotion(scheme_name, data):
	"""
	Update an existing promotional scheme.
	Supports updating validity dates, discount values, and slab conditions.
	"""
	check_promotion_permissions("write")

	import json
	if isinstance(data, str):
		data = json.loads(data)

	if not frappe.db.exists("Promotional Scheme", scheme_name):
		frappe.throw(_("Promotional Scheme {0} not found").format(scheme_name))

	try:
		scheme = frappe.get_doc("Promotional Scheme", scheme_name)

		# Update basic fields
		if "valid_from" in data:
			scheme.valid_from = data["valid_from"]
		if "valid_upto" in data:
			scheme.valid_upto = data["valid_upto"]
		if "disable" in data:
			scheme.disable = cint(data["disable"])

		# Update discount values in slabs
		if "discount_value" in data or "min_qty" in data or "max_qty" in data or "min_amt" in data or "max_amt" in data:
			# Update price discount slabs
			if scheme.price_discount_slabs and len(scheme.price_discount_slabs) > 0:
				slab = scheme.price_discount_slabs[0]
				if "min_qty" in data:
					slab.min_qty = flt(data["min_qty"])
				if "max_qty" in data:
					slab.max_qty = flt(data["max_qty"])
				if "min_amt" in data:
					slab.min_amount = flt(data["min_amt"])
				if "max_amt" in data:
					slab.max_amount = flt(data["max_amt"])
				if "discount_value" in data:
					if slab.rate_or_discount == "Discount Percentage":
						slab.discount_percentage = flt(data["discount_value"])
					elif slab.rate_or_discount == "Discount Amount":
						slab.discount_amount = flt(data["discount_value"])

		# Update free item slabs
		if "free_item" in data or "free_qty" in data or "min_qty" in data or "max_qty" in data or "min_amt" in data or "max_amt" in data:
			if scheme.product_discount_slabs and len(scheme.product_discount_slabs) > 0:
				slab = scheme.product_discount_slabs[0]
				if "free_item" in data:
					slab.free_item = data["free_item"]
				if "free_qty" in data:
					slab.free_qty = flt(data["free_qty"])
				if "min_qty" in data:
					slab.min_qty = flt(data["min_qty"])
				if "max_qty" in data:
					slab.max_qty = flt(data["max_qty"])
				if "min_amt" in data:
					slab.min_amount = flt(data["min_amt"])
				if "max_amt" in data:
					slab.max_amount = flt(data["max_amt"])

		# Save
		scheme.save()

		return {
			"success": True,
			"message": _("Promotion {0} updated successfully").format(scheme_name)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Promotion Update Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to update promotion: {0}").format(str(e)))


@frappe.whitelist()
def toggle_promotion(scheme_name, disable=None):
	"""Enable or disable a promotional scheme."""
	check_promotion_permissions("write")

	if not frappe.db.exists("Promotional Scheme", scheme_name):
		frappe.throw(_("Promotional Scheme {0} not found").format(scheme_name))

	try:
		scheme = frappe.get_doc("Promotional Scheme", scheme_name)

		if disable is not None:
			scheme.disable = cint(disable)
		else:
			scheme.disable = 0 if scheme.disable else 1

		scheme.save()

		status = "disabled" if scheme.disable else "enabled"
		return {
			"success": True,
			"message": _("Promotion {0} {1}").format(scheme_name, status),
			"disabled": scheme.disable
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Promotion Toggle Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to toggle promotion: {0}").format(str(e)))


@frappe.whitelist()
def delete_promotion(scheme_name):
	"""Delete a promotional scheme and its pricing rules."""
	check_promotion_permissions("delete")

	if not frappe.db.exists("Promotional Scheme", scheme_name):
		frappe.throw(_("Promotional Scheme {0} not found").format(scheme_name))

	try:
		# This will automatically delete associated pricing rules via on_trash
		frappe.delete_doc("Promotional Scheme", scheme_name)

		return {
			"success": True,
			"message": _("Promotion {0} deleted successfully").format(scheme_name)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Promotion Deletion Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to delete promotion: {0}").format(str(e)))


@frappe.whitelist()
def get_item_groups(company=None):
	"""Get all item groups."""
	# Item Group is a global doctype, not company-specific
	# Return all item groups (both parent groups and leaf nodes)
	return frappe.get_all(
		"Item Group",
		fields=["name", "parent_item_group", "is_group"],
		order_by="name"
	)


@frappe.whitelist()
def get_brands():
	"""Get all brands."""
	return frappe.get_all(
		"Brand",
		fields=["name"],
		order_by="name"
	)


@frappe.whitelist()
def search_items(search_term, pos_profile=None, limit=20):
	"""Search for items."""
	# Rate limiting: Track API calls per user
	cache_key = f"search_items_rate_limit:{frappe.session.user}"
	call_count_raw = frappe.cache().get(cache_key)
	call_count = int(call_count_raw) if call_count_raw else 0

	if call_count > 50:  # Max 50 searches per minute
		frappe.throw(_("Too many search requests. Please wait a moment."))

	frappe.cache().setex(cache_key, 60, call_count + 1)

	# Sanitize search term to prevent SQL injection
	if not search_term or not isinstance(search_term, str):
		return []

	# Remove any special SQL characters and limit length
	search_term = re.sub(r'[^\w\s-]', '', search_term)[:100]

	if len(search_term) < 2:
		return []

	filters = {"disabled": 0}

	if pos_profile:
		profile = frappe.get_doc("POS Profile", pos_profile)
		if profile.item_groups:
			item_groups = [d.item_group for d in profile.item_groups]
			filters["item_group"] = ["in", item_groups]

	# Limit results
	limit = min(int(limit) if limit else 20, 50)  # Max 50 results

	return frappe.get_all(
		"Item",
		filters=filters,
		or_filters={
			"item_code": ["like", f"%{search_term}%"],
			"item_name": ["like", f"%{search_term}%"]
		},
		fields=["item_code", "item_name", "item_group", "brand", "stock_uom"],
		limit=limit,
		order_by="item_name"
	)


# ==================== COUPON MANAGEMENT ====================

@frappe.whitelist()
def get_coupons(company=None, include_disabled=False, coupon_type=None):
	"""Get all coupons for the company with enhanced filtering."""
	check_promotion_permissions("read")

	filters = {}

	if company:
		filters["company"] = company

	# Check if disabled field exists before filtering
	has_disabled_field = frappe.db.has_column("POS Coupon", "disabled")

	if not include_disabled and has_disabled_field:
		filters["disabled"] = 0

	if coupon_type:
		filters["coupon_type"] = coupon_type

	# Build field list - only include fields that exist
	fields = [
		"name", "coupon_name", "coupon_code", "coupon_type",
		"customer", "customer_name",
		"valid_from", "valid_upto", "maximum_use", "used",
		"one_use", "company", "campaign"
	]

	# Check for optional fields
	if has_disabled_field:
		fields.append("disabled")

	coupons = frappe.get_all(
		"POS Coupon",
		filters=filters,
		fields=fields,
		order_by="modified desc"
	)

	# Enrich with status
	today = getdate(nowdate())

	for coupon in coupons:
		# Set disabled to 0 if field doesn't exist
		if not has_disabled_field:
			coupon["disabled"] = 0

		# Calculate status - disabled takes precedence
		if coupon.get("disabled"):
			coupon["status"] = "Disabled"
		elif coupon.valid_from and getdate(coupon.valid_from) > today:
			coupon["status"] = "Not Started"
		elif coupon.valid_upto and getdate(coupon.valid_upto) < today:
			coupon["status"] = "Expired"
		elif coupon.maximum_use and coupon.used >= coupon.maximum_use:
			coupon["status"] = "Exhausted"
		else:
			coupon["status"] = "Active"

		# Add usage percentage
		if coupon.maximum_use:
			coupon["usage_percent"] = (coupon.used / coupon.maximum_use) * 100
		else:
			coupon["usage_percent"] = 0

	return coupons


@frappe.whitelist()
def get_coupon_details(coupon_name):
	"""Get detailed information about a specific coupon."""
	check_promotion_permissions("read")

	if not frappe.db.exists("POS Coupon", coupon_name):
		frappe.throw(_("Coupon {0} not found").format(coupon_name))

	coupon = frappe.get_doc("POS Coupon", coupon_name)
	data = coupon.as_dict()

	return data


@frappe.whitelist()
def create_coupon(data):
	"""
	Create a new coupon.

	Input format:
	{
		"coupon_name": "Summer Sale Coupon",
		"coupon_type": "Promotional",  # Promotional or Gift Card
		"coupon_code": "SAVE20",  # Optional, auto-generated if not provided
		"discount_type": "Percentage",  # Percentage or Amount
		"discount_percentage": 20,  # Required if discount_type is Percentage
		"discount_amount": 100,  # Required if discount_type is Amount
		"min_amount": 500,  # Optional - Minimum cart amount
		"max_amount": 200,  # Optional - Maximum discount cap
		"apply_on": "Grand Total",  # Grand Total or Net Total
		"company": "Company Name",
		"customer": "CUST-001",  # Required for Gift Card
		"valid_from": "2025-01-01",
		"valid_upto": "2025-12-31",
		"maximum_use": 100,  # Optional
		"one_use": 0,  # 0 or 1
		"campaign": "Campaign Name"  # Optional
	}
	"""
	check_promotion_permissions("write")

	import json
	if isinstance(data, str):
		data = json.loads(data)

	# Validate required fields
	if not data.get("coupon_name"):
		frappe.throw(_("Coupon name is required"))
	if not data.get("coupon_type"):
		frappe.throw(_("Coupon type is required"))
	if not data.get("discount_type"):
		frappe.throw(_("Discount type is required"))
	if not data.get("company"):
		frappe.throw(_("Company is required"))

	# Validate discount configuration
	if data.get("discount_type") == "Percentage":
		if not data.get("discount_percentage"):
			frappe.throw(_("Discount percentage is required when discount type is Percentage"))
		if flt(data.get("discount_percentage")) <= 0 or flt(data.get("discount_percentage")) > 100:
			frappe.throw(_("Discount percentage must be between 0 and 100"))
	elif data.get("discount_type") == "Amount":
		if not data.get("discount_amount"):
			frappe.throw(_("Discount amount is required when discount type is Amount"))
		if flt(data.get("discount_amount")) <= 0:
			frappe.throw(_("Discount amount must be greater than 0"))

	# Validate Gift Card requires customer
	if data.get("coupon_type") == "Gift Card" and not data.get("customer"):
		frappe.throw(_("Customer is required for Gift Card coupons"))

	try:
		# Create coupon
		coupon = frappe.new_doc("POS Coupon")
		coupon.update({
			"coupon_name": data.get("coupon_name"),
			"coupon_type": data.get("coupon_type"),
			"coupon_code": data.get("coupon_code"),  # Will auto-generate if empty
			"discount_type": data.get("discount_type"),
			"discount_percentage": flt(data.get("discount_percentage")) if data.get("discount_type") == "Percentage" else None,
			"discount_amount": flt(data.get("discount_amount")) if data.get("discount_type") == "Amount" else None,
			"min_amount": flt(data.get("min_amount")) if data.get("min_amount") else None,
			"max_amount": flt(data.get("max_amount")) if data.get("max_amount") else None,
			"apply_on": data.get("apply_on", "Grand Total"),
			"company": data.get("company"),
			"customer": data.get("customer"),
			"valid_from": data.get("valid_from"),
			"valid_upto": data.get("valid_upto"),
			"maximum_use": cint(data.get("maximum_use", 0)) or None,
			"one_use": cint(data.get("one_use", 0)),
			"campaign": data.get("campaign"),
		})

		coupon.insert()

		return {
			"success": True,
			"message": _("Coupon {0} created successfully").format(coupon.coupon_code),
			"coupon_name": coupon.name,
			"coupon_code": coupon.coupon_code
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Coupon Creation Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to create coupon: {0}").format(str(e)))


@frappe.whitelist()
def update_coupon(coupon_name, data):
	"""
	Update an existing coupon.
	Can update validity dates, usage limits, disabled status, and discount configuration.
	"""
	check_promotion_permissions("write")

	import json
	if isinstance(data, str):
		data = json.loads(data)

	if not frappe.db.exists("POS Coupon", coupon_name):
		frappe.throw(_("Coupon {0} not found").format(coupon_name))

	try:
		coupon = frappe.get_doc("POS Coupon", coupon_name)

		# Update discount fields
		if "discount_type" in data:
			coupon.discount_type = data["discount_type"]
		if "discount_percentage" in data:
			coupon.discount_percentage = flt(data["discount_percentage"]) if data["discount_percentage"] else None
		if "discount_amount" in data:
			coupon.discount_amount = flt(data["discount_amount"]) if data["discount_amount"] else None
		if "min_amount" in data:
			coupon.min_amount = flt(data["min_amount"]) if data["min_amount"] else None
		if "max_amount" in data:
			coupon.max_amount = flt(data["max_amount"]) if data["max_amount"] else None
		if "apply_on" in data:
			coupon.apply_on = data["apply_on"]

		# Update validity and usage fields
		if "valid_from" in data:
			coupon.valid_from = data["valid_from"]
		if "valid_upto" in data:
			coupon.valid_upto = data["valid_upto"]
		if "maximum_use" in data:
			coupon.maximum_use = cint(data["maximum_use"]) or None
		if "one_use" in data:
			coupon.one_use = cint(data["one_use"])
		if "disabled" in data:
			coupon.disabled = cint(data["disabled"])
		if "description" in data:
			coupon.description = data["description"]

		coupon.save()

		return {
			"success": True,
			"message": _("Coupon {0} updated successfully").format(coupon.coupon_code)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Coupon Update Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to update coupon: {0}").format(str(e)))


@frappe.whitelist()
def toggle_coupon(coupon_name, disabled=None):
	"""Enable or disable a coupon."""
	check_promotion_permissions("write")

	if not frappe.db.exists("POS Coupon", coupon_name):
		frappe.throw(_("Coupon {0} not found").format(coupon_name))

	try:
		coupon = frappe.get_doc("POS Coupon", coupon_name)

		if disabled is not None:
			coupon.disabled = cint(disabled)
		else:
			# Toggle current state
			coupon.disabled = 0 if coupon.disabled else 1

		coupon.save()

		status = "disabled" if coupon.disabled else "enabled"
		return {
			"success": True,
			"message": _("Coupon {0} {1}").format(coupon.coupon_code, status),
			"disabled": coupon.disabled
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Coupon Toggle Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to toggle coupon: {0}").format(str(e)))


@frappe.whitelist()
def delete_coupon(coupon_name):
	"""Delete a coupon."""
	check_promotion_permissions("delete")

	if not frappe.db.exists("POS Coupon", coupon_name):
		frappe.throw(_("Coupon {0} not found").format(coupon_name))

	try:
		# Check if coupon has been used
		coupon = frappe.get_doc("POS Coupon", coupon_name)
		if coupon.used > 0:
			frappe.throw(_("Cannot delete coupon {0} as it has been used {1} times").format(
				coupon.coupon_code, coupon.used
			))

		frappe.delete_doc("POS Coupon", coupon_name)

		return {
			"success": True,
			"message": _("Coupon deleted successfully")
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Coupon Deletion Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to delete coupon: {0}").format(str(e)))


# =============================================================================
# REFERRAL CODE APIs
# =============================================================================

@frappe.whitelist()
def apply_referral_code(referral_code, customer):
	"""
	Apply a referral code for a customer - generates coupons for both referrer and referee

	Args:
		referral_code: The referral code to apply
		customer: The customer (referee) using the referral code

	Returns:
		dict with generated coupon information
	"""
	from pos_next.pos_next.doctype.referral_code.referral_code import apply_referral_code as apply_code

	try:
		result = apply_code(referral_code, customer)
		return {
			"success": True,
			"message": _("Referral code applied successfully! You've received a welcome coupon."),
			"referrer_coupon": result.get("referrer_coupon"),
			"referee_coupon": result.get("referee_coupon")
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Apply Referral Code Failed"),
			message=frappe.get_traceback()
		)
		frappe.throw(_("Failed to apply referral code: {0}").format(str(e)))


@frappe.whitelist()
def get_referral_codes(company=None, include_disabled=False):
	"""Get all referral codes with optional filters."""
	filters = {}

	if company:
		filters["company"] = company

	if not include_disabled:
		filters["disabled"] = 0

	referrals = frappe.get_all(
		"Referral Code",
		filters=filters,
		fields=[
			"name", "referral_name", "referral_code", "customer", "customer_name",
			"company", "campaign", "disabled", "referrals_count",
			"referrer_discount_type", "referrer_discount_percentage", "referrer_discount_amount",
			"referee_discount_type", "referee_discount_percentage", "referee_discount_amount"
		],
		order_by="creation desc"
	)

	return referrals


@frappe.whitelist()
def get_referral_details(referral_name):
	"""Get detailed information about a specific referral code."""
	check_promotion_permissions("read")

	if not frappe.db.exists("Referral Code", referral_name):
		frappe.throw(_("Referral Code {0} not found").format(referral_name))

	referral = frappe.get_doc("Referral Code", referral_name)
	data = referral.as_dict()

	# Get generated coupons for this referral
	coupons = frappe.get_all(
		"POS Coupon",
		filters={"referral_code": referral_name},
		fields=[
			"name", "coupon_code", "coupon_type", "customer", "customer_name",
			"used", "valid_from", "valid_upto", "disabled"
		],
		order_by="creation desc"
	)

	data["generated_coupons"] = coupons
	data["total_coupons_generated"] = len(coupons)

	return data
