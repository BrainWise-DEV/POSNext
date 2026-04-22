# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Sales Invoice — naming series validation, child tables."""

import frappe
from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync.exceptions import SyncValidationError
from pos_next.sync import registry


class SalesInvoiceAdapter(SubmittableAdapter):
	doctype = "Sales Invoice"

	def validate_incoming(self, payload):
		if not payload.get("origin_branch"):
			raise SyncValidationError(
				f"Sales Invoice {payload.get('name')} missing origin_branch — "
				"cannot accept invoice with unknown source branch"
			)

	def pre_apply_transform(self, payload):
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned


registry.register(SalesInvoiceAdapter)
