# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
import math
from functools import lru_cache

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.stock.doctype.batch.batch import get_batch_no, get_batch_qty
from frappe import _
from frappe.utils import (
	cint,
	cstr,
	flt,
	get_datetime,
	getdate,
	nowdate,
	nowtime,
	round_based_on_smallest_currency_fraction,
)

from pos_next.api.pricing import _draft_pricing_matches_db, enforce_server_side_pricing
from pos_next.api.security import ensure_desk_user, ensure_pos_user, is_pos_supervisor
from pos_next.utils import log_error_without_telemetry, validate_pos_profile_access

ALLOWED_RETURN_DOCTYPES = frozenset({"Sales Invoice", "POS Invoice"})

ALLOWED_INVOICE_FIELDS = frozenset(
	{
		"name",
		"doctype",
		"pos_profile",
		"posa_pos_opening_shift",
		"customer",
		"customer_name",
		"customer_group",
		"territory",
		"customer_address",
		"shipping_address_name",
		"contact_person",
		"company",
		"currency",
		"posting_date",
		"posting_time",
		"set_posting_time",
		"due_date",
		"delivery_date",
		"transaction_date",
		"order_type",
		"po_no",
		"po_date",
		"items",
		"payments",
		"taxes",
		"taxes_and_charges",
		"tax_category",
		"sales_team",
		"discount_amount",
		"additional_discount_percentage",
		"apply_discount_on",
		"coupon_code",
		"is_pos",
		"update_stock",
		"set_warehouse",
		"ignore_pricing_rule",
		"disable_rounded_total",
		"rounded_total",
		"base_rounded_total",
		"naming_series",
		"is_return",
		"return_against",
		"update_outstanding_for_self",
		"receivable_account",
		"change_amount",
		"write_off_amount",
		"offline_id",
		"idempotency_key",
		"idempotency_doctype",
		"add_to_customer_balance",
		"is_credit_sale",
		"redeemed_customer_credit",
		"customer_credit_dict",
		"authorization_token",
		"posa_notes",
		"remarks",
		"selling_price_list",
		"price_list_currency",
		"conversion_rate",
		"plc_conversion_rate",
		"posa_is_printed",
		"loyalty_points",
		"loyalty_amount",
		"redeem_loyalty_points",
		"loyalty_program",
		"loyalty_redemption_account",
		"loyalty_redemption_cost_center",
		"posa_offers",
		"posa_coupons",
		"custom_sales_person",
		"custom_pos_invoice_level_sales_team",
		"custom_pos_referral_code",
		"referral_code",
	}
)

ALLOWED_INVOICE_ITEM_FIELDS = frozenset(
	{
		"item_code",
		"item_name",
		"item_group",
		"brand",
		"description",
		"qty",
		"stock_qty",
		"rate",
		"price_list_rate",
		"uom",
		"stock_uom",
		"conversion_factor",
		"warehouse",
		"delivery_date",
		"batch_no",
		"serial_no",
		"use_serial_batch_fields",
		"discount_percentage",
		"discount_amount",
		"discount_source",
		"is_already_discounted",
		"is_accumulative_discount",
		"pricing_rules",
		"is_rate_manually_edited",
		"original_rate",
		"is_free_item",
		"posnext_coupon_code",
		"posnext_coupon_discount",
		"posnext_coupon_share",
		"posnext_discount_source",
		"posnext_fnf_percentage",
		"posnext_fnf_program",
		"posnext_fnf_replaced_discount",
		"sales_person",
		"sales_invoice_item",
		"item_tax_template",
		"posa_row_id",
		"posa_offer_applied",
		"posa_is_offer",
		"posa_is_replace",
		"posa_notes",
		"grant_commission",
	}
)

ALLOWED_INVOICE_PAYMENT_FIELDS = frozenset(
	{
		"mode_of_payment",
		"amount",
		"type",
		"default",
	}
)

ALLOWED_SALES_TEAM_FIELDS = frozenset(
	{
		"sales_person",
		"allocated_percentage",
		"commission_rate",
	}
)

ALLOWED_INVOICE_TAX_FIELDS = frozenset(
	{
		"charge_type",
		"account_head",
		"description",
		"rate",
		"tax_amount",
		"included_in_print_rate",
		"cost_center",
		"row_id",
	}
)

# ==========================================
# Constants for field names (avoid typos and enable refactoring)
# ==========================================
FIELD_IS_RATE_MANUALLY_EDITED = "is_rate_manually_edited"
FIELD_ORIGINAL_RATE = "original_rate"
FIELD_PRICE_LIST_RATE = "price_list_rate"
FIELD_RATE = "rate"
FIELD_ITEM_CODE = "item_code"
FIELD_DISCOUNT_PERCENTAGE = "discount_percentage"
FIELD_ALLOW_USER_TO_EDIT_RATE = "allow_user_to_edit_rate"
FIELD_MAX_DISCOUNT_ALLOWED = "max_discount_allowed"
FIELD_DISABLE_ROUNDED_TOTAL = "disable_rounded_total"
FIELD_ALLOW_NEGATIVE_STOCK = "allow_negative_stock"

# Doctypes
DOCTYPE_SALES_INVOICE = "Sales Invoice"
DOCTYPE_SALES_ORDER = "Sales Order"
DOCTYPE_POS_SETTINGS = "POS Settings"
DOCTYPE_POS_PROFILE = "POS Profile"
DOCTYPE_COMMENT = "Comment"
# Document types update_invoice / submit_invoice may create or change.
POS_DOCUMENT_DOCTYPES = frozenset({DOCTYPE_SALES_INVOICE, "Sales Order"})


try:
	from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
		apply_pricing_rule as erpnext_apply_pricing_rule,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		apply_pricing_rule_on_transaction as erpnext_apply_pricing_rule_on_transaction,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		get_applied_pricing_rules as erpnext_get_applied_pricing_rules,
	)
except Exception:  # pragma: no cover - ERPNext not installed in some environments
	erpnext_apply_pricing_rule = None
	erpnext_get_applied_pricing_rules = None
	erpnext_apply_pricing_rule_on_transaction = None

# ERPNext's rule lookups the one-time offer check matches redeemed rules with
# (Ruling 111/113). Without them that check fails closed (``_one_time_lookup_missing``).
try:
	from erpnext.accounts.doctype.pricing_rule.utils import (
		_get_pricing_rules as erpnext_get_item_pricing_rules,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		filter_pricing_rule_based_on_condition as erpnext_filter_pricing_rule_based_on_condition,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		filter_pricing_rules_for_qty_amount as erpnext_filter_pricing_rules_for_qty_amount,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		get_other_conditions as erpnext_get_other_conditions,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		get_pricing_rule_items as erpnext_get_pricing_rule_items,
	)
	from erpnext.accounts.doctype.pricing_rule.utils import (
		get_pricing_rules as erpnext_get_pricing_rules,
	)
except Exception:  # pragma: no cover
	erpnext_get_pricing_rules = None
	erpnext_get_pricing_rule_items = None
	erpnext_get_item_pricing_rules = None
	erpnext_filter_pricing_rule_based_on_condition = None
	erpnext_filter_pricing_rules_for_qty_amount = None
	erpnext_get_other_conditions = None


# ==========================================
# Helper Functions
# ==========================================


def calculate_price_list_rate(item_rate, discount_pct, current_price_list_rate):
	"""
	Calculate price_list_rate from discounted rate and discount percentage.

	Formula: rate = price_list_rate * (1 - discount_percentage/100)
	Reverse: price_list_rate = rate / (1 - discount_percentage/100)

	Args:
	    item_rate: The current item rate (after discount)
	    discount_pct: The discount percentage (0-100)
	    current_price_list_rate: The existing price_list_rate if any

	Returns:
	    float: The calculated price_list_rate
	"""
	# Early exit: no discount applied
	if discount_pct <= 0 or discount_pct >= 100:
		return current_price_list_rate if current_price_list_rate else item_rate

	# Reverse-calculate price_list_rate from discounted rate
	if item_rate > 0:
		discount_multiplier = 1 - discount_pct / 100
		return item_rate / discount_multiplier

	return current_price_list_rate if current_price_list_rate else item_rate


def log_manual_rate_edit(item, invoice_name, user=None):
	"""
	Create an audit log entry for manual rate edits.

	This function creates a Comment on the Sales Invoice documenting the rate change.
	It should only be called ONCE per item, after the invoice is successfully submitted.

	Args:
	    item: The item dict/object with rate information. Must contain:
	        - is_rate_manually_edited: Flag indicating manual edit (1 or 0)
	        - item_code: The item code
	        - rate: The new/edited rate
	        - original_rate: The original price before edit (or price_list_rate as fallback)
	    invoice_name: The Sales Invoice document name
	    user: Optional user who made the edit (defaults to session user)

	Returns:
	    None
	"""
	# Only log if rate was manually edited
	if not cint(item.get(FIELD_IS_RATE_MANUALLY_EDITED)):
		return

	user = user or frappe.session.user
	item_code = item.get(FIELD_ITEM_CODE)
	original_rate = flt(item.get(FIELD_ORIGINAL_RATE) or item.get(FIELD_PRICE_LIST_RATE) or 0)
	new_rate = flt(item.get(FIELD_RATE) or 0)

	# Skip logging if rates are the same (no actual change)
	if original_rate == new_rate:
		return

	# Calculate discount/markup percentage for logging
	change_pct = 0
	change_type = "reduction"
	if original_rate > 0:
		change_pct = round(abs((original_rate - new_rate) / original_rate) * 100, 2)
		if new_rate > original_rate:
			change_type = "increase"

	# Create audit comment on the invoice
	frappe.get_doc(
		{
			"doctype": DOCTYPE_COMMENT,
			"comment_type": "Comment",
			"reference_doctype": DOCTYPE_SALES_INVOICE,
			"reference_name": invoice_name,
			"content": _(
				"Manual rate edit by {user}: Item {item_code} rate changed from {original} to {new} ({change_pct}% {change_type})"
			).format(
				user=user,
				item_code=item_code,
				original=frappe.format_value(original_rate, {"fieldtype": "Currency"}),
				new=frappe.format_value(new_rate, {"fieldtype": "Currency"}),
				change_pct=change_pct,
				change_type=change_type,
			),
		}
	).insert(ignore_permissions=True)


def standardize_pricing_rules(items):
	"""
	Standardize pricing_rules field on invoice items.
	ERPNext expects a comma-separated string, but frontend/offline may send:
	- Python list: ["PRLE-0001", "PRLE-0002"]
	- JSON string: '["PRLE-0001"]' or '[\\n "PRLE-0001"\\n]'

	Args:
	    items: List of item dicts to standardize (modified in place)
	"""
	for item in items or []:
		pricing_rules = item.get("pricing_rules")
		if not pricing_rules:
			continue

		item["pricing_rules"] = _pricing_rule_to_string(pricing_rules)


def _pricing_rule_to_string(value):
	"""
	Convert pricing_rules value to comma-separated string.
	Returns empty string if value is invalid/unparseable.
	"""
	if not value:
		return ""

	# Already a list - join it
	if isinstance(value, list):
		return ",".join(str(r) for r in value if r)

	# Must be a string at this point
	if not isinstance(value, str):
		return ""

	stripped = value.strip()

	# Not JSON-like - return as-is (already a string like "PRLE-0001,PRLE-0002")
	if not stripped.startswith("["):
		return stripped

	# Try to parse JSON array
	try:
		parsed = json.loads(stripped)
		if isinstance(parsed, list):
			return ",".join(str(r) for r in parsed if r)
	except (json.JSONDecodeError, TypeError, ValueError):
		# Malformed JSON that looks like array - clear it to prevent issues
		frappe.log_error(f"Invalid pricing_rules JSON: {stripped[:100]}", "Pricing Rules Normalization")
		return ""

	return ""


def _rule_names(pricing_rules) -> list[str]:
	"""Pricing Rule names in a row's ``pricing_rules`` (comma list or JSON list)."""
	if erpnext_get_applied_pricing_rules:
		return [r for r in erpnext_get_applied_pricing_rules(pricing_rules) or [] if r]
	return [r.strip() for r in str(pricing_rules).split(",") if r.strip()]


def _keep_gift_rule_names(items) -> None:
	"""Free rows keep only names of existing product-discount (gift) Pricing Rules.

	Forged, unknown or price-discount names are dropped; a row left with none gets
	a blank ``pricing_rules``. A row made free by a Price rule the server confirmed
	(``flags.pos_backing_rule``, see ``_check_free_rows_backed``) keeps that rule.
	"""
	free_rows = [
		row
		for row in items
		if cint(row.get("is_free_item")) and row.get("pricing_rules") and not row.flags.pos_backing_rule
	]
	if not free_rows:
		return
	names = {name for row in free_rows for name in _rule_names(row.pricing_rules)}
	gift_rules = set(
		frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", list(names)], "price_or_product_discount": "Product"},
			pluck="name",
		)
	)
	for row in free_rows:
		row.pricing_rules = ",".join(name for name in _rule_names(row.pricing_rules) if name in gift_rules)


def _reset_row_pricing_rules(items) -> set[str]:
	"""Blank ``pricing_rules`` on paid rows; free rows keep only validated gift rule names.

	ERPNext zeroes a paid row's discount on the next save of an existing invoice
	with ``ignore_pricing_rule=1`` when the row still lists rules (see the comment
	in ``update_invoice``). Free rows are exempt: ``get_pricing_rule_for_item``
	returns early for ``is_free_item``, and the F&F gift policy needs their rule.
	Returns every rule name the rows carried (for one-time offers).
	"""
	seen = set()
	for item in items:
		if item.get("pricing_rules"):
			seen.update(_rule_names(item.pricing_rules))
			if not cint(item.get("is_free_item")):
				# What the client said priced the row, for the ended-offer check (D-R4-01)
				item.flags.pos_client_rules = _rule_names(item.pricing_rules)
				item.pricing_rules = ""
	_keep_gift_rule_names(items)
	return seen


UNBACKED_FREE_ITEM_LOG_TITLE = "Unbacked free item"
APPLY_OFFERS_METHOD = "pos_next.api.invoices.apply_offers"


def _offer_evaluator():
	"""The offer evaluator the cart calls: promotions' override when installed, else ours."""
	return frappe.get_attr(frappe.override_whitelisted_method(APPLY_OFFERS_METHOD))


def _first_rule(row) -> str:
	names = _rule_names(row.get("pricing_rules") or "")
	return names[0] if names else ""


def _is_zero_rate(row) -> bool:
	"""A paid row ERPNext will save at rate 0: 100% off (rate forced to 0 whatever is
	sent), or a rate that rounds to 0 at the field's precision. It is a free item."""
	return (
		not cint(row.get("is_free_item"))
		and flt(row.qty) > 0
		and (flt(row.get("discount_percentage")) >= 100 or flt(row.rate, row.precision("rate")) <= 0)
	)


def _paid_draft_free_qty(doc) -> dict:
	"""Free stock qty per (item_code, rule) on a stored draft that carries a payment, else {}.

	Those rows were checked (or logged) when the draft was saved; a re-save may keep them.
	"""
	if sum(flt(row.get("amount")) for row in doc.get("payments") or []) <= 0:
		return {}
	stored = {}
	for row in doc.get("items") or []:
		if cint(row.get("is_free_item")):
			key = (row.item_code, _first_rule(row))
			qty = flt(row.get("stock_qty")) or flt(row.qty) * (flt(row.get("conversion_factor")) or 1)
			stored[key] = stored.get(key, 0) + qty
	return stored


class _ItemData:
	"""Item master facts the checks trust instead of the client: group, brand, UOM factors."""

	def __init__(self):
		self.items, self.factors = {}, {}

	def load(self, codes):
		missing = list({code for code in codes if code} - set(self.items))
		if not missing:
			return
		for item in frappe.get_all(
			"Item", filters={"name": ["in", missing]}, fields=["name", "item_group", "brand", "stock_uom"]
		):
			self.items[item.name] = item
		for row in frappe.get_all(
			"UOM Conversion Detail",
			filters={"parenttype": "Item", "parent": ["in", missing]},
			fields=["parent", "uom", "conversion_factor"],
		):
			self.factors[(row.parent, row.uom)] = flt(row.conversion_factor)

	def get(self, code, field):
		return (self.items.get(code) or {}).get(field)

	def item_factor(self, code, uom) -> float | None:
		"""Stock units per ``uom`` as the Item defines it; None when the Item has no such UOM."""
		if not uom or uom == self.get(code, "stock_uom"):
			return 1
		return self.factors.get((code, uom))

	def factor(self, code, uom, fallback=None) -> float:
		"""Stock units per ``uom`` of ``code``: the Item's own factor, else ``fallback``."""
		return self.item_factor(code, uom) or flt(fallback) or 1


class _PricingContext:
	"""Server pricing facts for one save, shared by the free-row and paid-row checks.

	The offers of the genuinely paid rows are evaluated at most once per save and
	date (``paid_offers``), whichever check needs them first.
	"""

	def __init__(self, invoice_doc):
		self.doc = invoice_doc
		self.item_data = _ItemData()
		self.list_prices = {}
		self._paid = {}

	def load(self, rows):
		"""Item master facts and list prices (``_list_prices``) for ``rows``."""
		self.item_data.load(row.item_code for row in rows)
		missing = [row for row in rows if id(row) not in self.list_prices]
		if missing:
			self.list_prices.update(_list_prices(self.doc, missing, self.item_data))

	def paid_offers(self, paid_rows, on=None) -> tuple[dict, Exception | None]:
		"""The evaluator's answer for ``paid_rows`` (its items are in that order), on the
		evaluator's own date (today), or on the server date ``on``."""
		key = (tuple(id(row) for row in paid_rows), on)
		if key not in self._paid:
			self.load(paid_rows)
			payload = _offer_payload(self.doc, paid_rows, self.item_data, self.list_prices)
			if on:
				payload["posting_date"] = on
			self._paid[key] = _evaluate_offers(self.doc, payload)
		return self._paid[key]


def _pricing_context(invoice_doc) -> _PricingContext:
	if not invoice_doc.flags.pos_pricing:
		invoice_doc.flags.pos_pricing = _PricingContext(invoice_doc)
	return invoice_doc.flags.pos_pricing


def _refuse(message, title) -> None:
	"""Refuse an online save. Its Error Log row is a deferred insert, so the
	request's rollback does not take it away."""
	frappe.get_doc(doctype="Error Log", method=title, error=message).deferred_insert()
	frappe.throw(message, frappe.ValidationError)


def _force_item_factors(
	invoice_doc, rows, item_data, lenient, log_title=UNBACKED_FREE_ITEM_LOG_TITLE
) -> None:
	"""Checked rows move stock by the Item's own UOM factor, never the client's.

	ERPNext posts ``qty * conversion_factor`` from the row, so the row's factor is set
	to the Item's. A UOM the Item does not define cannot be measured: refused online,
	kept and logged on an offline sync.
	"""
	undefined = []
	for row in rows:
		factor = item_data.item_factor(row.item_code, row.get("uom"))
		if factor:
			row.conversion_factor = factor
		else:
			undefined.append(row)
	if not undefined:
		return
	if not lenient:
		row = undefined[0]
		_refuse(
			_("Row {0}: UOM {1} is not defined on item {2}.").format(row.idx, row.uom, row.item_code),
			log_title,
		)
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for row in undefined:
		log_error_without_telemetry(
			log_title,
			f"Invoice {reference}, row {row.idx}, item {row.item_code}: UOM {row.uom} not on the Item",
		)


def _server_price_list(invoice_doc) -> str | None:
	"""The POS Profile's selling price list, else the invoice's (a sale without a profile)."""
	profile = invoice_doc.get("pos_profile")
	return (
		profile and frappe.get_cached_value(DOCTYPE_POS_PROFILE, profile, "selling_price_list")
	) or invoice_doc.get("selling_price_list")


def _list_prices(invoice_doc, rows, item_data) -> dict:
	"""id(row) → list price from the POS Profile's price list (else the invoice's), or None."""
	price_list = _server_price_list(invoice_doc)
	codes = list({row.item_code for row in rows})
	if not price_list or not codes:
		return {}
	today = getdate(invoice_doc.get("posting_date") or nowdate())
	prices = {}
	for price in frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "item_code": ["in", codes]},
		fields=["item_code", "uom", "price_list_rate", "customer", "valid_from", "valid_upto"],
	):
		if price.customer and price.customer != invoice_doc.get("customer"):
			continue
		if (price.valid_from and getdate(price.valid_from) > today) or (
			price.valid_upto and getdate(price.valid_upto) < today
		):
			continue
		prices.setdefault(price.item_code, []).append(price)

	def row_price(row):
		# A customer's own price first; the row's UOM, else the stock UOM scaled.
		ranked = sorted(prices.get(row.item_code) or [], key=lambda price: not price.customer)
		for price in ranked:
			if price.uom and price.uom == row.get("uom"):
				return flt(price.price_list_rate)
		for price in ranked:
			if not price.uom or price.uom == item_data.get(row.item_code, "stock_uom"):
				factor = item_data.factor(row.item_code, row.get("uom"), row.get("conversion_factor"))
				return flt(price.price_list_rate) * factor
		return None

	return {id(row): row_price(row) for row in rows}


def _offer_payload(invoice_doc, paid_rows, item_data, list_prices, normalised=()) -> dict:
	"""The cart's apply_offers payload (posCart ``buildOfferEvaluationPayload``).

	Item group, brand and list price come from the server, never the client: they
	decide which offers (and amount thresholds) apply. A row without a list price
	uses the rate it is charged. A free row with a line-discount source
	(``normalised`` ids) goes in as a paid line at list price with no discount, so
	only the server can zero it; that payload is used for line pricing only.
	"""
	items = []
	for row in paid_rows:
		list_price = list_prices.get(id(row))
		rate = flt(list_price) if id(row) in normalised else flt(row.rate)
		discounts = {
			"discount_percentage": flt(row.get("discount_percentage")),
			"discount_amount": flt(row.get("discount_amount")),
			"discount_source": row.get("posnext_discount_source") or "",
		}
		if id(row) in normalised:
			discounts = {"discount_percentage": 0, "discount_amount": 0, "discount_source": ""}
		items.append(
			{
				"item_code": row.item_code,
				"item_name": row.get("item_name"),
				"qty": flt(row.qty),
				"rate": rate,
				"uom": row.get("uom"),
				"warehouse": row.get("warehouse"),
				"conversion_factor": item_data.factor(
					row.item_code, row.get("uom"), row.get("conversion_factor")
				),
				"price_list_rate": rate if list_price is None else list_price,
				**discounts,
				"pricing_rules": row.get("pricing_rules") or "",
				"item_group": item_data.get(row.item_code, "item_group"),
				"brand": item_data.get(row.item_code, "brand"),
				"amount": rate * flt(row.qty),
				"is_free_item": 0,
			}
		)
	return {
		"doctype": DOCTYPE_SALES_INVOICE,
		"pos_profile": invoice_doc.get("pos_profile"),
		"customer": invoice_doc.get("customer"),
		"company": invoice_doc.get("company"),
		"selling_price_list": invoice_doc.get("selling_price_list"),
		"currency": invoice_doc.get("currency"),
		"discount_amount": flt(invoice_doc.get("discount_amount")),
		"coupon_code": invoice_doc.get("coupon_code") or "",
		"items": items,
	}


def _gift_pool_groups(schemes) -> dict[str, dict[str, set[str]]]:
	"""Promotional Scheme → {pool item group: item codes}: a Gift Pool's choices, per pool."""
	if not schemes or not frappe.db.exists("DocType", "POS Gift Pool Item"):
		return {}
	pools = {}
	for row in frappe.get_all(
		"POS Gift Pool Item",
		filters={"parent": ["in", list(schemes)], "parenttype": "Promotional Scheme"},
		fields=["parent", "item_group", "item_code"],
	):
		pools.setdefault(row.parent, {}).setdefault(row.item_group, set()).add(row.item_code)
	return pools


def _expected_free_rows(free_items, item_data) -> tuple[dict, dict]:
	"""Evaluator free rows → ({(rule, item_code): stock qty}, {rule: {pool group: codes}}).

	Pools are set only for Gift Pool rules, and only the pools the evaluator granted
	from: the gift may be any item of that pool, up to the pool's granted qty.
	"""
	item_data.load(free.get("item_code") for free in free_items or [])
	expected, schemes = {}, {}
	for free in free_items or []:
		code = free.get("item_code")
		qty = flt(free.get("qty")) * item_data.factor(code, free.get("uom"), free.get("conversion_factor"))
		for rule in _rule_names(free.get("pricing_rules") or ""):
			expected[(rule, code)] = expected.get((rule, code), 0) + qty
			if free.get("applied_promotional_scheme"):
				schemes[rule] = free.get("applied_promotional_scheme")
	pools = _gift_pool_groups(set(schemes.values()))
	allowed = {}
	for rule, scheme in schemes.items():
		granted = {code for (r, code) in expected if r == rule}
		groups = {group: codes for group, codes in (pools.get(scheme) or {}).items() if codes & granted}
		if groups:
			allowed[rule] = groups
	return expected, allowed


def _pool_group(rule, item_code, allowed):
	return next((g for g in sorted(allowed.get(rule) or {}) if item_code in allowed[rule][g]), None)


def _row_rule(row, expected, allowed) -> str | None:
	"""The offer rule backing a free row: a sent name the evaluator expects, else one found by item."""

	def backs(rule):
		return (rule, row.item_code) in expected or _pool_group(rule, row.item_code, allowed) is not None

	sent = [rule for rule in _rule_names(row.get("pricing_rules") or "") if backs(rule)]
	if sent:
		return sent[0]
	candidates = sorted({rule for rule, _code in expected} | set(allowed))
	return next((rule for rule in candidates if backs(rule)), None)


def _line_zeroed(line) -> bool:
	"""A priced line the server discounted fully (by percentage, amount or rate).

	``discount_amount`` is the line total: both evaluators (pos_next's ``apply_offers``,
	promotions' engine) and the coupon engine report the line's discount, not ERPNext's
	per-unit field.
	"""
	gross = flt(line.get("price_list_rate")) * flt(line.get("qty") or 1)
	return (
		flt(line.get("discount_percentage")) >= 100
		or (gross > 0 and flt(line.get("discount_amount")) >= flt(gross, 2) - 0.01)
		or ("rate" in line and flt(line.get("rate"), 2) <= 0)
	)


def _offer_zeroing_rules(result, idx) -> list[str]:
	"""Applied rules with which the evaluator itself discounted paid line ``idx`` to 0.

	``applied_pricing_rules`` is only present when offers were evaluated (an early
	return echoes the sent rows), and the sent line carried no discount.
	"""
	applied = set(result.get("applied_pricing_rules") or [])
	items = result.get("items") or []
	if not applied or idx >= len(items):
		return []
	line = dict(items[idx])
	line.pop("rate", None)  # the evaluator echoes the sent rate; judge by its discount
	rules = applied & set(_rule_names(_pricing_rule_to_string(line.get("pricing_rules"))))
	return sorted(rules) if rules and _line_zeroed(line) else []


COUPON_DISCOUNT_METHOD = "pos_next.api.offers.calculate_coupon_discount"


def _coupon_line_updates(invoice_doc, coupon_code, payload, log_title) -> dict[int, dict] | None:
	"""Promotions' coupon resolver (its override of ``calculate_coupon_discount``) on
	``payload``: {line index: line update} where ``coupon_code`` discounts the line.

	None when promotions does not resolve coupons. Only the invoice's own coupon
	counts, so its usage limits apply (it is validated and counted from
	``coupon_code``): another code, an invalid coupon or a resolver error gives {}.
	"""
	override = frappe.override_whitelisted_method(COUPON_DISCOUNT_METHOD)
	if override == COUPON_DISCOUNT_METHOD:
		return None
	if cstr(invoice_doc.get("coupon_code")).upper() != cstr(coupon_code).upper():
		return {}
	message_count = len(frappe.local.message_log or [])
	try:
		result = frappe.get_attr(override)(
			coupon_code,
			json.dumps(payload, default=str),
			customer=invoice_doc.get("customer"),
			company=invoice_doc.get("company"),
			target_doctype=invoice_doc.doctype,
		)
	except Exception as error:
		# A failing resolver explains nothing; its own msgprint must not reach the
		# cashier as a second error.
		del frappe.local.message_log[message_count:]
		log_error_without_telemetry(
			log_title, f"Coupon {coupon_code}: could not be resolved ({type(error).__name__}: {error})"
		)
		return {}
	if not (result or {}).get("valid"):
		return {}
	return {
		cint(update.get("line_key")): update
		for update in result.get("line_updates") or []
		if update.get("line_key") is not None
	}


def _coupon_zeroed_lines(invoice_doc, coupon_code, payload) -> set[int]:
	"""Indexes of ``payload`` lines that ``coupon_code`` discounts fully, per the server.

	Promotions' coupon resolver when installed (``_coupon_line_updates``); otherwise
	pos_next's own POS Coupon, the invoice's own: a valid percentage coupon of at
	least 100% whose minimum amount the lines reach.
	"""
	updates = _coupon_line_updates(invoice_doc, coupon_code, payload, UNBACKED_FREE_ITEM_LOG_TITLE)
	if updates is not None:
		return {idx for idx, update in updates.items() if _line_zeroed(update)}
	if cstr(invoice_doc.get("coupon_code")).upper() != cstr(coupon_code).upper():
		return set()
	message_count = len(frappe.local.message_log or [])
	try:
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import check_coupon_code

		check = check_coupon_code(
			coupon_code, customer=invoice_doc.get("customer"), company=invoice_doc.get("company")
		)
		coupon = check.get("coupon")
		lines = [line for line in payload["items"] if not cint(line.get("is_free_item"))]
		subtotal = sum(flt(line.get("price_list_rate")) * flt(line.get("qty")) for line in lines)
		if (
			check.get("valid")
			and coupon.discount_type == "Percentage"
			and flt(coupon.discount_percentage) >= 100
			and subtotal >= flt(coupon.min_amount)
		):
			return set(range(len(lines)))
	except Exception as error:
		# A failing check backs nothing; the row is then checked as an unbacked free row.
		# Its own msgprint must not reach the cashier as a second error.
		del frappe.local.message_log[message_count:]
		log_error_without_telemetry(
			UNBACKED_FREE_ITEM_LOG_TITLE,
			f"Coupon {coupon_code}: could not be resolved ({type(error).__name__}: {error})",
		)
	return set()


EXCLUDED_RULES_FLAG = "pos_next_excluded_pricing_rules"


def _install_rule_exclusion() -> None:
	"""Let ERPNext's rule lookups leave out the rules named in ``frappe.flags`` (``EXCLUDED_RULES_FLAG``).

	Both of ERPNext's engines (per item and per transaction) build their rule query with
	``get_other_conditions``, looked up on the module when called, so one wrapper there
	makes a rule absent from the query: the engine then picks among the others, by its
	own priority and conflict rules, as if the rule did not exist. The wrapper is
	installed once per process and does nothing while the request-local flag is unset;
	pos_next's own reference (``erpnext_get_other_conditions``) stays unwrapped.
	"""
	from erpnext.accounts.doctype.pricing_rule import utils

	if getattr(utils.get_other_conditions, "pos_next_excludes_rules", False):
		return
	original = utils.get_other_conditions

	def get_other_conditions(*args, **kwargs):
		conditions = original(*args, **kwargs)
		excluded = frappe.flags.get(EXCLUDED_RULES_FLAG)
		if excluded:
			# ERPNext's (conditions, values, args); any other shape fails the lookup, so
			# the evaluation explains nothing rather than everything.
			values = kwargs["values"] if "values" in kwargs else args[1]
			conditions += f" and `tabPricing Rule`.name not in %({EXCLUDED_RULES_FLAG})s"
			values[EXCLUDED_RULES_FLAG] = tuple(sorted(excluded))
		return conditions

	get_other_conditions.pos_next_excludes_rules = True
	utils.get_other_conditions = get_other_conditions


def _evaluate_without(rule_names, evaluate):
	"""``evaluate()`` with ERPNext's engines leaving out the Pricing Rules ``rule_names``
	(``_install_rule_exclusion``); nothing is disabled for anyone else."""
	if not rule_names:
		return evaluate()
	_install_rule_exclusion()
	previous = frappe.flags.get(EXCLUDED_RULES_FLAG)
	frappe.flags[EXCLUDED_RULES_FLAG] = set(previous or ()) | set(rule_names)
	try:
		return evaluate()
	finally:
		frappe.flags[EXCLUDED_RULES_FLAG] = previous


def _desk_pricing_profile(invoice_doc) -> frappe._dict:
	"""The pricing facts the offer evaluator takes from a POS Profile, for a sale made
	without one (Desk): the invoice's own company, price list and currency."""
	return frappe._dict(
		company=invoice_doc.get("company"),
		selling_price_list=invoice_doc.get("selling_price_list"),
		currency=invoice_doc.get("currency"),
		warehouse=None,
		customer=None,
		ignore_pricing_rule=0,
	)


def _evaluate_offers(invoice_doc, payload, selected_offers=None) -> tuple[dict, Exception | None]:
	"""One call to the cart's evaluator; an error is logged and returned, never raised.

	``selected_offers`` (rule names the server verified, never the client's as sent)
	is passed on as the cart passes its applied offers.

	A sale without a POS Profile (Desk) is evaluated by pos_next's own evaluator on the
	invoice's pricing facts (``_desk_pricing_profile``). On a Sales Invoice, the one-time
	rules this customer already redeemed are left out of ERPNext's rule lookup, so the
	offers it picks are those it would pick without them (Ruling 117), on the
	evaluator's own date; an unresolved rule conflict is an error, which explains
	nothing.
	"""
	selected = json.dumps(sorted(selected_offers)) if selected_offers else None
	if payload.get("pos_profile"):
		cart_evaluator = _offer_evaluator()

		def evaluator(data):
			if selected:
				return cart_evaluator(data, selected_offers=selected)
			return cart_evaluator(data)
	else:
		profile = _desk_pricing_profile(invoice_doc)

		def evaluator(data):
			return _apply_offers(data, selected, profile=profile)

	payload = json.dumps(payload, default=str)
	message_count = len(frappe.local.message_log or [])
	result, evaluator_error = {}, None
	try:
		redeemed = set()
		if invoice_doc.doctype == DOCTYPE_SALES_INVOICE:
			redeemed = set(_redeemed_one_time_records(invoice_doc)[1])
		result = _evaluate_without(redeemed, lambda: evaluator(payload)) or {}
		if invoice_doc.doctype != DOCTYPE_SALES_INVOICE:
			result = _without_one_time_rules(result)
		elif redeemed:
			result = _without_one_time_rules(result, only=redeemed)
	except Exception as error:
		# Any evaluator failure means no offer backs anything; the callers decide.
		result, evaluator_error = {}, error
	if evaluator_error:
		# The evaluator's own msgprint must not reach the cashier as a second error.
		del frappe.local.message_log[message_count:]
		reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
		log_error_without_telemetry(
			UNBACKED_FREE_ITEM_LOG_TITLE,
			f"Invoice {reference}: offers could not be evaluated "
			f"({type(evaluator_error).__name__}: {evaluator_error})",
		)
	return result, evaluator_error


def _without_one_time_rules(result, only=None) -> dict:
	"""``result`` with nothing one-time-per-customer rules gave (``only`` those, when
	given). One-time rules apply only to a Sales Invoice, where they are redeemed, and
	a rule this customer already redeemed explains nothing whatever an evaluator
	answers (Ruling 113). A line any of them touched keeps no rule, so its discount is
	explained by nothing; a one-time transaction rule takes the header offer away;
	their gifts are dropped."""
	if not result:
		return result
	items = result.get("items") or []
	free_items = result.get("free_items") or []
	names = set(result.get("applied_pricing_rules") or [])
	for line in items:
		names.update(_rule_names(_pricing_rule_to_string(line.get("pricing_rules"))))
	names.update(cstr(free.get("pricing_rules")) for free in free_items if free.get("pricing_rules"))
	if not names:
		return result
	if only is not None:
		names &= set(only)
		if not names:
			return result
	one_time = {
		record.name: record.apply_on
		for record in frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", list(names)], "one_time_per_customer": 1},
			fields=["name", "apply_on"],
		)
	}
	if not one_time:
		return result
	result = dict(result)
	result["applied_pricing_rules"] = [
		name for name in result.get("applied_pricing_rules") or [] if name not in one_time
	]
	stripped = []
	for line in items:
		line = dict(line)
		if set(_rule_names(_pricing_rule_to_string(line.get("pricing_rules")))) & set(one_time):
			line.update(pricing_rules="", discount_percentage=0, discount_amount=0)
		stripped.append(line)
	result["items"] = stripped
	result["free_items"] = [free for free in free_items if cstr(free.get("pricing_rules")) not in one_time]
	if "Transaction" in one_time.values():
		result.update(additional_discount_percentage=0, discount_amount=0)
	return result


def _price_rule_names(rows) -> set[str]:
	"""Names on ``rows`` that are Price (line discount) Pricing Rules."""
	names = {name for row in rows for name in _rule_names(row.get("pricing_rules") or "")}
	if not names:
		return set()
	return set(
		frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", list(names)], "price_or_product_discount": "Price"},
			pluck="name",
		)
	)


def _line_sources(row, price_rules, coupon_code) -> set[tuple]:
	"""A free row's line-discount sources: its Price rules, and its coupon if it is the invoice's."""
	sources = {
		(row.item_code, name) for name in _rule_names(row.get("pricing_rules") or "") if name in price_rules
	}
	code = cstr(row.get("posnext_coupon_code")).upper()
	if code and code == cstr(coupon_code).upper():
		sources.add((row.item_code, f"coupon:{code}"))
	return sources


def _stored_line_sources(doc) -> set[tuple]:
	"""Line-discount sources of the free rows a stored draft already holds.

	They were confirmed when the draft was saved: a Price rule name survives on a
	free row only when the server confirmed it (``flags.pos_backing_rule``), and a
	coupon only when it is the invoice's own.
	"""
	free = [row for row in doc.get("items") or [] if cint(row.get("is_free_item"))]
	price_rules = _price_rule_names(free)
	return {source for row in free for source in _line_sources(row, price_rules, doc.get("coupon_code"))}


