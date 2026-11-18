# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from functools import lru_cache

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.stock.doctype.batch.batch import get_batch_no, get_batch_qty
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, getdate, nowdate, nowtime

from pos_next.utils import log_error_without_telemetry, validate_pos_profile_access

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

	The offers of the genuinely paid rows are evaluated at most once per save
	(``paid_offers``), whichever check needs them first.
	"""

	def __init__(self, invoice_doc):
		self.doc = invoice_doc
		self.item_data = _ItemData()
		self.list_prices = {}
		self._paid = None

	def load(self, rows):
		"""Item master facts and list prices (``_list_prices``) for ``rows``."""
		self.item_data.load(row.item_code for row in rows)
		missing = [row for row in rows if id(row) not in self.list_prices]
		if missing:
			self.list_prices.update(_list_prices(self.doc, missing, self.item_data))

	def paid_offers(self, paid_rows) -> tuple[dict, Exception | None]:
		"""The evaluator's answer for ``paid_rows`` (its items are in that order)."""
		key = [id(row) for row in paid_rows]
		if self._paid is None or self._paid[0] != key:
			self.load(paid_rows)
			payload = _offer_payload(self.doc, paid_rows, self.item_data, self.list_prices)
			self._paid = (key, *_evaluate_offers(self.doc, payload))
		return self._paid[1], self._paid[2]


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


def _list_prices(invoice_doc, rows, item_data) -> dict:
	"""id(row) → list price from the POS Profile's price list (else the invoice's), or None."""
	profile = invoice_doc.get("pos_profile")
	price_list = (
		profile and frappe.get_cached_value(DOCTYPE_POS_PROFILE, profile, "selling_price_list")
	) or invoice_doc.get("selling_price_list")
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


def _evaluate_offers(invoice_doc, payload) -> tuple[dict, Exception | None]:
	"""One call to the cart's evaluator; an error is logged and returned, never raised."""
	payload = json.dumps(payload, default=str)
	message_count = len(frappe.local.message_log or [])
	result, evaluator_error = {}, None
	try:
		result = _offer_evaluator()(payload) or {}
	except Exception as error:
		# Any evaluator failure means no offer backs anything; the callers decide.
		evaluator_error = error
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
	_check_free_rows(
		invoice_doc,
		remaining,
		result.get("free_items") or [],
		evaluator_error,
		item_data,
		offline_sync,
		paid_draft_free,
		sourceless,
	)


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
	"""Remove fields that are derived server-side and should not be replayed."""
	if not isinstance(payload, dict):
		return payload

	cleaned = dict(payload)
	# Packed Items are regenerated from Product Bundle definitions during save.
	# Accepting client-side packed rows can reintroduce duplicates on re-save.
	cleaned.pop("packed_items", None)
	# A client margin lets ERPNext compute a paid row down to 0 (taxes_and_totals
	# calculate_margin); the POS never sends one.
	if isinstance(cleaned.get("items"), list):
		cleaned["items"] = [
			{key: value for key, value in row.items() if key not in CLIENT_ROW_MARGIN_FIELDS}
			if isinstance(row, dict)
			else row
			for row in cleaned["items"]
		]
	return cleaned


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


def _carries_payment(doc) -> bool:
	return sum(flt(row.get("amount")) for row in doc.get("payments") or []) > 0


def _paid_draft_rates(doc) -> dict:
	"""Lowest rate per (item, UOM) on a stored draft that carries a payment, else {}."""
	if not _carries_payment(doc):
		return {}
	rates = {}
	for row in doc.get("items") or []:
		if row.get("item_code") and not cint(row.get("is_free_item")) and flt(row.qty) > 0:
			key = (row.item_code, row.get("uom"))
			rates[key] = min(rates.get(key, flt(row.rate)), flt(row.rate))
	return rates


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


