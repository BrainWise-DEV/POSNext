# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Stock Ledger Entry — insert-only, no updates."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, _set_sync_flags
from pos_next.sync import registry


class StockLedgerEntryAdapter(BaseSyncAdapter):
	doctype = "Stock Ledger Entry"

	def apply_incoming(self, payload, operation):
		"""Insert-only: SLEs are never updated after creation."""
		name = payload.get("name")
		if not name:
			raise ValueError("SLE payload missing 'name'")

		if operation == "delete":
			if frappe.db.exists(self.doctype, name):
				frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
			return name

		# Skip if already exists (insert-only)
		if frappe.db.exists(self.doctype, name):
			return name

		payload = self.pre_apply_transform(payload)
		doc = frappe.get_doc({"doctype": self.doctype, **payload})
		_set_sync_flags(doc)
		doc.insert(ignore_permissions=True)
		return doc.name


registry.register(StockLedgerEntryAdapter)
