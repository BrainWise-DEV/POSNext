# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncHistory(Document):
	"""Archived acknowledged Sync Outbox rows."""
	pass
