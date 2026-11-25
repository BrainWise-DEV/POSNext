# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Server-side pricing and discount verification for POS Next invoices.

Prevents client-side price manipulation (MW.WA.03) by resolving authoritative
catalog prices from ERPNext's ``Item Price`` / ``Item`` records (or the original
submitted invoice for returns) and validating all line-level and invoice-level
discounts against POS Settings, active Pricing Rules, and POS Coupons.

Offline sync tolerance:
    When ``is_offline_sync=True``, prices may have changed on the server while
    the POS terminal was offline. A bounded relative tolerance (default 15%,
    configurable via ``pos_next_offline_price_tolerance_pct`` in site config)
    allows legitimate queued offline sales to sync while still rejecting
    abusive price tampering.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

DEFAULT_OFFLINE_PRICE_TOLERANCE_PCT = 15.0
PRICE_ROUNDING_EPSILON = 0.02


def get_offline_price_tolerance_pct() -> float:
	"""Return the allowed percentage drift for offline-synced invoice rates."""
	try:
		configured = frappe.conf.get("pos_next_offline_price_tolerance_pct")
	except Exception:
		configured = None
	if configured is None:
		return DEFAULT_OFFLINE_PRICE_TOLERANCE_PCT
	return max(0.0, min(flt(configured), 100.0))


def _parse_pricing_rule_names(raw_rules) -> list[str]:
	"""Extract a list of Pricing Rule names from JSON, list, or CSV."""
	if not raw_rules:
		return []
	if isinstance(raw_rules, (list, tuple, set)):
		return [str(r).strip() for r in raw_rules if str(r).strip()]
	if isinstance(raw_rules, str):
		text = raw_rules.strip()
		if not text:
			return []
		if text.startswith("["):
			try:
				parsed = json.loads(text)
				if isinstance(parsed, list):
					return [str(r).strip() for r in parsed if str(r).strip()]
			except (ValueError, TypeError):
				pass
		return [r.strip() for r in text.split(",") if r.strip()]
	return []


def _resolve_uom_conversion_factor(item_code: str, uom: str | None, stock_uom: str | None) -> float:
	"""Resolve authoritative UOM conversion factor from DB (never trust client factor)."""
	if not uom or not stock_uom or uom == stock_uom:
		return 1.0
	factor = frappe.db.get_value(
		"UOM Conversion Detail",
		{"parent": item_code, "uom": uom},
		"conversion_factor",
	)
	return flt(factor) if flt(factor) > 0 else 1.0


def resolve_server_item_price(
	item_code: str,
	price_list: str | None,
	uom: str | None = None,
	customer: str | None = None,
	posting_date: str | None = None,
) -> float | None:
	"""Resolve the authoritative selling price_list_rate for an item from the DB.

	Returns:
		Authoritative positive rate, or None if no catalog price is configured.
	"""
	if not item_code:
		return None

	item_meta = frappe.db.get_value(
		"Item",
		item_code,
		["stock_uom", "standard_rate"],
		as_dict=True,
	)
	stock_uom = item_meta.stock_uom if item_meta else None
	effective_uom = uom or stock_uom
	conversion_factor = _resolve_uom_conversion_factor(item_code, effective_uom, stock_uom)

	if price_list:
		ref_date = getdate(posting_date or nowdate())
		rows = frappe.get_all(
			"Item Price",
			filters={
				"item_code": item_code,
				"price_list": price_list,
				"selling": 1,
			},
			fields=["price_list_rate", "uom", "customer", "valid_from", "valid_upto"],
			order_by="modified desc",
		)

		valid_rows = []
		for row in rows:
			if row.get("valid_from") and getdate(row.valid_from) > ref_date:
				continue
			if row.get("valid_upto") and getdate(row.valid_upto) < ref_date:
				continue
			valid_rows.append(row)

		# Priority: (customer + exact uom), (customer + base uom), (general + exact uom), (general + base uom)
		def _pick(match_customer: bool, match_exact_uom: bool):
			for r in valid_rows:
				row_cust = r.get("customer") or ""
				if match_customer and (not customer or row_cust != customer):
					continue
				if not match_customer and row_cust:
					continue
				row_uom = r.get("uom") or ""
				if match_exact_uom:
					if effective_uom and row_uom == effective_uom:
						return flt(r.price_list_rate)
				else:
					if not row_uom or (stock_uom and row_uom == stock_uom):
						return flt(r.price_list_rate) * conversion_factor
			return None

		for match_cust in (True, False):
			for exact_uom in (True, False):
				rate = _pick(match_cust, exact_uom)
				if rate is not None and rate > 0:
					return rate

	if item_meta and flt(item_meta.standard_rate) > 0:
		return flt(item_meta.standard_rate) * conversion_factor

	return None


