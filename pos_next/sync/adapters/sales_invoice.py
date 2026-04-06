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
		origin_branch = payload.get("origin_branch")
		if not origin_branch:
			frappe.log_error(
				f"Sales Invoice {payload.get('name')} missing origin_branch",
				"Sync Sales Invoice Adapter",
			)
			return

		# Naming series must contain the branch code (e.g. SINV-CAI-.#####)
		name = payload.get("name", "")
		naming_series = payload.get("naming_series", "")
		if naming_series and origin_branch not in naming_series:
			raise SyncValidationError(
				f"Sales Invoice {name}: naming series '{naming_series}' "
				f"does not contain origin branch code '{origin_branch}'"
			)

	def pre_apply_transform(self, payload):
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned


registry.register(SalesInvoiceAdapter)
