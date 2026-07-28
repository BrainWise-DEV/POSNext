# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

"""
Offers API - Fetches and manages promotional offers and pricing rules for POS

This module provides a clean API for retrieving promotional offers from both
Promotional Schemes and standalone Pricing Rules.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from pos_next.promotions.scope import (
	APPLY_ON_CHILD_DOCTYPE,
	SCOPE_PERCENTAGE_FIELD,
	get_item_group_with_descendants,
	get_scope_config,
)
from pos_next.api.gwp import PROMOTION_TYPE_GWP, calculate_gwp_discount_percentage

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

	items: list[str]
	item_groups: list[str]
	brands: list[str]


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
	discount_type: str | None
	rate: float
	discount_amount: float
	discount_percentage: float
	apply_discount_on_price: str | None
	min_or_max_discount_qty_limit: int
	valid_from: str | None
	valid_upto: str | None
	source: str
	promotional_scheme: str | None
	promotional_scheme_id: str | None
	eligible_items: list[str]
	eligible_item_groups: list[str]
	eligible_brands: list[str]
	# Free item fields for product discounts
	free_item: str | None = None
	free_qty: float = 0
	free_item_uom: str | None = None
	same_item: int = 0  # 1 if free item should be same as purchased item
	is_recursive: int = 0  # 1 if offer applies recursively (e.g., buy 2 get 1 free for every 2)
	recurse_for: float = 0  # Give free item for every N quantity (used when is_recursive=1)
	apply_recursion_over: float = 0  # Qty for which recursion isn't applicable
	one_time_per_customer: int = 0  # 1 if each customer may redeem this offer only once
	promotion_type: str | None = None
	# Accumulative discounts. `accumulative_scopes` is a list of
	# {values: [...], discount_percentage: n} — one entry per scope row, with
	# item groups pre-expanded to descendants and template items to variants so
	# the offline engine can match by plain lookup instead of walking trees.
	# The line discount is the sum of every entry represented in the cart,
	# capped by `max_accumulated_discount_percentage`.
	accumulative_scope_field: str | None = None
	accumulative_scopes: list[dict] | None = None
	max_accumulated_discount_percentage: float = 0
	min_scopes_required: int = 1
	gwp_paid_qty_basis: str | None = None

	def to_dict(self) -> dict:
		"""Convert to dictionary for API response"""
		return asdict(self)


# ============================================================================
# Database Query Helpers
# ============================================================================


class EligibilityFetcher:
	"""Fetches eligibility criteria for pricing rules/schemes in bulk"""

	@staticmethod
	def fetch_all(parent_names: list[str]) -> dict[str, OfferEligibility]:
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
				brands=brands_map.get(parent, []),
			)

		return eligibility

	@staticmethod
	def _fetch_items(parent_names: list[str]) -> dict[str, list[str]]:
		"""
		Fetch item codes for given parents, expanding template items to include variants.

		When a pricing rule is created for a template item (has_variants=1), this method
		automatically includes all its variant items in the eligible items list.
		This ensures offers work correctly when variants are added to cart.
		"""
		results = frappe.db.sql(
			"""
			SELECT parent, item_code
			FROM `tabPricing Rule Item Code`
			WHERE parent IN %s
		""",
			[parent_names],
			as_dict=1,
		)

		if not results:
			return {}

		# Collect all unique item codes
		all_item_codes = list({row["item_code"] for row in results})

		# Find which items are templates (have variants)
		template_items = frappe.get_all(
			"Item", filters={"name": ["in", all_item_codes], "has_variants": 1}, pluck="name"
		)

		# Fetch variants for all template items in one query
		variants_map = {}
		if template_items:
			variants = frappe.get_all(
				"Item",
				filters={"variant_of": ["in", template_items], "disabled": 0},
				fields=["name", "variant_of"],
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
	def _fetch_item_groups(parent_names: list[str]) -> dict[str, list[str]]:
		"""Fetch item groups for given parents, expanded to include descendants.

		Item groups match by lineage everywhere on the server — ERPNext's engine and
		``promotions/scope.py`` both treat a rule on ``Electronics`` as covering an
		item in ``Electronics > Phones``. The client, however, compares a cart line's
		``item_group`` against this list with a plain ``includes()``. Returning only
		the literal rows would make the client judge such an offer ineligible and
		never send it, even though the server would have applied it.
		"""
		results = frappe.db.sql(
			"""
			SELECT parent, item_group
			FROM `tabPricing Rule Item Group`
			WHERE parent IN %s
		""",
			[parent_names],
			as_dict=1,
		)

		groups_map: dict[str, list[str]] = {}
		for row in results:
			expanded = groups_map.setdefault(row["parent"], [])
			for group in get_item_group_with_descendants(row["item_group"]):
				if group not in expanded:
					expanded.append(group)
		return groups_map

	@staticmethod
	def _fetch_brands(parent_names: list[str]) -> dict[str, list[str]]:
		"""Fetch brands for given parents"""
		results = frappe.db.sql(
			"""
			SELECT parent, brand
			FROM `tabPricing Rule Brand`
			WHERE parent IN %s
		""",
			[parent_names],
			as_dict=1,
		)

		brands_map = {}
		for row in results:
			brands_map.setdefault(row["parent"], []).append(row["brand"])
		return brands_map


class AccumulativeFetcher:
	"""Fetches Accumulative config so the offline engine can reproduce it.

	Both scheme-generated and standalone offers are Pricing Rules, so one batch
	lookup keyed by rule name covers both. Scope values are expanded here — item
	groups to their descendants, template items to their variants — which keeps
	the client a plain lookup with no tree walking.
	"""

	MODE = "Accumulative"

	@staticmethod
	def fetch(rule_names: list[str]) -> dict[str, dict]:
		"""Return ``{rule_name: {field, scopes, cap, min_scopes}}`` for Accumulative rules."""
		if not rule_names:
			return {}
		if not frappe.db.has_column("Pricing Rule", "apply_discount_on_price"):
			return {}
		if not frappe.db.has_column("Pricing Rule", "min_scopes_required"):
			return {}

		rules = frappe.get_all(
			"Pricing Rule",
			filters={
				"name": ["in", rule_names],
				"apply_discount_on_price": AccumulativeFetcher.MODE,
			},
			fields=[
				"name",
				"apply_on",
				"max_accumulated_discount_percentage",
				"min_scopes_required",
			],
		)
		if not rules:
			return {}

		by_apply_on: dict[str, list[str]] = {}
		for rule in rules:
			if get_scope_config(rule.apply_on):
				by_apply_on.setdefault(rule.apply_on, []).append(rule.name)

		rows_by_rule = AccumulativeFetcher._fetch_scope_rows(by_apply_on)

		config = {}
		for rule in rules:
			scopes = rows_by_rule.get(rule.name)
			if not scopes:
				continue
			_, row_field = get_scope_config(rule.apply_on)
			config[rule.name] = {
				"field": row_field,
				"scopes": scopes,
				"cap": flt(rule.max_accumulated_discount_percentage),
				"min_scopes": max(cint(rule.min_scopes_required) or 1, 1),
			}
		return config

	@staticmethod
	def _fetch_scope_rows(by_apply_on: dict[str, list[str]]) -> dict[str, list[dict]]:
		rows_by_rule: dict[str, list[dict]] = {}

		for apply_on, names in by_apply_on.items():
			child_doctype = APPLY_ON_CHILD_DOCTYPE[apply_on]
			if not frappe.db.has_column(child_doctype, SCOPE_PERCENTAGE_FIELD):
				continue
			_, row_field = get_scope_config(apply_on)

			rows = frappe.get_all(
				child_doctype,
				filters={"parent": ["in", names], "parenttype": "Pricing Rule"},
				fields=["parent", row_field, SCOPE_PERCENTAGE_FIELD],
				order_by="idx asc",
			)

			for row in rows:
				percentage = flt(row.get(SCOPE_PERCENTAGE_FIELD))
				value = row.get(row_field)
				if percentage <= 0 or not value:
					continue
				rows_by_rule.setdefault(row["parent"], []).append(
					{
						"values": AccumulativeFetcher._expand(row_field, value),
						"discount_percentage": percentage,
					}
				)

		return rows_by_rule

	@staticmethod
	def _expand(row_field: str, value: str) -> list[str]:
		"""Every cart value this scope row covers."""
		if row_field == "item_group":
			return list(get_item_group_with_descendants(value))
		if row_field == "item_code":
			variants = frappe.get_all(
				"Item", filters={"variant_of": value, "disabled": 0}, pluck="name"
			)
			return [value, *variants]
		return [value]


class SlabFetcher:
	"""Fetches discount slabs for promotional schemes"""

	@staticmethod
	def fetch_price_slabs(scheme_names: list[str]) -> dict[str, dict]:
		"""Fetch first price discount slab for each scheme"""
		if not scheme_names:
			return {}

		# Optional POS Next custom columns — tolerate sites that have not migrated yet
		optional_cols = []
		if frappe.db.has_column("Promotional Scheme Price Discount", "apply_discount_on_price"):
			optional_cols.append("apply_discount_on_price")
		if frappe.db.has_column("Promotional Scheme Price Discount", "min_or_max_discount_qty_limit"):
			optional_cols.append("min_or_max_discount_qty_limit")
		optional_sql = (", " + ", ".join(optional_cols)) if optional_cols else ""

		results = frappe.db.sql(
			f"""
			SELECT
				parent, min_qty, max_qty, min_amount, max_amount,
				rate_or_discount, rate, discount_amount, discount_percentage,
				apply_multiple_pricing_rules{optional_sql}
			FROM `tabPromotional Scheme Price Discount`
			WHERE parent IN %s AND disable = 0
			ORDER BY parent, min_amount ASC, min_qty ASC
			""",
			[scheme_names],
			as_dict=1,
		)

		# Take first slab for each parent
		slabs_map = {}
		for slab in results:
			if slab["parent"] not in slabs_map:
				slabs_map[slab["parent"]] = slab

		return slabs_map

	@staticmethod
	def fetch_product_slabs(scheme_names: list[str]) -> dict[str, dict]:
		"""Fetch first product discount slab for each scheme"""
		if not scheme_names:
			return {}

		optional_cols = []
		if frappe.db.has_column("Promotional Scheme Product Discount", "gwp_paid_qty_basis"):
			optional_cols.append("gwp_paid_qty_basis")
		optional_sql = (", " + ", ".join(optional_cols)) if optional_cols else ""

		results = frappe.db.sql(
			f"""
			SELECT
				parent, min_qty, max_qty, min_amount, max_amount,
				apply_multiple_pricing_rules,
				free_item, free_qty, free_item_uom, same_item, is_recursive,
				recurse_for, apply_recursion_over{optional_sql}
			FROM `tabPromotional Scheme Product Discount`
			WHERE parent IN %s AND disable = 0
			ORDER BY parent, min_amount ASC, min_qty ASC
		""",
			[scheme_names],
			as_dict=1,
		)

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
	def build_from_scheme_rule(rule: dict, slab: dict, eligibility: OfferEligibility) -> Offer:
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
		promotion_type = rule.get("promotion_type") or None
		gwp_discount_percentage = 0
		if promotion_type == PROMOTION_TYPE_GWP and not is_price_discount:
			gwp_discount_percentage = calculate_gwp_discount_percentage(
				flt(slab.get("free_qty", 0)),
				flt(slab.get("min_qty", 0)),
			)

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
			discount_percentage=(
				flt(slab.get("discount_percentage", 0))
				if is_price_discount
				else gwp_discount_percentage
			),
			apply_discount_on_price=(slab.get("apply_discount_on_price") if is_price_discount else None),
			min_or_max_discount_qty_limit=(
				cint(slab.get("min_or_max_discount_qty_limit", 0)) if is_price_discount else 0
			),
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
			apply_recursion_over=flt(slab.get("apply_recursion_over", 0)) if not is_price_discount else 0,
			one_time_per_customer=1 if rule.get("one_time_per_customer") else 0,
			promotion_type=promotion_type,
			gwp_paid_qty_basis=slab.get("gwp_paid_qty_basis"),
		)

	@staticmethod
	def build_from_standalone_rule(rule: dict, eligibility: OfferEligibility) -> Offer:
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
			apply_discount_on_price=rule.get("apply_discount_on_price"),
			min_or_max_discount_qty_limit=cint(rule.get("min_or_max_discount_qty_limit", 0)),
			valid_from=rule.get("valid_from"),
			valid_upto=rule.get("valid_upto"),
			source=OfferSource.PRICING_RULE,
			promotional_scheme=None,
			promotional_scheme_id=None,
			eligible_items=eligible_items,
			eligible_item_groups=eligible_item_groups,
			eligible_brands=eligible_brands,
			one_time_per_customer=1 if rule.get("one_time_per_customer") else 0,
			promotion_type=rule.get("promotion_type") or None,
		)


# ============================================================================
# Main API Functions
# ============================================================================


@frappe.whitelist()
def get_offers(pos_profile: str) -> list[dict]:
	"""
	Fetch all auto-applicable offers for the POS profile

	Args:
		pos_profile: POS Profile name

	Returns:
		List of offer dictionaries
	"""
	try:
		profile = frappe.get_doc("POS Profile", pos_profile)

		# Respect POS Profile's ignore_pricing_rule setting
		if profile.ignore_pricing_rule:
			return []

		date = nowdate()

		offers = []

		# Get offers from promotional schemes
		scheme_offers = _get_promotional_scheme_offers(profile.company, date)
		offers.extend(scheme_offers)

		# Get standalone pricing rule offers
		standalone_offers = _get_standalone_pricing_rule_offers(profile.company, date)
		offers.extend(standalone_offers)

		_attach_accumulative_config(offers)

		return [offer.to_dict() for offer in offers]

	except Exception as e:
		frappe.log_error(f"Error fetching offers: {e!s}", "Offers API")
		return []


@frappe.whitelist()
def get_customer_one_time_redemptions(customer: str | None = None) -> list[str]:
	"""Return the Pricing Rule names a customer has already redeemed once.

	Used by the POS frontend to enforce one-time-per-customer offers OFFLINE:
	the cart caches this list when a customer is selected (while online) so the
	offline offer engine can mirror the server-side gate in ``apply_offers``.
	"""
	if not customer or not frappe.db.table_exists("One Time Customer Offer Usage"):
		return []

	return frappe.get_all(
		"One Time Customer Offer Usage",
		filters={"customer": customer},
		pluck="pricing_rule",
	)


def _attach_accumulative_config(offers: list[Offer]) -> None:
	"""Stamp Accumulative scope data onto the offers that use it.

	Done as one batch pass over both offer sources rather than inside each
	builder, since scheme-generated and standalone offers are both Pricing Rules
	and share the same lookup.
	"""
	if not offers:
		return

	config = AccumulativeFetcher.fetch([offer.name for offer in offers])
	if not config:
		return

	for offer in offers:
		entry = config.get(offer.name)
		if not entry:
			continue
		offer.apply_discount_on_price = AccumulativeFetcher.MODE
		offer.accumulative_scope_field = entry["field"]
		offer.accumulative_scopes = entry["scopes"]
		offer.max_accumulated_discount_percentage = entry["cap"]
		offer.min_scopes_required = entry["min_scopes"]


def _get_promotional_scheme_offers(company: str, date: str) -> list[Offer]:
	"""Fetch offers from promotional schemes"""

	# Fetch pricing rules linked to promotional schemes
	pricing_rules = frappe.db.sql(
		"""
		SELECT
			name, title, apply_on, selling, promotional_scheme,
			promotional_scheme_id, coupon_code_based, one_time_per_customer,
			price_or_product_discount, priority, valid_from, valid_upto,
			promotion_type
		FROM `tabPricing Rule`
		WHERE
			disable = 0
			AND selling = 1
			AND promotional_scheme IS NOT NULL
			AND company = %(company)s
			AND (valid_from IS NULL OR valid_from <= %(date)s)
			AND (valid_upto IS NULL OR valid_upto >= %(date)s)
		ORDER BY priority DESC, name
	""",
		{"company": company, "date": date},
		as_dict=1,
	)

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


def _get_standalone_pricing_rule_offers(company: str, date: str) -> list[Offer]:
	"""Fetch offers from standalone pricing rules"""

	# Fetch standalone pricing rules (not linked to schemes)
	pricing_rules = frappe.db.sql(
		"""
		SELECT
			name, title, apply_on, selling,
			coupon_code_based, one_time_per_customer, price_or_product_discount,
			rate_or_discount, rate, discount_amount, discount_percentage,
			apply_discount_on_price, min_or_max_discount_qty_limit,
			min_qty, max_qty, min_amt, max_amt,
			priority, valid_from, valid_upto, promotion_type
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
	""",
		{"company": company, "date": date, "discount_type": DiscountType.PRICE},
		as_dict=1,
	)

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


@frappe.whitelist()
def item_has_active_promotion(
	item_code: str, company: str | None = None, qty: float | None = None
) -> dict:
	"""Check if an item currently qualifies for an active selling promotion.

	Locks manual discounts only when ``qty`` falls within a matching rule's
	min_qty / max_qty (e.g. Buy 2–5 Get 1). Qty outside that range does not lock.
	"""
	if not item_code:
		return {"has_promotion": False}

	qty = flt(qty)
	# Without a qty we cannot know if thresholds are met — do not lock
	if qty <= 0:
		return {"has_promotion": False}

	date = nowdate()
	values: dict = {"item_code": item_code, "date": date}
	company_filter = ""
	if company:
		company_filter = "AND (pr.company IS NULL OR pr.company = '' OR pr.company = %(company)s)"
		values["company"] = company

	qty_filter = """
		AND (IFNULL(pr.min_qty, 0) = 0 OR pr.min_qty <= %(qty)s)
		AND (IFNULL(pr.max_qty, 0) = 0 OR pr.max_qty >= %(qty)s)
	"""
	values["qty"] = qty

	# Direct item-code pricing rules (includes rules generated from Promotional Schemes)
	row = frappe.db.sql(
		f"""
		SELECT pr.name, pr.promotional_scheme, pr.min_qty, pr.max_qty
		FROM `tabPricing Rule` pr
		INNER JOIN `tabPricing Rule Item Code` pri
			ON pri.parent = pr.name AND pri.parenttype = 'Pricing Rule'
		WHERE pri.item_code = %(item_code)s
			AND pr.disable = 0
			AND pr.selling = 1
			AND IFNULL(pr.coupon_code_based, 0) = 0
			AND (pr.valid_from IS NULL OR pr.valid_from <= %(date)s)
			AND (pr.valid_upto IS NULL OR pr.valid_upto >= %(date)s)
			{company_filter}
			{qty_filter}
		LIMIT 1
		""",
		values,
		as_dict=1,
	)
	if row:
		return {
			"has_promotion": True,
			"pricing_rule": row[0].name,
			"promotional_scheme": row[0].promotional_scheme,
			"min_qty": row[0].min_qty,
			"max_qty": row[0].max_qty,
		}

	item = frappe.db.get_value("Item", item_code, ["item_group", "brand"], as_dict=1)
	if not item:
		return {"has_promotion": False}

	# Item Group rules
	if item.item_group:
		values["item_group"] = item.item_group
		row = frappe.db.sql(
			f"""
			SELECT pr.name, pr.promotional_scheme, pr.min_qty, pr.max_qty
			FROM `tabPricing Rule` pr
			INNER JOIN `tabPricing Rule Item Group` prg
				ON prg.parent = pr.name AND prg.parenttype = 'Pricing Rule'
			WHERE (prg.item_group = %(item_group)s OR prg.item_group = 'All Item Groups')
				AND pr.disable = 0
				AND pr.selling = 1
				AND pr.apply_on = 'Item Group'
				AND IFNULL(pr.coupon_code_based, 0) = 0
				AND (pr.valid_from IS NULL OR pr.valid_from <= %(date)s)
				AND (pr.valid_upto IS NULL OR pr.valid_upto >= %(date)s)
				{company_filter}
				{qty_filter}
			LIMIT 1
			""",
			values,
			as_dict=1,
		)
		if row:
			return {
				"has_promotion": True,
				"pricing_rule": row[0].name,
				"promotional_scheme": row[0].promotional_scheme,
				"min_qty": row[0].min_qty,
				"max_qty": row[0].max_qty,
			}

	# Brand rules
	if item.brand:
		values["brand"] = item.brand
		row = frappe.db.sql(
			f"""
			SELECT pr.name, pr.promotional_scheme, pr.min_qty, pr.max_qty
			FROM `tabPricing Rule` pr
			INNER JOIN `tabPricing Rule Brand` prb
				ON prb.parent = pr.name AND prb.parenttype = 'Pricing Rule'
			WHERE prb.brand = %(brand)s
				AND pr.disable = 0
				AND pr.selling = 1
				AND pr.apply_on = 'Brand'
				AND IFNULL(pr.coupon_code_based, 0) = 0
				AND (pr.valid_from IS NULL OR pr.valid_from <= %(date)s)
				AND (pr.valid_upto IS NULL OR pr.valid_upto >= %(date)s)
				{company_filter}
				{qty_filter}
			LIMIT 1
			""",
			values,
			as_dict=1,
		)
		if row:
			return {
				"has_promotion": True,
				"pricing_rule": row[0].name,
				"promotional_scheme": row[0].promotional_scheme,
				"min_qty": row[0].min_qty,
				"max_qty": row[0].max_qty,
			}

	return {"has_promotion": False}


# ============================================================================
# Coupon Functions
# ============================================================================


@frappe.whitelist()
def get_active_coupons(customer: str | None = None, company: str | None = None) -> list[dict]:
	"""Get active gift card coupons for a customer"""
	if not customer or not company:
		return []

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
def validate_coupon(
	coupon_code: str, customer: str | None = None, company: str | None = None, items=None
) -> dict:
	"""Validate a coupon code and optionally compute line-level discounts for cart items."""
	if not customer:
		return {"valid": False, "message": _("Customer is required")}
	if not company:
		return {"valid": False, "message": _("Company is required")}

	if not frappe.db.table_exists("POS Coupon"):
		return {"valid": False, "message": _("Coupons are not enabled")}

	import json

	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
		apply_coupon_to_items,
		check_coupon_code,
	)

	if isinstance(items, str):
		items = json.loads(items) if items else None

	result = check_coupon_code(coupon_code, customer=customer, company=company)
	if not result.get("valid") or not result.get("coupon"):
		return {"valid": False, "message": result.get("msg") or _("Invalid coupon code")}

	coupon = result["coupon"]
	coupon_dict = coupon.as_dict()

	response = {
		"valid": True,
		"coupon": coupon_dict,
		"line_updates": [],
		"eligible_item_codes": [],
		"total_discount": 0,
	}

	if items is not None:
		apply_result = apply_coupon_to_items(coupon, items)
		if not apply_result.get("valid"):
			return {
				"valid": False,
				"message": apply_result.get("message") or _("No eligible items for this coupon"),
				"coupon": coupon_dict,
				"line_updates": [],
				"eligible_item_codes": apply_result.get("eligible_item_codes") or [],
				"total_discount": 0,
			}
		response.update(
			{
				"line_updates": apply_result.get("line_updates") or [],
				"eligible_item_codes": apply_result.get("eligible_item_codes") or [],
				"total_discount": apply_result.get("total_discount") or 0,
				"eligible_subtotal": apply_result.get("eligible_subtotal") or 0,
				"message": apply_result.get("message"),
			}
		)

	return response


@frappe.whitelist()
def calculate_coupon_discount(
	coupon_code: str, invoice_data, customer: str | None = None, company: str | None = None
):
	"""Validate and calculate coupon discount with item-level exclusion support."""
	import json

	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import apply_coupon_discount

	if isinstance(invoice_data, str):
		invoice_data = json.loads(invoice_data or "{}")

	invoice = frappe._dict(invoice_data or {})
	items = invoice.get("items") or []
	company = company or invoice.get("company")
	customer = customer or invoice.get("customer")

	validation = validate_coupon(coupon_code, customer, company, items=items)
	if not validation.get("valid"):
		return validation

	coupon = frappe._dict(validation.get("coupon") or {})

	grand_total = flt(invoice.get("grand_total") or 0)
	net_total = flt(invoice.get("net_total") or 0)
	tax_amount = flt(invoice.get("total_taxes_and_charges") or invoice.get("tax_amount") or 0)

	if not grand_total and items:
		from pos_next.api.promotion_exclusions import (
			PROMOTION_TARGET_COUPON,
			get_eligible_subtotal,
			get_excluded_subtotal,
		)
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import _get_excluded_brands

		excluded_brands = _get_excluded_brands(coupon)
		subtotal_kwargs = {
			"promotion_target": PROMOTION_TARGET_COUPON,
			"excluded_brands": excluded_brands,
		}
		net_total = get_eligible_subtotal(items, **subtotal_kwargs) + get_excluded_subtotal(
			items, **subtotal_kwargs
		)
		grand_total = net_total + tax_amount

	if not net_total and items:
		from pos_next.api.promotion_exclusions import (
			PROMOTION_TARGET_COUPON,
			get_eligible_subtotal,
			get_excluded_subtotal,
		)
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import _get_excluded_brands

		excluded_brands = _get_excluded_brands(coupon)
		subtotal_kwargs = {
			"promotion_target": PROMOTION_TARGET_COUPON,
			"excluded_brands": excluded_brands,
		}
		net_total = get_eligible_subtotal(items, **subtotal_kwargs) + get_excluded_subtotal(
			items, **subtotal_kwargs
		)

	result = apply_coupon_discount(
		coupon,
		cart_total=grand_total or net_total,
		net_total=net_total,
		items=items,
		tax_amount=tax_amount,
	)

	return {
		"valid": result.get("valid", False),
		"message": result.get("message"),
		"discount": flt(result.get("discount") or 0),
		"discount_type": result.get("discount_type"),
		"discount_percentage": result.get("discount_percentage"),
		"apply_on": result.get("apply_on"),
		"eligible_subtotal": flt(result.get("eligible_subtotal") or 0),
		"excluded_subtotal": flt(result.get("excluded_subtotal") or 0),
		"coupon": coupon,
	}