def _is_valid_free_item_rule(
	item_code: str,
	rule_names: list[str],
	company: str | None,
	posting_date: str | None,
	is_offline_sync: bool = False,
) -> bool:
	"""Verify that a free item is backed by an active Product Pricing Rule."""
	ref_date = getdate(posting_date or nowdate())

	filters = {
		"selling": 1,
		"price_or_product_discount": "Product",
	}
	if not is_offline_sync:
		filters["disable"] = 0
	if rule_names:
		filters["name"] = ["in", rule_names]

	rules = frappe.get_all(
		"Pricing Rule",
		filters=filters,
		fields=[
			"name",
			"company",
			"valid_from",
			"valid_upto",
			"free_item",
			"same_item",
			"disable",
		],
	)

	for rule in rules:
		if company and rule.get("company") and rule.company != company:
			continue
		if not is_offline_sync:
			if rule.get("valid_from") and getdate(rule.valid_from) > ref_date:
				continue
			if rule.get("valid_upto") and getdate(rule.valid_upto) < ref_date:
				continue
		if rule.get("same_item") or not rule.get("free_item") or rule.get("free_item") == item_code:
			return True

	# If rule_names were cleared or not attached, check if any active Product rule targets this free_item directly
	if rule_names:
		direct = frappe.get_all(
			"Pricing Rule",
			filters={
				"selling": 1,
				"price_or_product_discount": "Product",
				"free_item": item_code,
				**({} if is_offline_sync else {"disable": 0}),
			},
			fields=["name", "company", "valid_from", "valid_upto"],
		)
		for rule in direct:
			if company and rule.get("company") and rule.company != company:
				continue
			if not is_offline_sync:
				if rule.get("valid_from") and getdate(rule.valid_from) > ref_date:
					continue
				if rule.get("valid_upto") and getdate(rule.valid_upto) < ref_date:
					continue
			return True

	return False


def _max_pricing_rule_discount_amount(
	server_price_list_rate: float,
	rule_names: list[str],
	company: str | None,
	posting_date: str | None,
) -> float:
	"""Compute the maximum valid line-level discount amount from active referenced Pricing Rules."""
	if not rule_names or server_price_list_rate <= 0:
		return 0.0

	ref_date = getdate(posting_date or nowdate())
	rules = frappe.get_all(
		"Pricing Rule",
		filters={
			"name": ["in", rule_names],
			"selling": 1,
			"disable": 0,
		},
		fields=[
			"name",
			"company",
			"valid_from",
			"valid_upto",
			"price_or_product_discount",
			"rate_or_discount",
			"discount_percentage",
			"discount_amount",
			"rate",
		],
	)

	total_discount = 0.0
	for rule in rules:
		if company and rule.get("company") and rule.company != company:
			continue
		if rule.get("valid_from") and getdate(rule.valid_from) > ref_date:
			continue
		if rule.get("valid_upto") and getdate(rule.valid_upto) < ref_date:
			continue
		if rule.get("price_or_product_discount") != "Price":
			continue

		kind = rule.get("rate_or_discount")
		if kind == "Discount Percentage":
			pct = max(0.0, min(flt(rule.get("discount_percentage")), 100.0))
			total_discount += server_price_list_rate * (pct / 100.0)
		elif kind == "Discount Amount":
			total_discount += max(0.0, flt(rule.get("discount_amount")))
		elif kind == "Rate":
			rule_rate = flt(rule.get("rate"))
			if 0 <= rule_rate < server_price_list_rate:
				total_discount += server_price_list_rate - rule_rate

	return min(total_discount, server_price_list_rate)


