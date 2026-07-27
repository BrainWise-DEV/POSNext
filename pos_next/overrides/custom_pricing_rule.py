# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from erpnext.accounts.doctype.pricing_rule.pricing_rule import PricingRule

PROMOTION_TYPE_GWP = "GWP"


class CustomPricingRule(PricingRule):
	"""POS Next tweaks for GWP promotions."""

	def validate_rate_or_discount(self):
		if (
			self.price_or_product_discount == "Product"
			and not self.free_item
			and self.get("promotion_type") == PROMOTION_TYPE_GWP
			and (self.get("same_item") or self.mixed_conditions)
		):
			return
		super().validate_rate_or_discount()

	def cleanup_fields_value(self):
		keep_same_item = self.get("promotion_type") == PROMOTION_TYPE_GWP and self.mixed_conditions
		super().cleanup_fields_value()
		if keep_same_item:
			self.same_item = 1
