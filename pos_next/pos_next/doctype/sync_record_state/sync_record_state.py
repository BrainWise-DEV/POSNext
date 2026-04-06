# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncRecordState(Document):
	"""Per-record sync tracking: hash + source + timestamp of last successful sync."""

	@classmethod
	def upsert(cls, reference_doctype, reference_name, payload_hash, source):
		"""Record that a record was just synced; store hash + source."""
		existing = frappe.db.get_value(
			"Sync Record State",
			{"reference_doctype": reference_doctype, "reference_name": reference_name},
			"name",
		)
		if existing:
			doc = frappe.get_doc("Sync Record State", existing)
			doc.last_synced_hash = payload_hash
			doc.last_synced_at = now_datetime()
			doc.last_synced_from = source
			doc.save(ignore_permissions=True)
			return doc
		doc = frappe.get_doc({
			"doctype": "Sync Record State",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"last_synced_hash": payload_hash,
			"last_synced_at": now_datetime(),
			"last_synced_from": source,
		})
		doc.insert(ignore_permissions=True)
		return doc

	@classmethod
	def get_hash(cls, reference_doctype, reference_name):
		"""Return the last-synced hash, or None."""
		return frappe.db.get_value(
			"Sync Record State",
			{"reference_doctype": reference_doctype, "reference_name": reference_name},
			"last_synced_hash",
		)