def _max_coupon_discount_amount(
	server_price_list_rate: float,
	coupon_code: str | None,
	customer: str | None,
	company: str | None,
) -> float:
	"""Return the maximum discount a valid POS Coupon can grant on a line."""
	if not coupon_code or server_price_list_rate <= 0:
		return 0.0
	if not frappe.db.table_exists("POS Coupon"):
		return 0.0

	try:
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import check_coupon_code

		res = check_coupon_code(coupon_code, customer=customer, company=company)
		if not res or not res.get("valid"):
			return 0.0
	except Exception:
		return 0.0

	coupon = frappe.db.get_value(
		"POS Coupon",
		{"coupon_code": coupon_code},
		["discount_type", "discount_percentage", "discount_amount"],
		as_dict=True,
	)
	if not coupon:
		return 0.0

	if coupon.get("discount_type") == "Percentage" or flt(coupon.get("discount_percentage")) > 0:
		pct = max(0.0, min(flt(coupon.get("discount_percentage")), 100.0))
		return server_price_list_rate * (pct / 100.0)
	return min(max(0.0, flt(coupon.get("discount_amount"))), server_price_list_rate)


def _has_active_friends_and_family_discount(pos_profile: str | None, customer: str | None) -> float:
	"""Return active Friends & Family discount percentage if a benefit provider is installed and eligible."""
	if not pos_profile or not customer:
		return 0.0
	try:
		if "posnext_promotions" not in frappe.get_installed_apps():
			return 0.0
		check_fn = frappe.get_attr(
			"posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility"
		)
		res = check_fn(customer=customer, pos_profile=pos_profile)
		if isinstance(res, dict) and res.get("eligible"):
			return max(0.0, min(flt(res.get("discount_percentage")), 100.0))
	except Exception:
		return 0.0
	return 0.0


def _enforce_return_pricing(invoice_doc) -> None:
	"""Verify return invoice item rates do not exceed the original invoice's line rates."""
	return_against = invoice_doc.get("return_against")
	if not return_against:
		return

	orig_rows = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": return_against},
		fields=["name", "item_code", "rate", "price_list_rate", "net_rate"],
	)
	if not orig_rows:
		return

	by_row_name = {r.name: r for r in orig_rows}
	by_item_code = {}
	for r in orig_rows:
		# If an item appears multiple times, allow up to the highest original rate for that item_code
		prev = by_item_code.get(r.item_code)
		if prev is None or flt(r.rate) > flt(prev.rate):
			by_item_code[r.item_code] = r

	for item in invoice_doc.get("items", []):
		row_ref = item.get("sales_invoice_item")
		orig = by_row_name.get(row_ref) if row_ref else by_item_code.get(item.item_code)
		if not orig:
			continue

		max_refund_rate = max(flt(orig.rate), flt(orig.net_rate))
		claimed_rate = abs(flt(item.rate))
		if claimed_rate > max_refund_rate + PRICE_ROUNDING_EPSILON:
			frappe.throw(
				_("Return rate for item {0} ({1}) exceeds original invoice rate ({2})").format(
					item.item_code, claimed_rate, max_refund_rate
				),
				frappe.ValidationError,
			)
		if flt(orig.price_list_rate) > 0:
			item.price_list_rate = flt(orig.price_list_rate)


def _draft_pricing_matches_db(existing_doc, incoming_payload: dict) -> bool:
	"""Return True if ``incoming_payload`` makes no pricing/item/discount changes to ``existing_doc``."""
	if not existing_doc or not isinstance(incoming_payload, dict):
		return False

	for field in ("discount_amount", "additional_discount_percentage", "selling_price_list"):
		if field in incoming_payload:
			if abs(flt(incoming_payload.get(field)) - flt(existing_doc.get(field))) > PRICE_ROUNDING_EPSILON:
				if field == "selling_price_list":
					if (incoming_payload.get(field) or "") != (existing_doc.get(field) or ""):
						return False
				else:
					return False

	if "items" not in incoming_payload or incoming_payload["items"] is None:
		return True

	incoming_items = incoming_payload.get("items") or []
	existing_items = existing_doc.get("items") or []
	if len(incoming_items) != len(existing_items):
		return False

	for inc, cur in zip(incoming_items, existing_items):
		if (inc.get("item_code") or "") != (cur.get("item_code") or ""):
			return False
		if (inc.get("uom") or cur.get("uom") or "") != (cur.get("uom") or ""):
			return False
		if abs(flt(inc.get("qty")) - flt(cur.get("qty"))) > 0.0001:
			return False
		if abs(flt(inc.get("rate")) - flt(cur.get("rate"))) > PRICE_ROUNDING_EPSILON:
			return False
		if cint(inc.get("is_free_item") or 0) != cint(cur.get("is_free_item") or 0):
			return False

	return True


