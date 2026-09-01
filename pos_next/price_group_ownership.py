"""Ownership constants and field definitions for the Price Group feature.

Ported from the `selling_additional` app. A Price Group owns exactly one generated
Price List (`PG-<name>`), the unscoped Item Price rows on that list, and the POS
Profiles matching its outlets. Ownership is recorded in Custom Fields so a row can
always be traced back to the group that created it — and restored when the group is
disabled or deleted.
"""

from dataclasses import dataclass
from types import MappingProxyType

OWNER_FIELD = "custom_pos_next_price_group"
PRICE_LIST_OWNER_FIELD = OWNER_FIELD
ITEM_PRICE_OWNER_FIELD = OWNER_FIELD
PROFILE_OWNER_FIELD = OWNER_FIELD
PROFILE_PREVIOUS_PRICE_LIST_FIELD = "custom_pos_next_previous_price_list"
MANAGED_PRICE_LIST_PREFIX = "PG-"

SCOPE_FIELDS = ("customer", "supplier", "batch_no", "valid_upto", "packing_unit")
"""Item Price fields that mark a row as SCOPED, and that can legitimately be empty.

`valid_from` is deliberately NOT here even though `ItemPrice.check_duplicates` treats it as
a discriminator. It carries meta default `'Today'`, so every row Frappe inserts already has
a date and no managed row can ever match an empty-valued predicate on it: adding either
`["is", "not set"]` or `["in", [None, ""]]` selects zero rows, which would make every
managed identity look new and then fail in `check_duplicates`. A future-dated legacy row
that some other path marks is caught instead by the duplicate-identity throw in
`PriceGroup._sync_item_prices`.
"""


def managed_item_price_filters(price_group: str, price_list: str) -> dict:
	"""Filters selecting ONLY the unscoped Item Price rows this Price Group manages.

	Scoped rows (customer, supplier, batch, end date, packing unit) are never managed
	even if some other path marked them, so every managed-row query must exclude them.
	See SCOPE_FIELDS for why `valid_from` cannot be one of those predicates.
	"""
	filters = {"price_list": price_list, OWNER_FIELD: price_group}
	for field in SCOPE_FIELDS:
		filters[field] = ["in", [None, 0]] if field == "packing_unit" else ["is", "not set"]
	return filters


@dataclass(frozen=True)
class ManagedState:
	price_list_name: str
	desired_profiles: tuple[str, ...]
	currently_owned_profiles: tuple[str, ...]
	all_profiles: tuple[str, ...]
	managed_item_prices: tuple[str, ...]
	outlet_profiles: MappingProxyType


def managed_price_list_name(price_group_name: str) -> str:
	return f"{MANAGED_PRICE_LIST_PREFIX}{price_group_name}"


def owner_filters(price_group: str) -> dict:
	"""Filter dict selecting rows this Price Group owns via OWNER_FIELD."""
	return {OWNER_FIELD: price_group}