def _check_free_rows_backed(
	invoice_doc, offline_sync=False, paid_draft_free=None, stored_sources=frozenset()
) -> None:
	"""Every free row must come from an offer; a row at zero price is a free row.

	A paid row ERPNext would save at rate 0 (100% off, or a rate that rounds to 0) is
	made a free row (``is_free_item`` 1, rate 0, no discount) that keeps its source
	(``pricing_rules`` or ``posnext_coupon_code``). A free row with a line-discount
	source (made free now, or confirmed on the stored draft: ``stored_sources``) is
	backed when the server confirms that source gives the line 100%:
	- a line pricing evaluation: paid rows plus these rows at list price with no
	  discount; it is used for nothing else;
	- or the coupon resolver, for the invoice's own coupon.
	Every other free row must match a Product rule gift from a gift evaluation of
	only the genuinely paid rows: a free row never earns its own gift (Ruling 83).

	The cart's evaluator is promotions' ``apply_offers`` override when installed. It
	gets item group, brand and list price from the server. Free qty is compared in
	stock units, per rule and item (per pool for a Gift Pool), and free rows move
	stock by the Item's own UOM factor.

	An unbacked or excess free row, or an evaluator error, refuses the save, except:
	- ``offline_sync`` (an offline sale synced through ``submit_invoice``, first try or
	  a retry with no completed invoice): every problem is only logged;
	- ``paid_draft_free`` (see ``_paid_draft_free_qty``): free qty up to what the
	  stored paid draft already held is only logged.
	Must run before ``_reset_row_pricing_rules`` blanks the paid rows' rules.
	"""
	if invoice_doc.get("is_return"):
		return
	rows = [row for row in invoice_doc.get("items") or [] if row.get("item_code")]
	made_free = [row for row in rows if _is_zero_rate(row)]
	for row in made_free:
		# As ERPNext stores a gift; a list price left on it would make ERPNext
		# re-price the row (taxes_and_totals.calculate_item_values).
		row.update(
			{
				"is_free_item": 1,
				"rate": 0,
				"price_list_rate": 0,
				"discount_percentage": 0,
				"discount_amount": 0,
			}
		)
	free_rows = [row for row in rows if cint(row.get("is_free_item"))]
	if not free_rows:
		return
	made_free_ids = {id(row) for row in made_free}
	price_rules = _price_rule_names(free_rows)
	coupon_code = invoice_doc.get("coupon_code")
	candidates = [
		row
		for row in free_rows
		if (
			id(row) in made_free_ids
			and (_rule_names(row.get("pricing_rules") or "") or row.get("posnext_coupon_code"))
		)
		or (
			id(row) not in made_free_ids
			and _line_sources(row, price_rules, coupon_code) & set(stored_sources)
		)
	]
	# A manual edit to 0 has no source: it is told so, not that offers changed.
	sourceless = {
		id(row)
		for row in made_free
		if not _rule_names(row.get("pricing_rules") or "") and not row.get("posnext_coupon_code")
	}
	paid_rows = [row for row in rows if not cint(row.get("is_free_item"))]
	context = _pricing_context(invoice_doc)
	item_data, list_prices = context.item_data, context.list_prices
	item_data.load(row.item_code for row in rows)
	_force_item_factors(invoice_doc, free_rows, item_data, lenient=offline_sync)
	context.load(paid_rows + candidates)

	backed = set()
	if candidates:
		candidate_ids = {id(row) for row in candidates}
		priced = [row for row in rows if id(row) in candidate_ids or not cint(row.get("is_free_item"))]
		payload = _offer_payload(invoice_doc, priced, item_data, list_prices, candidate_ids)
		result, _error = _evaluate_offers(invoice_doc, payload)
		coupon_lines = {}
		for idx, row in enumerate(priced):
			if id(row) not in candidate_ids:
				continue
			rules = _offer_zeroing_rules(result, idx)
			if rules:
				row.pricing_rules = ",".join(rules)
				row.flags.pos_backing_rule = True
				backed.add(id(row))
			elif row.get("posnext_coupon_code"):
				code = row.posnext_coupon_code
				if code not in coupon_lines:
					coupon_lines[code] = _coupon_zeroed_lines(invoice_doc, code, payload)
				if idx in coupon_lines[code]:
					backed.add(id(row))

	remaining = [row for row in free_rows if id(row) not in backed]
	if not remaining:
		return
	result, evaluator_error = context.paid_offers(paid_rows)
	free_items = list(result.get("free_items") or [])
	if not evaluator_error:
		free_items += _selected_gift_free_items(invoice_doc, rows, paid_rows, context, result)
	_check_free_rows(
		invoice_doc,
		remaining,
		free_items,
		evaluator_error,
		item_data,
		offline_sync,
		paid_draft_free,
		sourceless,
	)


def _free_item_rules(free_items) -> set[str]:
	return {name for free in free_items or [] for name in _rule_names(free.get("pricing_rules") or "")}


AGGREGATED_RULES_FLAG = "pos_next_aggregated_rule_totals"
# The gifts promotions' cart evaluator grants on the cart's summed quantity.
AGGREGATED_PROMOTION_TYPES = ("GWP", "Gift Pool")


def _install_aggregated_qty() -> None:
	"""Let ERPNext's quantity and amount filter judge some rules on cart totals.

	While ``frappe.flags`` holds a callable (``AGGREGATED_RULES_FLAG``), each rule it
	gives totals for is judged on them: the cart's summed quantity and amount over
	the rule's items, as the cart's evaluator grants a GWP or Gift Pool. Every other
	rule keeps the row's own quantity. ERPNext's selection (priority, apply multiple,
	conflicts) is otherwise its own. ``filter_pricing_rules_for_qty_amount`` is looked
	up on the module when called, so one wrapper there is enough; it is installed
	once per process and does nothing while the flag is unset.
	"""
	from erpnext.accounts.doctype.pricing_rule import utils

	if getattr(utils.filter_pricing_rules_for_qty_amount, "pos_next_aggregates", False):
		return
	original = utils.filter_pricing_rules_for_qty_amount

	def filter_pricing_rules_for_qty_amount(qty, rate, pricing_rules, args=None):
		totals = frappe.flags.get(AGGREGATED_RULES_FLAG)
		if not totals:
			return original(qty, rate, pricing_rules, args)
		kept = []
		for rule in pricing_rules:
			rule_qty, rule_amount = totals(rule) or (qty, rate)
			if original(rule_qty, rule_amount, [rule], args):
				kept.append(rule)
		return kept

	filter_pricing_rules_for_qty_amount.pos_next_aggregates = True
	utils.filter_pricing_rules_for_qty_amount = filter_pricing_rules_for_qty_amount


class _ServerCart(frappe._dict):
	"""The cart on server data, as ERPNext's rule selection reads a document: the
	invoice's fields (for a rule's Python condition) and its paid rows."""

	def as_dict(self, *args, **kwargs):
		return self


def _server_cart(invoice_doc, paid_rows, item_data, list_prices, price_list) -> _ServerCart:
	items = []
	for row in paid_rows:
		factor = item_data.factor(row.item_code, row.get("uom"), row.get("conversion_factor"))
		list_price = list_prices.get(id(row))
		price = flt(row.rate) if list_price is None else flt(list_price)
		items.append(
			frappe._dict(
				item_code=row.item_code,
				item_group=item_data.get(row.item_code, "item_group"),
				brand=item_data.get(row.item_code, "brand"),
				uom=row.get("uom"),
				conversion_factor=factor,
				qty=flt(row.qty),
				stock_qty=flt(row.qty) * factor,
				price_list_rate=price,
				rate=price,
				warehouse=row.get("warehouse"),
			)
		)
	cart = _ServerCart(invoice_doc.as_dict())
	cart.update(items=items, selling_price_list=price_list)
	return cart


def _rule_totals(cart):
	"""rule → (stock qty, amount) of the cart's paid rows in the rule's scope, for a GWP
	or Gift Pool rule (a Gift Pool's own pool items do not count); None otherwise."""
	cache = {}

	def totals(rule):
		name = rule.get("name")
		if cstr(rule.get("promotion_type")) not in AGGREGATED_PROMOTION_TYPES or not name:
			return None
		if name not in cache:
			pr_doc = frappe.get_cached_doc("Pricing Rule", name)
			scope = set(erpnext_get_pricing_rule_items(pr_doc) or [])
			field = frappe.scrub(pr_doc.apply_on or "")
			pool = set()
			if pr_doc.get("promotion_type") == "Gift Pool" and pr_doc.get("promotional_scheme"):
				for codes in (_gift_pool_groups({pr_doc.promotional_scheme}).get(pr_doc.promotional_scheme) or {}).values():
					pool |= codes
			rows = [item for item in cart["items"] if item.get(field) in scope and item.item_code not in pool]
			cache[name] = (
				sum(item.stock_qty for item in rows),
				sum(item.price_list_rate * item.qty for item in rows),
			)
		return cache[name]

	return totals


def _cart_gift_winners(invoice_doc, rows, paid_rows, context, granted) -> set[str]:
	"""Product rules named on the cart's rows that win ERPNext's own rule selection for
	this cart (Ruling 148), less ``granted`` (rules the plain evaluation already gave).

	A named rule counts only when ERPNext's ``get_pricing_rules`` returns it for a paid
	row: on server data (item, item group, brand, UOM, warehouse, list price), the POS
	Profile's price list (never the client's), today, the customer and its groups and
	territory, POS-only rules for a POS sale, with the rule's condition, quantity and amount thresholds, priority,
	``apply_multiple_pricing_rules`` and every competing rule, Price rules included. A
	GWP or Gift Pool rule is judged on the cart's summed quantity, as the cart's
	evaluator grants it (``_install_aggregated_qty``); a redeemed one-time rule is left
	out of the lookup. A conflict ERPNext cannot resolve picks nothing. Without the
	lookup: none.
	"""
	sent = {name for row in rows for name in _rule_names(row.get("pricing_rules") or "")} - set(granted)
	if not sent or not paid_rows or not (erpnext_get_pricing_rules and erpnext_get_pricing_rule_items):
		return set()
	products = set(
		frappe.get_all(
			"Pricing Rule",
			filters={
				"name": ["in", list(sent)],
				"price_or_product_discount": "Product",
				"coupon_code_based": 0,
			},
			pluck="name",
		)
	)
	if not products:
		return set()
	price_list = _server_price_list(invoice_doc)
	item_data = context.item_data
	cart = _server_cart(invoice_doc, paid_rows, item_data, context.list_prices, price_list)
	base = frappe._dict(
		_one_time_match_args(invoice_doc, invoice_doc.get("customer")),
		price_list=price_list,
		currency=invoice_doc.get("currency"),
		transaction_date=nowdate(),
		# A sale through a POS Profile is a POS sale: POS-only rules apply to it.
		is_pos=1 if invoice_doc.get("pos_profile") else cint(invoice_doc.get("is_pos")),
	)
	redeemed = set()
	if invoice_doc.doctype == DOCTYPE_SALES_INVOICE:
		redeemed = set(_redeemed_one_time_records(invoice_doc)[1])
	won = set()

	def lookup():
		for item in cart["items"]:
			args = frappe._dict(base, **item)
			message_count = len(frappe.local.message_log or [])
			try:
				rules = erpnext_get_pricing_rules(args, cart) or []
			except Exception:
				# An unresolved conflict (or any lookup error) picks nothing here.
				del frappe.local.message_log[message_count:]
				continue
			won.update(rule.get("name") for rule in rules if isinstance(rule, dict) and rule.get("name"))
			if products <= won:
				return

	_install_aggregated_qty()
	previous = frappe.flags.get(AGGREGATED_RULES_FLAG)
	frappe.flags[AGGREGATED_RULES_FLAG] = _rule_totals(cart)
	try:
		_evaluate_without(redeemed, lookup)
	finally:
		frappe.flags[AGGREGATED_RULES_FLAG] = previous
	return won & products - redeemed


def _selected_gift_free_items(invoice_doc, rows, paid_rows, context, result) -> list:
	"""Free rows of rules the cart applied that the plain evaluation does not grant
	(D-R2-08), when the server confirms them.

	A mixed-SKU GWP (buy A + B, 2 in all) is granted by the cart's evaluator only for
	a selected rule: ERPNext's per-item lookup reads min_qty on each item alone. A
	rule the rows name counts only if it wins ERPNext's own selection for this cart
	(``_cart_gift_winners``, Ruling 148). Those rules are selected, with every rule the
	plain evaluation applied, and only their free rows are taken from that
	evaluation: each rule's gift comes from one evaluation, and that evaluation
	decides its quantity.
	"""
	granted = _free_item_rules(result.get("free_items"))
	extra = _cart_gift_winners(invoice_doc, rows, paid_rows, context, granted)
	if not extra:
		return []
	applied = set(result.get("applied_pricing_rules") or [])
	for line in result.get("items") or []:
		applied.update(_rule_names(_pricing_rule_to_string(line.get("pricing_rules"))))
	payload = _offer_payload(invoice_doc, paid_rows, context.item_data, context.list_prices)
	selected, error = _evaluate_offers(invoice_doc, payload, extra | applied | granted)
	if error:
		return []
	return [
		free
		for free in selected.get("free_items") or []
		if _free_item_rules([free]) and _free_item_rules([free]) <= extra
	]


def _check_free_rows(
	invoice_doc, free_rows, free_items, evaluator_error, item_data, offline_sync, paid_draft_free, sourceless
):
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	expected, allowed = _expected_free_rows(free_items, item_data)
	sent, by_stored_key, first_row = {}, {}, {}
	for row in free_rows:
		rule = _row_rule(row, expected, allowed)
		group = _pool_group(rule, row.item_code, allowed) if rule in allowed else None
		key = (rule, ("pool", group)) if group is not None else (rule, row.item_code)
		qty = flt(row.qty) * item_data.factor(row.item_code, row.get("uom"), row.get("conversion_factor"))
		sent[key] = sent.get(key, 0) + qty
		stored_key = (row.item_code, rule or _first_rule(row))
		by_stored_key.setdefault(key, {})
		by_stored_key[key][stored_key] = by_stored_key[key].get(stored_key, 0) + qty
		first_row.setdefault(key, row)
		if rule:
			row.pricing_rules = rule
			row.flags.pos_server_rule = True

	refused, logged = [], []
	for key, qty in sent.items():
		rule, target = key
		if isinstance(target, tuple):
			cap = sum(
				q for (r, code), q in expected.items() if r == rule and code in allowed[rule][target[1]]
			)
		else:
			cap = expected.get(key, 0) if rule else 0
		if flt(qty, 6) <= flt(cap, 6):
			continue
		problem = (first_row[key], cap, qty)
		already_held = all(
			flt(held, 6) <= flt((paid_draft_free or {}).get(stored_key, 0), 6)
			for stored_key, held in by_stored_key[key].items()
		)
		(logged if offline_sync or already_held else refused).append(problem)

	if refused:
		zero_priced = [row for row, _cap, _qty in refused if id(row) in sourceless]
		if zero_priced:
			_refuse(_zero_price_message(zero_priced[0]), UNBACKED_FREE_ITEM_LOG_TITLE)
		messages = [
			_("Row {0}: free item {1} is not backed by an offer (free qty {2} expected, {3} sent).").format(
				row.idx, row.item_code, cap, qty
			)
			for row, cap, qty in refused
		]
		if evaluator_error:
			messages.append(_("Free items could not be checked against the offers."))
		messages.append(_("The offers changed. Refresh and re-apply offers."))
		_refuse("<br>".join(messages), UNBACKED_FREE_ITEM_LOG_TITLE)
	for row, cap, qty in logged:
		log_error_without_telemetry(
			UNBACKED_FREE_ITEM_LOG_TITLE,
			f"Invoice {reference}, row {row.idx}, item {row.item_code}: free stock qty {cap} expected, "
			f"{qty} sent (rules sent: {row.get('pricing_rules') or '-'})",
		)


def _strip_server_managed_fields(payload):
	"""Validate doctype and filter invoice payload to allowlisted fields only."""
	if not isinstance(payload, dict):
		return payload

	payload_doctype = payload.get("doctype")
	if payload_doctype and payload_doctype not in POS_DOCUMENT_DOCTYPES:
		frappe.throw(
			_("Only Sales Invoice or Sales Order documents are allowed"),
			frappe.PermissionError,
		)

	cleaned = {k: v for k, v in payload.items() if k in ALLOWED_INVOICE_FIELDS}
	cleaned["doctype"] = payload_doctype or DOCTYPE_SALES_INVOICE
	# One-time offers used by this sale are stamped by the server only (Ruling 110).
	cleaned.pop("pos_applied_one_time_rules", None)
	# Packed Items are regenerated from Product Bundle definitions during save.
	cleaned.pop("packed_items", None)

	if isinstance(cleaned.get("items"), list):
		cleaned["items"] = [
			{
				k: v
				for k, v in row.items()
				if k in ALLOWED_INVOICE_ITEM_FIELDS and k not in CLIENT_ROW_MARGIN_FIELDS
			}
			for row in cleaned["items"]
			if isinstance(row, dict)
		]

	if isinstance(cleaned.get("payments"), list):
		cleaned["payments"] = [
			{k: v for k, v in row.items() if k in ALLOWED_INVOICE_PAYMENT_FIELDS}
			for row in cleaned["payments"]
			if isinstance(row, dict)
		]

	if isinstance(cleaned.get("sales_team"), list):
		cleaned["sales_team"] = [
			{k: v for k, v in row.items() if k in ALLOWED_SALES_TEAM_FIELDS}
			for row in cleaned["sales_team"]
			if isinstance(row, dict)
		]

	if isinstance(cleaned.get("taxes"), list):
		cleaned["taxes"] = [
			{k: v for k, v in row.items() if k in ALLOWED_INVOICE_TAX_FIELDS}
			for row in cleaned["taxes"]
			if isinstance(row, dict)
		]

	return cleaned


def _ensure_invoice_draft_access(
	invoice_name: str,
	pos_profile: str | None = None,
	doctype: str = DOCTYPE_SALES_INVOICE,
	raise_on_submitted: type[Exception] | None = None,
):
	"""Load an existing draft POS document and verify caller ownership/supervisor and profile access."""
	current_user = ensure_desk_user()
	invoice_doc = frappe.get_doc(doctype, invoice_name)

	if invoice_doc.docstatus != 0 and raise_on_submitted is None:
		frappe.throw(
			_("Only draft invoices can be modified or submitted here"),
			frappe.PermissionError,
		)

	target_profile = invoice_doc.get("pos_profile") or pos_profile
	ensure_pos_user(target_profile, current_user)

	if (
		pos_profile
		and invoice_doc.get("pos_profile")
		and pos_profile != invoice_doc.pos_profile
		and not is_pos_supervisor(current_user)
	):
		frappe.throw(
			_("Cannot move a draft invoice to a different POS Profile"),
			frappe.PermissionError,
		)

	if invoice_doc.owner != current_user and not is_pos_supervisor(current_user):
		frappe.throw(
			_("You can only modify or submit your own draft invoices"),
			frappe.PermissionError,
		)

	if invoice_doc.docstatus == 1 and raise_on_submitted is not None:
		# First, before any check (stock among them): the POS reads this as "already
		# submitted" and closes the cart as sold (F6, Ruling 138).
		frappe.throw(
			_("Invoice {0} was already submitted").format(invoice_doc.name),
			raise_on_submitted,
		)

	if invoice_doc.docstatus != 0:
		frappe.throw(
			_("Only draft invoices can be modified or submitted here"),
			frappe.PermissionError,
		)

	return invoice_doc


def _ensure_opening_shift_for_invoice(opening_shift_name: str | None, pos_profile: str | None) -> None:
	"""Ensure an attached POS Opening Shift belongs to the caller (or supervisor) and POS Profile."""
	if not opening_shift_name:
		return

	current_user = ensure_desk_user()
	shift = frappe.db.get_value(
		"POS Opening Shift",
		opening_shift_name,
		["user", "pos_profile", "status", "docstatus"],
		as_dict=True,
	)
	if not shift:
		return

	if shift.user != current_user and not is_pos_supervisor(current_user):
		frappe.throw(
			_("You cannot attach an invoice to another user's shift"),
			frappe.PermissionError,
		)

	if pos_profile and shift.pos_profile and shift.pos_profile != pos_profile:
		frappe.throw(
			_("POS Opening Shift does not match POS Profile"),
			frappe.ValidationError,
		)


CLIENT_ROW_MARGIN_FIELDS = (
	"margin_type",
	"margin_rate_or_amount",
	"rate_with_margin",
	"base_rate_with_margin",
)


def _refuse_zero_rate_after_totals(invoice_doc, lenient) -> None:
	"""A paid row ERPNext computed at rate 0 is refused online, logged on an offline sync.

	Runs after ``calculate_taxes_and_totals``: it judges the rate ERPNext will save,
	whatever field produced it.
	"""
	if invoice_doc.get("is_return"):
		return
	zero = [
		row
		for row in invoice_doc.get("items") or []
		if not cint(row.get("is_free_item"))
		and flt(row.qty) > 0
		and flt(row.rate, row.precision("rate")) <= 0
	]
	if not zero:
		return
	if not lenient:
		_refuse(_zero_price_message(zero[0]), UNBACKED_FREE_ITEM_LOG_TITLE)
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for row in zero:
		log_error_without_telemetry(
			UNBACKED_FREE_ITEM_LOG_TITLE,
			f"Invoice {reference}, row {row.idx}, item {row.item_code}: paid row computed at rate 0",
		)


def _zero_price_message(row) -> str:
	return _("Item {0} cannot be sold at zero price. Free items must come from an offer.").format(
		row.item_code
	)


UNEXPLAINED_DISCOUNT_LOG_TITLE = "Unexplained discount"
ENDED_OFFER_LOG_TITLE = "Offline discount from an ended offer"


def _ended_rule_reasons(rule_names, on_date) -> dict[str, str]:
	"""{rule: why it no longer prices a sale} for the named Pricing Rules that are disabled,
	or out of their validity on ``on_date``."""
	if not rule_names:
		return {}
	rows = frappe.get_all(
		"Pricing Rule",
		filters={"name": ["in", list(rule_names)]},
		fields=["name", "title", "disable", "valid_from", "valid_upto"],
	)
	day = getdate(on_date)
	reasons = {}
	for rule in rows:
		if cint(rule.disable):
			# Known only as of now: it may still have been live when the till sold (review M4)
			reason = "disabled at sync"
		elif rule.valid_upto and getdate(rule.valid_upto) < day:
			reason = f"expired on {rule.valid_upto}"
		elif rule.valid_from and getdate(rule.valid_from) > day:
			reason = f"not valid before {rule.valid_from}"
		else:
			continue
		reasons[rule.name] = f"{rule.name} ({rule.title}) {reason}" if rule.title else f"{rule.name} {reason}"
	return reasons


def _log_ended_offer_rows(invoice_doc, below) -> None:
	"""Offline sync (D-R4-01): a paid row the till priced with an offer that has since been
	disabled or has expired is not taken on the rule's word. The sale is kept (offline
	policy: keep and log, never strand) and each such row is logged once, with its rule,
	row and rate, whatever else would explain the discount."""
	named = {id(row): row.flags.get("pos_client_rules") or [] for row, *_ in below}
	ended = _ended_rule_reasons(
		{rule for rules in named.values() for rule in rules}, invoice_doc.get("posting_date") or nowdate()
	)
	if not ended:
		return
	done = invoice_doc.flags.setdefault("pos_ended_offer_logged", set())
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for row, list_price, _tolerance in below:
		for rule in named[id(row)]:
			key = (row.idx, rule)
			if rule not in ended or key in done:
				continue
			done.add(key)
			log_error_without_telemetry(
				ENDED_OFFER_LOG_TITLE,
				f"Invoice {reference} (offline): Row {row.idx}: item {row.item_code} sold at {flt(row.rate)} "
				f"against a list price of {flt(list_price)} by offer {ended[rule]}; the sale is kept.",
			)


FNF_DISCOUNT_SOURCE = "friends_and_family"
FIELD_ALLOW_USER_TO_EDIT_ITEM_DISCOUNT = "allow_user_to_edit_item_discount"
FIELD_ALLOW_USER_TO_EDIT_ADDITIONAL_DISCOUNT = "allow_user_to_edit_additional_discount"
# POS Settings defaults (pos_settings.json) when a profile has no POS Settings row.
DISCOUNT_SETTING_DEFAULTS = {
	FIELD_ALLOW_USER_TO_EDIT_ADDITIONAL_DISCOUNT: 0,
	FIELD_ALLOW_USER_TO_EDIT_ITEM_DISCOUNT: 1,
	FIELD_ALLOW_USER_TO_EDIT_RATE: 0,
	FIELD_MAX_DISCOUNT_ALLOWED: 0,
}


def _promotions_evaluates_offers() -> bool:
	"""Promotions is installed and owns offers (it overrides ``apply_offers``)."""
	return frappe.override_whitelisted_method(APPLY_OFFERS_METHOD) != APPLY_OFFERS_METHOD


def _fnf_repriced_in_this_save(invoice_doc, offline_sync) -> bool:
	"""Promotions re-prices this save's F&F rows itself: an unpaid, online POS Sales Invoice
	draft that is not being submitted in this call (no payment on the document or in its
	flags, no offline sync, no ``offline_id``, not ``submit_invoice``) with promotions
	installed. Storing such a draft is harmless: every submit route judges its F&F rows in
	before_submit (``_fnf_rows_on_submit``, Ruling 128). "Paid" is the document's own payments, whatever flag a path set
	or not yet set (Ruling 126).

	Its validate then clears a stale F&F mark and gives the row what F&F really gives,
	so the row's mark is left for it (Ruling 123). A paid save, an offline sync and
	before_submit are judged on the computed F&F rate instead (Ruling 120).
	"""
	return (
		invoice_doc.doctype == DOCTYPE_SALES_INVOICE
		and cint(invoice_doc.get("is_pos"))
		and not offline_sync
		and not invoice_doc.flags.pos_offline_sync
		and not invoice_doc.flags.pos_submitting
		and not invoice_doc.flags.pos_payment_collected
		and not _carries_payment(invoice_doc)
		and not invoice_doc.get("offline_id")
		and _promotions_evaluates_offers()
	)


def _fnf_rows_left_to_promotions(invoice_doc, offline_sync) -> bool:
	"""This save carries an F&F-marked row that ``_check_paid_row_discounts`` left to
	promotions (``_fnf_repriced_in_this_save``): before_submit must judge it again."""
	return _fnf_repriced_in_this_save(invoice_doc, offline_sync) and any(
		row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE for row in invoice_doc.get("items") or []
	)


def _fnf_not_eligible_message(row, list_price) -> str:
	return _(
		"Row {0}: item {1} is discounted from {2} to {3} as Friends & Family, but this sale is "
		"not eligible for Friends & Family on that item."
	).format(row.idx, row.item_code, list_price, flt(row.rate))


FNF_REPLACED_FIELD = "posnext_fnf_replaced_discount"


def _stored_fnf_snapshots(doc) -> list[tuple]:
	"""The signed replaced-discount snapshots (``posnext_fnf_replaced_discount``) of a
	stored draft's F&F rows, with each row's item, UOM, qty and rate.

	Promotions signs the snapshot on the unpaid save (the payment-open check). The POS
	never sends it back, and promotions never re-prices (so never re-signs) a paid save,
	so without this the submitted row loses the record of the discount F&F beat (D-10).
	"""
	if not doc.meta.get_field("items") or not frappe.get_meta(doc.meta.get_field("items").options).has_field(
		FNF_REPLACED_FIELD
	):
		return []
	return [
		(row.item_code, row.uom, flt(row.qty, 6), flt(row.rate, row.precision("rate")), row.get(FNF_REPLACED_FIELD))
		for row in doc.get("items") or []
		if row.get(FNF_REPLACED_FIELD) and row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE
	]


def _carry_fnf_snapshots(doc, snapshots) -> None:
	"""Put a stored F&F row's signed snapshot back on the submitted row it matches
	exactly (item, UOM, qty, rate), one to one. The value is the server's own and
	promotions verifies its signature wherever it uses it; it never explains a price
	here."""
	left = list(snapshots)
	for row in doc.get("items") or []:
		if not left or row.get("posnext_discount_source") != FNF_DISCOUNT_SOURCE:
			continue
		key = (row.item_code, row.uom, flt(row.qty, 6), flt(row.rate, row.precision("rate")))
		for i, snap in enumerate(left):
			if snap[:4] == key:
				row.set(FNF_REPLACED_FIELD, snap[4])
				del left[i]
				break


def _carries_payment(doc) -> bool:
	return sum(flt(row.get("amount")) for row in doc.get("payments") or []) > 0


def _paid_draft_rates(doc) -> dict:
	"""Lowest rate per (item, UOM) on a stored paid draft, else {}.

	``doc`` is the draft as the database holds it. It counts as a stored paid draft only
	when it carries a payment and the server's paid-row check passed it exactly as stored
	(``_checked_paid_draft``): a payment saved on Desk, or set in memory, holds nothing
	(Ruling 130).
	"""
	rates = {}
	for item_code, uom, _qty, rate, _factor in _paid_draft_rows(doc):
		rates[(item_code, uom)] = min(rates.get((item_code, uom), rate), rate)
	return rates


def _paid_draft_rows(doc) -> list[tuple]:
	"""The paid rows of a stored paid draft (see ``_paid_draft_rates``), each as
	(item_code, uom, qty, rate, conversion_factor), else []. A submitted row is held
	only by a stored row it matches exactly, one to one (``_take_held_row``, Ruling 132).
	"""
	if not _carries_payment(doc) or not _checked_paid_draft(doc.doctype, doc.name):
		return []
	return [
		(
			row.item_code,
			row.get("uom"),
			flt(row.qty),
			flt(row.rate),
			flt(row.get("conversion_factor")) or 1.0,
		)
		for row in doc.get("items") or []
		if row.get("item_code") and not cint(row.get("is_free_item")) and flt(row.qty) > 0
	]


def _take_held_row(held_rows, row) -> bool:
	"""Whether a stored paid draft row matches ``row`` exactly on item, UOM, qty, rate and
	conversion factor; the match is removed, so a second row cannot reuse it (Ruling 132)."""
	precision = row.precision("rate")
	precision = 2 if precision is None else cint(precision)
	key = (
		row.item_code,
		row.get("uom"),
		flt(row.qty, 6),
		flt(row.rate, precision),
		flt(flt(row.get("conversion_factor")) or 1.0, 6),
	)
	for position, (item_code, uom, qty, rate, factor) in enumerate(held_rows or []):
		if (item_code, uom, flt(qty, 6), flt(rate, precision), flt(factor, 6)) == key:
			del held_rows[position]
			return True
	return False


#: ``tabDefaultValue`` parent of the record that the server's paid-row check passed a
#: draft. No whitelisted method writes it, and its value is sealed with the site key.
CHECKED_PAID_DRAFT_PARENT = "__pos_next_checked_paid_draft"


def _stored_draft_state(doctype, name) -> str | None:
	"""The draft the DATABASE holds under ``name`` (customer, rows, payments) as one string,
	or None when no draft is stored. Never the doc in memory."""
	header = name and frappe.db.get_value(doctype, name, ["docstatus", "customer"], as_dict=True)
	if not header or cint(header.docstatus) != 0:
		return None
	meta = frappe.get_meta(doctype)
	items_doctype = meta.get_field("items").options
	item_fields = ["item_code", "uom", "qty", "rate", "is_free_item"]
	if frappe.get_meta(items_doctype).has_field("posnext_discount_source"):
		item_fields.append("posnext_discount_source")
	rows = frappe.get_all(
		items_doctype,
		filters={"parent": name, "parenttype": doctype, "parentfield": "items"},
		fields=item_fields,
		order_by="idx asc",
	)
	payments = frappe.get_all(
		meta.get_field("payments").options,
		filters={"parent": name, "parenttype": doctype, "parentfield": "payments"},
		fields=["mode_of_payment", "amount"],
		order_by="idx asc",
	)
	return json.dumps(
		[header.customer, [[row.get(field) for field in item_fields] for row in rows], payments],
		default=str,
		sort_keys=True,
	)


def _paid_draft_seal(doctype, name, state) -> str:
	import hashlib
	import hmac

	from frappe.utils.password import get_encryption_key

	message = f"{doctype}\n{name}\n{state}".encode()
	return hmac.new(get_encryption_key().encode(), message, hashlib.sha256).hexdigest()


def _record_checked_paid_draft(doc) -> None:
	"""The server's paid-row check passed this paid draft, as it is now saved."""
	state = _stored_draft_state(doc.doctype, doc.name)
	if state is not None:
		frappe.defaults.set_default(
			f"{doc.doctype}::{doc.name}",
			_paid_draft_seal(doc.doctype, doc.name, state),
			CHECKED_PAID_DRAFT_PARENT,
		)


def _checked_paid_draft(doctype, name) -> bool:
	"""Whether the draft the database holds under ``name`` is exactly one the server's
	paid-row check passed (``_record_checked_paid_draft``). A record lost or changed
	means no: the draft is then judged like a new sale."""
	state = _stored_draft_state(doctype, name)
	if state is None:
		return False
	seal = frappe.db.get_value(
		"DefaultValue", {"parent": CHECKED_PAID_DRAFT_PARENT, "defkey": f"{doctype}::{name}"}, "defvalue"
	)
	return bool(seal) and seal == _paid_draft_seal(doctype, name, state)


def _forget_checked_paid_draft(doc) -> None:
	if doc.name:
		frappe.db.delete(
			"DefaultValue", {"parent": CHECKED_PAID_DRAFT_PARENT, "defkey": f"{doc.doctype}::{doc.name}"}
		)


def _held_paid_draft_rows(doc) -> list[tuple]:
	"""Before_submit, any route: the rows of the stored paid draft ``doc`` is submitted
	from, read from the DATABASE (Ruling 130). ``submit_invoice`` saves before it submits,
	so it passes the stored draft's rows it read before its own save
	(``flags.pos_paid_draft_rows``, [] on the create path). A fresh list: matching
	consumes it."""
	rows = doc.flags.get("pos_paid_draft_rows")
	if rows is not None:
		return list(rows)
	if doc.is_new() or not frappe.db.exists(doc.doctype, {"name": doc.name, "docstatus": 0}):
		return []
	return _paid_draft_rows(frappe.get_doc(doc.doctype, doc.name))


def _offer_rate(result, idx, list_price) -> float | None:
	"""Per-unit rate that rules the server applied give paid line ``idx``, or None.

	Only a line carrying a rule listed in ``applied_pricing_rules`` counts: the
	evaluators echo a cashier's own discount on a line without rules, and an early
	return echoes every line as sent. ``discount_amount`` is the line total.
	"""
	applied = set(result.get("applied_pricing_rules") or [])
	items = result.get("items") or []
	if not applied or idx >= len(items):
		return None
	line = items[idx]
	if not applied & set(_rule_names(_pricing_rule_to_string(line.get("pricing_rules")))):
		return None
	price = flt(line.get("price_list_rate")) or list_price
	qty = flt(line.get("qty")) or 1
	by_percentage = price * (1 - min(flt(line.get("discount_percentage")), 100) / 100)
	by_amount = price - flt(line.get("discount_amount")) / qty
	return max(min(by_percentage, by_amount), 0)


# Fields of a line the server's offer evaluation priced, as the coupon resolver reads a
# cart line's own discount (an F&F line also carries the signed snapshot of the offer
# it displaced, which promotions verifies itself).
OFFER_PRICED_FIELDS = (
	"discount_percentage",
	"discount_amount",
	"discount_source",
	"is_already_discounted",
	"pricing_rules",
	"posnext_discount_source",
	"posnext_fnf_percentage",
	"posnext_fnf_program",
	FNF_REPLACED_FIELD,
)


def _coupon_line_rates(invoice_doc, coupon_code, paid_rows, context) -> tuple[dict[int, float], set[int]]:
	"""Per-unit rate the invoice's coupon gives each paid line, ({line index: rate},
	stacked line indexes). Both empty without promotions.

	The coupon is priced on the server's list price with no other discount. A coupon
	that stacks on an offer ("Add on top") is also priced on the line as the server's
	own offer evaluation prices it (``_offer_priced_payload``): where promotions' resolver
	stacks it there, the rate is the offer-priced rate less the coupon, and the line is
	in the stacked set: its discount is the offer's and the coupon's together (D-R3-04).
	Nothing the client sent prices either payload.
	"""
	measures = {
		id(row): flt(row.get("price_list_rate"))
		if context.list_prices.get(id(row)) is None
		else context.list_prices[id(row)]
		for row in paid_rows
	}
	payload = _offer_payload(
		invoice_doc, paid_rows, context.item_data, measures, normalised={id(row) for row in paid_rows}
	)
	updates = _coupon_line_updates(invoice_doc, coupon_code, payload, UNEXPLAINED_DISCOUNT_LOG_TITLE)
	rates = {idx: flt(update["rate"]) for idx, update in (updates or {}).items() if "rate" in update}
	stacked_lines = set()
	if updates is None:
		return rates, stacked_lines
	priced = _offer_priced_payload(invoice_doc, payload)
	if priced is not None:
		stacked = _coupon_line_updates(invoice_doc, coupon_code, priced, UNEXPLAINED_DISCOUNT_LOG_TITLE)
		for idx, update in (stacked or {}).items():
			if update.get("stacked") and "rate" in update:
				rates[idx] = flt(update["rate"])
				stacked_lines.add(idx)
	return rates, stacked_lines


def _offer_priced_payload(invoice_doc, payload) -> dict | None:
	"""``payload`` (paid lines at list price, no discount) with each line's discount as the
	server's offer evaluation of that same payload gives it, or None when nothing is
	discounted or the offers could not be evaluated."""
	result, error = _evaluate_offers(invoice_doc, payload)
	lines = result.get("items") or []
	if error or len(lines) != len(payload["items"]):
		return None
	items, changed = [], False
	for line, evaluated in zip(payload["items"], lines, strict=True):
		line = dict(line)
		if flt(evaluated.get("discount_percentage")) > 0 or flt(evaluated.get("discount_amount")) > 0:
			for field in OFFER_PRICED_FIELDS:
				if field in evaluated:
					line[field] = evaluated[field]
			line["pricing_rules"] = _pricing_rule_to_string(line.get("pricing_rules"))
			changed = True
		items.append(line)
	return dict(payload, items=items) if changed else None


