from erpnext.accounts.doctype.pricing_rule.pricing_rule import apply_price_discount_rule as _original_apply_price_discount_rule

def apply_price_discount_rule(pricing_rule, item_details, args):
	"""
	Override to handle apply_discount_on_cheapest flag.
	
	When this flag is enabled, we skip immediate discount application
	and mark it for post-processing to apply on cheapest items.
	"""
	if pricing_rule.get("apply_discount_on_cheapest"):
		return
	
	return _original_apply_price_discount_rule(pricing_rule, item_details, args)