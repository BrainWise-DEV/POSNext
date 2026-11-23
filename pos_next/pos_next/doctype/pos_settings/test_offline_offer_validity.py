# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-01 review M5: Offline Offer Validity is at least 1 hour.

The POS read 0 (or blank) as the 24-hour default, while an admin setting 0 could mean
"never apply offers offline" or "never expire". 0 is refused instead.

Run:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.pos_next.doctype.pos_settings.test_offline_offer_validity'}"
"""

import unittest

import frappe


class TestOfflineOfferValidity(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		name = frappe.db.get_value("POS Settings", {}, "name")
		if not name:
			self.skipTest("no POS Settings on this site")
		self.doc = frappe.get_doc("POS Settings", name)

	def test_zero_is_refused(self):
		self.doc.offline_offer_validity_hours = 0
		with self.assertRaises(frappe.ValidationError):
			self.doc.validate()

	def test_an_hour_or_more_is_accepted(self):
		for hours in (1, 24, 72):
			self.doc.offline_offer_validity_hours = hours
			self.doc.validate()