NEW_ROW_KEY = "pos-next-new-row-"


def _fnf_line_rates(invoice_doc, list_prices) -> dict[int, float]:
	"""Per-unit rate F&F gives each F&F-marked row in ``list_prices`` ({id(row): the
	server's list price}): {id(row): rate}, never below 0 or above that list price.

	The rate is what the benefit providers compute on the server's data
	(``registry.fnf_line_rates``, Ruling 120). The mark only asks for it and explains
	nothing by itself. With no provider, or on a document that is not a Sales Invoice,
	it is {}. The provider sees copies of the invoice and its rows, without flags, with
	each row on its server list price. An unsaved row is keyed by its position.
	"""
	from pos_next.integrations import registry

	marked = {
		id(row)
		for row in invoice_doc.get("items") or []
		if id(row) in list_prices and row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE
	}
	if invoice_doc.doctype != DOCTYPE_SALES_INVOICE or not marked:
		return {}
	view = frappe._dict(invoice_doc.as_dict())
	# The stored creation only, never one set in memory (Ruling 125).
	stored = invoice_doc.get("name") and frappe.db.get_value(
		invoice_doc.doctype, invoice_doc.name, "creation"
	)
	view["creation"] = stored or None
	rows, copies = {}, []
	for position, row in enumerate(invoice_doc.get("items") or []):
		copy = frappe._dict(row.as_dict())
		copy.name = row.name or f"{NEW_ROW_KEY}{position}"
		if id(row) in list_prices:
			copy.price_list_rate = list_prices[id(row)]
		rows[copy.name] = row
		copies.append(copy)
	view["items"] = copies
	rates = {}
	for name, rate in registry.fnf_line_rates(view).items():
		row = rows.get(name)
		if row is not None and id(row) in marked:
			rates[id(row)] = min(flt(rate), flt(list_prices[id(row)]))
	return rates


def _discount_settings(pos_profile) -> dict:
	settings = (
		pos_profile
		and frappe.db.get_value(
			DOCTYPE_POS_SETTINGS, {"pos_profile": pos_profile}, list(DISCOUNT_SETTING_DEFAULTS), as_dict=True
		)
	) or {}
	return {
		field: default if settings.get(field) is None else settings.get(field)
		for field, default in DISCOUNT_SETTING_DEFAULTS.items()
	}


def _manual_discount_problem(row, list_price, unexplained, tolerance, settings) -> str | None:
	"""Why a cashier may not take ``unexplained`` (per unit) off ``list_price``, or None.

	The part carried by the row's discount percentage needs Allow Item Discount;
	any further gap down to the rate needs Allow User To Edit Rate. Max Discount
	Percentage Allowed (0 = no limit) caps the sum, as a percentage of list price.
	"""
	rate = flt(row.rate)
	percentage = flt(row.get("discount_percentage"))
	in_discount, in_rate = 0, unexplained
	if 0 < percentage < 100:
		in_discount = min(unexplained, rate * percentage / (100 - percentage))
		# The POS sends the percentage at 2 decimals and the rate rounded to the currency
		# unit (G8). Read back through the %, a rate error grows by 1 / (1 - %), so allow
		# a currency unit plus half a 2-dp % step (list × 0.00005) on the rate itself,
		# scaled the same way.
		in_rate = unexplained - in_discount - (tolerance + list_price * 0.00005) * 100 / (100 - percentage)
	prices = (row.idx, row.item_code, list_price, rate)
	if in_discount > tolerance and not cint(settings[FIELD_ALLOW_USER_TO_EDIT_ITEM_DISCOUNT]):
		return _(
			"Row {0}: item {1} is discounted from {2} to {3}, and item discounts are not allowed "
			"for this POS Profile."
		).format(*prices)
	if in_rate > tolerance and not cint(settings[FIELD_ALLOW_USER_TO_EDIT_RATE]):
		return _(
			"Row {0}: item {1} is priced {3} against a list price of {2}, and rate editing is not "
			"allowed for this POS Profile."
		).format(*prices)
	limit = flt(settings[FIELD_MAX_DISCOUNT_ALLOWED])
	taken = flt(unexplained / list_price * 100, 2)
	# The lowest rate the limit allows, at the rate's own precision: the maximum typed
	# exactly and rounded to the cent (50% of 20.01 is 10.00) is never over it.
	precision = -round(math.log10(tolerance)) if tolerance > 0 else 2
	lowest = flt(list_price * (1 - limit / 100), precision)
	if limit > 0 and flt(lowest - (list_price - unexplained), precision + 2) > tolerance:
		return _(
			"Row {0}: item {1} is reduced from {2} to {3} ({4}%), above the maximum allowed discount of {5}%."
		).format(*prices, taken, limit)
	return None


def _paid_rows(invoice_doc) -> list:
	"""The invoice's paid item rows, in order: the rows the shared evaluator call sees."""
	return [
		row
		for row in invoice_doc.get("items") or []
		if row.get("item_code") and not cint(row.get("is_free_item"))
	]


def _check_paid_row_discounts(invoice_doc, offline_sync=False, paid_draft_rows=None) -> None:
	"""A paid row below its list price must be explained by the server, not the client.

	Runs after ``calculate_taxes_and_totals``: it judges the rate that will be saved.
	List price: the Item Price ``_list_prices`` finds, which also becomes the row's
	saved ``price_list_rate``; else the row's ``price_list_rate`` (a measure only,
	never an exemption). Nothing skips a paid row (Ruling 88). The reduction from
	there to the rate is explained by, in turn:
	- the offers the server evaluates for the paid rows (``_PricingContext``,
	  shared with the free-row check), only discounts of rules it applied;
	- a line coupon (``posnext_coupon_code``): what promotions' coupon resolver gives
	  that line on the server's list price, for the invoice's own coupon only;
	- an F&F line (``posnext_discount_source``): down to the rate the benefit provider
	  computes for that row on the server's data (``_fnf_line_rates``), never the mark
	  itself (Ruling 120); without a provider, or on a Sales Order, nothing. On an
	  unpaid, online POS save the row is left to promotions, which re-prices it in the
	  same save (``_fnf_repriced_in_this_save``, Ruling 123);
	- a manual edit the POS Settings permit (``_manual_discount_problem``), except on
	  a row a one-time offer this customer already used matches: that row takes no
	  manual discount at all (``_used_one_time_offer_rows``, Ruling 111).
	Client flags (``is_rate_manually_edited``, ``original_rate``) decide nothing.
	One-time offers the server applied to a discounted row are stamped on a Sales
	Invoice whatever rule names the client sent (``_stamp_server_one_time_rules``),
	unless the row's coupon or F&F rate explains at least as much: its discount is then
	the coupon's or F&F's, not the offer's (Rulings 118, 120).
	Tolerance: one unit of the rate's precision per unit sold. A row at rate 0 is
	``_refuse_zero_rate_after_totals``'s.

	An unexplained reduction refuses the save, except on an offline sync, or for
	a row that matches a stored paid draft's row exactly, one to one
	(``paid_draft_rows``, ``_take_held_row``, Ruling 132):
	then it is kept and logged.
	"""
	if invoice_doc.get("is_return"):
		return
	held_rows = list(paid_draft_rows or [])
	paid_rows = _paid_rows(invoice_doc)
	rows = [row for row in paid_rows if flt(row.qty) > 0 and flt(row.rate) > 0]
	if not rows:
		return
	context = _pricing_context(invoice_doc)
	context.item_data.load(row.item_code for row in rows)
	_force_item_factors(
		invoice_doc, rows, context.item_data, lenient=offline_sync, log_title=UNEXPLAINED_DISCOUNT_LOG_TITLE
	)
	context.load(rows)
	for row in rows:
		# Saved (and measured by promotions' F&F check) on the server's list price.
		if context.list_prices.get(id(row)) is not None:
			row.price_list_rate = context.list_prices[id(row)]
	fnf_left_to_promotions = _fnf_repriced_in_this_save(invoice_doc, offline_sync)

	below = []
	for row in rows:
		list_price = flt(row.get("price_list_rate"))
		precision = row.precision("rate")
		tolerance = 10 ** -cint(2 if precision is None else precision)
		if list_price <= 0 or flt(row.rate) >= list_price - tolerance:
			continue
		if fnf_left_to_promotions and row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE:
			continue
		below.append((row, list_price, tolerance))
	if not below:
		return
	if offline_sync:
		_log_ended_offer_rows(invoice_doc, below)

	result, _error = context.paid_offers(paid_rows)
	index = {id(row): idx for idx, row in enumerate(paid_rows)}
	fnf_rates = _fnf_line_rates(invoice_doc, {id(row): list_price for row, list_price, _t in below})
	coupon_rates = {}
	settings = _discount_settings(invoice_doc.get("pos_profile"))
	refused, logged = [], []
	used_offers = None
	offer_lines = []
	for row, list_price, tolerance in below:
		idx = index[id(row)]
		offer = _offer_rate(result, idx, list_price)
		coupon, stacked = None, False
		code = row.get("posnext_coupon_code")
		if code:
			if code not in coupon_rates:
				coupon_rates[code] = _coupon_line_rates(invoice_doc, code, paid_rows, context)
			coupon = coupon_rates[code][0].get(idx)
			stacked = idx in coupon_rates[code][1]
		fnf = fnf_rates.get(id(row))
		other = min((rate for rate in (coupon, fnf) if rate is not None), default=None)
		if other is None or (offer is not None and offer < other):
			# The line's discount is the offer's, not a coupon's or F&F's at least as large
			# (Rulings 118, 120).
			offer_lines.append(idx)
			if offer is not None and abs(offer - flt(row.rate)) <= tolerance:
				# Written to the row at before_submit (Ruling 137): the server's names only.
				row.flags.pos_server_rules = ",".join(sorted(_server_line_rules(result, [idx])))
		elif stacked and flt(row.rate) <= coupon + tolerance:
			# At the coupon's rate or below it: any further cut is a manual discount judged
			# below, and the offer is still part of the line's discount (H2 round 1).
			# An "Add on top" coupon priced on the offer: the offer is part of the line's
			# discount, so the row keeps its rules and a one-time one is stamped (D-R3-04).
			offer_lines.append(idx)
			row.flags.pos_server_rules = ",".join(sorted(_server_line_rules(result, [idx])))
		if (
			min(rate for rate in (list_price, offer, coupon, fnf) if rate is not None) - flt(row.rate)
			<= tolerance
		):
			continue
		if used_offers is None:
			used_offers = _offline_safe(
				offline_sync,
				invoice_doc,
				dict,
				_used_one_time_offer_rows,
				invoice_doc,
				[below_row for below_row, *_ in below],
				context.item_data,
			)
		problem, held = _row_discount_problem(
			invoice_doc,
			row,
			list_price,
			tolerance,
			(offer, coupon, fnf),
			used_offers.get(id(row)),
			settings,
			held_rows,
		)
		if problem:
			(logged if offline_sync or held else refused).append(problem)
	if invoice_doc.doctype == DOCTYPE_SALES_INVOICE:
		_stamp_server_one_time_rules(invoice_doc, result, offer_lines)
	if refused:
		_refuse("<br>".join(refused), UNEXPLAINED_DISCOUNT_LOG_TITLE)
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for problem in logged:
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")


def _row_discount_problem(
	invoice_doc, row, list_price, tolerance, rates, used_rule, settings, held_rows=None
) -> tuple[str | None, bool]:
	"""Why a paid row's rate is refused, or None; and whether a stored paid draft held it,
	matching one of ``held_rows`` exactly (then it is logged, not refused). One judge for the POS paid-row check and the
	before_submit F&F check (Ruling 128), so both give the same answer.

	``rates`` are the per-unit rates the server explains the row down to (offers,
	coupon, F&F; None where none applies). What is left below them:
	- on a row a one-time offer this customer already used matches (``used_rule``),
	  "already used": the offers were evaluated without the used ones, so a regular
	  offer ERPNext would pick still explains its part (Rulings 111, 116, 117);
	- else a manual discount the POS Settings may permit (``_manual_discount_problem``);
	  an F&F row the server gives no F&F rate says so instead (M2).
	"""
	offer, coupon, fnf = rates
	unexplained = min(rate for rate in (list_price, offer, coupon, fnf) if rate is not None) - flt(row.rate)
	if unexplained <= tolerance:
		return None, False
	if used_rule:
		return _one_time_used_message(used_rule), False
	problem = _manual_discount_problem(row, list_price, unexplained, tolerance, settings)
	if not problem:
		return None, False
	if (
		fnf is None
		and invoice_doc.doctype == DOCTYPE_SALES_INVOICE
		and row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE
	):
		# An F&F row the server gives no F&F rate: say so, not "a manual discount".
		problem = _fnf_not_eligible_message(row, list_price)
	return problem, _take_held_row(held_rows, row)


def _fnf_rows_on_submit(doc) -> tuple[list[str], list[str]]:
	"""Sales Invoice before_submit, any route (Ruling 128): every F&F-marked paid row below
	its list price is judged as the POS paid-row check judges it (``_row_discount_problem``),
	on the F&F rate the server computes (``_fnf_line_rates``: today and the stored
	creation day, Ruling 125), the offers on ``_offer_dates`` without this customer's
	redeemed one-time rules, the invoice's own line coupon, and the POS Settings.

	Returns (refused, held) messages; ``held`` are rows the stored paid draft already held
	(an exact, one-to-one match with ``_held_paid_draft_rows``, read from the database on
	every route, Rulings 130 and 132), which are logged.
	"""
	rows = [
		row
		for row in _paid_rows(doc)
		if row.get("posnext_discount_source") == FNF_DISCOUNT_SOURCE
		and flt(row.qty) > 0
		and flt(row.rate) > 0
	]
	if not rows:
		return [], []
	context = _pricing_context(doc)
	paid_rows = _paid_rows(doc)
	context.load(paid_rows)
	index = {id(row): idx for idx, row in enumerate(paid_rows)}
	below = []
	for row in rows:
		precision = row.precision("rate")
		tolerance = 10 ** -cint(2 if precision is None else precision)
		# The server's list price or the row's, whichever is higher (as ``_redeem_on_submit``).
		list_price = max(flt(context.list_prices.get(id(row))), flt(row.get("price_list_rate")))
		if list_price > 0 and flt(row.rate) < list_price - tolerance:
			below.append((row, list_price, tolerance))
	if not below:
		return [], []
	fnf_rates = _fnf_line_rates(doc, {id(row): list_price for row, list_price, _t in below})
	used = _used_one_time_offer_rows(doc, [row for row, *_ in below], context.item_data)
	settings = _discount_settings(doc.get("pos_profile"))
	dates = _offer_dates(doc)
	held_rows = _held_paid_draft_rows(doc)
	coupon_rates, refused, held = {}, [], []
	for row, list_price, tolerance in below:
		idx = index[id(row)]
		offers = [_offer_rate(context.paid_offers(paid_rows, on)[0], idx, list_price) for on in dates]
		offer = min((rate for rate in offers if rate is not None), default=None)
		coupon = None
		code = row.get("posnext_coupon_code")
		if code:
			if code not in coupon_rates:
				coupon_rates[code] = _coupon_line_rates(doc, code, paid_rows, context)
			coupon = coupon_rates[code][0].get(idx)
		problem, kept = _row_discount_problem(
			doc,
			row,
			list_price,
			tolerance,
			(offer, coupon, fnf_rates.get(id(row))),
			used.get(id(row)),
			settings,
			held_rows,
		)
		if problem:
			(held if kept else refused).append(problem)
	return refused, held


def _paid_draft_header(doc) -> tuple[float, float] | None:
	"""(header discount, its share of the total before it) of a stored draft that
	carries a payment, else None. The stored totals give the share, as 8k's paid-draft
	rule is per unit."""
	if not _carries_payment(doc):
		return None
	header = flt(doc.get("discount_amount"))
	base = _header_discount_bases(doc).get(cstr(doc.get("apply_discount_on")) or "Grand Total") or 0
	return header, header / base if base > 0 else 0


def _header_discount_bases(invoice_doc) -> dict[str, float]:
	"""Totals before the header discount, after ``calculate_taxes_and_totals``:
	{"Net Total": ..., "Grand Total": ...}.

	ERPNext takes the header discount off the totals it applies to, so adding it
	back gives the total it was taken from. Its percentage is worked out on that
	total, minus any Actual taxes for "Grand Total", so this base is never smaller.
	"""
	discount = flt(invoice_doc.get("discount_amount"))
	net, grand = flt(invoice_doc.get("net_total")), flt(invoice_doc.get("grand_total"))
	if cstr(invoice_doc.get("apply_discount_on")) == "Net Total":
		return {"Net Total": net + discount, "Grand Total": grand + discount * (grand / net if net else 1)}
	return {"Net Total": net + discount * (net / grand if grand else 1), "Grand Total": grand + discount}


def _coupon_header_left_to_promotions(invoice_doc, paid) -> bool:
	"""Promotions caps a POS Coupon's header discount on an unpaid POS Sales Invoice
	(its validate hook). A paid invoice is never re-priced there, and its header next
	to F&F rows is only logged (Ruling 89), so pos_next judges a paid one itself."""
	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import resolve_coupon_name

	return (
		not paid
		and invoice_doc.doctype == DOCTYPE_SALES_INVOICE
		and cint(invoice_doc.get("is_pos"))
		and frappe.override_whitelisted_method(COUPON_DISCOUNT_METHOD) != COUPON_DISCOUNT_METHOD
		and bool(resolve_coupon_name(invoice_doc.get("coupon_code")))
	)


def _coupon_header_value(invoice_doc, bases) -> float:
	"""What the invoice's POS Coupon gives as a header discount, in invoice currency.

	pos_next's own coupon rule (``check_coupon_code`` + ``apply_coupon_discount``) on
	the totals before the header. Coupon amounts are company currency. An invalid or
	unknown coupon, or one whose check fails, gives 0.
	"""
	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import apply_coupon_discount, check_coupon_code

	code = invoice_doc.get("coupon_code")
	conversion_rate = flt(invoice_doc.get("conversion_rate")) or 1
	message_count = len(frappe.local.message_log or [])
	try:
		check = check_coupon_code(
			code, customer=invoice_doc.get("customer"), company=invoice_doc.get("company")
		)
		if not check.get("valid"):
			return 0
		value = apply_coupon_discount(
			check["coupon"], bases["Grand Total"] * conversion_rate, bases["Net Total"] * conversion_rate
		)
	except Exception as error:
		# A failing check explains nothing; its own msgprint must not reach the cashier.
		del frappe.local.message_log[message_count:]
		log_error_without_telemetry(
			UNEXPLAINED_DISCOUNT_LOG_TITLE,
			f"Coupon {code}: could not be resolved ({type(error).__name__}: {error})",
		)
		return 0
	return flt(value.get("discount")) / conversion_rate if value.get("valid") else 0


def _offer_header_value(result, bases, apply_discount_on) -> float:
	"""Header discount the server-evaluated transaction offers give (0 when none fired).

	The evaluators work it out on a fresh document, so it is never the client's
	header echoed back. A percentage is valued on this invoice's base.
	"""
	base = bases.get(cstr(result.get("apply_discount_on")) or apply_discount_on) or 0
	return max(
		flt(result.get("discount_amount")),
		base * flt(result.get("additional_discount_percentage")) / 100,
	)


def _unexplained_header(invoice_doc, dates=(None,)) -> frappe._dict:
	"""How much of the invoice's header discount nothing on the server explains, for the
	POS checks and the Desk before_submit hook alike (Ruling 117).

	Run after the totals. The header (``discount_amount``) is explained, the larger of the
	two (the cart never combines them), by:
	- the invoice's coupon: pos_next's POS Coupon value (``_coupon_header_value``);
	- the transaction offers the server evaluates for the paid rows (the shared
	  ``_PricingContext`` call), without the one-time rules this customer already
	  redeemed (``_evaluate_offers``), on each of ``dates`` (None: the evaluator's
	  own date), the most any of them gives.
	Returns header, manual (the rest), explained, source, evaluator_error, bases and
	apply_discount_on.
	"""
	header = flt(invoice_doc.get("discount_amount"))
	tolerance = 10 ** -cint(_currency_precision(invoice_doc.get("currency")))
	code = invoice_doc.get("coupon_code")
	bases = _header_discount_bases(invoice_doc)
	apply_discount_on = cstr(invoice_doc.get("apply_discount_on")) or "Grand Total"
	coupon = _coupon_header_value(invoice_doc, bases) if code else 0
	offers, evaluator_error = 0, None
	if header - coupon > tolerance:
		context, paid_rows = _pricing_context(invoice_doc), _paid_rows(invoice_doc)
		for on in dates:
			result, error = context.paid_offers(paid_rows, on)
			evaluator_error = evaluator_error or error
			offers = max(offers, _offer_header_value(result, bases, apply_discount_on))
	explained, source = (
		(coupon, _("coupon {0}").format(code)) if coupon >= offers else (offers, _("the offers"))
	)
	return frappe._dict(
		header=header,
		manual=header - explained,
		explained=explained,
		source=source,
		evaluator_error=evaluator_error,
		bases=bases,
		apply_discount_on=apply_discount_on,
	)


def _check_header_discount(
	invoice_doc, offline_sync=False, paid_draft_header=None, paid_draft_rates=None
) -> None:
	"""The invoice-level discount must be explained by the server, not the client.

	Runs after ``calculate_taxes_and_totals`` and the paid-row check, on the header
	that will be saved (``discount_amount``, worked out from any percentage). On an
	unpaid POS Sales Invoice with promotions and a coupon, promotions caps a POS
	Coupon's header itself, so nothing is checked here. Otherwise the coupon or the
	server-evaluated offers explain part of it (``_unexplained_header``, shared with
	the Desk hook). The rest is a manual invoice discount: on a cart a one-time offer
	this customer already used matches, it is refused at any size; else it needs Allow
	Additional Discount, and
	Max Discount Percentage Allowed (0 = no limit) caps it as a percentage of the
	total before the header it applies to (``apply_discount_on``), separately from
	the line cap. Tolerance: one unit of the currency precision.

	An unexplained header refuses the save, except on an offline sync, or when a
	stored paid draft already held a header no smaller, as an amount and as a share
	of the total before it (Ruling 90), on the same rows at rates no lower (Ruling
	100): then it is kept and logged. When the offers could not be evaluated, the
	refusal says so.
	"""
	if invoice_doc.get("is_return"):
		return
	precision = cint(_currency_precision(invoice_doc.get("currency")))
	tolerance = 10**-precision
	if flt(invoice_doc.get("discount_amount")) <= tolerance:
		return
	paid = bool(
		offline_sync
		or invoice_doc.get("offline_id")
		or paid_draft_header is not None
		or _carries_payment(invoice_doc)
	)
	if invoice_doc.get("coupon_code") and _coupon_header_left_to_promotions(invoice_doc, paid):
		return
	unexplained = _unexplained_header(invoice_doc)
	header, manual, explained = unexplained.header, unexplained.manual, unexplained.explained
	source, evaluator_error, bases = unexplained.source, unexplained.evaluator_error, unexplained.bases
	apply_discount_on = unexplained.apply_discount_on
	if manual <= tolerance:
		return
	used = _offline_safe(
		offline_sync, invoice_doc, lambda: None, _used_one_time_transaction_rule, invoice_doc
	) or _offline_safe(offline_sync, invoice_doc, lambda: None, _used_one_time_item_in_cart, invoice_doc)
	if used:
		# No manual header re-gives a cart offer this customer already used (Ruling 113).
		problem = _one_time_used_message(used)
		if not offline_sync:
			_refuse(problem, UNEXPLAINED_DISCOUNT_LOG_TITLE)
		reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")
		return

	explanation = (
		_("{0} of it is given by {1}").format(flt(explained, precision), source)
		if explained > tolerance
		else _("no coupon or offer gives it")
	)
	settings = _discount_settings(invoice_doc.get("pos_profile"))
	base = bases.get(apply_discount_on, bases["Grand Total"])
	limit = flt(settings[FIELD_MAX_DISCOUNT_ALLOWED])
	if not cint(settings[FIELD_ALLOW_USER_TO_EDIT_ADDITIONAL_DISCOUNT]):
		problem = _(
			"Invoice discount {0} ({1}): manual invoice discounts are not allowed for this POS Profile."
		).format(flt(header, precision), explanation)
	elif limit > 0 and manual > base * limit / 100 + tolerance:
		problem = _(
			"Invoice discount {0} ({1}): the manual part {2} is {3}% of {4}, above the maximum allowed "
			"invoice discount of {5}%."
		).format(
			flt(header, precision),
			explanation,
			flt(manual, precision),
			flt(manual / base * 100, 2) if base > 0 else 100,
			flt(base, precision),
			limit,
		)
	else:
		return
	if evaluator_error:
		problem = _(
			"Invoice discount {0} could not be checked against the offers. Try again in a moment."
		).format(flt(header, precision))
	if offline_sync or _keeps_held_header(invoice_doc, paid_draft_header, paid_draft_rates):
		reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")
		return
	_refuse(problem, UNEXPLAINED_DISCOUNT_LOG_TITLE)


def _validate_invoice_profile(payload):
	"""The caller must be allowed to use the payload's POS Profile (required).

	Only POS document types are accepted. When ``name`` is given, the document
	must exist and have been saved under that same profile; a blank stored
	profile (e.g. a Desk draft) is accepted only for users who can write POS
	Profile. "Missing" and "not yours" share one message, so a caller cannot
	probe which names exist.
	"""
	if not isinstance(payload, dict):
		frappe.throw(_("Invalid invoice format"), frappe.PermissionError)
	pos_profile = payload.get("pos_profile")
	if not isinstance(pos_profile, str):
		pos_profile = None
	validate_pos_profile_access(pos_profile, frappe.PermissionError)

	doctype = payload.get("doctype") or DOCTYPE_SALES_INVOICE
	if doctype not in POS_DOCUMENT_DOCTYPES:
		frappe.throw(_("Invalid invoice format"), frappe.PermissionError)
	name = payload.get("name")
	if name is None or name == "":
		return
	if not isinstance(name, str):
		frappe.throw(_("Invalid invoice format"), frappe.PermissionError)

	stored = None
	if frappe.get_meta(doctype).has_field("pos_profile"):
		stored = frappe.db.get_value(doctype, name, ["name", "pos_profile"], as_dict=True)
	else:
		stored = frappe.db.get_value(doctype, name, ["name"], as_dict=True)
	if isinstance(stored, str):
		if stored != pos_profile:
			frappe.throw(_("This document cannot be changed from this POS Profile."), frappe.PermissionError)
		return
	if stored and not stored.get("pos_profile") and frappe.has_permission("POS Profile", "write"):
		return
	if not stored or stored.get("pos_profile") != pos_profile:
		frappe.throw(_("This document cannot be changed from this POS Profile."), frappe.PermissionError)


def _set_payment_collected_flag(invoice_doc, payments):
	"""Flag the save when the payload carries money (payments summing to > 0).

	Benefit engines read ``flags.pos_payment_collected`` to freeze a paid
	invoice's discounts instead of silently changing its totals.
	"""
	total = sum(flt(row.get("amount")) for row in (payments or []) if isinstance(row, dict))
	invoice_doc.flags.pos_payment_collected = total > 0


def _set_paid_draft_flag(invoice_doc, paid_draft_header, paid_draft_rates=None):
	"""Flag the save as a stored paid draft keeping the header it held (Ruling 99).

	Set only when the stored draft carried a payment and a header above one currency
	unit (``paid_draft_header``, see ``_paid_draft_header``), and this save's header
	(after ``calculate_taxes_and_totals``) is no larger than it, as an amount and as a
	share of the total before it: Ruling 90 applied to the whole header. Benefit engines
	read ``flags.pos_paid_draft`` to log, not refuse, that header (Ruling 97); any other
	save gets no flag, so their online rules apply. pos_next's own coupon valuation is no
	bound here (it counts F&F lines). The rows must also be the held ones, at rates no
	lower (``_keeps_held_rows``, Ruling 100). Always assigned, so a stale value never survives.
	"""
	invoice_doc.flags.pos_paid_draft = _keeps_held_header(invoice_doc, paid_draft_header, paid_draft_rates)


def _keeps_held_rows(invoice_doc, held_rates) -> bool:
	"""Every paid row is an (item, UOM) the stored paid draft held, at a rate no lower
	(``held_rates``, see ``_paid_draft_rates``): the header stays on the lines it was
	earned on (Ruling 100). A smaller quantity of the same rows keeps it."""
	tolerance = 10 ** -cint(_currency_precision(invoice_doc.get("currency")))
	for row in invoice_doc.get("items") or []:
		if not row.get("item_code") or cint(row.get("is_free_item")) or flt(row.qty) <= 0:
			continue
		held_rate = (held_rates or {}).get((row.item_code, row.get("uom")))
		if held_rate is None or flt(row.rate) < held_rate - tolerance:
			return False
	return True


def _keeps_held_header(invoice_doc, held, held_rates) -> bool:
	if held is None or invoice_doc.get("is_return") or not _keeps_held_rows(invoice_doc, held_rates):
		return False
	tolerance = 10 ** -cint(_currency_precision(invoice_doc.get("currency")))
	if flt(held[0]) <= tolerance:
		return False
	header = flt(invoice_doc.get("discount_amount"))
	apply_discount_on = cstr(invoice_doc.get("apply_discount_on")) or "Grand Total"
	base = _header_discount_bases(invoice_doc).get(apply_discount_on) or 0
	return header <= flt(held[0]) + tolerance and header <= flt(held[1]) * base + tolerance


def _apply_pos_sales_team(invoice_doc, sales_team_data=None, pos_profile=None):
	"""
	Resolve item-level + invoice-level Sales Persons into Sales Invoice.sales_team.

	- Lines with ``sales_person`` keep that SP at 100% of the line.
	- Uncovered lines fall back to ``sales_team_data`` (invoice-level team).
	- Rebuilds allocated_percentage / incentives using Item / Item Group / Brand rates.

	``sales_team_data`` must be the cashier / payment-screen team (or ``[]`` / ``None``).
	Never pass the rebuilt aggregate from a draft invoice — that would treat item-level
	SPs as invoice-level fallbacks. ``None`` means no invoice-level team (``[]``).

	Offline sync (``invoice_doc.flags.pos_offline_sync``): the sale already happened
	on the till, where the POS lets cashiers finish without a Sales Person. Never
	reject it here, or the invoice would be stuck in the offline queue forever.
	The required / allowlist checks are skipped, Sales Persons deleted since are
	dropped, and disabled ones are kept so commission lands on whoever made the sale.
	"""
	from pos_next.pos_next.utils.sales_person_commission import (
		apply_return_sales_person_from_original,
		apply_sales_team_to_invoice,
		build_sales_team_from_items,
		clear_sales_person_fields,
		drop_missing_sales_persons,
		original_has_sales_attribution,
		persist_invoice_level_sales_team,
		sales_persons_enabled,
		validate_sales_person_assignments,
		validate_sales_person_coverage,
	)

	profile = pos_profile or invoice_doc.get("pos_profile")
	is_return = bool(invoice_doc.get("is_return") and invoice_doc.get("return_against"))

	# Feature disabled → strip any client-supplied SP fields (do not build commission).
	# Exception: a return whose original sale carried sales persons still mirrors
	# them, so the commission earned on the sale is reversed.
	if not sales_persons_enabled(profile) and not (
		is_return and original_has_sales_attribution(invoice_doc.return_against)
	):
		clear_sales_person_fields(invoice_doc)
		return

	if is_return:
		# Returns: lock sales_person (and invoice-level team) to the original sale.
		# No "Sales Person is required" check: a reversal mirrors whatever the
		# original had — including nothing (sold before the feature was enabled,
		# while it was Disabled, or offline without a Sales Person). Deleted SPs
		# are dropped; disabled ones are kept so their commission is reversed.
		apply_return_sales_person_from_original(invoice_doc)
		invoice_level = drop_missing_sales_persons(
			invoice_doc,
			getattr(invoice_doc.flags, "pos_invoice_level_sales_team", None) or [],
		)
		invoice_doc.flags.pos_allow_disabled_sales_persons = True
	else:
		# Explicit cashier team only — never fall back to rebuilt doc.sales_team
		invoice_level = sales_team_data if sales_team_data is not None else []

		if invoice_doc.flags.pos_offline_sync:
			invoice_level = drop_missing_sales_persons(invoice_doc, invoice_level)
			invoice_doc.flags.pos_allow_disabled_sales_persons = True
		else:
			validate_sales_person_coverage(
				invoice_doc,
				pos_profile=profile,
				invoice_level_team=invoice_level,
			)
			validate_sales_person_assignments(
				invoice_doc,
				pos_profile=profile,
				invoice_level_team=invoice_level,
			)

	# Remember invoice-level fallback so calculate_contribution can rebuild correctly
	invoice_doc.flags.pos_invoice_level_sales_team = invoice_level
	# Persist cashier team (not the rebuilt aggregate) for accurate return reversal
	if not is_return:
		persist_invoice_level_sales_team(invoice_doc, invoice_level)

	rows = build_sales_team_from_items(invoice_doc, invoice_level_team=invoice_level)
	apply_sales_team_to_invoice(invoice_doc, rows)


def _resolve_submit_invoice_level_team(invoice, data, invoice_name=None):
	"""Cashier invoice-level team for submit.

	Prefer ``data.sales_team`` (online flow). Offline sync stores the cashier team on
	the invoice payload and sends ``data: {}`` — accept ``invoice.sales_team`` only
	when ``offline_id`` is present (never for online drafts whose sales_team is the
	rebuilt aggregate).

	Otherwise (older clients, or callers that submit a saved draft without resending
	the team) fall back to the cashier team persisted on the draft
	(``custom_pos_invoice_level_sales_team``). Without that fallback the invoice-level
	sales persons would be silently dropped, or the submit rejected as having none.
	"""
	from pos_next.pos_next.utils.sales_person_commission import load_stored_invoice_level_sales_team

	if isinstance(data, dict) and isinstance(data.get("sales_team"), list):
		return data.get("sales_team")
	if invoice.get("offline_id") and isinstance(invoice.get("sales_team"), list):
		return invoice.get("sales_team")
	stored = load_stored_invoice_level_sales_team(invoice_name or invoice.get("name"))
	return stored if stored is not None else []


def get_payment_account(mode_of_payment, company):
	"""
	Get account for mode of payment.
	Tries multiple fallback methods to find a suitable account.
	"""
	# Try 1: Mode of Payment Account table
	account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)
	if account:
		return {"account": account}

	# Try 2: POS Payment Method from POS Profile
	account = frappe.db.sql(
		"""
		SELECT ppm.default_account
		FROM `tabPOS Payment Method` ppm
		INNER JOIN `tabPOS Profile` pp ON ppm.parent = pp.name
		WHERE ppm.mode_of_payment = %s
		AND pp.company = %s
		AND ppm.default_account IS NOT NULL
		LIMIT 1
	""",
		(mode_of_payment, company),
		as_dict=1,
	)

	if account and account[0].default_account:
		return {"account": account[0].default_account}

	# Try 3: Company default cash account (for cash payments)
	if "cash" in mode_of_payment.lower():
		account = frappe.get_value("Company", company, "default_cash_account")
		if account:
			return {"account": account}

	# Try 4: Company default bank account
	account = frappe.get_value("Company", company, "default_bank_account")
	if account:
		return {"account": account}

	# Try 5: Any Cash/Bank account for the company
	account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": ["in", ["Cash", "Bank"]], "is_group": 0},
		"name",
	)
	if account:
		return {"account": account}

	# No account found - throw error
	frappe.throw(
		_(
			"Please set default Cash or Bank account in Mode of Payment {0} or set default accounts in Company {1}"
		).format(mode_of_payment, company),
		title=_("Missing Account"),
	)


def _validate_receivable_account(account, company, pos_profile):
	"""Validate a cashier-selected receivable account for "Pay on Receivable Account".

	Ensures the account is a real, enabled, non-group Receivable account belonging to the
	POS company, and that credit sales are enabled for the profile (the same gate that
	governs the existing "Pay on Account" button). Raises on any violation so a tampered
	client cannot force an arbitrary debit_to.
	"""
	if not account:
		return

	if not company:
		frappe.throw(_("Company is required to set a receivable account"))

	acc = frappe.db.get_value(
		"Account",
		account,
		["company", "account_type", "is_group", "disabled"],
		as_dict=True,
	)
	if not acc:
		frappe.throw(_("Receivable account {0} does not exist").format(account))
	if acc.company != company:
		frappe.throw(_("Receivable account {0} does not belong to company {1}").format(account, company))
	if acc.account_type != "Receivable":
		frappe.throw(_("Account {0} is not a Receivable account").format(account))
	if cint(acc.is_group):
		frappe.throw(_("Receivable account {0} is a group account").format(account))
	if cint(acc.disabled):
		frappe.throw(_("Receivable account {0} is disabled").format(account))

	allow_credit_sale = cint(
		frappe.db.get_value(DOCTYPE_POS_SETTINGS, {"pos_profile": pos_profile}, "allow_credit_sale")
	)
	if not allow_credit_sale:
		frappe.throw(_("Credit sales are not enabled for this POS Profile."))


def _set_payment_accounts(payments, company):
	"""Set the account for each payment entry that is missing one.

	Handles both Document objects (from invoice_doc.payments) and plain dicts
	(from frontend data).  Document objects use BaseDocument.set() which writes
	directly to __dict__, while plain dicts use normal key assignment.
	"""
	if not payments or not company:
		return

	for payment in payments:
		mode_of_payment = payment.get("mode_of_payment")
		if not mode_of_payment or payment.get("account"):
			continue
		try:
			account_info = get_payment_account(mode_of_payment, company)
			if account_info:
				account = account_info.get("account")
				if hasattr(payment, "set") and callable(payment.set):
					payment.set("account", account)
				else:
					payment["account"] = account
		except Exception as e:
			frappe.log_error(
				f"Failed to get payment account for {mode_of_payment}: {e}",
				"Payment Account Lookup",
			)


