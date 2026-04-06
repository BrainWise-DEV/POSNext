# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Generic adapter for simple master DocTypes that need no special logic."""

from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync import registry


GENERIC_MASTER_DOCTYPES = [
	"POS Profile",
	"Warehouse",
	"Mode of Payment",
	"Item Group",
	"UOM",
	"Price List",
	"Company",
	"Currency",
	"Branch",
	"Customer Group",
	"Sales Person",
	"Employee",
	"User",
	"Role Profile",
	"Sales Taxes and Charges Template",
	"Item Tax Template",
	"POS Settings",
	"Loyalty Program",
	"Item Barcode",
]


class GenericMasterAdapter(BaseSyncAdapter):
	"""
	Default adapter for masters that need only standard upsert-by-name.
	One class registered for many DocTypes.
	"""
	pass


# Register for all generic masters
for _dt in GENERIC_MASTER_DOCTYPES:
	_cls = type(f"GenericMasterAdapter_{_dt.replace(' ', '_')}", (GenericMasterAdapter,), {"doctype": _dt})
	registry.register(_cls)
