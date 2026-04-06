# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Customer — bidirectional with mobile_no dedup."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class CustomerAdapter(BaseSyncAdapter):
	doctype = "Customer"

	def conflict_key(self, payload):
		return ("mobile_no",)

	def apply_incoming(self, payload, operation):
		"""
		Dedup by mobile_no: if a local customer has the same mobile_no,
		return the existing name rather than creating a duplicate.
		"""
		if operation == "delete":
			return super().apply_incoming(payload, operation)

		payload = self.pre_apply_transform(payload)
		cleaned = strip_meta(payload)
		name = cleaned.get("name")
		mobile_no = cleaned.get("mobile_no")

		# Dedup: check if local customer with same mobile_no exists
		if mobile_no:
			existing = frappe.db.get_value(
				"Customer",
				{"mobile_no": mobile_no},
				"name",
			)
			if existing and existing != name:
				return existing

		# Standard upsert by name
		if name and frappe.db.exists("Customer", name):
			doc = frappe.get_doc("Customer", name)
			for key, val in cleaned.items():
				if key not in ("doctype", "name") and not isinstance(val, list):
					doc.set(key, val)
			doc.save(ignore_permissions=True)
			return doc.name
		else:
			# Customer uses autoname — don't force central's name
			cleaned.pop("name", None)
			doc = frappe.get_doc({"doctype": "Customer", **cleaned})
			doc.insert(ignore_permissions=True)
			return doc.name


registry.register(CustomerAdapter)
