# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Sales Invoice — currently uses the base submittable behavior."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class SalesInvoiceAdapter(SubmittableAdapter):
	doctype = "Sales Invoice"


registry.register(SalesInvoiceAdapter)
