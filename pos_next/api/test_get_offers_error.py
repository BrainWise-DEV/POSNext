# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-01 review I-2: a server error is not an empty offer list.

The POS clears its offline offer cache when the server answers an empty list (D-R4-01).
get_offers caught every error and answered [] too, so one server-side blip wiped the
offline offers of every till that fetched during it. It now logs and raises: the till
keeps its cache, as for any failed request.

Run:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_get_offers_error'}"
"""

import unittest
from unittest.mock import patch

import frappe

from pos_next.api import offers

PREFIX = "_PNXT_I1_"


class TestGetOffersError(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.profile = frappe.db.get_value("POS Profile", {"ignore_pricing_rule": 0}, "name")
		if not self.profile:
			self.skipTest("no POS Profile that applies pricing rules")

	def tearDown(self):
		for name in frappe.get_all("Error Log", filters={"error": ["like", f"%{PREFIX}%"]}, pluck="name"):
			frappe.delete_doc("Error Log", name, force=True, ignore_permissions=True)

	def test_a_server_error_is_raised_not_answered_as_no_offers(self):
		boom = RuntimeError(f"{PREFIX} lock wait timeout")
		with (
			patch.object(offers, "_get_standalone_pricing_rule_offers", side_effect=boom),
			patch.object(offers.frappe, "log_error") as log_error,
		):
			with self.assertRaises(RuntimeError):
				offers.get_offers(self.profile)
		# Still logged under its title
		log_error.assert_called_once()
		self.assertEqual(log_error.call_args.args[1], "Offers API")

	def test_a_real_answer_is_still_a_list(self):
		self.assertIsInstance(offers.get_offers(self.profile), list)
