# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.actions.sales_invoice — the two shipped actions
resolve on the right documents.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import gate, registry


class TestSalesInvoiceActions(FrappeTestCase):
	def test_return_against_invoice_selects_the_return_action(self):
		from pos_next.authorization.actions.sales_invoice import (
			ACTION_RETURN_WITHOUT_INVOICE,
			ACTION_SALES_INVOICE_RETURN,
		)

		doc = frappe._dict({"doctype": "Sales Invoice", "is_return": 1, "return_against": "SINV-1"})
		fired = [a.name for a in registry.for_doctype("Sales Invoice") if a.applies(doc)]
		self.assertEqual(fired, [ACTION_SALES_INVOICE_RETURN])

		doc = frappe._dict({"doctype": "Sales Invoice", "is_return": 1, "return_against": None})
		fired = [a.name for a in registry.for_doctype("Sales Invoice") if a.applies(doc)]
		self.assertEqual(fired, [ACTION_RETURN_WITHOUT_INVOICE])

	def test_ordinary_sale_fires_nothing(self):
		doc = frappe._dict({"doctype": "Sales Invoice", "is_return": 0})
		fired = [a.name for a in registry.for_doctype("Sales Invoice") if a.applies(doc)]
		self.assertEqual(fired, [])

	def test_context_amount_is_absolute(self):
		"""Return invoices carry a negative grand_total; bindings compare magnitudes."""
		doc = frappe._dict(
			{"doctype": "Sales Invoice", "is_return": 1, "grand_total": -1500, "pos_profile": "P"}
		)
		self.assertEqual(gate.context_from_doc(doc)["amount"], 1500)
