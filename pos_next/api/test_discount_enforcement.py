# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The server enforces price edits and the maximum discount (Task 8k, Ruling 87).

A paid row below its server list price must be explained by an offer the server
applies, by F&F / a line coupon left to promotions, or by a manual edit the POS
Settings permit (discount fields → Allow Item Discount, the rest → Allow User To
Edit Rate, the sum capped by Max Discount Percentage Allowed). Client flags never
decide. Online: refused; offline sync or a rate a paid draft already held: logged.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_discount_enforcement'}"
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.api.test_ff_markers import enable_ff
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_TEST_DISC_"
CUSTOMER = f"{PREFIX}CUSTOMER"
EMAIL_DOMAIN = "discenforce.example"
ITEM_NO_PRICE = f"{PREFIX}ITEM_NO_PRICE"
FNF = invoices.FNF_DISCOUNT_SOURCE
PRICE = ITEM_PRICES[ITEM_A]  # 50
RATE_EDIT_OFF = "rate editing is not allowed"
ITEM_DISCOUNT_OFF = "item discounts are not allowed"
OVER_LIMIT = "maximum allowed discount"


class DiscountEnforcementCase(FrappeTestCase):
	"""Fixtures and helpers shared with the header-discount tests (no tests of its own)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		cls.ctx = _ctx()
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
		if not frappe.db.exists("Item", ITEM_NO_PRICE):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM_NO_PRICE,
					"item_name": ITEM_NO_PRICE,
					"item_group": frappe.db.get_value("Item", ITEM_A, "item_group"),
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		# Defaults of pos_settings.json, whatever the site has.
		self._pos_settings(
			allow_user_to_edit_item_discount=1, allow_user_to_edit_rate=0, max_discount_allowed=0
		)

	# ---- helpers -----------------------------------------------------------

	def _pos_settings(self, **values):
		name = frappe.db.get_value("POS Settings", {"pos_profile": self.ctx.pos_profile}, "name")
		if not name:
			self.skipTest("No POS Settings for the test POS Profile")
		old = frappe.db.get_value("POS Settings", name, list(values), as_dict=True)
		frappe.db.set_value("POS Settings", name, values)
		self.addCleanup(frappe.db.set_value, "POS Settings", name, old)

	def _payload(self, rate, discount_percentage=0, item=ITEM_A, **row):
		line = _line(self.ctx, item, price_list_rate=row.pop("price_list_rate", None))
		line.update(
			{
				"rate": rate,
				"discount_percentage": discount_percentage,
				"discount_amount": flt(flt(line["price_list_rate"]) - rate, 2) if discount_percentage else 0,
				**row,
			}
		)
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = CUSTOMER
		return payload

	def _draft(self, payload):
		draft = update_invoice(json.dumps(payload))
		self.addCleanup(
			frappe.delete_doc, "Sales Invoice", draft["name"], force=True, ignore_permissions=True
		)
		return frappe.get_doc("Sales Invoice", draft["name"])

	def _submit(self, payload, offline=False):
		paid = sum(flt(row["rate"]) * flt(row["qty"]) for row in payload["items"])
		payload = dict(payload, payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": paid}])
		if offline:
			payload["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", result["name"])

	def assertRefused(self, payload, text):
		with self.assertRaises(frappe.ValidationError) as caught:
			update_invoice(json.dumps(payload))
		self.assertIn(text, str(caught.exception))
		return str(caught.exception)

	@staticmethod
	def _logs():
		return set(
			frappe.get_all(
				"Error Log", filters={"method": invoices.UNEXPLAINED_DISCOUNT_LOG_TITLE}, pluck="name"
			)
		)

	def _price_rule(self, percentage):
		name = _make_rule(
			f"{PREFIX}PRICE_{percentage}",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=percentage,
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name


class TestDiscountEnforcement(DiscountEnforcementCase):
	# ---- manual edits -------------------------------------------------------

	def test_unflagged_low_rate_refused(self):
		"""0.01 with no flag and no discount fields: refused, and the refusal is logged."""
		self._pos_settings(allow_user_to_edit_rate=1, max_discount_allowed=20)
		with patch("frappe.deferred_insert.deferred_insert") as deferred:
			message = self.assertRefused(self._payload(0.01), OVER_LIMIT)
		for text in ("Row 1", ITEM_A, "50.0", "0.01", "20.0%"):
			self.assertIn(text, message)
		self.assertEqual(deferred.call_args.kwargs["doctype"], "Error Log")
		self.assertEqual(
			deferred.call_args.kwargs["records"]["method"], invoices.UNEXPLAINED_DISCOUNT_LOG_TITLE
		)

	def test_manual_edit_within_limit_saved(self):
		"""Measured against the server's list price, not the client's original_rate."""
		self._pos_settings(allow_user_to_edit_rate=1, max_discount_allowed=20)
		payload = self._payload(45, is_rate_manually_edited=1, original_rate=1000)
		doc = self._draft(payload)
		self.assertEqual(flt(doc.items[0].rate), 45)

	def test_manual_edit_over_limit_refused(self):
		self._pos_settings(allow_user_to_edit_rate=1, max_discount_allowed=10)
		message = self.assertRefused(self._payload(40), OVER_LIMIT)
		self.assertIn("10.0%", message)

	def test_edit_rate_off_refused(self):
		"""A rate below list price with no discount fields needs rate editing."""
		self.assertRefused(self._payload(45), RATE_EDIT_OFF)

	def test_item_discount_off_refused(self):
		self._pos_settings(allow_user_to_edit_item_discount=0, allow_user_to_edit_rate=1)
		self.assertRefused(self._payload(45, discount_percentage=10), ITEM_DISCOUNT_OFF)

	def test_item_discount_within_limit_saved(self):
		self._pos_settings(max_discount_allowed=20)
		doc = self._draft(self._payload(45, discount_percentage=10))
		self.assertEqual(flt(doc.items[0].rate), 45)

	def test_item_discount_over_limit_refused(self):
		"""max_discount_allowed applies to discount-% edits too, not only rate edits."""
		self._pos_settings(max_discount_allowed=5)
		self.assertRefused(self._payload(45, discount_percentage=10), OVER_LIMIT)

	def test_no_item_price_measured_against_row_price(self):
		"""No Item Price: the row's price_list_rate is the measure, never an exemption."""
		self.assertRefused(self._payload(10, item=ITEM_NO_PRICE, price_list_rate=100), RATE_EDIT_OFF)

	# ---- offers, F&F, coupons -----------------------------------------------

	def test_offer_discount_saved(self):
		"""A server-applied 10% rule explains 10% even with both manual rights off."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		rule = self._price_rule(10)
		doc = self._draft(self._payload(45, discount_percentage=10, pricing_rules=rule))
		self.assertEqual(flt(doc.items[0].rate), 45)

	def test_offer_explains_only_its_own_discount(self):
		"""A 10% rule name on a 60% line: the other 50% is a manual discount."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		rule = self._price_rule(10)
		self.assertRefused(self._payload(20, discount_percentage=60, pricing_rules=rule), ITEM_DISCOUNT_OFF)

	def test_ff_line_left_to_promotions(self):
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		self._pos_settings(allow_user_to_edit_item_discount=0)
		evaluator = MagicMock()
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			doc = self._draft(self._payload(35, discount_percentage=30, posnext_discount_source=FNF))
		evaluator.assert_not_called()
		self.assertEqual(flt(doc.items[0].rate), 35)

	def test_ff_mark_without_promotions_explains_nothing(self):
		self._pos_settings(allow_user_to_edit_item_discount=0)
		payload = self._payload(35, discount_percentage=30, posnext_discount_source=FNF)
		with patch.object(invoices.frappe, "override_whitelisted_method", side_effect=lambda method: method):
			self.assertRefused(payload, ITEM_DISCOUNT_OFF)

	def test_ff_mark_cannot_lower_its_own_base(self):
		"""A forged price_list_rate does not shrink the F&F saving promotions measures (Ruling 88)."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		payload = self._payload(
			0.01, discount_percentage=30, price_list_rate=0.019, posnext_discount_source=FNF
		)
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		with self.assertRaises(frappe.ValidationError):
			update_invoice(json.dumps(payload))

	def test_saved_price_list_rate_is_the_servers(self):
		doc = self._draft(self._payload(45, discount_percentage=10, price_list_rate=1000))
		self.assertEqual((flt(doc.items[0].price_list_rate), flt(doc.items[0].rate)), (PRICE, 45))

	# ---- price-list currency (Ruling 102) -----------------------------------

	def _server_list_prices(self, payload):
		doc = frappe.get_doc(payload)
		item_data = invoices._ItemData()
		item_data.load(row.item_code for row in doc.items)
		return [invoices._list_prices(doc, doc.items, item_data)[id(row)] for row in doc.items]

	def test_cross_currency_price_list_raw(self):
		"""Ruling 102: a price list in another currency than the invoice is measured on the
		raw Item Price, the number the cart sells, whatever exchange rates the invoice has."""
		currency = frappe.db.get_value("Price List", self.ctx.price_list, "currency")
		if not currency or currency == self.ctx.currency:
			self.skipTest("The test price list is in the invoice currency")
		payload = self._payload(PRICE)
		payload.update(conversion_rate=1, plc_conversion_rate=1.5)
		self.assertEqual(self._server_list_prices(payload), [PRICE])
		doc = self._draft(dict(payload))
		self.assertEqual((flt(doc.items[0].price_list_rate), flt(doc.items[0].rate)), (PRICE, PRICE))
		# 40 is a rate edit against the raw 50, not against a converted list price.
		over = self._payload(40, price_list_rate=40)
		over.update(conversion_rate=1, plc_conversion_rate=1.5)
		self.assertIn(f"list price of {flt(PRICE)}", self.assertRefused(over, RATE_EDIT_OFF))

	def test_same_currency_unchanged(self):
		"""An invoice in the price list's own currency takes the Item Price as it is."""
		currency = frappe.db.get_value("Price List", self.ctx.price_list, "currency")
		payload = self._payload(PRICE)
		payload.update(currency=currency, conversion_rate=2, plc_conversion_rate=3)
		self.assertEqual(self._server_list_prices(payload), [PRICE])

	def _line_coupon(self, code, percentage=10):
		if not frappe.db.has_column("POS Coupon", "apply_scope"):
			self.skipTest("Line-level coupons are not installed")
		existing = frappe.db.get_value("POS Coupon", {"coupon_code": code}, "name")
		if existing:
			frappe.delete_doc("POS Coupon", existing, force=True, ignore_permissions=True)
		coupon = frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": code,
				"coupon_code": code,
				"coupon_type": "Promotional",
				"company": self.ctx.company,
				"discount_type": "Percentage",
				"discount_percentage": percentage,
				"apply_on": "Net Total",
				"apply_scope": "All Eligible Items",
				"maximum_use": 100,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		return code

	def _coupon_payload(self, rate, code, header=True, percentage=10):
		payload = self._payload(
			rate,
			discount_percentage=percentage,
			posnext_coupon_code=code,
			posnext_coupon_discount=flt(PRICE * percentage / 100, 2),
		)
		if header:
			payload["coupon_code"] = code
		return payload

	def test_coupon_line_saved_at_its_discount(self):
		self._pos_settings(allow_user_to_edit_item_discount=0)
		code = self._line_coupon(f"{PREFIX}C10")
		doc = self._draft(self._coupon_payload(45, code))
		self.assertEqual(flt(doc.items[0].rate), 45)

	def test_coupon_tag_does_not_explain_the_rate(self):
		"""A real 10% coupon on the invoice (row labelled 10%) explains 45, not a rate of 0.01."""
		code = self._line_coupon(f"{PREFIX}C10")
		self.assertRefused(self._coupon_payload(0.01, code), RATE_EDIT_OFF)

	def test_coupon_tag_without_the_invoice_coupon_explains_nothing(self):
		self._pos_settings(allow_user_to_edit_item_discount=0)
		code = self._line_coupon(f"{PREFIX}C10")
		with self.assertRaises(frappe.ValidationError):
			update_invoice(json.dumps(self._coupon_payload(45, code, header=False)))

	def test_sales_order_tag_explains_nothing(self):
		payload = self._payload(0.01, posnext_coupon_code="NO_SUCH_COUPON", posnext_discount_source=FNF)
		payload.update({"doctype": "Sales Order", "delivery_date": frappe.utils.nowdate()})
		self.assertRefused(payload, RATE_EDIT_OFF)

	def test_list_price_cart_no_evaluator_call(self):
		evaluator = MagicMock()
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			self._draft(self._payload(PRICE))
		evaluator.assert_not_called()

	# ---- offline / paid earlier / existing drafts ---------------------------

	def test_offline_logged_not_refused(self):
		before = self._logs()
		doc = self._submit(self._payload(0.01), offline=True)
		self.assertEqual((doc.docstatus, flt(doc.items[0].rate)), (1, 0.01))
		new_logs = self._logs() - before
		self.assertEqual(len(new_logs), 1)
		self.assertIn(ITEM_A, frappe.db.get_value("Error Log", new_logs.pop(), "error"))

	def test_paid_draft_keeps_only_rates_it_held(self):
		"""A paid draft (saved with rate editing on) is re-submitted after it was turned off."""
		self._pos_settings(allow_user_to_edit_rate=1)
		payload = self._payload(40)
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		draft = update_invoice(json.dumps(payload))
		self._pos_settings(allow_user_to_edit_rate=0)

		lower = dict(self._payload(30), name=draft["name"])
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(lower)
		self.assertIn(RATE_EDIT_OFF, str(caught.exception))

		before = self._logs()
		doc = self._submit(dict(self._payload(40), name=draft["name"]))
		self.assertEqual((doc.docstatus, flt(doc.items[0].rate)), (1, 40))
		self.assertEqual(len(self._logs() - before), 1)

	def test_paid_draft_rate_is_per_uom(self):
		"""A rate held for 1 Nos does not cover the same rate for a Box of 12."""
		item = frappe.get_doc("Item", ITEM_A)
		if not any(row.uom == "Box" for row in item.uoms):
			if not frappe.db.exists("UOM", "Box"):
				frappe.get_doc({"doctype": "UOM", "uom_name": "Box"}).insert(ignore_permissions=True)
			item.append("uoms", {"uom": "Box", "conversion_factor": 12})
			item.save(ignore_permissions=True)
			self.addCleanup(self._drop_uom, ITEM_A, "Box")
		self._pos_settings(allow_user_to_edit_rate=1)
		payload = self._payload(40)
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		draft = update_invoice(json.dumps(payload))
		self._pos_settings(allow_user_to_edit_rate=0)

		boxes = dict(self._payload(40, uom="Box", conversion_factor=12), name=draft["name"])
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(boxes)
		self.assertIn(RATE_EDIT_OFF, str(caught.exception))

	@staticmethod
	def _drop_uom(item_code, uom):
		item = frappe.get_doc("Item", item_code)
		item.uoms = [row for row in item.uoms if row.uom != uom]
		item.save(ignore_permissions=True)

	def test_existing_draft_submit_checked(self):
		"""submit_invoice's existing-draft path judges the rates it will store."""
		draft = self._draft(self._payload(PRICE))
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(dict(self._payload(0.01), name=draft.name))
		self.assertIn(RATE_EDIT_OFF, str(caught.exception))

	def test_existing_draft_zero_rate_after_totals_refused(self):
		draft = self._draft(self._payload(PRICE))
		payload = self._payload(5, price_list_rate=PRICE, margin_type="Amount", margin_rate_or_amount=-49.999)
		with patch.object(invoices, "CLIENT_ROW_MARGIN_FIELDS", ()):
			with self.assertRaises(frappe.ValidationError) as caught:
				self._submit(dict(payload, name=draft.name))
		self.assertIn("cannot be sold at zero price", str(caught.exception))

	def test_paid_row_factor_is_the_items(self):
		"""A paid row moves stock by the Item's UOM factor, not the client's."""
		doc = self._draft(self._payload(PRICE, conversion_factor=12))
		self.assertEqual((flt(doc.items[0].conversion_factor), flt(doc.items[0].stock_qty)), (1, 1))

	def test_return_skipped(self):
		evaluator = MagicMock()
		doc = frappe.get_doc(self._payload(0.01))
		doc.is_return = 1
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			invoices._check_paid_row_discounts(doc)
		evaluator.assert_not_called()

	# ---- pos_next's own evaluator (no promotions) ---------------------------

	def test_fallback_stacked_rules_clamped_at_100(self):
		"""Two 60% rules on one line stop at 100% and at the line's value."""
		rules = [self._price_rule(60), self._price_rule(61)]
		payload = self._payload(PRICE)
		payload["items"][0]["qty"] = 2
		with patch.object(
			invoices, "erpnext_apply_pricing_rule", return_value=[{"pricing_rules": ",".join(rules)}]
		):
			result = invoices.apply_offers(json.dumps(payload))
		(line,) = result["items"]
		self.assertEqual((flt(line["discount_percentage"]), flt(line["discount_amount"])), (100, 2 * PRICE))