def _coupon_line_rates(invoice_doc, coupon_code, paid_rows, context) -> dict[int, float]:
	"""Per-unit rate the invoice's coupon gives each paid line, on the server's list
	price with no other discount: {line index: rate}. Empty without promotions."""
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
	return {idx: flt(update["rate"]) for idx, update in (updates or {}).items() if "rate" in update}


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
		# The POS sends the percentage at 2 decimals: allow that much on the split.
		in_rate = unexplained - in_discount - list_price * 0.0001
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
	if limit > 0 and taken > limit:
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


def _check_paid_row_discounts(invoice_doc, offline_sync=False, paid_draft_rates=None) -> None:
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
	- an F&F line (``posnext_discount_source``) on a Sales Invoice with promotions:
	  promotions' F&F check is the authority, measuring on the server's list price;
	  without promotions, or on a Sales Order, the mark explains nothing;
	- a manual edit the POS Settings permit (``_manual_discount_problem``).
	Client flags (``is_rate_manually_edited``, ``original_rate``) decide nothing.
	Tolerance: one unit of the rate's precision per unit sold. A row at rate 0 is
	``_refuse_zero_rate_after_totals``'s.

	An unexplained reduction refuses the save, except on an offline sync, or for
	an item a stored paid draft already held in that UOM at a rate no higher
	(``paid_draft_rates``):
	then it is kept and logged.
	"""
	if invoice_doc.get("is_return"):
		return
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
	fnf_left_to_promotions = invoice_doc.doctype == DOCTYPE_SALES_INVOICE and _promotions_evaluates_offers()

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

	result, _error = context.paid_offers(paid_rows)
	index = {id(row): idx for idx, row in enumerate(paid_rows)}
	coupon_rates = {}
	settings = _discount_settings(invoice_doc.get("pos_profile"))
	refused, logged = [], []
	for row, list_price, tolerance in below:
		idx = index[id(row)]
		explained = [list_price, _offer_rate(result, idx, list_price)]
		code = row.get("posnext_coupon_code")
		if code:
			if code not in coupon_rates:
				coupon_rates[code] = _coupon_line_rates(invoice_doc, code, paid_rows, context)
			explained.append(coupon_rates[code].get(idx))
		unexplained = min(rate for rate in explained if rate is not None) - flt(row.rate)
		if unexplained <= tolerance:
			continue
		problem = _manual_discount_problem(row, list_price, unexplained, tolerance, settings)
		if not problem:
			continue
		held = (paid_draft_rates or {}).get((row.item_code, row.get("uom")))
		lenient = offline_sync or (held is not None and flt(row.rate) >= held - tolerance)
		(logged if lenient else refused).append(problem)
	if refused:
		_refuse("<br>".join(refused), UNEXPLAINED_DISCOUNT_LOG_TITLE)
	reference = invoice_doc.name or invoice_doc.get("offline_id") or "new"
	for problem in logged:
		log_error_without_telemetry(UNEXPLAINED_DISCOUNT_LOG_TITLE, f"Invoice {reference}: {problem}")


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


def _check_header_discount(invoice_doc, offline_sync=False, paid_draft_header=None) -> None:
	"""The invoice-level discount must be explained by the server, not the client.

	Runs after ``calculate_taxes_and_totals`` and the paid-row check, on the header
	that will be saved (``discount_amount``, worked out from any percentage). It is
	explained, the larger of the two (the cart never combines them), by:
	- the invoice's coupon: on an unpaid POS Sales Invoice with promotions,
	  promotions caps a POS Coupon's header itself, so nothing is checked here;
	  otherwise (also any paid one) pos_next's POS Coupon value (``_coupon_header_value``);
	- the transaction offers the server evaluates for the paid rows (the shared
	  ``_PricingContext`` call, no second one).
	The rest is a manual invoice discount: it needs Allow Additional Discount, and
	Max Discount Percentage Allowed (0 = no limit) caps it as a percentage of the
	total before the header it applies to (``apply_discount_on``), separately from
	the line cap. Tolerance: one unit of the currency precision.

	An unexplained header refuses the save, except on an offline sync, or when a
	stored paid draft already held a header no smaller, as an amount and as a share
	of the total before it (Ruling 90): then it is kept and logged. When the offers
	could not be evaluated, the refusal says so.
	"""
	if invoice_doc.get("is_return"):
		return
	header = flt(invoice_doc.get("discount_amount"))
	precision = cint(_currency_precision(invoice_doc.get("currency")))
	tolerance = 10**-precision
	if header <= tolerance:
		return
	code = invoice_doc.get("coupon_code")
	paid = bool(
		offline_sync
		or invoice_doc.get("offline_id")
		or paid_draft_header is not None
		or _carries_payment(invoice_doc)
	)
	if code and _coupon_header_left_to_promotions(invoice_doc, paid):
		return
	bases = _header_discount_bases(invoice_doc)
	apply_discount_on = cstr(invoice_doc.get("apply_discount_on")) or "Grand Total"
	coupon = _coupon_header_value(invoice_doc, bases) if code else 0
	offers, evaluator_error = 0, None
	if header - coupon > tolerance:
		result, evaluator_error = _pricing_context(invoice_doc).paid_offers(_paid_rows(invoice_doc))
		offers = _offer_header_value(result, bases, apply_discount_on)
	explained, source = (
		(coupon, _("coupon {0}").format(code)) if coupon >= offers else (offers, _("the offers"))
	)
	manual = header - explained
	if manual <= tolerance:
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
	held = paid_draft_header
	if offline_sync or (
		held is not None and header <= held[0] + tolerance and header <= held[1] * base + tolerance
	):
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


def _set_paid_draft_flag(invoice_doc, paid_draft_header):
	"""Flag the save as a stored paid draft keeping the header it held (Ruling 99).

	Set only when the stored draft carried a payment and a header above one currency
	unit (``paid_draft_header``, see ``_paid_draft_header``), and this save's header
	(after ``calculate_taxes_and_totals``) is no larger than it, as an amount and as a
	share of the total before it: Ruling 90 applied to the whole header. Benefit engines
	read ``flags.pos_paid_draft`` to log, not refuse, that header (Ruling 97); any other
	save gets no flag, so their online rules apply. pos_next's own coupon valuation is no
	bound here (it counts F&F lines). Always assigned, so a stale value never survives.
	"""
	invoice_doc.flags.pos_paid_draft = _keeps_held_header(invoice_doc, paid_draft_header)


def _keeps_held_header(invoice_doc, held) -> bool:
	if held is None or invoice_doc.get("is_return"):
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
	return _update_invoice(data)


def _update_invoice(data: str | dict, offline_sync: bool = False) -> dict:
	"""Create or update an invoice draft.

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
	try:
		data = _strip_server_managed_fields(data)

		pos_profile = data.get("pos_profile")
		doctype = data.get("doctype", "Sales Invoice")

		# Ensure the document type is set
		data.setdefault("doctype", doctype)

		# Normalize pricing_rules before document creation
		standardize_pricing_rules(data.get("items"))

		# Create or update invoice
		paid_draft_free, stored_sources, paid_draft_rates, paid_draft_header = {}, set(), {}, None
		if data.get("name"):
			invoice_doc = frappe.get_doc(doctype, data.get("name"))
			paid_draft_free = _paid_draft_free_qty(invoice_doc)
			stored_sources = _stored_line_sources(invoice_doc)
			paid_draft_rates = _paid_draft_rates(invoice_doc)
			paid_draft_header = _paid_draft_header(invoice_doc)
			invoice_doc.update(data)
		else:
			invoice_doc = frappe.get_doc(data)

		# Important: set before set_missing_values()/pricing/validation paths that may
		# read linked docs (e.g., Customer) and trigger controller permission checks.
		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		# Offline-queued sale being synced (see _apply_pos_sales_team)
		invoice_doc.flags.pos_offline_sync = bool(data.get("offline_id"))
		_set_payment_collected_flag(invoice_doc, data.get("payments"))

		pos_profile_doc = None
		if pos_profile:
			try:
				pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
			except Exception:
				frappe.throw(_("Unable to load POS Profile {0}").format(pos_profile))

			invoice_doc.pos_profile = pos_profile

			if pos_profile_doc:
				if pos_profile_doc.company and not invoice_doc.get("company"):
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
				[FIELD_ALLOW_NEGATIVE_STOCK],
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

		# ========================================================================
		# DISCOUNT CALCULATION - CRITICAL LOGIC
		# ========================================================================
		# Frontend sends: rate (discounted), price_list_rate (original), discount_percentage
		# Priority: Trust frontend's price_list_rate if provided (avoids rounding errors)
		# Fallback: Reverse-calculate price_list_rate from rate and discount_percentage
		#
		# Formula: rate = price_list_rate * (1 - discount_percentage/100)
		# Reverse: price_list_rate = rate / (1 - discount_percentage/100)
		# ========================================================================
		for item in invoice_doc.get("items", []):
			item_rate = flt(item.rate or 0)
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

			# POS Next computes offers itself (via apply_offers) and sends each
			# item with discount_percentage / discount_amount / rate already set.
			# We pair that with invoice_doc.ignore_pricing_rule = 1 so ERPNext's
			# own pricing engine stays out of the way.
			#
			# However, ERPNext's get_pricing_rule_for_item() has a branch that
			# fires when ignore_pricing_rule=1 AND the doc already exists in DB
			# AND item.pricing_rules is non-empty — it interprets that as the
			# user disabling pricing rules on an invoice that previously had
			# them, calls remove_pricing_rule_for_item(), and silently zeroes
			# discount_percentage / discount_amount / rate on the next save.
			# That branch fires on the 2nd save (submit step), producing
			# "Partly Paid" invoices where the cashier collected the discounted
			# amount but the saved grand_total reverted to the pre-discount
			# price. See erpnext/accounts/doctype/pricing_rule/pricing_rule.py
			# around line 421.
			#
			# Clearing item.pricing_rules (_reset_row_pricing_rules, after this
			# loop; submit_invoice does the same for an existing draft) avoids
			# that branch entirely. The discount itself is preserved via the
			# discount_percentage / discount_amount fields we already set above.

		# Free rows only from offers (a zero-rate row is a free row).
		_check_free_rows_backed(
			invoice_doc,
			offline_sync=offline_sync,
			paid_draft_free=paid_draft_free,
			stored_sources=stored_sources,
		)
		applied_rule_names_seen = _reset_row_pricing_rules(invoice_doc.get("items", []))

		if doctype == "Sales Invoice":
			one_time_applied = (
				frappe.get_all(
					"Pricing Rule",
					filters={
						"name": ["in", list(applied_rule_names_seen)],
						"one_time_per_customer": 1,
					},
					pluck="name",
				)
				if applied_rule_names_seen
				else []
			)
			invoice_doc.pos_applied_one_time_rules = (
				json.dumps(sorted(one_time_applied)) if one_time_applied else ""
			)

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

		# Calculate totals and apply discounts (with rounding disabled)
		invoice_doc.calculate_taxes_and_totals()
		# Judge the rates ERPNext computed: no paid row may come out at 0, and
		# none below list price without a reason the server confirms.
		_refuse_zero_rate_after_totals(invoice_doc, lenient=offline_sync)
		_check_paid_row_discounts(invoice_doc, offline_sync=offline_sync, paid_draft_rates=paid_draft_rates)
		_check_header_discount(invoice_doc, offline_sync=offline_sync, paid_draft_header=paid_draft_header)
		# After totals: the flag compares this save's header with the one the draft held.
		_set_paid_draft_flag(invoice_doc, paid_draft_header)

		# Validate return rows after the totals, so the rates checked are the
		# rates that will be saved
		if invoice_doc.get("is_return"):
			_validate_return_rows(invoice_doc)
		elif doctype == "Sales Invoice":
			# Header discounts come from transaction-level rules; record the
			# one-time ones with the per-item ones stamped above.
			txn_one_time = _applied_one_time_transaction_rules(
				invoice_doc, pos_profile_doc.customer if pos_profile_doc else None
			)
			if txn_one_time:
				stamped = json.loads(invoice_doc.pos_applied_one_time_rules or "[]")
				invoice_doc.pos_applied_one_time_rules = json.dumps(sorted(set(stamped) | set(txn_one_time)))
		if invoice_doc.grand_total is None:
			invoice_doc.grand_total = 0.0
		if invoice_doc.base_grand_total is None:
			invoice_doc.base_grand_total = 0.0

		# Set accounts for payment methods before saving
		_set_payment_accounts(invoice_doc.payments, invoice_doc.company)

		# For return invoices, ensure payments are negative
		if invoice_doc.get("is_return"):
			# Return handling is primarily for Sales Invoice
			if doctype == "Sales Invoice" and invoice_doc.get("payments"):
				for payment in invoice_doc.payments:
					payment.amount = -abs(payment.amount)
					if payment.base_amount:
						payment.base_amount = -abs(payment.base_amount)

				invoice_doc.paid_amount = flt(sum(p.amount for p in invoice_doc.payments))
				invoice_doc.base_paid_amount = flt(sum(p.base_amount or 0 for p in invoice_doc.payments))

		# Validate and track POS Coupon if coupon_code is provided
		coupon_code = data.get("coupon_code")
		if coupon_code:
			# Validate POS Coupon exists and is valid
			if frappe.db.table_exists("POS Coupon"):
				from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
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
						# check_coupon_code returns its msg already translated
						frappe.throw((coupon_result or {}).get("msg") or _("Invalid coupon code"))
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

		return invoice_doc.as_dict()
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
	sync_doc = frappe.get_doc("Offline Invoice Sync", sync_record_name)
	sync_doc.status = "Pending"
	sync_doc.synced_at = None
	sync_doc.flags.ignore_permissions = True
	sync_doc.save()
	return {"already_synced": False, "sync_record_name": sync_record_name}


