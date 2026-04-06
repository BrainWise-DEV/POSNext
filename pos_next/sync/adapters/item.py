# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item DocType — variant-aware delete guard."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class ItemAdapter(BaseSyncAdapter):
	doctype = "Item"

	def pre_apply_transform(self, payload):
		"""Strip meta fields from children too."""
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned

	def apply_incoming(self, payload, operation):
		"""Don't delete template Items that have local variants."""
		if operation == "delete":
			name = payload.get("name")
			if name and frappe.db.exists("Item", name):
				has_variants = frappe.db.get_value("Item", name, "has_variants")
				if has_variants and frappe.db.count("Item", {"variant_of": name}) > 0:
					frappe.log_error(
						f"Skipping delete of template Item {name}: variants exist",
						"Sync Item Adapter",
					)
					return name
		return super().apply_incoming(payload, operation)


registry.register(ItemAdapter)
