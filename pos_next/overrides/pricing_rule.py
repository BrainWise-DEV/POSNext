import frappe
from frappe.utils import flt
from collections import defaultdict
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
        rule_items, pricing_rules = _collect_min_max_rule_items(doc)

        for pr_name, items in rule_items.items():
            pr = pricing_rules[pr_name]

            if pr.for_price_list and pr.for_price_list != doc.selling_price_list:
                continue

            if not items:
                continue

            key = lambda i: flt(i.price_list_rate or i.rate or 0)
            target_item = (
                max(items, key=key)
                if pr.apply_discount_on_price == "Max"
                else min(items, key=key)
            )

            for item in items:
                if item != target_item:
                    item.discount_percentage = 0.0
                    item.discount_amount = 0.0
                    item.rate = flt(item.price_list_rate)
                    item.amount = item.rate * item.qty

            _apply_discount(pr, target_item)

        if hasattr(doc, "calculate_taxes_and_totals"):
            doc.calculate_taxes_and_totals()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Min/Max Pricing Rule Failed")



def _apply_discount(pricing_rule, item):
    """
    Apply discount safely and force the rate to update.
    """
    # Use price_list_rate as the source of truth to avoid compounding discounts
    base_rate = flt(item.price_list_rate) or flt(item.rate)
    if not base_rate:
        return

    if pricing_rule.rate_or_discount == "Discount Percentage":
        item.discount_percentage = flt(pricing_rule.discount_percentage)
        item.discount_amount = 0.0
    elif pricing_rule.rate_or_discount == "Discount Amount":
        item.discount_amount = flt(pricing_rule.discount_amount)
        item.discount_percentage = 0.0
    

    item.rate = base_rate * (1.0 - (flt(item.discount_percentage) / 100.0)) - flt(item.discount_amount)
    item.amount = flt(item.rate) * flt(item.qty)


def _collect_min_max_rule_items(doc):
    rule_items = defaultdict(list)
    pricing_rules_cache = {}

    for item in doc.items:
        if item.is_free_item or flt(item.qty) <= 0 or not item.pricing_rules:
            continue

        for pr_name in get_applied_pricing_rules(item.pricing_rules):
            if pr_name not in pricing_rules_cache:
                pr = frappe.get_cached_doc("Pricing Rule", pr_name)
                if (
                    pr.price_or_product_discount == "Price"
                    and pr.apply_discount_on_price in ("Min", "Max")
                ):
                    pricing_rules_cache[pr_name] = pr
                else:
                    pricing_rules_cache[pr_name] = None

            if pricing_rules_cache[pr_name]:
                rule_items[pr_name].append(item)

    return rule_items, pricing_rules_cache