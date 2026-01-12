# Copyright (c) 2025, BrainWise and contributors
import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules
from erpnext.setup.doctype.item_group.item_group import get_child_item_groups


def apply_cheapest_item_discounts(doc):
	"""
	Apply discounts to cheapest items after all standard pricing rules are evaluated.
	
	This processes pricing rules that have apply_discount_on_cheapest enabled.
	
	It checks if the condition (N qty from Item Code/Item Group/Brand) is met, 
	and if so, applies discount to the cheapest M items from the ENTIRE document.
	
	Args:
		doc: Sales Invoice, Sales Order, or Quotation document
	"""
	if not hasattr(doc, "items") or not doc.items:
		return
	
	# Collect pricing rules that need cheapest item discount processing
	cheapest_discount_rules = {}
	
	# First: collect all pricing rules with apply_discount_on_cheapest
	for item in doc.items:
		if not item.get("pricing_rules") or item.get("is_free_item"):
			continue
			
		pricing_rules = get_applied_pricing_rules(item.get("pricing_rules"))
		for pr_name in pricing_rules:
			try:
				pr = frappe.get_cached_doc("Pricing Rule", pr_name)
				
				if pr.get("price_or_product_discount") != "Price":
					continue
				
				if pr.get("apply_discount_on_cheapest") and pr.get("cheapest_qty"):
					if _check_pricing_rule_condition_met(doc, pr):
						if pr_name not in cheapest_discount_rules:
							cheapest_discount_rules[pr_name] = {
								"pricing_rule": pr,
								"cheapest_qty": flt(pr.get("cheapest_qty", 0)),
								"discount_percentage": flt(pr.get("discount_percentage", 0)),
								"discount_amount": flt(pr.get("discount_amount", 0)),
								"rate_or_discount": pr.get("rate_or_discount"),
							}
			except Exception:
				# Skip if pricing rule doesn't exist
				continue
	
	if not cheapest_discount_rules:
		return
	
	# Second: For each rule, find cheapest items that HAVE the pricing rule and apply discount
	# look at items that have this pricing rule, then select cheapest ones
	for pr_name, rule_data in cheapest_discount_rules.items():
		pr = rule_data["pricing_rule"]
		
		# Get items that have this pricing rule applied
		items_with_rule = []
		for item in doc.items:
			if item.get("is_free_item"):
				continue
			
			# Check if this item has the pricing rule
			item_pricing_rules = get_applied_pricing_rules(item.get("pricing_rules") or "")
			if pr_name in item_pricing_rules:
				items_with_rule.append(item)
		
		if not items_with_rule:
			continue
		
		# Sort by price_list_rate (cheapest first)
		# If price_list_rate not available, use rate
		items_with_rule.sort(
			key=lambda x: flt(x.get("price_list_rate") or x.get("rate") or 0)
		)
		
		# Apply discount to cheapest M items (from items that have the pricing rule)
		remaining_qty = rule_data["cheapest_qty"]
		
		for item in items_with_rule:
			if remaining_qty <= 0:
				break
				
			# Calculate how much qty to discount for this item
			item_qty = flt(item.get("qty") or 0)
			if item_qty <= 0:
				continue
				
			discount_qty = min(item_qty, remaining_qty)
			remaining_qty -= discount_qty
			
			# Apply discount to this item
			_apply_discount_to_item(item, rule_data, discount_qty, item_qty)
	
	# Recalculate totals after applying discounts
	if hasattr(doc, "calculate_taxes_and_totals"):
		doc.calculate_taxes_and_totals()


def _check_pricing_rule_condition_met(doc, pricing_rule):
	"""
	Check if minimum qty/amount condition is met for the pricing rule.
	
	Supports all apply_on types: Item Code, Item Group, and Brand.
	
	Args:
		doc: Document with items
		pricing_rule: Pricing Rule document
		
	Returns:
		bool: True if condition is met
	"""
	apply_on = pricing_rule.get("apply_on")
	
	# Only support Item Code, Item Group, and Brand
	if apply_on not in ["Item Code", "Item Group", "Brand"]:
		return False
	
	# Get the items/codes that match the pricing rule criteria
	matching_items = _get_matching_items_for_pricing_rule(doc, pricing_rule)
	
	if not matching_items:
		return False
	
	# Calculate total qty/amount from matching items
	total_qty = 0
	total_amt = 0
	
	for item in doc.items:
		if item.get("is_free_item"):
			continue
		
		# Check if this item matches the pricing rule criteria
		item_matches = False
		
		if apply_on == "Item Code":
			item_code = item.get("item_code")
			if item_code in matching_items:
				item_matches = True
				
		elif apply_on == "Item Group":
			item_group = item.get("item_group")
			if item_group in matching_items:
				item_matches = True
				
		elif apply_on == "Brand":
			brand = item.get("brand")
			if brand in matching_items:
				item_matches = True
		
		if item_matches:
			# Use stock_qty if available, else qty
			qty = flt(item.get("stock_qty") or item.get("qty") or 0)
			total_qty += qty
			
			# Calculate amount
			rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
			total_amt += qty * rate
	
	# Check if min_qty or min_amt condition is met
	min_qty = flt(pricing_rule.get("min_qty") or 0)
	min_amt = flt(pricing_rule.get("min_amt") or 0)
	
	if min_qty > 0 and total_qty >= min_qty:
		return True
	if min_amt > 0 and total_amt >= min_amt:
		return True
		
	return False


