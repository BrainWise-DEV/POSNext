# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Stock Reconciliation — uses base submittable behavior."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class StockReconciliationAdapter(SubmittableAdapter):
	doctype = "Stock Reconciliation"


registry.register(StockReconciliationAdapter)
