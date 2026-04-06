# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item Price — uses composite conflict key."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class ItemPriceAdapter(BaseSyncAdapter):
	doctype = "Item Price"

	def conflict_key(self, payload):
		"""Item Price identity is by item_code + price_list + uom."""
		return ("item_code", "price_list", "uom")

	def apply_incoming(self, payload, operation):
		"""Look up by composite key first. If found, update. If not, insert."""
		if operation == "delete":
			return super().apply_incoming(payload, operation)

		payload = self.pre_apply_transform(payload)
		cleaned = strip_meta(payload)

		# Look up by composite key
		filters = {
			"item_code": cleaned.get("item_code"),
			"price_list": cleaned.get("price_list"),
		}
		if cleaned.get("uom"):
			filters["uom"] = cleaned["uom"]

		from pos_next.sync.adapters.base import _set_sync_flags

		existing = frappe.db.get_value("Item Price", filters, "name")

		if existing:
			doc = frappe.get_doc("Item Price", existing)
			for key, val in cleaned.items():
				if key not in ("doctype", "name", "modified", "modified_by", "creation", "owner") and not isinstance(val, list):
					doc.set(key, val)
			doc.db_update()
			return doc.name
		else:
			cleaned.pop("name", None)
			doc = frappe.get_doc({"doctype": "Item Price", **cleaned})
			_set_sync_flags(doc)
			doc.insert(ignore_permissions=True)
			return doc.name


registry.register(ItemPriceAdapter)
