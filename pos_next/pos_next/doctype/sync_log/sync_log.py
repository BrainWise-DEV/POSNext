# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SyncLog(Document):
	"""Append-only log of sync operations."""

	@classmethod
	def record(cls, operation, status, duration_ms=0, records_touched=0, error=None, context=None):
		"""Write a log entry. Safe to call from anywhere."""
		import json
		doc = frappe.get_doc({
			"doctype": "Sync Log",
			"operation": operation,
			"status": status,
			"duration_ms": duration_ms,
			"records_touched": records_touched,
			"error": (error or "")[:500],
			"context": json.dumps(context) if context else None,
		})
		doc.insert(ignore_permissions=True)
		return doc
