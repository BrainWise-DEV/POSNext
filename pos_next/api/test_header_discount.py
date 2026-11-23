# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The server caps the invoice-level (header) discount (Task 8m).

After totals, ``discount_amount`` must be explained by the invoice's coupon
(promotions' cap when installed, else pos_next's POS Coupon value), by a
transaction offer the server evaluates, or by a manual invoice discount the POS
Settings permit (Allow Additional Discount, capped by Max Discount Percentage
Allowed on the total before the header). Online: refused; offline sync or a header
a paid draft already held: logged.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_header_discount'}"
"""

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import update_invoice
from pos_next.api.test_discount_enforcement import (
	CUSTOMER,
	EMAIL_DOMAIN,
	FNF,
	PREFIX,
	PRICE,
	DiscountEnforcementCase,
)
from pos_next.api.test_ff_markers import enable_ff
from pos_next.test_promotions import ITEM_B, _make_rule

NOT_ALLOWED = "manual invoice discounts are not allowed"
OVER_LIMIT = "above the maximum allowed invoice discount"
NO_SOURCE = "no coupon or offer gives it"
NOT_CHECKED = "could not be checked against the offers"
HEADER_PREFIX = f"{PREFIX}HDR_"


def _without_promotions():
	"""Neither promotions' evaluator nor its coupon resolver is used."""
	return patch.object(invoices.frappe, "override_whitelisted_method", side_effect=lambda method: method)


