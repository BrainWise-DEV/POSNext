# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cstr
from erpnext.accounts.doctype.pricing_rule.pricing_rule import PricingRule

PROMOTION_TYPE_GWP = "GWP"
PROMOTION_TYPE_GIFT_POOL = "Gift Pool"


class CustomPricingRule(PricingRule):
	"""POS Next tweaks for GWP and Gift Pool promotions."""

	def _scheme_promotion_type(self) -> str:
		if self.promotional_scheme:
			return cstr(
				frappe.db.get_value("Promotional Scheme", self.promotional_scheme, "promotion_type")
			)
		return ""

	def _is_gwp_promotion(self) -> bool:
		if self.get("promotion_type") == PROMOTION_TYPE_GWP:
			return True
		return self._scheme_promotion_type() == PROMOTION_TYPE_GWP

	def _is_gift_pool_promotion(self) -> bool:
		if self.get("promotion_type") == PROMOTION_TYPE_GIFT_POOL:
			return True
		return self._scheme_promotion_type() == PROMOTION_TYPE_GIFT_POOL

	def validate_rate_or_discount(self):
		if (
			self.price_or_product_discount == "Product"
			and not self.free_item
			and (self._is_gwp_promotion() or self._is_gift_pool_promotion())
		):
			# GWP discounts the purchased line(s), not a separate free item.
			# Gift Pool grants from an ordered pool, so free_item may be empty
			# until the scheme's first pool SKU is synced onto the rule.
			if self._is_gwp_promotion() and not self.mixed_conditions and not self.get("same_item"):
				self.same_item = 1
			return
		super().validate_rate_or_discount()

	def cleanup_fields_value(self):
		keep_same_item = self._is_gwp_promotion() and self.mixed_conditions
		super().cleanup_fields_value()
		if keep_same_item:
			self.same_item = 1