def _ensure_offline_uniqueness(offline_id, pos_profile=None, customer=None):
	"""
	Ensure offline invoice uniqueness with race condition protection.

	Uses a reservation pattern:
	1. Check if a sync record exists (with row-level lock)
	2. If synced with valid invoice, return existing invoice
	3. If synced but invoice deleted/invalid, allow retry
	4. If pending but expired (>5 min), allow retry
	5. If pending and active, reject (another request processing)
	6. If failed, allow retry
	7. If not exists, create pending reservation

	Args:
	    offline_id: The unique offline ID from the client
	    pos_profile: POS Profile name
	    customer: Customer name

	Returns:
	    dict with:
	    - already_synced (bool): True if invoice was already synced
	    - invoice_data (dict): Existing invoice data if already_synced
	    - sync_record_name (str): Name of the sync record for this attempt
	"""
	# Acquire row-level lock to prevent race conditions
	existing_sync = frappe.db.get_value(
		"Offline Invoice Sync",
		{"offline_id": offline_id},
		["name", "sales_invoice", "status", "modified", "pos_profile"],
		as_dict=True,
		for_update=True,
	)

	if existing_sync and existing_sync.pos_profile and existing_sync.pos_profile != pos_profile:
		# An offline_id reserved by another profile: never reuse it or return its invoice.
		frappe.throw(_("This offline invoice belongs to another POS Profile."), frappe.PermissionError)

	if existing_sync:
		sync_status = existing_sync.get("status")
		sync_record_name = existing_sync.name

		# Handle Pending status
		if sync_status == "Pending":
			if _is_pending_expired(existing_sync.get("modified")):
				# Expired pending - allow retry
				return _reuse_sync_record(sync_record_name)
			else:
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
			if frappe.db.exists("Sales Invoice", existing_sync.sales_invoice):
				existing_invoice = frappe.get_doc("Sales Invoice", existing_sync.sales_invoice)
				if existing_invoice.docstatus == 1:
					return {
						"already_synced": True,
						"invoice_data": {
							"name": existing_invoice.name,
							"status": existing_invoice.docstatus,
							"grand_total": existing_invoice.grand_total,
							"total": existing_invoice.total,
							"net_total": existing_invoice.net_total,
							"outstanding_amount": getattr(existing_invoice, "outstanding_amount", 0),
							"paid_amount": getattr(existing_invoice, "paid_amount", 0),
							"change_amount": getattr(existing_invoice, "change_amount", 0),
							"duplicate_prevented": True,
							"offline_id": offline_id,
						},
					}

			# Synced record points to deleted/invalid invoice - allow retry
			return _reuse_sync_record(sync_record_name)

		# Unknown status or synced without invoice - allow retry
		return _reuse_sync_record(sync_record_name)

	# No existing record - create pending reservation
	try:
		pending_sync = frappe.get_doc(
			{
				"doctype": "Offline Invoice Sync",
				"offline_id": offline_id,
				"sales_invoice": "",
				"pos_profile": pos_profile,
				"customer": customer,
				"status": "Pending",
			}
		)
		pending_sync.flags.ignore_permissions = True
		pending_sync.insert()

		return {"already_synced": False, "sync_record_name": pending_sync.name}
	except frappe.DuplicateEntryError:
		# Race condition: another request just created the record
		# Retry the check to get the new record
		return _ensure_offline_uniqueness(offline_id, pos_profile, customer)


