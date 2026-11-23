# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""One-time-per-customer offers are not applied again after redemption.

``One Time Customer Offer Usage`` is named ``{customer}:{pricing_rule}``;
``apply_offers`` looks it up by that name. Item-level and transaction-level
(header discount) rules are both gated, and both are recorded on submit.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_one_time_offers'}"
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now

from pos_next.api.invoices import apply_offers, submit_invoice, update_invoice
from pos_next.api.sales_invoice_hooks import record_one_time_offer_usage
from pos_next.test_promotions import (
	ITEM_C,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_customer_group,
	_resolve_territory,
)

CUSTOMER = "_PNXT_TEST_OT_CUSTOMER"
RULE_TITLE = "_PNXT_TEST_OneTime"
TXN_RULE_TITLE = "_PNXT_TEST_OneTimeTxn"
ALLOWED_TXN_RULE_TITLE = "_PNXT_TEST_TxnAllowed"


class TestOneTimeOffers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		# The POS Profile's default (walk-in) customer never gets one-time
		# offers, so use a named customer of its own.
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_group": _resolve_customer_group(),
					"territory": _resolve_territory(),
					"customer_type": "Individual",
				}
			).insert(ignore_permissions=True)
		cls.rule = _make_rule(
			RULE_TITLE,
			apply_on="Item Code",
			items=[{"item_code": ITEM_C}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=10,
			one_time_per_customer=1,
		)
		frappe.db.delete("One Time Customer Offer Usage", {"customer": CUSTOMER})
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete("One Time Customer Offer Usage", {"customer": CUSTOMER})
		for title in (RULE_TITLE, TXN_RULE_TITLE, ALLOWED_TXN_RULE_TITLE):
			for name in frappe.get_all("Pricing Rule", filters={"title": title}, pluck="name"):
				frappe.delete_doc("Pricing Rule", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.db.delete("One Time Customer Offer Usage", {"customer": CUSTOMER})

	def _discount(self):
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C)])
		payload["customer"] = CUSTOMER
		response = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps([self.rule]))
		return flt((response.get("items") or [{}])[0].get("discount_percentage"))

	def _txn_rule(self):
		# Disable the item rule so only the transaction rule is in play
		frappe.db.set_value("Pricing Rule", self.rule, "disable", 1)
		return _make_rule(
			TXN_RULE_TITLE,
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=5,
			apply_discount_on="Grand Total",
			one_time_per_customer=1,
		)

	def test_redeemed_one_time_offer_not_applied_again(self):
		# Not redeemed yet: the offer applies.
		self.assertEqual(self._discount(), 10)

		usage = frappe.get_doc(
			{
				"doctype": "One Time Customer Offer Usage",
				"customer": CUSTOMER,
				"pricing_rule": self.rule,
				"redemption_date": now(),
			}
		).insert(ignore_permissions=True)
		self.assertEqual(usage.name, f"{CUSTOMER}:{self.rule}")

		# Redeemed: the same customer does not get it again.
		self.assertEqual(self._discount(), 0)

	def test_redeemed_one_time_transaction_offer_not_applied_again(self):
		rule = self._txn_rule()
		self.addCleanup(frappe.db.set_value, "Pricing Rule", self.rule, "disable", 0)

		# Not redeemed: the header discount applies, and the sale records it.
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C, qty=2)])
		payload["customer"] = CUSTOMER
		response = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps([rule]))
		self.assertEqual(flt(response.get("additional_discount_percentage")), 5)
		self.assertEqual(flt(response.get("discount_amount")), 2)  # 5% of 40.00
		self.assertIn(rule, response.get("applied_pricing_rules") or [])

		# Like the POS (useInvoice.js): the header discount goes as an amount only.
		payload["discount_amount"] = flt(response.get("discount_amount"))
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 38}]
		draft = update_invoice(json.dumps(payload))
		self.assertEqual(json.loads(draft["pos_applied_one_time_rules"]), [rule])
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		sale = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(flt(sale.grand_total), 38)
		# posnext_promotions may be installed here; run pos_next's own recorder.
		with patch("pos_next.optional_apps.promotions_installed", return_value=False):
			record_one_time_offer_usage(sale)
		self.assertTrue(frappe.db.exists("One Time Customer Offer Usage", f"{CUSTOMER}:{rule}"))

		# Redeemed: no header discount for the same customer.
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C, qty=2)])
		payload["customer"] = CUSTOMER
		response = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps([rule]))
		self.assertEqual(flt(response.get("additional_discount_percentage")), 0)
		self.assertEqual(flt(response.get("discount_amount")), 0)
		self.assertNotIn(rule, response.get("applied_pricing_rules") or [])

	def test_one_time_transaction_offer_never_for_walk_in(self):
		rule = self._txn_rule()
		self.addCleanup(frappe.db.set_value, "Pricing Rule", self.rule, "disable", 0)
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C, qty=2)])  # profile default customer
		response = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps([rule]))
		self.assertEqual(flt(response.get("additional_discount_percentage")), 0)

	def test_allowed_percentage_rule_keeps_its_amount_when_one_time_rule_blocked(self):
		blocked = self._txn_rule()
		self.addCleanup(frappe.db.set_value, "Pricing Rule", self.rule, "disable", 0)
		allowed = _make_rule(
			ALLOWED_TXN_RULE_TITLE,
			apply_on="Transaction",
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=3,
			apply_discount_on="Grand Total",
		)
		self.addCleanup(frappe.db.set_value, "Pricing Rule", allowed, "disable", 1)
		frappe.get_doc(
			{
				"doctype": "One Time Customer Offer Usage",
				"customer": CUSTOMER,
				"pricing_rule": blocked,
				"redemption_date": now(),
			}
		).insert(ignore_permissions=True)

		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C, qty=2)])
		payload["customer"] = CUSTOMER
		response = apply_offers(invoice_data=json.dumps(payload), selected_offers=json.dumps([allowed]))
		self.assertEqual(flt(response.get("additional_discount_percentage")), 3)
		# The POS reads only the amount: 3% of 40.00
		self.assertEqual(flt(response.get("discount_amount")), 1.2)
