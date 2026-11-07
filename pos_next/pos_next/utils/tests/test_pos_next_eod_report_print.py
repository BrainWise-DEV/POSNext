from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

import pos_next

TEMPLATE_PATH = os.path.join(
	os.path.dirname(pos_next.__file__),
	"pos_next",
	"print_format",
	"pos_next_eod_report",
	"pos_next_eod_report.json",
)

MALICIOUS_NAME = "<style>*{display:none}</style>"


def _load_template() -> str:
	with open(TEMPLATE_PATH) as f:
		return json.load(f)["html"]


def _closing_doc(**overrides):
	data = dict(
		name="POS-CLO-TEST-0001",
		company="Test Company",
		pos_profile="Test Profile",
		user="cashier@example.com",
		period_start_date="2026-01-01 08:00:00",
		period_end_date="2026-01-01 20:00:00",
		pos_transactions=None,
		total_quantity=None,
		net_total=None,
		grand_total=None,
		taxes=None,
		payment_reconciliation=None,
	)
	data.update(overrides)
	return SimpleNamespace(**data)


class TestPOSNextEODReportPrint(FrappeTestCase):
	def _render(self, doc, items):
		company = SimpleNamespace(company_name="Test <b>Co</b>", default_currency="USD")
		profile = SimpleNamespace(company_address=None)

		real_get_cached_doc = frappe.get_cached_doc
		fakes = {"Company": company, "POS Profile": profile}

		def fake_cached_doc(doctype, *args, **kwargs):
			if doctype in fakes:
				return fakes[doctype]
			return real_get_cached_doc(doctype, *args, **kwargs)

		real_get_value = frappe.db.get_value

		def fake_get_value(doctype, *args, **kwargs):
			if doctype in ("User", "Address"):
				return None
			return real_get_value(doctype, *args, **kwargs)

		# Plain functions (not MagicMock) so the sandboxed Jinja env allows calling them.
		with (
			patch.object(frappe, "get_cached_doc", new=fake_cached_doc),
			patch.object(frappe.db, "get_value", new=fake_get_value),
		):
			return frappe.render_template(_load_template(), {"doc": doc, "get_items_sold": lambda d: items})

	def test_renders_with_none_values_and_escapes_user_data(self):
		doc = _closing_doc(
			pos_transactions=[SimpleNamespace(sales_invoice="SINV-1")],
			taxes=[SimpleNamespace(account_head="VAT <i>x</i>", rate=None, amount=None)],
			payment_reconciliation=[
				SimpleNamespace(
					mode_of_payment="Cash <script>",
					opening_amount=None,
					expected_amount=None,
					closing_amount=None,
					difference=None,
				)
			],
		)
		items = [{"item_code": "ITEM-1", "item_name": MALICIOUS_NAME, "qty": 1.0, "amount": 10.0}]

		html = self._render(doc, items)

		self.assertNotIn(MALICIOUS_NAME, html)
		self.assertIn("&lt;style&gt;", html)
		self.assertIn("Test &lt;b&gt;Co&lt;/b&gt;", html)
		self.assertIn("VAT &lt;i&gt;x&lt;/i&gt;", html)
		self.assertIn("Cash &lt;script&gt;", html)
		self.assertIn("Total Qty", html)

	def test_empty_states(self):
		html = self._render(_closing_doc(), [])

		self.assertIn("No item rows found", html)
		self.assertIn("No tax rows found", html)
		self.assertIn("No payment rows found", html)
