# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Product-discount (free item) quantity helpers for recursive offers."""

from __future__ import annotations

import math

from frappe.utils import flt

from pos_next.api.gwp import is_gwp_total_qty_eligible


def floor_free_qty(qty) -> int:
	"""Free gift quantities are whole units only (never round up)."""
	return max(0, int(math.floor(flt(qty))))


def compute_additional_recursive_free_qty(
	purchased_qty, free_qty, recurse_for, apply_recursion_over=0
) -> int:
	"""ERPNext-style recursive free qty: extra free units for every ``recurse_for``.

	Example: recurse_for=2, free_qty=1, purchased=6 → 3 free (additional row).
	"""
	free_qty = flt(free_qty) or 1
	recurse_for = flt(recurse_for)
	effective = max(0, flt(purchased_qty) - flt(apply_recursion_over))
	if recurse_for <= 0:
		return floor_free_qty(free_qty) if effective > 0 else 0
	if effective <= 0:
		return 0
	return floor_free_qty((effective // recurse_for) * free_qty)


def compute_included_recursive_free_qty(
	purchased_qty, free_qty, recurse_for, apply_recursion_over=0
) -> int:
	"""Same-item recursive free qty taken from the purchased units (bundled).

	Buy ``recurse_for`` get ``free_qty`` free means one free unit in every
	``recurse_for + free_qty`` purchased units (pay for recurse_for, get free_qty).

	Example: recurse_for=2, free_qty=1 → cycle 3:
	- qty 2 → 0 free (need 3 to qualify for the first free)
	- qty 3 → 1 free (pay 2)
	- qty 5 → 1 free
	- qty 6 → 2 free
	"""
	free_qty = flt(free_qty) or 1
	recurse_for = flt(recurse_for)
	effective = max(0, flt(purchased_qty) - flt(apply_recursion_over))
	if recurse_for <= 0:
		return floor_free_qty(min(free_qty, effective)) if effective > 0 else 0
	if effective <= 0:
		return 0

	cycle = recurse_for + free_qty
	if cycle <= 0:
		return 0
	return floor_free_qty((effective // cycle) * free_qty)


def compute_product_recursive_free_qty(
	purchased_qty,
	free_qty,
	recurse_for,
	apply_recursion_over=0,
	*,
	same_item: bool = False,
	is_recursive: bool = True,
	min_qty=0,
	max_qty=0,
) -> int:
	"""Return free qty for a product discount given purchased qty and rule flags."""
	purchased_qty = flt(purchased_qty)
	if not is_gwp_total_qty_eligible(purchased_qty, min_qty, max_qty):
		return 0

	slab_free = flt(free_qty) or 1
	if not is_recursive:
		return floor_free_qty(min(slab_free, purchased_qty)) if purchased_qty > 0 else 0

	if same_item:
		return compute_included_recursive_free_qty(
			purchased_qty, slab_free, recurse_for, apply_recursion_over
		)
	return compute_additional_recursive_free_qty(
		purchased_qty, slab_free, recurse_for, apply_recursion_over
	)


def should_aggregate_product_quantities(apply_on, scheme_item_count=0) -> bool:
	"""Whether Item Group / Brand scopes may aggregate for *other-item* free gifts.

	Same-item product discounts never aggregate — callers must also require
	``not same_item``. Item Code is always per-SKU.

	``scheme_item_count`` is kept for call-site compatibility.
	"""
	apply_on = (apply_on or "").strip()
	_ = scheme_item_count
	return apply_on in ("Item Group", "Brand")
