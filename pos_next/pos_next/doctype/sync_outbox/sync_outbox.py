# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


TERMINAL_OPERATIONS = {"submit", "cancel", "delete"}


class SyncOutbox(Document):
	"""Pending change event awaiting push to central."""

	@classmethod
	def enqueue(cls, reference_doctype, reference_name, operation, payload, priority=100):
		"""
		Add a change event to the outbox, compacting pending updates to the same record.

		For terminal operations (submit/cancel/delete), always insert.
		For insert/update, if a pending row already exists for this
		(reference_doctype, reference_name, operation), update its payload in place.

		Returns the created or updated Sync Outbox document.
		"""
		if operation not in TERMINAL_OPERATIONS:
			existing = frappe.db.get_value(
				"Sync Outbox",
				{
					"reference_doctype": reference_doctype,
					"reference_name": reference_name,
					"operation": operation,
					"sync_status": "pending",
				},
				"name",
			)
			if existing:
				doc = frappe.get_doc("Sync Outbox", existing)
				doc.payload = payload
				doc.priority = priority
				doc.save(ignore_permissions=True)
				return doc

		doc = frappe.get_doc({
			"doctype": "Sync Outbox",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"operation": operation,
			"payload": payload,
			"priority": priority,
			"sync_status": "pending",
			"attempts": 0,
		})
		doc.insert(ignore_permissions=True)
		return doc
