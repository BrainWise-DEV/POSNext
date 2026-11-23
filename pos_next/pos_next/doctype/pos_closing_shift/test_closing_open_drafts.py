# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R2-18: the shift close lists the drafts still open on the shift, so the POS
warns the cashier before closing.

	PYTHONPATH=<worktree> bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.pos_next.doctype.pos_closing_shift.test_closing_open_drafts'}"
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import (
	get_open_shift_drafts,
	make_closing_shift_from_opening,
)

PREFIX = "_PNXT_G4_"


class TestClosingShiftOpenDrafts(FrappeTestCase):
	"""Read-only on shared records: an existing POS Profile is read, never saved, and
	the opening shift is the dict the close is built from (not inserted), so the
	test takes no lock other runs on the site may hold."""

	PERIOD_START = "2026-09-08 22:00:00"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		profile = frappe.db.get_value("POS Profile", {"disabled": 0}, ["name", "company"], as_dict=True)
		if not profile:
			raise unittest.SkipTest("no POS Profile on this site")
		cls.PROFILE = profile.name
		cls.COMPANY = profile.company

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _make_opening_shift(self, suffix="SHIFT"):
		return frappe._dict(
			{
				"doctype": "POS Opening Shift",
				"name": f"{PREFIX}{suffix}",
				"period_start_date": self.PERIOD_START,
				"posting_date": "2026-09-08",
				"company": self.COMPANY,
				"pos_profile": self.PROFILE,
				"user": frappe.session.user,
				"balance_details": [],
			}
		)

	def _draft(self, shift, suffix, printed=0, grand_total=50):
		"""A bare draft on the shift: only the fields the close reads."""
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.COMPANY,
				"customer": None,
				"customer_name": f"{PREFIX}Customer {suffix}",
				"posting_date": "2026-09-08",
				"pos_profile": self.PROFILE,
				"posa_pos_opening_shift": shift.name,
				"posa_is_printed": printed,
				"grand_total": grand_total,
				"rounded_total": grand_total,
			}
		)
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		doc.insert(set_name=f"{PREFIX}DRAFT-{suffix}")
		return doc

	def _closing_from(self, shift):
		return make_closing_shift_from_opening(json.dumps(shift, default=str))

	def test_lists_the_open_drafts_on_the_shift(self):
		shift = self._make_opening_shift()
		self._draft(shift, "1", grand_total=50)
		self._draft(shift, "2", grand_total=70)

		drafts = get_open_shift_drafts(shift.name)

		self.assertEqual([d.name for d in drafts], [f"{PREFIX}DRAFT-1", f"{PREFIX}DRAFT-2"])
		self.assertEqual(flt(drafts[1].grand_total), 70)
		self.assertEqual(drafts[0].customer_name, f"{PREFIX}Customer 1")

	def test_the_closing_data_carries_them_and_what_happens_to_them(self):
		shift = self._make_opening_shift()
		self._draft(shift, "1")

		closing = self._closing_from(shift)

		self.assertEqual([d["name"] for d in closing["open_drafts"]], [f"{PREFIX}DRAFT-1"])
		allow_delete = bool(frappe.db.get_value("POS Profile", self.PROFILE, "posa_allow_delete"))
		self.assertEqual(closing["open_drafts_deleted_on_close"], allow_delete)

	def test_no_open_drafts(self):
		shift = self._make_opening_shift()
		self.assertEqual(self._closing_from(shift)["open_drafts"], [])

	def test_printed_and_other_shift_drafts_are_not_listed(self):
		shift = self._make_opening_shift()
		self._draft(shift, "P", printed=1)  # submitted by the close itself (submit_printed_invoices)
		other = self._make_opening_shift("OTHER-SHIFT")
		self._draft(other, "OTHER")
		self.assertEqual(get_open_shift_drafts(shift.name), [])
		self.assertEqual([d.name for d in get_open_shift_drafts(other.name)], [f"{PREFIX}DRAFT-OTHER"])

	def test_only_the_close_is_an_http_endpoint(self):
		"""I2 (Ruling 150): the drafts helper is server-only (it reads without permission
		checks); make_closing_shift_from_opening keeps its whitelist."""
		self.assertNotIn(get_open_shift_drafts, frappe.whitelisted)
		self.assertIn(make_closing_shift_from_opening, frappe.whitelisted)
