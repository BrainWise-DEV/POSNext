"""
Override module for ERPNext Pricing Rules to support Min/Max price-based discounts.

This module extends the standard pricing rule functionality to handle discounts
that should be applied only to items with minimum or maximum prices within a
transaction. The Min/Max discount logic requires special handling because it
needs to evaluate all items together to determine which items qualify for the
discount based on their relative prices.
"""
import frappe
from frappe.utils import flt
from collections import defaultdict
from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules
from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	apply_price_discount_rule as _original_apply_price_discount_rule
)
from frappe import _


def apply_price_discount_rule(pricing_rule, item_details, args):
    """
    Override function to defer Min/Max discount application to a later stage.
    
    This function intercepts the standard pricing rule application process.
    For Min/Max pricing rules, it skips the immediate discount application
    because these rules require evaluating all items together to determine
    which items qualify based on their relative prices.
    
    Args:
        pricing_rule (dict): The pricing rule configuration dictionary
        item_details (dict): Details about the item being processed
        args (dict): Additional arguments for the pricing rule application
        
    Returns:
        None: If the rule is Min/Max type (deferred to apply_min_max_price_discounts)
        Any: Result from the original function for non-Min/Max rules
    """
    apply_discount_on_price = pricing_rule.get("apply_discount_on_price") or ""
    
    # Defer Min/Max discount application - these require evaluating all items
    # together to determine which items qualify based on price ranking
    if apply_discount_on_price in ["Min", "Max"]:
        item_details.pricing_rule_for = pricing_rule.rate_or_discount
        return 
    
    # For standard pricing rules, use the original implementation
    return _original_apply_price_discount_rule(pricing_rule, item_details, args)

def patch_pricing_rule():
    """Safely patch the pricing rule module after Frappe is initialized."""
    try:
        from erpnext.accounts.doctype.pricing_rule import pricing_rule as pricing_rule_module
        pricing_rule_module.apply_price_discount_rule = apply_price_discount_rule
    except Exception:
        frappe.log_error("Failed to patch pricing rule module for Min/Max discounts")

def apply_min_max_price_discounts(doc, method=None):
    """
    Apply Min/Max pricing rule discounts to document items.
    
    This function processes all items that have Min/Max pricing rules applied.
    It sorts items by price (ascending for Min, descending for Max) and applies
    discounts only to the items that qualify based on the quantity limit specified
    in the pricing rule.
    
    The discount is applied in priority order:
    - For "Min" rules: Items with lowest prices get discounted first
    - For "Max" rules: Items with highest prices get discounted first
    
    Args:
        doc: The document (e.g., Sales Invoice, Quotation) containing items
        method (str, optional): Hook method name if called via Frappe hooks
    """
    try:
        # Collect all items that have Min/Max pricing rules applied
        rule_items, pricing_rules = _collect_min_max_rule_items(doc)

        # Process each pricing rule separately
        for pr_name, items in rule_items.items():
            pr = pricing_rules[pr_name]
            doc_price_list = (
                doc.get("selling_price_list") 
                or doc.get("buying_price_list") 
                or doc.get("price_list")
            )
            # Skip if pricing rule is restricted to a different price list
            if pr.for_price_list and pr.for_price_list != doc_price_list:
                continue

            # Skip if no items match this rule
            if not items:
                continue

            # Determine sort direction: Max rules need descending order (highest first)
            # Min rules need ascending order (lowest first)
            reverse = pr.apply_discount_on_price == "Max"
            items.sort(
                key=lambda i: flt(i.price_list_rate or i.rate or 0),
                reverse=reverse
            )

            # Track remaining quantity that can receive discount
            # This limit ensures only a specified quantity gets discounted
            qty_limit = flt(pr.min_or_max_discount_qty_limit or 0)
            has_qty_limit = qty_limit > 0
            remaining_qty = qty_limit if has_qty_limit else 0

            # Apply discount to items in priority order (sorted by price)
            for item in items:
                base_rate = flt(item.price_list_rate) or flt(item.rate)
                if not base_rate:
                    continue
                
                # Unlimited discount -> apply fully
                if not has_qty_limit:
                    if item == items[0]:
                        _apply_discount(pr, item, item.qty)
                        continue

                    
                # If discount quantity limit exhausted, reset item to base price
                if remaining_qty <= 0:
                    item.discount_percentage = 0.0
                    item.discount_amount = 0.0
                    continue

                # Calculate how much of this item's quantity qualifies for discount
                # This ensures we don't exceed the total discount quantity limit
                discount_qty =  min(flt(item.qty), remaining_qty)

                # Apply discount to the eligible quantity
                _apply_discount(pr, item, discount_qty)
                remaining_qty -= discount_qty

        # Recalculate totals after applying all discounts
        if hasattr(doc, "calculate_taxes_and_totals"):
            doc.calculate_taxes_and_totals()
    except frappe.ValidationError:
        raise
    except Exception as e:
        # Log errors but don't break the document processing flow
        frappe.log_error(frappe.get_traceback(), "Min/Max Pricing Rule Failed", e)
        frappe.throw(
            _("Failed to apply pricing rule discounts: {0}").format(str(e)),
            title=_("Pricing Rule Error")
        )


