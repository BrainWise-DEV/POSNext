# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OfflineExpenseSync(Document):
	"""Tracks offline POS expense sync to prevent duplicate Journal Entries."""

	def before_insert(self):
		if not self.synced_at:
			self.synced_at = frappe.utils.now_datetime()

	@staticmethod
	def create_sync_record(
		offline_id,
		journal_entry=None,
		pos_profile=None,
		pos_opening_shift=None,
		status="Synced",
	):
		if not offline_id:
			return None

		existing = frappe.db.get_value(
			"Offline Expense Sync",
			{"offline_id": offline_id},
			["name", "status"],
			as_dict=True,
		)

		if existing:
			if existing.status == "Pending" and status == "Synced" and journal_entry:
				sync_doc = frappe.get_doc("Offline Expense Sync", existing.name)
				sync_doc.journal_entry = journal_entry
				sync_doc.status = "Synced"
				sync_doc.synced_at = frappe.utils.now_datetime()
				sync_doc.flags.ignore_permissions = True
				sync_doc.save()
			return frappe.get_doc("Offline Expense Sync", existing.name)

		doc = frappe.get_doc(
			{
				"doctype": "Offline Expense Sync",
				"offline_id": offline_id,
				"journal_entry": journal_entry or "",
				"pos_profile": pos_profile,
				"pos_opening_shift": pos_opening_shift,
				"status": status,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	@staticmethod
	def is_synced(offline_id):
		if not offline_id:
			return {"synced": False, "journal_entry": None, "status": None}

		existing = frappe.db.get_value(
			"Offline Expense Sync",
			{"offline_id": offline_id},
			["name", "journal_entry", "status"],
			as_dict=True,
		)

		if existing:
			is_synced = existing.status == "Synced" and existing.journal_entry
			return {
				"synced": bool(is_synced),
				"journal_entry": existing.journal_entry if is_synced else None,
				"status": existing.status,
			}

		return {"synced": False, "journal_entry": None, "status": None}
