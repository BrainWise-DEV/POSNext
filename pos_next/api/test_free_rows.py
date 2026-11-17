# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Free invoice rows must be backed by an offer (Task 8i).

Before save the server re-evaluates the paid rows' offers with the cart's evaluator
(promotions' ``apply_offers`` override when installed). Online, an unbacked or excess
free row refuses the save. Only the first sync of an offline sale (submit_invoice with
a new offline_id), and free qty a paid draft already held, are kept and logged. The
evaluator gets item group, brand and list price from the server, and free qty is
compared in stock units. A paid row charged 0 needs the POS Settings rate-edit rights.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_free_rows'}"
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, flt

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.api.test_ff_markers import enable_ff
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_B,
	ITEM_C,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_company,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_TEST_FREE_"
CUSTOMER = f"{PREFIX}CUSTOMER"
EMAIL_DOMAIN = "freerows.example"
GIFT_POOL_SCHEME = f"{PREFIX}GIFT_POOL"
FNF = "friends_and_family"
GIFT_POOL = "Gift Pool"  # promotions' Promotional Scheme promotion_type
GROUP = f"{PREFIX}GROUP"
G2 = f"{PREFIX}G2"
ITEM_G2 = f"{PREFIX}ITEM_G2"
NOT_BACKED = "not backed by an offer"
ZERO_PRICE = "cannot be sold at zero price"


class TestFreeRows(FrappeTestCase):
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
		# Scoped to this test's customer so no other sale picks the rule up.
		cls.gift = _make_rule(
			f"{PREFIX}GIFT",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_C,
			min_qty=1,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		for group in (GROUP, G2):
			if not frappe.db.exists("Item Group", group):
				frappe.get_doc(
					{
						"doctype": "Item Group",
						"item_group_name": group,
						"parent_item_group": "All Item Groups",
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM_G2):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM_G2,
					"item_name": ITEM_G2,
					"item_group": G2,
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("UOM", "Box"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Box"}).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")

	# ---- helpers -----------------------------------------------------------

	def _payload(self, paid=ITEM_B, free=ITEM_C, free_qty=1, free_rules=None):
		free_row = _line(self.ctx, free, qty=free_qty, price_list_rate=0)
		free_row.update({"is_free_item": 1, "pricing_rules": self.gift if free_rules is None else free_rules})
		payload = _cart_payload(self.ctx, [_line(self.ctx, paid), free_row])
		payload["customer"] = CUSTOMER
		return payload

	def _draft(self, payload):
		draft = update_invoice(json.dumps(payload))
		self.addCleanup(
			frappe.delete_doc, "Sales Invoice", draft["name"], force=True, ignore_permissions=True
		)
		return frappe.get_doc("Sales Invoice", draft["name"])

	def _rule(self, title, **fields):
		defaults = {
			"price_or_product_discount": "Product",
			"rate_or_discount": "Discount Percentage",
			"same_item": 0,
			"free_item": ITEM_C,
			"free_qty": 1,
			"free_item_uom": "Nos",
			"free_item_rate": 0,
			"applicable_for": "Customer",
			"customer": CUSTOMER,
		}
		name = _make_rule(f"{PREFIX}{title}", **{**defaults, **fields})
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	@staticmethod
	def _free_rows(doc):
		return [row for row in doc.items if cint(row.is_free_item)]

	@staticmethod
	def _logs(title=invoices.UNBACKED_FREE_ITEM_LOG_TITLE):
		return set(frappe.get_all("Error Log", filters={"method": title}, pluck="name"))

	def _payments(self, payload):
		paid = sum(
			flt(row["rate"]) * flt(row["qty"]) for row in payload["items"] if not row.get("is_free_item")
		)
		return [{"mode_of_payment": self.ctx.mode_of_payment, "amount": paid}]

	def _submit(self, payload, offline=False):
		payload = dict(payload, payments=self._payments(payload))
		if offline:
			payload["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", result["name"])

	def assertRefused(self, call, text=NOT_BACKED):
		with self.assertRaises(frappe.ValidationError) as caught:
			call()
		self.assertIn(text, str(caught.exception))
		return str(caught.exception)

	def _pos_settings(self, **values):
		name = frappe.db.get_value("POS Settings", {"pos_profile": self.ctx.pos_profile}, "name")
		if not name:
			self.skipTest("No POS Settings for the test POS Profile")
		old = frappe.db.get_value("POS Settings", name, list(values), as_dict=True)
		frappe.db.set_value("POS Settings", name, values)
		self.addCleanup(frappe.db.set_value, "POS Settings", name, old)

	def _zero_rate_payload(self):
		row = _line(self.ctx, ITEM_A)
		row.update({"rate": 0, "discount_percentage": 100, "discount_amount": ITEM_PRICES[ITEM_A]})
		payload = _cart_payload(self.ctx, [row])
		payload["customer"] = CUSTOMER
		return payload

	# ---- online -------------------------------------------------------------

	def test_forged_free_row_refused_online(self):
		# ITEM_A triggers no offer, so no gift is due.
		message = self.assertRefused(lambda: update_invoice(json.dumps(self._payload(paid=ITEM_A))))
		self.assertIn(ITEM_C, message)

	def test_excess_free_qty_refused(self):
		self.assertRefused(lambda: update_invoice(json.dumps(self._payload(free_qty=2))))

	def test_excess_split_over_two_rows_refused(self):
		payload = self._payload()
		payload["items"].append(dict(payload["items"][1]))
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def _pair_on_item_c(self):
		"""ITEM_C gets a Pair UOM (2 Nos); rolled back with the test class."""
		if not frappe.db.exists("UOM", "Pair"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Pair"}).insert(ignore_permissions=True)
		item = frappe.get_doc("Item", ITEM_C)
		if not any(row.uom == "Pair" for row in item.uoms):
			item.append("uoms", {"uom": "Pair", "conversion_factor": 2})
			item.save(ignore_permissions=True)

	def test_bigger_uom_gift_refused(self):
		"""1 Pair (2 Nos) for a 1 Nos gift: compared in stock units."""
		self._pair_on_item_c()
		payload = self._payload()
		payload["items"][1].update({"uom": "Pair", "conversion_factor": 2})
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def test_uom_not_on_item_refused(self):
		"""A free row in a UOM the Item does not define cannot be measured: refused."""
		payload = self._payload()
		payload["items"][1].update({"uom": "Box", "conversion_factor": 1})
		self.assertRefused(lambda: update_invoice(json.dumps(payload)), "Box")

	def test_free_row_factor_is_the_items(self):
		"""1 Pair sent with conversion_factor 500 moves 2 Nos (the Item's factor), not 500."""
		self._pair_on_item_c()
		self._rule("PAIR_GIFT", apply_on="Item Code", items=[{"item_code": ITEM_A}], min_qty=1, free_qty=2)
		payload = self._payload(paid=ITEM_A, free_rules="")
		payload["items"][1].update({"uom": "Pair", "conversion_factor": 500})
		doc = self._draft(payload)
		(free,) = self._free_rows(doc)
		self.assertEqual((flt(free.conversion_factor), flt(free.stock_qty)), (2, 2))

	def test_online_submit_with_payments_refused(self):
		"""Payments sent with an online submit were not taken earlier: still refused."""
		self.assertRefused(lambda: self._submit(self._payload(paid=ITEM_A)))

	def test_relabelled_item_group_cannot_unlock_gift(self):
		"""The paid row's item group comes from the Item, not the client (Gift Pool on G2)."""
		rule = self._gift_pool({G2: [ITEM_G2]})
		payload = self._payload(paid=ITEM_A, free=ITEM_G2, free_rules=rule)
		payload["items"][0].update({"item_group": G2, "brand": f"{PREFIX}BRAND"})
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def test_inflated_price_list_rate_cannot_unlock_min_amt_gift(self):
		self._rule(
			"MIN_AMT_GIFT", apply_on="Item Code", items=[{"item_code": ITEM_A}], min_qty=0, min_amt=500
		)
		payload = self._payload(paid=ITEM_A, free_rules="")
		payload["items"][0].update(
			{
				"price_list_rate": 1000,
				"rate": ITEM_PRICES[ITEM_A],
				"discount_percentage": 95,
				"discount_amount": 950,
			}
		)
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def test_blank_rule_name_restored(self):
		"""A real gift sent with a blank rule name gets the rule back (non-F&F customer)."""
		doc = self._draft(self._payload(free_rules=""))
		self.assertEqual([row.pricing_rules for row in self._free_rows(doc)], [self.gift])

	def test_forbidden_gift_refused_for_ff_customer(self):
		"""F&F on the trigger line and gifts not allowed with F&F: no offer backs the gift."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		payload = self._payload(free_rules="")
		price = ITEM_PRICES[ITEM_B]
		payload["items"][0].update(
			{
				"discount_percentage": 30,
				"discount_amount": flt(price * 0.3, 2),
				"rate": flt(price * 0.7, 2),
				"posnext_discount_source": FNF,
			}
		)
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def test_valid_gift_saved_unchanged(self):
		doc = self._draft(self._payload())
		(free,) = self._free_rows(doc)
		self.assertEqual((free.item_code, flt(free.qty), free.pricing_rules), (ITEM_C, 1, self.gift))

	def test_sales_order_forged_free_row_refused(self):
		payload = self._payload(paid=ITEM_A)
		payload.update({"doctype": "Sales Order", "delivery_date": frappe.utils.nowdate()})
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	# ---- Gift Pool ----------------------------------------------------------

	def _gift_pool(self, pools):
		if not frappe.db.exists("DocType", "POS Gift Pool Item") or not frappe.db.has_column(
			"Promotional Scheme", "promotion_type"
		):
			self.skipTest("Gift Pool is not installed")
		if frappe.db.exists("Promotional Scheme", GIFT_POOL_SCHEME):
			frappe.delete_doc("Promotional Scheme", GIFT_POOL_SCHEME, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": GIFT_POOL_SCHEME,
				"company": _resolve_company(),
				"apply_on": "Item Group",
				"selling": 1,
				"promotion_type": GIFT_POOL,
				"item_groups": [{"item_group": group} for group in pools],
				"applicable_for": "Customer",
				"customer": [{"customer": CUSTOMER}],
				"gift_pool_items": [
					{"item_group": group, "item_code": code, "free_qty": 1}
					for group, codes in pools.items()
					for code in codes
				],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			frappe.delete_doc, "Promotional Scheme", GIFT_POOL_SCHEME, force=True, ignore_permissions=True
		)
		return frappe.db.get_value(
			"Pricing Rule", {"promotional_scheme": GIFT_POOL_SCHEME, "disable": 0}, "name"
		)

	def test_gift_pool_choice_accepted(self):
		"""A Gift Pool gift may be any item of the granted pool, not only the evaluator's pick."""
		item_group = frappe.db.get_value("Item", ITEM_A, "item_group")
		pool = [
			code for code in (ITEM_B, ITEM_C) if frappe.db.get_value("Item", code, "item_group") == item_group
		]
		if len(pool) < 2:
			self.skipTest("Test items are not in one item group")
		rule = self._gift_pool({item_group: pool})

		# The evaluator grants the first pool item; the customer chose the second.
		doc = self._draft(self._payload(paid=ITEM_A, free=pool[1], free_rules=""))
		self.assertEqual(
			[(row.item_code, row.pricing_rules) for row in self._free_rows(doc)], [(pool[1], rule)]
		)

		self.assertRefused(
			lambda: update_invoice(
				json.dumps(self._payload(paid=ITEM_A, free=pool[1], free_qty=2, free_rules=rule))
			)
		)

	def test_gift_pool_other_pool_refused(self):
		"""A purchase in pool G1's group earns a G1 gift, never a G2 one."""
		item_group = frappe.db.get_value("Item", ITEM_A, "item_group")
		if frappe.db.get_value("Item", ITEM_B, "item_group") != item_group:
			self.skipTest("Test items are not in one item group")
		rule = self._gift_pool({item_group: [ITEM_B], G2: [ITEM_G2]})
		self.assertRefused(
			lambda: update_invoice(json.dumps(self._payload(paid=ITEM_A, free=ITEM_G2, free_rules=rule)))
		)

	# ---- zero price (Rulings 71/72: a zero-price row is a free row) ----------

	def _zero_price_gift_payload(self, **row):
		"""Paid ITEM_B (earns the ITEM_C gift) plus ITEM_C sent as a 'paid' row at zero price."""
		payload = self._payload()
		payload["items"][1] = dict(_line(self.ctx, ITEM_C), rate=1, discount_percentage=100, **row)
		return payload

	def test_zero_price_row_with_offer_saved_as_gift(self):
		doc = self._draft(self._zero_price_gift_payload())
		(free,) = self._free_rows(doc)
		self.assertEqual(
			(free.item_code, flt(free.rate), flt(free.discount_percentage), free.pricing_rules),
			(ITEM_C, 0, 0, self.gift),
		)

	def test_zero_price_row_without_offer_refused(self):
		"""A manual edit to 0 (no rule, no coupon) is told it cannot be sold at zero price."""
		self.assertRefused(lambda: update_invoice(json.dumps(self._zero_rate_payload())), ZERO_PRICE)

	def test_zero_price_refused_even_with_rate_edit(self):
		self._pos_settings(allow_user_to_edit_rate=1, max_discount_allowed=0)
		self.assertRefused(lambda: update_invoice(json.dumps(self._zero_rate_payload())), ZERO_PRICE)

	def test_full_price_rule_line_saved_as_free_item(self):
		"""A Price rule giving the line 100% off: saved as a free item with that rule's name."""
		name = _make_rule(
			f"{PREFIX}FULL100",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=100,
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		payload = self._zero_rate_payload()
		payload["items"][0]["pricing_rules"] = name
		doc = self._draft(payload)
		(row,) = doc.items
		self.assertEqual((cint(row.is_free_item), flt(row.rate), row.pricing_rules), (1, 0, name))

	def _coupon(self, code, percentage=100, **fields):
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
				"maximum_use": 100,
				**fields,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		return coupon

	def _coupon_line_payload(self, code, header=None):
		payload = self._zero_rate_payload()
		payload["items"][0].update(
			{"posnext_coupon_code": code, "posnext_coupon_discount": ITEM_PRICES[ITEM_A]}
		)
		if header is not None:
			payload["coupon_code"] = header
		return payload

	def test_full_coupon_line_saved_as_free_item(self):
		"""A coupon applied to the invoice that gives the line 100% off: saved as a free item."""
		code = f"{PREFIX}C100"
		self._coupon(code)
		doc = self._draft(self._coupon_line_payload(code, header=code.lower()))
		(row,) = doc.items
		self.assertEqual((cint(row.is_free_item), flt(row.rate), row.posnext_coupon_code), (1, 0, code))

	def test_coupon_line_without_the_invoice_coupon_refused(self):
		"""The line's coupon must be the invoice's coupon, so its usage is counted."""
		code = f"{PREFIX}C100"
		self._coupon(code)
		self.assertRefused(lambda: update_invoice(json.dumps(self._coupon_line_payload(code))))
		other = f"{PREFIX}C10"
		self._coupon(other, percentage=10)
		self.assertRefused(lambda: update_invoice(json.dumps(self._coupon_line_payload(code, header=other))))

	def test_single_use_coupon_line_cannot_be_reused(self):
		code = f"{PREFIX}C100ONCE"
		coupon = self._coupon(code, maximum_use=1)
		frappe.db.set_value("POS Coupon", coupon.name, "used", 1)
		with self.assertRaises(frappe.ValidationError):
			update_invoice(json.dumps(self._coupon_line_payload(code, header=code)))
		with self.assertRaises(frappe.ValidationError):
			update_invoice(json.dumps(self._coupon_line_payload(code)))

	def test_client_full_discount_without_source_refused(self):
		"""A 100% discount the client sent with no rule or coupon behind it."""
		payload = self._zero_rate_payload()
		payload["items"][0]["rate"] = 1
		self.assertRefused(lambda: update_invoice(json.dumps(payload)), ZERO_PRICE)

	def test_sub_precision_rate_refused(self):
		"""A rate that rounds to 0 at the field's precision is a zero price."""
		payload = self._zero_rate_payload()
		payload["items"][0].update({"rate": 0.004, "discount_percentage": 99.99})
		self.assertRefused(lambda: update_invoice(json.dumps(payload)), ZERO_PRICE)

	def test_zero_price_without_item_price_checked(self):
		"""An item with no Item Price on the price list is not exempt."""
		row = _line(self.ctx, ITEM_G2, price_list_rate=0)
		row.update({"rate": 0, "discount_percentage": 100})
		payload = _cart_payload(self.ctx, [row])
		payload["customer"] = CUSTOMER
		self.assertRefused(lambda: update_invoice(json.dumps(payload)), ZERO_PRICE)

	def test_offline_zero_price_kept_and_logged(self):
		before = self._logs()
		payload = self._zero_rate_payload()
		payload["items"][0]["rate"] = 1
		payload["items"].append(_line(self.ctx, ITEM_B))
		doc = self._submit(payload, offline=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual([row.item_code for row in self._free_rows(doc)], [ITEM_A])
		self.assertEqual(len(self._logs() - before), 1)

	# ---- a free row never earns its own gift (Ruling 83) ----------------------

	def _same_item_rule(self, min_qty=1):
		self._rule(
			"SAME_ITEM",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			same_item=1,
			free_item=None,
			min_qty=min_qty,
			free_qty=1,
		)

	def _only(self, *rows):
		payload = _cart_payload(self.ctx, list(rows))
		payload["customer"] = CUSTOMER
		return payload

	def test_zero_price_row_cannot_earn_its_own_same_item_gift(self):
		self._same_item_rule()
		row = dict(_line(self.ctx, ITEM_A), rate=1, discount_percentage=100)
		self.assertRefused(lambda: update_invoice(json.dumps(self._only(row))), ZERO_PRICE)

	def test_free_row_with_junk_coupon_cannot_earn_its_own_gift(self):
		self._same_item_rule()
		row = dict(_line(self.ctx, ITEM_A, price_list_rate=0), is_free_item=1, posnext_coupon_code="JUNK")
		self.assertRefused(lambda: update_invoice(json.dumps(self._only(row))))

	def test_zero_price_row_cannot_complete_buy_2_get_1(self):
		self._same_item_rule(min_qty=2)
		paid = _line(self.ctx, ITEM_A)
		zero = dict(_line(self.ctx, ITEM_A), rate=1, discount_percentage=100)
		self.assertRefused(lambda: update_invoice(json.dumps(self._only(paid, zero))), ZERO_PRICE)

	def test_free_row_with_price_rule_name_not_from_a_draft_refused(self):
		"""A row sent already free with a Price rule name was never confirmed: Product check only."""
		name = self._rule(
			"FULL100_PRICE",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Price",
			discount_percentage=100,
			free_item=None,
			free_qty=0,
		)
		row = dict(_line(self.ctx, ITEM_A, price_list_rate=0), is_free_item=1, pricing_rules=name)
		self.assertRefused(lambda: update_invoice(json.dumps(self._only(row))))

	def test_client_margin_cannot_zero_a_paid_row(self):
		row = dict(
			_line(self.ctx, ITEM_A),
			rate=5,
			price_list_rate=ITEM_PRICES[ITEM_A],
			margin_type="Amount",
			margin_rate_or_amount=-49.999,
		)
		try:
			doc = self._draft(self._only(row))
		except frappe.ValidationError as error:
			self.assertIn(ZERO_PRICE, str(error))
			return
		self.assertGreater(flt(doc.items[0].rate), 0)

	def test_zero_rate_after_totals_refused(self):
		"""Whatever ERPNext computes at 0 for a paid row is refused (margin fields let through)."""
		row = dict(
			_line(self.ctx, ITEM_A),
			rate=5,
			price_list_rate=ITEM_PRICES[ITEM_A],
			margin_type="Amount",
			margin_rate_or_amount=-49.999,
		)
		with patch.object(invoices, "CLIENT_ROW_MARGIN_FIELDS", ()):
			self.assertRefused(lambda: update_invoice(json.dumps(self._only(row))), ZERO_PRICE)

	# ---- offline / paid -----------------------------------------------------

	def test_offline_unbacked_logged_not_thrown(self):
		before = self._logs()
		doc = self._submit(self._payload(paid=ITEM_A), offline=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual([row.item_code for row in self._free_rows(doc)], [ITEM_C])
		new_logs = self._logs() - before
		self.assertEqual(len(new_logs), 1)
		message = frappe.db.get_value("Error Log", new_logs.pop(), "error")
		self.assertIn(ITEM_C, message)
		self.assertIn("1.0 sent", message)

	def test_offline_retry_after_failure_logged_not_refused(self):
		"""A failed offline sync retried after its offer ended is kept and logged (Ruling 68)."""
		payload = self._payload()
		payload["payments"] = self._payments(payload)
		payload["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		with patch.object(invoices, "_apply_pos_sales_team", side_effect=frappe.ValidationError("down")):
			with self.assertRaises(frappe.ValidationError):
				submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.assertEqual(
			frappe.db.get_value("Offline Invoice Sync", {"offline_id": payload["offline_id"]}, "status"),
			"Failed",
		)

		frappe.db.set_value("Pricing Rule", self.gift, "disable", 1)
		self.addCleanup(frappe.db.set_value, "Pricing Rule", self.gift, "disable", 0)
		before = self._logs()
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual([row.item_code for row in self._free_rows(doc)], [ITEM_C])
		self.assertEqual(len(self._logs() - before), 1)

	def test_offline_id_on_update_invoice_not_lenient(self):
		"""A client-sent offline_id on update_invoice is not an offline sync."""
		payload = self._payload(paid=ITEM_A)
		payload["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		self.assertRefused(lambda: update_invoice(json.dumps(payload)))

	def test_paid_draft_resubmit_only_keeps_stored_gift(self):
		"""A token payment on a draft does not open the door to new free rows."""
		payload = self._payload()
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		draft = update_invoice(json.dumps(payload))

		forged = self._payload()
		forged_row = dict(forged["items"][1], item_code=ITEM_A, pricing_rules="")
		forged.update({"name": draft["name"], "items": [*forged["items"], forged_row]})
		self.assertRefused(lambda: self._submit(forged))

		# The stored gift, no longer due (the paid row changed): kept and logged.
		before = self._logs()
		kept = self._payload(paid=ITEM_A)
		kept["name"] = draft["name"]
		doc = self._submit(kept)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual([row.item_code for row in self._free_rows(doc)], [ITEM_C])
		self.assertEqual(len(self._logs() - before), 1)

	# ---- evaluator ----------------------------------------------------------

	def test_evaluator_error_refused_online_kept_offline(self):
		def broken(*args, **kwargs):
			frappe.throw(_("Error applying offers"))

		with patch.object(invoices, "_offer_evaluator", return_value=broken):
			self.assertRefused(lambda: update_invoice(json.dumps(self._payload())))
			doc = self._submit(self._payload(), offline=True)
		self.assertEqual([row.item_code for row in self._free_rows(doc)], [ITEM_C])

	def test_no_free_rows_no_evaluator_call(self):
		evaluator = MagicMock()
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A)])
			payload["customer"] = CUSTOMER
			self._draft(payload)
		evaluator.assert_not_called()

	def test_return_skipped(self):
		evaluator = MagicMock()
		doc = frappe.get_doc(self._payload(paid=ITEM_A))
		doc.is_return = 1
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			invoices._check_free_rows_backed(doc)
		evaluator.assert_not_called()
