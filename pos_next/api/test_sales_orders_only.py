# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Settings "Create Only Sales Order": the server makes no POS Sales Invoice
(H2 round 1, I-2). An online one is refused; one synced from offline is kept and
logged, never stranded.

	bench --site nexus.local execute pos_next.dev_tests.run \\
		--kwargs "{'module': 'pos_next.api.test_sales_orders_only'}"
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, nowdate

from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.api.test_return_safety import _ensure_pos_settings
from pos_next.test_promotions import ITEM_C, ITEM_PRICES, _cart_payload, _ctx, _line

PREFIX = "_PNXT_H2_"
REFUSAL = "Create Only Sales Order is on"
LOG_TITLE = "Sales Invoice synced under Create Only Sales Order"


class TestSalesOrdersOnly(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		cls.settings, _created = _ensure_pos_settings(cls.ctx.pos_profile)
		cls.saved = frappe.db.get_value("POS Settings", cls.settings, "create_only_sales_order")

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("POS Settings", cls.settings, "create_only_sales_order", cls.saved)
		frappe.db.delete("Error Log", {"error": ["like", f"%{PREFIX}%"]})
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.db.set_value("POS Settings", self.settings, "create_only_sales_order", 1)

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.set_value("POS Settings", self.settings, "create_only_sales_order", self.saved)
		frappe.db.delete("Error Log", {"error": ["like", f"%{PREFIX}%"]})
		frappe.db.commit()

	def _payload(self, **extra):
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C)])
		payload["payments"] = [
			{"mode_of_payment": self.ctx.mode_of_payment, "amount": flt(ITEM_PRICES[ITEM_C])}
		]
		payload.update(extra)
		return payload

	def _discard(self, name, offline_id, doctype="Sales Invoice"):
		if frappe.db.exists(doctype, name):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.delete("Offline Invoice Sync", {"offline_id": offline_id})
		frappe.db.commit()

	def test_online_draft_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, REFUSAL):
			update_invoice(json.dumps(self._payload()))

	def test_online_submit_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, REFUSAL):
			submit_invoice(invoice=json.dumps(self._payload()), data=json.dumps({}))

	def test_offline_sale_is_kept_and_logged(self):
		offline_id = f"{PREFIX}{frappe.generate_hash(length=10)}"
		result = submit_invoice(invoice=json.dumps(self._payload(offline_id=offline_id)), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"], offline_id)
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		logs = frappe.get_all(
			"Error Log",
			filters={"method": LOG_TITLE},
			fields=["error"],
			order_by="creation desc",
		)
		self.assertTrue(any(offline_id in (log.error or "") for log in logs))

	def test_offline_order_syncs_as_a_sales_order(self):
		offline_id = f"{PREFIX}{frappe.generate_hash(length=10)}"
		payload = self._payload(offline_id=offline_id, doctype="Sales Order", delivery_date=nowdate())
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"], offline_id, "Sales Order")
		self.assertEqual(frappe.db.get_value("Sales Order", result["name"], "docstatus"), 1)

	def test_setting_off_sells_as_before(self):
		frappe.db.set_value("POS Settings", self.settings, "create_only_sales_order", 0)
		draft = update_invoice(json.dumps(self._payload()))
		self.assertTrue(draft["name"])
