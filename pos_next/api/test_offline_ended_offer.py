# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""D-R4-01: an offline sale priced by an offer that has since ended is kept and logged.

A till that cached its offer list keeps applying an offer offline after the offer was
disabled (or its validity ended). At sync the server does not take the row's rule name
as a reason: it logs the row under ``ENDED_OFFER_LOG_TITLE`` with the rule, the row and
the rate, and keeps the sale (offline policy: keep and log, never strand). Before, a
POS Profile that lets the cashier discount saved it silently as a manual discount
(UIT run 4, ACC-SINV-2026-00340).

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_offline_ended_offer'}"
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from pos_next.api import invoices
from pos_next.api.test_discount_enforcement import CUSTOMER, PRICE, DiscountEnforcementCase
from pos_next.test_promotions import ITEM_A, _make_rule

PREFIX = "_PNXT_I1_"


class TestOfflineEndedOffer(DiscountEnforcementCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._drop_logs)

	@staticmethod
	def _drop_logs():
		for name in frappe.get_all("Error Log", filters={"error": ["like", f"%{PREFIX}%"]}, pluck="name"):
			frappe.delete_doc("Error Log", name, force=True, ignore_permissions=True)

	def _rule(self, suffix, **fields):
		name = _make_rule(
			f"{PREFIX}HALF_{suffix}",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=50,
			applicable_for="Customer",
			customer=CUSTOMER,
			**fields,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def _offline_sale(self, rule):
		payload = self._payload(PRICE / 2, discount_percentage=50, pricing_rules=rule)
		return self._submit(payload, offline=True)

	@staticmethod
	def _ended_logs():
		return frappe.get_all(
			"Error Log",
			filters={"method": invoices.ENDED_OFFER_LOG_TITLE, "error": ["like", f"%{PREFIX}%"]},
			pluck="error",
		)

	def test_disabled_offer_kept_and_logged(self):
		rule = self._rule("DISABLED")
		frappe.db.set_value("Pricing Rule", rule, "disable", 1)
		doc = self._offline_sale(rule)
		self.assertEqual((doc.docstatus, flt(doc.items[0].rate)), (1, PRICE / 2))
		logs = self._ended_logs()
		self.assertEqual(len(logs), 1, logs)
		# "at sync": the rule may still have been live when the till sold (review M4)
		for text in (rule, "Row 1", ITEM_A, "25", "disabled at sync"):
			self.assertIn(text, logs[0])

	def test_expired_offer_kept_and_logged(self):
		rule = self._rule("EXPIRED", valid_from=add_days(nowdate(), -10), valid_upto=add_days(nowdate(), -1))
		doc = self._offline_sale(rule)
		self.assertEqual(doc.docstatus, 1)
		logs = self._ended_logs()
		self.assertEqual(len(logs), 1, logs)
		self.assertIn(rule, logs[0])
		self.assertIn("expired", logs[0])

	def test_live_offer_not_logged(self):
		rule = self._rule("LIVE")
		doc = self._offline_sale(rule)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(self._ended_logs(), [])
