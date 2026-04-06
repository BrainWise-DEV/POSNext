# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Customer — bidirectional with mobile_no dedup."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, SKIP_ON_UPSERT, _set_sync_flags
from pos_next.sync import registry


class CustomerAdapter(BaseSyncAdapter):
	doctype = "Customer"

	def conflict_key(self, payload):
		return ("mobile_no",)

	def apply_incoming(self, payload, operation):
		"""Dedup by mobile_no before standard upsert."""
		if operation == "delete":
			return super().apply_incoming(payload, operation)

		payload = self.pre_apply_transform(payload)
		mobile_no = payload.get("mobile_no")
		name = payload.get("name")

		# Dedup: if local customer with same mobile_no exists, return it
		if mobile_no:
			existing = frappe.db.get_value("Customer", {"mobile_no": mobile_no}, "name")
			if existing and existing != name:
				return existing

		# Update existing by name
		if name and frappe.db.exists("Customer", name):
			doc = frappe.get_doc("Customer", name)
			for key, val in payload.items():
				if key not in SKIP_ON_UPSERT and not isinstance(val, list):
					doc.set(key, val)
			doc.db_update()
			return doc.name

		# Insert new — Customer uses autoname, don't force central's name
		payload.pop("name", None)
		doc = frappe.get_doc({"doctype": "Customer", **payload})
		_set_sync_flags(doc)
		doc.insert(ignore_permissions=True)
		return doc.name


registry.register(CustomerAdapter)