def _validate_payment_account_not_debit_to(invoice_doc):
	"""Reject payment modes mapped to the same account as the invoice receivable."""
	if not invoice_doc.get("payments"):
		return

	debit_to = invoice_doc.get("debit_to")
	if not debit_to and invoice_doc.get("customer") and invoice_doc.get("company"):
		from erpnext.accounts.party import get_party_account

		debit_to = get_party_account("Customer", invoice_doc.customer, invoice_doc.company)

	if not debit_to:
		return

	for payment in invoice_doc.payments:
		if not payment.get("account") or not flt(payment.get("amount")):
			continue
		if payment.account == debit_to:
			frappe.throw(
				_(
					"Mode of Payment {0} uses account {1}, which is the same as the invoice receivable account. "
					"Please set a Cash or Bank account on the Mode of Payment."
				).format(payment.mode_of_payment, debit_to),
				title=_("Invalid Payment Account"),
			)


def _ensure_invoice_customer(invoice_doc, pos_profile=None):
	"""Ensure POS Sales Invoice has a customer for Receivable GL entries (debit_to).

	Falls back to the POS Profile default customer when the cashier did not
	select one explicitly.
	"""
	from pos_next.overrides.sales_invoice import _resolve_pos_customer

	customer = _resolve_pos_customer(invoice_doc)
	if customer:
		invoice_doc.customer = customer
		if not invoice_doc.get("customer_name"):
			invoice_doc.customer_name = frappe.db.get_value("Customer", customer, "customer_name")
		return

	frappe.throw(
		_("Customer is required. Please select a customer or configure a default customer in POS Profile."),
		title=_("Customer Required"),
	)


def _apply_pos_item_accounting_dimensions(invoice_doc):
	"""Stamp the invoice customer on every Sales Invoice Item row of a POS invoice.

	Always overwrite (not only blank rows): a draft re-saved with a different
	customer would otherwise keep the previous customer on existing rows, and
	that stale value would flow into item-level GL entries when a Customer
	accounting dimension is configured.
	"""
	if invoice_doc.doctype != "Sales Invoice" or not cint(invoice_doc.get("is_pos")):
		return

	item_meta = frappe.get_meta("Sales Invoice Item", cached=True)
	if not item_meta.has_field("customer"):
		return

	customer = invoice_doc.get("customer")
	if not customer:
		return

	for item in invoice_doc.get("items") or []:
		if item.get("customer") != customer:
			item.customer = customer


def _validate_customer_for_receivable_payments(invoice_doc):
	"""Require a customer when any payment mode uses a Receivable account."""
	if not invoice_doc.get("payments") or invoice_doc.get("customer"):
		return

	company = invoice_doc.get("company")
	for payment in invoice_doc.payments:
		account = payment.get("account")
		if not account and payment.get("mode_of_payment") and company:
			try:
				account_info = get_payment_account(payment.mode_of_payment, company)
				account = account_info.get("account") if account_info else None
			except Exception:
				continue

		if not account:
			continue

		account_type = frappe.get_cached_value("Account", account, "account_type")
		if account_type == "Receivable":
			frappe.throw(
				_("Customer is required when paying with {0}").format(payment.get("mode_of_payment")),
				title=_("Customer Required"),
			)


# ==========================================
# Stock Validation Functions
# ==========================================


def _get_available_stock(item):
	"""Return available stock qty for an item row."""
	warehouse = item.get("warehouse")
	batch_no = item.get("batch_no")
	item_code = item.get("item_code")

	if not item_code or not warehouse:
		return 0

	if batch_no:
		return get_batch_qty(batch_no, warehouse) or 0

	# Get stock from Bin
	bin_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	return flt(bin_qty) or 0


def _collect_stock_errors(items):
	"""Return list of items exceeding available stock.

	Sums qty per (item_code, warehouse, batch_no) so:
	- paid + free rows of the same SKU (and same batch) are checked together
	- different products are never combined
	- different batches of the same SKU are checked against their own batch qty
	  (aggregating only by item+warehouse would compare total demand to one
	  sample batch and allow overselling other batches)

	Respects per-item allow_negative_stock if the field exists on Item.
	"""
	allowed_items = _get_item_negative_stock_allow_set(items)
	requested_by_key = {}
	sample_by_key = {}
	for d in items:
		if flt(d.get("qty")) < 0:
			continue
		item_code = d.get("item_code")
		warehouse = d.get("warehouse")
		if not item_code or not warehouse:
			continue
		requested = flt(d.get("stock_qty") or (flt(d.get("qty")) * flt(d.get("conversion_factor") or 1)))
		batch_no = d.get("batch_no") or ""
		key = (item_code, warehouse, batch_no)
		requested_by_key[key] = requested_by_key.get(key, 0) + requested
		sample_by_key[key] = d

	errors = []
	for key, requested in requested_by_key.items():
		item_code, warehouse, batch_no = key
		if item_code in allowed_items:
			continue
		sample = sample_by_key[key]
		available = _get_available_stock(sample)
		if requested > available:
			error = {
				"item_code": item_code,
				"warehouse": warehouse,
				"requested_qty": requested,
				"available_qty": available,
			}
			if batch_no:
				error["batch_no"] = batch_no
			errors.append(error)

	return errors


@lru_cache(maxsize=1)
def _item_has_allow_negative_stock_field():
	"""Check whether Item doctype has an allow_negative_stock field."""
	try:
		return frappe.get_meta("Item").has_field("allow_negative_stock")
	except Exception:
		return False


def _get_item_negative_stock_allow_set(items):
	"""Return set of item codes that allow negative stock at Item level."""
	if not items or not _item_has_allow_negative_stock_field():
		return set()

	item_codes = list({d.get("item_code") for d in items if d.get("item_code")})
	if not item_codes:
		return set()

	return set(
		frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes], "allow_negative_stock": 1},
			pluck="name",
		)
		or []
	)


def _should_block(pos_profile):
	"""Check if sale should be blocked for insufficient stock."""
	# First check global ERPNext Stock Settings
	allow_negative = cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0)
	if allow_negative:
		return False

	# Check POS Settings for the specific profile
	if pos_profile:
		# Check if POS Settings allows negative stock
		pos_settings_allow_negative = cint(
			frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "allow_negative_stock") or 0
		)
		if pos_settings_allow_negative:
			return False

		# Try to get custom field (may not exist in vanilla ERPNext)
		block_sale = cint(
			frappe.db.get_value("POS Profile", pos_profile, "posa_block_sale_beyond_available_qty") or 1
		)
		return bool(block_sale)

	# Default to blocking if no profile specified
	return True


def _validate_stock_on_invoice(invoice_doc):
	"""Validate stock availability before submission."""
	if invoice_doc.doctype == "Sales Invoice" and not cint(getattr(invoice_doc, "update_stock", 0)):
		return

	# Collect all stock items to check
	items_to_check = [d.as_dict() for d in invoice_doc.items if d.get("is_stock_item")]

	# Include packed items if present
	if hasattr(invoice_doc, "packed_items"):
		items_to_check.extend([d.as_dict() for d in invoice_doc.packed_items])

	# Check for stock errors
	errors = _collect_stock_errors(items_to_check)

	# Throw error if stock insufficient and blocking is enabled
	if errors and _should_block(invoice_doc.pos_profile):
		frappe.throw(frappe.as_json({"errors": errors}), frappe.ValidationError)


def _auto_set_return_batches(invoice_doc):
	"""Assign batch numbers for return invoices without a source invoice.

	When an item requires a batch number, this function allocates the first
	available batch in FIFO order. If no batches exist in the selected
	warehouse, an informative error is raised.
	"""
	if not invoice_doc.get("is_return") or invoice_doc.get("return_against"):
		return

	for d in invoice_doc.items:
		if not d.get("item_code") or not d.get("warehouse"):
			continue

		has_batch = frappe.db.get_value("Item", d.item_code, "has_batch_no")
		if has_batch and not d.get("batch_no"):
			batch_list = get_batch_qty(item_code=d.item_code, warehouse=d.warehouse) or []
			batch_list = [b for b in batch_list if flt(b.get("qty")) > 0]

			if batch_list:
				# FIFO: batches are already sorted by posting/expiry in ERPNext
				d.batch_no = batch_list[0].get("batch_no")
			else:
				frappe.throw(_("No batches available in {0} for {1}.").format(d.warehouse, d.item_code))


# ==========================================
# Validation Functions
# ==========================================


@frappe.whitelist()
def validate_cart_items(items, pos_profile=None):
	"""Validate cart items for available stock.

	Returns a list of item dicts where requested quantity exceeds availability.
	This can be used on the front-end for pre-submission checks.
	"""
	ensure_desk_user()
	if pos_profile:
		ensure_pos_user(pos_profile)
	if isinstance(items, str):
		items = json.loads(items)

	if pos_profile and not frappe.db.exists("POS Profile", pos_profile):
		pos_profile = None

	if not _should_block(pos_profile):
		return []

	errors = _collect_stock_errors(items)
	if not errors:
		return []

	return errors


# Child-row field that links a return row to its original row, per invoice doctype.
RETURN_ROW_LINK_FIELD = {"Sales Invoice": "sales_invoice_item", "POS Invoice": "pos_invoice_item"}
# A refund may differ from a return's total by its rounding plus a cent a row
# (the dialog rounds each row); more than that is refused (D-R2-16).
RETURN_REFUND_TOLERANCE = 0.01


def _currency_precision(currency):
	"""Decimal places for money in ``currency`` (from its number format, not System Settings)."""
	from frappe.utils import get_number_format_info

	number_format = (
		(currency and frappe.db.get_value("Currency", currency, "number_format", cache=True))
		or frappe.db.get_default("number_format")
		or "#,###.##"
	)
	return get_number_format_info(number_format)[2]


@frappe.whitelist()
def validate_return_items(original_invoice_name, return_items, doctype="Sales Invoice"):
	"""Ensure that return items do not exceed the quantity from the original invoice.
	Also validates return time frame based on POS Settings.

	Every return row must link to its original row (``sales_invoice_item`` /
	``pos_invoice_item``) and must not be refunded above that row's rate.

	Uses query builder for parameterized queries. Fetches invoice details, original
	item quantities, and already-returned quantities in 3 queries total.
	"""
	ensure_desk_user()
	if doctype not in ALLOWED_RETURN_DOCTYPES:
		frappe.throw(_("Invalid invoice doctype"), frappe.PermissionError)
	from frappe.query_builder.functions import Abs, Sum
	from frappe.utils import date_diff, getdate

	if isinstance(return_items, str):
		return_items = json.loads(return_items)

	if doctype not in RETURN_ROW_LINK_FIELD:
		return {"valid": False, "message": _("Returns are not supported for {0}").format(doctype)}
	link_field = RETURN_ROW_LINK_FIELD[doctype]

	# Fetch invoice pos_profile, posting_date and currency for validation
	si = frappe.qb.DocType(doctype)
	invoice_data = (
		frappe.qb.from_(si)
		.select(si.pos_profile, si.posting_date, si.currency)
		.where(si.name == original_invoice_name)
	).run(as_dict=True)

	if not invoice_data:
		return {"valid": False, "message": _("Invoice {0} not found").format(original_invoice_name)}

	invoice_info = invoice_data[0]

	# Check return validity period from POS Settings
	if invoice_info.pos_profile:
		return_validity_days = cint(
			frappe.db.get_value(
				"POS Settings", {"pos_profile": invoice_info.pos_profile}, "return_validity_days"
			)
			or 0
		)

		if return_validity_days > 0:
			days_since_invoice = date_diff(getdate(nowdate()), getdate(invoice_info.posting_date))
			if days_since_invoice > return_validity_days:
				return {
					"valid": False,
					"message": _(
						"Return period has expired. Invoice {0} was created {1} days ago. "
						"Returns are only allowed within {2} days of purchase."
					).format(original_invoice_name, days_since_invoice, return_validity_days),
				}

	# Aggregate original item quantities by item_code and by row name
	si_item = frappe.qb.DocType(f"{doctype} Item")
	original_items = (
		frappe.qb.from_(si_item)
		.select(si_item.name, si_item.item_code, si_item.qty, si_item.rate)
		.where(si_item.parent == original_invoice_name)
	).run(as_dict=True)

	# Aggregate quantities already returned from previous return invoices
	ret_si = frappe.qb.DocType(doctype)
	ret_item = frappe.qb.DocType(f"{doctype} Item")

	returned_qty_data = (
		frappe.qb.from_(ret_si)
		.inner_join(ret_item)
		.on(ret_item.parent == ret_si.name)
		.select(
			ret_item.item_code,
			getattr(ret_item, link_field),
			Sum(Abs(ret_item.qty)).as_("returned_qty"),
		)
		.where(
			(ret_si.return_against == original_invoice_name)
			& (ret_si.docstatus == 1)
			& (ret_si.is_return == 1)
		)
		.groupby(ret_item.item_code, getattr(ret_item, link_field))
	).run(as_dict=True)

	return _check_return_quantities(
		original_invoice_name,
		original_items,
		returned_qty_data,
		return_items,
		link_field=link_field,
		precision=_currency_precision(invoice_info.currency),
	)


def _check_return_quantities(
	original_invoice_name,
	original_items,
	returned_qty_data,
	return_items,
	link_field="sales_invoice_item",
	precision=2,
):
	"""Pure row / item quantity and rate checks for ``validate_return_items`` (no DB access).

	``original_items``: rows of the original invoice (name, item_code, qty, rate).
	``returned_qty_data``: already-returned qty grouped by (item_code, ``link_field``).
	``return_items``: the new return's rows (item_code, qty, rate, ``link_field``).
	``precision``: money precision of the invoice currency, used for the rate check.
	"""
	original_item_qty = {}
	original_row_qty = {}
	original_row_item = {}
	original_row_rate = {}
	for item in original_items:
		original_item_qty[item.item_code] = original_item_qty.get(item.item_code, 0) + flt(item.qty)
		original_row_qty[item.name] = flt(item.qty)
		original_row_item[item.name] = item.item_code
		original_row_rate[item.name] = flt(item.get("rate"))

	# Subtract returned quantities (by row when linked, else by item_code)
	for row in returned_qty_data:
		qty = flt(row.returned_qty)
		linked_row = row.get(link_field)
		if linked_row and linked_row in original_row_qty:
			original_row_qty[linked_row] -= qty
		if row.item_code in original_item_qty:
			original_item_qty[row.item_code] -= qty

	# Validate new return items
	for position, item in enumerate(return_items, start=1):
		item_code = item.get("item_code")
		return_qty = abs(flt(item.get("qty", 0)))
		row_ref = item.get(link_field)
		row_no = item.get("idx") or position

		# Every return row must point at the original row it refunds: the row
		# fixes both the quantity left and the rate the customer actually paid.
		if not row_ref:
			return {
				"valid": False,
				"message": _("Row #{0}: return item {1} is not linked to a row of invoice {2}").format(
					row_no, item_code, original_invoice_name
				),
			}

		if row_ref not in original_row_item:
			return {
				"valid": False,
				"message": _("Return item link {0} does not belong to invoice {1}").format(
					row_ref, original_invoice_name
				),
			}
		if item_code and original_row_item[row_ref] != item_code:
			return {
				"valid": False,
				"message": _("Return item {0} does not match original row {1} ({2})").format(
					item_code, row_ref, original_row_item[row_ref]
				),
			}
		# ERPNext skips its own rate check for Moving Average items, so the
		# POS checks every row here, whatever the valuation method.
		return_rate = flt(abs(flt(item.get("rate"))), precision)
		original_rate = flt(original_row_rate[row_ref], precision)
		if return_rate > original_rate:
			return {
				"valid": False,
				"message": _(
					"Row #{0}: return rate {1} for item {2} is higher than the rate {3} it was sold at"
				).format(row_no, return_rate, item_code, original_rate),
			}

		remaining_row = original_row_qty.get(row_ref, 0)
		if return_qty > remaining_row:
			return {
				"valid": False,
				"message": _(
					"You are trying to return more quantity for item {0} than remains on that line."
				).format(item_code),
			}
		original_row_qty[row_ref] = remaining_row - return_qty

		remaining = original_item_qty.get(item_code, 0)
		if return_qty > remaining:
			return {
				"valid": False,
				"message": _("You are trying to return more quantity for item {0} than was sold.").format(
					item_code
				),
			}
		original_item_qty[item_code] = remaining - return_qty

	return {"valid": True}


SALES_ORDERS_ONLY_LOG_TITLE = "Sales Invoice synced under Create Only Sales Order"


def _enforce_sales_orders_only(payload, offline_sync=False):
	"""POS Settings "Create Only Sales Order": the POS makes no Sales Invoice (H2 round 1, I-2).

	An online sale is refused. A sale synced from offline already happened: it is kept
	and logged under a fixed title, never stranded in the queue. Returns are not sales
	and are left alone.
	"""
	if (payload.get("doctype") or DOCTYPE_SALES_INVOICE) != DOCTYPE_SALES_INVOICE:
		return
	pos_profile = payload.get("pos_profile")
	if not pos_profile or not cint(
		frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "create_only_sales_order")
	):
		return
	is_return = payload.get("is_return")
	name = payload.get("name")
	if not is_return and name and frappe.db.exists(DOCTYPE_SALES_INVOICE, name):
		is_return = frappe.db.get_value(DOCTYPE_SALES_INVOICE, name, "is_return")
	if cint(is_return):
		return
	if offline_sync:
		log_error_without_telemetry(
			SALES_ORDERS_ONLY_LOG_TITLE,
			f"POS Profile {pos_profile}: offline sale {payload.get('offline_id') or name or '-'} "
			"was synced as a Sales Invoice while Create Only Sales Order is on; it is kept.",
		)
		return
	frappe.throw(
		_(
			"Only Sales Orders are made on POS Profile {0}: Create Only Sales Order is on in its POS Settings."
		).format(pos_profile),
		title=_("Sales Orders Only"),
	)


def _refuse_return_if_disallowed(pos_profile):
	"""Throw unless POS Settings "Allow Return" is on for ``pos_profile`` (D-R3-10).

	The server is the authority: a client that ignores the setting is refused. A
	profile with no POS Settings row has returns on, as the field and the POS
	default it.
	"""
	value = (
		frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "allow_return")
		if pos_profile
		else 0
	)
	allowed = 1 if value is None else cint(value)
	if not allowed:
		frappe.throw(
			_("Returns are not allowed on POS Profile {0}: Allow Return is off in its POS Settings.").format(
				pos_profile or ""
			),
			title=_("Returns Not Allowed"),
		)


def _mirror_return_free_rows(invoice_doc):
	"""A return row takes ``is_free_item`` from the original row it returns (D-R3-05).

	The return dialog rebuilds its rows without the flag, so a returned free row was
	saved as a paid row at rate 0. The original row is the authority, both ways.
	"""
	link_field = RETURN_ROW_LINK_FIELD.get(invoice_doc.doctype)
	if not (link_field and invoice_doc.get("return_against")):
		return
	linked = [row.get(link_field) for row in invoice_doc.get("items", []) if row.get(link_field)]
	if not linked:
		return
	free = {
		row.name: cint(row.is_free_item)
		for row in frappe.get_all(
			f"{invoice_doc.doctype} Item",
			filters={
				"parent": invoice_doc.return_against,
				"parenttype": invoice_doc.doctype,
				"name": ["in", linked],
			},
			fields=["name", "is_free_item"],
		)
	}
	for row in invoice_doc.get("items", []):
		if row.get(link_field) in free:
			row.is_free_item = free[row.get(link_field)]


def _validate_return_rows(invoice_doc):
	"""Throw unless every row of a return against an invoice passes ``validate_return_items``."""
	if not invoice_doc.get("return_against"):
		return
	validation = validate_return_items(
		invoice_doc.return_against,
		[d.as_dict() for d in invoice_doc.items],
		doctype=invoice_doc.doctype,
	)
	if not validation.get("valid"):
		frappe.throw(validation.get("message"))


# ==========================================
# Invoice Management (Two-Step Flow)
# ==========================================


@frappe.whitelist()
def update_invoice(data: str | dict) -> dict:
	"""Create or update invoice draft (Step 1)."""
	ensure_desk_user()
	return _update_invoice(data)


def _update_invoice(data: str | dict, offline_sync: bool = False, submitting: bool = False) -> dict:
	"""Create or update an invoice draft.

	``submitting``: set by ``submit_invoice``, which submits this draft in the same call:
	its F&F rows are judged here on the computed rate, never left to promotions
	(Ruling 128).

	``offline_sync``: set only by ``submit_invoice`` for an offline sale it reserved
	for sync (a new ``offline_id``, or a retry with no completed invoice); free-row
	problems are then only logged.
	A client-sent ``offline_id`` alone never makes this check lenient.
	"""
	# Before the try: a refused profile is not an "Update Invoice Error".
	data = json.loads(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		frappe.throw(_("Invalid invoice format"))
	_validate_invoice_profile(data)
	if not submitting:
		# submit_invoice checks its own payload (and knows whether it is an offline sync)
		_enforce_sales_orders_only(data)
	try:
		data = _strip_server_managed_fields(data)
		doctype = data.get("doctype") or DOCTYPE_SALES_INVOICE
		pos_profile = data.get("pos_profile")

		# Normalize pricing_rules before document creation
		standardize_pricing_rules(data.get("items"))

		# Create or update invoice
		paid_draft_free, stored_sources, paid_draft_rates, paid_draft_header = {}, set(), {}, None
		paid_draft_rows = []
		if data.get("name"):
			invoice_doc = _ensure_invoice_draft_access(
				data.get("name"),
				pos_profile=pos_profile,
				doctype=doctype,
				raise_on_submitted=frappe.DocstatusTransitionError,
			)
			pos_profile = pos_profile or invoice_doc.get("pos_profile")
			paid_draft_free = _paid_draft_free_qty(invoice_doc)
			stored_sources = _stored_line_sources(invoice_doc)
			paid_draft_rates = _paid_draft_rates(invoice_doc)
			paid_draft_rows = _paid_draft_rows(invoice_doc)
			paid_draft_header = _paid_draft_header(invoice_doc)
			update_data = {k: v for k, v in data.items() if k not in ("name", "doctype")}
			invoice_doc.update(update_data)
		else:
			ensure_pos_user(pos_profile)
			invoice_doc = frappe.get_doc(data)

		_ensure_opening_shift_for_invoice(
			data.get("posa_pos_opening_shift") or invoice_doc.get("posa_pos_opening_shift"),
			pos_profile,
		)

		# A pos_next API save: its rule tags are the server's (sales_invoice_hooks,
		# Ruling 140, blanks only those of a Desk copy).
		invoice_doc.flags.pos_next_api = True
		# Important: set before set_missing_values()/pricing/validation paths that may
		# read linked docs (e.g., Customer) and trigger controller permission checks.
		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		# Offline-queued sale being synced (see _apply_pos_sales_team)
		invoice_doc.flags.pos_offline_sync = bool(data.get("offline_id"))
		invoice_doc.flags.pos_submitting = submitting
		_set_payment_collected_flag(invoice_doc, data.get("payments"))

		pos_profile_doc = None
		if pos_profile:
			try:
				pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
			except Exception:
				frappe.throw(_("Unable to load POS Profile {0}").format(pos_profile))

			invoice_doc.pos_profile = pos_profile

			if pos_profile_doc:
				if pos_profile_doc.company:
					invoice_doc.company = pos_profile_doc.company
				if pos_profile_doc.currency and not invoice_doc.get("currency"):
					invoice_doc.currency = pos_profile_doc.currency

				# Copy accounting dimensions from POS Profile
				if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
					invoice_doc.branch = pos_profile_doc.branch
					# Also set branch on all items for GL entries
					for item in invoice_doc.get("items", []):
						item.branch = pos_profile_doc.branch

		company = invoice_doc.get("company") or (pos_profile_doc.company if pos_profile_doc else None)

		if company and invoice_doc.get("payments") and doctype == "Sales Invoice":
			_set_payment_accounts(invoice_doc.payments, company)

		# Ensure customer exists
		customer_name = invoice_doc.get("customer")
		if customer_name and not frappe.db.exists("Customer", customer_name):
			try:
				cust = frappe.get_doc(
					{
						"doctype": "Customer",
						"customer_name": customer_name,
						"customer_group": "All Customer Groups",
						"territory": "All Territories",
						"customer_type": "Individual",
					}
				)
				cust.flags.ignore_permissions = True
				cust.insert()
				invoice_doc.customer = cust.name
				invoice_doc.customer_name = cust.customer_name
			except Exception as e:
				frappe.log_error(f"Failed to create customer {customer_name}: {e}")

		# Customer checks run only after the auto-create above, so a customer typed
		# at the till (not yet in the system) is created rather than rejected.
		if doctype == "Sales Invoice":
			_ensure_invoice_customer(invoice_doc, pos_profile)
			_apply_pos_item_accounting_dimensions(invoice_doc)
			if company and invoice_doc.get("payments"):
				_validate_customer_for_receivable_payments(invoice_doc)
				_validate_payment_account_not_debit_to(invoice_doc)

		# Disable automatic pricing rules (we handle discounts manually from POS)
		invoice_doc.ignore_pricing_rule = 1
		invoice_doc.flags.ignore_pricing_rule = True

		# ========================================================================
		# OPTIMIZATION: Cache POS Settings to avoid repeated DB queries
		# Fetch all needed settings in a single query at the start
		# ========================================================================
		pos_settings_cache = None
		if pos_profile:
			pos_settings_cache = frappe.db.get_value(
				DOCTYPE_POS_SETTINGS,
				{"pos_profile": pos_profile},
				[
					FIELD_ALLOW_USER_TO_EDIT_RATE,
					FIELD_ALLOW_USER_TO_EDIT_ITEM_DISCOUNT,
					FIELD_ALLOW_USER_TO_EDIT_ADDITIONAL_DISCOUNT,
					FIELD_MAX_DISCOUNT_ALLOWED,
					FIELD_ALLOW_NEGATIVE_STOCK,
				],
				as_dict=True,
			)
			# disable_rounded_total is on POS Profile, not POS Settings
			pos_profile_rounded = frappe.db.get_value(
				DOCTYPE_POS_PROFILE, pos_profile, FIELD_DISABLE_ROUNDED_TOTAL
			)
			if pos_settings_cache:
				pos_settings_cache[FIELD_DISABLE_ROUNDED_TOTAL] = pos_profile_rounded
			else:
				pos_settings_cache = {FIELD_DISABLE_ROUNDED_TOTAL: pos_profile_rounded}

		# Pin selling_price_list to POS Profile's authoritative price list when configured
		if pos_profile_doc and pos_profile_doc.get("selling_price_list") and not invoice_doc.get("is_return"):
			invoice_doc.selling_price_list = pos_profile_doc.selling_price_list

		# ========================================================================
		# SERVER-SIDE PRICING & DISCOUNT ENFORCEMENT
		# ========================================================================
		for item in invoice_doc.get("items", []):
			if not cint(invoice_doc.get("is_return")) and flt(item.get("qty")) <= 0:
				frappe.throw(
					_("Quantity for item {0} must be greater than zero").format(item.get("item_code")),
					frappe.ValidationError,
				)
			item_rate = flt(item.rate or 0)
			if not cint(invoice_doc.get("is_return")) and item_rate < 0:
				frappe.throw(
					_("Rate for item {0} cannot be negative").format(item.get("item_code")),
					frappe.ValidationError,
				)
			discount_pct = flt(item.discount_percentage or 0)
			frontend_price_list_rate = flt(item.get("price_list_rate") or 0)
			is_manual_edit = cint(item.get(FIELD_IS_RATE_MANUALLY_EDITED) or 0)

			if is_manual_edit:
				# MANUAL RATE EDIT: preserve original price_list_rate for audit
				original_rate = flt(item.get(FIELD_ORIGINAL_RATE) or item.get(FIELD_PRICE_LIST_RATE) or 0)
				if original_rate > 0:
					item.price_list_rate = original_rate
				# Whether the edit is allowed is decided against the server's list
				# price, flag or not (_check_paid_row_discounts, after the totals).
			else:
				# NORMAL FLOW: Trust frontend's price_list_rate if provided and valid
				if frontend_price_list_rate > 0:
					item.price_list_rate = frontend_price_list_rate
				# Fallback: reverse-calculate if discount exists but no price_list_rate
				elif discount_pct > 0 and discount_pct < 100 and item_rate > 0:
					item.price_list_rate = calculate_price_list_rate(
						item_rate, discount_pct, frontend_price_list_rate
					)
				else:
					# No discount or price_list_rate - use rate as is
					item.price_list_rate = item_rate

				# Ensure price_list_rate is never less than rate (data integrity)
				if flt(item.price_list_rate) < item_rate:
					item.price_list_rate = item_rate

			# IMPORTANT: Keep the rate from frontend (do NOT set to 0)
			# ERPNext will recalculate if needed, but preserving frontend rate
			# prevents rounding issues and ensures UI matches invoice
			#
			# Clearing item.pricing_rules (_reset_row_pricing_rules, after this
			# loop; submit_invoice does the same for an existing draft) avoids
			# ERPNext's remove_pricing_rule_for_item() branch on the 2nd save.

		# Free rows only from offers (a zero-rate row is a free row).
		_check_free_rows_backed(
			invoice_doc,
			offline_sync=offline_sync,
			paid_draft_free=paid_draft_free,
			stored_sources=stored_sources,
		)
		_reset_row_pricing_rules(invoice_doc.get("items", []))

		if doctype == "Sales Invoice":
			_stamp_one_time_item_rules(invoice_doc, _server_free_row_rules(invoice_doc.get("items", [])))

		# Set invoice flags BEFORE calculations
		if doctype == "Sales Invoice":
			invoice_doc.is_pos = 1
			invoice_doc.update_stock = 1
			if pos_profile_doc and pos_profile_doc.warehouse:
				invoice_doc.set_warehouse = pos_profile_doc.warehouse

		# ========================================================================
		# ROUNDING CONFIGURATION
		# ========================================================================
		# Load rounding preference from POS Settings (use cached value)
		# When disabled (0): ERPNext rounds to nearest whole number
		# When enabled (1): Shows exact amount without rounding
		# ========================================================================
		disable_rounded = 1  # Default: disable rounding for POS (show exact amounts)

		if pos_settings_cache and pos_settings_cache.get(FIELD_DISABLE_ROUNDED_TOTAL) is not None:
			disable_rounded = cint(pos_settings_cache.get(FIELD_DISABLE_ROUNDED_TOTAL))

		invoice_doc.disable_rounded_total = disable_rounded

		# ========================================================================
		# POPULATE MISSING FIELDS — using for_validate=True intentionally
		# ========================================================================
		# ERPNext's set_missing_values() calls set_pos_fields() internally.
		#
		# With for_validate=False (the default):
		#   set_pos_fields() -> update_multi_mode_option() which does:
		#     1. doc.set("payments", [])          — wipes ALL payment rows
		#     2. Rebuilds payments from POS Profile template with amount=0
		#   Result: frontend payment amounts are destroyed before the invoice
		#   is saved, causing invoices to appear unpaid (outstanding = grand_total).
		#
		# With for_validate=True:
		#   set_pos_fields() skips update_multi_mode_option() entirely,
		#   and only fills in missing fields (debit_to, currency, write_off_account,
		#   cost_center, etc.) without overwriting values already set.
		#   Payment accounts are set separately via _set_payment_accounts() below.
		#
		# This is safe on all ERPNext versions because POS Next already sets
		# the fields that for_validate=True skips:
		#   - ignore_pricing_rule  → set above (line ~752)
		#   - customer             → sent from frontend
		#   - tax_category         → sent from frontend or not needed
		# ========================================================================
		invoice_doc.set_missing_values(for_validate=True)

		# A return's header discount is worked out here, from the original invoice
		_apply_return_header_discount(invoice_doc)
		# It rounds, and is taxed, like the original; its refund rows are kept
		# before the totals
		_apply_return_rounding(invoice_doc)
		_apply_return_taxes(invoice_doc)
		sent_refund = _sent_return_refund(invoice_doc)

		# Calculate totals and apply discounts (with rounding disabled)
		invoice_doc.calculate_taxes_and_totals()
		# Judge the rates ERPNext computed: no paid row may come out at 0, and
		# none below list price without a reason the server confirms.
		_refuse_zero_rate_after_totals(invoice_doc, lenient=offline_sync)
		_check_paid_row_discounts(invoice_doc, offline_sync=offline_sync, paid_draft_rows=paid_draft_rows)
		_check_header_discount(
			invoice_doc,
			offline_sync=offline_sync,
			paid_draft_header=paid_draft_header,
			paid_draft_rates=paid_draft_rates,
		)
		# After totals: the flag compares this save's header and rows with the draft's.
		_set_paid_draft_flag(invoice_doc, paid_draft_header, paid_draft_rates)

		# Validate return rows after the totals, so the rates checked are the
		# rates that will be saved
		if invoice_doc.get("is_return"):
			_refuse_return_if_disallowed(invoice_doc.get("pos_profile"))
			_mirror_return_free_rows(invoice_doc)
			_validate_return_rows(invoice_doc)
		elif doctype == "Sales Invoice":
			_stamp_one_time_transaction_rules(invoice_doc, pos_profile_doc)
		if invoice_doc.grand_total is None:
			invoice_doc.grand_total = 0.0
		if invoice_doc.base_grand_total is None:
			invoice_doc.base_grand_total = 0.0

		# Set accounts for payment methods before saving
		_set_payment_accounts(invoice_doc.payments, invoice_doc.company)

		# A return refunds its payable total, negative, through the rows sent
		_set_return_refund(invoice_doc, sent_refund)

		# Validate and track POS Coupon if coupon_code is provided
		coupon_code = data.get("coupon_code")
		if coupon_code:
			# Validate POS Coupon exists and is valid
			if frappe.db.table_exists("POS Coupon"):
				from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
					LIMIT_MAXIMUM_USE,
					CouponNotApplicableError,
					check_coupon_code,
					offline_overshoot_allowed,
					resolve_coupon_name,
				)

				if invoice_doc.flags.pos_offline_sync and offline_overshoot_allowed(pos_profile):
					# An offline sale already happened and POS Settings allows it to
					# skip coupon checks: only the code must exist here. On submit the
					# coupon is re-checked, counted, and any skipped check is logged
					# (pos_coupon.count_usage_on_submit).
					coupon_name = resolve_coupon_name(coupon_code)
					if not coupon_name:
						frappe.throw(_("Sorry, this coupon code does not exist"))
					canonical_code = frappe.db.get_value("POS Coupon", coupon_name, "coupon_code")
				else:
					coupon_result = check_coupon_code(
						coupon_code, customer=invoice_doc.customer, company=invoice_doc.company
					)
					if not coupon_result or not coupon_result.get("valid"):
						coupon_result = coupon_result or {}
						if coupon_result.get("reason") == LIMIT_MAXIMUM_USE:
							# Used up since it was applied, e.g. by another cashier (D-R3-08)
							message = _("Coupon {0} has reached its usage limit").format(
								coupon_result.get("code") or coupon_code
							)
						else:
							# check_coupon_code returns its msg already translated
							message = coupon_result.get("msg") or _("Invalid coupon code")
						frappe.throw(message, CouponNotApplicableError, title=_("Coupon Not Applicable"))
					canonical_code = coupon_result["coupon"].coupon_code

				# Store the coupon's own code (canonical case) on the invoice for tracking
				invoice_doc.coupon_code = canonical_code

		# Validate stock availability before saving draft
		# is_stock_item may not be set on unsaved doc items (frontend doesn't send it),
		# so look it up from Item master
		if not invoice_doc.get("is_return") and _should_block(pos_profile):
			item_codes = list({d.item_code for d in invoice_doc.items if d.get("item_code")})
			if item_codes:
				stock_item_set = set(
					frappe.get_all(
						"Item", filters={"name": ["in", item_codes], "is_stock_item": 1}, pluck="name"
					)
				)
				stock_items = [d.as_dict() for d in invoice_doc.items if d.get("item_code") in stock_item_set]
				if stock_items:
					errors = _collect_stock_errors(stock_items)
					if errors:
						frappe.throw(frappe.as_json({"errors": errors}), frappe.ValidationError)

		# Resolve item-level + invoice-level sales persons into sales_team.
		# Use only the cashier payload team — never the (possibly rebuilt) doc.sales_team.
		if doctype == "Sales Invoice":
			_apply_pos_sales_team(
				invoice_doc,
				sales_team_data=data.get("sales_team") if isinstance(data.get("sales_team"), list) else [],
				pos_profile=pos_profile,
			)

		# Save as draft
		if doctype == "Sales Invoice":
			_ensure_invoice_customer(invoice_doc, pos_profile)
			_apply_pos_item_accounting_dimensions(invoice_doc)

		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		invoice_doc.docstatus = 0
		invoice_doc.save()
		if submitting:
			# submit_invoice re-reads this draft to submit it: carry the server's rule names
			# (Ruling 137) to its before_submit by row name.
			rules = {row.name: row.flags.pos_server_rules for row in invoice_doc.get("items") or [] if row.flags.pos_server_rules}
			if rules:
				frappe.flags.pos_server_row_rules = dict(frappe.flags.pos_server_row_rules or {}, **{invoice_doc.name: rules})
		if (
			_carries_payment(invoice_doc)
			and not offline_sync
			and not invoice_doc.flags.pos_offline_sync
			and not submitting
			and not invoice_doc.get("is_return")
		):
			# The paid-row check above passed this paid draft: it is a stored paid draft on
			# every submit route while the database holds it unchanged (Ruling 130).
			_record_checked_paid_draft(invoice_doc)

		result = invoice_doc.as_dict()
		# The F&F decision this save made (promotions' validate hook, when installed): the
		# POS opening payment takes the server's per-line F&F from it (Ruling 101).
		friends_and_family = invoice_doc.flags.get("friends_and_family")
		if isinstance(friends_and_family, dict):
			result["friends_and_family"] = friends_and_family
		return result
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Update Invoice Error")
		raise


PENDING_TIMEOUT_MINUTES = 5  # Pending records older than this are considered stale


def _is_pending_expired(modified_time):
	"""Check if a pending record has expired based on modified time."""
	if not modified_time:
		return True  # No timestamp means treat as expired
	age_minutes = (frappe.utils.now_datetime() - modified_time).total_seconds() / 60
	return age_minutes > PENDING_TIMEOUT_MINUTES


def _reuse_sync_record(sync_record_name):
	"""Reset an existing sync record to Pending status for retry."""
	# Locking read: the row may be newer than this transaction's snapshot.
	sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name, for_update=True)
	sync_doc.status = "Pending"
	sync_doc.synced_at = None
	sync_doc.flags.ignore_permissions = True
	# An order key's row holds a Sales Order name in the link column (F6).
	sync_doc.flags.ignore_links = True
	sync_doc.save()
	return {"already_synced": False, "sync_record_name": sync_record_name}