def _complete_offline_sync(sync_record_name, invoice_name):
	"""
	Mark an offline sync record as completed after successful invoice submission.

	Args:
	    sync_record_name: Name of the Offline Invoice Sync record
	    invoice_name: Name of the submitted Sales Invoice
	"""
	if not sync_record_name:
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
		sync_doc.save()
	except Exception as error:
		frappe.log_error(
			title="Offline Sync Cleanup Error",
			message=f"Failed to mark sync record {sync_record_name} as failed: {error!s}",
		)


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
	from pos_next.pos_next.doctype.offline_invoice_sync.offline_invoice_sync import (
		OfflineInvoiceSync,
	)

	result = OfflineInvoiceSync.is_synced(offline_id)

	# Defensive check - ensure result is a dict
	if not result or not isinstance(result, dict):
		return {"synced": False, "sales_invoice": None}

	# Additionally verify the sales invoice still exists and is submitted
	if result.get("synced") and result.get("sales_invoice"):
		if frappe.db.exists("Sales Invoice", result["sales_invoice"]):
			docstatus = frappe.db.get_value("Sales Invoice", result["sales_invoice"], "docstatus")
			if docstatus == 1:  # Submitted
				return result

		# Invoice was deleted or not submitted, clear the sync record
		return {"synced": False, "sales_invoice": None}

	return result


