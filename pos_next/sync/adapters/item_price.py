# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item Price — uses composite conflict key."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, SKIP_ON_UPSERT, _set_sync_flags
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
		filters = {"item_code": payload.get("item_code"), "price_list": payload.get("price_list")}
		if payload.get("uom"):
			filters["uom"] = payload["uom"]

		existing = frappe.db.get_value("Item Price", filters, "name")
		if existing:
			doc = frappe.get_doc("Item Price", existing)
			for key, val in payload.items():
				if key not in SKIP_ON_UPSERT and not isinstance(val, list):
					doc.set(key, val)
			doc.db_update()
			return doc.name

		payload.pop("name", None)
		doc = frappe.get_doc({"doctype": "Item Price", **payload})
		_set_sync_flags(doc)
		doc.insert(ignore_permissions=True)
		return doc.name


registry.register(ItemPriceAdapter)