def _insert_sync_reservation(offline_id, pos_profile=None, customer=None) -> str | None:
	"""Insert a Pending reservation for ``offline_id``; its name, or None when the id is
	already reserved (the unique ``offline_id`` index).

	A plain INSERT takes a record lock on the new row only, no gap lock, so reserving
	one id never waits on another id's open submit (I-3). Inserting an id another open
	transaction reserved waits for that transaction, then fails with a duplicate key
	once it commits (or succeeds if it rolled back).
	"""
	name = frappe.generate_hash(length=10)
	now = frappe.utils.now_datetime()
	user = frappe.session.user
	try:
		frappe.db.sql(
			"""INSERT INTO `tabOffline Invoice Sync`
				(name, creation, modified, owner, modified_by, docstatus, idx,
				offline_id, sales_invoice, status, pos_profile, customer, synced_at)
			VALUES (%s, %s, %s, %s, %s, 0, 0, %s, '', 'Pending', %s, %s, NULL)""",
			(name, now, now, user, user, offline_id, pos_profile, customer),
		)
	except Exception as error:
		if frappe.db.is_duplicate_entry(error):
			return None
		raise
	return name


def _ensure_offline_uniqueness(
	offline_id, pos_profile=None, customer=None, _retry=True, doctype=DOCTYPE_SALES_INVOICE
):
	"""
	Ensure offline invoice uniqueness with race condition protection.

	Uses a reservation pattern, insert first (I-3):
	1. Insert a pending reservation; when the id is new, this request owns it
	2. Otherwise read the existing record with a row lock (a record lock only):
	3. If synced with valid invoice, return existing invoice
	4. If synced but invoice deleted/invalid, allow retry
	5. If pending but expired (>5 min), allow retry
	6. If pending and active, reject (another request processing)
	7. If failed, allow retry

	Args:
	    offline_id: The unique offline ID from the client
	    pos_profile: POS Profile name
	    customer: Customer name
	    doctype: what the record's link column names: a Sales Invoice, or a Sales
	        Order for an order's online submit key (F6)

	Returns:
	    dict with:
	    - already_synced (bool): True if invoice was already synced
	    - invoice_data (dict): Existing invoice data if already_synced
	    - sync_record_name (str): Name of the sync record for this attempt
	"""
	reserved = _insert_sync_reservation(offline_id, pos_profile, customer)
	if reserved:
		return {"already_synced": False, "sync_record_name": reserved}

	# The id exists: lock that row (a record lock, no gap lock).
	existing_sync = frappe.db.get_value(
		"Offline Invoice Sync",
		{"offline_id": offline_id},
		["name", "sales_invoice", "status", "modified", "pos_profile"],
		as_dict=True,
		for_update=True,
	)
	if not existing_sync:
		# Deleted between the insert and the read (or a name collision): once more.
		if _retry:
			return _ensure_offline_uniqueness(offline_id, pos_profile, customer, _retry=False, doctype=doctype)
		frappe.throw(_("This invoice is currently being processed. Please wait."), title="SYNC_IN_PROGRESS")

	if existing_sync.pos_profile and existing_sync.pos_profile != pos_profile:
		# An offline_id reserved by another profile: never reuse it or return its invoice.
		frappe.throw(_("This offline invoice belongs to another POS Profile."), frappe.PermissionError)

	sync_status = existing_sync.get("status")
	sync_record_name = existing_sync.name

	# Handle Pending status
	if sync_status == "Pending":
		if _is_pending_expired(existing_sync.get("modified")):
			# Expired pending - allow retry
			return _reuse_sync_record(sync_record_name)
		# Active pending - reject with specific error code
		frappe.throw(
			_("This invoice is currently being processed. Please wait."),
			exc=frappe.ValidationError,
			title="SYNC_IN_PROGRESS",
		)

	# Handle Failed status - allow retry
	if sync_status == "Failed":
		return _reuse_sync_record(sync_record_name)

	# Handle Synced status - verify invoice still valid
	if sync_status == "Synced" and existing_sync.sales_invoice:
		name = existing_sync.sales_invoice
		invoice_data = _synced_invoice_data(name, doctype)
		if not invoice_data and str(offline_id).startswith(ONLINE_SUBMIT_KEY_PREFIX):
			# A key carried across doctypes completes under the document made (m-e).
			# A plain check first: a locking read of a missing name takes a gap lock.
			invoice_data = next(
				(
					data
					for other in _key_doctypes(offline_id)[1:]
					if frappe.db.exists(other, name) and (data := _synced_invoice_data(name, other))
				),
				None,
			)
		if invoice_data:
			invoice_data["offline_id"] = offline_id
			return {"already_synced": True, "invoice_data": invoice_data}

	# Synced record points to deleted/invalid invoice, or unknown status - allow retry
	return _reuse_sync_record(sync_record_name)


def _record_offline_id_as(offline_id, invoice_name, pos_profile=None, customer=None) -> None:
	"""Point ``offline_id`` at ``invoice_name`` (the online sale its key already made),
	so a re-sync and ``check_offline_invoice_synced`` find it. Another profile's id is
	refused by ``_ensure_offline_uniqueness``."""
	result = _ensure_offline_uniqueness(offline_id, pos_profile, customer)
	if not result.get("already_synced"):
		_complete_offline_sync(result["sync_record_name"], invoice_name, strict=True)


def _synced_invoice_data(invoice_name, doctype=DOCTYPE_SALES_INVOICE) -> dict | None:
	"""What a repeated submit returns for the submitted ``doctype`` ``invoice_name``, or None.

	A locking read: after waiting on the other request's reservation, this transaction's
	REPEATABLE READ snapshot predates that request's commit, so a plain read would not
	see the invoice it made.
	"""
	fields = ["name", "docstatus", "grand_total", "total", "net_total"]
	if doctype == DOCTYPE_SALES_INVOICE:
		fields += ["outstanding_amount", "paid_amount", "change_amount"]
	existing = frappe.db.get_value(doctype, invoice_name, fields, as_dict=True, for_update=True)
	if not existing or existing.docstatus != 1:
		return None
	return {
		"name": existing.name,
		"status": existing.docstatus,
		"grand_total": existing.grand_total,
		"total": existing.total,
		"net_total": existing.net_total,
		"outstanding_amount": existing.get("outstanding_amount") or 0,
		"paid_amount": existing.get("paid_amount") or 0,
		"change_amount": existing.get("change_amount") or 0,
		"duplicate_prevented": True,
	}


def _complete_offline_sync(sync_record_name, invoice_name, strict=False):
	"""
	Mark an offline sync record as completed after successful invoice submission.

	Args:
	    sync_record_name: Name of the Offline Invoice Sync record
	    invoice_name: Name of the submitted Sales Invoice
	    strict: raise instead of logging. An online submit key (D-19) left Pending would
	        let a retry after the pending timeout make a second sale, so its submit fails
	        (and keeps nothing) when the record cannot be completed.
	"""
	if not sync_record_name:
		return

	if strict:
		frappe.db.set_value(
			"Offline Invoice Sync",
			sync_record_name,
			{"sales_invoice": invoice_name, "status": "Synced", "synced_at": frappe.utils.now_datetime()},
		)
		return

	try:
		sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
		sync_doc.sales_invoice = invoice_name
		sync_doc.status = "Synced"
		sync_doc.synced_at = frappe.utils.now_datetime()
		sync_doc.flags.ignore_permissions = True
		sync_doc.save()
	except Exception as error:
		frappe.log_error(
			title="Offline Sync Completion Error",
			message=f"Failed to complete sync record {sync_record_name} for invoice {invoice_name}: {error!s}",
		)


def _cleanup_failed_sync(sync_record_name):
	"""
	Mark a sync record as failed when invoice submission fails.

	Instead of deleting, we mark as 'failed' to:
	1. Preserve audit trail of sync attempts
	2. Allow manual investigation of failures
	3. Enable retry logic based on failure count

	Args:
	    sync_record_name: Name of the Offline Invoice Sync record
	"""
	if not sync_record_name:
		return

	try:
		sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
		sync_doc.status = "Failed"
		sync_doc.synced_at = frappe.utils.now_datetime()
		sync_doc.flags.ignore_permissions = True
		# An order key's row holds a Sales Order name in the link column (F6).
		sync_doc.flags.ignore_links = True
		sync_doc.save()
	except Exception as error:
		frappe.log_error(
			title="Offline Sync Cleanup Error",
			message=f"Failed to mark sync record {sync_record_name} as failed: {error!s}",
		)


# An online submit's client key (D-19) is reserved in the Offline Invoice Sync table
# under this prefix: the unique ``offline_id`` index makes one invoice per key.
ONLINE_SUBMIT_KEY_PREFIX = "pos_online:"
# A Sales Order's key (F6): reserved per doctype, so an order key is never an invoice
# key. Under the same prefix, so the sync report still leaves it out; a key cannot
# contain ":". The row's ``sales_invoice`` column then holds the order's name.
ONLINE_ORDER_KEY_PREFIX = f"{ONLINE_SUBMIT_KEY_PREFIX}SO:"
_ONLINE_SUBMIT_KEY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _online_submit_key(invoice, data, doctype) -> str | None:
	"""The reservation name of an online submit's ``idempotency_key``, or None.

	The POS sends one key per checkout attempt and keeps it while it retries the same
	cart. A Sales Invoice and a Sales Order are reserved, each under its own prefix
	(F6); an offline sale is reserved by its ``offline_id`` instead.
	"""
	key = data.get("idempotency_key")
	if key is None:
		key = invoice.get("idempotency_key")
	if key is None or doctype not in (DOCTYPE_SALES_INVOICE, DOCTYPE_SALES_ORDER):
		return None
	if not isinstance(key, str) or not 8 <= len(key) <= 100 or not set(key) <= _ONLINE_SUBMIT_KEY_CHARS:
		frappe.throw(_("Invalid submit key"))
	prefix = ONLINE_ORDER_KEY_PREFIX if _key_doctype_of(invoice, data, doctype) == DOCTYPE_SALES_ORDER else ONLINE_SUBMIT_KEY_PREFIX
	return f"{prefix}{key}"


def _key_doctype_of(invoice, data, doctype) -> str:
	"""The doctype a submit key was made for (Ruling 146 (c)). It is the submitted one,
	unless the cashier carried an earlier sale's key over (``idempotency_doctype``): an
	offline sale queued as an invoice may be the same sale as an order whose response
	was lost, and must then find that order."""
	key_doctype = data.get("idempotency_doctype") or invoice.get("idempotency_doctype") or doctype
	if key_doctype not in (DOCTYPE_SALES_INVOICE, DOCTYPE_SALES_ORDER):
		frappe.throw(_("Invalid submit key"))
	return key_doctype


def _key_doctype(offline_id) -> str:
	"""The doctype a sync record's link column names (F6)."""
	if str(offline_id or "").startswith(ONLINE_ORDER_KEY_PREFIX):
		return DOCTYPE_SALES_ORDER
	return DOCTYPE_SALES_INVOICE


def _key_doctypes(offline_id) -> tuple:
	"""Where an online key's sale may be: its own doctype first. A key the cashier carried
	across doctypes (Ruling 146) completes under the document actually made, so the
	other doctype is read too (m-e). An offline id names a Sales Invoice only."""
	own = _key_doctype(offline_id)
	if not str(offline_id or "").startswith(ONLINE_SUBMIT_KEY_PREFIX):
		return (own,)
	other = DOCTYPE_SALES_INVOICE if own == DOCTYPE_SALES_ORDER else DOCTYPE_SALES_ORDER
	return (own, other)


@frappe.whitelist()
def check_offline_invoice_synced(offline_id):
	"""
	Check if an offline invoice has already been synced.

	This endpoint is called by the frontend before attempting to sync
	an offline invoice, preventing duplicate submissions.

	Args:
	    offline_id: The unique offline ID to check

	Returns:
	    dict with 'synced' (bool) and 'sales_invoice' (str or None)
	"""
	ensure_desk_user()
	from pos_next.pos_next.doctype.offline_invoice_sync.offline_invoice_sync import (
		OfflineInvoiceSync,
	)

	if str(offline_id or "").startswith(ONLINE_SUBMIT_KEY_PREFIX):
		return _probe_online_key(offline_id)

	result = OfflineInvoiceSync.is_synced(offline_id)

	# Defensive check - ensure result is a dict
	if not result or not isinstance(result, dict):
		return {"synced": False, "sales_invoice": None}

	if result.get("status") == "Pending":
		# A submit holding this key is still running, or stopped without completing it:
		# not "not made" (Ruling 149). The POS treats this as no answer.
		return dict(result, in_flight=True)

	# Additionally verify the sales invoice (an order key's Sales Order) still exists and is submitted
	if result.get("synced") and result.get("sales_invoice"):
		for doctype in _key_doctypes(offline_id):
			if not frappe.db.exists(doctype, result["sales_invoice"]):
				continue
			fields = ["docstatus"]
			if frappe.get_meta(doctype).has_field("pos_profile"):
				fields.append("pos_profile")
			inv_info = frappe.db.get_value(doctype, result["sales_invoice"], fields, as_dict=True)
			if inv_info and inv_info.get("pos_profile"):
				ensure_pos_user(inv_info.pos_profile)
			if inv_info and inv_info.docstatus == 1:  # Submitted
				return result

		# Invoice was deleted or not submitted, clear the sync record
		return {"synced": False, "sales_invoice": None}

	return result


KEY_PROBE_SAVEPOINT = "pos_next_key_probe"


def _probe_online_key(offline_id) -> dict:
	"""Is an online submit key's reservation absent, even from a submit still running?
	(Ruling 149, C-1).

	A plain read cannot see a reservation an in-flight submit has not committed yet, so it
	would answer "not made" for a sale about to be made. Instead the reservation is
	inserted inside a savepoint and rolled back: through the unique ``offline_id`` index
	that insert waits for an open holder (a record lock, no gap lock: no FOR UPDATE, so no
	site-wide wait, Ruling 139).

	Returns the "never reserved" answer when the insert went in (nobody holds the key),
	the "in flight" answer when the wait timed out or the row is Pending, else the row's
	answer. The row is read in share mode: after the wait, this transaction's snapshot
	may predate the other request's commit. The row exists (the insert hit it), so that
	is a record lock on the unique index, no gap lock.
	"""
	try:
		frappe.db.savepoint(KEY_PROBE_SAVEPOINT)
		reserved = _insert_sync_reservation(offline_id)
	except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
		_rollback_key_probe()
		return {"synced": False, "sales_invoice": None, "status": "Pending", "in_flight": True}
	_rollback_key_probe()
	if reserved:
		return {"synced": False, "sales_invoice": None, "status": None, "in_flight": False}
	row = frappe.db.sql(
		"select sales_invoice, status from `tabOffline Invoice Sync` where offline_id = %s lock in share mode",
		(offline_id,),
		as_dict=True,
	)
	if not row:
		return {"synced": False, "sales_invoice": None, "status": None, "in_flight": False}
	status, name = row[0].status, row[0].sales_invoice
	if status == "Pending":
		return {"synced": False, "sales_invoice": None, "status": status, "in_flight": True}
	if status == "Synced" and name:
		for doctype in _key_doctypes(offline_id):
			made = frappe.db.sql(
				f"select docstatus from `tab{doctype}` where name = %s lock in share mode", (name,)
			)
			if made and made[0][0] == 1:
				return {"synced": True, "sales_invoice": name, "status": status, "in_flight": False}
	return {"synced": False, "sales_invoice": None, "status": status, "in_flight": False}


def _rollback_key_probe() -> None:
	try:
		frappe.db.rollback(save_point=KEY_PROBE_SAVEPOINT)
	except Exception:
		frappe.db.rollback()


SUBMIT_SAVEPOINT = "pos_next_submit_invoice"


def _store_canonical_coupon_code(invoice_doc) -> None:
	"""Store the POS Coupon's own code, as update_invoice does; a code that does not exist
	is refused with update_invoice's message (Ruling 110)."""
	code = invoice_doc.get("coupon_code")
	if not code or not frappe.db.table_exists("POS Coupon"):
		return
	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import resolve_coupon_name

	coupon_name = resolve_coupon_name(code)
	if not coupon_name:
		frappe.throw(_("Sorry, this coupon code does not exist"))
	invoice_doc.coupon_code = frappe.db.get_value("POS Coupon", coupon_name, "coupon_code")


def _rollback_submit() -> None:
	"""Undo what a refused ``submit_invoice`` wrote, back to its savepoint.

	A deadlock has already rolled the whole transaction back (the savepoint with it).
	"""
	try:
		frappe.db.rollback(save_point=SUBMIT_SAVEPOINT)
	except Exception:
		frappe.db.rollback()


@frappe.whitelist()
def submit_invoice(invoice: str | dict | None = None, data: str | dict | None = None) -> dict:
	"""Submit the invoice (Step 2)."""
	# Handle different calling conventions
	ensure_desk_user()
	if invoice is None:
		if data:
			# Check if data is a JSON string containing both params
			data_parsed = json.loads(data) if isinstance(data, str) else data

			# frappe-ui might send all params nested in data
			if isinstance(data_parsed, dict):
				if "invoice" in data_parsed:
					invoice = data_parsed.get("invoice")
					data = data_parsed.get("data", {})
				elif "name" in data_parsed or "doctype" in data_parsed:
					# Data itself might be the invoice
					invoice = data_parsed
					data = {}
				else:
					frappe.throw(
						_("Missing invoice parameter. Received data: {0}").format(
							json.dumps(data_parsed, default=str)
						)
					)
			else:
				frappe.throw(_("Missing invoice parameter"))
		else:
			frappe.throw(_("Both invoice and data parameters are missing"))

	# Parse JSON strings if needed
	if isinstance(data, str):
		data = json.loads(data) if data and data != "{}" else {}
	if isinstance(invoice, str):
		invoice = json.loads(invoice)

	# Ensure invoice and data are dicts
	if not isinstance(invoice, dict):
		frappe.throw(_("Invalid invoice format"))
		return  # Never reached, but helps type checker
	if not isinstance(data, dict):
		data = {}

	# Before the offline dedup: a refused call must neither reserve an offline_id
	# nor read another profile's synced invoice.
	_validate_invoice_profile(invoice)
	invoice = _strip_server_managed_fields(invoice)

	pos_profile = invoice.get("pos_profile")
	doctype = invoice.get("doctype") or DOCTYPE_SALES_INVOICE

	if invoice.get("name") and frappe.db.exists(doctype, invoice.get("name")):
		if frappe.get_meta(doctype).has_field("pos_profile"):
			existing_profile = frappe.db.get_value(doctype, invoice.get("name"), "pos_profile")
			pos_profile = pos_profile or existing_profile

	ensure_pos_user(pos_profile)
	_ensure_opening_shift_for_invoice(invoice.get("posa_pos_opening_shift"), pos_profile)

	# Normalize pricing_rules before processing
	standardize_pricing_rules(invoice.get("items"))

	# ========================================================================
	# OFFLINE INVOICE DEDUPLICATION
	# ========================================================================
	# Prevents duplicate invoice creation when the same offline invoice is
	# submitted multiple times (e.g., network retry, multiple tabs).
	# Uses a reservation pattern: create a "pending" record first, then
	# update to "synced" after successful submission.
	# ========================================================================
	offline_id = invoice.get("offline_id") or data.get("offline_id")
	# An online submit is reserved by its client key the same way (D-19): a retry after a
	# lost response returns the invoice the first request made. The key never makes the
	# submit an offline sync: ``offline_sync`` and ``pos_offline_sync`` read offline_id only.
	# An offline sale queued after a lost response carries the same key (Ruling 139): the
	# key is reserved first, so the sync returns the online invoice instead of a second.
	submit_key = _online_submit_key(invoice, data, doctype)
	key_doctype = _key_doctype(submit_key) if submit_key else doctype
	invoice.pop("idempotency_key", None)
	invoice.pop("idempotency_doctype", None)
	sync_record_name = None
	key_record_name = None

	if submit_key:
		# One row per key (the unique ``offline_id`` index), inserted first: a concurrent
		# request with the same key waits for this one, then finds its Synced row.
		key_result = _ensure_offline_uniqueness(
			offline_id=submit_key, pos_profile=pos_profile, customer=invoice.get("customer"), doctype=key_doctype
		)
		if key_result.get("already_synced"):
			existing = dict(key_result.get("invoice_data") or {})
			existing["idempotency_key"] = submit_key.split(":")[-1]
			existing.pop("offline_id", None)
			if offline_id:
				# The queued sale is that invoice: its offline id points there too. A carried
				# order key's sale is an order: no row is recorded for the offline id, which
				# names an invoice (it would show as a broken link in the sync report);
				# a re-sync is still caught by the key.
				if frappe.db.exists(doctype, existing["name"]):
					_record_offline_id_as(offline_id, existing["name"], pos_profile, invoice.get("customer"))
				existing["offline_id"] = offline_id
			return existing
		key_record_name = key_result.get("sync_record_name")

	if offline_id:
		dedup_result = _ensure_offline_uniqueness(
			offline_id=offline_id, pos_profile=pos_profile, customer=invoice.get("customer")
		)

		if dedup_result and dedup_result.get("already_synced"):
			# Invoice was already synced - return the existing invoice details
			existing = dict(dedup_result.get("invoice_data") or {})
			if key_record_name:
				_complete_offline_sync(key_record_name, existing["name"], strict=True)
			return existing

		# Store the sync record name for later update
		sync_record_name = dedup_result.get("sync_record_name") if dedup_result else None
	# An offline sale reserved for sync here (new, or a retry with no completed
	# invoice) makes the free-row check log-only (Ruling 68).
	offline_sync = bool(offline_id and sync_record_name)

	# Track whether invoice was successfully submitted
	invoice_submitted = False
	# A refused submit keeps nothing it wrote: not the draft's payments (so no later
	# re-save is a paid-draft re-save) nor its docstatus (Ruling 101). A request is rolled
	# back whole anyway; this also holds for a direct call.
	frappe.db.savepoint(SUBMIT_SAVEPOINT)

	try:
		_enforce_sales_orders_only(invoice, offline_sync=offline_sync)
		invoice_name = invoice.get("name")
		# Set below when a stored paid draft is re-saved
		paid_draft_header, paid_draft_rates, paid_draft_rows = None, {}, []

		# Get or create invoice
		if not invoice_name or not frappe.db.exists(doctype, invoice_name):
			created = _update_invoice(json.dumps(invoice), offline_sync=offline_sync, submitting=True)
			if not created or not isinstance(created, dict):
				frappe.throw(_("Failed to create invoice draft"))
			invoice_name = created.get("name")
			if not invoice_name:
				frappe.throw(_("Failed to get invoice name from draft"))
			invoice_doc = frappe.get_doc(doctype, invoice_name)
			# No stored draft held anything: this call made it (Ruling 130).
			invoice_doc.flags.pos_paid_draft_rows = []
		else:
			invoice_doc = _ensure_invoice_draft_access(invoice_name, pos_profile=pos_profile, doctype=doctype)
			invoice_doc.flags.pos_next_api = True
			existing_customer = invoice_doc.customer
			paid_draft_free = _paid_draft_free_qty(invoice_doc)
			stored_sources = _stored_line_sources(invoice_doc)
			paid_draft_rates = _paid_draft_rates(invoice_doc)
			paid_draft_rows = _paid_draft_rows(invoice_doc)
			paid_draft_header = _paid_draft_header(invoice_doc)
			fnf_snapshots = _stored_fnf_snapshots(invoice_doc)
			update_invoice_fields = {k: v for k, v in invoice.items() if k not in ("name", "doctype")}
			invoice_doc.update(update_invoice_fields)
			_carry_fnf_snapshots(invoice_doc, fnf_snapshots)
			if not invoice_doc.get("customer") and existing_customer:
				invoice_doc.customer = existing_customer
			# Before the paid-row check, which reads them (Rulings 126, 128).
			invoice_doc.flags.pos_offline_sync = bool(offline_id)
			invoice_doc.flags.pos_submitting = True
			_set_payment_collected_flag(invoice_doc, invoice.get("payments"))
			# The before_submit F&F check keeps a row this stored paid draft held, as here:
			# read before the save below, which overwrites the stored draft (Ruling 130).
			invoice_doc.flags.pos_paid_draft_rows = paid_draft_rows
			# The POS submits its cart as the draft checked when payment opened; the code
			# comes as typed.
			_store_canonical_coupon_code(invoice_doc)
			_check_free_rows_backed(
				invoice_doc,
				offline_sync=offline_sync,
				paid_draft_free=paid_draft_free,
				stored_sources=stored_sources,
			)
			_reset_row_pricing_rules(invoice_doc.get("items", []))
			if doctype == DOCTYPE_SALES_INVOICE:
				# The rows may not be the stored draft's: stamp the one-time offers as
				# update_invoice does (Ruling 110).
				_stamp_one_time_item_rules(invoice_doc, _server_free_row_rules(invoice_doc.get("items", [])))
			if not invoice_doc.get("is_return"):
				# Judge the rates this save will store, as update_invoice does.
				invoice_doc.calculate_taxes_and_totals()
				if doctype == DOCTYPE_SALES_INVOICE:
					_stamp_one_time_transaction_rules(
						invoice_doc,
						frappe.get_cached_doc("POS Profile", pos_profile) if pos_profile else None,
					)
				_refuse_zero_rate_after_totals(invoice_doc, lenient=offline_sync)
				_check_paid_row_discounts(
					invoice_doc, offline_sync=offline_sync, paid_draft_rows=paid_draft_rows
				)
				_check_header_discount(
					invoice_doc,
					offline_sync=offline_sync,
					paid_draft_header=paid_draft_header,
					paid_draft_rates=paid_draft_rates,
				)
			# The draft was validated by update_invoice, but its rows and header
			# discount may have been replaced by this payload, so redo both.
			# Validating before totals is safe here: it checks only row links,
			# quantities and rates, and recalculating totals does not change rates.
			if invoice_doc.get("is_return"):
				_refuse_return_if_disallowed(invoice_doc.get("pos_profile"))
				_mirror_return_free_rows(invoice_doc)
				_apply_return_header_discount(invoice_doc)
				_validate_return_rows(invoice_doc)
				_apply_return_rounding(invoice_doc)
				_apply_return_taxes(invoice_doc)
				sent_refund = _sent_return_refund(invoice_doc)
				invoice_doc.calculate_taxes_and_totals()
				_set_return_refund(invoice_doc, sent_refund)

		# Keep permission bypass consistent for POS API flow.
		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		# Offline-queued sale being synced (see _apply_pos_sales_team)
		invoice_doc.flags.pos_offline_sync = bool(offline_id)
		# Set again here: the draft made by update_invoice above is re-fetched.
		_set_payment_collected_flag(invoice_doc, invoice.get("payments"))
		_set_paid_draft_flag(invoice_doc, paid_draft_header, paid_draft_rates)

		# Ensure update_stock is set for Sales Invoice
		if doctype == "Sales Invoice":
			invoice_doc.update_stock = 1
			_ensure_invoice_customer(invoice_doc, pos_profile)
			_apply_pos_item_accounting_dimensions(invoice_doc)

		# For return invoices, set update_outstanding_for_self = 0
		# This ensures the GL entry's against_voucher points to the original invoice,
		# which properly reduces the original invoice's outstanding amount and
		# sets its status to "Credit Note Issued"
		if invoice_doc.get("is_return") and invoice_doc.get("return_against"):
			invoice_doc.update_outstanding_for_self = 0

		# Copy accounting dimensions from POS Profile if not already set
		if pos_profile and not invoice_doc.get("branch"):
			try:
				pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
				if hasattr(pos_profile_doc, "branch") and pos_profile_doc.branch:
					invoice_doc.branch = pos_profile_doc.branch
					# Also set branch on all items for GL entries
					for item in invoice_doc.get("items", []):
						if not item.get("branch"):
							item.branch = pos_profile_doc.branch
			except Exception as e:
				# Branch is optional, log and continue
				frappe.log_error(
					f"Failed to set branch from POS Profile {pos_profile}: {e}", "POS Profile Branch"
				)
		# Rows that replaced a stored draft's rows (the POS submits its cart as the draft
		# checked when payment opened) take the header's branch, as update_invoice's rows do.
		if invoice_doc.get("branch"):
			for item in invoice_doc.get("items", []):
				if not item.get("branch"):
					item.branch = invoice_doc.branch

		# Set accounts for all payment methods before saving
		if doctype == "Sales Invoice" and hasattr(invoice_doc, "payments"):
			_set_payment_accounts(invoice_doc.payments, invoice_doc.company)
			_validate_customer_for_receivable_payments(invoice_doc)
			_validate_payment_account_not_debit_to(invoice_doc)

		# Resolve item-level + invoice-level sales persons into sales_team.
		# Prefer cashier team from submit ``data``; offline uses invoice.sales_team
		# only when offline_id is set (never the rebuilt draft aggregate).
		if doctype == "Sales Invoice":
			_apply_pos_sales_team(
				invoice_doc,
				sales_team_data=_resolve_submit_invoice_level_team(
					invoice, data, invoice_name=invoice_doc.name
				),
				pos_profile=pos_profile,
			)

		# POS Coupon usage is counted by the invoice's on_submit hook from the
		# saved coupon_code (see pos_coupon.count_usage_on_submit), not here.

		# Auto-set batch numbers for returns
		_auto_set_return_batches(invoice_doc)

		# Handle write-off amount if provided
		write_off_amount = flt(data.get("write_off_amount") or invoice.get("write_off_amount") or 0)
		if write_off_amount > 0 and doctype == "Sales Invoice":
			# Get write-off account and cost center from POS Profile
			if pos_profile:
				try:
					pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
					write_off_account = pos_profile_doc.write_off_account
					write_off_cost_center = pos_profile_doc.write_off_cost_center
					write_off_limit = flt(pos_profile_doc.write_off_limit or 0)

					# Validate write-off amount is within limit
					if write_off_limit > 0 and write_off_amount > write_off_limit:
						frappe.throw(
							_("Write-off amount {0} exceeds limit {1}").format(
								write_off_amount, write_off_limit
							)
						)

					# Set write-off fields on invoice
					if write_off_account:
						invoice_doc.write_off_account = write_off_account
						invoice_doc.write_off_cost_center = write_off_cost_center
						invoice_doc.write_off_amount = write_off_amount
						invoice_doc.base_write_off_amount = write_off_amount  # Assuming same currency
				except Exception as e:
					frappe.log_error(
						f"Failed to apply write-off from POS Profile {pos_profile}: {e}",
						"POS Write-Off Error",
					)

		# Validate stock availability before submission
		# _validate_stock_on_invoice checks _should_block internally
		# (global Stock Settings, POS Settings, and POS Profile flags)
		_validate_stock_on_invoice(invoice_doc)

		# Allow pure customer-credit POS sales to submit without a payment row.
		customer_credit_dict = data.get("customer_credit_dict") or invoice.get("customer_credit_dict")
		redeemed_customer_credit = data.get("redeemed_customer_credit") or invoice.get(
			"redeemed_customer_credit"
		)
		if redeemed_customer_credit and not invoice_doc.payments:
			invoice_doc.flags.pos_next_redeemed_customer_credit = flt(redeemed_customer_credit)

		# Allow intentional "Pay on Account" credit sales to submit without a
		# payment row. The frontend sends is_credit_sale=1 when the cashier puts
		# the full amount on the customer's account. Only honour it when the POS
		# Settings for this profile actually permit credit sales, so a tampered
		# client can't bypass the core payment-row requirement.
		is_credit_sale = cint(data.get("is_credit_sale") or invoice.get("is_credit_sale"))
		if is_credit_sale and not invoice_doc.payments and flt(invoice_doc.grand_total) > 0:
			allow_credit_sale = cint(
				frappe.db.get_value(DOCTYPE_POS_SETTINGS, {"pos_profile": pos_profile}, "allow_credit_sale")
			)
			if not allow_credit_sale:
				frappe.throw(_("Credit sales are not enabled for this POS Profile."))
			if not invoice_doc.get("customer"):
				frappe.throw(_("Customer is required for credit sales"), title=_("Customer Required"))
			invoice_doc.flags.pos_next_credit_sale = 1

		# Save before submit
		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		if doctype == "Sales Invoice":
			_ensure_invoice_customer(invoice_doc, pos_profile)
			_apply_pos_item_accounting_dimensions(invoice_doc)
		invoice_doc.save()

		from pos_next.authorization.gate import TOKEN_FLAG

		invoice_doc.flags[TOKEN_FLAG] = invoice.get("authorization_token") or data.get("authorization_token")

		if doctype == DOCTYPE_SALES_INVOICE:
			_redeem_one_time_rules(invoice_doc, offline_sync=offline_sync)

		# Submit invoice
		invoice_doc.submit()
		invoice_submitted = True
		# Handle wallet transaction reversal for returns
		wallet_reversal_ok = False
		if invoice_doc.get("is_return") and invoice_doc.get("return_against"):
			from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import (
				reverse_wallet_transactions_for_return,
			)

			try:
				reverse_wallet_transactions_for_return(
					original_invoice=invoice_doc.return_against, return_invoice=invoice_doc.name
				)
				wallet_reversal_ok = True
			except Exception as wallet_reversal_error:
				frappe.log_error(
					title="Wallet Reversal Error",
					message=(
						f"Return invoice: {invoice_doc.name}, "
						f"Original invoice: {invoice_doc.return_against}, "
						f"Error: {wallet_reversal_error!s}\n{frappe.get_traceback()}"
					),
				)
				frappe.msgprint(
					_(
						"Return invoice submitted successfully, but wallet reversal failed. Please contact administrator."
					),
					alert=True,
					indicator="orange",
				)

		# Credit return amount to customer wallet when "Add to Customer Credit Balance" is enabled.
		# Only proceed if the wallet reversal above succeeded (or was not needed) to
		# avoid double-crediting the customer when reversal fails.
		if invoice_doc.get("is_return"):
			add_to_customer_balance = invoice.get("add_to_customer_balance")
			has_return_against = bool(invoice_doc.get("return_against"))
			if add_to_customer_balance and (wallet_reversal_ok or not has_return_against):
				from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import (
					credit_return_to_wallet,
				)

				try:
					credit_return_to_wallet(
						return_invoice=invoice_doc.name, amount=_return_credit_amount(invoice_doc)
					)
				except Exception as wallet_credit_error:
					frappe.log_error(
						title="Wallet Credit on Return Error",
						message=(
							f"Return invoice: {invoice_doc.name}, "
							f"Error: {wallet_credit_error!s}\n{frappe.get_traceback()}"
						),
					)
					frappe.msgprint(
						_("Return submitted but wallet credit failed. Please contact administrator."),
						alert=True,
						indicator="orange",
					)
		# Complete the offline sync record
		if sync_record_name:
			_complete_offline_sync(sync_record_name, invoice_doc.name)
		if key_record_name:
			_complete_offline_sync(key_record_name, invoice_doc.name, strict=True)

		# Handle credit redemption after successful submission
		if redeemed_customer_credit and customer_credit_dict:
			try:
				from pos_next.api.credit_sales import redeem_customer_credit

				redeem_customer_credit(invoice_doc.name, customer_credit_dict)
			except Exception as credit_error:
				frappe.log_error(
					title="Credit Redemption Error",
					message=f"Invoice: {invoice_doc.name}, Error: {credit_error!s}\n{frappe.get_traceback()}",
				)
				raise

		# Log manual rate edits for audit trail (only after successful submission)
		if doctype == DOCTYPE_SALES_INVOICE:
			incoming_items = invoice.get("items") or []
			for item in incoming_items:
				if cint(item.get(FIELD_IS_RATE_MANUALLY_EDITED)):
					log_manual_rate_edit(
						{
							FIELD_ITEM_CODE: item.get(FIELD_ITEM_CODE),
							"item_name": item.get("item_name"),
							FIELD_RATE: flt(item.get(FIELD_RATE)),
							FIELD_ORIGINAL_RATE: flt(
								item.get(FIELD_ORIGINAL_RATE) or item.get(FIELD_PRICE_LIST_RATE)
							),
							FIELD_IS_RATE_MANUALLY_EDITED: 1,
						},
						invoice_doc.name,
					)

		# Return complete invoice details
		result = {
			"name": invoice_doc.name,
			"status": invoice_doc.docstatus,
			"grand_total": invoice_doc.grand_total,
			"total": invoice_doc.total,
			"net_total": invoice_doc.net_total,
			"outstanding_amount": getattr(invoice_doc, "outstanding_amount", 0),
			"paid_amount": getattr(invoice_doc, "paid_amount", 0),
			"change_amount": getattr(invoice_doc, "change_amount", 0),
		}

		# Include offline_id in response for client-side tracking
		if offline_id:
			result["offline_id"] = offline_id

		return result

	except frappe.PermissionError:
		raise
	except Exception:
		traceback = frappe.get_traceback()
		_rollback_submit()
		frappe.log_error(traceback, "Submit Invoice Error")
		raise

	finally:
		# Cleanup sync record if invoice was not successfully submitted
		if sync_record_name and not invoice_submitted:
			_cleanup_failed_sync(sync_record_name)
		if key_record_name and not invoice_submitted:
			_cleanup_failed_sync(key_record_name)


# ==========================================
# Invoice History Management
# ==========================================


@frappe.whitelist()
def get_invoice(invoice_name):
	"""
	Get a single invoice with all details for POS.

	Args:
		invoice_name: Sales Invoice name

	Returns:
		Complete invoice document with items and payments
	"""
	ensure_desk_user()
	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

	# Check permissions
	if not frappe.has_permission("Sales Invoice", "read", invoice_name):
		frappe.throw(_("You don't have permission to view this invoice"))

	# Get invoice document
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	return invoice.as_dict()


