# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Adapter for submittable docs (Sales Invoice, Payment Entry, POS shifts).

Replication strategy: just call ERPNext's normal doc.insert() + doc.submit().
Central treats a branch-pushed invoice exactly as if a local user had created
it via the API — ERPNext runs validate, creates Stock Ledger Entries, posts
GL entries, updates Bin, the lot. The doc's `owner` is set to frappe.session.user
automatically, which is the branch's API user on central.

Side-effect: Stock Ledger Entry is no longer synced separately — central
generates its own SLE when it submits the Sales Invoice.
"""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync.exceptions import SyncValidationError


class SubmittableAdapter(BaseSyncAdapter):

	def validate_incoming(self, payload):
		if not payload.get("origin_branch"):
			raise SyncValidationError(
				f"{self.doctype} {payload.get('name')}: missing origin_branch"
			)

	def pre_apply_transform(self, payload):
		"""Strip server-generated/client-only meta from parent and child rows."""
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned

	def apply_incoming(self, payload, operation):
		name = payload.get("name")
		sync_uuid = payload.get("sync_uuid")
		if not name:
			raise ValueError(f"{self.doctype}: payload missing 'name' field")

		# Resolve the local row (if any) by sync_uuid — name lookup is unsafe
		# because branch and central may both use ACC-SINV-style series for
		# their own invoices (branch sites should use SINV-<BRANCH>- prefix).
		existing = (
			frappe.db.get_value(self.doctype, {"sync_uuid": sync_uuid}, "name")
			if sync_uuid else None
		)

		if operation == "delete":
			if existing:
				frappe.delete_doc(self.doctype, existing, ignore_permissions=True, force=True)
			return existing or name

		if operation == "cancel":
			if existing:
				doc = frappe.get_doc(self.doctype, existing)
				if doc.docstatus == 1:
					doc.cancel()
			return existing or name

		# Already synced — transactional docs are immutable post-submit. Skip.
		if existing:
			return existing

		payload = self.pre_apply_transform(payload)
		target_docstatus = payload.get("docstatus", 0)

		# Insert as draft, then submit if the source was submitted. Splitting
		# this from a single insert(docstatus=1) is intentional: it forces
		# Frappe to run the full submit lifecycle (validate → before_submit →
		# on_submit) which is what creates SLEs and GL entries.
		insert_payload = dict(payload)
		insert_payload["docstatus"] = 0
		doc = frappe.get_doc({"doctype": self.doctype, **insert_payload})
		doc.insert(ignore_permissions=True)

		if target_docstatus == 1:
			doc.submit()

		return doc.name
