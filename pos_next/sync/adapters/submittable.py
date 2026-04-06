# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Base adapter for submitted documents — docstatus-aware insert/cancel."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, SKIP_ON_UPSERT, _set_sync_flags


class SubmittableAdapter(BaseSyncAdapter):
	"""
	Adapter for DocTypes that use docstatus (submit/cancel workflow).

	On central, submitted docs are inserted as read-only replicas
	with docstatus already set — no doc.submit() is called.
	Cancel sets docstatus=2 via db_update — no doc.cancel() is called.
	"""

	def apply_incoming(self, payload, operation):
		name = payload.get("name")
		if not name:
			raise ValueError(f"{self.doctype}: payload missing 'name' field")

		if operation == "delete":
			if frappe.db.exists(self.doctype, name):
				frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
			return name

		if operation == "cancel":
			if frappe.db.exists(self.doctype, name):
				doc = frappe.get_doc(self.doctype, name)
				doc.docstatus = 2
				doc.db_update()
			return name

		payload = self.pre_apply_transform(payload)

		try:
			doc = frappe.get_doc(self.doctype, name)
			for key, val in payload.items():
				if key not in SKIP_ON_UPSERT and not isinstance(val, list):
					doc.set(key, val)
			doc.db_update()
		except frappe.DoesNotExistError:
			doc = frappe.get_doc({"doctype": self.doctype, **payload})
			_set_sync_flags(doc)
			doc.insert(ignore_permissions=True)
		return doc.name
