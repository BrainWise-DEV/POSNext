import frappe
from frappe.utils import flt
from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules
from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	apply_price_discount_rule as _original_apply_price_discount_rule
)


def apply_price_discount_rule(pricing_rule, item_details, args):
	"""
	Override to skip applying discount if apply_discount_on_price is Min/Max.
	The discount will be applied by apply_min_max_price_discounts instead.
	"""
	apply_discount_on_price = pricing_rule.get("apply_discount_on_price") or ""
	
	# Skip applying discount if Min/Max - will be handled by apply_min_max_price_discounts
	if apply_discount_on_price in ["Min", "Max"]:
		return 
	
	# Otherwise, use original function
	return _original_apply_price_discount_rule(pricing_rule, item_details, args)


def apply_min_max_price_discounts(doc, method=None):
    """
    Apply discount only to the min/max priced item based on applied Pricing Rules.
    Reset discount on other items for the same pricing rule.
    """
    try:
        for pr_name in _get_min_max_pricing_rules(doc):
            pr = frappe.get_cached_doc("Pricing Rule", pr_name)

            # Enforce price list
            if pr.for_price_list and pr.for_price_list != doc.selling_price_list:
                continue

            eligible_items = [
                item for item in doc.items
                if not item.is_free_item
                and flt(item.qty) > 0
                and item.pricing_rules
                and pr_name in get_applied_pricing_rules(item.pricing_rules)
            ]

            if not eligible_items:
                continue

            reverse = pr.apply_discount_on_price == "Max"
            eligible_items.sort(
                key=lambda x: flt(x.price_list_rate or x.rate or 0),
                reverse=reverse
            )

            target_item = eligible_items[0]

            # Reset discount for non-target items FIRST
            for item in eligible_items:
                if item != target_item:
                    # Remove this pricing rule's discount contribution
                    item.discount_percentage = 0.0
                    item.discount_amount = 0.0
            
            # Then apply discount to target item
            _apply_discount(pr, target_item)
        
        # Recalculate totals once after processing all pricing rules
        if hasattr(doc, "calculate_taxes_and_totals"):
            doc.calculate_taxes_and_totals()
            
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Min/Max Pricing Rule Failed"
        )

def _get_min_max_pricing_rules(doc):
	"""
	Extract unique Pricing Rules with apply_discount_on_price.
	"""
	rules = set()

	for item in doc.items:
		for pr_name in get_applied_pricing_rules(item.pricing_rules or ""):
			pr = frappe.get_cached_doc("Pricing Rule", pr_name)
			if pr.price_or_product_discount == "Price" and pr.apply_discount_on_price in ("Min", "Max"):
				rules.add(pr_name)

	return rules


def _apply_discount(pricing_rule, item):
	"""
	Apply discount safely to a single item.
	"""

	base_rate = flt(item.rate or item.price_list_rate)
	if not base_rate:
		return

	if pricing_rule.rate_or_discount == "Discount Percentage":
		item.discount_percentage = flt(pricing_rule.discount_percentage)
	elif pricing_rule.rate_or_discount == "Discount Amount":
		item.discount_amount = flt(pricing_rule.discount_amount)
		item.discount_percentage = flt(
			(item.discount_amount / base_rate) * 100,
			2
		)