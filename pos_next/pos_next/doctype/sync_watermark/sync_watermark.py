# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncWatermark(Document):
	"""Per-DocType watermark for master pull cycles."""

	@classmethod
	def upsert(cls, doctype_name, last_modified, records_pulled=0):
		"""Insert or update the watermark row for a DocType."""
		existing = frappe.db.get_value("Sync Watermark", {"doctype_name": doctype_name}, "name")
		if existing:
			doc = frappe.get_doc("Sync Watermark", existing)
			doc.last_modified = last_modified
			doc.last_pulled_at = now_datetime()
			doc.records_pulled = records_pulled
			doc.save(ignore_permissions=True)
			return doc
		doc = frappe.get_doc({
			"doctype": "Sync Watermark",
			"doctype_name": doctype_name,
			"last_modified": last_modified,
			"last_pulled_at": now_datetime(),
			"records_pulled": records_pulled,
		})
		doc.insert(ignore_permissions=True)
		return doc

	@classmethod
	def get_for(cls, doctype_name):
		"""Fetch the watermark row for a DocType, or None."""
		name = frappe.db.get_value("Sync Watermark", {"doctype_name": doctype_name}, "name")
		return frappe.get_doc("Sync Watermark", name) if name else None
