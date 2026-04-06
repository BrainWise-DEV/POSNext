# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncDeadLetter(Document):
	"""Outbox rows that exceeded max retries; awaiting human handling."""
	pass