def enforce_server_side_pricing(
	invoice_doc,
	pos_profile: str | None,
	pos_profile_doc=None,
	pos_settings_cache: dict | None = None,
	is_offline_sync: bool = False,
	validate_manual_rate_edit_fn=None,
) -> None:
	"""Validate and enforce server-side prices and discounts on ``invoice_doc``.

	- Resolves authoritative ``price_list_rate`` from DB (or original invoice on returns).
	- Rejects forged free items and unauthorized line/invoice discounts.
	- Allows bounded price drift for offline-synced invoices (``is_offline_sync=True``).
	"""
	if cint(invoice_doc.get("is_return")):
		_enforce_return_pricing(invoice_doc)
		return

	if not pos_profile_doc and pos_profile:
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

	# Pin selling_price_list to POS Profile's authoritative price list when configured
	if pos_profile_doc and pos_profile_doc.get("selling_price_list"):
		invoice_doc.selling_price_list = pos_profile_doc.selling_price_list

	price_list = invoice_doc.get("selling_price_list")
	company = invoice_doc.get("company") or (pos_profile_doc.company if pos_profile_doc else None)
	customer = invoice_doc.get("customer")
	posting_date = invoice_doc.get("posting_date") or nowdate()

	# Fetch POS Settings discount permissions
	pos_settings = dict(pos_settings_cache or {})
	if pos_profile and "allow_user_to_edit_item_discount" not in pos_settings:
		extra = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": pos_profile},
			[
				"allow_user_to_edit_rate",
				"allow_user_to_edit_item_discount",
				"allow_user_to_edit_additional_discount",
				"max_discount_allowed",
			],
			as_dict=True,
		)
		if extra:
			pos_settings.update(extra)

	allow_item_discount = cint(pos_settings.get("allow_user_to_edit_item_discount", 1))
	allow_additional_discount = cint(pos_settings.get("allow_user_to_edit_additional_discount", 0))
	max_discount_allowed = flt(pos_settings.get("max_discount_allowed") or 0)
	offline_tolerance_pct = get_offline_price_tolerance_pct() if is_offline_sync else 0.0
	fnf_discount_pct = _has_active_friends_and_family_discount(pos_profile, customer)
	invoice_coupon = invoice_doc.get("coupon_code")

	for item in invoice_doc.get("items", []):
		if flt(item.get("qty")) <= 0:
			frappe.throw(
				_("Quantity for item {0} must be greater than zero").format(item.get("item_code")),
				frappe.ValidationError,
			)

		rule_names = _parse_pricing_rule_names(item.get("pricing_rules"))

		if cint(item.get("is_free_item")):
			if not _is_valid_free_item_rule(
				item.item_code,
				rule_names,
				company=company,
				posting_date=posting_date,
				is_offline_sync=is_offline_sync,
			):
				frappe.throw(
					_("Free item {0} is not backed by an active promotional offer").format(item.item_code),
					frappe.ValidationError,
				)
			item.price_list_rate = 0
			item.rate = 0
			item.discount_percentage = 0
			item.discount_amount = 0
			continue

		server_price = resolve_server_item_price(
			item_code=item.item_code,
			price_list=price_list,
			uom=item.get("uom"),
			customer=customer,
			posting_date=posting_date,
		)

		client_rate = flt(item.get("rate") or 0)
		if client_rate < 0:
			frappe.throw(
				_("Rate for item {0} cannot be negative").format(item.item_code),
				frappe.ValidationError,
			)

		is_manual_edit = cint(item.get("is_rate_manually_edited") or 0)

		if server_price is not None and server_price > 0:
			item.price_list_rate = server_price

			if is_manual_edit:
				# Authoritative original_rate must come from server catalog price, not client
				item.original_rate = server_price
				if validate_manual_rate_edit_fn:
					validation = validate_manual_rate_edit_fn(item, pos_profile, pos_settings)
					if not validation.get("valid"):
						frappe.throw(validation.get("message"), frappe.ValidationError)
				continue

			# If client rate is below authoritative price_list_rate, verify discount authorization
			if client_rate < server_price - PRICE_ROUNDING_EPSILON:
				promo_discount = _max_pricing_rule_discount_amount(
					server_price, rule_names, company=company, posting_date=posting_date
				)
				line_coupon = item.get("posnext_coupon_code") or invoice_coupon
				coupon_discount = _max_coupon_discount_amount(
					server_price, line_coupon, customer=customer, company=company
				)
				fnf_discount = server_price * (fnf_discount_pct / 100.0) if fnf_discount_pct > 0 else 0.0

				if allow_item_discount:
					if max_discount_allowed > 0:
						cashier_discount = server_price * (min(max_discount_allowed, 100.0) / 100.0)
					else:
						# When allow_user_to_edit_item_discount=1 and max_discount_allowed=0 (unbounded),
						# only permit explicit cashier discount when client explicitly sent discount fields
						# (still never allowing rate=0 stealth tampering without discount_percentage/amount).
						explicit_disc = flt(item.get("discount_percentage")) > 0 or flt(item.get("discount_amount")) > 0
						cashier_discount = server_price if explicit_disc else 0.0
				else:
					cashier_discount = 0.0

				# Stackable cap: best of (promo + coupon, fnf + coupon, cashier discount)
				max_allowed_discount = min(
					server_price,
					max(
						promo_discount + coupon_discount,
						fnf_discount + coupon_discount,
						cashier_discount,
					),
				)
				min_allowed_rate = max(0.0, server_price - max_allowed_discount)

				if client_rate < min_allowed_rate - PRICE_ROUNDING_EPSILON:
					if is_offline_sync and offline_tolerance_pct > 0:
						drift_pct = ((min_allowed_rate - client_rate) / server_price) * 100.0
						if drift_pct <= offline_tolerance_pct:
							frappe.logger().warning(
								f"Offline sync price drift accepted for {item.item_code}: "
								f"client_rate={client_rate}, server_price={server_price}, drift={drift_pct:.2f}%"
							)
							item.discount_amount = max(0.0, server_price - client_rate)
							item.discount_percentage = (
								round((item.discount_amount / server_price) * 100.0, 2) if server_price else 0.0
							)
							continue

					frappe.throw(
						_("Rate for item {0} ({1}) is below the authorized price ({2})").format(
							item.item_code, client_rate, round(min_allowed_rate, 2)
						),
						frappe.ValidationError,
					)

			# Ensure price_list_rate >= rate and discount fields match authoritative price
			if flt(item.price_list_rate) < client_rate:
				item.price_list_rate = client_rate
			discount_amt = max(0.0, flt(item.price_list_rate) - client_rate)
			item.discount_amount = discount_amt
			item.discount_percentage = (
				round((discount_amt / flt(item.price_list_rate)) * 100.0, 4)
				if flt(item.price_list_rate) > 0 and discount_amt > 0
				else 0.0
			)
		elif is_manual_edit and validate_manual_rate_edit_fn:
			validation = validate_manual_rate_edit_fn(item, pos_profile, pos_settings)
			if not validation.get("valid"):
				frappe.throw(validation.get("message"), frappe.ValidationError)

	# Validate invoice-level additional discount
	add_disc_amt = flt(invoice_doc.get("discount_amount") or 0)
	add_disc_pct = flt(invoice_doc.get("additional_discount_percentage") or 0)
	if add_disc_amt < 0 or add_disc_pct < 0:
		frappe.throw(_("Discount cannot be negative"), frappe.ValidationError)

	if add_disc_amt > PRICE_ROUNDING_EPSILON or add_disc_pct > 0:
		has_valid_coupon = bool(invoice_coupon) and _max_coupon_discount_amount(
			100.0, invoice_coupon, customer=customer, company=company
		) > 0
		if not allow_additional_discount and not has_valid_coupon and not is_offline_sync:
			frappe.throw(
				_("Additional invoice discount is not allowed for this POS Profile"),
				frappe.ValidationError,
			)
		if allow_additional_discount and max_discount_allowed > 0 and not has_valid_coupon:
			subtotal = sum(flt(i.qty) * flt(i.rate) for i in invoice_doc.get("items", []))
			effective_pct = (
				add_disc_pct
				if add_disc_pct > 0
				else ((add_disc_amt / subtotal) * 100.0 if subtotal > 0 else 0.0)
			)
			if effective_pct > max_discount_allowed + 0.01:
				frappe.throw(
					_("Additional discount ({0}%) exceeds maximum allowed discount ({1}%)").format(
						round(effective_pct, 2), max_discount_allowed
					),
					frappe.ValidationError,
				)
