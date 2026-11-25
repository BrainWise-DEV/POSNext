"""The shift payload carries what the POS needs to round the total as ERPNext does (D-5).

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_shift_profile_payload'}"
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api.shifts import _pos_profile_payload


class TestShiftProfilePayload(FrappeTestCase):
	def setUp(self):
		self.profile = frappe.db.get_value("POS Profile", {"disabled": 0}, ["name", "currency"], as_dict=True)
		if not self.profile:
			self.skipTest("no POS Profile on this site")

	def test_profile_fields_and_rounding_inputs(self):
		payload = _pos_profile_payload(self.profile.name)
		self.assertIsInstance(payload, dict)
		self.assertEqual(payload["name"], self.profile.name)
		self.assertIn("disable_rounded_total", payload)
		self.assertIn("company", payload)
		self.assertEqual(
			payload["smallest_currency_fraction_value"],
			flt(frappe.db.get_value("Currency", self.profile.currency, "smallest_currency_fraction_value")),
		)

	def test_fraction_follows_the_currency(self):
		frappe.db.set_value("Currency", self.profile.currency, "smallest_currency_fraction_value", 0.05)
		frappe.clear_cache(doctype="Currency")
		try:
			self.assertEqual(_pos_profile_payload(self.profile.name)["smallest_currency_fraction_value"], 0.05)
		finally:
			frappe.db.rollback()
			frappe.clear_cache(doctype="Currency")