def _get_matching_items_for_pricing_rule(doc, pricing_rule):
	"""
	Get list of items/codes that match the pricing rule criteria.
	
	Args:
		doc: Document with items
		pricing_rule: Pricing Rule document
		
	Returns:
		list: List of matching item codes, item groups, or brands
	"""
	apply_on = pricing_rule.get("apply_on")
	matching_items = []
	
	if apply_on == "Item Code":
		# Get item codes from pricing rule
		for row in pricing_rule.get("items", []):
			item_code = row.get("item_code")
			if item_code:
				matching_items.append(item_code)
		
	elif apply_on == "Item Group":
		# Get item groups from pricing rule (including child groups)
		for row in pricing_rule.get("item_groups", []):
			item_group = row.get("item_group")
			if item_group:
				# Include child item groups
				matching_items.extend(get_child_item_groups(item_group))
				matching_items.append(item_group)
		
	elif apply_on == "Brand":
		# Get brands from pricing rule
		for row in pricing_rule.get("brands", []):
			brand = row.get("brand")
			if brand:
				matching_items.append(brand)
	
	# Remove duplicates and return
	return list(set(matching_items))


def _apply_discount_to_item(item, rule_data, discount_qty, item_qty):
	"""
	Apply discount to a single item based on rule data.
	
	Args:
		item: Item row
		rule_data: Dictionary containing pricing rule and discount info
		discount_qty: Quantity of this item to apply discount on
		item_qty: Total quantity of this item
	"""
	pr = rule_data["pricing_rule"]
	rate_or_discount = rule_data["rate_or_discount"]
	
	# Get current item rate
	item_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)
	if item_rate <= 0:
		return
	
	# Calculate discount based on rate_or_discount type
	if rate_or_discount == "Discount Percentage":
		# Calculate discount amount for this item proportionally
		discount_percentage = rule_data["discount_percentage"]
		discount_amt_per_unit = item_rate * (discount_percentage / 100)
		discount_amt = discount_amt_per_unit * (discount_qty / item_qty)
		
		# Add to existing discount
		current_discount_amt = flt(item.get("discount_amount") or 0)
		item.discount_amount = current_discount_amt + discount_amt
		
		# Recalculate discount percentage
		if item_rate > 0:
			total_discount_pct = (item.discount_amount / item_rate) * 100
			item.discount_percentage = flt(total_discount_pct, 2)
			
	elif rate_or_discount == "Discount Amount":
		# Apply discount amount proportionally
		discount_amt_per_unit = rule_data["discount_amount"]
		discount_amt = discount_amt_per_unit * (discount_qty / item_qty)
		
		# Add to existing discount
		current_discount_amt = flt(item.get("discount_amount") or 0)
		item.discount_amount = current_discount_amt + discount_amt
		
		# Recalculate discount percentage
		if item_rate > 0:
			item.discount_percentage = flt((item.discount_amount / item_rate) * 100, 2)
	
	# Recalculate item rate
	if item.get("price_list_rate"):
		# Apply discount percentage
		if item.get("discount_percentage"):
			item.rate = flt(
				item.price_list_rate * (1.0 - (flt(item.discount_percentage) / 100.0)),
				item.precision("rate") if hasattr(item, "precision") else 2
			)
		
		# Apply discount amount (takes precedence)
		if item.get("discount_amount"):
			item.rate = flt(
				item.price_list_rate - item.discount_amount,
				item.precision("rate") if hasattr(item, "precision") else 2
			)
	
	# Recalculate item amount
	if hasattr(item, "amount"):
		item.amount = flt(
			item.rate * item.qty, 
			item.precision("amount") if hasattr(item, "precision") else 2
		)

