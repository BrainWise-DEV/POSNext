# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Delivery Note — uses base submittable behavior."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class DeliveryNoteAdapter(SubmittableAdapter):
	doctype = "Delivery Note"


registry.register(DeliveryNoteAdapter)
