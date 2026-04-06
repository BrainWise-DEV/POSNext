# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Payment Entry."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class PaymentEntryAdapter(SubmittableAdapter):
	doctype = "Payment Entry"

	def pre_apply_transform(self, payload):
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned


registry.register(PaymentEntryAdapter)