@frappe.whitelist()
def submit_invoice(invoice: str | dict | None = None, data: str | dict | None = None) -> dict:
	"""Submit the invoice (Step 2)."""
	# Handle different calling conventions
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

	invoice = _strip_server_managed_fields(invoice)
	# Before the offline dedup: a refused call must neither reserve an offline_id
	# nor read another profile's synced invoice.
	_validate_invoice_profile(invoice)

	pos_profile = invoice.get("pos_profile")
	doctype = invoice.get("doctype", "Sales Invoice")

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
	sync_record_name = None

	if offline_id:
		dedup_result = _ensure_offline_uniqueness(
			offline_id=offline_id, pos_profile=pos_profile, customer=invoice.get("customer")
		)

		if dedup_result and dedup_result.get("already_synced"):
			# Invoice was already synced - return the existing invoice details
			return dedup_result.get("invoice_data", {})

		# Store the sync record name for later update
		sync_record_name = dedup_result.get("sync_record_name") if dedup_result else None
	# An offline sale reserved for sync here (new, or a retry with no completed
	# invoice) makes the free-row check log-only (Ruling 68).
	offline_sync = bool(offline_id and sync_record_name)

	# Track whether invoice was successfully submitted
	invoice_submitted = False

	try:
		invoice_name = invoice.get("name")
		paid_draft_header = None  # set below when a stored paid draft is re-saved

		# Get or create invoice
		if not invoice_name or not frappe.db.exists(doctype, invoice_name):
			created = _update_invoice(json.dumps(invoice), offline_sync=offline_sync)
			if not created or not isinstance(created, dict):
				frappe.throw(_("Failed to create invoice draft"))
			invoice_name = created.get("name")
			if not invoice_name:
				frappe.throw(_("Failed to get invoice name from draft"))
			invoice_doc = frappe.get_doc(doctype, invoice_name)
		else:
			invoice_doc = frappe.get_doc(doctype, invoice_name)
			existing_customer = invoice_doc.customer
			paid_draft_free = _paid_draft_free_qty(invoice_doc)
			stored_sources = _stored_line_sources(invoice_doc)
			paid_draft_rates = _paid_draft_rates(invoice_doc)
			paid_draft_header = _paid_draft_header(invoice_doc)
			invoice_doc.update(invoice)
			if not invoice_doc.get("customer") and existing_customer:
				invoice_doc.customer = existing_customer
			_check_free_rows_backed(
				invoice_doc,
				offline_sync=offline_sync,
				paid_draft_free=paid_draft_free,
				stored_sources=stored_sources,
			)
			_reset_row_pricing_rules(invoice_doc.get("items", []))
			if not invoice_doc.get("is_return"):
				# Judge the rates this save will store, as update_invoice does.
				invoice_doc.calculate_taxes_and_totals()
				_refuse_zero_rate_after_totals(invoice_doc, lenient=offline_sync)
				_check_paid_row_discounts(
					invoice_doc, offline_sync=offline_sync, paid_draft_rates=paid_draft_rates
				)
				_check_header_discount(
					invoice_doc, offline_sync=offline_sync, paid_draft_header=paid_draft_header
				)
			# The draft was validated by update_invoice, but its rows and header
			# discount may have been replaced by this payload, so redo both.
			# Validating before totals is safe here: it checks only row links,
			# quantities and rates, and recalculating totals does not change rates.
			if invoice_doc.get("is_return"):
				_apply_return_header_discount(invoice_doc)
				_validate_return_rows(invoice_doc)

		# Keep permission bypass consistent for POS API flow.
		invoice_doc.flags.ignore_permissions = True
		frappe.flags.ignore_account_permission = True
		# Offline-queued sale being synced (see _apply_pos_sales_team)
		invoice_doc.flags.pos_offline_sync = bool(offline_id)
		# Set again here: the draft made by update_invoice above is re-fetched.
		_set_payment_collected_flag(invoice_doc, invoice.get("payments"))
		_set_paid_draft_flag(invoice_doc, paid_draft_header)

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
						return_invoice=invoice_doc.name, amount=abs(flt(invoice_doc.grand_total))
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

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Submit Invoice Error")
		raise

	finally:
		# Cleanup sync record if invoice was not successfully submitted
		if sync_record_name and not invoice_submitted:
			_cleanup_failed_sync(sync_record_name)


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
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	limit = cint(limit) or 100
	start = cint(start) or 0

	# Permission check
	has_access = frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": frappe.session.user})
	if not has_access and not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("You don't have access to this POS Profile"))

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
	filters = {
		"docstatus": 0,
	}

	# Add pos_opening_shift filter if the field exists
	if frappe.db.has_column(doctype, "pos_opening_shift"):
		filters["pos_opening_shift"] = pos_opening_shift

	# Performance: Get all invoice names first
	invoices_list = frappe.get_list(
		doctype,
		filters=filters,
		fields=["name"],
		limit_page_length=0,
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
	doctype = "Sales Invoice"

	if not frappe.db.exists(doctype, invoice):
		frappe.throw(_("Invoice {0} does not exist").format(invoice))

	# Check if it's a draft
	if frappe.db.get_value(doctype, invoice, "docstatus") != 0:
		frappe.throw(_("Cannot delete submitted invoice {0}").format(invoice))

	frappe.delete_doc(doctype, invoice, force=1)
	return _("Invoice {0} Deleted").format(invoice)


@frappe.whitelist()
def cleanup_old_drafts(pos_profile=None, max_age_hours=48):
	"""
	Clean up old draft invoices to prevent stock reservation issues.
	Deletes drafts older than max_age_hours (default 24 hours).
	"""
	from datetime import datetime, timedelta

	doctype = "Sales Invoice"
	cutoff_time = datetime.now() - timedelta(hours=int(max_age_hours))

	filters = {
		"docstatus": 0,  # Draft only
		"is_pos": 1,  # Only POS Sales Invoices
		"modified": ["<", cutoff_time.strftime("%Y-%m-%d %H:%M:%S")],
	}

	# Optionally filter by POS profile
	if pos_profile:
		filters["pos_profile"] = pos_profile

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
	from frappe.utils import add_days, today

	# Check return validity days from POS Settings
	return_validity_days = 0
	if pos_profile:
		return_validity_days = cint(
			frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "return_validity_days") or 0
		)

	si = frappe.qb.DocType("Sales Invoice")

	# Over-fetch to compensate for fully-returned invoices removed in step 2
	fetch_limit = cint(limit) * 2

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
	return _filter_fully_returned(candidates)[: cint(limit)]


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


