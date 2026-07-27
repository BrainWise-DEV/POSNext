# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Scope resolution for Pricing Rules — which cart lines a rule targets.

A Pricing Rule selects its targets through ``apply_on``. For ``Item Code``,
``Item Group`` and ``Brand`` the targets live in a **child table**; Pricing Rule
carries no scalar ``item_code`` / ``item_group`` / ``brand`` field at all, so
reading one off the document raises ``AttributeError`` (Frappe's ``Document``
defines no ``__getattr__``). ``Transaction`` targets every line.

Matching semantics differ by scope:

- **Item Code** / **Brand** — exact match on the line's value.
- **Item Group** — matches by tree lineage, so a rule row on ``Electronics``
  also covers an item in ``Electronics > Phones``. This mirrors ERPNext's own
  pricing engine, which resolves item groups through the nested set.

Callers that test many lines against one rule should hoist
:func:`get_scope_keys` out of their loop and pass the result to
:func:`item_matches_rule_scope` as ``scope_keys``.
"""

from __future__ import annotations

import frappe
from frappe.query_builder import DocType
from frappe.utils import cstr

APPLY_ON_TRANSACTION = "Transaction"

# apply_on -> (child table fieldname on Pricing Rule, value fieldname on the row)
APPLY_ON_SCOPE: dict[str, tuple[str, str]] = {
	"Item Code": ("items", "item_code"),
	"Item Group": ("item_groups", "item_group"),
	"Brand": ("brands", "brand"),
}

# apply_on -> the child DocType holding the rows (same table for Pricing Rule and
# Promotional Scheme, which is why one custom field per child covers both).
APPLY_ON_CHILD_DOCTYPE: dict[str, str] = {
	"Item Code": "Pricing Rule Item Code",
	"Item Group": "Pricing Rule Item Group",
	"Brand": "Pricing Rule Brand",
}

ITEM_GROUP_FIELD = "item_group"

# Per-scope-row discount, added by POS Next to all three child DocTypes.
SCOPE_PERCENTAGE_FIELD = "pos_discount_percentage"


def get_item_group_with_descendants(item_group):
	"""Get an item group and all its descendants using nested set model."""
	if not item_group:
		return []

	cache_key = f"item_group_descendants:{item_group}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	ItemGroup = DocType("Item Group")
	group_data = (
		frappe.qb.from_(ItemGroup)
		.select(ItemGroup.lft, ItemGroup.rgt, ItemGroup.is_group)
		.where(ItemGroup.name == item_group)
		.run(as_dict=True)
	)

	if not group_data:
		result = [item_group]
	else:
		group = group_data[0]
		if not group.is_group:
			result = [item_group]
		else:
			descendants = (
				frappe.qb.from_(ItemGroup)
				.select(ItemGroup.name)
				.where(ItemGroup.lft > group.lft)
				.where(ItemGroup.rgt < group.rgt)
				.run(pluck="name")
			)
			result = [item_group, *list(descendants)]

	frappe.cache().set_value(cache_key, result, expires_in_sec=300)
	return result


def get_scope_config(apply_on) -> tuple[str, str] | None:
	"""Return ``(child_table_fieldname, row_fieldname)`` for a child-table scope.

	``None`` for ``Transaction`` and for anything unrecognised — callers must
	treat those separately rather than falling through to a child-table read.
	"""
	return APPLY_ON_SCOPE.get(cstr(apply_on or ""))


def get_scope_keys(rule) -> set[str]:
	"""Every value the rule targets, with item groups expanded to their descendants.

	Returns an empty set for ``Transaction`` (which matches on presence, not on a
	key) and for rules whose scope table is empty.
	"""
	scope = get_scope_config(rule.get("apply_on"))
	if not scope:
		return set()

	table_field, row_field = scope
	keys = {cstr(row.get(row_field)) for row in (rule.get(table_field) or []) if row.get(row_field)}

	if row_field != ITEM_GROUP_FIELD:
		return keys

	expanded: set[str] = set()
	for group in keys:
		expanded.update(get_item_group_with_descendants(group))
	return expanded


def item_matches_rule_scope(item, rule, scope_keys: set[str] | None = None) -> bool:
	"""Whether a cart line falls inside the rule's scope.

	``scope_keys`` may be precomputed via :func:`get_scope_keys` to avoid
	re-expanding item group trees for every line.
	"""
	apply_on = rule.get("apply_on")
	if apply_on == APPLY_ON_TRANSACTION:
		return True

	scope = get_scope_config(apply_on)
	if not scope:
		return False

	_, row_field = scope
	value = cstr(item.get(row_field) or "")
	if not value:
		return False

	if scope_keys is None:
		scope_keys = get_scope_keys(rule)
	return value in scope_keys