@frappe.whitelist()
def get_invoices(
	pos_profile: str,
	search=None,
	limit: int = 20,
	offset=0,
	from_date=None,
	to_date=None,
	include_items=False,
	docstatus=None,
	start: int = 0,
) -> list:
	"""
	Get paginated, server-side filtered list of invoices for a POS Profile.

	Args:
		pos_profile: POS Profile name
		search: Optional search term matched against invoice name or customer_name
		limit: Page size (default 20)
		offset: Number of records to skip for pagination (default 0)
		from_date: Optional start date filter (YYYY-MM-DD)
		to_date: Optional end date filter (YYYY-MM-DD)
		limit: Maximum number of invoices to return (default 100)
		start: Offset for pagination (default 0)

	Returns:
		List of invoice dicts with basic fields (no per-invoice item loading)
	"""
	ensure_desk_user()
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	limit = cint(limit) or 100
	start = cint(start) or 0

	# Permission check
	ensure_pos_user(pos_profile)

	# Clamp page size securely: minimum 1, maximum 100
	limit = max(1, min(cint(limit) or 20, 100))
	offset = max(0, cint(offset) or 0)

	# Build WHERE conditions and params
	conditions = [
		"pos_profile = %(pos_profile)s",
		"is_pos = 1",
	]
	params = {"pos_profile": pos_profile, "limit": limit, "offset": offset}

	if docstatus is not None:
		if isinstance(docstatus, (list, tuple)):
			docstatus_list = [cint(d) for d in docstatus]
			conditions.append(f"docstatus IN ({','.join(map(str, docstatus_list))})")
		else:
			conditions.append("docstatus = %(docstatus)s")
			params["docstatus"] = cint(docstatus)
	else:
		conditions.append("docstatus < 2")

	if search:
		conditions.append(
			"(name LIKE %(search)s OR customer_name LIKE %(search)s OR customer LIKE %(search)s)"
		)
		params["search"] = f"%{cstr(search)}%"

	if from_date:
		conditions.append("posting_date >= %(from_date)s")
		params["from_date"] = from_date

	if to_date:
		conditions.append("posting_date <= %(to_date)s")
		params["to_date"] = to_date

	where_clause = " AND ".join(conditions)
	params["limit"] = limit
	params["offset"] = offset

	invoices = frappe.db.sql(
		f"""
		SELECT
			name,
			customer,
			customer_name,
			posting_date,
			posting_time,
			grand_total,
			paid_amount,
			outstanding_amount,
			status,
			docstatus,
			is_return,
			return_against
		FROM
			`tabSales Invoice`
		WHERE
			{where_clause}
		ORDER BY
			posting_date DESC,
			posting_time DESC
		LIMIT %(limit)s
		OFFSET %(offset)s
	""",
		params,
		as_dict=True,
	)

	invoice_names = [invoice.name for invoice in invoices]
	payments_by_invoice = {}
	if invoice_names:
		payments = frappe.db.sql(
			"""
			SELECT
				parent,
				mode_of_payment,
				amount
			FROM
				`tabSales Invoice Payment`
			WHERE
				parent IN %(invoice_names)s
			ORDER BY
				parent,
				idx
		""",
			{"invoice_names": tuple(invoice_names)},
			as_dict=True,
		)

		for payment in payments:
			payments_by_invoice.setdefault(payment.parent, []).append(
				{
					"mode_of_payment": payment.mode_of_payment,
					"amount": payment.amount,
				}
			)

	# Load items for each invoice for filtering purposes
	for invoice in invoices:
		invoice.payments = payments_by_invoice.get(invoice.name, [])
		items = frappe.db.sql(
			"""
			SELECT
				item_code,
				item_name,
				qty,
				rate,
				amount
			FROM
				`tabSales Invoice Item`
			WHERE
				parent = %(invoice_name)s
			ORDER BY
				idx
		""",
			{"invoice_name": invoice.name},
			as_dict=True,
		)
		invoice.items = items

	return invoices


# ==========================================
# Draft Invoice Management
# ==========================================


@frappe.whitelist()
def get_draft_invoices(pos_opening_shift, doctype="Sales Invoice"):
	"""Get all draft invoices for a POS opening shift."""
	current_user = ensure_desk_user()
	if doctype != DOCTYPE_SALES_INVOICE:
		frappe.throw(_("Only Sales Invoice drafts are supported"), frappe.PermissionError)

	if not pos_opening_shift:
		frappe.throw(_("POS Opening Shift is required"), frappe.ValidationError)

	shift = frappe.db.get_value(
		"POS Opening Shift",
		pos_opening_shift,
		["user", "pos_profile"],
		as_dict=True,
	)
	if not shift:
		frappe.throw(_("POS Opening Shift {0} not found").format(pos_opening_shift))

	if shift.user != current_user and not is_pos_supervisor(current_user):
		frappe.throw(
			_("You are not authorized to view drafts for this shift"),
			frappe.PermissionError,
		)

	ensure_pos_user(shift.pos_profile, current_user)

	filters = {
		"docstatus": 0,
		"is_pos": 1,
	}

	if frappe.db.has_column(doctype, "posa_pos_opening_shift"):
		filters["posa_pos_opening_shift"] = pos_opening_shift
	elif frappe.db.has_column(doctype, "pos_opening_shift"):
		filters["pos_opening_shift"] = pos_opening_shift

	if not is_pos_supervisor(current_user):
		filters["owner"] = current_user

	# Performance: Get all invoice names first
	invoices_list = frappe.get_all(
		doctype,
		filters=filters,
		fields=["name"],
		limit_page_length=100,
		order_by="modified desc",
	)

	# Performance: Batch load all documents at once using get_cached_doc
	# This leverages Frappe's internal caching and is faster than individual queries
	data = []
	for invoice in invoices_list:
		data.append(frappe.get_cached_doc(doctype, invoice["name"]))

	return data


@frappe.whitelist()
def delete_invoice(invoice):
	"""Delete draft invoice."""
	current_user = ensure_desk_user()
	doctype = DOCTYPE_SALES_INVOICE

	if not frappe.db.exists(doctype, invoice):
		frappe.throw(_("Invoice {0} does not exist").format(invoice))

	inv_info = frappe.db.get_value(
		doctype,
		invoice,
		["docstatus", "owner", "pos_profile", "is_pos"],
		as_dict=True,
	)

	# Check if it's a draft
	if inv_info.docstatus != 0:
		frappe.throw(_("Cannot delete submitted invoice {0}").format(invoice))

	if not cint(inv_info.is_pos) and not is_pos_supervisor(current_user):
		frappe.throw(_("Only POS draft invoices can be deleted here"), frappe.PermissionError)

	if inv_info.pos_profile:
		ensure_pos_user(inv_info.pos_profile, current_user)

	if inv_info.owner != current_user and not is_pos_supervisor(current_user):
		frappe.throw(_("You can only delete your own draft invoices"), frappe.PermissionError)

	frappe.delete_doc(doctype, invoice, force=1)
	return _("Invoice {0} Deleted").format(invoice)


MIN_DRAFT_CLEANUP_AGE_HOURS = 24


@frappe.whitelist()
def cleanup_old_drafts(pos_profile=None, max_age_hours=48):
	"""
	Clean up old draft invoices to prevent stock reservation issues.
	Deletes drafts older than max_age_hours (minimum 24 hours).
	"""
	current_user = ensure_desk_user()
	from datetime import datetime, timedelta

	age_hours = cint(max_age_hours)
	if age_hours < MIN_DRAFT_CLEANUP_AGE_HOURS:
		frappe.throw(
			_("max_age_hours must be at least {0} hours").format(MIN_DRAFT_CLEANUP_AGE_HOURS),
			frappe.ValidationError,
		)

	supervisor = is_pos_supervisor(current_user)
	if pos_profile:
		ensure_pos_user(pos_profile, current_user)
	elif not supervisor:
		frappe.throw(_("POS Profile is required"), frappe.ValidationError)

	doctype = DOCTYPE_SALES_INVOICE
	cutoff_time = datetime.now() - timedelta(hours=age_hours)

	filters = {
		"docstatus": 0,  # Draft only
		"is_pos": 1,  # Only POS Sales Invoices
		"modified": ["<", cutoff_time.strftime("%Y-%m-%d %H:%M:%S")],
	}

	# Optionally filter by POS profile
	if pos_profile:
		filters["pos_profile"] = pos_profile

	# Non-supervisors may only clean up their own old drafts
	if not supervisor:
		filters["owner"] = current_user

	# Get old drafts
	old_drafts = frappe.get_all(
		doctype,
		filters=filters,
		fields=["name", "modified"],
		limit_page_length=100,  # Safety limit
	)

	deleted_count = 0
	for draft in old_drafts:
		try:
			frappe.delete_doc(doctype, draft["name"], force=True, ignore_permissions=True)
			deleted_count += 1
		except Exception as e:
			frappe.log_error(
				f"Failed to delete draft {draft['name']}: {e!s}",
				"Draft Cleanup Error",
			)

	return {
		"deleted": deleted_count,
		"message": f"Cleaned up {deleted_count} old draft invoices",
	}


# ==========================================
# Return Invoice Management
# ==========================================


def _filter_fully_returned(invoices):
	"""Remove invoices where all items have already been returned.

	Uses two targeted queries instead of a 4-table LEFT JOIN to avoid
	cartesian explosion (SI x SI_Item x Ret_SI x Ret_Item).
	Only touches the small candidate set passed in.
	"""
	if not invoices:
		return []

	from frappe.query_builder.functions import Abs, Sum

	invoice_names = [inv["name"] for inv in invoices]

	# Original qty per invoice
	si_item = frappe.qb.DocType("Sales Invoice Item")
	orig_rows = (
		frappe.qb.from_(si_item)
		.select(si_item.parent, Sum(si_item.qty).as_("total_original_qty"))
		.where(si_item.parent.isin(invoice_names))
		.groupby(si_item.parent)
	).run(as_dict=True)
	orig_map = {r["parent"]: flt(r["total_original_qty"]) for r in orig_rows}

	# Returned qty per original invoice
	ret_si = frappe.qb.DocType("Sales Invoice")
	ret_item = frappe.qb.DocType("Sales Invoice Item")
	ret_rows = (
		frappe.qb.from_(ret_si)
		.inner_join(ret_item)
		.on(ret_item.parent == ret_si.name)
		.select(ret_si.return_against, Sum(Abs(ret_item.qty)).as_("total_returned_qty"))
		.where(
			(ret_si.return_against.isin(invoice_names)) & (ret_si.docstatus == 1) & (ret_si.is_return == 1)
		)
		.groupby(ret_si.return_against)
	).run(as_dict=True)
	ret_map = {r["return_against"]: flt(r["total_returned_qty"]) for r in ret_rows}

	for inv in invoices:
		inv["total_original_qty"] = orig_map.get(inv["name"], 0)
		inv["total_returned_qty"] = ret_map.get(inv["name"], 0)

	return [inv for inv in invoices if inv["total_original_qty"] > inv["total_returned_qty"]]


@frappe.whitelist()
def get_returnable_invoices(limit=50, pos_profile=None):
	"""Get list of invoices that have items available for return.
	Filters by return validity period if configured in POS Settings.

	Two-step approach for performance:
	1. Fetch recent POS invoices (fast indexed query, no JOINs)
	2. Filter out fully-returned ones via _filter_fully_returned
	"""
	ensure_desk_user()
	if pos_profile:
		ensure_pos_user(pos_profile)
	frappe.has_permission("Sales Invoice", "read", throw=True)
	from frappe.utils import add_days, today

	safe_limit = min(max(cint(limit) or 50, 1), 100)

	# Check return validity days from POS Settings
	return_validity_days = 0
	if pos_profile:
		return_validity_days = cint(
			frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "return_validity_days") or 0
		)

	si = frappe.qb.DocType("Sales Invoice")

	# Over-fetch to compensate for fully-returned invoices removed in step 2
	fetch_limit = safe_limit * 2

	# Step 1: fetch candidates (lightweight, no JOINs)
	query = (
		frappe.qb.from_(si)
		.select(
			si.name,
			si.customer,
			si.customer_name,
			si.contact_mobile,
			si.posting_date,
			si.grand_total,
			si.rounded_total,
			si.paid_amount,
			si.change_amount,
			si.status,
		)
		.where((si.docstatus == 1) & (si.is_return == 0) & (si.is_pos == 1))
		.orderby(si.posting_date, order=frappe.qb.desc)
		.orderby(si.creation, order=frappe.qb.desc)
		.limit(fetch_limit)
	)

	if return_validity_days > 0:
		cutoff_date = add_days(today(), -return_validity_days)
		query = query.where(si.posting_date >= cutoff_date)

	candidates = query.run(as_dict=True)

	# Step 2: filter out fully-returned invoices, then trim to requested limit
	return _filter_fully_returned(candidates)[:safe_limit]


@frappe.whitelist()
def search_invoice_by_number(search_term, pos_profile=None):
	"""Search for invoices by invoice number across the entire database.
	No date restrictions - searches all returnable invoices matching the term.

	Two-step approach for performance:
	1. Find matching POS invoices by name (fast indexed LIKE query)
	2. Filter out fully-returned ones via _filter_fully_returned

	Args:
	    search_term: Invoice number or partial number to search for (min 3 chars)
	    pos_profile: Optional POS profile for context (reserved for future use)

	Returns:
	    List of matching invoices with return availability info (max 10 results)
	"""
	ensure_desk_user()
	if pos_profile:
		ensure_pos_user(pos_profile)
	frappe.has_permission("Sales Invoice", "read", throw=True)
	if not search_term or len(search_term) < 3:
		return []

	# Escape LIKE wildcards in user input to prevent pattern abuse.
	# frappe.db.escape() returns a quoted string for raw SQL — not usable with
	# frappe.qb's .like() which parameterizes internally. Manual escaping needed.
	search_term = cstr(search_term).strip().replace("%", r"\%").replace("_", r"\_")
	si = frappe.qb.DocType("Sales Invoice")

	# Step 1: find matching invoices (lightweight, no JOINs)
	candidates = (
		frappe.qb.from_(si)
		.select(
			si.name,
			si.customer,
			si.customer_name,
			si.contact_mobile,
			si.posting_date,
			si.grand_total,
			si.rounded_total,
			si.paid_amount,
			si.change_amount,
			si.status,
		)
		.where(
			(si.docstatus == 1) & (si.is_return == 0) & (si.is_pos == 1) & (si.name.like(f"%{search_term}%"))
		)
		.orderby(si.posting_date, order=frappe.qb.desc)
		.orderby(si.creation, order=frappe.qb.desc)
		.limit(10)
	).run(as_dict=True)

	# Step 2: filter out fully-returned invoices
	return _filter_fully_returned(candidates)


@frappe.whitelist()
def check_invoice_return_validity(invoice_name):
	"""Check if an invoice is within the return validity period.

	Returns detailed information for the UI to display, including:
	- valid: Boolean indicating if return is allowed
	- error_type: 'not_found' or 'return_period_expired' if invalid
	- Additional context (invoice_date, days_since, allowed_days) for expired returns
	"""
	ensure_desk_user()
	frappe.has_permission("Sales Invoice", "read", invoice_name, throw=True)
	from frappe.utils import date_diff, formatdate, getdate

	# Fetch only the fields needed for validation
	si = frappe.qb.DocType("Sales Invoice")
	invoice_data = (
		frappe.qb.from_(si).select(si.pos_profile, si.posting_date).where(si.name == invoice_name)
	).run(as_dict=True)

	if not invoice_data:
		return {
			"valid": False,
			"error_type": "not_found",
			"message": _("Invoice {0} does not exist").format(invoice_name),
		}

	invoice_info = invoice_data[0]

	# Check return validity period from POS Settings
	if invoice_info.pos_profile:
		return_validity_days = cint(
			frappe.db.get_value(
				"POS Settings", {"pos_profile": invoice_info.pos_profile}, "return_validity_days"
			)
			or 0
		)

		if return_validity_days > 0:
			days_since_invoice = date_diff(getdate(nowdate()), getdate(invoice_info.posting_date))
			if days_since_invoice > return_validity_days:
				return {
					"valid": False,
					"error_type": "return_period_expired",
					"invoice_name": invoice_name,
					"invoice_date": formatdate(invoice_info.posting_date),
					"days_since": days_since_invoice,
					"allowed_days": return_validity_days,
					"message": _("Return period has expired"),
				}

	return {"valid": True}


@frappe.whitelist()
def get_invoice_for_return(invoice_name):
	"""Get invoice with return tracking - calculates remaining qty for each item.
	Also validates return validity period based on POS Settings.

	Returns the full invoice document with each item's qty adjusted to show
	only the remaining returnable quantity (original qty minus already returned).
	"""
	ensure_desk_user()
	frappe.has_permission("Sales Invoice", "read", invoice_name, throw=True)
	from frappe.query_builder.functions import Abs, Coalesce, Sum
	from frappe.utils import date_diff, getdate

	# Validate invoice exists and get fields needed for return period check
	si = frappe.qb.DocType("Sales Invoice")
	invoice_check = (
		frappe.qb.from_(si).select(si.pos_profile, si.posting_date).where(si.name == invoice_name)
	).run(as_dict=True)

	if not invoice_check:
		frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

	invoice_info = invoice_check[0]

	# Check return validity period from POS Settings
	if invoice_info.pos_profile:
		return_validity_days = cint(
			frappe.db.get_value(
				"POS Settings", {"pos_profile": invoice_info.pos_profile}, "return_validity_days"
			)
			or 0
		)

		if return_validity_days > 0:
			days_since_invoice = date_diff(getdate(nowdate()), getdate(invoice_info.posting_date))
			if days_since_invoice > return_validity_days:
				frappe.throw(
					_(
						"Return period has expired. Invoice {0} was created {1} days ago. "
						"Returns are only allowed within {2} days of purchase."
					).format(invoice_name, days_since_invoice, return_validity_days)
				)

	# Aggregate quantities already returned from previous return invoices.
	# Uses COALESCE to match by sales_invoice_item (row ID) first, then item_code as fallback.
	ret_si = frappe.qb.DocType("Sales Invoice")
	ret_item = frappe.qb.DocType("Sales Invoice Item")

	returned_qty_results = (
		frappe.qb.from_(ret_si)
		.inner_join(ret_item)
		.on(ret_item.parent == ret_si.name)
		.select(
			Coalesce(ret_item.sales_invoice_item, ret_item.item_code).as_("key_field"),
			Sum(Abs(ret_item.qty)).as_("returned_qty"),
		)
		.where((ret_si.return_against == invoice_name) & (ret_si.docstatus == 1) & (ret_si.is_return == 1))
		.groupby(Coalesce(ret_item.sales_invoice_item, ret_item.item_code))
	).run(as_dict=True)

	returned_qty = {row["key_field"]: flt(row["returned_qty"]) for row in returned_qty_results}

	# Get the full invoice document (needed for complete response)
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice_dict = invoice.as_dict()

	# Calculate remaining quantities
	updated_items = []
	for item in invoice_dict.get("items", []):
		# Check how much has been returned using the item's name (row ID)
		already_returned = returned_qty.get(item.name, 0)
		remaining_qty = flt(item.qty) - already_returned

		if remaining_qty > 0:
			item_copy = item.copy()
			item_copy["original_qty"] = item.qty
			item_copy["qty"] = remaining_qty
			item_copy["already_returned"] = already_returned
			updated_items.append(item_copy)

	invoice_dict["items"] = updated_items
	return invoice_dict


def _parse_item_wise_tax_detail(raw_detail):
	"""Parse item_wise_tax_detail from string or dict format."""
	if not raw_detail:
		return {}
	if isinstance(raw_detail, str):
		return json.loads(raw_detail)
	return raw_detail


def _return_row_tax(items: list, taxes: list) -> dict:
	"""Row idx -> the row's tax (absolute value), from the taxes child table.

	item_wise_tax_detail ({"ITEM-CODE": [tax_rate, tax_amount]}) is kept per item
	code, so an item on several rows (a paid row and its free row, or two paid
	rows) has its tax shared by the rows' net amounts: a free row carries none.
	Return documents have negative amounts, hence abs().
	"""
	item_tax = {}
	for tax_row in taxes:
		try:
			details = _parse_item_wise_tax_detail(tax_row.get("item_wise_tax_detail"))
			for item_code, (_, tax_amount) in details.items():
				item_tax[item_code] = item_tax.get(item_code, 0) + abs(flt(tax_amount))
		except (json.JSONDecodeError, TypeError, ValueError, KeyError):
			continue

	weights = {}
	for item in items:
		weights.setdefault(item.get("item_code"), []).append(
			(item.get("idx"), abs(flt(item.get("net_amount"))))
		)

	row_tax = {}
	for item_code, rows in weights.items():
		total = sum(weight for _, weight in rows)
		for idx, weight in rows:
			row_tax[idx] = item_tax.get(item_code, 0) * weight / total if total else 0
	return row_tax


def _remap_foreign_payment_modes(payments_data, current_profile, original_profile):
	"""Remap payment modes that don't belong to the current POS profile.

	Cross-branch returns problem:
	    Each POS branch has its own cash Mode of Payment that maps to a
	    dedicated GL cash account (e.g. "Boulaq Cash" -> account 12114,
	    "Cash lebanon" -> account 12123). When a customer returns an invoice
	    that was originally sold at a different branch, ERPNext's
	    make_sales_return() copies the *original* branch's payment modes.

	    If we don't remap, two things go wrong:
	    1. GL entries: the refund is posted against the wrong branch's cash
	       account (e.g. crediting Lebanon's cash instead of Boulaq's).
	    2. Shift closing: the foreign mode creates an orphan payment row
	       that doesn't exist in the current profile's opening balance,
	       blocking reconciliation.

	Remapping strategy:
	    Modes are matched by their Mode of Payment *type* field:
	    - Cash -> Cash  (e.g. "Cash lebanon" -> "Boulaq Cash")
	    - Bank -> Bank  (e.g. "Lebanon Visa" -> "Visa")
	    - General -> first available in profile, or cash fallback

	    This ensures the GL account matches the physical cash drawer or
	    bank account at the branch where the return is processed.

	Fallback chain for default mode:
	    1. POS Profile.posa_cash_mode_of_payment (explicit cash mode config)
	    2. First mode with type "Cash" in the profile
	    3. First mode in the profile (any type)

	When remapping is skipped (no-op):
	    - Same profile (current == original)
	    - No current_profile provided
	    - All original modes already exist in the current profile
	    - No default_mode could be determined (empty profile)

	Args:
	    payments_data: list of frappe._dict with mode_of_payment, amount, etc.
	                   (from Sales Invoice Payment child table of original invoice)
	    current_profile: POS Profile name where the return is being processed
	    original_profile: POS Profile name where the original sale happened

	Returns:
	    The same payments_data list with mode_of_payment remapped in-place.
	    Shared modes (e.g. "Visa" exists in both profiles) are left unchanged.

	Example:
	    Original invoice (profile "2- Lebanon"):
	        payments = [{"mode_of_payment": "Cash lebanon", "amount": 3240}]

	    Current profile "4- Boulaq" has modes:
	        [{"mode_of_payment": "Boulaq Cash", type: "Cash"},
	         {"mode_of_payment": "Visa",        type: "Bank"}]

	    After remap:
	        payments = [{"mode_of_payment": "Boulaq Cash", "amount": 3240}]

	    "Cash lebanon" (type=Cash) -> "Boulaq Cash" (type=Cash)
	"""
	if not current_profile or current_profile == original_profile:
		return payments_data

	# Get current profile's payment modes
	current_modes = {
		row.mode_of_payment
		for row in frappe.get_all(
			"POS Payment Method",
			filters={"parent": current_profile, "parenttype": "POS Profile"},
			fields=["mode_of_payment"],
		)
	}

	# Check if any payment needs remapping
	needs_remap = any(p.mode_of_payment not in current_modes for p in payments_data)
	if not needs_remap:
		return payments_data

	# Build type->mode map for the current profile.
	# Uses setdefault so the first mode of each type wins (matches profile order).
	mop = frappe.qb.DocType("Mode of Payment")
	ppm = frappe.qb.DocType("POS Payment Method")
	current_type_map = {}
	rows = (
		frappe.qb.from_(ppm)
		.inner_join(mop)
		.on(mop.name == ppm.mode_of_payment)
		.select(ppm.mode_of_payment, mop.type)
		.where((ppm.parent == current_profile) & (ppm.parenttype == "POS Profile"))
	).run(as_dict=True)

	for row in rows:
		current_type_map.setdefault(row.type, row.mode_of_payment)

	# Default fallback: posa_cash_mode_of_payment > first Cash type > first mode
	default_mode = (
		frappe.db.get_value("POS Profile", current_profile, "posa_cash_mode_of_payment")
		or current_type_map.get("Cash")
		or (rows[0].mode_of_payment if rows else None)
	)

	if not default_mode:
		return payments_data

	# Fetch the type for each foreign mode in a single query
	foreign_modes = [p.mode_of_payment for p in payments_data if p.mode_of_payment not in current_modes]
	foreign_types = {}
	if foreign_modes:
		type_rows = frappe.get_all(
			"Mode of Payment",
			filters={"name": ["in", foreign_modes]},
			fields=["name", "type"],
		)
		foreign_types = {r.name: r.type for r in type_rows}

	# Remap: foreign Cash -> current Cash, foreign Bank -> current Bank, etc.
	# If no type match in current profile, fall back to default_mode.
	for payment in payments_data:
		if payment.mode_of_payment in current_modes:
			continue
		foreign_type = foreign_types.get(payment.mode_of_payment)
		payment.mode_of_payment = current_type_map.get(foreign_type, default_mode)

	return payments_data


@frappe.whitelist()
def prepare_return_invoice(invoice_name, pos_opening_shift=None):
	"""Prepare a return invoice using ERPNext's make_sales_return.

	This uses ERPNext's standard return document creation which properly copies
	all child tables including:
	- sales_team: For correct commission reversal on returned items
	- taxes: For correct tax reversal
	- Other child tables maintained by ERPNext

	The function validates:
	- Invoice exists and is submitted (docstatus = 1)
	- Invoice is not already a return
	- Return is within the validity period (if configured in POS Settings)

	Args:
	    invoice_name: The original Sales Invoice name to create return against
	    pos_opening_shift: The current POS Opening Shift name

	Returns:
	    dict: The prepared return invoice document with:
	        - items: Only items with remaining_qty > 0 (not fully returned)
	        - _original_invoice: Reference data from original invoice (payments, amounts)
	        - Each item includes original_qty, already_returned, and remaining_qty
	"""
	ensure_desk_user()
	frappe.has_permission("Sales Invoice", "read", invoice_name, throw=True)
	if pos_opening_shift:
		_ensure_opening_shift_for_invoice(pos_opening_shift, None)
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
	from frappe.query_builder.functions import Abs, Coalesce, Sum
	from frappe.utils import date_diff, getdate

	# Validate invoice and get fields needed for return period check
	si = frappe.qb.DocType("Sales Invoice")
	invoice_check = (
		frappe.qb.from_(si)
		.select(
			si.docstatus,
			si.is_return,
			si.pos_profile,
			si.posting_date,
			si.is_pos,
			si.grand_total,
			si.paid_amount,
			si.outstanding_amount,
			si.customer,
			si.customer_name,
			si.net_total,
			si.total_taxes_and_charges,
			si.currency,
			si.total,
			si.discount_amount,
			si.apply_discount_on,
			si.rounded_total,
			si.disable_rounded_total,
			si.change_amount,
			si.base_change_amount,
			si.status,
		)
		.where(si.name == invoice_name)
	).run(as_dict=True)

	if not invoice_check:
		frappe.throw(_("Invoice {0} does not exist").format(invoice_name))

	invoice_info = invoice_check[0]

	# Validate docstatus
	if invoice_info.docstatus != 1:
		frappe.throw(_("Invoice must be submitted to create a return"))

	# Check if it's already a return
	if invoice_info.is_return:
		frappe.throw(_("Cannot create return against a return invoice"))

	# Returns off in the POS Settings of the profile the return is made under: the
	# cashier's shift profile, else the original's (D-R3-10)
	shift_profile = (
		frappe.db.get_value("POS Opening Shift", pos_opening_shift, "pos_profile")
		if pos_opening_shift
		else None
	)
	_refuse_return_if_disallowed(shift_profile or invoice_info.pos_profile)

	# Check return validity period from POS Settings
	if invoice_info.pos_profile:
		return_validity_days = cint(
			frappe.db.get_value(
				"POS Settings", {"pos_profile": invoice_info.pos_profile}, "return_validity_days"
			)
			or 0
		)

		if return_validity_days > 0:
			days_since_invoice = date_diff(getdate(nowdate()), getdate(invoice_info.posting_date))
			if days_since_invoice > return_validity_days:
				frappe.throw(
					_(
						"Return period has expired. Invoice {0} was created {1} days ago. "
						"Returns are only allowed within {2} days of purchase."
					).format(invoice_name, days_since_invoice, return_validity_days)
				)

	# Use ERPNext's make_sales_return to create properly mapped return document
	# This automatically copies sales_team, taxes, and other child tables
	return_doc = make_sales_return(invoice_name)

	# Set POS-specific fields
	if pos_opening_shift:
		return_doc.posa_pos_opening_shift = pos_opening_shift

	# Ensure POS flags are set
	return_doc.is_pos = invoice_info.is_pos
	return_doc.pos_profile = invoice_info.pos_profile

	# Aggregate quantities already returned from previous return invoices
	ret_si = frappe.qb.DocType("Sales Invoice")
	ret_item = frappe.qb.DocType("Sales Invoice Item")

	returned_qty_results = (
		frappe.qb.from_(ret_si)
		.inner_join(ret_item)
		.on(ret_item.parent == ret_si.name)
		.select(
			Coalesce(ret_item.sales_invoice_item, ret_item.item_code).as_("key_field"),
			Sum(Abs(ret_item.qty)).as_("returned_qty"),
		)
		.where((ret_si.return_against == invoice_name) & (ret_si.docstatus == 1) & (ret_si.is_return == 1))
		.groupby(Coalesce(ret_item.sales_invoice_item, ret_item.item_code))
	).run(as_dict=True)

	returned_qty_map = {row["key_field"]: flt(row["returned_qty"]) for row in returned_qty_results}

	# Convert to dict and update items with remaining quantities
	return_dict = return_doc.as_dict()

	# Fetch original invoice payments for refund handling in frontend
	si_payment = frappe.qb.DocType("Sales Invoice Payment")
	payments_data = (
		frappe.qb.from_(si_payment)
		.select(si_payment.mode_of_payment, si_payment.amount, si_payment.base_amount, si_payment.account)
		.where(si_payment.parent == invoice_name)
	).run(as_dict=True)
	payments_data = _payments_net_of_change(
		payments_data, invoice_info.change_amount, invoice_info.base_change_amount
	)
	_set_refunded_by_mode(payments_data, invoice_name)

	# Cross-branch return: remap foreign payment modes to the current profile.
	#
	# When the original invoice's POS profile differs from the current shift's
	# profile, the original payment modes (e.g. "Cash lebanon") won't exist in
	# the current profile ("4- Boulaq"). _remap_foreign_payment_modes matches
	# by Mode of Payment type (Cash->Cash, Bank->Bank) so the frontend
	# pre-fills the correct refund method and the resulting GL entries debit
	# the correct branch cash/bank account.
	#
	# This is the primary fix point (Layer 1). The frontend and closing shift
	# code have additional safety nets for cases where this remap doesn't run
	# (e.g. no pos_opening_shift provided) or for already-submitted invoices
	# with the wrong payment mode.
	if pos_opening_shift:
		current_profile = frappe.db.get_value("POS Opening Shift", pos_opening_shift, "pos_profile")
		if current_profile:
			payments_data = _remap_foreign_payment_modes(
				payments_data, current_profile, invoice_info.pos_profile
			)

	# Include original invoice data for reference (payments, amounts, etc.)
	return_dict["_original_invoice"] = {
		"name": invoice_name,
		# The return dialog's status pill (D-R4-09 d)
		"status": invoice_info.status,
		"grand_total": invoice_info.grand_total,
		"paid_amount": invoice_info.paid_amount,
		"change_amount": invoice_info.change_amount,
		"outstanding_amount": invoice_info.outstanding_amount,
		"customer": invoice_info.customer,
		"customer_name": invoice_info.customer_name,
		"posting_date": invoice_info.posting_date,
		"payments": payments_data,
		"net_total": invoice_info.net_total,
		"total_taxes_and_charges": invoice_info.total_taxes_and_charges,
		# The return rounds as this invoice did (see _apply_return_rounding): the
		# dialog rounds its refund the same way.
		"rounded_total": invoice_info.rounded_total,
		"disable_rounded_total": cint(invoice_info.disable_rounded_total),
		# Cash still refundable on it: the dialog refunds no more (Ruling 147)
		"refundable_cash": _return_refundable_cash("Sales Invoice", invoice_name)[0],
		"smallest_currency_fraction_value": flt(
			frappe.get_cached_value("Currency", invoice_info.currency, "smallest_currency_fraction_value")
		),
	}

	row_tax = _return_row_tax(return_dict.get("items", []), return_dict.get("taxes", []))

	# Check if taxes are inclusive by inspecting the tax rows copied from the original
	# invoice (immutable after submission, unlike POS Settings which can change later).
	# Only consider percentage-based taxes (On Net Total, etc.) — Actual charge types
	# are never inclusive (same logic as sales_invoice_hooks.apply_tax_inclusive).
	applicable_taxes = [tax for tax in return_dict.get("taxes", []) if tax.get("charge_type") != "Actual"]
	tax_inclusive = bool(applicable_taxes) and all(
		tax.get("included_in_print_rate") for tax in applicable_taxes
	)

	precision = _currency_precision(invoice_info.currency)

	# Header discount: the server owns the return's discount (see
	# _apply_return_header_discount), so line rates stay at the original rates.
	# The refund shown to the cashier subtracts each row's share of the discount
	# still to be returned, so a full return shows exactly what is left to refund.
	discount_plan = _return_discount_plan("Sales Invoice", invoice_name)
	row_discounts = _full_return_row_discounts(discount_plan, precision) if discount_plan else {}
	# Without tax, or with inclusive tax, the line rate is what the customer was charged
	rate_is_gross = tax_inclusive or not applicable_taxes

	# make_sales_return already takes earlier returns off each row's qty, so
	# read the sold qty from the original rows (else they are taken off twice).
	original_row_qty = dict(
		frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": invoice_name, "parenttype": "Sales Invoice"},
			fields=["name", "qty"],
			as_list=True,
		)
	)

	def process_return_item(item):
		"""Process single item for return, returns None if not returnable."""
		item_ref = item.get("sales_invoice_item") or item.get("item_code")
		original_qty = abs(flt(original_row_qty.get(item.get("sales_invoice_item"), item.get("qty", 0))))
		remaining_qty = original_qty - returned_qty_map.get(item_ref, 0)

		if remaining_qty <= 0:
			return None

		# Get rate breakdown for display
		price_list_rate = flt(item.get("price_list_rate") or item.get("rate"), precision)
		net_rate = flt(item.get("net_rate") or item.get("rate"), precision)
		# This row's tax for the qty left to return, unrounded so qty x rate_with_tax
		# gives the row's refund (a free row has none).
		row_qty = abs(flt(item.get("qty")))
		exact_tax_per_unit = row_tax.get(item.get("idx"), 0) / row_qty if row_qty else 0
		tax_per_unit = flt(exact_tax_per_unit, precision)

		# For inclusive taxes, use the original rate (already includes tax) to prevent
		# ERPNext from back-calculating and double-reducing the tax.
		# With a header discount, also use the original rate: the server applies
		# the discount to the return (net_rate already has it, so it would count twice).
		# Otherwise (exclusive taxes) use net_rate as before.
		if tax_inclusive or discount_plan:
			item_rate = flt(item.get("rate"), precision)
			rate_with_tax = item_rate if tax_inclusive else net_rate + exact_tax_per_unit
			# Both price_list_rate and rate are tax-inclusive, so discount is their difference
			discount_per_unit = flt(price_list_rate - item_rate, precision)
		else:
			item_rate = net_rate
			rate_with_tax = net_rate + exact_tax_per_unit
			discount_per_unit = flt(price_list_rate - net_rate, precision)

		if discount_plan and rate_is_gross:
			# Unrounded per-unit figure: the dialog rounds qty x rate_with_tax per
			# row, so returning the full remaining qty gives the exact row refund.
			row_discount = row_discounts.get(item.get("sales_invoice_item"), 0)
			rate_with_tax = (item_rate * remaining_qty - row_discount) / remaining_qty

		return {
			**item,
			"original_qty": original_qty,
			"already_returned": original_qty - remaining_qty,
			"remaining_qty": remaining_qty,
			"qty": -remaining_qty,
			"price_list_rate": price_list_rate,
			"rate": item_rate,
			"discount_per_unit": discount_per_unit,
			"amount": flt(item_rate * -remaining_qty, precision),
			"tax_per_unit": tax_per_unit,
			"rate_with_tax": rate_with_tax,
			"tax_included_in_rate": tax_inclusive,
		}

	return_dict["items"] = [
		processed
		for item in return_dict.get("items", [])
		if (processed := process_return_item(item)) is not None
	]

	# Check if all items have been fully returned
	if not return_dict["items"]:
		frappe.throw(_("All items from this invoice have already been returned"))

	# make_sales_return copies the full header discount (negated). The server
	# works out the return's discount itself, so a caller that sends this dict
	# back must not carry a second one.
	for field in ("discount_amount", "base_discount_amount", "additional_discount_percentage"):
		return_dict[field] = 0

	return return_dict


