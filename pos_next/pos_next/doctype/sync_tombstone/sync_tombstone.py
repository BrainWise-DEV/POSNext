# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncTombstone(Document):
	"""Record that a master was deleted on central, so branches can replay the delete."""

	@classmethod
	def record(cls, reference_doctype, reference_name):
		"""Create a tombstone for a deleted record."""
		doc = frappe.get_doc({
			"doctype": "Sync Tombstone",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"deleted_at": now_datetime(),
		})
		doc.insert(ignore_permissions=True)
		return doc
