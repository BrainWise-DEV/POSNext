# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.pricing_rule.pricing_rule import PricingRule

PROMOTION_TYPE_GWP = "GWP"


class CustomPricingRule(PricingRule):
	"""POS Next tweaks for GWP promotions."""

	def _is_gwp_promotion(self) -> bool:
		if self.get("promotion_type") == PROMOTION_TYPE_GWP:
			return True
		if self.promotional_scheme:
			return (
				frappe.db.get_value("Promotional Scheme", self.promotional_scheme, "promotion_type")
				== PROMOTION_TYPE_GWP
			)
		return False

	def validate_rate_or_discount(self):
		if (
			self.price_or_product_discount == "Product"
			and not self.free_item
			and self._is_gwp_promotion()
		):
			# GWP discounts the purchased line(s), not a separate free item.
			if not self.mixed_conditions and not self.get("same_item"):
				self.same_item = 1
			return
		super().validate_rate_or_discount()

	def cleanup_fields_value(self):
		keep_same_item = self._is_gwp_promotion() and self.mixed_conditions
		super().cleanup_fields_value()
		if keep_same_item:
			self.same_item = 1
