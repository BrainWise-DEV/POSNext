# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Payment Entry — currently uses the base submittable behavior."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class PaymentEntryAdapter(SubmittableAdapter):
	doctype = "Payment Entry"


registry.register(PaymentEntryAdapter)
