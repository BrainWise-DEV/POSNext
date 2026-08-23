# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Gift Pool promotion helpers.

A Gift Pool scheme targets item groups. Each group has an ordered list of free
items from that group. Buying any non-pool item in the group grants a total of
``free_qty`` free units, spread across those item codes in list order — once
per cart, not once per paid unit.
"""

from __future__ import annotations

from collections import OrderedDict

import frappe
from frappe.utils import cint, cstr, flt

from pos_next.promotions.scope import get_item_group_with_descendants

PROMOTION_TYPE_GIFT_POOL = "Gift Pool"


def _row_value(row, fieldname: str):
	if hasattr(row, "get"):
		return row.get(fieldname)
	return getattr(row, fieldname, None)


def group_gift_pool_items(rows) -> dict[str, list[str]]:
	"""Return item_group -> ordered unique free item codes."""
	pools: dict[str, list[str]] = OrderedDict()
	for row in rows or []:
		item_group = cstr(_row_value(row, "item_group"))
		item_code = cstr(_row_value(row, "item_code"))
		if not item_group or not item_code:
			continue
		pool = pools.setdefault(item_group, [])
		if item_code not in pool:
			pool.append(item_code)
	return dict(pools)


def _free_qty(row) -> int:
	qty = cint(_row_value(row, "free_qty"))
	return qty if qty > 0 else 1


def group_gift_pool_free_qty(rows) -> dict[str, int]:
	"""Return item_group -> Free Qty from the first row in that group."""
	qtys: dict[str, int] = OrderedDict()
	for row in rows or []:
		item_group = cstr(_row_value(row, "item_group"))
		if not item_group or item_group in qtys:
			continue
		qtys[item_group] = _free_qty(row)
	return dict(qtys)


def allocate_gift_pool_free_items(paid_qty, pool_item_codes: list[str], free_qty=1) -> dict[str, int]:
	"""Spread ``free_qty`` units across pool item codes in row order.

	The total granted quantity equals ``free_qty``. Extra units wrap around:
	qty 3 with A, B, C → ``{A: 1, B: 1, C: 1}``; qty 5 with A, B → ``{A: 3, B: 2}``.
	"""
	paid_qty = max(0, int(flt(paid_qty)))
	free_qty = cint(free_qty)
	if free_qty <= 0:
		free_qty = 1
	if paid_qty <= 0 or not pool_item_codes:
		return {}
	counts: dict[str, int] = OrderedDict()
	n = len(pool_item_codes)
	for i in range(free_qty):
		code = pool_item_codes[i % n]
		counts[code] = counts.get(code, 0) + 1
	return dict(counts)


def _scheme_gift_pool_rows(scheme_name: str):
	if not scheme_name or not frappe.db.exists("DocType", "POS Gift Pool Item"):
		return []
	if not frappe.db.exists("Promotional Scheme", scheme_name):
		return []
	fields = ["item_group", "item_code", "idx"]
	if frappe.db.has_column("POS Gift Pool Item", "free_qty"):
		fields.append("free_qty")
	return frappe.get_all(
		"POS Gift Pool Item",
		filters={"parent": scheme_name, "parenttype": "Promotional Scheme"},
		fields=fields,
		order_by="idx asc",
	)


def get_scheme_gift_pools(scheme_name: str) -> dict[str, list[str]]:
	"""Load ordered free-item pools for a Promotional Scheme."""
	return group_gift_pool_items(_scheme_gift_pool_rows(scheme_name))


def get_scheme_gift_pool_qtys(scheme_name: str) -> dict[str, int]:
	"""Load Free Qty per item group for a Promotional Scheme."""
	return group_gift_pool_free_qty(_scheme_gift_pool_rows(scheme_name))


def item_belongs_to_item_group(item_code: str, item_group: str) -> bool:
	"""True when the item's group is ``item_group`` or a descendant of it."""
	if not item_code or not item_group:
		return False
	item_item_group = cstr(frappe.get_cached_value("Item", item_code, "item_group"))
	if not item_item_group:
		return False
	return item_item_group in {cstr(g) for g in get_item_group_with_descendants(item_group)}


def expanded_groups(item_group: str) -> set[str]:
	return {cstr(g) for g in get_item_group_with_descendants(item_group) if cstr(g)}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def gift_pool_item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
	"""Item search for Gift Pool: selected group plus descendants.

	Link fields want rows as lists. MultiSelectDialog calls search_widget with
	``as_dict=1`` and reads ``result.item_name`` / ``result.item_group``; lists
	render as blank checkbox rows.
	"""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = frappe._dict(filters or {})
	item_group = filters.pop("item_group", None)

	list_filters = {
		"disabled": 0,
		"has_variants": 0,
	}
	if item_group:
		list_filters["item_group"] = ["in", list(expanded_groups(item_group)) or [item_group]]
	list_filters.update({k: v for k, v in filters.items() if v not in (None, "")})

	or_filters = []
	if txt:
		or_filters = [
			["name", "like", f"%{txt}%"],
			["item_name", "like", f"%{txt}%"],
		]
		if searchfield and searchfield not in ("name", "item_name"):
			or_filters.append([searchfield, "like", f"%{txt}%"])

	as_dict = bool(cint(as_dict))
	rows = frappe.get_list(
		"Item",
		filters=list_filters,
		fields=["name", "item_name", "item_group"],
		limit_start=start,
		limit_page_length=page_len,
		order_by="item_name asc",
		or_filters=or_filters or None,
		as_list=False,
	)
	if as_dict:
		return rows
	return [[row.get("name"), row.get("item_name"), row.get("item_group")] for row in rows]
