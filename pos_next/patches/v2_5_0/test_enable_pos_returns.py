# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The upgrade turns POS returns on for existing POS Settings (D-R3-10).

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.patches.v2_5_0.test_enable_pos_returns'}"
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api.test_return_safety import _ensure_pos_settings
from pos_next.patches.v2_5_0 import enable_pos_returns
from pos_next.test_promotions import _ctx


class TestEnablePosReturns(FrappeTestCase):
	def setUp(self):
		self.settings, _created = _ensure_pos_settings(_ctx().pos_profile)

	def tearDown(self):
		frappe.db.rollback()

	def test_a_row_at_0_ends_at_1(self):
		frappe.db.set_value("POS Settings", self.settings, "allow_return", 0)
		enable_pos_returns.execute()
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings, "allow_return"), 1)

	def test_running_it_again_changes_nothing(self):
		frappe.db.set_value("POS Settings", self.settings, "allow_return", 1)
		modified = frappe.db.get_value("POS Settings", self.settings, "modified")
		enable_pos_returns.execute()
		enable_pos_returns.execute()
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings, "allow_return"), 1)
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings, "modified"), modified)

	def test_new_rows_default_to_1(self):
		# The DocType JSON as shipped (the site's meta follows it on migrate)
		path = frappe.get_app_path("pos_next", "pos_next", "doctype", "pos_settings", "pos_settings.json")
		with open(path) as handle:
			fields = {field["fieldname"]: field for field in json.load(handle)["fields"]}
		self.assertEqual(fields["allow_return"].get("default"), "1")
