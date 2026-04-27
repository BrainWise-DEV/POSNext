# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Purchase Receipt — uses base submittable behavior."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class PurchaseReceiptAdapter(SubmittableAdapter):
	doctype = "Purchase Receipt"


registry.register(PurchaseReceiptAdapter)