def _apply_discount(pr, item, eligible_qty):
    """
    Apply discount to an item based on the pricing rule configuration.
    
    This helper function calculates and applies the discount amount based on
    the pricing rule's discount type (Rate, Discount Percentage, or Discount Amount).
    It ensures that discounts never result in negative item rates.
    
    Args:
        pr: The Pricing Rule document
        item: The item row to apply discount to
        eligible_qty (float): The quantity of this item that qualifies for discount
    """
    base_rate = flt(item.price_list_rate) or flt(item.rate)
    if not base_rate or eligible_qty <= 0:
        return

    qty = flt(item.qty)
    # Calculate maximum possible discount to prevent negative rates
    # This ensures the discount never exceeds the item's base value
    base_discount_cap = base_rate * eligible_qty
    total_discount = 0.0

    # Calculate discount based on pricing rule type
    if pr.rate_or_discount == "Rate" and pr.rate:
        # Fixed rate: discount is the difference between base rate and rule rate
        total_discount = (base_rate - flt(pr.rate)) * eligible_qty

    elif pr.rate_or_discount == "Discount Percentage" and pr.discount_percentage:
        # Percentage discount: calculate per unit, then multiply by eligible quantity
        per_unit_discount = base_rate * flt(pr.discount_percentage) / 100
        total_discount = per_unit_discount * eligible_qty

    elif pr.rate_or_discount == "Discount Amount" and pr.discount_amount:
        # Fixed amount discount: apply per unit of eligible quantity
        total_discount = flt(pr.discount_amount) * eligible_qty

    # Enforce discount cap to prevent negative rates
    total_discount = min(total_discount, base_discount_cap)

    # Calculate effective rate after discount
    # Note: discount is applied to eligible_qty, but rate is calculated per total qty
    effective_rate = (base_rate * qty - total_discount) / qty

    # Update item fields with calculated values
    item.rate = max(effective_rate, 0.0)  # Ensure rate is never negative
    item.discount_amount = total_discount
    # Calculate discount percentage based on total item value
    item.discount_percentage = (
        total_discount / (base_rate * qty)
    ) * 100 if base_rate * qty else 0.0

    # Recalculate item amount with new rate
    item.amount = item.rate * qty


def _collect_min_max_rule_items(doc):
    """
    Collect all items that have Min/Max pricing rules applied.
    
    This function iterates through all items in the document and identifies
    which items are subject to Min/Max pricing rules. It uses caching to
    avoid repeatedly fetching the same pricing rule documents.
    
    Args:
        doc: The document containing items to process
        
    Returns:
        tuple: A tuple containing:
            - rule_items (dict): Dictionary mapping pricing rule names to lists of items
            - pricing_rules_cache (dict): Dictionary of cached Pricing Rule documents
    """
    # Group items by their pricing rules
    rule_items = defaultdict(list)
    # Cache pricing rule documents to avoid redundant database queries
    pricing_rules_cache = {}

    for item in doc.items:
        # Skip free items, items with zero/negative quantity, or items without pricing rules
        if item.is_free_item or flt(item.qty) <= 0 or not item.pricing_rules:
            continue

        # Get all pricing rules applied to this item
        for pr_name in get_applied_pricing_rules(item.pricing_rules):
            # Fetch and cache pricing rule if not already cached
            if pr_name not in pricing_rules_cache:
                pr = frappe.get_cached_doc("Pricing Rule", pr_name)
                # Only cache rules that are Price-type Min/Max rules
                # Other rules are handled by the standard pricing rule system
                if (
                    pr.price_or_product_discount == "Price"
                    and pr.apply_discount_on_price in ("Min", "Max")
                ):
                    pricing_rules_cache[pr_name] = pr
                else:
                    # Mark non-Min/Max rules as None to skip them
                    pricing_rules_cache[pr_name] = None

            # Add item to the rule's item list if it's a Min/Max rule
            if pricing_rules_cache[pr_name]:
                rule_items[pr_name].append(item)

    return rule_items, pricing_rules_cache
