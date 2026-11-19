# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""A "Block submit" F&F cap refusal never follows payment (Task 8o, Ruling 101).

When the payment dialog opens, the POS saves the cart as an unpaid draft
(``update_invoice`` with no payments): promotions re-prices F&F to the customer's
remaining allowance and the response carries the server ``grand_total`` and the
F&F block. The POS then submits that draft with the payments in one
``submit_invoice`` request. If another invoice used the allowance in between,
"Block submit" refuses there, and nothing of that request is kept: the draft
stays unpaid, so no later re-save is a paid-draft re-save. "Allow and log" and
offline sales still submit and log the breach.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_payment_open_recheck'}"
"""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.api.test_ff_markers import enable_ff
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_C,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_TEST_PAYOPEN_"
FNF = invoices.FNF_DISCOUNT_SOURCE
FF_SETTINGS = "Friends and Family Settings"
PRICE = ITEM_PRICES[ITEM_A]  # 50; F&F 30% = 15 off a unit
FNF_RATE = 35
MONTHLY_CAP = 20
ALLOW = "Allow and log"
BLOCK = "Block submit"
CAP_MESSAGE = "exceeds the customer's remaining monthly allowance"


class TestPaymentOpenRecheck(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		options = (frappe.get_meta(FF_SETTINGS).get_field("on_cap_breach_at_submit").options or "").split(
			"\n"
		)
		if not {ALLOW, BLOCK} <= set(options):
			raise unittest.SkipTest("Friends and Family Settings has no Block submit policy")
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")
		# A fresh customer per test: the monthly allowance starts at the full cap.
		token = frappe.generate_hash(length=8).lower()
		self.customer = (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"{PREFIX}{token}",
					"customer_group": _resolve_customer_group(),
					"territory": _resolve_territory(),
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.domain = f"payopen{token}.example"

	# ---- helpers -----------------------------------------------------------

	def _enable(self, policy):
		enable_ff(
			self,
			self.customer,
			self.domain,
			max_discount_per_customer_month=MONTHLY_CAP,
			on_cap_breach_at_submit=policy,
		)

	def _cart(self, qty=1):
		line = _line(self.ctx, ITEM_A, qty=qty)
		line.update(
			{
				"rate": FNF_RATE,
				"discount_percentage": 30,
				"discount_amount": PRICE - FNF_RATE,
				"posnext_discount_source": FNF,
			}
		)
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		return payload

	def _payments(self, amount):
		return [{"mode_of_payment": self.ctx.mode_of_payment, "amount": amount}]

	def _open_check(self, payload):
		"""What the POS does when the payment dialog opens: an unpaid draft save."""
		result = update_invoice(json.dumps(dict(payload, payments=[])))
		self.addCleanup(self._discard, result["name"])
		return result

	def _discard(self, name):
		if not frappe.db.exists("Sales Invoice", name):
			return
		doc = frappe.get_doc("Sales Invoice", name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

	def _submit(self, payload, amount, name=None, offline=False):
		"""One submit_invoice request, paid ``amount``; ``name`` submits that stored draft.
		A refusal raises; submit_invoice itself rolls back to its savepoint."""
		invoice = dict(payload, payments=self._payments(amount))
		if name:
			invoice["name"] = name
		if offline:
			invoice["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		result = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"])
		return frappe.get_doc("Sales Invoice", result["name"])

	def _use_allowance(self):
		"""Another sale for the same customer uses 15 of the 20 allowance."""
		return self._submit(self._cart(), FNF_RATE)

	def _paid_draft_flags(self, save):
		"""``flags.pos_paid_draft`` as each Sales Invoice validate during ``save`` sees it."""
		from pos_next.overrides.sales_invoice import CustomSalesInvoice

		seen, validate = [], CustomSalesInvoice.validate

		def spy(doc):
			seen.append(doc.flags.get("pos_paid_draft"))
			return validate(doc)

		with patch.object(CustomSalesInvoice, "validate", spy):
			save()
		return seen

	def _pos_settings(self, **values):
		name = frappe.db.get_value("POS Settings", {"pos_profile": self.ctx.pos_profile}, "name")
		if not name:
			self.skipTest("No POS Settings for the test POS Profile")
		old = frappe.db.get_value("POS Settings", name, list(values), as_dict=True)
		frappe.db.set_value("POS Settings", name, values)
		self.addCleanup(frappe.db.set_value, "POS Settings", name, old)

	def _cap_logs(self, name):
		return frappe.get_all(
			"Friends and Family Log",
			filters={"reference_name": name, "cap_hit": ["is", "set"]},
			pluck="name",
		)

	# ---- tests -------------------------------------------------------------

	def test_payment_open_reprices_to_allowance(self):
		"""Two F&F units (30 off) against a 20 allowance: the unpaid draft save prices
		F&F down to 20 and returns that total with the per-line F&F result."""
		self._enable(BLOCK)
		result = self._open_check(self._cart(qty=2))

		self.assertAlmostEqual(flt(result["grand_total"]), 2 * PRICE - MONTHLY_CAP, places=2)
		block = result.get("friends_and_family")
		self.assertIsInstance(block, dict)
		self.assertTrue(block.get("eligible"))
		lines = block.get("items") or []
		self.assertEqual([line.get("idx") for line in lines], [0])
		self.assertTrue(lines[0].get("capped"))
		self.assertAlmostEqual(flt(lines[0].get("discount_amount")), MONTHLY_CAP, places=2)
		doc = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual(doc.docstatus, 0)
		self.assertFalse([row for row in doc.payments if flt(row.amount)])

	def test_block_submit_race_refuses_and_leaves_no_paid_draft(self):
		"""Allowance used by another invoice between the open-check and submit: under
		Block the submit is refused with the cap message, the draft keeps no payment,
		and a later re-save of it is no paid-draft re-save."""
		self._enable(BLOCK)
		cart = self._cart()
		draft = self._open_check(cart)
		self.assertAlmostEqual(flt(draft["grand_total"]), FNF_RATE, places=2)

		self._use_allowance()
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(cart, FNF_RATE, name=draft["name"])
		self.assertIn(CAP_MESSAGE, str(caught.exception))

		doc = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(doc.docstatus, 0)
		self.assertFalse([row for row in doc.payments if flt(row.amount)])
		self.assertEqual(flt(doc.paid_amount), 0)
		# What the paid-draft leniency is built from: nothing, for an unpaid draft.
		self.assertEqual(invoices._paid_draft_rates(doc), {})
		self.assertIsNone(invoices._paid_draft_header(doc))

		resave = dict(cart, name=draft["name"], payments=self._payments(FNF_RATE))
		flags = self._paid_draft_flags(lambda: self._try(resave))
		self.assertTrue(flags)
		self.assertNotIn(True, flags)

	def _try(self, payload):
		"""A re-save that may be refused (its F&F is over the allowance now)."""
		try:
			update_invoice(json.dumps(payload))
		except frappe.ValidationError:
			pass

	def test_allow_and_log_unchanged(self):
		"""The same race under "Allow and log": the sale submits and the breach is logged."""
		self._enable(ALLOW)
		cart = self._cart()
		draft = self._open_check(cart)
		self._use_allowance()

		doc = self._submit(cart, FNF_RATE, name=draft["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertTrue(self._cap_logs(doc.name))

	def test_offline_still_logs(self):
		"""An offline sale over the allowance under "Block submit" submits and is logged."""
		self._enable(BLOCK)
		self._use_allowance()

		doc = self._submit(self._cart(), FNF_RATE, offline=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertTrue(self._cap_logs(doc.name))

	def test_submit_of_checked_draft_saves_like_update_invoice(self):
		"""The POS submits the cart (not the stored draft) as the checked draft: the
		submit saves it as update_invoice does. A manual rate edit keeps its original
		rate as the list price, as on any update_invoice save."""
		self._pos_settings(allow_user_to_edit_rate=1, max_discount_allowed=20)
		line = _line(self.ctx, ITEM_A)
		line.update({"rate": 45, "price_list_rate": 45, "is_rate_manually_edited": 1, "original_rate": PRICE})
		cart = dict(_cart_payload(self.ctx, [line]), customer=self.customer)

		checked = self._open_check(cart)
		self.assertEqual(flt(checked["items"][0]["price_list_rate"]), PRICE)

		doc = self._submit(cart, 45, name=checked["name"])
		self.assertEqual(doc.name, checked["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(flt(doc.items[0].price_list_rate), PRICE)
		self.assertEqual(flt(doc.items[0].rate), 45)

	def test_submit_of_checked_draft_keeps_canonical_coupon_code(self):
		"""The cart sends the code as typed (upper-cased); the submitted invoice stores the
		coupon's own code, as update_invoice does."""
		code = f"{PREFIX}Cpn{frappe.generate_hash(length=6).lower()}"
		coupon = frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": code,
				"coupon_code": code,
				"coupon_type": "Promotional",
				"company": self.ctx.company,
				"discount_type": "Percentage",
				"discount_percentage": 10,
				"apply_on": "Grand Total",
				"maximum_use": 100,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		cart = dict(
			_cart_payload(self.ctx, [_line(self.ctx, ITEM_A)]),
			customer=self.customer,
			coupon_code=code.upper(),
			discount_amount=5,
		)

		checked = self._open_check(cart)
		self.assertEqual(checked["coupon_code"], code)

		doc = self._submit(cart, PRICE - 5, name=checked["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.coupon_code, code)

	# ---- fix round 1 (Ruling 110) --------------------------------------------

	def _one_time_rule(self):
		"""A one-time 10% rule on ITEM_C (20), only for this test's customer."""
		rule = _make_rule(
			f"{PREFIX}ONE_TIME",
			apply_on="Item Code",
			items=[{"item_code": ITEM_C}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=10,
			one_time_per_customer=1,
			applicable_for="Customer",
			customer=self.customer,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", rule, force=True, ignore_permissions=True)
		return rule

	def _item_c_cart(self, rule=None):
		price = ITEM_PRICES[ITEM_C]
		line = _line(self.ctx, ITEM_C)
		if rule:
			line.update(
				{
					"rate": price * 0.9,
					"discount_percentage": 10,
					"discount_amount": price * 0.1,
					"pricing_rules": rule,
				}
			)
		return dict(_cart_payload(self.ctx, [line]), customer=self.customer)

	def _usage(self, rule):
		return frappe.db.count(
			"One Time Customer Offer Usage", {"customer": self.customer, "pricing_rule": rule}
		)

	def _stamp(self, name):
		return json.loads(frappe.db.get_value("Sales Invoice", name, "pos_applied_one_time_rules") or "[]")

	def test_one_time_offer_stamped_on_checked_draft_submit(self):
		"""S1: the check saw a plain cart, the submit carries the one-time rule's row. The
		server stamps the rule on that submit; a second such sale for the customer is
		refused or does not re-apply the rule, and one usage row is left."""
		# No manual discounts: a discounted row must be backed by an offer the server applies.
		self._pos_settings(allow_user_to_edit_item_discount=0, allow_user_to_edit_rate=0)
		rule = self._one_time_rule()
		price = ITEM_PRICES[ITEM_C]

		draft = self._open_check(self._item_c_cart())
		doc = self._submit(self._item_c_cart(rule), price * 0.9, name=draft["name"])
		self.assertEqual(self._stamp(doc.name), [rule])
		self.assertEqual(self._usage(rule), 1)

		draft = self._open_check(self._item_c_cart())
		try:
			again = self._submit(self._item_c_cart(rule), price * 0.9, name=draft["name"])
		except frappe.ValidationError:
			again = None
		if again is not None:
			self.assertNotIn(rule, self._stamp(again.name))
		self.assertEqual(self._usage(rule), 1)

	def test_forged_one_time_stamp_ignored(self):
		"""B2: the client's pos_applied_one_time_rules is never stored, on any path."""
		rule = self._one_time_rule()
		price = ITEM_PRICES[ITEM_C]
		forged = dict(self._item_c_cart(), pos_applied_one_time_rules=json.dumps([rule]))

		draft = self._open_check(forged)
		self.assertEqual(self._stamp(draft["name"]), [])
		doc = self._submit(forged, price, name=draft["name"])
		self.assertEqual(self._stamp(doc.name), [])
		doc = self._submit(forged, price)
		self.assertEqual(self._stamp(doc.name), [])
		self.assertEqual(self._usage(rule), 0)

	def test_unknown_coupon_refused_at_submit(self):
		"""C2: submit refuses a coupon code that does not exist, as update_invoice does."""
		cart = dict(_cart_payload(self.ctx, [_line(self.ctx, ITEM_A)]), customer=self.customer)
		draft = self._open_check(cart)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(dict(cart, coupon_code="NO-SUCH-XYZ"), PRICE, name=draft["name"])
		self.assertIn("coupon code does not exist", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)

	def test_submit_of_adopted_check_not_refused(self):
		"""Probe A: the check drops an F&F customer's 1.00 coupon header. The POS adopts the
		server draft (no coupon, no header) and collects its total: that submit goes through."""
		self._enable(BLOCK)
		code = f"{PREFIX}AMT{frappe.generate_hash(length=6).upper()}"
		coupon = frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": code,
				"coupon_code": code,
				"coupon_type": "Promotional",
				"company": self.ctx.company,
				"discount_type": "Amount",
				"discount_amount": 1,
				"apply_on": "Grand Total",
				"maximum_use": 100,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		cart = dict(self._cart(), coupon_code=code, discount_amount=1)

		checked = self._open_check(cart)
		self.assertFalse(checked.get("coupon_code"))
		adopted = dict(
			cart, coupon_code=checked.get("coupon_code"), discount_amount=checked["discount_amount"]
		)
		doc = self._submit(adopted, flt(checked["grand_total"]), name=checked["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertAlmostEqual(flt(doc.grand_total), flt(checked["grand_total"]), places=2)
