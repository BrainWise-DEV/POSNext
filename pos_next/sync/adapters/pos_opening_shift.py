# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for POS Opening Shift — priority 10, synced first."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class POSOpeningShiftAdapter(SubmittableAdapter):
	doctype = "POS Opening Shift"


registry.register(POSOpeningShiftAdapter)