def _build_item_tax_map(taxes: list) -> dict:
	"""Build item_code -> tax_amount map from taxes child table.

	Args:
	    taxes: List of tax row dicts containing item_wise_tax_detail

	Returns:
	    Dict mapping item_code to total tax amount (absolute value)

	Note:
	    item_wise_tax_detail format: {"ITEM-CODE": [tax_rate, tax_amount]}
	    Return documents have negative amounts, hence abs() is used.
	"""
	from collections import defaultdict

	tax_map = defaultdict(float)

	for tax_row in taxes:
		try:
			details = _parse_item_wise_tax_detail(tax_row.get("item_wise_tax_detail"))
			for item_code, (_, tax_amount) in details.items():
				tax_map[item_code] += abs(flt(tax_amount))
		except (json.JSONDecodeError, TypeError, ValueError, KeyError):
			continue

	return dict(tax_map)


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
		"grand_total": invoice_info.grand_total,
		"paid_amount": invoice_info.paid_amount,
		"outstanding_amount": invoice_info.outstanding_amount,
		"customer": invoice_info.customer,
		"customer_name": invoice_info.customer_name,
		"posting_date": invoice_info.posting_date,
		"payments": payments_data,
		"net_total": invoice_info.net_total,
		"total_taxes_and_charges": invoice_info.total_taxes_and_charges,
	}

	item_tax_map = _build_item_tax_map(return_dict.get("taxes", []))

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
		tax_per_unit = (
			flt(item_tax_map.get(item.get("item_code"), 0) / original_qty, precision) if original_qty else 0
		)

		# For inclusive taxes, use the original rate (already includes tax) to prevent
		# ERPNext from back-calculating and double-reducing the tax.
		# With a header discount, also use the original rate: the server applies
		# the discount to the return (net_rate already has it, so it would count twice).
		# Otherwise (exclusive taxes) use net_rate as before.
		if tax_inclusive or discount_plan:
			item_rate = flt(item.get("rate"), precision)
			rate_with_tax = item_rate if tax_inclusive else flt(net_rate + tax_per_unit, precision)
			# Both price_list_rate and rate are tax-inclusive, so discount is their difference
			discount_per_unit = flt(price_list_rate - item_rate, precision)
		else:
			item_rate = net_rate
			rate_with_tax = flt(net_rate + tax_per_unit, precision)
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
	from frappe.query_builder.functions import Abs, Count, Sum

	page = cint(page) or 1
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

		if not invoice.get("pos_profile") or not erpnext_apply_pricing_rule:
			# Either no POS profile supplied or ERPNext promotional engine unavailable
			return {"items": items}

		profile = frappe.get_cached_doc("POS Profile", invoice.get("pos_profile"))

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
				if record.one_time_per_customer and _one_time_rule_blocked(
					record.name, customer, default_customer
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
				if record.one_time_per_customer and _one_time_rule_blocked(
					record.name, customer, default_customer
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
