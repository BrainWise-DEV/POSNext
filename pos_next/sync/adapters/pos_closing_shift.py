# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for POS Closing Shift — priority 20."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class POSClosingShiftAdapter(SubmittableAdapter):
	doctype = "POS Closing Shift"


registry.register(POSClosingShiftAdapter)