def _return_discount_plan(doctype, invoice_name):
	"""What a return against ``invoice_name`` needs to share out its header discount.

	Returns ``None`` when the invoice has no header discount. Otherwise a dict:
	``discount`` (D), the original discount settings, ``rows`` (row name ->
	original qty and weight = net amount before the discount), ``weight``
	(sum of weights), and what earlier submitted returns already took:
	``prior_discount`` and ``prior_qty`` (row name -> qty).
	"""
	link_field = RETURN_ROW_LINK_FIELD.get(doctype)
	if not link_field:
		return None
	original = frappe.db.get_value(
		doctype,
		invoice_name,
		["discount_amount", "apply_discount_on", "is_cash_or_non_trade_discount", "currency"],
		as_dict=True,
	)
	if not original or not flt(original.discount_amount):
		return None

	rows = {}
	for row in frappe.get_all(
		f"{doctype} Item",
		filters={"parent": invoice_name, "parenttype": doctype},
		fields=["name", "qty", "net_amount", "distributed_discount_amount"],
	):
		rows[row.name] = frappe._dict(
			qty=abs(flt(row.qty)),
			weight=abs(flt(row.net_amount) + flt(row.distributed_discount_amount)),
		)

	earlier_returns = frappe.get_all(
		doctype,
		filters={"return_against": invoice_name, "is_return": 1, "docstatus": 1},
		fields=["name", "discount_amount"],
	)
	prior_qty = {}
	if earlier_returns:
		for row in frappe.get_all(
			f"{doctype} Item",
			filters={"parent": ["in", [r.name for r in earlier_returns]], "parenttype": doctype},
			fields=[link_field, "qty"],
		):
			linked = row.get(link_field)
			if linked:
				prior_qty[linked] = prior_qty.get(linked, 0) + abs(flt(row.qty))

	return frappe._dict(
		link_field=link_field,
		discount=abs(flt(original.discount_amount)),
		apply_discount_on=original.apply_discount_on,
		is_cash_or_non_trade_discount=original.is_cash_or_non_trade_discount,
		precision=_currency_precision(original.currency),
		rows=rows,
		weight=sum(r.weight for r in rows.values()),
		prior_discount=sum(abs(flt(r.discount_amount)) for r in earlier_returns),
		prior_qty=prior_qty,
	)


def _return_discount_amount(plan, return_qty):
	"""Header discount (positive) for a return of ``return_qty`` (row name -> qty).

	The return takes D x (its rows' share of the original net). The return
	that completes the invoice takes whatever is left, so all returns together
	give back exactly D.
	"""
	precision = plan.precision
	left = flt(plan.discount - plan.prior_discount, precision)
	if left <= 0 or not plan.weight:
		return 0
	# Rows with no weight (free items) carry no discount, so they need not be returned
	completes = all(
		plan.prior_qty.get(name, 0) + return_qty.get(name, 0) >= row.qty
		for name, row in plan.rows.items()
		if row.weight
	)
	if completes:
		return left
	share = sum(
		row.weight * min(return_qty.get(name, 0), row.qty) / row.qty
		for name, row in plan.rows.items()
		if row.qty
	)
	return min(flt(plan.discount * share / plan.weight, precision), left)


def _full_return_row_discounts(plan, precision):
	"""Split the discount still to be returned over the rows still to be returned.

	Matches what _return_discount_amount gives a return of everything left; the
	rounding remainder goes on the row with the largest share.
	"""
	left = flt(plan.discount - plan.prior_discount, precision)
	shares = {}
	for name, row in plan.rows.items():
		remaining = row.qty - plan.prior_qty.get(name, 0)
		if remaining > 0 and row.qty and plan.weight:
			shares[name] = flt(plan.discount * row.weight * remaining / row.qty / plan.weight, precision)
	if not shares or left <= 0:
		return {}
	largest = max(shares, key=shares.get)
	shares[largest] = flt(shares[largest] + left - sum(shares.values()), precision)
	return shares


def _apply_return_header_discount(invoice_doc):
	"""Set the header discount of a return against an invoice (the server owns it).

	Whatever discount the client sent is replaced. With no header discount on
	the original, the return gets none. Otherwise the return gets
	``-_return_discount_amount`` with the original's ``apply_discount_on``, so
	ERPNext spreads it over the rows the same way it did on the sale. The
	amount is used rather than ``additional_discount_percentage``: a percentage
	would be recomputed from the return's own totals and lose the exact remainder.
	"""
	if not (invoice_doc.get("is_return") and invoice_doc.get("return_against")):
		return
	invoice_doc.additional_discount_percentage = 0
	plan = _return_discount_plan(invoice_doc.doctype, invoice_doc.return_against)
	if not plan:
		invoice_doc.discount_amount = 0
		return

	return_qty = {}
	for row in invoice_doc.get("items", []):
		linked = row.get(plan.link_field)
		if linked in plan.rows:
			return_qty[linked] = return_qty.get(linked, 0) + abs(flt(row.qty))

	invoice_doc.apply_discount_on = plan.apply_discount_on
	if invoice_doc.meta.has_field("is_cash_or_non_trade_discount"):
		invoice_doc.is_cash_or_non_trade_discount = plan.is_cash_or_non_trade_discount
	invoice_doc.discount_amount = -_return_discount_amount(plan, return_qty)


def _payments_net_of_change(payments, change_amount, base_change_amount=None):
	"""The original payment rows as the customer kept them paid: change given back
	comes off the cash row (else the largest row), and empty rows are dropped.
	The return dialog starts its refund rows from these (D-R2-16)."""
	payments = [frappe._dict(p) for p in payments]
	change = flt(change_amount)
	if change and payments:
		cash = _refund_cash_row(payments)
		cash.amount = max(flt(cash.amount) - change, 0)
		if cash.get("base_amount") is not None:
			base_change = change if base_change_amount is None else flt(base_change_amount)
			cash.base_amount = max(flt(cash.base_amount) - base_change, 0)
	return [p for p in payments if flt(p.amount) > 0]


def _set_refunded_by_mode(payments, original_name):
	"""Set ``refunded`` on each original payment row: what earlier submitted returns
	refunded through its mode (D-R3-03).

	The return dialog shares a refund over the modes by what each still has to
	refund, so the last return lands every mode on its exact remainder. A mode on
	several rows is taken from them in order. Refunds through a mode the original
	did not use (a cross-branch remap) are not matched to any row.
	"""
	returns = frappe.get_all(
		DOCTYPE_SALES_INVOICE,
		filters={"return_against": original_name, "is_return": 1, "docstatus": 1},
		pluck="name",
	)
	left = {}
	if returns:
		for row in frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": ["in", returns], "parenttype": DOCTYPE_SALES_INVOICE},
			fields=["mode_of_payment", "amount"],
		):
			left[row.mode_of_payment] = left.get(row.mode_of_payment, 0) + abs(flt(row.amount))
	precision = frappe.get_precision("Sales Invoice Payment", "amount") or 2
	for row in payments:
		refunded = flt(min(flt(row.amount), left.get(row.mode_of_payment, 0)), precision)
		row["refunded"] = refunded
		if row.mode_of_payment in left:
			left[row.mode_of_payment] -= refunded


def _refund_cash_row(rows):
	"""The row a refund's rounding (or a sale's change) goes on: the first Cash
	row, else the largest one."""
	for row in rows:
		if frappe.get_cached_value("Mode of Payment", row.get("mode_of_payment"), "type") == "Cash":
			return row
	return max(rows, key=lambda row: abs(flt(row.get("amount"))))


def _apply_return_rounding(invoice_doc):
	"""A return against an invoice rounds as that invoice did (D-R2-16).

	The original's flag is read from its submitted record: the POS Profile may
	have changed since the sale, and a full return must refund what was paid.
	"""
	if invoice_doc.get("is_return") and invoice_doc.get("return_against"):
		invoice_doc.disable_rounded_total = cint(
			frappe.db.get_value(invoice_doc.doctype, invoice_doc.return_against, "disable_rounded_total")
		)


def _sent_return_refund(invoice_doc):
	"""A POS return's refund rows as sent, before ERPNext's totals see them.

	On a POS return that refunds more than its total, ERPNext's
	set_total_amount_to_default_mop replaces every payment row with one row on
	the default mode for the excess only (D-R2-16), so _set_return_refund works
	from this copy. ``None`` for anything else.
	"""
	if invoice_doc.doctype != DOCTYPE_SALES_INVOICE or not invoice_doc.get("is_return"):
		return None
	return [row.as_dict(no_default_fields=True) for row in invoice_doc.get("payments", [])]


def _return_refundable_cash(doctype, original_name):
	"""(cash still refundable, amount still owed) on a return's original (Ruling 147).

	What was paid on the original, at the POS or later, less what its submitted
	returns took back. Each return lowers the original's outstanding by its
	payable total less its refund and write-off, so this is the original's
	payable, less its write-off, its returns' payable totals (net of their
	write-offs) and what it still owes. A partly paid original thus refunds at
	most what was paid, and the returns together never refund more. A credit
	already given back (a negative outstanding) counts as refunded.
	"""
	original = frappe.db.get_value(
		doctype,
		original_name,
		["rounded_total", "grand_total", "write_off_amount", "outstanding_amount", "currency"],
		as_dict=True,
	)
	if not original:
		return None, 0
	precision = _currency_precision(original.currency)
	returned = sum(
		abs(flt(r.rounded_total or r.grand_total)) - abs(flt(r.write_off_amount))
		for r in frappe.get_all(
			doctype,
			filters={"return_against": original_name, "is_return": 1, "docstatus": 1},
			fields=["rounded_total", "grand_total", "write_off_amount"],
		)
	)
	owed = flt(original.outstanding_amount, precision)
	refundable = flt(
		flt(original.rounded_total or original.grand_total)
		- abs(flt(original.write_off_amount))
		- returned
		- max(owed, 0),
		precision,
	)
	return max(refundable, 0), owed


def _return_empties_original(invoice_doc):
	"""Whether this return takes back everything left of its original's paid rows.

	Free rows (no net amount) need not come back: they carry no money.
	"""
	link_field = RETURN_ROW_LINK_FIELD.get(invoice_doc.doctype)
	original = invoice_doc.get("return_against")
	if not (link_field and original):
		return False
	sold = {
		row.name: abs(flt(row.qty))
		for row in frappe.get_all(
			f"{invoice_doc.doctype} Item",
			filters={"parent": original, "parenttype": invoice_doc.doctype},
			fields=["name", "qty", "net_amount"],
		)
		if flt(row.net_amount)
	}
	if not sold:
		return False
	returned = {}
	earlier = frappe.get_all(
		invoice_doc.doctype,
		filters={"return_against": original, "is_return": 1, "docstatus": 1},
		pluck="name",
	)
	if earlier:
		for row in frappe.get_all(
			f"{invoice_doc.doctype} Item",
			filters={"parent": ["in", earlier], "parenttype": invoice_doc.doctype},
			fields=[link_field, "qty"],
		):
			returned[row.get(link_field)] = returned.get(row.get(link_field), 0) + abs(flt(row.qty))
	for row in invoice_doc.get("items", []):
		linked = row.get(link_field)
		returned[linked] = returned.get(linked, 0) + abs(flt(row.qty))
	return all(returned.get(name, 0) >= qty for name, qty in sold.items())


def return_payable_target(invoice_doc):
	"""The payable total a POS return must have, or ``None`` to keep ERPNext's (Ruling 151).

	A POS return being saved or submitted that empties its original (every paid row returned) of an
	original that owes nothing refunds exactly the paid remainder
	(_return_refundable_cash), even when its own rounded total differs: the
	partial returns before it took their own rounding. The return's
	rounded_total is set to it (see CustomSalesInvoice.calculate_taxes_and_totals),
	so ERPNext neither replaces the refund rows nor leaves a residue.
	Only when the return rounds: unrounded totals take no rounding to make up.
	"""
	if not (
		invoice_doc.doctype == DOCTYPE_SALES_INVOICE
		and cint(invoice_doc.get("is_pos"))
		and invoice_doc.get("is_return")
		and invoice_doc.get("return_against")
		# A draft, or the submit's own validate (docstatus is already 1 there)
		and (not invoice_doc.docstatus or getattr(invoice_doc, "_action", None) == "submit")
		and not cint(invoice_doc.get("disable_rounded_total"))
	):
		return None
	refundable, owed = _return_refundable_cash(invoice_doc.doctype, invoice_doc.return_against)
	if refundable is None or owed > 0 or not _return_empties_original(invoice_doc):
		return None
	return refundable


def return_target_is_rounding(invoice_doc, target):
	"""Whether ``target`` differs from the return's own rounded total by rounding only (Ruling 153).

	Each rounded document (the original and every submitted return on it,
	this one included) drifts by at most half the currency's rounding unit
	(its smallest fraction, else 1). A larger gap (an Actual charge copied
	onto every partial return, an earlier write-off) is no rounding: the
	return keeps ERPNext's total and _set_return_refund caps and writes it off.
	"""
	unit = (
		flt(
			frappe.db.get_value(
				"Currency", invoice_doc.currency, "smallest_currency_fraction_value", cache=True
			)
		)
		or 1
	)
	documents = (
		frappe.db.count(
			invoice_doc.doctype,
			{"return_against": invoice_doc.return_against, "is_return": 1, "docstatus": 1},
		)
		+ 1  # this return
		+ 1  # the original
	)
	gap = abs(flt(target) - abs(flt(invoice_doc.rounded_total)))
	return flt(gap, invoice_doc.precision("rounded_total")) <= flt(0.5 * unit * documents, 9)


def _set_return_refund(invoice_doc, sent):
	"""Refund a POS return through the rows the cashier chose (D-R2-16, Ruling 147).

	Run after the totals, with ``sent`` from _sent_return_refund. The return
	refunds its ``rounded_total or grand_total`` (it rounds like its original),
	but never more than is still refundable on the original
	(_return_refundable_cash):

	- no refund rows (or all 0), e.g. "Add to Customer Credit": kept, the return
	  stays outstanding as the customer's credit;
	- a rounding difference: taken up on the cash row (else the largest row);
	- a refund below that, while the original still owes money: kept (the
	  dialog refunds the paid share, the rest clears what is owed);
	- anything else is refused: the cashier was shown another amount.

	What the original neither still owes nor can refund (the rounding earlier
	partial returns took) is written off, so the returns together refund
	exactly what was paid.
	"""
	if sent is None:
		return
	rows = [frappe._dict(row) for row in sent]
	for row in rows:
		row.amount = abs(flt(row.amount))
	precision = invoice_doc.precision("paid_amount")
	sent_total = flt(sum(row.amount for row in rows), precision)
	payable = abs(flt(invoice_doc.rounded_total or invoice_doc.grand_total, precision))
	refundable, owed = payable, 0
	if invoice_doc.get("return_against"):
		refundable, owed = _return_refundable_cash(invoice_doc.doctype, invoice_doc.return_against)
		refundable = payable if refundable is None else min(payable, refundable)

	if sent_total:
		difference = flt(sent_total - refundable, precision)
		# What the dialog's per-row rounding and the return's rounding can account
		# for. It only gates the refusal: an accepted refund is set to the refundable.
		# ERPNext's own rounding of the return, not a payable set by return_payable_target.
		natural_rounding = (
			0
			if cint(invoice_doc.get("disable_rounded_total"))
			else round_based_on_smallest_currency_fraction(
				flt(invoice_doc.grand_total), invoice_doc.currency, precision
			)
			- flt(invoice_doc.grand_total)
		)
		tolerance = flt(
			abs(natural_rounding) + RETURN_REFUND_TOLERANCE * max(len(invoice_doc.get("items", [])), 1),
			precision,
		)
		keeps_lower = difference < 0 and owed > 0
		if abs(difference) > tolerance and not keeps_lower:
			frappe.throw(
				_(
					"The refund {0} does not match the refund due {1}. Reload the POS and open the return again."
				).format(
					frappe.format_value(sent_total, {"fieldtype": "Currency"}),
					frappe.format_value(refundable, {"fieldtype": "Currency"}),
				),
				title=_("Refund Mismatch"),
			)
		if difference and not keeps_lower:
			paying = [row for row in rows if row.amount] or rows
			row = _refund_cash_row(paying)
			if row.amount - difference < 0:
				row = max(paying, key=lambda r: r.amount)
			row.amount = flt(row.amount - difference, precision)

	for row in rows:
		row.amount = -row.amount
		row.base_amount = flt(row.amount * flt(invoice_doc.conversion_rate or 1), precision)
	invoice_doc.set("payments", rows)
	_set_payment_accounts(invoice_doc.payments, invoice_doc.company)
	_set_return_write_off(invoice_doc, flt(payable - max(owed, 0) - refundable, precision))
	invoice_doc.calculate_taxes_and_totals()


def _return_credit_amount(invoice_doc):
	"""What a submitted "Add to Customer Credit" return gives the customer (Ruling 151).

	Its payable, net of any write-off, but no more than the credit it left on its
	original: on a partly paid original the part that clears what was owed is no
	credit, so no wallet credit is made for money never paid.
	"""
	amount = abs(flt(invoice_doc.rounded_total or invoice_doc.grand_total)) - abs(
		flt(invoice_doc.write_off_amount)
	)
	if invoice_doc.get("return_against") and not invoice_doc.get("update_outstanding_for_self"):
		owed = flt(frappe.db.get_value(invoice_doc.doctype, invoice_doc.return_against, "outstanding_amount"))
		amount = min(amount, max(-owed, 0))
	return flt(max(amount, 0), invoice_doc.precision("grand_total"))


def _set_return_write_off(invoice_doc, amount):
	"""Write off ``amount`` (positive) of a return: what it would give back beyond
	what is refundable on its original (Ruling 147)."""
	amount = max(flt(amount), 0)
	invoice_doc.write_off_amount = -amount
	invoice_doc.base_write_off_amount = flt(-amount * flt(invoice_doc.conversion_rate or 1))
	if not amount:
		return
	profile = (
		frappe.db.get_value(
			"POS Profile",
			invoice_doc.pos_profile,
			["write_off_account", "write_off_cost_center"],
			as_dict=True,
		)
		if invoice_doc.get("pos_profile")
		else None
	) or frappe._dict()
	invoice_doc.write_off_account = invoice_doc.get("write_off_account") or profile.write_off_account
	invoice_doc.write_off_cost_center = (
		invoice_doc.get("write_off_cost_center") or profile.write_off_cost_center
	)


def _apply_return_taxes(invoice_doc):
	"""A return against an invoice carries that invoice's taxes (Ruling 147).

	Tax rows sent by the client, and today's POS Profile template, are ignored:
	the refund is priced from the original. Actual charges are negated, as in
	ERPNext's make_sales_return.
	"""
	if not (invoice_doc.get("is_return") and invoice_doc.get("return_against")):
		return
	original = frappe.get_doc(invoice_doc.doctype, invoice_doc.return_against)
	invoice_doc.taxes_and_charges = original.get("taxes_and_charges")
	invoice_doc.set("taxes", [])
	for tax in original.get("taxes", []):
		row = tax.as_dict(no_default_fields=True)
		if row.get("charge_type") == "Actual":
			row["tax_amount"] = -abs(flt(row.get("tax_amount")))
		invoice_doc.append("taxes", row)


@frappe.whitelist()
def search_invoices_for_return(
	invoice_name=None,
	company=None,
	customer_name=None,
	customer_id=None,
	mobile_no=None,
	from_date=None,
	to_date=None,
	min_amount=None,
	max_amount=None,
	page=1,
	doctype="Sales Invoice",
):
	"""Search for invoices that can be returned with pagination.

	Supports filtering by:
	- invoice_name: Partial match on invoice number
	- company: Exact match
	- customer_name, customer_id, mobile_no: Partial match (OR condition)
	- from_date, to_date: Date range
	- min_amount, max_amount: Amount range

	Returns invoices with their items adjusted to show remaining returnable quantities.
	"""
	ensure_desk_user()
	if doctype not in ALLOWED_RETURN_DOCTYPES:
		frappe.throw(_("Invalid invoice doctype"), frappe.PermissionError)
	frappe.has_permission(doctype, "read", throw=True)
	from frappe.query_builder.functions import Abs, Count, Sum

	page = max(cint(page) or 1, 1)
	page_length = 100
	start = (page - 1) * page_length

	# Build main invoice query
	si = frappe.qb.DocType(doctype)

	# Start building the query
	query = (
		frappe.qb.from_(si)
		.select(si.name, si.customer, si.customer_name, si.posting_date, si.grand_total, si.status)
		.where((si.docstatus == 1) & (si.is_return == 0))
		.orderby(si.posting_date, order=frappe.qb.desc)
		.orderby(si.name, order=frappe.qb.desc)
		.limit(page_length)
		.offset(start)
	)

	# Add company filter
	if company:
		query = query.where(si.company == company)

	# Add invoice name filter
	if invoice_name:
		query = query.where(si.name.like(f"%{invoice_name}%"))

	# Add date range filters
	if from_date and to_date:
		query = query.where(si.posting_date.between(from_date, to_date))
	elif from_date:
		query = query.where(si.posting_date >= from_date)
	elif to_date:
		query = query.where(si.posting_date <= to_date)

	# Add amount filters
	if min_amount and max_amount:
		query = query.where(si.grand_total.between(float(min_amount), float(max_amount)))
	elif min_amount:
		query = query.where(si.grand_total >= float(min_amount))
	elif max_amount:
		query = query.where(si.grand_total <= float(max_amount))

	# Search customers matching any of the provided criteria (OR logic)
	if customer_name or customer_id or mobile_no:
		cust = frappe.qb.DocType("Customer")
		cust_query = frappe.qb.from_(cust).select(cust.name).limit(100)

		# Build OR conditions for customer search
		cust_conditions = []
		if customer_name:
			cust_conditions.append(cust.customer_name.like(f"%{customer_name}%"))
		if customer_id:
			cust_conditions.append(cust.name.like(f"%{customer_id}%"))
		if mobile_no:
			cust_conditions.append(cust.mobile_no.like(f"%{mobile_no}%"))

		# Combine with OR
		if cust_conditions:
			combined_condition = cust_conditions[0]
			for cond in cust_conditions[1:]:
				combined_condition = combined_condition | cond
			cust_query = cust_query.where(combined_condition)

		customers = cust_query.run(as_dict=True)
		customer_ids = [c.name for c in customers]

		if customer_ids:
			query = query.where(si.customer.isin(customer_ids))
		else:
			return {"invoices": [], "has_more": False}

	# Execute main query
	invoices_list = query.run(as_dict=True)

	if not invoices_list:
		return {"invoices": [], "has_more": False}

	invoice_names = [inv["name"] for inv in invoices_list]

	# Count total matching invoices for pagination
	count_query = (
		frappe.qb.from_(si)
		.select(Count(si.name).as_("total"))
		.where((si.docstatus == 1) & (si.is_return == 0))
	)

	# Re-apply the same filters for count
	if company:
		count_query = count_query.where(si.company == company)
	if invoice_name:
		count_query = count_query.where(si.name.like(f"%{invoice_name}%"))
	if from_date and to_date:
		count_query = count_query.where(si.posting_date.between(from_date, to_date))
	elif from_date:
		count_query = count_query.where(si.posting_date >= from_date)
	elif to_date:
		count_query = count_query.where(si.posting_date <= to_date)
	if min_amount and max_amount:
		count_query = count_query.where(si.grand_total.between(float(min_amount), float(max_amount)))
	elif min_amount:
		count_query = count_query.where(si.grand_total >= float(min_amount))
	elif max_amount:
		count_query = count_query.where(si.grand_total <= float(max_amount))
	if customer_name or customer_id or mobile_no:
		if customer_ids:
			count_query = count_query.where(si.customer.isin(customer_ids))

	count_result = count_query.run(as_dict=True)
	total_count = count_result[0].total if count_result else 0

	# Batch fetch returned quantities for all invoices in current page
	ret_si = frappe.qb.DocType(doctype)
	ret_item = frappe.qb.DocType(f"{doctype} Item")

	returned_qty_results = (
		frappe.qb.from_(ret_si)
		.inner_join(ret_item)
		.on(ret_item.parent == ret_si.name)
		.select(
			ret_si.return_against.as_("invoice_name"),
			ret_item.item_code,
			Sum(Abs(ret_item.qty)).as_("returned_qty"),
		)
		.where(
			(ret_si.return_against.isin(invoice_names)) & (ret_si.docstatus == 1) & (ret_si.is_return == 1)
		)
		.groupby(ret_si.return_against, ret_item.item_code)
	).run(as_dict=True)

	# Build a map of invoice_name -> {item_code: returned_qty}
	returned_qty_map = {}
	for row in returned_qty_results:
		inv_name = row["invoice_name"]
		if inv_name not in returned_qty_map:
			returned_qty_map[inv_name] = {}
		returned_qty_map[inv_name][row["item_code"]] = flt(row["returned_qty"])

	# Batch fetch all items for invoices in current page
	si_item = frappe.qb.DocType(f"{doctype} Item")
	all_items = (
		frappe.qb.from_(si_item)
		.select(
			si_item.parent,
			si_item.name,
			si_item.item_code,
			si_item.item_name,
			si_item.qty,
			si_item.rate,
			si_item.amount,
			si_item.stock_qty,
			si_item.uom,
			si_item.warehouse,
		)
		.where(si_item.parent.isin(invoice_names))
		.orderby(si_item.idx)
	).run(as_dict=True)

	# Group items by parent invoice
	items_by_invoice = {}
	for item in all_items:
		parent = item["parent"]
		if parent not in items_by_invoice:
			items_by_invoice[parent] = []
		items_by_invoice[parent].append(item)

	# Process and return results
	data = []
	for invoice in invoices_list:
		inv_name = invoice["name"]
		returned_qty = returned_qty_map.get(inv_name, {})
		items = items_by_invoice.get(inv_name, [])

		# Calculate remaining quantities
		filtered_items = []
		for item in items:
			already_returned = returned_qty.get(item["item_code"], 0)
			remaining_qty = flt(item["qty"]) - already_returned

			if remaining_qty > 0:
				new_item = item.copy()
				new_item["qty"] = remaining_qty
				new_item["amount"] = remaining_qty * flt(item["rate"])
				if item.get("stock_qty") and item.get("qty"):
					new_item["stock_qty"] = flt(item["stock_qty"]) / flt(item["qty"]) * remaining_qty
				filtered_items.append(frappe._dict(new_item))

		# Only include invoices with returnable items
		if filtered_items or not returned_qty:
			invoice_data = frappe._dict(invoice)
			invoice_data["items"] = filtered_items if filtered_items else items
			data.append(invoice_data)

	# Check if there are more results
	has_more = (start + page_length) < total_count

	return {"invoices": data, "has_more": has_more}


# ==========================================
# Legacy/Helper Functions
# ==========================================


def _evaluate_transaction_offers(
	invoice,
	profile,
	pricing_items,
	customer,
	customer_group,
	territory,
	posting_date,
	currency,
	price_list,
	rule_map,
	selected_offer_names,
	blocked_rules=frozenset(),
):
	"""Run ERPNext's transaction-level pricing engine and collect free items.

	``blocked_rules``: one-time rules this customer may not get. ERPNext's
	engine picks rules with its own query, so a header discount it set from a
	blocked rule is worked out again from the other rules it applied.

	ERPNext routes `apply_on = "Transaction"` rules through a different entry
	point (`apply_pricing_rule_on_transaction`) than the per-item engine. That
	function mutates a real Sales Invoice document in place — appending free
	item rows via `doc.append("items", ...)` — so we build a transient,
	never-saved Sales Invoice document for evaluation only.

	Returns {"free_items": dict keyed by (item_code, rule_name), "applied_rules": set}.
	"""
	if not erpnext_apply_pricing_rule_on_transaction or not pricing_items:
		return {"free_items": {}, "applied_rules": set()}

	total_qty = sum(flt(it.qty) for it in pricing_items)
	total = sum(flt(it.qty) * flt(it.rate) for it in pricing_items)
	if total <= 0:
		return {"free_items": {}, "applied_rules": set()}

	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"is_pos": 1,
			"company": profile.company,
			"currency": currency,
			"conversion_rate": 1,
			"selling_price_list": price_list,
			"price_list_currency": currency,
			"plc_conversion_rate": 1,
			"customer": customer,
			"customer_group": customer_group,
			"territory": territory,
			"transaction_date": posting_date,
			"posting_date": posting_date,
			"pos_profile": invoice.get("pos_profile"),
			"coupon_code": invoice.get("coupon_code") or None,
		}
	)
	doc.flags.ignore_mandatory = True

	for prep in pricing_items:
		doc.append(
			"items",
			{
				"item_code": prep.item_code,
				"item_name": prep.item_name,
				"item_group": prep.item_group,
				"brand": prep.brand,
				"qty": prep.qty,
				"stock_qty": prep.stock_qty,
				"conversion_factor": prep.conversion_factor,
				"uom": prep.uom,
				"stock_uom": prep.stock_uom,
				"rate": prep.rate,
				"price_list_rate": prep.price_list_rate,
				"base_rate": prep.base_rate,
				"base_price_list_rate": prep.base_price_list_rate,
				"amount": flt(prep.rate) * flt(prep.qty),
				"warehouse": prep.warehouse,
			},
		)

	# filter_pricing_rules_for_qty_amount reads these straight off the doc
	# (erpnext/accounts/doctype/pricing_rule/utils.py:572).
	doc.total_qty = total_qty
	doc.total = total

	initial_item_count = len(doc.items)
	pre_addl_pct = flt(doc.get("additional_discount_percentage") or 0)
	pre_discount_amt = flt(doc.get("discount_amount") or 0)
	try:
		erpnext_apply_pricing_rule_on_transaction(doc)
	except Exception:
		# A misconfigured transaction-scoped rule must not break the per-item
		# discounts that have already been computed by the caller.
		frappe.log_error(frappe.get_traceback(), "POS Apply Offers (Transaction Rules)")
		return {
			"free_items": {},
			"applied_rules": set(),
			"additional_discount_percentage": 0,
			"discount_amount": 0,
			"apply_discount_on": None,
		}

	free_items = {}
	applied_rules = set()
	for row in doc.items[initial_item_count:]:
		if not getattr(row, "is_free_item", 0):
			continue
		rule_name = row.get("pricing_rules")
		if not rule_name or rule_name not in rule_map:
			continue
		if selected_offer_names and rule_name not in selected_offer_names:
			continue
		fid = frappe._dict(row.as_dict())
		fid.applied_promotional_scheme = rule_map[rule_name].promotional_scheme
		free_items[(row.item_code, rule_name)] = fid
		applied_rules.add(rule_name)

	# Capture header-level discount that ERPNext's apply_pricing_rule_on_transaction
	# set on the doc when a Price-type Transaction rule fired. ERPNext writes one of
	# additional_discount_percentage / discount_amount onto the doc (see
	# erpnext/accounts/doctype/pricing_rule/utils.py:578-616) but does not surface
	# which rule fired. We detect "fired" by diffing the doc fields against the
	# pre-call snapshot and attribute the application to every selected, in-scope
	# transaction-level Price rule in rule_map. The frontend treats the response
	# additional_discount_percentage / discount_amount as authoritative for the
	# header, so attribution mismatches only affect the UI badge, not totals.
	post_addl_pct = flt(doc.get("additional_discount_percentage") or 0)
	post_discount_amt = flt(doc.get("discount_amount") or 0)
	apply_discount_on = doc.get("apply_discount_on") or None

	engine_applied = _transaction_rules_applied(doc)
	if blocked_rules and blocked_rules.intersection(engine_applied):
		post_addl_pct, post_discount_amt, apply_discount_on = _replay_transaction_discount(
			doc,
			[name for name in engine_applied if name not in blocked_rules],
			pre_addl_pct,
			pre_discount_amt,
		)

	header_discount_changed = post_addl_pct != pre_addl_pct or post_discount_amt != pre_discount_amt
	if header_discount_changed:
		for rule_name, details in rule_map.items():
			if selected_offer_names and rule_name not in selected_offer_names:
				continue
			if details.get("price_or_product_discount") != "Price":
				continue
			if frappe.db.get_value("Pricing Rule", rule_name, "apply_on") != "Transaction":
				continue
			applied_rules.add(rule_name)

	return {
		"free_items": free_items,
		"applied_rules": applied_rules,
		"additional_discount_percentage": post_addl_pct,
		"discount_amount": post_discount_amt,
		"apply_discount_on": apply_discount_on,
	}


def _one_time_rule_blocked(rule_name, customer, default_customer):
	"""True when a one-time-per-customer rule may not apply to ``customer``.

	Walk-in / default customers can't be tracked, so they never get one-time
	rules; a named customer gets each one only until it is redeemed.
	"""
	from pos_next.pos_next.doctype.one_time_customer_offer_usage.one_time_customer_offer_usage import (
		is_redeemed,
	)

	if not customer or customer == default_customer:
		return True
	return is_redeemed(customer, rule_name)


def _one_time_used_message(rule_name) -> str:
	title = frappe.db.get_value("Pricing Rule", rule_name, "title") or rule_name
	return _("{0} was already used by this customer").format(title)


def _tracked_customer(invoice_doc) -> str | None:
	"""The invoice's customer when one-time offers are tracked for it: never the
	walk-in / default customer (``_one_time_rule_blocked``)."""
	customer = invoice_doc.get("customer")
	pos_profile = invoice_doc.get("pos_profile")
	default_customer = (
		frappe.get_cached_value("POS Profile", pos_profile, "customer") if pos_profile else None
	)
	return customer if customer and customer != default_customer else None


def _stamped_one_time_rules(customer, invoice_name=None) -> set[str]:
	"""One-time rules stamped on ``customer``'s other submitted sales."""
	filters = {
		"customer": customer,
		"docstatus": 1,
		"is_return": 0,
		"pos_applied_one_time_rules": ["is", "set"],
	}
	if invoice_name:
		filters["name"] = ["!=", invoice_name]
	rules = set()
	for stamp in frappe.get_all(DOCTYPE_SALES_INVOICE, filters=filters, pluck="pos_applied_one_time_rules"):
		try:
			rules.update(json.loads(stamp or "[]"))
		except (ValueError, TypeError):
			continue
	return rules


def _redeemed_one_time_rules(customer, invoice_name=None) -> set[str]:
	"""One-time rules ``customer`` already redeemed on another invoice: a usage row,
	or a stamp on another submitted sale (Ruling 111)."""
	usage = frappe.get_all(
		"One Time Customer Offer Usage",
		filters={"customer": customer},
		fields=["pricing_rule", "sales_invoice"],
	)
	redeemed = {row.pricing_rule for row in usage if not invoice_name or row.sales_invoice != invoice_name}
	return redeemed | _stamped_one_time_rules(customer, invoice_name)


def _redeemed_one_time_records(invoice_doc) -> tuple[str | None, dict]:
	"""(customer, {rule: record}) for the enabled one-time rules this invoice's tracked
	customer already redeemed on another invoice (``_redeemed_one_time_rules``)."""
	customer = _tracked_customer(invoice_doc)
	if not customer:
		return None, {}
	redeemed = _redeemed_one_time_rules(customer, invoice_doc.name)
	if not redeemed:
		return customer, {}
	records = frappe.get_all(
		"Pricing Rule",
		filters={"name": ["in", list(redeemed)], "one_time_per_customer": 1, "disable": 0},
		fields=["name", "apply_on", "price_or_product_discount", "free_item", "promotional_scheme"],
	)
	return customer, {record.name: record for record in records}


def _one_time_match_dates(invoice_doc) -> list:
	"""The sale's posting date, today and the day the invoice was first saved (its stored
	``creation``): a rule valid on any of them matches (Rulings 113, 120, 125)."""
	dates = {cstr(invoice_doc.get("posting_date") or nowdate()), nowdate()}
	created = _stored_creation_day(invoice_doc)
	if created:
		dates.add(created)
	return sorted(dates)


def _one_time_match_args(invoice_doc, customer) -> frappe._dict:
	customer_group, territory = frappe.get_cached_value(
		"Customer", customer, ["customer_group", "territory"]
	) or (None, None)
	return frappe._dict(
		doctype=invoice_doc.doctype,
		name=invoice_doc.name,
		transaction_type="selling",
		company=invoice_doc.get("company"),
		customer=customer,
		customer_group=customer_group,
		territory=territory,
		price_list=invoice_doc.get("selling_price_list")
		or (
			invoice_doc.get("pos_profile")
			and frappe.get_cached_value("POS Profile", invoice_doc.get("pos_profile"), "selling_price_list")
		),
	)


def _one_time_lookup_missing():
	"""ERPNext's rule lookup is gone: the check cannot run, so it fails closed."""
	frappe.throw(
		_("One-time offers could not be checked for this customer. Try again in a moment."),
		frappe.ValidationError,
	)


def _used_one_time_offer_rows(invoice_doc, rows, item_data, rules=None) -> dict[int, str]:
	"""{id(row): rule} for ``rows`` a one-time rule this customer already redeemed matches.

	A redeemed rule never reaches the offer evaluators, so it is matched here with
	ERPNext's own rule lookup on server data (item, item group, brand, UOM,
	warehouse, customer, customer group, territory, company, price list), on the
	posting date or today, before any quantity threshold or priority: the item is
	the offer's item. A gift rule also matches its ``free_item`` and, for a Gift Pool
	scheme, every item of its pools. The row's
	``pricing_rules`` play no part. Without the lookup the check raises.
	``rules`` ((customer, {rule: record})) replaces the redeemed rules.
	"""
	customer, redeemed = rules or _redeemed_one_time_records(invoice_doc)
	if not redeemed:
		return {}
	if not erpnext_get_item_pricing_rules:
		_one_time_lookup_missing()

	gifts = {}
	products = [record for record in redeemed.values() if record.price_or_product_discount == "Product"]
	pools = _gift_pool_groups({record.promotional_scheme for record in products if record.promotional_scheme})
	for record in products:
		# The gift, and every item of a Gift Pool scheme's pools (Ruling 116).
		codes = {record.free_item} if record.free_item else set()
		for pool in (pools.get(record.promotional_scheme) or {}).values():
			codes |= pool
		for code in codes:
			gifts.setdefault(code, []).append(record.name)
	base = _one_time_match_args(invoice_doc, customer)
	dates = _one_time_match_dates(invoice_doc)
	used = {}
	for row in rows:
		matched = set(gifts.get(row.item_code, ()))
		for date in dates:
			args = frappe._dict(
				base,
				item_code=row.item_code,
				item_group=item_data.get(row.item_code, "item_group"),
				brand=item_data.get(row.item_code, "brand"),
				uom=row.get("uom"),
				warehouse=row.get("warehouse"),
				transaction_date=date,
			)
			matched.update(
				rule.name
				for apply_on in ("Item Code", "Item Group", "Brand")
				for rule in erpnext_get_item_pricing_rules(apply_on, args, {})
				if rule.name in redeemed
			)
		if matched:
			used[id(row)] = sorted(matched)[0]
	return used