class TestHeaderDiscount(DiscountEnforcementCase):
	def setUp(self):
		super().setUp()
		self._pos_settings(allow_user_to_edit_additional_discount=0)

	def _header_payload(self, header, rate=PRICE, **row):
		payload = self._payload(rate, **row)
		payload["discount_amount"] = header
		return payload

	def _header_coupon(self, code, percentage=10, **fields):
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
				"apply_on": "Grand Total",
				"maximum_use": 100,
				**fields,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		return code

	# ---- manual header -------------------------------------------------------

	def test_manual_header_discount_off_refused(self):
		with patch("frappe.deferred_insert.deferred_insert") as deferred:
			message = self.assertRefused(self._header_payload(5), NOT_ALLOWED)
		self.assertIn("Invoice discount 5.0", message)
		self.assertIn(NO_SOURCE, message)
		self.assertEqual(
			deferred.call_args.kwargs["records"]["method"], invoices.UNEXPLAINED_DISCOUNT_LOG_TITLE
		)

	def test_manual_header_within_limit(self):
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=20)
		doc = self._draft(self._header_payload(10))
		self.assertEqual(flt(doc.discount_amount), 10)

	def test_manual_header_no_limit_when_zero(self):
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=0)
		doc = self._draft(self._header_payload(40))
		self.assertEqual(flt(doc.discount_amount), 40)

	def test_manual_header_over_limit_refused(self):
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		message = self.assertRefused(self._header_payload(10), OVER_LIMIT)
		for text in ("Invoice discount 10.0", NO_SOURCE, "20.0% of 50.0", "of 10.0%"):
			self.assertIn(text, message)

	def test_manual_header_percentage_measured_after_line_discounts(self):
		"""The base is the total the header applies to: 5 on a 45 line is 11.11%."""
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		message = self.assertRefused(self._header_payload(5, rate=45, discount_percentage=10), OVER_LIMIT)
		self.assertIn("11.11% of 45.0", message)
		doc = self._draft(self._header_payload(4.5, rate=45, discount_percentage=10))
		self.assertEqual(flt(doc.discount_amount), 4.5)

	def test_header_percentage_field_is_judged(self):
		"""additional_discount_percentage is judged by the amount ERPNext works out from it."""
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		payload = self._header_payload(0)
		payload["additional_discount_percentage"] = 30
		self.assertRefused(payload, OVER_LIMIT)

	def test_line_and_header_capped_separately(self):
		"""10% on the line and 10% on the header, max 10%: each within its own cap."""
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		doc = self._draft(self._header_payload(4.5, rate=45, discount_percentage=10))
		self.assertEqual((flt(doc.items[0].rate), flt(doc.discount_amount)), (45, 4.5))

	def test_sales_order_header_checked(self):
		payload = self._header_payload(5)
		payload.update(
			{
				"doctype": "Sales Order",
				"delivery_date": frappe.utils.nowdate(),
				"apply_discount_on": "Grand Total",
			}
		)
		self.assertRefused(payload, NOT_ALLOWED)

	# ---- coupon / offers -----------------------------------------------------

	def test_coupon_header_capped_without_promotions(self):
		"""Without promotions, pos_next's POS Coupon value (10% of 50 = 5) caps the header."""
		code = self._header_coupon(f"{HEADER_PREFIX}C10")
		with _without_promotions():
			doc = self._draft(dict(self._header_payload(5), coupon_code=code))
			self.assertEqual(flt(doc.discount_amount), 5)
			message = self.assertRefused(dict(self._header_payload(8), coupon_code=code), NOT_ALLOWED)
		self.assertIn(f"5.0 of it is given by coupon {code}", message)

	def test_coupon_header_plus_manual_within_limit(self):
		"""Only the part above the coupon is manual: 9 = coupon 5 + manual 4 (8%); 11 is 12%.

		Judged on the computed invoice: on save, promotions' own hook caps a coupon
		header at the coupon's value.
		"""
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		code = self._header_coupon(f"{HEADER_PREFIX}C10")

		def check(header):
			doc = frappe.get_doc({**self._header_payload(header), "coupon_code": code})
			doc.apply_discount_on = "Grand Total"
			doc.calculate_taxes_and_totals()
			invoices._check_header_discount(doc)

		with _without_promotions():
			check(9)
			with self.assertRaises(frappe.ValidationError) as caught:
				check(11)
		self.assertIn(f"5.0 of it is given by coupon {code}", str(caught.exception))
		self.assertIn("the manual part 6.0 is 12.0% of 50.0", str(caught.exception))

	def test_unknown_coupon_explains_nothing(self):
		with _without_promotions():
			self.assertRefused(dict(self._header_payload(5), coupon_code="NO_SUCH_COUPON"), NOT_ALLOWED)

	def test_coupon_header_left_to_promotions(self):
		"""With promotions on a POS Sales Invoice, promotions caps the coupon header (8 → 5)."""
		if invoices.frappe.override_whitelisted_method(invoices.COUPON_DISCOUNT_METHOD) == (
			invoices.COUPON_DISCOUNT_METHOD
		):
			self.skipTest("promotions does not resolve coupons")
		code = self._header_coupon(f"{HEADER_PREFIX}C10")
		doc = self._draft(dict(self._header_payload(8), coupon_code=code))
		self.assertEqual(flt(doc.discount_amount), 5)

	def _transaction_rule(self, percentage=10):
		name = _make_rule(
			f"{HEADER_PREFIX}TXN_{percentage}",
			apply_on="Transaction",
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=percentage,
			apply_discount_on="Grand Total",
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def test_transaction_offer_header_saved(self):
		"""A server-evaluated 10% transaction rule explains 5 on 50, with manual discounts off."""
		self._transaction_rule(10)
		doc = self._draft(self._header_payload(5))
		self.assertEqual(flt(doc.discount_amount), 5)

	def test_transaction_offer_explains_only_its_own_header(self):
		self._transaction_rule(10)
		message = self.assertRefused(self._header_payload(9), NOT_ALLOWED)
		self.assertIn("5.0 of it is given by the offers", message)

	def test_one_evaluator_call_for_rows_and_header(self):
		"""A row below list price and an unexplained header share one evaluator call."""
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		with patch.object(invoices, "_evaluate_offers", wraps=invoices._evaluate_offers) as evaluate:
			self._draft(self._header_payload(4, rate=45, discount_percentage=10))
		self.assertEqual(evaluate.call_count, 1)

	def test_no_header_no_evaluator_call(self):
		evaluator = MagicMock()
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			self._draft(self._header_payload(0))
		evaluator.assert_not_called()

	# ---- offline / paid earlier / returns ------------------------------------

	def test_offline_header_logged(self):
		before = self._logs()
		paid = PRICE - 5
		payload = dict(
			self._header_payload(5),
			payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": paid}],
			offline_id=f"{HEADER_PREFIX}OFFLINE_{frappe.generate_hash(length=10)}",
		)
		result = invoices.submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual((doc.docstatus, flt(doc.discount_amount)), (1, 5))
		new_logs = self._logs() - before
		self.assertEqual(len(new_logs), 1)
		self.assertIn(NOT_ALLOWED, frappe.db.get_value("Error Log", new_logs.pop(), "error"))

	def test_paid_draft_keeps_only_the_header_it_held(self):
		"""A paid draft saved with the header allowed is re-submitted after it was turned off."""
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		payments = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		draft = update_invoice(json.dumps(dict(self._header_payload(5), payments=payments)))
		self._pos_settings(allow_user_to_edit_additional_discount=0)

		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(dict(self._header_payload(6), name=draft["name"]))
		self.assertIn(NOT_ALLOWED, str(caught.exception))

		before = self._logs()
		paid = dict(self._header_payload(5), name=draft["name"])
		paid["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": PRICE - 5}]
		result = invoices.submit_invoice(invoice=json.dumps(paid), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", result["name"])
		self.assertEqual((doc.docstatus, flt(doc.discount_amount)), (1, 5))
		self.assertEqual(len(self._logs() - before), 1)

	def _paid(self, payload, header):
		"""Submit ``payload`` paid online in full (rows at their rate, less the header)."""
		paid = sum(flt(row["rate"]) * flt(row["qty"]) for row in payload["items"]) - header
		payload = dict(payload, payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": paid}])
		result = invoices.submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", result["name"])

	def _fnf_coupon_payload(self, header, code):
		"""An F&F line (35 of 50) and the invoice's 10% Grand Total coupon (3.5 on 35)."""
		payload = self._header_payload(header, rate=35, discount_percentage=30, posnext_discount_source=FNF)
		payload["coupon_code"] = code
		return payload

	def test_paid_coupon_header_on_fnf_lines_refused_online(self):
		"""Ruling 98 (was Ruling 89's "at the coupon's value it passes"): a line that got F&F
		gets no coupon, so next to an F&F-only cart a coupon header is refused online, even
		at the 3.5 pos_next values the coupon at. The cart sends no header there (8j)."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(self._fnf_coupon_payload(3.5, code), 3.5)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))

	def test_paid_draft_coupon_header_on_fnf_lines_kept(self):
		"""Ruling 97: a paid draft held before deploy with that coupon header (3.5 next to
		F&F) is re-submitted: pos_next flags it a paid draft, so it is kept and logged."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		payload = self._fnf_coupon_payload(0, code)
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		name = update_invoice(json.dumps(payload))["name"]
		# The header it held under the old rules (its totals as ERPNext stored them).
		frappe.db.set_value(
			"Sales Invoice",
			name,
			{"discount_amount": 3.5, "base_discount_amount": 3.5, "net_total": 31.5, "grand_total": 31.5},
		)
		doc = self._paid(dict(self._fnf_coupon_payload(3.5, code), name=name), 3.5)
		self.assertEqual((doc.docstatus, flt(doc.discount_amount)), (1, 3.5))

	def _stored_paid_draft(self, payload):
		payload = dict(payload, payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}])
		return update_invoice(json.dumps(payload))["name"]

	def _resave_paid(self, payload, name):
		payload = dict(payload, name=name)
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		return update_invoice(json.dumps(payload))

	def test_paid_draft_coupon_header_on_fnf_lines_stored_zero_refused(self):
		"""Ruling 99 (B1): the twin of ``…_kept`` with the stored header left at 0. A draft
		that held no header gets no paid-draft leniency, so 3.5 next to F&F is refused."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		name = self._stored_paid_draft(self._fnf_coupon_payload(0, code))
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(dict(self._fnf_coupon_payload(3.5, code), name=name), 3.5)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))

	def test_paid_draft_header_chain_refused(self):
		"""Ruling 99 (B1): draft at 0 with a 0.01 payment, re-saved at 3.5, then submitted at
		3.5: both the re-save and the submit are refused."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		name = self._stored_paid_draft(self._fnf_coupon_payload(0, code))
		with self.assertRaises(frappe.ValidationError) as caught:
			self._resave_paid(self._fnf_coupon_payload(3.5, code), name)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", name, "discount_amount")), 0)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(dict(self._fnf_coupon_payload(3.5, code), name=name), 3.5)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))

	def _better_payload(self, header, code, rule):
		"""ITEM_A at 45 (its 10% rule) and ITEM_B at 80 with a 20% "Better of the two" coupon:
		promotions gives 21 (5 top-up + 16), pos_next's whole-cart value is 25."""
		payload = self._header_payload(header, rate=45, discount_percentage=10, pricing_rules=rule)
		payload["items"].append(self._payload(80, item=ITEM_B)["items"][0])
		payload["coupon_code"] = code
		return payload

	def test_paid_draft_better_of_two_header_chain_refused(self):
		"""Ruling 99: a paid draft that held the 21 the coupon gives is re-saved, then
		submitted, above it (25, within pos_next's 25; 26): refused, never logged."""
		code = self._header_coupon(
			f"{HEADER_PREFIX}BETTER", 20, max_amount=100, promotion_conflict="Better of the two"
		)
		rule = self._price_rule(10)
		name = self._stored_paid_draft(self._better_payload(21, code, rule))
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", name, "discount_amount")), 21)
		for header in (25, 26):
			with self.subTest(header=header):
				with self.assertRaises(frappe.ValidationError):
					self._resave_paid(self._better_payload(header, code, rule), name)
				with self.assertRaises(frappe.ValidationError):
					self._paid(dict(self._better_payload(header, code, rule), name=name), header)

	def test_paid_draft_rows_still_judged(self):
		"""Ruling 97's leniency is the header's only: a stored paid draft re-submitted with a
		90% F&F row, or for a customer without F&F, is still refused."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)

		def stored_paid_draft():
			payload = self._header_payload(0, rate=35, discount_percentage=30, posnext_discount_source=FNF)
			payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
			return update_invoice(json.dumps(payload))["name"]

		over = self._header_payload(0, rate=5, discount_percentage=90, posnext_discount_source=FNF)
		other = self._header_payload(0, rate=35, discount_percentage=30, posnext_discount_source=FNF)
		other["customer"] = frappe.db.get_value("Customer", {"name": ["!=", CUSTOMER], "disabled": 0}, "name")
		for label, payload in (("90% F&F", over), ("customer without F&F", other)):
			with self.subTest(label):
				name = stored_paid_draft()
				with self.assertRaises(frappe.ValidationError) as caught:
					self._paid(dict(payload, name=name), 0)
				self.assertIn("Friends & Family", str(caught.exception))

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

	def test_paid_draft_flag_only_on_resaved_paid_draft(self):
		"""Rulings 97, 99: pos_next tells benefit engines (by ``flags.pos_paid_draft`` only)
		that it re-saves a stored paid draft keeping the header it held, on both save paths.
		A draft that held no header, a larger header, an unpaid draft or a fresh sale: no flag."""
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		name = self._paid_draft(1, 5)

		def resave(header):
			payload = dict(self._header_payload(header), name=name)
			payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
			return lambda: update_invoice(json.dumps(payload))

		self.assertEqual(set(self._paid_draft_flags(resave(5))), {True})
		self.assertEqual(set(self._paid_draft_flags(resave(4))), {True})
		self.assertEqual(set(self._paid_draft_flags(resave(6))), {False})
		self.assertEqual(
			set(self._paid_draft_flags(lambda: self._paid(dict(self._header_payload(5), name=name), 5))),
			{True},
		)

		held_none = self._paid_draft(1, 0)
		self.assertNotIn(
			True,
			self._paid_draft_flags(lambda: self._paid(dict(self._header_payload(0), name=held_none), 0)),
		)
		unpaid = update_invoice(json.dumps(self._header_payload(5)))["name"]
		self.assertNotIn(
			True,
			self._paid_draft_flags(lambda: self._paid(dict(self._header_payload(5), name=unpaid), 5)),
		)
		self.assertNotIn(True, self._paid_draft_flags(lambda: self._paid(self._header_payload(5), 5)))

	def _coupon_payload(self, header, code, qty=1):
		"""ITEM_A at list price (no F&F) with the invoice's 10% Grand Total coupon."""
		payload = self._header_payload(header)
		payload["items"][0]["qty"] = qty
		payload["coupon_code"] = code
		return payload

	def test_paid_draft_header_moved_to_fnf_line_refused(self):
		"""Ruling 100: a paid draft that held the coupon's 5 on 1 x 50 at list price is
		re-saved, then submitted, with that line at F&F 35 and header 3.5 (within the held
		amount and share): the line is no longer the one the header was earned on, so no
		paid-draft leniency, and the coupon next to F&F is refused at both. Also with the
		header on Net Total (rereview4's variant)."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		for apply_on in ("Grand Total", "Net Total"):
			with self.subTest(apply_discount_on=apply_on):
				name = self._stored_paid_draft(
					dict(self._coupon_payload(5, code), apply_discount_on=apply_on)
				)
				self.assertEqual(flt(frappe.db.get_value("Sales Invoice", name, "discount_amount")), 5)
				moved = dict(self._fnf_coupon_payload(3.5, code), apply_discount_on=apply_on)
				with self.assertRaises(frappe.ValidationError) as caught:
					self._resave_paid(dict(moved), name)
				self.assertIn(f"is more than coupon {code} gives", str(caught.exception))
				with self.assertRaises(frappe.ValidationError) as caught:
					self._paid(dict(moved, name=name), 3.5)
				self.assertIn(f"is more than coupon {code} gives", str(caught.exception))

	def test_paid_draft_header_moved_to_other_lines_refused(self):
		"""Ruling 100: a paid draft that held the "Better of the two" coupon's 32 on 2 x ITEM_B
		at 80 is re-saved, then submitted, as ITEM_A at 45 (its 10% rule) + ITEM_B at 80 with
		header 25 (within the held 32 and 20%): ITEM_A was never held, so refused at both."""
		code = self._header_coupon(
			f"{HEADER_PREFIX}BETTER", 20, max_amount=100, promotion_conflict="Better of the two"
		)
		rule = self._price_rule(10)
		held = self._payload(80, item=ITEM_B)
		held["items"][0]["qty"] = 2
		held.update(discount_amount=32, coupon_code=code)
		name = self._stored_paid_draft(held)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", name, "discount_amount")), 32)
		# Refused by the coupon's own cap, which applies only when not flagged a paid draft.
		with self.assertRaises(frappe.ValidationError) as caught:
			self._resave_paid(self._better_payload(25, code, rule), name)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(dict(self._better_payload(25, code, rule), name=name), 25)
		self.assertIn(f"is more than coupon {code} gives", str(caught.exception))

	def test_paid_draft_smaller_cart_same_rows_logged(self):
		"""Ruling 100 keeps Ruling 97's case: a paid draft that held 10.5 next to 3 x F&F 35
		is submitted as 1 x F&F 35 with 3.5 (the same row, rate and share): flagged a paid
		draft, so the header is kept (promotions logs it)."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		payload = self._fnf_coupon_payload(0, code)
		payload["items"][0]["qty"] = 3
		name = self._stored_paid_draft(payload)
		frappe.db.set_value(
			"Sales Invoice",
			name,
			{"discount_amount": 10.5, "base_discount_amount": 10.5, "net_total": 94.5, "grand_total": 94.5},
		)
		docs = []
		flags = self._paid_draft_flags(
			lambda: docs.append(self._paid(dict(self._fnf_coupon_payload(3.5, code), name=name), 3.5))
		)
		self.assertEqual(set(flags), {True})
		self.assertEqual((docs[0].docstatus, flt(docs[0].discount_amount)), (1, 3.5))

	def test_paid_coupon_header_with_fnf_above_coupon_refused(self):
		"""Probe P3: promotions only logs a header next to F&F rows on a paid invoice."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		code = self._header_coupon(f"{HEADER_PREFIX}FC")
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(self._fnf_coupon_payload(30, code), 30)
		message = str(caught.exception)
		self.assertIn(NOT_ALLOWED, message)
		self.assertIn(f"3.5 of it is given by coupon {code}", message)

	def _paid_draft(self, qty, header):
		payload = self._header_payload(header)
		payload["items"][0]["qty"] = qty
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0.01}]
		return update_invoice(json.dumps(payload))["name"]

	def test_paid_draft_shrunk_cart_keeps_no_larger_share(self):
		"""Probe P1: 10 x 50 with header 50 (10%), resubmitted as 1 x 50 with header 40 (80%)."""
		self._pos_settings(allow_user_to_edit_additional_discount=1, max_discount_allowed=10)
		name = self._paid_draft(10, 50)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(dict(self._header_payload(40), name=name), 40)
		self.assertIn(OVER_LIMIT, str(caught.exception))
		self.assertIn("80.0% of 50.0", str(caught.exception))

	def test_paid_draft_shrunk_offer_header_refused(self):
		"""Probe Q2: a held offer header (5 on 10 x 50) does not cover 40 on 1 x 50."""
		self._transaction_rule(10)
		name = self._paid_draft(10, 50)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._paid(dict(self._header_payload(40), name=name), 40)
		self.assertIn(NOT_ALLOWED, str(caught.exception))
		self.assertIn("5.0 of it is given by the offers", str(caught.exception))

	def test_paid_draft_same_share_still_lenient(self):
		"""2 x 50 with header 10 (10%), resubmitted as 1 x 50 with header 5 (10%): kept and logged."""
		self._pos_settings(allow_user_to_edit_additional_discount=1)
		name = self._paid_draft(2, 10)
		self._pos_settings(allow_user_to_edit_additional_discount=0)
		before = self._logs()
		doc = self._paid(dict(self._header_payload(5), name=name), 5)
		self.assertEqual((doc.docstatus, flt(doc.discount_amount)), (1, 5))
		self.assertEqual(len(self._logs() - before), 1)

	def test_evaluator_error_says_not_checked(self):
		"""Ruling 91: a failing evaluator gives "could not be checked", not "no coupon or offer"."""
		with patch.object(
			invoices, "_offer_evaluator", return_value=MagicMock(side_effect=RuntimeError("down"))
		):
			message = self.assertRefused(self._header_payload(5), NOT_CHECKED)
		self.assertIn("Invoice discount 5.0", message)
		self.assertNotIn(NO_SOURCE, message)

	def test_return_skipped(self):
		evaluator = MagicMock()
		doc = frappe.get_doc(self._header_payload(5))
		doc.is_return = 1
		with patch.object(invoices, "_offer_evaluator", return_value=evaluator):
			invoices._check_header_discount(doc)
		evaluator.assert_not_called()
