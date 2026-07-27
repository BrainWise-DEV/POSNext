# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

from frappe.utils import cstr, flt

try:
	from erpnext.setup.doctype.item_group.item_group import get_child_item_groups
except Exception:  # pragma: no cover - ERPNext not installed in some environments

	def get_child_item_groups(item_group):
		return [item_group] if item_group else []


PROMOTION_TYPE_GWP = "GWP"

GWP_BASIS_MIN = "Min Qty"
GWP_BASIS_MAX = "Max Qty"


def _row_value(row, fieldname: str):
	if hasattr(row, "get"):
		return row.get(fieldname)
	return getattr(row, fieldname, None)


def _pricing_rule_apply_on_values(rule) -> set[str]:
	"""Return normalized apply-on values from a Pricing Rule document."""
	apply_on = cstr(_row_value(rule, "apply_on")).strip()
	if apply_on == "Item Code":
		if _row_value(rule, "mixed_conditions"):
			return {
				cstr(_row_value(row, "item_code"))
				for row in (_row_value(rule, "items") or [])
				if cstr(_row_value(row, "item_code"))
			}
		item_code = _row_value(rule, "item_code")
		return {cstr(item_code)} if item_code else set()

	if apply_on == "Item Group":
		values: set[str] = set()
		for row in _row_value(rule, "item_groups") or []:
			item_group = _row_value(row, "item_group")
			if item_group:
				values.update(cstr(group) for group in get_child_item_groups(item_group))
		return values

	if apply_on == "Brand":
		return {
			cstr(_row_value(row, "brand"))
			for row in (_row_value(rule, "brands") or [])
			if cstr(_row_value(row, "brand"))
		}

	return set()


def item_matches_pricing_rule_apply_on(item, rule) -> bool:
	"""True when a cart line falls under the rule's apply_on scope."""
	apply_on = cstr(_row_value(rule, "apply_on")).strip()
	if apply_on == "Transaction":
		return True

	field_map = {
		"Item Code": "item_code",
		"Item Group": "item_group",
		"Brand": "brand",
	}
	fieldname = field_map.get(apply_on)
	if not fieldname:
		return False

	item_value = cstr(_row_value(item, fieldname))
	return item_value in _pricing_rule_apply_on_values(rule)


def should_aggregate_gwp_quantities(apply_on, scheme_item_count=0):
	"""Aggregate cart qty when scheme targets an item group or multiple item codes."""
	apply_on = (apply_on or "").strip()
	if apply_on == "Item Group":
		return True
	if apply_on == "Item Code" and flt(scheme_item_count) > 1:
		return True
	return False


def calculate_gwp_discount_percentage(free_qty, purchased_qty):
	"""Return proportional GWP discount for display: free_qty / purchased_qty * 100."""
	purchased_qty = flt(purchased_qty)
	free_qty = flt(free_qty)
	if purchased_qty <= 0 or free_qty <= 0:
		return 0
	return min(100, flt(free_qty) / purchased_qty * 100)


def calculate_gwp_discount_amount(free_qty, unit_price):
	"""Return exact GWP discount amount: free_qty * unit_price."""
	free_qty = flt(free_qty)
	unit_price = flt(unit_price)
	if free_qty <= 0 or unit_price <= 0:
		return 0
	return free_qty * unit_price


def is_gwp_total_qty_eligible(total_qty, min_qty, max_qty):
	"""True when combined eligible quantity is within the min/max purchase range."""
	total_qty = flt(total_qty)
	min_qty = flt(min_qty)
	max_qty = flt(max_qty)

	if min_qty > 0 and total_qty < min_qty:
		return False
	if max_qty > 0 and total_qty > max_qty:
		return False
	return True


def get_gwp_slab_free_qty(slab_free_qty, total_qty, min_qty, max_qty):
	"""Return slab free_qty when the cart total is inside the min/max range."""
	if not is_gwp_total_qty_eligible(total_qty, min_qty, max_qty):
		return 0

	free_qty = flt(slab_free_qty)
	total_qty = flt(total_qty)
	if free_qty <= 0 or total_qty <= 0:
		return 0
	return min(free_qty, total_qty)


def distribute_gwp_free_units_for_basis(line_quantities, line_prices, total_free_units, paid_qty_basis):
	"""Allocate free units by price tier.

	Max Qty basis: discount on cheapest lines (customer pays expensive items).
	Min Qty basis: discount on most expensive lines (customer pays cheaper items).
	"""
	basis = (paid_qty_basis or GWP_BASIS_MAX).strip()
	expensive_first = basis == GWP_BASIS_MIN
	return distribute_gwp_free_units_by_price(
		line_quantities,
		line_prices,
		total_free_units,
		expensive_first=expensive_first,
	)


def distribute_gwp_free_units_by_price(
	line_quantities, line_prices, total_free_units, *, expensive_first=False
):
	"""Assign free units to lines sorted by unit price."""
	total_free_units = int(round(flt(total_free_units)))
	if total_free_units <= 0:
		return [0] * len(line_quantities)

	quantities = [int(flt(q)) for q in line_quantities]
	prices = [flt(p) for p in line_prices]
	if not quantities or sum(quantities) <= 0:
		return [0] * len(quantities)

	result = [0] * len(quantities)
	remaining = total_free_units
	sort_key = (lambda i: (-prices[i], i)) if expensive_first else (lambda i: (prices[i], i))
	for index in sorted(range(len(quantities)), key=sort_key):
		if remaining <= 0:
			break
		take = min(quantities[index], remaining)
		result[index] = take
		remaining -= take

	return result
