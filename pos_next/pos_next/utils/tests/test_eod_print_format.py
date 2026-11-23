"""D-R4-04: the "POS Next EOD Report" print format renders.

It read POS Profile `address`, a field POS Profile does not have (it has
`company_address`), so every render failed with SQL 1054 and the EOD report never printed.

Run:
	PYTHONPATH=<worktree> bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.pos_next.utils.tests.test_eod_print_format'}"
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

PRINT_FORMAT_JSON = (
	Path(__file__).resolve().parents[2] / "print_format" / "pos_next_eod_report" / "pos_next_eod_report.json"
)


def _render(doc):
	html = json.loads(PRINT_FORMAT_JSON.read_text())["html"]
	return frappe.render_template(html, {"doc": doc})


class TestEODPrintFormat(FrappeTestCase):
	def setUp(self):
		self.profile = frappe.db.get_value("POS Profile", {}, "name")
		if not self.profile:
			self.skipTest("no POS Profile on this site")

	def tearDown(self):
		# bench execute commits on return: nothing written here may outlive the test
		frappe.db.rollback()

	def _doc(self):
		return frappe._dict(
			pos_profile=self.profile,
			company="_PNXT_I1_ Co",
			user="Administrator",
			taxes=[],
			payment_reconciliation=[],
			pos_transactions=[],
		)

	def test_renders_without_a_company_address(self):
		frappe.db.set_value("POS Profile", self.profile, "company_address", None, update_modified=False)
		out = _render(self._doc())
		self.assertIn("END-OF-DAY REPORT", out)

	def test_shows_the_profile_company_address(self):
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "_PNXT_I1_ EOD",
				"address_type": "Billing",
				"address_line1": "_PNXT_I1_ 12 Nile St",
				"city": "_PNXT_I1_ Cairo",
				"country": frappe.db.get_value("Country", {}, "name"),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("POS Profile", self.profile, "company_address", address.name, update_modified=False)
		out = _render(self._doc())
		self.assertIn("_PNXT_I1_ 12 Nile St", out)
		self.assertIn("_PNXT_I1_ Cairo", out)
