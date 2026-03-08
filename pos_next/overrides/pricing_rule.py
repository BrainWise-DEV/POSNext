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
        # Set pricing_rule_for for reference, but don't apply discount here
        # The discount will be applied later in apply_min_max_price_discounts
        if hasattr(item_details, 'pricing_rule_for'):
            item_details.pricing_rule_for = pricing_rule.get("rate_or_discount")
        # Return None to skip standard pricing rule application
        return None
    
    # For standard pricing rules, use the original implementation
    return _original_apply_price_discount_rule(pricing_rule, item_details, args)

def apply_min_max_price_discounts(doc, method=None, allowed_rules=None):
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
        doc: Document or dict containing items
        method: Hook method name (optional)
        allowed_rules: Optional list/set of rule names to restrict application to
    """
    try:
        # Collect all items that have Min/Max pricing rules applied
        rule_items, pricing_rules = _collect_min_max_rule_items(doc)

        # Process each pricing rule separately
        for pr_name, items in rule_items.items():
            # Respect allowed_rules filter if provided
            if allowed_rules is not None and pr_name not in allowed_rules:
                continue

            pr = pricing_rules[pr_name]
            if not pr:
                continue

            doc_price_list = (
                doc.get("selling_price_list") 
                or doc.get("buying_price_list") 
                or doc.get("price_list")
            )
            # Skip if pricing rule is restricted to a different price list
            if pr.for_price_list and pr.for_price_list != doc_price_list:
                continue

            # Determine sort direction: Max rules need descending order (highest first)
            # Min rules need ascending order (lowest first)
            reverse = pr.apply_discount_on_price == "Max"
            items.sort(
                key=lambda i: flt(i.price_list_rate or i.rate or 0),
                reverse=reverse
            )

            # Track remaining quantity that can receive discount
            qty_limit = flt(pr.min_or_max_discount_qty_limit or 0)
            has_qty_limit = qty_limit > 0
            remaining_qty = qty_limit if has_qty_limit else 0

            # Apply discount to items in priority order (sorted by price)
            for item in items:
                base_rate = flt(item.price_list_rate) or flt(item.rate)
                qty = flt(item.qty)
                if not base_rate or qty <= 0:
                    continue
                
                # Unlimited discount to first item only if no limit is set
                if not has_qty_limit:
                    if item == items[0]:
                        _apply_discount(pr, item, qty)
                    else:
                        # Reset other items that might have had discounts
                        item.discount_percentage = 0.0
                        item.discount_amount = 0.0
                        item.rate = base_rate
                        item.amount = base_rate * qty
                    continue

                # If discount quantity limit exhausted, reset item to base price
                if remaining_qty <= 0:
                    item.discount_percentage = 0.0
                    item.discount_amount = 0.0
                    item.rate = base_rate
                    item.amount = base_rate * qty
                    continue

                # Calculate how much of this item's quantity qualifies for discount
                discount_qty = min(qty, remaining_qty)

                # Apply discount to the eligible quantity
                _apply_discount(pr, item, discount_qty)
                remaining_qty -= discount_qty

        # Recalculate totals after applying all discounts
        if hasattr(doc, "calculate_taxes_and_totals") and callable(doc.calculate_taxes_and_totals):
            doc.calculate_taxes_and_totals()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Min/Max Pricing Rule Failed")
        if not frappe.flags.in_test:
            frappe.msgprint(_("Warning: Min/Max pricing rules could not be fully applied."), indicator="orange")


def _apply_discount(pr, item, eligible_qty):
    """
    Apply discount to an item based on the pricing rule configuration.
    Ensures mathematical accuracy where rate * qty = amount.
    """
    base_rate = flt(item.price_list_rate) or flt(item.rate)
    qty = flt(item.qty)
    
    if not base_rate or eligible_qty <= 0 or qty <= 0:
        return

    # Calculate maximum possible discount to prevent negative rates
    total_discount = 0.0
    if pr.rate_or_discount == "Rate":
        total_discount = (base_rate - flt(pr.rate)) * eligible_qty
    elif pr.rate_or_discount == "Discount Percentage":
        total_discount = (base_rate * flt(pr.discount_percentage) / 100) * eligible_qty
    elif pr.rate_or_discount == "Discount Amount":
        total_discount = flt(pr.discount_amount) * eligible_qty
    
    # Mathematical accuracy: Set amount first, then derive rate
    # This ensures (rate * qty) exactly matches (base_value - total_discount)
    total_line_value = base_rate * qty
    net_amount = max(total_line_value - total_discount, 0.0)
    
    item.update({
        "amount": net_amount,
        "rate": net_amount / qty if qty else 0,
        "discount_amount": total_line_value - net_amount,
        "discount_percentage": ((total_line_value - net_amount) / total_line_value * 100) if total_line_value else 0,
        "pricing_rule": pr.name,
        "pricing_rule_for": pr.rate_or_discount
    })

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

    items = doc.get("items") or []
    for item in items:
        # Skip free items, items with zero/negative quantity, or items without pricing rules
        if item.get("is_free_item") or flt(item.get("qty")) <= 0 or not item.get("pricing_rules"):
            continue

        # Get all pricing rules applied to this item
        for pr_name in get_applied_pricing_rules(item.get("pricing_rules")):
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

"""
Pricing Rule Override
Adds POS-only filtering to ERPNext's pricing rule conditions.

When a Pricing Rule has pos_only=1, it should only apply to POS transactions
(Sales Invoice with is_pos=1, or POS Invoice). Non-POS documents like
Quotations, Sales Orders, Delivery Notes, and regular Sales Invoices
will have these rules excluded from matching.
"""


def sync_pos_only_to_pricing_rules(doc, method=None):
	"""Sync pos_only from Promotional Scheme to its generated Pricing Rules.

	Called via doc_events on_update hook, which runs after ERPNext's
	PromotionalScheme.on_update() has already created/updated the Pricing Rules.
	"""
	pos_only = doc.get("pos_only") or 0
	frappe.db.set_value(
		"Pricing Rule",
		{"promotional_scheme": doc.name},
		"pos_only",
		pos_only,
		update_modified=False,
	)


def patch_get_other_conditions(pr_utils):
	"""Monkey-patch get_other_conditions to filter pos_only pricing rules.

	No Frappe hook exists for non-whitelisted module-level functions,
	so monkey-patching is the only option for this SQL condition injection.
	"""
	_original_get_other_conditions = pr_utils.get_other_conditions

	def _patched_get_other_conditions(conditions, values, args):
		conditions = _original_get_other_conditions(conditions, values, args)

		doctype = args.get("doctype", "")
		# POS Invoice doctype — always POS, all rules apply
		if doctype in ("POS Invoice", "POS Invoice Item"):
			pass
		# Sales Invoice — check is_pos flag
		elif doctype in ("Sales Invoice", "Sales Invoice Item"):
			if not args.get("is_pos"):
				conditions += " and ifnull(`tabPricing Rule`.pos_only, 0) = 0"
		# All other doctypes (Quotation, SO, DN, Purchase docs) — exclude POS-only
		else:
			conditions += " and ifnull(`tabPricing Rule`.pos_only, 0) = 0"

		return conditions

	pr_utils.get_other_conditions = _patched_get_other_conditions
