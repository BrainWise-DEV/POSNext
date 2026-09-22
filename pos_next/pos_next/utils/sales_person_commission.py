# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Item / Item Group / Brand Sales Person commission helpers for POS Next.

Commission rate priority (most specific first):
  1. Item
  2. Item Group
  3. Brand
  4. Sales Person.commission_rate (fallback)
"""

from __future__ import annotations

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


FIELD_ITEM_COMMISSIONS = "custom_item_commissions"
FIELD_ITEM_GROUP_COMMISSIONS = "custom_item_group_commissions"
FIELD_BRAND_COMMISSIONS = "custom_brand_commissions"
# Persisted cashier / payment-screen team (not the rebuilt sales_team aggregate)
FIELD_INVOICE_LEVEL_TEAM = "custom_pos_invoice_level_sales_team"


def _doc_get(doc, key, default=None):
	"""Read a field from a Frappe Document, dict, or SimpleNamespace."""
	if doc is None:
		return default
	if hasattr(doc, "get") and callable(doc.get):
		val = doc.get(key)
		return default if val is None else val
	return getattr(doc, key, default)


def sales_persons_enabled(pos_profile: str | None) -> bool:
	"""Return True when POS Settings enable_sales_persons is not Disabled."""
	if not pos_profile:
		return False
	value = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile},
		"enable_sales_persons",
	)
	return bool(value and value != "Disabled")


def get_allowed_sales_person_names(pos_profile: str | None = None) -> set[str]:
	"""Return enabled, non-group Sales Person names allowed for POS assignment.

	Mirrors the filters used by ``get_sales_persons`` (enabled, not group,
	optionally company-scoped via POS Profile).
	"""
	filters: dict = {
		"enabled": 1,
		"is_group": 0,
	}
	if pos_profile:
		company = frappe.db.get_value("POS Profile", pos_profile, "company")
		if company and frappe.db.has_column("Sales Person", "company"):
			filters["company"] = company

	return set(frappe.get_all("Sales Person", filters=filters, pluck="name"))


def _commission_map(doctype: str, fieldname: str, key_field: str, sales_person: str) -> dict[str, float]:
	"""Load {key: commission_rate} child rows for a Sales Person."""
	if not sales_person:
		return {}
	if not frappe.get_meta("Sales Person").has_field(fieldname):
		return {}

	rows = frappe.get_all(
		doctype,
		filters={"parent": sales_person, "parenttype": "Sales Person"},
		fields=[key_field, "commission_rate"],
	)
	return {r.get(key_field): flt(r.commission_rate) for r in rows if r.get(key_field)}


def get_item_commission_map(sales_person: str) -> dict[str, float]:
	"""Return {item_code: commission_rate} for a Sales Person."""
	return _commission_map(
		"Sales Person Item Commission",
		FIELD_ITEM_COMMISSIONS,
		"item",
		sales_person,
	)


def get_item_group_commission_map(sales_person: str) -> dict[str, float]:
	"""Return {item_group: commission_rate} for a Sales Person."""
	return _commission_map(
		"Sales Person Item Group Commission",
		FIELD_ITEM_GROUP_COMMISSIONS,
		"item_group",
		sales_person,
	)


def get_brand_commission_map(sales_person: str) -> dict[str, float]:
	"""Return {brand: commission_rate} for a Sales Person."""
	return _commission_map(
		"Sales Person Brand Commission",
		FIELD_BRAND_COMMISSIONS,
		"brand",
		sales_person,
	)


def get_sales_person_commission_maps(sales_person: str) -> dict:
	"""Return all override maps + fallback rate for a Sales Person."""
	return {
		"item_map": get_item_commission_map(sales_person),
		"item_group_map": get_item_group_commission_map(sales_person),
		"brand_map": get_brand_commission_map(sales_person),
		"commission_rate": flt(
			frappe.db.get_value("Sales Person", sales_person, "commission_rate") or 0
		)
		if sales_person
		else 0.0,
	}


def resolve_commission_rate(
	sales_person: str,
	item_code: str | None = None,
	item_group: str | None = None,
	brand: str | None = None,
	*,
	fallback_rate: float | None = None,
	item_map: dict[str, float] | None = None,
	ig_map: dict[str, float] | None = None,
	brand_map: dict[str, float] | None = None,
) -> float:
	"""Resolve rate by priority: Item → Item Group → Brand → Commission Rate."""
	if not sales_person:
		return 0.0

	if item_map is None:
		item_map = get_item_commission_map(sales_person)
	if ig_map is None:
		ig_map = get_item_group_commission_map(sales_person)
	if brand_map is None:
		brand_map = get_brand_commission_map(sales_person)

	if item_code and item_code in item_map:
		return flt(item_map[item_code])
	if item_group and item_group in ig_map:
		return flt(ig_map[item_group])
	if brand and brand in brand_map:
		return flt(brand_map[brand])

	if fallback_rate is not None:
		return flt(fallback_rate)

	return flt(frappe.db.get_value("Sales Person", sales_person, "commission_rate") or 0)


def _get_item_master_dims(item_code: str | None, cache: dict | None = None) -> dict:
	"""Load item_group, brand, grant_commission from Item master (never trust client)."""
	if not item_code:
		return {"item_group": None, "brand": None, "grant_commission": 1}

	if cache is not None and item_code in cache:
		return cache[item_code]

	row = frappe.db.get_value(
		"Item",
		item_code,
		["item_group", "brand", "grant_commission"],
		as_dict=True,
	)
	dims = {
		"item_group": row.item_group if row else None,
		"brand": row.brand if row else None,
		# ERPNext Item default for grant_commission is 1
		"grant_commission": cint(row.grant_commission) if row and row.grant_commission is not None else 1,
	}
	if cache is not None:
		cache[item_code] = dims
	return dims


def _item_grants_commission(item, *, item_cache: dict | None = None) -> bool:
	"""Match ERPNext: only items with grant_commission contribute.

	Always resolves from Item master by item_code when available so clients
	cannot spoof grant_commission on the commission path.
	"""
	item_code = _line_item_code(item)
	if item_code:
		dims = _get_item_master_dims(item_code, item_cache)
		return bool(cint(dims["grant_commission"]))

	# No item_code — fall back to line value / default True
	if hasattr(item, "get"):
		grant = item.get("grant_commission")
	else:
		grant = getattr(item, "grant_commission", None)
	if grant is None:
		return True
	return bool(cint(grant))


def _line_net_amount(item) -> float:
	"""Prefer base_net_amount (company currency); fall back to net_amount / amount."""
	for key in ("base_net_amount", "net_amount", "amount", "base_amount"):
		val = item.get(key) if hasattr(item, "get") else getattr(item, key, None)
		if val is not None:
			return flt(val)
	return 0.0


def _line_item_code(item) -> str | None:
	code = item.get("item_code") if hasattr(item, "get") else getattr(item, "item_code", None)
	return code or None


def _line_item_group(item, *, item_cache: dict | None = None) -> str | None:
	"""Item Group from Item master only (ignore client-supplied line value)."""
	item_code = _line_item_code(item)
	if item_code:
		return _get_item_master_dims(item_code, item_cache)["item_group"]
	group = item.get("item_group") if hasattr(item, "get") else getattr(item, "item_group", None)
	return group or None


def _line_brand(item, *, item_cache: dict | None = None) -> str | None:
	"""Brand from Item master only (ignore client-supplied line value)."""
	item_code = _line_item_code(item)
	if item_code:
		return _get_item_master_dims(item_code, item_cache)["brand"]
	brand = item.get("brand") if hasattr(item, "get") else getattr(item, "brand", None)
	return brand or None


def _line_sales_person(item) -> str | None:
	sp = item.get("sales_person") if hasattr(item, "get") else getattr(item, "sales_person", None)
	return sp or None


def _line_needs_sales_person_coverage(item) -> bool:
	"""True when the line is economically billable and must have an effective SP.

	Do not trust client ``is_free_item`` alone — a tampered flag with positive net
	would otherwise bypass mandatory Sales Person. Exempt only when abs(net) ≈ 0
	(legitimate promo free rows after totals).
	"""
	return abs(_line_net_amount(item)) > 0.0001


def all_items_have_sales_person(items) -> bool:
	"""True when every billable (non-zero-net) cart/SI line has a sales_person set."""
	paid = [item for item in (items or []) if _line_needs_sales_person_coverage(item)]
	if not paid:
		return False
	for item in paid:
		if not _line_sales_person(item):
			return False
	return True


def _has_any_commission_overrides(sales_person: str) -> bool:
	maps = get_sales_person_commission_maps(sales_person)
	return bool(maps["item_map"] or maps["item_group_map"] or maps["brand_map"])


def needs_item_level_contribution(invoice_doc) -> bool:
	"""True when item-level SP or scoped rates require custom incentives."""
	items = _doc_get(invoice_doc, "items") or []
	for item in items:
		if _line_sales_person(item):
			return True

	sales_team = _doc_get(invoice_doc, "sales_team") or []
	for row in sales_team:
		sp = row.get("sales_person") if hasattr(row, "get") else getattr(row, "sales_person", None)
		if sp and _has_any_commission_overrides(sp):
			return True

	return False


def _team_has_sales_person(invoice_team) -> bool:
	for row in invoice_team or []:
		sp = row.get("sales_person") if hasattr(row, "get") else getattr(row, "sales_person", None)
		if sp:
			return True
	return False


def validate_sales_person_coverage(
	invoice_doc,
	pos_profile: str | None = None,
	*,
	invoice_level_team=None,
) -> None:
	"""Throw if sales persons are enabled and any line lacks an effective SP.

	``invoice_level_team`` must be the cashier / payment-screen team (or ``[]``),
	never the rebuilt aggregate ``sales_team`` after ``build_sales_team_from_items``.
	"""
	profile = pos_profile or _doc_get(invoice_doc, "pos_profile")
	if not sales_persons_enabled(profile):
		return

	items = _doc_get(invoice_doc, "items") or []
	if not items:
		return

	if invoice_level_team is None:
		invoice_level_team = _doc_get(invoice_doc, "sales_team") or []

	has_invoice_team = _team_has_sales_person(invoice_level_team)
	# Free / zero-net rows do not need a Sales Person (ignore client is_free_item alone)
	uncovered = [
		item
		for item in items
		if _line_needs_sales_person_coverage(item) and not _line_sales_person(item)
	]
	if uncovered and not has_invoice_team:
		frappe.throw(
			_(
				"Sales Person is required. Select a Sales Person on the payment screen, "
				"or assign a Sales Person to every item in the cart."
			),
			title=_("Sales Person Required"),
		)


def validate_sales_person_assignments(
	invoice_doc,
	pos_profile: str | None = None,
	*,
	invoice_level_team=None,
) -> None:
	"""Reject Sales Person IDs that are disabled, group nodes, or out of company scope."""
	profile = pos_profile or _doc_get(invoice_doc, "pos_profile")
	if not sales_persons_enabled(profile):
		return

	allowed = get_allowed_sales_person_names(profile)
	invalid: set[str] = set()

	for item in _doc_get(invoice_doc, "items") or []:
		sp = _line_sales_person(item)
		if sp and sp not in allowed:
			invalid.add(sp)

	team = invoice_level_team
	if team is None:
		team = _doc_get(invoice_doc, "sales_team") or []
	for row in team or []:
		sp = row.get("sales_person") if hasattr(row, "get") else getattr(row, "sales_person", None)
		if sp and sp not in allowed:
			invalid.add(sp)

	if invalid:
		frappe.throw(
			_("Invalid or disabled Sales Person(s): {0}").format(", ".join(sorted(invalid))),
			title=_("Invalid Sales Person"),
		)


def clear_sales_person_fields(invoice_doc) -> None:
	"""Strip item-level and invoice-level sales person when the feature is disabled."""
	for item in _doc_get(invoice_doc, "items") or []:
		if hasattr(item, "sales_person"):
			item.sales_person = None
		elif isinstance(item, dict):
			item["sales_person"] = None

	invoice_doc.sales_team = []
	invoice_doc.flags.pos_invoice_level_sales_team = []
	invoice_doc.flags.pos_commission_breakdown = {
		"allocated_by_sp": {},
		"incentives_by_sp": {},
		"eligible_total": 0,
	}
	persist_invoice_level_sales_team(invoice_doc, [])


def persist_invoice_level_sales_team(invoice_doc, invoice_level) -> None:
	"""Store cashier invoice-level team on the SI (survives rebuild of sales_team)."""
	meta = getattr(invoice_doc, "meta", None)
	if not meta or not meta.has_field(FIELD_INVOICE_LEVEL_TEAM):
		return
	payload = []
	for m in invoice_level or []:
		sp = m.get("sales_person") if hasattr(m, "get") else getattr(m, "sales_person", None)
		if not sp:
			continue
		pct = flt(
			m.get("allocated_percentage")
			if hasattr(m, "get")
			else getattr(m, "allocated_percentage", 0)
		)
		payload.append({"sales_person": sp, "allocated_percentage": pct})
	invoice_doc.set(FIELD_INVOICE_LEVEL_TEAM, frappe.as_json(payload))


def load_stored_invoice_level_sales_team(invoice_name: str) -> list[dict] | None:
	"""Load persisted cashier team from a Sales Invoice, or None if unset/missing field."""
	if not invoice_name:
		return None
	if not frappe.get_meta("Sales Invoice").has_field(FIELD_INVOICE_LEVEL_TEAM):
		return None
	raw = frappe.db.get_value("Sales Invoice", invoice_name, FIELD_INVOICE_LEVEL_TEAM)
	if raw in (None, ""):
		return None
	try:
		parsed = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError, json.JSONDecodeError):
		return None
	if not isinstance(parsed, list):
		return None
	return parsed


def _legacy_invoice_level_from_original(return_against: str, original_items) -> list[dict]:
	"""Best-effort recover cashier team for invoices saved before persistence existed."""
	item_sps = [r.sales_person for r in original_items]
	if item_sps and all(item_sps):
		# All lines had item-level SP → no invoice-level fallback
		return []
	if not any(item_sps):
		# Pure invoice-level sale → saved sales_team is the cashier team
		rows = frappe.get_all(
			"Sales Team",
			filters={"parent": return_against, "parenttype": "Sales Invoice"},
			fields=["sales_person", "allocated_percentage"],
			order_by="idx",
		)
		return [
			{"sales_person": r.sales_person, "allocated_percentage": flt(r.allocated_percentage)}
			for r in rows
			if r.sales_person
		]
	# Mixed legacy — cannot safely recover cashier team from the aggregate
	return []


def apply_return_sales_person_from_original(invoice_doc) -> None:
	"""Force return line sales_person from the original Sales Invoice Item row.

	Ignores client overrides so commission reversal hits the same SP as the sale.
	Restores invoice-level team from the persisted cashier team (not the aggregate).
	Requires ``sales_invoice_item`` when the original has duplicate item_code rows.
	"""
	if not _doc_get(invoice_doc, "is_return"):
		return

	return_against = _doc_get(invoice_doc, "return_against")
	if not return_against:
		return

	original_items = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": return_against},
		fields=["name", "item_code", "sales_person"],
	)
	by_name = {r.name: r for r in original_items}
	# Safe item_code fallback only when a single original row exists for that code
	code_counts: dict[str, list] = defaultdict(list)
	for r in original_items:
		if r.item_code:
			code_counts[r.item_code].append(r)

	stored = load_stored_invoice_level_sales_team(return_against)
	if stored is not None:
		invoice_doc.flags.pos_invoice_level_sales_team = stored
	else:
		invoice_doc.flags.pos_invoice_level_sales_team = _legacy_invoice_level_from_original(
			return_against, original_items
		)

	has_sales_person_field = frappe.get_meta("Sales Invoice Item").has_field("sales_person")

	for item in _doc_get(invoice_doc, "items") or []:
		ref = _doc_get(item, "sales_invoice_item")
		code = _line_item_code(item)
		orig = None

		if ref:
			orig = by_name.get(ref)
			if not orig:
				frappe.throw(
					_("Return item link {0} does not belong to invoice {1}").format(
						ref, return_against
					),
					title=_("Invalid Return Item"),
				)
			if code and orig.item_code and orig.item_code != code:
				frappe.throw(
					_(
						"Return item {0} does not match original row {1} ({2})"
					).format(code, ref, orig.item_code),
					title=_("Invalid Return Item"),
				)
		else:
			matches = code_counts.get(code or "", [])
			if len(matches) == 1:
				orig = matches[0]
				# Bind the row so downstream qty checks can use it
				if hasattr(item, "sales_invoice_item"):
					item.sales_invoice_item = orig.name
				elif isinstance(item, dict):
					item["sales_invoice_item"] = orig.name
			elif len(matches) > 1:
				frappe.throw(
					_(
						"sales_invoice_item is required when returning {0} "
						"(multiple matching lines on the original invoice)."
					).format(code),
					title=_("Return Item Required"),
				)

		sp = orig.sales_person if orig and has_sales_person_field else None
		if hasattr(item, "sales_person"):
			item.sales_person = sp or None
		elif isinstance(item, dict):
			item["sales_person"] = sp or None


def _normalize_invoice_team(invoice_team) -> list[dict]:
	"""Return list of {sales_person, allocated_percentage} with positive shares."""
	members = []
	for row in invoice_team or []:
		sp = row.get("sales_person") if hasattr(row, "get") else getattr(row, "sales_person", None)
		if not sp:
			continue
		pct = flt(
			row.get("allocated_percentage")
			if hasattr(row, "get")
			else getattr(row, "allocated_percentage", 0)
		)
		members.append({"sales_person": sp, "allocated_percentage": pct})

	if not members:
		return []

	total_pct = sum(m["allocated_percentage"] for m in members)
	if total_pct <= 0:
		even = 100.0 / len(members)
		for m in members:
			m["allocated_percentage"] = even
	elif abs(total_pct - 100.0) > 0.01:
		# Renormalize to 100
		for m in members:
			m["allocated_percentage"] = m["allocated_percentage"] * 100.0 / total_pct

	return members


def build_sales_team_from_items(invoice_doc, invoice_level_team=None) -> list[dict]:
	"""
	Build sales_team rows from item-level SP + invoice-level fallback.

	Returns list of dicts ready for invoice_doc.append("sales_team", ...):
	sales_person, allocated_percentage, commission_rate, incentives (prelim).

	Side effect: leaves resolved commission details on invoice_doc.flags for
	calculate_contribution override.
	"""
	items = _doc_get(invoice_doc, "items") or []
	invoice_team = _normalize_invoice_team(
		invoice_level_team if invoice_level_team is not None else _doc_get(invoice_doc, "sales_team")
	)

	# Cache SP master data + Item dims
	sp_cache: dict[str, dict] = {}
	item_cache: dict[str, dict] = {}

	def _sp_info(name: str) -> dict:
		if name not in sp_cache:
			maps = get_sales_person_commission_maps(name)
			sp_cache[name] = {
				"commission_rate": maps["commission_rate"],
				"item_map": maps["item_map"],
				"ig_map": maps["item_group_map"],
				"brand_map": maps["brand_map"],
			}
		return sp_cache[name]

	# Aggregates per sales person
	allocated_by_sp: dict[str, float] = defaultdict(float)
	incentives_by_sp: dict[str, float] = defaultdict(float)
	weighted_rate_num: dict[str, float] = defaultdict(float)

	eligible_total = 0.0

	for item in items:
		if not _item_grants_commission(item, item_cache=item_cache):
			continue

		line_net = _line_net_amount(item)
		if not line_net:
			continue

		item_code = _line_item_code(item)
		item_group = _line_item_group(item, item_cache=item_cache)
		brand = _line_brand(item, item_cache=item_cache)
		line_sp = _line_sales_person(item)

		shares: list[tuple[str, float]] = []
		if line_sp:
			shares = [(line_sp, 1.0)]
		elif invoice_team:
			shares = [
				(m["sales_person"], flt(m["allocated_percentage"]) / 100.0) for m in invoice_team
			]
		else:
			continue

		eligible_total += abs(line_net)

		for sp_name, share in shares:
			info = _sp_info(sp_name)
			rate = resolve_commission_rate(
				sp_name,
				item_code=item_code,
				item_group=item_group,
				brand=brand,
				fallback_rate=info["commission_rate"],
				item_map=info["item_map"],
				ig_map=info["ig_map"],
				brand_map=info["brand_map"],
			)
			portion = line_net * share
			commission = portion * rate / 100.0
			allocated_by_sp[sp_name] += portion
			incentives_by_sp[sp_name] += commission
			weighted_rate_num[sp_name] += abs(portion) * rate

	if not allocated_by_sp:
		# No eligible amounts — still surface invoice team if provided
		result = []
		for m in invoice_team:
			info = _sp_info(m["sales_person"])
			result.append(
				{
					"sales_person": m["sales_person"],
					"allocated_percentage": m["allocated_percentage"],
					"commission_rate": info["commission_rate"],
					"incentives": 0,
				}
			)
		invoice_doc.flags.pos_commission_breakdown = {
			"allocated_by_sp": {},
			"incentives_by_sp": {},
			"eligible_total": 0,
		}
		return result

	# Use absolute amounts for percentage so returns (negative nets) still sum to 100
	abs_total = sum(abs(v) for v in allocated_by_sp.values()) or 1.0
	result = []
	sp_names = list(allocated_by_sp.keys())
	raw_pcts = [abs(allocated_by_sp[sp]) * 100.0 / abs_total for sp in sp_names]
	# Force exact 100 on the last row to avoid float drift
	running_pct = 0.0
	for idx, sp_name in enumerate(sp_names):
		amount = allocated_by_sp[sp_name]
		if idx == len(sp_names) - 1:
			pct = 100.0 - running_pct
		else:
			pct = raw_pcts[idx]
			running_pct += pct

		abs_alloc = abs(amount) or 1.0
		display_rate = (weighted_rate_num[sp_name] / abs_alloc) if abs_alloc else 0.0

		result.append(
			{
				"sales_person": sp_name,
				"allocated_percentage": flt(pct),
				"commission_rate": flt(display_rate),
				"incentives": flt(incentives_by_sp[sp_name]),
			}
		)

	invoice_doc.flags.pos_commission_breakdown = {
		"allocated_by_sp": dict(allocated_by_sp),
		"incentives_by_sp": dict(incentives_by_sp),
		"eligible_total": eligible_total,
		"weighted_rate_num": dict(weighted_rate_num),
	}
	return result


def apply_sales_team_to_invoice(invoice_doc, sales_team_rows: list[dict]) -> None:
	"""Replace invoice sales_team with computed rows."""
	invoice_doc.sales_team = []
	for row in sales_team_rows or []:
		if not row.get("sales_person"):
			continue
		invoice_doc.append(
			"sales_team",
			{
				"sales_person": row["sales_person"],
				"allocated_percentage": flt(row.get("allocated_percentage") or 0),
				"commission_rate": row.get("commission_rate"),
				"incentives": flt(row.get("incentives") or 0),
			},
		)


def apply_item_level_contribution(invoice_doc) -> None:
	"""
	Set allocated_amount / incentives / commission_rate on sales_team using
	per-line Item Group rates. Call from CustomSalesInvoice.calculate_contribution.

	Always rebuilds from current item nets so amounts stay correct after
	ERPNext's calculate_taxes_and_totals.
	"""
	# Prefer the original invoice-level team captured at POS submit time.
	# Falling back to current sales_team would incorrectly treat item-level
	# SPs as invoice-level fallbacks for uncovered lines.
	invoice_level = getattr(invoice_doc.flags, "pos_invoice_level_sales_team", None)
	if invoice_level is None:
		# Desk / non-POS path: only use invoice team for lines without item SP
		# when no item has sales_person (classic behaviour), otherwise empty
		# fallback so item-level rows are not re-used as invoice fallback.
		has_item_sp = any(_line_sales_person(item) for item in (_doc_get(invoice_doc, "items") or []))
		if has_item_sp:
			invoice_level = []
		else:
			invoice_level = [
				{
					"sales_person": row.sales_person,
					"allocated_percentage": flt(row.allocated_percentage),
				}
				for row in (_doc_get(invoice_doc, "sales_team") or [])
				if row.sales_person
			]

	rows = build_sales_team_from_items(invoice_doc, invoice_level_team=invoice_level)
	apply_sales_team_to_invoice(invoice_doc, rows)
	breakdown = invoice_doc.flags.pos_commission_breakdown or {}

	allocated_by_sp = breakdown.get("allocated_by_sp") or {}
	incentives_by_sp = breakdown.get("incentives_by_sp") or {}
	weighted_rate_num = breakdown.get("weighted_rate_num") or {}

	# Ensure amount_eligible_for_commission is set (ERPNext may have set it)
	if invoice_doc.meta.get_field("amount_eligible_for_commission"):
		item_cache: dict[str, dict] = {}
		eligible = sum(
			_line_net_amount(item)
			for item in (_doc_get(invoice_doc, "items") or [])
			if _item_grants_commission(item, item_cache=item_cache)
		)
		invoice_doc.amount_eligible_for_commission = flt(
			eligible, invoice_doc.precision("amount_eligible_for_commission")
		)

	sales_team = _doc_get(invoice_doc, "sales_team") or []
	total_pct = 0.0
	for row in sales_team:
		sp = row.sales_person
		invoice_doc.round_floats_in(row)

		alloc = flt(allocated_by_sp.get(sp, 0))
		row.allocated_amount = flt(alloc, invoice_doc.precision("allocated_amount", row))

		incentive = flt(incentives_by_sp.get(sp, 0))
		row.incentives = flt(incentive, invoice_doc.precision("incentives", row))

		abs_alloc = abs(alloc) or 1.0
		if sp in weighted_rate_num:
			row.commission_rate = flt(weighted_rate_num[sp] / abs_alloc, 6)

		total_pct += flt(row.allocated_percentage)

	if sales_team and abs(flt(total_pct, 6) - 100.0) > 0.05:
		frappe.throw(_("Total allocated percentage for sales team should be 100"))