def _used_one_time_transaction_rule(invoice_doc, rules=None) -> str | None:
	"""A one-time transaction rule this customer already redeemed whose conditions match
	this cart, or None.

	ERPNext's own transaction evaluation on server data: its rule conditions (company,
	customer, customer group, territory, validity on the posting date or today), its
	quantity and amount thresholds on the cart's totals, and its Python condition.
	Without the lookup the check raises. ``rules`` ((customer, {rule: record}))
	replaces the redeemed rules.
	"""
	customer, redeemed = rules or _redeemed_one_time_records(invoice_doc)
	names = tuple(name for name, record in redeemed.items() if record.apply_on == "Transaction")
	if not names:
		return None
	if not (
		erpnext_get_other_conditions
		and erpnext_filter_pricing_rules_for_qty_amount
		and erpnext_filter_pricing_rule_based_on_condition
	):
		_one_time_lookup_missing()
	base = _one_time_match_args(invoice_doc, customer)
	for date in _one_time_match_dates(invoice_doc):
		values = {"one_time_rules": names}
		conditions = erpnext_get_other_conditions(
			"`tabPricing Rule`.name in %(one_time_rules)s", values, frappe._dict(base, transaction_date=date)
		)
		rules = frappe.db.sql(
			f"select `tabPricing Rule`.* from `tabPricing Rule` where {conditions} "
			"and `tabPricing Rule`.disable = 0 and `tabPricing Rule`.apply_on = 'Transaction'",
			values,
			as_dict=True,
		)
		rules = erpnext_filter_pricing_rules_for_qty_amount(
			invoice_doc.get("total_qty"), invoice_doc.get("total"), rules
		)
		rules = erpnext_filter_pricing_rule_based_on_condition(rules, invoice_doc)
		if rules:
			return sorted(rule.name for rule in rules)[0]
	return None


def _server_line_rules(result, indexes) -> set[str]:
	"""Rules the server's offer evaluation ``result`` applied to its paid lines ``indexes``."""
	applied = set(result.get("applied_pricing_rules") or [])
	items = result.get("items") or []
	names = set()
	for idx in indexes:
		if idx < len(items):
			names.update(set(_rule_names(_pricing_rule_to_string(items[idx].get("pricing_rules")))) & applied)
	return names


def _stamp_server_one_time_rules(invoice_doc, result, indexes) -> None:
	"""Add to the stamp the one-time rules the server's offer evaluation applied to the
	discounted paid lines ``indexes``, so a redemption never depends on the client
	sending the rule's name."""
	names = _server_line_rules(result, indexes)
	if not names:
		return
	one_time = frappe.get_all(
		"Pricing Rule", filters={"name": ["in", list(names)], "one_time_per_customer": 1}, pluck="name"
	)
	if one_time:
		stamped = json.loads(invoice_doc.get("pos_applied_one_time_rules") or "[]")
		invoice_doc.pos_applied_one_time_rules = json.dumps(sorted(set(stamped) | set(one_time)))


def _offline_safe(offline_sync, invoice_doc, empty, fn, *args):
	"""``fn(*args)``; on an offline sync an error is logged and ``empty()`` returned,
	so a one-time offer check never refuses a sale already made (Ruling 111)."""
	if not offline_sync:
		return fn(*args)
	savepoint = "pos_next_one_time_offer"
	frappe.db.savepoint(savepoint)
	try:
		return fn(*args)
	except Exception as error:
		frappe.db.rollback(save_point=savepoint)
		reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
		log_error_without_telemetry(
			UNEXPLAINED_DISCOUNT_LOG_TITLE,
			f"Invoice {reference}: one-time offers could not be checked ({type(error).__name__}: {error})",
		)
		return empty()


def _redeem_one_time_rules(invoice_doc, offline_sync=False) -> None:
	"""Record the one-time offers this sale redeems, just before it is submitted.

	Each stamped rule takes the customer's usage row (``redeem``): its name is the
	(customer, rule) key, so a second tab or device redeeming the same rule waits
	on the first insert and then finds it taken. A rule stamped on another
	submitted sale is taken too, and so is one whose key is still held when the
	lock wait times out. A taken rule refuses the submit online with the offer's
	"already used"; an offline sync keeps the sale and logs, and drops a timed-out
	rule from its stamp so no on_submit recorder waits on the key again. The
	walk-in customer is never tracked.

	The pos_next before_submit hook (``check_one_time_offers_on_submit``) leaves a
	sale checked here alone.
	"""
	from pos_next.pos_next.doctype.one_time_customer_offer_usage import one_time_customer_offer_usage

	# An F&F row left to promotions was never judged on the computed rate: before_submit
	# judges the sale again then (Ruling 126).
	if not _fnf_rows_left_to_promotions(invoice_doc, offline_sync):
		invoice_doc.flags.pos_one_time_checked = True
	if invoice_doc.get("is_return"):
		return
	customer = _tracked_customer(invoice_doc)
	try:
		rules = json.loads(invoice_doc.get("pos_applied_one_time_rules") or "[]")
	except (ValueError, TypeError):
		rules = []
	if not customer or not rules:
		return
	timed_out = set()

	def taken_rules():
		stamped_elsewhere = _stamped_one_time_rules(customer, invoice_doc.name)
		taken = []
		for rule in sorted(rules):
			try:
				redeemed = one_time_customer_offer_usage.redeem(customer, rule, invoice_doc.name)
			except frappe.QueryTimeoutError:
				timed_out.add(rule)
				redeemed = False
			if not redeemed or rule in stamped_elsewhere:
				taken.append(_one_time_used_message(rule))
		return taken

	taken = _offline_safe(offline_sync, invoice_doc, list, taken_rules)
	if not taken:
		return
	if not offline_sync:
		_refuse("<br>".join(taken), UNEXPLAINED_DISCOUNT_LOG_TITLE)
	if timed_out:
		kept = sorted(set(rules) - timed_out)
		invoice_doc.pos_applied_one_time_rules = json.dumps(kept) if kept else ""
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for problem in taken:
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")


def check_one_time_offers_on_submit(doc) -> None:
	"""Sales Invoice before_submit, any origin (Desk, an invoice billed from a Sales
	Order, a printed draft at shift close): every one-time rule the sale carries or
	matches is redeemed here, under the same (customer, rule) key as the POS
	(Rulings 113, 114). The first use counts; a rule already redeemed on another
	invoice (usage row or stamp) refuses the submit, and an offline sync logs.

	Carries: the rule is stamped, or named on a row or in the header's pricing rules.
	Matches: the server's offer evaluation applied it to a discounted row; a free row,
	or a row discounted beyond what that evaluation explains, the rule matches
	(``_used_one_time_offer_rows``); a header discount on a cart the conditions of a
	rule not yet used match (``_used_one_time_transaction_rule``). A used rule refuses
	a header only for its part no regular offer or coupon explains
	(``_unexplained_header``, as on the POS). The redeemed rules are added to the stamp;
	the on_submit recorders then find their rows. A sale ``submit_invoice`` already
	checked and recorded (``_redeem_one_time_rules``) is not redeemed again.

	First, on every route and every sale, each F&F-marked row is judged on the F&F rate
	the server computes (``_fnf_rows_on_submit``, Ruling 128): this is the one place a
	Desk, ``frappe.client.submit``, credit-sale or shift-close submit cannot skip.
	"""
	# A return or debit note adjusts a sale; a consolidated invoice merges checked ones.
	if doc.get("is_return") or doc.get("is_debit_note") or doc.get("is_consolidated"):
		return
	offline_sync = bool(doc.flags.pos_offline_sync)
	# Every route ends here, so every F&F row is judged here, also on a sale the POS
	# already checked (Ruling 128).
	problems, held = _offline_safe(offline_sync, doc, lambda: ([], []), _fnf_rows_on_submit, doc)
	if not doc.flags.pos_one_time_checked:
		problems = problems + _offline_safe(offline_sync, doc, list, _redeem_on_submit, doc)
	# A used offer's F&F row is "already used" in both checks: say it once.
	problems = list(dict.fromkeys(problems))
	if problems and not offline_sync:
		_refuse("<br>".join(problems), UNEXPLAINED_DISCOUNT_LOG_TITLE)
	# Submitted: no longer a draft (rolled back with the submit if it fails later).
	_forget_checked_paid_draft(doc)
	_write_server_pricing_rules(doc)
	problems = list(dict.fromkeys(problems + held))
	if not problems:
		return
	reference = doc.name or doc.get("offline_id") or "new"
	for problem in problems:
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")


def _write_server_pricing_rules(doc) -> None:
	"""Put on each paid row the Pricing Rules the server's own offer evaluation applied
	to it, for the rows that evaluation explained (Ruling 137); never a client name.

	Paid rows are saved with a blank ``pricing_rules`` (``_reset_row_pricing_rules``: a
	stored row that lists rules has its discount zeroed by ERPNext on the next save of
	the invoice). before_submit runs after the last validate, so the names written here
	are stored once and never re-priced; returns clear them (ERPNext's return mapping).
	Runs after the one-time checks above, which judge the rows as saved.
	"""
	carried = (frappe.flags.pos_server_row_rules or {}).pop(doc.name, None) or {}
	for row in doc.get("items") or []:
		if cint(row.get("is_free_item")):
			continue
		names = row.flags.pos_server_rules
		if names is None:
			names = carried.get(row.name)
		if names:
			row.pricing_rules = names


def _redeem_on_submit(doc) -> list[str]:
	"""Redeem every one-time rule ``doc`` carries or matches; the "already used"
	messages of the rules another invoice holds."""
	from pos_next.pos_next.doctype.one_time_customer_offer_usage import one_time_customer_offer_usage

	customer = _tracked_customer(doc)
	if not customer:
		return []
	records = {
		record.name: record
		for record in frappe.get_all(
			"Pricing Rule",
			filters={"one_time_per_customer": 1, "disable": 0, "selling": 1},
			fields=["name", "apply_on", "price_or_product_discount", "free_item", "promotional_scheme"],
		)
	}
	if not records:
		return []
	try:
		stamped = set(json.loads(doc.get("pos_applied_one_time_rules") or "[]"))
	except (ValueError, TypeError):
		stamped = set()
	carried = set(stamped)
	rows = [row for row in doc.get("items") or [] if row.get("item_code")]
	for row in rows:
		carried.update(_rule_names(row.get("pricing_rules") or ""))
	carried.update(row.pricing_rule for row in doc.get("pricing_rules") or [] if row.get("pricing_rule"))
	rules = carried & set(records)

	context = _pricing_context(doc)
	paid_rows = _paid_rows(doc)
	context.load(rows)
	item_data = context.item_data
	index = {id(row): idx for idx, row in enumerate(paid_rows)}
	discounted, below = [], []
	for row in rows:
		precision = row.precision("rate")
		tolerance = 10 ** -cint(2 if precision is None else precision)
		# The server's list price (``_list_prices``) or the row's, whichever is higher,
		# as the row's own may be the caller's.
		list_price = max(flt(context.list_prices.get(id(row))), flt(row.get("price_list_rate")))
		if cint(row.get("is_free_item")):
			discounted.append(row)
		elif flt(row.rate) < list_price - tolerance:
			below.append((row, list_price, tolerance))
	# Only a row some one-time rule matches can redeem or re-give one: the server's offers
	# are evaluated for those alone.
	matched = (
		_used_one_time_offer_rows(doc, [row for row, *_ in below], item_data, (customer, records))
		if below
		else {}
	)
	dates = _offer_dates(doc)
	# F&F explains a marked row only down to the rate the provider computes (Ruling 120).
	fnf_rates = _fnf_line_rates(
		doc, {id(row): list_price for row, list_price, _t in below if id(row) in matched}
	)
	coupon_rates, offers_on = {}, []
	for row, list_price, tolerance in below:
		if id(row) not in matched:
			continue
		idx = index[id(row)]
		# The server's offers without the redeemed one-time rules (``_evaluate_offers``,
		# Ruling 117), on each date (``_offer_dates``); the most any gives explains.
		offers = [_offer_rate(context.paid_offers(paid_rows, on)[0], idx, list_price) for on in dates]
		offer = min((rate for rate in offers if rate is not None), default=None)
		coupon, stacked = None, False
		code = row.get("posnext_coupon_code")
		if code:
			# pos_next's coupon resolver, for the invoice's own coupon only (Ruling 118).
			if code not in coupon_rates:
				coupon_rates[code] = _coupon_line_rates(doc, code, paid_rows, context)
			coupon = coupon_rates[code][0].get(idx)
			stacked = idx in coupon_rates[code][1]
		fnf = fnf_rates.get(id(row))
		other = min((rate for rate in (coupon, fnf) if rate is not None), default=None)
		if (offer is not None and (other is None or offer < other)) or (
			stacked and flt(row.rate) <= coupon + tolerance
		):
			# The offer is the row's discount, or part of it under an "Add on top" coupon
			# (D-R3-04): a one-time rule it applied is this sale's use.
			offers_on.append(idx)
		explained = min(rate for rate in (list_price, offer, coupon, fnf) if rate is not None)
		# Any rest is a discount the matching one-time rule redeems or re-gives.
		if flt(row.rate) < explained - tolerance:
			discounted.append(row)
	for on in dates if offers_on else ():
		rules.update(_server_line_rules(context.paid_offers(paid_rows, on)[0], offers_on) & set(records))
	if discounted:
		rules.update(_used_one_time_offer_rows(doc, discounted, item_data, (customer, records)).values())
	header_taken = []
	tolerance = 10 ** -cint(_currency_precision(doc.get("currency")))
	if flt(doc.get("discount_amount")) > tolerance:
		redeemed = _redeemed_one_time_records(doc)[1]
		unredeemed = {name: record for name, record in records.items() if name not in redeemed}
		# A one-time cart offer this customer has not used yet: the header redeems it.
		header_rule = _used_one_time_transaction_rule(doc, (customer, unredeemed))
		if header_rule:
			rules.add(header_rule)
		# On a cart a used cart or item offer matches, the part of the header no regular
		# offer or coupon explains (as on the POS) re-gives it (Ruling 116). The match is
		# looked up first: the offers are evaluated only when it finds one.
		used = _used_one_time_transaction_rule(doc, (customer, redeemed)) or _used_one_time_item_in_cart(
			doc, item_data
		)
		if used and _unexplained_header(doc, dates).manual > tolerance:
			header_taken.append(_one_time_used_message(used))
	if not rules:
		return header_taken

	stamped_elsewhere = _stamped_one_time_rules(customer, doc.name)
	taken, recorded = [], set()
	for rule in sorted(rules):
		try:
			redeemed = one_time_customer_offer_usage.redeem(customer, rule, doc.name)
		except frappe.QueryTimeoutError:
			redeemed = False
		if redeemed and rule not in stamped_elsewhere:
			recorded.add(rule)
		else:
			taken.append(_one_time_used_message(rule))
	if recorded - stamped and doc.meta.has_field("pos_applied_one_time_rules"):
		doc.pos_applied_one_time_rules = json.dumps(sorted(stamped | recorded))
	return taken + header_taken


def _offer_dates(doc) -> list:
	"""Dates the before_submit check evaluates offers on: the evaluator's own (today, as
	None), then the day the invoice was first saved (its STORED ``creation``), so a
	printed draft closed the next day keeps its sale day's offers (Ruling 118). Never
	the caller's ``posting_date``, nor a ``creation`` set on the document in memory;
	an unsaved invoice has today only (Ruling 125)."""
	created = _stored_creation_day(doc)
	return [None, created] if created and created != nowdate() else [None]


def _stored_creation_day(doc) -> str | None:
	"""The day the invoice was first saved, read from the database by name, or None."""
	if not doc.get("name") or (getattr(doc, "is_new", None) and doc.is_new()):
		return None
	created = frappe.db.get_value(doc.doctype, doc.name, "creation")
	return cstr(getdate(created)) if created else None


def _used_one_time_item_in_cart(invoice_doc, item_data=None) -> str | None:
	"""An item (or gift) one-time rule this customer already redeemed that matches any
	paid or free row of the cart, or None: such a cart takes no manual header
	discount (Ruling 116)."""
	rows = [row for row in invoice_doc.get("items") or [] if row.get("item_code")]
	if not rows:
		return None
	if item_data is None:
		item_data = _pricing_context(invoice_doc).item_data
	item_data.load(row.item_code for row in rows)
	used = _used_one_time_offer_rows(invoice_doc, rows, item_data)
	return sorted(used.values())[0] if used else None


def _transaction_rules_applied(doc):
	"""Transaction-level rules ERPNext applied to ``doc``, in order.

	ERPNext records them as ``pricing_rules`` rows without an item.
	"""
	return list(
		dict.fromkeys(
			row.pricing_rule
			for row in doc.get("pricing_rules") or []
			if row.pricing_rule and not row.get("item_code") and not row.get("child_docname")
		)
	)


def _replay_transaction_discount(doc, rule_names, addl_pct, discount_amt):
	"""Header discount from Price-type transaction rules, set in order as ERPNext does.

	The fields are set on ``doc`` (the transient evaluation invoice) and its
	totals recalculated, so a percentage rule's amount is worked out by ERPNext
	on the right base (``apply_discount_on``). The POS reads only the amount.
	"""
	apply_discount_on = None
	for name in rule_names:
		rule = frappe.db.get_value(
			"Pricing Rule",
			name,
			["price_or_product_discount", "apply_discount_on", "discount_percentage", "discount_amount"],
			as_dict=True,
		)
		if not rule or rule.price_or_product_discount != "Price":
			continue
		if rule.apply_discount_on:
			apply_discount_on = rule.apply_discount_on
		if flt(rule.discount_percentage):
			addl_pct = flt(rule.discount_percentage)
		if flt(rule.discount_amount):
			discount_amt = flt(rule.discount_amount)

	doc.additional_discount_percentage = addl_pct
	doc.discount_amount = discount_amt
	if apply_discount_on:
		doc.apply_discount_on = apply_discount_on
	doc.calculate_taxes_and_totals()
	return (
		flt(doc.additional_discount_percentage),
		flt(doc.discount_amount),
		doc.get("apply_discount_on") or None,
	)


def _server_free_row_rules(items) -> set[str]:
	"""Rule names the server put on free rows (``_check_free_rows_backed``): never a
	name the client sent (Ruling 113). Paid rows are stamped by
	``_stamp_server_one_time_rules``."""
	return {
		name
		for row in items
		if cint(row.get("is_free_item")) and (row.flags.pos_backing_rule or row.flags.pos_server_rule)
		for name in _rule_names(row.get("pricing_rules") or "")
	}


def _stamp_one_time_item_rules(invoice_doc, rule_names) -> None:
	"""Stamp ``pos_applied_one_time_rules`` with the one-time rules among the rows' rules.

	Server-side only: the client's value is stripped (``_strip_server_managed_fields``).
	"""
	one_time_applied = (
		frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", list(rule_names)], "one_time_per_customer": 1},
			pluck="name",
		)
		if rule_names
		else []
	)
	invoice_doc.pos_applied_one_time_rules = json.dumps(sorted(one_time_applied)) if one_time_applied else ""


def _stamp_one_time_transaction_rules(invoice_doc, pos_profile_doc=None) -> None:
	"""After totals: add the one-time transaction rules behind the header discount."""
	txn_one_time = _applied_one_time_transaction_rules(
		invoice_doc, pos_profile_doc.customer if pos_profile_doc else None
	)
	if txn_one_time:
		stamped = json.loads(invoice_doc.pos_applied_one_time_rules or "[]")
		invoice_doc.pos_applied_one_time_rules = json.dumps(sorted(set(stamped) | set(txn_one_time)))


def _applied_one_time_transaction_rules(invoice_doc, default_customer=None):
	"""One-time transaction-level rules behind this sale's header discount.

	The POS sends the header discount, not the rule that produced it. Run
	ERPNext's transaction engine on a throwaway copy (without the discount) and
	keep the one-time rules it applies whose discount matches the invoice.
	"""
	pct = flt(invoice_doc.get("additional_discount_percentage"))
	amount = flt(invoice_doc.get("discount_amount"))
	customer = invoice_doc.get("customer")
	if not (pct or amount) or not customer or customer == default_customer:
		return []
	if not erpnext_apply_pricing_rule_on_transaction:
		return []
	candidates = frappe.get_all(
		"Pricing Rule",
		filters={
			"disable": 0,
			"apply_on": "Transaction",
			"one_time_per_customer": 1,
			"selling": 1,
			"company": invoice_doc.company,
			"price_or_product_discount": "Price",
		},
		fields=["name", "discount_percentage", "discount_amount", "apply_discount_on"],
	)
	if not candidates:
		return []

	probe = frappe.copy_doc(invoice_doc)
	probe.additional_discount_percentage = 0
	probe.discount_amount = 0
	probe.set("pricing_rules", [])
	probe.flags.ignore_mandatory = True
	try:
		probe.calculate_taxes_and_totals()
		# Totals before any header discount: the base a percentage rule applies to
		base = {"Grand Total": flt(probe.grand_total), "Net Total": flt(probe.net_total)}
		erpnext_apply_pricing_rule_on_transaction(probe)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "POS One-Time Transaction Rule Check")
		return []

	precision = _currency_precision(invoice_doc.get("currency"))
	invoice_amount = flt(amount, precision)

	def rule_amount(rule):
		if flt(rule.discount_amount):
			return flt(rule.discount_amount, precision)
		return flt(
			base[rule.apply_discount_on or "Grand Total"] * flt(rule.discount_percentage) / 100, precision
		)

	# ponytail: NOTE heuristic ceiling. The POS sends only the header discount
	# amount, so a rule counts as used when the engine applies it and its
	# discount equals the invoice's. A manual header discount of the same value
	# would be recorded as that rule. Phase 4 sends the applied rule names.
	applied = set(_transaction_rules_applied(probe))
	return sorted(
		rule.name
		for rule in candidates
		if rule.name in applied
		and (
			(pct and flt(rule.discount_percentage) == pct)
			or (invoice_amount and rule_amount(rule) == invoice_amount)
		)
	)


@frappe.whitelist()
def apply_offers(invoice_data, selected_offers=None):
	"""Calculate and apply promotional offers using ERPNext Pricing Rules.

	Args:
	        invoice_data (str | dict): Sales Invoice payload used for offer evaluation.
	        selected_offers (str | list | None): Optional collection of Pricing Rule names.
	                When provided, results are filtered to only include these rules.
	                ERPNext handles all conflict resolution based on priority.
	"""
	ensure_desk_user()
	return _apply_offers(invoice_data, selected_offers)


def _apply_offers(invoice_data, selected_offers=None, profile=None):
	"""``apply_offers``; ``profile`` replaces the payload's POS Profile (a Desk sale's
	pricing facts, ``_desk_pricing_profile``)."""
	try:
		if isinstance(invoice_data, str):
			invoice_data = json.loads(invoice_data or "{}")

		invoice = frappe._dict(invoice_data or {})
		items = invoice.get("items") or []

		if isinstance(selected_offers, str):
			try:
				selected_offers = json.loads(selected_offers)
			except ValueError:
				selected_offers = [selected_offers]

		if isinstance(selected_offers, list | tuple | set):
			selected_offer_names = {cstr(name) for name in selected_offers if cstr(name)}
		else:
			selected_offer_names = set()

		if not items:
			return {"items": []}

		if not (profile or invoice.get("pos_profile")) or not erpnext_apply_pricing_rule:
			# Either no POS profile supplied or ERPNext promotional engine unavailable
			return {"items": items}

		profile = profile or frappe.get_cached_doc("POS Profile", invoice.get("pos_profile"))

		# Respect POS Profile's ignore_pricing_rule setting
		if profile.ignore_pricing_rule:
			return {"items": items}

		# Batch fetch all item details in a single query (reduces N queries to 1)
		item_codes = list({item.get("item_code") for item in items if item.get("item_code")})
		item_details_map = {}
		if item_codes:
			item_records = frappe.get_all(
				"Item",
				filters={"name": ["in", item_codes]},
				fields=["name", "item_name", "item_group", "brand", "stock_uom"],
			)
			item_details_map = {r.name: r for r in item_records}

		pricing_items = []
		index_map = []
		prepared_items = [frappe._dict(row) for row in items]

		for idx, item in enumerate(prepared_items):
			item_code = item.get("item_code")
			qty = flt(item.get("qty") or item.get("quantity") or 0)

			if not item_code or qty <= 0:
				continue

			# Use batch-fetched item details
			cached = item_details_map.get(item_code)

			conversion_factor = flt(item.get("conversion_factor") or 1) or 1
			price_list_rate = flt(item.get("price_list_rate") or item.get("rate") or 0)

			pricing_items.append(
				frappe._dict(
					{
						"doctype": "Sales Invoice Item",
						"name": item.get("name") or f"POS-{idx}",
						"item_code": item_code,
						"item_name": (cached.item_name if cached else item.get("item_name")),
						"item_group": (cached.item_group if cached else item.get("item_group")),
						"brand": (cached.brand if cached else item.get("brand")),
						"qty": qty,
						"stock_qty": qty * conversion_factor,
						"conversion_factor": conversion_factor,
						"uom": item.get("uom")
						or item.get("stock_uom")
						or (cached.stock_uom if cached else None),
						"stock_uom": item.get("stock_uom") or (cached.stock_uom if cached else None),
						"price_list_rate": price_list_rate,
						"base_price_list_rate": price_list_rate,
						"rate": flt(item.get("rate") or price_list_rate),
						"base_rate": flt(item.get("rate") or price_list_rate),
						"discount_percentage": 0,
						"discount_amount": 0,
						"warehouse": item.get("warehouse") or profile.warehouse,
						"parenttype": invoice.get("doctype") or "Sales Invoice",
					}
				)
			)
			index_map.append(idx)

			# Clear previously applied promotional metadata if the
			# current quantity can no longer satisfy the rule.
			item.discount_percentage = 0
			item.discount_amount = 0
			item.pricing_rules = []
			item.applied_promotional_schemes = []

		if not pricing_items:
			return {"items": items}

		company_currency = frappe.get_cached_value("Company", profile.company, "default_currency")

		# Get customer details if customer is provided
		customer = invoice.get("customer")
		customer_group = invoice.get("customer_group")
		territory = invoice.get("territory")

		if customer and not customer_group:
			# Fetch customer_group from customer
			try:
				customer_data = frappe.get_cached_value(
					"Customer", customer, ["customer_group", "territory"], as_dict=1
				)
				if customer_data:
					customer_group = customer_data.get("customer_group")
					if not territory:
						territory = customer_data.get("territory")
			except Exception as e:
				# Customer lookup failed, will use defaults
				frappe.log_error(f"Failed to fetch customer data for {customer}: {e}", "Customer Data Lookup")

		# If still no customer_group, use default
		if not customer_group:
			customer_group = "All Customer Groups"

		pricing_args = frappe._dict(
			{
				"doctype": invoice.get("doctype") or "Sales Invoice",
				"name": invoice.get("name") or "POS-INVOICE",
				"is_pos": 1,
				"company": profile.company,
				"transaction_date": invoice.get("posting_date") or nowdate(),
				"posting_date": invoice.get("posting_date") or nowdate(),
				"currency": invoice.get("currency") or profile.get("currency") or company_currency,
				"conversion_rate": flt(invoice.get("conversion_rate") or 1) or 1,
				"plc_conversion_rate": flt(invoice.get("plc_conversion_rate") or 1) or 1,
				"price_list": invoice.get("price_list") or profile.get("selling_price_list"),
				"customer": customer,
				"customer_group": customer_group,
				"territory": territory,
				"items": pricing_items,
			}
		)

		# Call ERPNext pricing engine - it handles all conflicts based on priority
		#
		# Why we pass pricing_args twice:
		# - 1st param (args): ERPNext extracts and pops 'items' from this, then processes each item individually
		# - 2nd param (doc): Used by 'mixed_conditions' pricing rules to access the FULL items list
		#                    for quantity accumulation across different items in the same group
		#
		# Example: A rule "Buy 2 from Demo Item Group, get 10% off" with mixed_conditions=1
		# needs to see ALL items (1 Book + 1 Camera) to know total qty=2, not just each item's qty=1
		#
		# See: erpnext/accounts/doctype/pricing_rule/utils.py -> get_qty_and_rate_for_mixed_conditions()
		pricing_results = erpnext_apply_pricing_rule(pricing_args, doc=pricing_args) or []

		if not pricing_results:
			return {"items": items}

		raw_rule_names = set()
		for result in pricing_results:
			if not result:
				continue
			rules = []
			if erpnext_get_applied_pricing_rules:
				rules = erpnext_get_applied_pricing_rules(result.get("pricing_rules"))
			else:
				raw_rules = result.get("pricing_rules") or []
				if isinstance(raw_rules, str):
					if raw_rules.startswith("["):
						rules = json.loads(raw_rules)
					else:
						rules = [r.strip() for r in raw_rules.split(",") if r.strip()]
				elif isinstance(raw_rules, list | tuple | set):
					rules = list(raw_rules)
			raw_rule_names.update(rules)

		# Build a map of applicable pricing rules from the ERPNext engine results.
		#
		# ERPNext has two types of pricing rules:
		#
		# 1. Promotional Scheme Rules (promotional_scheme is set):
		#    - Created automatically when a Promotional Scheme is saved
		#    - The scheme acts as a "template" that generates one or more Pricing Rules
		#    - Example: "Summer Sale" scheme creates "PRLE-0001", "PRLE-0002" rules
		#
		# 2. Standalone Pricing Rules (promotional_scheme is empty):
		#    - Created directly as Pricing Rule documents
		#    - Not linked to any Promotional Scheme
		#    - Example: A direct "10% off Item X" rule created in Pricing Rule doctype
		#
		# We include BOTH types for POS, but exclude coupon_code_based rules
		# (those require explicit coupon entry and are handled separately).
		#
		# Walk-in / default customer can't be tracked one-time, so one-time
		# rules never apply to anonymous sales (see the loop below).
		default_customer = profile.get("customer")
		# One-time rules are redeemed on a Sales Invoice only: never on an order (Ruling 113).
		one_time_off = (invoice.get("doctype") or DOCTYPE_SALES_INVOICE) != DOCTYPE_SALES_INVOICE

		rule_map = {}
		if raw_rule_names:
			rule_records = frappe.get_all(
				"Pricing Rule",
				filters={"name": ["in", list(raw_rule_names)]},
				fields=[
					"name",
					"promotional_scheme",
					"coupon_code_based",
					"one_time_per_customer",
					"promotional_scheme_id",
					"price_or_product_discount",
				],
			)
			for record in rule_records:
				# Skip coupon-based rules (require explicit coupon code entry)
				if record.coupon_code_based:
					continue

				# One-time-per-customer rules: skip for anonymous sales and for
				# customers who have already redeemed this rule. Dropping the rule
				# here keeps its discount out of the per-item loop below (which only
				# applies rules present in rule_map), mirroring the coupon skip above.
				if record.one_time_per_customer and (
					one_time_off or _one_time_rule_blocked(record.name, customer, default_customer)
				):
					continue

				# Include both promotional scheme rules and standalone pricing rules
				rule_map[record.name] = record

		blocked_txn_rules = set()

		# Top up rule_map with transaction-scoped rules. The per-item engine
		# never surfaces apply_on="Transaction" rules, so without this they
		# would be dropped at the `if not rule_map: return` check below.
		# ERPNext's own SQL inside apply_pricing_rule_on_transaction handles
		# date/currency/pos_only filtering, so a broad superset is sufficient.
		if erpnext_apply_pricing_rule_on_transaction:
			txn_rule_records = frappe.get_all(
				"Pricing Rule",
				filters={
					"disable": 0,
					"apply_on": "Transaction",
					"company": profile.company,
					"selling": 1,
					"coupon_code_based": 0,
				},
				fields=[
					"name",
					"promotional_scheme",
					"coupon_code_based",
					"one_time_per_customer",
					"promotional_scheme_id",
					"price_or_product_discount",
				],
			)
			for record in txn_rule_records:
				# Same one-time gate as the per-item rules above
				if record.one_time_per_customer and (
					one_time_off or _one_time_rule_blocked(record.name, customer, default_customer)
				):
					blocked_txn_rules.add(record.name)
					continue
				rule_map.setdefault(record.name, record)

		if selected_offer_names:
			# Restrict available rules to the ones explicitly selected from the UI.
			rule_map = {name: details for name, details in rule_map.items() if name in selected_offer_names}

		if not rule_map:
			return {"items": items}

		applied_rules = set()
		# Deduplicate free items using a dict keyed by (item_code, pricing_rule).
		# ERPNext's apply_pricing_rule() returns one result per cart item and for
		# mixed_conditions rules attaches the same free_item_data to every matching
		# item's result. ERPNext's own apply_pricing_rule_for_free_items() deduplicates
		# the same way: {(item_code, pricing_rules): data for data in free_item_data}.
		free_items_map = {}

		for result, item_index in zip(pricing_results, index_map, strict=False):
			if not result:
				continue

			if erpnext_get_applied_pricing_rules:
				rule_names = erpnext_get_applied_pricing_rules(result.get("pricing_rules"))
			else:
				raw_rules = result.get("pricing_rules") or []
				if isinstance(raw_rules, str):
					if raw_rules.startswith("["):
						rule_names = json.loads(raw_rules)
					else:
						rule_names = [r.strip() for r in raw_rules.split(",") if r.strip()]
				elif isinstance(raw_rules, list | tuple | set):
					rule_names = list(raw_rules)
				else:
					rule_names = []

			applicable_rule_names = [name for name in rule_names or [] if name in rule_map]

			if not applicable_rule_names:
				continue

			applied_rules.update(applicable_rule_names)

			item_doc = prepared_items[item_index]
			qty = flt(item_doc.get("qty") or item_doc.get("quantity") or 0)
			price_list_rate = flt(
				result.get("price_list_rate") or item_doc.get("price_list_rate") or item_doc.get("rate") or 0
			)

			# Get discount from result or fetch from pricing rule
			discount_percentage = flt(result.get("discount_percentage") or 0)
			per_unit_discount = flt(result.get("discount_amount") or 0)

			# If ERPNext didn't calculate discount (validate_applied_rule=1),
			# we need to fetch and apply it manually
			if not discount_percentage and not per_unit_discount and applicable_rule_names:
				for rule_name in applicable_rule_names:
					rule_doc = rule_map.get(rule_name)
					if not rule_doc:
						continue

					# Fetch full pricing rule to get discount values
					full_rule = frappe.get_cached_doc("Pricing Rule", rule_name)

					if full_rule.rate_or_discount == "Discount Percentage" and full_rule.discount_percentage:
						discount_percentage += flt(full_rule.discount_percentage)
					elif full_rule.rate_or_discount == "Discount Amount" and full_rule.discount_amount:
						per_unit_discount += flt(full_rule.discount_amount)
					elif full_rule.rate_or_discount == "Rate" and full_rule.rate:
						# Apply fixed rate
						price_list_rate = flt(full_rule.rate)

			line_discount_amount = 0
			if discount_percentage and qty and price_list_rate:
				line_discount_amount = price_list_rate * qty * discount_percentage / 100
			elif per_unit_discount and qty:
				line_discount_amount = per_unit_discount * qty
			else:
				line_discount_amount = per_unit_discount

			# Several rules' discounts are summed above; they stop at the line's value
			# (100 %), never beyond it.
			discount_percentage = min(discount_percentage, 100.0)
			if qty and price_list_rate:
				line_discount_amount = min(line_discount_amount, price_list_rate * qty)

			if not discount_percentage and line_discount_amount and qty and price_list_rate:
				base_amount = price_list_rate * qty
				if base_amount:
					discount_percentage = (line_discount_amount / base_amount) * 100

			item_doc.discount_percentage = discount_percentage
			item_doc.discount_amount = line_discount_amount
			item_doc.price_list_rate = price_list_rate
			item_doc.rate = flt(item_doc.get("rate") or price_list_rate)
			# ERPNext expects pricing_rules as comma-separated string, not a list
			item_doc.pricing_rules = ",".join(applicable_rule_names) if applicable_rule_names else ""

			item_doc.applied_promotional_schemes = list(
				{
					rule_map[name].promotional_scheme
					for name in applicable_rule_names
					if rule_map[name].promotional_scheme
				}
			)

			for free_item in result.get("free_item_data") or []:
				rule_name = free_item.get("pricing_rules")
				if not rule_name or rule_name not in rule_map:
					continue
				free_item_doc = frappe._dict(free_item)
				free_item_doc.applied_promotional_scheme = rule_map[rule_name].promotional_scheme
				free_items_map[(free_item.get("item_code"), rule_name)] = free_item_doc

		# Evaluate apply_on="Transaction" rules through ERPNext's separate
		# transaction-level engine. The per-item engine above does not see
		# them, so without this step "Entire Transaction" promotional schemes
		# (free product based on cart total) would never apply.
		txn_result = _evaluate_transaction_offers(
			invoice,
			profile,
			pricing_items,
			customer,
			customer_group,
			territory,
			invoice.get("posting_date") or nowdate(),
			pricing_args.currency,
			pricing_args.price_list,
			rule_map,
			selected_offer_names,
			blocked_rules=blocked_txn_rules,
		)
		# Per-item results win on collisions because they already carry full
		# discount metadata from the per-item engine result.
		for key, free_item_doc in txn_result.get("free_items", {}).items():
			free_items_map.setdefault(key, free_item_doc)
		applied_rules.update(txn_result.get("applied_rules", set()))

		# Surface every rule ERPNext stamped on a line so the frontend tracks it.
		if erpnext_get_applied_pricing_rules:
			for prepared_item in prepared_items:
				if not prepared_item.get("pricing_rules"):
					continue
				for pr_name in erpnext_get_applied_pricing_rules(prepared_item.get("pricing_rules")):
					if pr_name in rule_map:
						applied_rules.add(pr_name)

		return {
			"items": [dict(item) for item in prepared_items],
			# Free rows carry the item image so gifts not already in the cart show it
			"free_items": [
				dict(
					item, image=item.get("image") or frappe.get_cached_value("Item", item.item_code, "image")
				)
				for item in free_items_map.values()
			],
			"applied_pricing_rules": sorted(applied_rules),
			# Header-level (transaction-scope) discount surfaced from
			# _evaluate_transaction_offers. Frontend should apply these to the
			# invoice header (additionalDiscount + apply_discount_on) when
			# present. Both fields are zero when no transaction-level Price
			# rule fired.
			"additional_discount_percentage": flt(txn_result.get("additional_discount_percentage") or 0),
			"discount_amount": flt(txn_result.get("discount_amount") or 0),
			"apply_discount_on": txn_result.get("apply_discount_on"),
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Apply Offers Error")
		frappe.throw(_("Error applying offers: {0}").format(str(e)))
