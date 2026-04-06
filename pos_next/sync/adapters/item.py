# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item DocType — handles child tables and variant awareness."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import to_payload, strip_meta
from pos_next.sync import registry


class ItemAdapter(BaseSyncAdapter):
	doctype = "Item"

	def serialize(self, doc):
		"""Include child tables (barcodes, defaults, etc.)."""
		return to_payload(doc)

	def pre_apply_transform(self, payload):
		"""Strip meta fields and remove server-only keys from children."""
		cleaned = strip_meta(payload)
		# Strip meta from child table rows too
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned

	def apply_incoming(self, payload, operation):
		"""
		Upsert Item. Special handling:
		- Don't delete template items that have local variants referencing them.
		- On update, handle child table replacement carefully.
		"""
		name = payload.get("name")
		if not name:
			raise ValueError("Item payload missing 'name'")

		if operation == "delete":
			# Don't delete templates that have local variants
			if frappe.db.exists("Item", name):
				has_variants = frappe.db.get_value("Item", name, "has_variants")
				if has_variants:
					variant_count = frappe.db.count("Item", {"variant_of": name})
					if variant_count > 0:
						frappe.log_error(
							f"Skipping delete of template Item {name}: {variant_count} variants exist",
							"Sync Item Adapter",
						)
						return name
				frappe.delete_doc("Item", name, ignore_permissions=True, force=True)
			return name

		payload = self.pre_apply_transform(payload)

		from pos_next.sync.adapters.base import _set_sync_flags

		if frappe.db.exists("Item", name):
			doc = frappe.get_doc("Item", name)
			for key, val in payload.items():
				if not isinstance(val, list) and key not in ("doctype", "name"):
					doc.set(key, val)
			_set_sync_flags(doc)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Item", **payload})
			_set_sync_flags(doc)
			doc.insert(ignore_permissions=True)
		return doc.name


registry.register(ItemAdapter)
