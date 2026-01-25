# -*- coding: utf-8 -*-
# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

"""
Offers API - Fetches and manages promotional offers and pricing rules for POS

This module provides a clean API for retrieving promotional offers from both
Promotional Schemes and standalone Pricing Rules.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


# ============================================================================
# Constants
# ============================================================================

class DiscountType:
	"""Discount type constants"""
	PRICE = "Price"
	PRODUCT = "Product"


class ApplyOn:
	"""Apply on constants"""
	ITEM_CODE = "Item Code"
	ITEM_GROUP = "Item Group"
	BRAND = "Brand"
	TRANSACTION = "Transaction"


class OfferSource:
	"""Offer source constants"""
	PROMOTIONAL_SCHEME = "Promotional Scheme"
	PRICING_RULE = "Pricing Rule"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class OfferEligibility:
	"""Eligibility criteria for an offer"""
	items: List[str]
	item_groups: List[str]
	brands: List[str]


@dataclass
class Offer:
	"""Structured offer data"""
	name: str
	title: str
	description: str
	apply_on: str
	offer: str
	auto: int
	coupon_based: int
	min_qty: float
	max_qty: float
	min_amt: float
	max_amt: float
	discount_type: Optional[str]
	rate: float
	discount_amount: float
	discount_percentage: float
	valid_from: Optional[str]
	valid_upto: Optional[str]
	source: str
	promotional_scheme: Optional[str]
	promotional_scheme_id: Optional[str]
	eligible_items: List[str]
	eligible_item_groups: List[str]
	eligible_brands: List[str]
	# Free item fields for product discounts
	free_item: Optional[str] = None
	free_qty: float = 0
	free_item_uom: Optional[str] = None
	same_item: int = 0  # 1 if free item should be same as purchased item
	is_recursive: int = 0  # 1 if offer applies recursively (e.g., buy 2 get 1 free for every 2)
	recurse_for: float = 0  # Give free item for every N quantity (used when is_recursive=1)
	apply_recursion_over: float = 0  # Qty for which recursion isn't applicable

	def to_dict(self) -> Dict:
		"""Convert to dictionary for API response"""
		return asdict(self)


# ============================================================================
# Database Query Helpers
# ============================================================================

class EligibilityFetcher:
	"""Fetches eligibility criteria for pricing rules/schemes in bulk"""

	@staticmethod
	def fetch_all(parent_names: List[str]) -> Dict[str, OfferEligibility]:
		"""
		Fetch all eligibility criteria for given parent names

		Args:
			parent_names: List of pricing rule or scheme names

		Returns:
			Dict mapping parent name to OfferEligibility
		"""
		if not parent_names:
			return {}

		items_map = EligibilityFetcher._fetch_items(parent_names)
		item_groups_map = EligibilityFetcher._fetch_item_groups(parent_names)
		brands_map = EligibilityFetcher._fetch_brands(parent_names)

		# Combine all maps into OfferEligibility objects
		eligibility = {}
		for parent in parent_names:
			eligibility[parent] = OfferEligibility(
				items=items_map.get(parent, []),
				item_groups=item_groups_map.get(parent, []),
				brands=brands_map.get(parent, [])
			)

		return eligibility

	@staticmethod
	def _fetch_items(parent_names: List[str]) -> Dict[str, List[str]]:
		"""
		Fetch item codes for given parents, expanding template items to include variants.

		When a pricing rule is created for a template item (has_variants=1), this method
		automatically includes all its variant items in the eligible items list.
		This ensures offers work correctly when variants are added to cart.
		"""
		results = frappe.db.sql("""
			SELECT parent, item_code
			FROM `tabPricing Rule Item Code`
			WHERE parent IN %s
		""", [parent_names], as_dict=1)

		if not results:
			return {}

		# Collect all unique item codes
		all_item_codes = list({row["item_code"] for row in results})

		# Find which items are templates (have variants)
		template_items = frappe.get_all(
			"Item",
			filters={
				"name": ["in", all_item_codes],
				"has_variants": 1
			},
			pluck="name"
		)

		# Fetch variants for all template items in one query
		variants_map = {}
		if template_items:
			variants = frappe.get_all(
				"Item",
				filters={
					"variant_of": ["in", template_items],
					"disabled": 0
				},
				fields=["name", "variant_of"]
			)
			for variant in variants:
				variants_map.setdefault(variant["variant_of"], []).append(variant["name"])

		# Build items map, expanding templates to include their variants
		items_map = {}
		for row in results:
			parent = row["parent"]
			item_code = row["item_code"]

			items_map.setdefault(parent, []).append(item_code)

			# If this item is a template, also add all its variants
			if item_code in variants_map:
				items_map[parent].extend(variants_map[item_code])

		return items_map

	@staticmethod
	def _fetch_item_groups(parent_names: List[str]) -> Dict[str, List[str]]:
		"""Fetch item groups for given parents"""
		results = frappe.db.sql("""
			SELECT parent, item_group
			FROM `tabPricing Rule Item Group`
			WHERE parent IN %s
		""", [parent_names], as_dict=1)

		groups_map = {}
		for row in results:
			groups_map.setdefault(row["parent"], []).append(row["item_group"])
		return groups_map

	@staticmethod
	def _fetch_brands(parent_names: List[str]) -> Dict[str, List[str]]:
		"""Fetch brands for given parents"""
		results = frappe.db.sql("""
			SELECT parent, brand
			FROM `tabPricing Rule Brand`
			WHERE parent IN %s
		""", [parent_names], as_dict=1)

		brands_map = {}
		for row in results:
			brands_map.setdefault(row["parent"], []).append(row["brand"])
		return brands_map


class SlabFetcher:
	"""Fetches discount slabs for promotional schemes"""

	@staticmethod
	def fetch_price_slabs(scheme_names: List[str]) -> Dict[str, Dict]:
		"""Fetch first price discount slab for each scheme"""
		if not scheme_names:
			return {}

		results = frappe.db.sql("""
			SELECT
				parent, min_qty, max_qty, min_amount, max_amount,
				rate_or_discount, rate, discount_amount, discount_percentage,
				apply_multiple_pricing_rules
			FROM `tabPromotional Scheme Price Discount`
			WHERE parent IN %s AND disable = 0
			ORDER BY parent, min_amount ASC, min_qty ASC
		""", [scheme_names], as_dict=1)

		# Take first slab for each parent
		slabs_map = {}
		for slab in results:
			if slab["parent"] not in slabs_map:
				slabs_map[slab["parent"]] = slab

		return slabs_map

	@staticmethod
	def fetch_product_slabs(scheme_names: List[str]) -> Dict[str, Dict]:
		"""Fetch first product discount slab for each scheme"""
		if not scheme_names:
			return {}

		results = frappe.db.sql("""
			SELECT
				parent, min_qty, max_qty, min_amount, max_amount,
				apply_multiple_pricing_rules,
				free_item, free_qty, free_item_uom, same_item, is_recursive,
				recurse_for, apply_recursion_over
			FROM `tabPromotional Scheme Product Discount`
			WHERE parent IN %s AND disable = 0
			ORDER BY parent, min_amount ASC, min_qty ASC
		""", [scheme_names], as_dict=1)

		# Take first slab for each parent
		slabs_map = {}
		for slab in results:
			if slab["parent"] not in slabs_map:
				slabs_map[slab["parent"]] = slab

		return slabs_map


# ============================================================================
# Offer Builders
# ============================================================================

class OfferBuilder:
	"""Builds Offer objects from pricing rules and schemes"""

	@staticmethod
	def build_from_scheme_rule(
		rule: Dict,
		slab: Dict,
		eligibility: OfferEligibility
	) -> Offer:
		"""Build offer from promotional scheme pricing rule"""

		# Determine if auto-apply
		is_auto = 0
		if not rule.get("coupon_code_based"):
			if not slab.get("apply_multiple_pricing_rules"):
				is_auto = 1

		# Extract eligibility based on apply_on
		eligible_items = []
		eligible_item_groups = []
		eligible_brands = []

		if rule["apply_on"] == ApplyOn.ITEM_CODE:
			eligible_items = eligibility.items
		elif rule["apply_on"] == ApplyOn.ITEM_GROUP:
			eligible_item_groups = eligibility.item_groups
		elif rule["apply_on"] == ApplyOn.BRAND:
			eligible_brands = eligibility.brands

		# Determine offer type
		is_price_discount = rule.get("price_or_product_discount") == DiscountType.PRICE

		return Offer(
			name=rule["name"],
			title=rule.get("title") or rule.get("promotional_scheme") or rule["name"],
			description=rule.get("title") or rule.get("promotional_scheme") or "",
			apply_on=rule["apply_on"],
			offer="Item Price" if is_price_discount else "Give Product",
			auto=is_auto,
			coupon_based=1 if rule.get("coupon_code_based") else 0,
			min_qty=flt(slab.get("min_qty", 0)),
			max_qty=flt(slab.get("max_qty", 0)),
			min_amt=flt(slab.get("min_amount", 0)),
			max_amt=flt(slab.get("max_amount", 0)),
			discount_type=slab.get("rate_or_discount") if is_price_discount else None,
			rate=flt(slab.get("rate", 0)) if is_price_discount else 0,
			discount_amount=flt(slab.get("discount_amount", 0)) if is_price_discount else 0,
			discount_percentage=flt(slab.get("discount_percentage", 0)) if is_price_discount else 0,
			valid_from=rule.get("valid_from"),
			valid_upto=rule.get("valid_upto"),
			source=OfferSource.PROMOTIONAL_SCHEME,
			promotional_scheme=rule.get("promotional_scheme"),
			promotional_scheme_id=rule.get("promotional_scheme_id"),
			eligible_items=eligible_items,
			eligible_item_groups=eligible_item_groups,
			eligible_brands=eligible_brands,
			# Free item fields for product discounts
			free_item=slab.get("free_item") if not is_price_discount else None,
			free_qty=flt(slab.get("free_qty", 0)) if not is_price_discount else 0,
			free_item_uom=slab.get("free_item_uom") if not is_price_discount else None,
			same_item=1 if slab.get("same_item") and not is_price_discount else 0,
			is_recursive=1 if slab.get("is_recursive") and not is_price_discount else 0,
			recurse_for=flt(slab.get("recurse_for", 0)) if not is_price_discount else 0,
			apply_recursion_over=flt(slab.get("apply_recursion_over", 0)) if not is_price_discount else 0
		)

	@staticmethod
	def build_from_standalone_rule(
		rule: Dict,
		eligibility: OfferEligibility
	) -> Offer:
		"""Build offer from standalone pricing rule"""

		# Standalone rules auto-apply unless coupon-based
		is_auto = 0 if rule.get("coupon_code_based") else 1

		# Extract eligibility based on apply_on
		eligible_items = []
		eligible_item_groups = []
		eligible_brands = []

		if rule["apply_on"] == ApplyOn.ITEM_CODE:
			eligible_items = eligibility.items
		elif rule["apply_on"] == ApplyOn.ITEM_GROUP:
			eligible_item_groups = eligibility.item_groups
		elif rule["apply_on"] == ApplyOn.BRAND:
			eligible_brands = eligibility.brands

		return Offer(
			name=rule["name"],
			title=rule.get("title") or rule["name"],
			description=rule.get("title") or f"Pricing Rule: {rule['name']}",
			apply_on=rule["apply_on"],
			offer="Item Price",
			auto=is_auto,
			coupon_based=1 if rule.get("coupon_code_based") else 0,
			min_qty=flt(rule.get("min_qty", 0)),
			max_qty=flt(rule.get("max_qty", 0)),
			min_amt=flt(rule.get("min_amt", 0)),
			max_amt=flt(rule.get("max_amt", 0)),
			discount_type=rule.get("rate_or_discount"),
			rate=flt(rule.get("rate", 0)),
			discount_amount=flt(rule.get("discount_amount", 0)),
			discount_percentage=flt(rule.get("discount_percentage", 0)),
			valid_from=rule.get("valid_from"),
			valid_upto=rule.get("valid_upto"),
			source=OfferSource.PRICING_RULE,
			promotional_scheme=None,
			promotional_scheme_id=None,
			eligible_items=eligible_items,
			eligible_item_groups=eligible_item_groups,
			eligible_brands=eligible_brands
		)


# ============================================================================
# Main API Functions
# ============================================================================

@frappe.whitelist()
def get_offers(pos_profile: str) -> List[Dict]:
	"""
	Fetch all auto-applicable offers for the POS profile

	Args:
		pos_profile: POS Profile name

	Returns:
		List of offer dictionaries
	"""
	try:
		profile = frappe.get_doc("POS Profile", pos_profile)
		date = nowdate()

		offers = []

		# Get offers from promotional schemes
		scheme_offers = _get_promotional_scheme_offers(profile.company, date)
		offers.extend(scheme_offers)

		# Get standalone pricing rule offers
		standalone_offers = _get_standalone_pricing_rule_offers(profile.company, date)
		offers.extend(standalone_offers)

		return [offer.to_dict() for offer in offers]

	except Exception as e:
		frappe.log_error(f"Error fetching offers: {str(e)}", "Offers API")
		return []


def _get_promotional_scheme_offers(company: str, date: str) -> List[Offer]:
	"""Fetch offers from promotional schemes"""

	# Fetch pricing rules linked to promotional schemes
	pricing_rules = frappe.db.sql("""
		SELECT
			name, title, apply_on, selling, promotional_scheme,
			promotional_scheme_id, coupon_code_based,
			price_or_product_discount, priority, valid_from, valid_upto
		FROM `tabPricing Rule`
		WHERE
			disable = 0
			AND selling = 1
			AND promotional_scheme IS NOT NULL
			AND company = %(company)s
			AND (valid_from IS NULL OR valid_from <= %(date)s)
			AND (valid_upto IS NULL OR valid_upto >= %(date)s)
		ORDER BY priority DESC, name
	""", {"company": company, "date": date}, as_dict=1)

	if not pricing_rules:
		return []

	# Get unique scheme names
	scheme_names = list({rule["promotional_scheme"] for rule in pricing_rules})

	# Fetch all slabs and eligibility in batch
	price_slabs = SlabFetcher.fetch_price_slabs(scheme_names)
	product_slabs = SlabFetcher.fetch_product_slabs(scheme_names)
	eligibility_map = EligibilityFetcher.fetch_all(scheme_names)

	# Build offers
	offers = []
	for rule in pricing_rules:
		scheme_name = rule["promotional_scheme"]

		# Get appropriate slab
		if rule.get("price_or_product_discount") == DiscountType.PRICE:
			slab = price_slabs.get(scheme_name)
		else:
			slab = product_slabs.get(scheme_name)

		if not slab:
			continue

		eligibility = eligibility_map.get(scheme_name, OfferEligibility([], [], []))
		offer = OfferBuilder.build_from_scheme_rule(rule, slab, eligibility)
		offers.append(offer)

	return offers


def _get_standalone_pricing_rule_offers(company: str, date: str) -> List[Offer]:
	"""Fetch offers from standalone pricing rules"""

	# Fetch standalone pricing rules (not linked to schemes)
	pricing_rules = frappe.db.sql("""
		SELECT
			name, title, apply_on, selling,
			coupon_code_based, price_or_product_discount,
			rate_or_discount, rate, discount_amount, discount_percentage,
			min_qty, max_qty, min_amt, max_amt,
			priority, valid_from, valid_upto
		FROM `tabPricing Rule`
		WHERE
			disable = 0
			AND selling = 1
			AND promotional_scheme IS NULL
			AND company = %(company)s
			AND (valid_from IS NULL OR valid_from <= %(date)s)
			AND (valid_upto IS NULL OR valid_upto >= %(date)s)
			AND price_or_product_discount = %(discount_type)s
		ORDER BY priority DESC, name
	""", {"company": company, "date": date, "discount_type": DiscountType.PRICE}, as_dict=1)

	if not pricing_rules:
		return []

	# Get rule names
	rule_names = [rule["name"] for rule in pricing_rules]

	# Fetch eligibility in batch
	eligibility_map = EligibilityFetcher.fetch_all(rule_names)

	# Build offers
	offers = []
	for rule in pricing_rules:
		eligibility = eligibility_map.get(rule["name"], OfferEligibility([], [], []))
		offer = OfferBuilder.build_from_standalone_rule(rule, eligibility)
		offers.append(offer)

	return offers


# ============================================================================
# Coupon Functions
# ============================================================================

@frappe.whitelist()
def get_active_coupons(customer: str, company: str) -> List[Dict]:
	"""Get active gift card coupons for a customer"""
	if not frappe.db.table_exists("POS Coupon"):
		return []

	coupons = frappe.get_all(
		"POS Coupon",
		filters={
			"company": company,
			"coupon_type": "Gift Card",
			"customer": customer,
			"used": 0,
		},
		fields=["name", "coupon_code", "coupon_name", "valid_from", "valid_upto"],
	)

	return coupons


@frappe.whitelist()
def validate_coupon(coupon_code: str, customer: str, company: str) -> Dict:
	"""Validate a coupon code and return its details"""
	if not frappe.db.table_exists("POS Coupon"):
		return {"valid": False, "message": _("Coupons are not enabled")}

	date = getdate()

	# Fetch coupon with case-insensitive code matching
	# Note: coupon_code field is unique, so we can fetch directly
	coupon = frappe.db.get_value(
		"POS Coupon",
		{"coupon_code": coupon_code, "company": company},
		["*"],
		as_dict=1
	)

	if not coupon:
		return {"valid": False, "message": _("Invalid coupon code")}

	if coupon.disabled:
		return {"valid": False, "message": _("This coupon is disabled")}

	# Check usage limits
	if coupon.coupon_type == "Gift Card":
		if coupon.used:
			return {"valid": False, "message": _("This gift card has already been used")}
	else:
		# Promotional coupons
		if coupon.maximum_use > 0 and coupon.used >= coupon.maximum_use:
			return {"valid": False, "message": _("This coupon has reached its usage limit")}

	# Check validity dates
	if coupon.valid_from and coupon.valid_from > date:
		return {"valid": False, "message": _("This coupon is not yet valid")}

	if coupon.valid_upto and coupon.valid_upto < date:
		return {"valid": False, "message": _("This coupon has expired")}

	# Check customer restriction
	if coupon.customer and coupon.customer != customer:
		return {"valid": False, "message": _("This coupon is not valid for this customer")}

	return {
		"valid": True,
		"coupon": coupon
	}
