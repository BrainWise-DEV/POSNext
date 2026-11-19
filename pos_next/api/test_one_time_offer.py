# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""A one-time-per-customer offer is redeemed once, never again by hand (Task 8p, Ruling 111).

The profile here allows item discounts with no maximum, so before 8p a second sale
could re-give a redeemed offer's discount as a "permitted manual discount". Now a
paid row that a one-time rule this customer already redeemed matches may carry no
unexplained discount at all, and the redemption is recorded at submit under the
usage row's (customer, rule) key, so two tabs cannot both redeem.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_one_time_offer'}"
"""

import json
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, nowdate

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.test_promotions import (
	ITEM_A,
	ITEM_B,
	ITEM_C,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_TEST_OT8P_"
USAGE = "One Time Customer Offer Usage"
ALREADY_USED = "was already used by this customer"


class TestOneTimeOffer(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")
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
		# Item discounts allowed with no maximum: the profile the hole was found on.
		self._pos_settings(
			allow_user_to_edit_item_discount=1, allow_user_to_edit_rate=0, max_discount_allowed=0
		)
		self.rule = self._one_time_rule(self.customer)
		self.title = frappe.db.get_value("Pricing Rule", self.rule, "title")
		# A refusal's Error Log is a deferred insert that outlives the test's rollback.
		deferred = patch("frappe.deferred_insert.deferred_insert")
		deferred.start()
		self.addCleanup(deferred.stop)

	# ---- helpers -----------------------------------------------------------

	def _pos_settings(self, **values):
		name = frappe.db.get_value("POS Settings", {"pos_profile": self.ctx.pos_profile}, "name")
		if not name:
			self.skipTest("No POS Settings for the test POS Profile")
		old = frappe.db.get_value("POS Settings", name, list(values), as_dict=True)
		frappe.db.set_value("POS Settings", name, values)
		self.addCleanup(frappe.db.set_value, "POS Settings", name, old)

	def _one_time_rule(self, customer):
		"""A one-time 10% rule on ITEM_C (20), only for ``customer``."""
		rule = _make_rule(
			f"{PREFIX}{customer}",
			apply_on="Item Code",
			items=[{"item_code": ITEM_C}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=10,
			one_time_per_customer=1,
			applicable_for="Customer",
			customer=customer,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", rule, force=True, ignore_permissions=True)
		self.addCleanup(frappe.db.delete, USAGE, {"pricing_rule": rule})
		return rule

	def _cart(self, item=ITEM_C, percentage=0, rule=None, customer=None, qty=1):
		price = ITEM_PRICES[item]
		line = _line(self.ctx, item, qty=qty)
		line.update(
			{
				"rate": price * (1 - percentage / 100),
				"discount_percentage": percentage,
				"discount_amount": price * percentage / 100,
				"pricing_rules": rule or "",
			}
		)
		return dict(_cart_payload(self.ctx, [line]), customer=customer or self.customer)

	@staticmethod
	def _total(payload):
		return sum(flt(row["rate"]) * flt(row["qty"]) for row in payload["items"])

	def _payments(self, amount):
		return [{"mode_of_payment": self.ctx.mode_of_payment, "amount": amount}]

	def _open_check(self, payload):
		"""The POS's unpaid draft save when the payment dialog opens."""
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
		if doc.docstatus != 2 or not frappe.get_all(
			"Sales Invoice", filters={"return_against": name, "docstatus": 1}, limit=1
		):
			frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

	def _submit(self, payload, name=None, offline=False, amount=None):
		total = self._total(payload) if amount is None else amount
		invoice = dict(payload, payments=self._payments(total))
		if name:
			invoice["name"] = name
		if offline:
			invoice["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		result = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"])
		return frappe.get_doc("Sales Invoice", result["name"])

	def _redeem(self):
		"""The customer's first sale with the offer."""
		return self._submit(self._cart(percentage=10, rule=self.rule))

	def _usage(self, customer=None):
		return frappe.get_all(
			USAGE,
			filters={"customer": customer or self.customer, "pricing_rule": self.rule},
			pluck="sales_invoice",
		)

	def _stamp(self, name):
		return json.loads(frappe.db.get_value("Sales Invoice", name, "pos_applied_one_time_rules") or "[]")

	def assertAlreadyUsed(self, save):
		with self.assertRaises(frappe.ValidationError) as caught:
			save()
		self.assertIn(ALREADY_USED, str(caught.exception))
		self.assertIn(self.title, str(caught.exception))

	@staticmethod
	def _logs():
		return set(
			frappe.get_all(
				"Error Log", filters={"method": invoices.UNEXPLAINED_DISCOUNT_LOG_TITLE}, pluck="name"
			)
		)

	# ---- tests -------------------------------------------------------------

	def test_first_redemption_ok_and_recorded(self):
		sale = self._redeem()
		self.assertEqual(sale.docstatus, 1)
		self.assertEqual(flt(sale.items[0].rate), ITEM_PRICES[ITEM_C] * 0.9)
		self.assertEqual(self._stamp(sale.name), [self.rule])
		self.assertEqual(self._usage(), [sale.name])

	def test_offer_applied_by_server_is_stamped_without_client_rule_name(self):
		"""The stamp is the server's: a row the offer explains is a redemption even when the
		client leaves the rule name off, so the offer cannot be taken twice that way."""
		sale = self._submit(self._cart(percentage=10))
		self.assertEqual(self._stamp(sale.name), [self.rule])
		self.assertEqual(self._usage(), [sale.name])

	def test_second_redemption_as_manual_discount_refused(self):
		self._redeem()
		again = self._cart(percentage=10)
		paid = dict(again, payments=self._payments(self._total(again)))
		self.assertAlreadyUsed(lambda: update_invoice(json.dumps(paid)))
		self.assertAlreadyUsed(lambda: self._submit(again))
		self.assertEqual(len(self._usage()), 1)

	def test_manual_discount_on_redeemed_offer_item_refused_any_size(self):
		self._redeem()
		for percentage in (1, 10, 50):
			with self.subTest(percentage=percentage):
				self.assertAlreadyUsed(lambda p=percentage: self._submit(self._cart(percentage=p)))
		# The rule's own name on the row changes nothing.
		self.assertAlreadyUsed(lambda: self._submit(self._cart(percentage=10, rule=self.rule)))
		# At list price the item still sells.
		self.assertEqual(self._submit(self._cart()).docstatus, 1)

	def test_two_tabs_second_submit_refused(self):
		"""Two drafts checked before either sale; both submit. When another device's sale
		takes the key between this submit's checks and its insert, the usage key alone
		refuses it; once a sale is in, the row check refuses the next. One usage row."""
		tab_a = self._open_check(self._cart(percentage=10, rule=self.rule))
		tab_b = self._open_check(self._cart(percentage=10, rule=self.rule))
		tab_c = self._open_check(self._cart(percentage=10, rule=self.rule))

		from pos_next.pos_next.doctype.one_time_customer_offer_usage import one_time_customer_offer_usage

		real_redeem = one_time_customer_offer_usage.redeem

		def other_device_first(customer, rule, sales_invoice):
			# Tab A's sale commits its usage row while tab C is being submitted.
			frappe.get_doc(
				{"doctype": USAGE, "customer": customer, "pricing_rule": rule, "sales_invoice": tab_a["name"]}
			).insert(ignore_permissions=True)
			return real_redeem(customer, rule, sales_invoice)

		with patch.object(one_time_customer_offer_usage, "redeem", side_effect=other_device_first):
			self.assertAlreadyUsed(
				lambda: self._submit(self._cart(percentage=10, rule=self.rule), name=tab_c["name"])
			)
		first = self._submit(self._cart(percentage=10, rule=self.rule), name=tab_a["name"])
		self.assertEqual(first.docstatus, 1)
		self.assertAlreadyUsed(
			lambda: self._submit(self._cart(percentage=10, rule=self.rule), name=tab_b["name"])
		)
		self.assertEqual(self._usage(), [first.name])
		for tab in (tab_b, tab_c):
			self.assertEqual(frappe.db.get_value("Sales Invoice", tab["name"], "docstatus"), 0)

	def test_offline_sync_second_redemption_logged(self):
		self._redeem()
		before = self._logs()
		sale = self._submit(self._cart(percentage=10, rule=self.rule), offline=True)
		self.assertEqual((sale.docstatus, flt(sale.items[0].rate)), (1, ITEM_PRICES[ITEM_C] * 0.9))
		errors = [frappe.db.get_value("Error Log", name, "error") for name in self._logs() - before]
		self.assertTrue(errors)
		self.assertTrue(all(ALREADY_USED in error and self.title in error for error in errors), errors)
		self.assertEqual(len(self._usage()), 1)

	def test_offline_sync_never_refused_when_check_fails(self):
		"""An offline sale is already made: a failing one-time check logs, never refuses."""
		self._redeem()
		before = self._logs()
		with (
			patch.object(invoices, "_used_one_time_offer_rows", side_effect=RuntimeError("boom")),
			patch.object(invoices, "_stamped_one_time_rules", side_effect=RuntimeError("boom")),
		):
			sale = self._submit(self._cart(percentage=10, rule=self.rule), offline=True)
		self.assertEqual(sale.docstatus, 1)
		errors = [frappe.db.get_value("Error Log", name, "error") for name in self._logs() - before]
		# The row check could not run; the offer, blocked for this customer, is not stamped.
		self.assertEqual(sum("could not be checked" in error for error in errors), 1, errors)
		self.assertEqual(self._stamp(sale.name), [])

	def test_walk_in_unchanged(self):
		"""The profile's default customer never redeems: a manual discount on the offer's
		item stays a permitted manual discount, every time, and nothing is recorded."""
		walk_in = self.ctx.customer
		rule = self._one_time_rule(walk_in)
		for _ in range(2):
			sale = self._submit(self._cart(percentage=10, customer=walk_in))
			self.assertEqual(sale.docstatus, 1)
			self.assertEqual(self._stamp(sale.name), [])
		self.assertFalse(frappe.get_all(USAGE, filters={"pricing_rule": rule}))

	def test_other_items_manual_discount_unchanged(self):
		self._redeem()
		sale = self._submit(self._cart(item=ITEM_A, percentage=10))
		self.assertEqual((sale.docstatus, flt(sale.items[0].rate)), (1, ITEM_PRICES[ITEM_A] * 0.9))

	def test_cancel_releases_per_existing_rule(self):
		"""Pinned: cancelling the redeeming sale deletes its usage row, so the customer may
		redeem again; a return against it releases nothing."""
		first = self._redeem()
		first.flags.ignore_permissions = True
		first.cancel()
		self.assertEqual(self._usage(), [])

		second = self._redeem()
		self.assertEqual(self._usage(), [second.name])

		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit_note = make_sales_return(second.name)
		credit_note.flags.ignore_permissions = True
		credit_note.insert()
		credit_note.submit()
		self.addCleanup(self._discard, credit_note.name)
		self.assertEqual(self._usage(), [second.name])

	# ---- fix round 1 (Ruling 113) -------------------------------------------

	def _rule(self, suffix, **fields):
		rule = _make_rule(
			f"{PREFIX}{suffix}_{self.customer}",
			one_time_per_customer=1,
			applicable_for="Customer",
			customer=self.customer,
			**fields,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", rule, force=True, ignore_permissions=True)
		self.addCleanup(frappe.db.delete, USAGE, {"pricing_rule": rule})
		return rule, frappe.db.get_value("Pricing Rule", rule, "title")

	def _header_cart(self, percentage, items=((ITEM_A, 2),)):
		lines = [_line(self.ctx, item, qty=qty) for item, qty in items]
		return dict(
			_cart_payload(self.ctx, lines),
			customer=self.customer,
			additional_discount_percentage=percentage,
			apply_discount_on="Grand Total",
		)

	def _header_rule(self):
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		return self._rule(
			"TXN",
			apply_on="Transaction",
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=10,
			apply_discount_on="Grand Total",
			min_amt=60,
		)

	def test_header_discount_on_cart_matching_redeemed_transaction_offer_refused(self):
		"""I1: a used one-time cart offer is not re-given as a manual header discount of any size."""
		rule, title = self._header_rule()
		first = self._submit(self._header_cart(10), amount=90)
		self.assertEqual(self._stamp(first.name), [rule])
		self.title = title
		for percentage in (9.99, 9, 10, 20):
			with self.subTest(percentage=percentage):
				self.assertAlreadyUsed(
					lambda p=percentage: self._submit(self._header_cart(p), amount=100 * (1 - p / 100))
				)
		paid = dict(self._header_cart(9), payments=self._payments(91))
		self.assertAlreadyUsed(lambda: update_invoice(json.dumps(paid)))
		# A cart the offer's conditions do not match (below its minimum amount) keeps the header.
		sale = self._submit(self._header_cart(10, items=((ITEM_C, 1),)), amount=18)
		self.assertEqual(sale.docstatus, 1)

	def _gift_rule(self):
		return self._rule(
			"GIFT",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Product",
			free_item=ITEM_C,
			free_qty=1,
			same_item=0,
		)

	def _free_row(self, rule=""):
		row = _line(self.ctx, ITEM_C)
		row.update(rate=0, price_list_rate=0, is_free_item=1, pricing_rules=rule)
		return row

	def test_gift_item_of_redeemed_offer_takes_no_manual_discount(self):
		"""I2: the gift of a used one-time offer, sold as a paid row, takes no manual discount."""
		# Only the gift rule is in play: ITEM_C's own one-time rule would explain the 99%.
		frappe.db.set_value("Pricing Rule", self.rule, "disable", 1)
		rule, title = self._gift_rule()
		cart = dict(_cart_payload(self.ctx, [_line(self.ctx, ITEM_A), self._free_row(rule)]))
		first = self._submit(dict(cart, customer=self.customer), amount=50)
		self.assertEqual(self._stamp(first.name), [rule])
		self.title = title
		for percentage in (99, 10):
			with self.subTest(percentage=percentage):
				lines = [_line(self.ctx, ITEM_A), self._cart(percentage=percentage)["items"][0]]
				again = dict(_cart_payload(self.ctx, lines), customer=self.customer)
				self.assertAlreadyUsed(lambda again=again: self._submit(again))

	def test_back_dated_sale_still_matches_redeemed_offer(self):
		"""I3: the offer is matched on the posting date or today, whichever makes it valid."""
		self._redeem()
		self.assertAlreadyUsed(
			lambda: self._submit(dict(self._cart(percentage=10), posting_date="2020-01-01"))
		)

	def test_missing_rule_lookup_refuses_online_logs_offline(self):
		"""I4: without ERPNext's rule lookup the check fails closed online, and logs offline."""
		self._redeem()
		with patch.object(invoices, "erpnext_get_item_pricing_rules", None, create=True):
			with self.assertRaises(frappe.ValidationError) as caught:
				self._submit(self._cart(percentage=10))
			self.assertIn("could not be checked", str(caught.exception))
			before = self._logs()
			sale = self._submit(self._cart(percentage=10), offline=True)
		self.assertEqual(sale.docstatus, 1)
		errors = [frappe.db.get_value("Error Log", name, "error") for name in self._logs() - before]
		self.assertTrue(any("could not be checked" in error for error in errors), errors)

	def _sales_order(self, payload):
		payload = dict(payload, doctype="Sales Order", delivery_date=nowdate(), payments=[])
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(self._discard_order, result["name"])
		return frappe.get_doc("Sales Order", result["name"])

	@staticmethod
	def _discard_order(name):
		if not frappe.db.exists("Sales Order", name):
			return
		order = frappe.get_doc("Sales Order", name)
		if order.docstatus == 1:
			order.flags.ignore_permissions = True
			order.cancel()
		frappe.delete_doc("Sales Order", name, force=True, ignore_permissions=True)

	def test_sales_order_never_applies_one_time_offer(self):
		"""I5: a Sales Order is never given a one-time offer; only a manual discount the
		profile permits, which redeems nothing."""
		cart = self._cart(percentage=10, rule=self.rule)
		evaluated = invoices.apply_offers(
			json.dumps(dict(self._cart(), doctype="Sales Order")), json.dumps([self.rule])
		)
		self.assertEqual(flt(evaluated["items"][0].get("discount_percentage")), 0)
		self._pos_settings(allow_user_to_edit_item_discount=0)
		with self.assertRaises(frappe.ValidationError):
			self._sales_order(cart)
		self.assertEqual(self._usage(), [])

	def test_sales_order_refused_after_redemption(self):
		self._redeem()
		self.assertAlreadyUsed(lambda: self._sales_order(self._cart(percentage=10)))

	def _desk_invoice(self, rate=None, discount=0, item_code=ITEM_C, **header):
		item = {"item_code": item_code, "qty": 1, "uom": "Nos", "warehouse": self.ctx.warehouse}
		if discount:
			item.update(discount_percentage=discount)
		if rate is not None:
			item.update(rate=rate, price_list_rate=ITEM_PRICES[item_code])
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"company": self.ctx.company,
				"selling_price_list": self.ctx.price_list,
				"currency": self.ctx.currency,
				"posting_date": nowdate(),
				"set_warehouse": self.ctx.warehouse,
				"update_stock": 0,
				"ignore_pricing_rule": 1,
				"items": [item],
				**header,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		self.addCleanup(self._discard, doc.name)
		return doc

	def test_desk_submit_of_stale_pos_draft_refused(self):
		"""I6a: a POS draft stamped before the offer was used elsewhere cannot be submitted in Desk."""
		draft = self._open_check(self._cart(percentage=10, rule=self.rule))
		self.assertEqual(self._stamp(draft["name"]), [self.rule])
		self._redeem()
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		doc.flags.ignore_permissions = True
		doc.set("payments", self._payments(18))
		invoices._set_payment_accounts(doc.payments, doc.company)
		doc.save()
		self.assertAlreadyUsed(doc.submit)
		self.assertEqual(len(self._usage()), 1)

	def test_desk_invoice_with_redeemed_offer_discount_refused(self):
		"""I6b: a Desk sale (any origin) is refused when a discounted row matches a used offer;
		at list price it submits; an offline-synced one is logged, not refused."""
		self._redeem()
		doc = self._desk_invoice(discount=10)
		self.assertLess(flt(doc.items[0].rate), ITEM_PRICES[ITEM_C])
		self.assertAlreadyUsed(doc.submit)

		# The row's own list price is the caller's: the server's measures it.
		forged = self._desk_invoice(discount=10)
		forged.items[0].price_list_rate = forged.items[0].rate
		forged.flags.ignore_validate_update_after_submit = True
		forged.items[0].db_update()
		forged.reload()
		self.assertEqual(flt(forged.items[0].price_list_rate), flt(forged.items[0].rate))
		self.assertAlreadyUsed(forged.submit)

		plain = self._desk_invoice()
		plain.submit()
		self.assertEqual(plain.docstatus, 1)

		synced = self._desk_invoice(discount=10)
		synced.flags.pos_offline_sync = True
		before = self._logs()
		synced.submit()
		self.assertEqual(synced.docstatus, 1)
		errors = [frappe.db.get_value("Error Log", name, "error") for name in self._logs() - before]
		self.assertTrue(any(ALREADY_USED in error for error in errors), errors)

	def _lock_wait(self):
		return patch(
			"pos_next.pos_next.doctype.one_time_customer_offer_usage.one_time_customer_offer_usage.redeem",
			side_effect=frappe.QueryTimeoutError("Lock wait timeout exceeded"),
		)

	def test_lock_wait_online_says_already_used(self):
		"""M1: another device holding the offer's key is "already used", not a raw DB error."""
		with self._lock_wait():
			self.assertAlreadyUsed(lambda: self._redeem())

	def test_lock_wait_offline_logged_and_unstamped(self):
		"""M1: an offline sync waiting on the key keeps the sale, logs, and leaves the rule off
		its stamp so no on_submit recorder waits on the key again."""
		before = self._logs()
		with self._lock_wait():
			sale = self._submit(self._cart(percentage=10, rule=self.rule), offline=True)
		self.assertEqual(sale.docstatus, 1)
		self.assertEqual(self._stamp(sale.name), [])
		self.assertEqual(self._usage(), [])
		errors = [frappe.db.get_value("Error Log", name, "error") for name in self._logs() - before]
		self.assertTrue(any(ALREADY_USED in error for error in errors), errors)

	def test_recorder_logs_lock_wait(self):
		"""M1: pos_next's on_submit recorder logs a lock wait instead of failing the submit."""
		from pos_next.api import sales_invoice_hooks

		doc = frappe._dict(
			doctype="Sales Invoice",
			name=f"{PREFIX}LOCKWAIT",
			customer=self.customer,
			is_return=0,
			pos_applied_one_time_rules=json.dumps([self.rule]),
		)
		before = set(
			frappe.get_all("Error Log", filters={"method": sales_invoice_hooks.USAGE_LOG_TITLE}, pluck="name")
		)
		from frappe.model.document import Document

		real_insert = Document.insert

		def insert_waits(self, *args, **kwargs):
			if self.doctype == USAGE:
				raise frappe.QueryTimeoutError("Lock wait timeout exceeded")
			return real_insert(self, *args, **kwargs)

		insert = patch.object(Document, "insert", autospec=True, side_effect=insert_waits)
		with patch("pos_next.optional_apps.promotions_installed", return_value=False), insert:
			sales_invoice_hooks.record_one_time_offer_usage(doc)
		after = set(
			frappe.get_all("Error Log", filters={"method": sales_invoice_hooks.USAGE_LOG_TITLE}, pluck="name")
		)
		self.assertEqual(len(after - before), 1)

	def test_client_rule_name_alone_never_stamps(self):
		"""M4: only rules the server's evaluation applied are stamped, never a client's name."""
		sale = self._submit(self._cart(rule=self.rule))
		self.assertEqual(self._stamp(sale.name), [])
		self.assertEqual(self._usage(), [])

	# ---- fix round 2 (Ruling 114) -------------------------------------------

	def test_desk_use_is_recorded_and_a_second_refused(self):
		"""(b) The first Desk sale with the offer is a redemption: it is recorded under the
		key, a second Desk sale is refused, and so is a POS sale after it."""
		first = self._desk_invoice(discount=10)
		first.submit()
		self.assertEqual(first.docstatus, 1)
		self.assertEqual(self._usage(), [first.name])
		self.assertEqual(self._stamp(first.name), [self.rule])

		self.assertAlreadyUsed(self._desk_invoice(discount=10).submit)
		self.assertAlreadyUsed(lambda: self._redeem())
		self.assertEqual(self._usage(), [first.name])

	def test_invoice_billed_from_sales_order_records_redemption(self):
		"""(b) A Sales Order gives no offer, but the invoice billed from it in Desk, carrying
		the discount on the offer's item, redeems it; a second such invoice is refused."""
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

		# Both orders are taken before any redemption; after one, an order is refused.
		orders = [self._sales_order(self._cart(percentage=10)) for _ in range(2)]

		def bill(order):
			self.assertEqual(order.docstatus, 1)
			invoice = make_sales_invoice(order.name)
			invoice.flags.ignore_permissions = True
			invoice.insert()
			self.addCleanup(self._discard, invoice.name)
			return invoice

		first = bill(orders[0])
		self.assertLess(flt(first.items[0].rate), ITEM_PRICES[ITEM_C])
		first.submit()
		self.assertEqual(self._usage(), [first.name])
		self.assertAlreadyUsed(bill(orders[1]).submit)

	def _printed_draft(self):
		draft = self._open_check(self._cart(percentage=10, rule=self.rule))
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		doc.flags.ignore_permissions = True
		doc.set("payments", self._payments(18))
		invoices._set_payment_accounts(doc.payments, doc.company)
		doc.save()
		return doc.name

	def test_closing_shift_names_the_refused_printed_invoice(self):
		"""(c) Closing a shift submits its printed drafts: one whose offer was used meanwhile is
		refused, the error names it, and nothing is skipped."""
		from pos_next.pos_next.doctype.pos_closing_shift import pos_closing_shift

		printed = self._printed_draft()
		self._redeem()
		real_get_all = frappe.get_all

		def shift_drafts(doctype, *args, **kwargs):
			filters = kwargs.get("filters") or {}
			if doctype == "Sales Invoice" and "posa_is_printed" in filters:
				# The shift's printed drafts (a real shift needs a POS Opening Shift).
				return [frappe._dict(name=printed)]
			return real_get_all(doctype, *args, **kwargs)

		with patch.object(pos_closing_shift.frappe, "get_all", side_effect=shift_drafts):
			with self.assertRaises(frappe.ValidationError) as caught:
				pos_closing_shift.submit_printed_invoices(f"{PREFIX}SHIFT", "Sales Invoice")
		self.assertIn(printed, str(caught.exception))
		self.assertIn(ALREADY_USED, str(caught.exception))
		self.assertEqual(frappe.db.get_value("Sales Invoice", printed, "docstatus"), 0)

	def test_redeem_waits_briefly_then_restores(self):
		"""(d) Another connection holding the key: redeem() gives up after the short lock
		wait, not the server's default, and leaves the session's own wait as it was."""
		import time

		import pymysql

		from pos_next.pos_next.doctype.one_time_customer_offer_usage import one_time_customer_offer_usage

		# A fresh transaction: earlier locking reads in this one hold gap locks on the
		# usage table that would block the other connection's insert.
		frappe.db.rollback()
		self.setUp()
		mine = self._open_check(self._cart())["name"]
		before = frappe.db.sql("select @@session.innodb_lock_wait_timeout")[0][0]
		other = pymysql.connect(
			host=frappe.conf.db_host or "127.0.0.1",
			port=int(frappe.conf.db_port or 3306),
			user=frappe.conf.db_user or frappe.conf.db_name,
			password=frappe.conf.db_password,
			database=frappe.conf.db_name,
			autocommit=False,
		)
		try:
			with other.cursor() as cursor:
				cursor.execute(
					"insert into `tabOne Time Customer Offer Usage` (name, customer, pricing_rule, sales_invoice) "
					"values (%s, %s, %s, %s)",
					(f"{self.customer}:{self.rule}", self.customer, self.rule, f"{PREFIX}OTHER"),
				)
			started = time.monotonic()
			with self.assertRaises(frappe.QueryTimeoutError):
				one_time_customer_offer_usage.redeem(self.customer, self.rule, mine)
			waited = time.monotonic() - started
		finally:
			other.rollback()
			other.close()
		self.assertLess(waited, one_time_customer_offer_usage.LOCK_WAIT_SECONDS + 5)
		self.assertGreaterEqual(waited, one_time_customer_offer_usage.LOCK_WAIT_SECONDS - 1)
		self.assertEqual(frappe.db.sql("select @@session.innodb_lock_wait_timeout")[0][0], before)

	# ---- fix round 3 (Ruling 116) -------------------------------------------

	def test_desk_debit_note_neither_redeems_nor_refused(self):
		"""N1: a debit note charges more; it never redeems an offer and is never refused."""
		original = self._desk_invoice()
		original.submit()
		debit = self._desk_invoice(rate=2, is_debit_note=1, return_against=original.name)
		debit.submit()
		self.assertEqual((debit.docstatus, self._usage(), self._stamp(debit.name)), (1, [], []))

		self._redeem()
		again = self._desk_invoice(rate=2, is_debit_note=1, return_against=original.name)
		again.submit()
		self.assertEqual(again.docstatus, 1)

	def test_consolidated_invoice_neither_redeems_nor_refused(self):
		"""N3: a consolidated invoice merges sales already checked (spec 10.4)."""
		for _ in range(2):
			doc = self._desk_invoice()
			doc.is_consolidated = 1
			doc.items[0].update({"rate": 18, "price_list_rate": 0, "pricing_rules": self.rule})
			invoices.check_one_time_offers_on_submit(doc)
		self.assertEqual(self._usage(), [])

	def _gift_pool_rule(self):
		"""A one-time Gift Pool scheme: buy ITEM_A's group, a gift from pool G2 (ITEM_G2).
		Its rule's ``free_item`` is set to another item, so only the pool names ITEM_G2."""
		from pos_next.api.test_free_rows import G2, ITEM_G2

		if not frappe.db.exists("DocType", "POS Gift Pool Item") or not frappe.db.has_column(
			"Promotional Scheme", "promotion_type"
		):
			self.skipTest("Gift Pool is not installed")
		for group in (G2,):
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
		scheme = f"{PREFIX}POOL_{self.customer}"
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": scheme,
				"company": self.ctx.company,
				"apply_on": "Item Group",
				"selling": 1,
				"promotion_type": "Gift Pool",
				"item_groups": [{"item_group": frappe.db.get_value("Item", ITEM_A, "item_group")}],
				"applicable_for": "Customer",
				"customer": [{"customer": self.customer}],
				"gift_pool_items": [{"item_group": G2, "item_code": ITEM_G2, "free_qty": 1}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Promotional Scheme", scheme, force=True, ignore_permissions=True)
		rule = frappe.db.get_value("Pricing Rule", {"promotional_scheme": scheme, "disable": 0}, "name")
		frappe.db.set_value(
			"Pricing Rule",
			rule,
			{"one_time_per_customer": 1, "price_or_product_discount": "Product", "free_item": ITEM_B},
		)
		self.addCleanup(frappe.db.delete, USAGE, {"pricing_rule": rule})
		return rule, ITEM_G2

	def test_gift_pool_item_of_redeemed_offer_takes_no_manual_discount(self):
		"""N2: every item of a used one-time Gift Pool is the offer's item, not only free_item."""
		rule, pool_item = self._gift_pool_rule()
		frappe.get_doc(
			{"doctype": USAGE, "customer": self.customer, "pricing_rule": rule, "sales_invoice": None}
		).insert(ignore_permissions=True)
		self.title = frappe.db.get_value("Pricing Rule", rule, "title")
		row = _line(self.ctx, pool_item, price_list_rate=10)
		row.update(rate=0.1, discount_percentage=99, discount_amount=9.9)
		cart = dict(_cart_payload(self.ctx, [row]), customer=self.customer)
		self.assertAlreadyUsed(lambda: self._submit(cart))

	def test_item_offer_not_re_given_as_header_discount(self):
		"""O1: after an item offer is used, a manual header discount on a cart with its item is
		refused (POS and Desk); a cart without that item keeps its header discount."""
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		self._redeem()
		for percentage in (10, 1):
			with self.subTest(percentage=percentage):
				self.assertAlreadyUsed(
					lambda p=percentage: self._submit(
						self._header_cart(p, items=((ITEM_C, 1),)), amount=20 * (1 - p / 100)
					)
				)
		self.assertAlreadyUsed(self._desk_invoice(additional_discount_percentage=10).submit)
		sale = self._submit(self._header_cart(10, items=((ITEM_A, 1),)), amount=45)
		self.assertEqual(sale.docstatus, 1)

	def test_regular_offer_on_redeemed_item_still_allowed(self):
		"""O2: only the unexplained part is refused; a regular offer on the item still applies."""
		self._redeem()
		regular, _title = self._rule(
			"REGULAR",
			apply_on="Item Code",
			items=[{"item_code": ITEM_C}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=5,
		)
		frappe.db.set_value("Pricing Rule", regular, "one_time_per_customer", 0)
		# The used offer outranks the regular one: only an evaluation without it finds the
		# regular offer (Ruling 117).
		frappe.db.set_value("Pricing Rule", self.rule, "priority", "10")
		self._pos_settings(allow_user_to_edit_item_discount=0)
		sale = self._submit(self._cart(percentage=5))
		self.assertEqual((sale.docstatus, flt(sale.items[0].rate)), (1, 19))
		self.assertAlreadyUsed(lambda: self._submit(self._cart(percentage=10)))

	# ---- fix round 4 (Ruling 117) -------------------------------------------

	def _regular_rule(self, suffix, percentage, priority, **fields):
		"""A regular (not one-time) percentage rule on ITEM_C, for every customer."""
		args = {
			"apply_on": "Item Code",
			"items": [{"item_code": ITEM_C}],
			"price_or_product_discount": "Price",
			"rate_or_discount": "Discount Percentage",
			"discount_percentage": percentage,
			"priority": str(priority),
			**fields,
		}
		rule = _make_rule(f"{PREFIX}{suffix}_{self.customer}", **args)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", rule, force=True, ignore_permissions=True)
		return rule

	@staticmethod
	@contextmanager
	def _quiet_logs():
		"""A rule conflict is logged with rule names only, no test prefix to clean up by."""
		with patch.object(invoices, "log_error_without_telemetry"), patch("frappe.log_error"):
			yield

	def test_used_offer_item_takes_only_the_regular_offer_erpnext_picks(self):
		"""NB2: on a used offer's item the explained part is what ERPNext would apply without
		that offer (priority decides), never the most generous rule that merely matches."""
		frappe.db.set_value("Pricing Rule", self.rule, "priority", "10")
		self._redeem()
		self._pos_settings(allow_user_to_edit_item_discount=0)
		self._regular_rule("S1", 5, 5)
		s2 = self._regular_rule("S2", 15, 1)

		self.assertAlreadyUsed(lambda: self._submit(self._cart(percentage=15)))
		self.assertAlreadyUsed(lambda: self._submit(self._cart(percentage=15, rule=s2)))
		self.assertAlreadyUsed(self._desk_invoice(rate=17).submit)
		sale = self._submit(self._cart(percentage=5))
		self.assertEqual((sale.docstatus, flt(sale.items[0].rate)), (1, 19))
		desk = self._desk_invoice(rate=19)
		desk.submit()
		self.assertEqual(desk.docstatus, 1)
		self.assertEqual(len(self._usage()), 1)

	def test_used_offer_item_explains_nothing_on_a_rule_conflict(self):
		"""NB2: when ERPNext cannot pick (equal priority, "Multiple Price Rules"), nothing is
		explained on the used offer's item."""
		frappe.db.set_value("Pricing Rule", self.rule, "priority", "10")
		self._redeem()
		self._pos_settings(allow_user_to_edit_item_discount=0)
		self._regular_rule("S1", 5, 1)
		self._regular_rule("S2", 15, 1)
		with self._quiet_logs():
			self.assertAlreadyUsed(lambda: self._submit(self._cart(percentage=15)))
			self.assertAlreadyUsed(self._desk_invoice(rate=17).submit)

	def test_used_offer_item_back_dated_takes_no_expired_regular_offer(self):
		"""NB2: a regular offer is valid on the evaluator's own date, not a back-dated posting date."""
		self._redeem()
		self._pos_settings(allow_user_to_edit_item_discount=0)
		self._regular_rule("EXP", 50, 1, valid_from="2020-01-01", valid_upto="2020-12-31")
		cart = dict(self._cart(percentage=50), posting_date="2020-06-01", set_posting_time=1)
		self.assertAlreadyUsed(lambda: self._submit(cart))

	def test_used_offer_item_takes_a_cart_wide_regular_offer(self):
		"""NB2: a regular rule that needs the whole cart (mixed conditions) still explains its
		part on a used offer's item."""
		frappe.db.set_value("Pricing Rule", self.rule, "priority", "5")
		self._redeem()
		self._pos_settings(allow_user_to_edit_item_discount=0)
		group = frappe.db.get_value("Item", ITEM_C, "item_group")
		self._regular_rule(
			"MIXED",
			5,
			1,
			apply_on="Item Group",
			items=[],
			item_groups=[{"item_group": group}],
			mixed_conditions=1,
			min_qty=2,
		)
		sale = self._submit(self._cart(percentage=5, qty=2))
		self.assertEqual((sale.docstatus, flt(sale.items[0].rate)), (1, 19))

	def test_header_explained_by_regular_transaction_offer_submits_everywhere(self):
		"""NB1: a header a regular transaction offer explains is no manual discount on a cart with
		a used offer's item: Desk and the closing shift's printed drafts submit it; a manual
		header on top is still refused."""
		from pos_next.pos_next.doctype.pos_closing_shift import pos_closing_shift

		self._pos_settings(allow_user_to_edit_additional_discount=1)
		# The used offer needs two, so ERPNext's own Desk pricing never applies it to one.
		frappe.db.set_value("Pricing Rule", self.rule, "min_qty", 2)
		self._submit(self._cart(percentage=10, rule=self.rule, qty=2))
		self.assertEqual(len(self._usage()), 1)
		regular = _make_rule(
			f"{PREFIX}TXN_REGULAR_{self.customer}",
			apply_on="Transaction",
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=5,
			apply_discount_on="Grand Total",
			applicable_for="Customer",
			customer=self.customer,
			min_qty=0,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", regular, force=True, ignore_permissions=True)

		desk = self._desk_invoice(ignore_pricing_rule=0)
		self.assertEqual(flt(desk.discount_amount), 1)
		desk.submit()
		self.assertEqual(desk.docstatus, 1)

		header = dict(self._cart(), additional_discount_percentage=5, apply_discount_on="Grand Total")
		printed = update_invoice(json.dumps(dict(header, payments=self._payments(19))))["name"]
		self.addCleanup(self._discard, printed)
		frappe.db.set_value("Sales Invoice", printed, "posa_is_printed", 1)
		real_get_all = frappe.get_all

		def shift_drafts(doctype, *args, **kwargs):
			if doctype == "Sales Invoice" and "posa_is_printed" in (kwargs.get("filters") or {}):
				return [frappe._dict(name=printed)]
			return real_get_all(doctype, *args, **kwargs)

		with patch.object(pos_closing_shift.frappe, "get_all", side_effect=shift_drafts):
			pos_closing_shift.submit_printed_invoices(f"{PREFIX}SHIFT", "Sales Invoice")
		self.assertEqual(frappe.db.get_value("Sales Invoice", printed, "docstatus"), 1)

		self.assertAlreadyUsed(self._desk_invoice(additional_discount_percentage=10).submit)
		self.assertEqual(len(self._usage()), 1)

	# ---- fix round 5 (Ruling 118) -------------------------------------------

	def _close(self, name):
		"""Close a shift whose one printed draft is ``name`` (a real shift needs a POS Opening Shift)."""
		from pos_next.pos_next.doctype.pos_closing_shift import pos_closing_shift

		real_get_all = frappe.get_all

		def shift_drafts(doctype, *args, **kwargs):
			if doctype == "Sales Invoice" and "posa_is_printed" in (kwargs.get("filters") or {}):
				return [frappe._dict(name=name)]
			return real_get_all(doctype, *args, **kwargs)

		with patch.object(pos_closing_shift.frappe, "get_all", side_effect=shift_drafts):
			pos_closing_shift.submit_printed_invoices(f"{PREFIX}SHIFT", "Sales Invoice")
		return frappe.db.get_value("Sales Invoice", name, "docstatus")

	def _printed(self, payload, amount):
		name = update_invoice(json.dumps(dict(payload, payments=self._payments(amount))))["name"]
		self.addCleanup(self._discard, name)
		frappe.db.set_value("Sales Invoice", name, "posa_is_printed", 1)
		return name

	def _marked_cart(self, percentage, **marks):
		cart = self._cart(percentage=percentage)
		cart["items"][0].update(marks)
		return cart

	def _enable_ff(self):
		if not invoices._promotions_evaluates_offers():
			self.skipTest("F&F is judged by promotions, which is not installed")
		from pos_next.api.test_ff_markers import enable_ff

		enable_ff(self, self.customer, "ot8pff.example")

	def test_printed_fnf_draft_on_used_offer_item_closes(self):
		"""C4: a real F&F sale on a used offer's item, printed and closed, submits and records
		nothing more."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		self._redeem()
		self._enable_ff()
		printed = self._printed(
			self._marked_cart(30, posnext_discount_source=invoices.FNF_DISCOUNT_SOURCE), 14
		)
		self.assertEqual(self._close(printed), 1)
		self.assertEqual(len(self._usage()), 1)
		self.assertEqual(self._stamp(printed), [])

	def test_printed_fnf_draft_never_uses_an_unused_offer(self):
		"""C4: an F&F sale is no use of the offer: closing its printed draft records nothing."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		self._enable_ff()
		printed = self._printed(
			self._marked_cart(30, posnext_discount_source=invoices.FNF_DISCOUNT_SOURCE), 14
		)
		self.assertEqual(self._close(printed), 1)
		self.assertEqual(self._usage(), [])

	def test_forged_fnf_mark_on_desk_still_refused(self):
		"""C4: a Desk invoice (not is_pos) is not judged by promotions' F&F check, so its F&F
		mark explains nothing."""
		self._redeem()
		doc = self._desk_invoice(rate=14)
		doc.items[0].posnext_discount_source = invoices.FNF_DISCOUNT_SOURCE
		doc.items[0].db_update()
		self.assertAlreadyUsed(doc.submit)

	def _line_coupon(self, percentage=30):
		if not frappe.db.has_column("POS Coupon", "apply_scope"):
			self.skipTest("Line-level coupons are not installed")
		code = f"OT8P{frappe.generate_hash(length=6)}".upper()
		coupon = frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": f"{PREFIX}{code}",
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

	def _coupon_cart(self, code):
		cart = self._marked_cart(
			30, posnext_coupon_code=code, posnext_coupon_discount=6, posnext_discount_source="coupon"
		)
		return dict(cart, coupon_code=code)

	def test_printed_line_coupon_draft_on_used_offer_item_closes(self):
		"""C4: a line coupon on a used offer's item is the coupon's discount, not the offer's:
		its printed draft closes and records nothing more."""
		self._pos_settings(allow_user_to_edit_item_discount=0)
		code = self._line_coupon()
		self._redeem()
		printed = self._printed(self._coupon_cart(code), 14)
		self.assertEqual(self._close(printed), 1)
		self.assertEqual(len(self._usage()), 1)

	def test_printed_line_coupon_draft_never_uses_an_unused_offer(self):
		self._pos_settings(allow_user_to_edit_item_discount=0)
		code = self._line_coupon()
		printed = self._printed(self._coupon_cart(code), 14)
		self.assertEqual(self._close(printed), 1)
		self.assertEqual(self._usage(), [])

	def test_forged_line_coupon_mark_on_desk_still_refused(self):
		"""C4: a coupon code on a Desk row that the coupon resolver does not back explains nothing:
		the sale is refused (pos_next's coupon-row check refuses it first) and records nothing."""
		code = self._line_coupon()
		self._redeem()
		doc = self._desk_invoice(rate=14)
		doc.items[0].posnext_coupon_code = code
		doc.items[0].db_update()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.assertEqual(len(self._usage()), 1)
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.name, "docstatus"), 0)

	def test_printed_draft_keeps_the_regular_offer_of_its_sale_day(self):
		"""C7: a regular offer that ended on the sale day still explains the printed draft when
		the shift closes the next day (the draft's server-set creation date)."""
		from frappe.utils import add_days, add_to_date, now_datetime

		frappe.db.set_value("Pricing Rule", self.rule, "priority", "10")
		self._redeem()
		self._pos_settings(allow_user_to_edit_item_discount=0)
		regular = self._regular_rule("ENDS", 5, 5, valid_upto=nowdate())
		printed = self._printed(self._cart(percentage=5), 19)
		# The sale was yesterday, the last day of the offer; the shift closes today.
		yesterday = add_days(nowdate(), -1)
		frappe.db.set_value(
			"Pricing Rule", regular, {"valid_from": add_days(nowdate(), -2), "valid_upto": yesterday}
		)
		frappe.db.set_value(
			"Sales Invoice",
			printed,
			{"creation": add_to_date(now_datetime(), days=-1), "posting_date": yesterday},
			update_modified=False,
		)
		self.assertEqual(self._close(printed), 1)
		self.assertEqual(len(self._usage()), 1)
