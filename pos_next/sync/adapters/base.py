# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Base class for per-DocType sync adapters."""

import frappe
from pos_next.sync.payload import to_payload


class BaseSyncAdapter:
	"""
	Subclass per synced DocType. Override methods as needed.

	Each subclass MUST set the class attribute `doctype`.
	"""
	doctype: str = ""

	def serialize(self, doc):
		"""Build a sync payload dict from a Frappe Document."""
		return to_payload(doc)

	def apply_incoming(self, payload, operation):
		"""
		Apply an incoming payload locally. Default implementation:
		- delete operation → delete local record if exists
		- insert/update/submit/cancel → upsert

		Returns the local document name.
		"""
		name = payload.get("name")
		if not name:
			raise ValueError(f"{self.doctype}: payload missing 'name' field")

		if operation == "delete":
			if frappe.db.exists(self.doctype, name):
				frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
			return name

		payload = self.pre_apply_transform(payload)

		if frappe.db.exists(self.doctype, name):
			doc = frappe.get_doc(self.doctype, name)
			doc.update(payload)
			_set_sync_flags(doc)
			doc.save(ignore_permissions=True)
		else:
			payload_with_doctype = {"doctype": self.doctype, **payload}
			doc = frappe.get_doc(payload_with_doctype)
			_set_sync_flags(doc)
			doc.insert(ignore_permissions=True)
		return doc.name

	def conflict_key(self, payload):
		"""Tuple of fieldnames that identify this record across sites."""
		return ("name",)

	def validate_incoming(self, payload):
		"""Raise on invalid payload. Default: accept everything."""
		return None

	def pre_apply_transform(self, payload):
		"""Transform payload before apply. Default: identity."""
		return payload


def _set_sync_flags(doc):
	"""Bypass validations for synced data — it was valid on the source site."""
	doc.flags.ignore_validate = True
	doc.flags.ignore_links = True
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_conflict = True
