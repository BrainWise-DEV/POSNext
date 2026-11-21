# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS return refunds (UI test run 2, D-R2-16).

A POS return refunds what the customer paid, through the payment rows the
cashier chose, and leaves nothing outstanding unless the cashier chose "Add to
Customer Credit" (no payment rows):

- a full return of an invoice that rounded refunds its rounded total;
- a free row is returned at 0 and adds no tax to the refund;
- a partial return refunds its own total, rounded the way ERPNext rounds it;
- the shift close expects the cash that was handed back.

The payloads below send the amounts the dialog sent before the fix (the
unrounded total), so the server is tested on its own.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_return_refunds'}"
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime, nowdate, round_based_on_smallest_currency_fraction

from pos_next.api import invoices
from pos_next.api.invoices import prepare_return_invoice, submit_invoice, update_invoice
from pos_next.api.test_return_safety import _ensure_pos_settings, _ensure_tax_account
from pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift import make_closing_shift_from_opening
from pos_next.test_promotions import ITEM_A, ITEM_C, _ctx, _line


class TestReturnRefunds(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		cls.tax_account = _ensure_tax_account(cls.ctx.company)
		cls.pos_settings, cls.created_pos_settings = _ensure_pos_settings(cls.ctx.pos_profile)
		cls.saved_tax_inclusive = frappe.db.get_value("POS Settings", cls.pos_settings, "tax_inclusive")
		cls.saved_rounding = frappe.db.get_value("POS Profile", cls.ctx.pos_profile, "disable_rounded_total")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		if cls.created_pos_settings:
			frappe.delete_doc("POS Settings", cls.pos_settings, force=True, ignore_permissions=True)
		else:
			frappe.db.set_value("POS Settings", cls.pos_settings, "tax_inclusive", cls.saved_tax_inclusive)
		frappe.db.set_value("POS Profile", cls.ctx.pos_profile, "disable_rounded_total", cls.saved_rounding)
		frappe.clear_document_cache("POS Profile", cls.ctx.pos_profile)
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

	def _set_rounding(self, rounded):
		frappe.db.set_value("POS Profile", self.ctx.pos_profile, "disable_rounded_total", 0 if rounded else 1)
		frappe.clear_document_cache("POS Profile", self.ctx.pos_profile)

	def _sale(self, lines, rounded=False, exclusive_tax=False, shift=None, paid=None, payments=None):
		"""Submit a POS Sales Invoice through the POS API, paid in full (or ``paid``).

		``payments``: [(mode, amount)] instead of one row on the profile's mode.
		"""
		self._set_rounding(rounded)
		payload = {
			"doctype": "Sales Invoice",
			"is_pos": 1,
			"pos_profile": self.ctx.pos_profile,
			"company": self.ctx.company,
			"currency": self.ctx.currency,
			"customer": self.ctx.customer,
			"selling_price_list": self.ctx.price_list,
			"posting_date": nowdate(),
			"items": lines,
			"payments": [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0}],
		}
		if shift:
			payload["posa_pos_opening_shift"] = shift
		if exclusive_tax:
			frappe.db.set_value("POS Settings", self.pos_settings, "tax_inclusive", 0)
			payload["taxes"] = [
				{
					"charge_type": "On Net Total",
					"account_head": self.tax_account,
					"description": "VAT 15%",
					"rate": 15,
					"included_in_print_rate": 0,
				}
			]
		draft = update_invoice(json.dumps(payload))
		draft["payments"][0]["amount"] = (
			paid if paid is not None else (draft.get("rounded_total") or draft["grand_total"])
		)
		if payments:
			draft["payments"] = [{"mode_of_payment": mode, "amount": amount} for mode, amount in payments]
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(doc.docstatus, 1)
		return doc

	def _payload(self, prepared, refund, qty=None, shift=None, credit=False, payments=None):
		"""The return as ReturnInvoiceDialog.vue builds it, refunding ``refund``.

		It carries no taxes, as the dialog sends none. ``payments``: [(mode, amount)].
		"""
		qty = qty or {}
		rows = [
			dict(i, return_qty=qty.get(i["sales_invoice_item"], i["remaining_qty"]))
			for i in prepared["items"]
		]
		payload = {
			"doctype": "Sales Invoice",
			"pos_profile": self.ctx.pos_profile,
			"customer": prepared["customer"],
			"company": prepared["company"],
			"is_return": 1,
			"return_against": prepared["return_against"],
			"update_outstanding_for_self": 0,
			"is_pos": 1,
			"update_stock": 1,
			"items": [
				{
					"item_code": i["item_code"],
					"item_name": i["item_name"],
					"qty": -abs(i["return_qty"]),
					"rate": i["rate"],
					"warehouse": i["warehouse"],
					"uom": i["uom"],
					"conversion_factor": i.get("conversion_factor") or 1,
					"sales_invoice_item": i["sales_invoice_item"],
				}
				for i in rows
				if i["return_qty"]
			],
			"add_to_customer_balance": credit,
			"payments": []
			if credit
			else [
				{"mode_of_payment": mode, "amount": -abs(amount)}
				for mode, amount in (payments or [(self.ctx.mode_of_payment, refund)])
			],
		}
		if shift:
			payload["posa_pos_opening_shift"] = shift
		return payload

	def _old_dialog_refund(self, prepared, qty=None):
		"""What the dialog refunded before the fix: sum of round(qty x rate_with_tax), unrounded."""
		qty = qty or {}
		return flt(
			sum(
				flt(
					qty.get(i["sales_invoice_item"], i["remaining_qty"])
					* flt(i["rate_with_tax"] or i["rate"]),
					2,
				)
				for i in prepared["items"]
			),
			2,
		)

	def _return(self, payload):
		ret = submit_invoice(invoice=json.dumps(payload, default=str), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", ret["name"])
		self.assertEqual(doc.docstatus, 1)
		return doc

	def _payable(self, doc):
		return flt(doc.rounded_total or doc.grand_total, 2)

	def _assert_refunded(self, ret, amount, mode=None):
		"""``ret`` refunds ``amount`` through ``mode`` and leaves nothing outstanding."""
		self.assertEqual(flt(-ret.paid_amount, 2), flt(amount, 2))
		self.assertEqual(flt(-self._payable(ret), 2), flt(amount, 2))
		self.assertEqual(flt(ret.outstanding_amount, 2), 0)
		self.assertEqual(
			[(p.mode_of_payment, flt(p.amount, 2)) for p in ret.payments if flt(p.amount)],
			[(mode or self.ctx.mode_of_payment, flt(-amount, 2))],
		)

	# ------------------------------------------------------------------
	# Rounded originals
	# ------------------------------------------------------------------

	def test_round_down_full_return_refunds_rounded_total(self):
		# 00078: grand 34.50 rounded to 34 (half to even), paid 34
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True)
		self.assertEqual(flt(sale.grand_total), 34.5)
		self.assertEqual(flt(sale.rounded_total), 34)
		self.assertEqual(flt(sale.paid_amount), 34)

		prepared = prepare_return_invoice(sale.name)
		original = prepared["_original_invoice"]
		self.assertEqual(flt(original["rounded_total"]), 34)
		self.assertEqual(int(original["disable_rounded_total"]), 0)
		self.assertIn("smallest_currency_fraction_value", original)

		# The dialog used to send the unrounded -34.50 (server booked -0.50)
		self.assertEqual(self._old_dialog_refund(prepared), 34.5)
		ret = self._return(self._payload(prepared, 34.5))
		self._assert_refunded(ret, 34)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), 0)

	def test_round_up_full_return_refunds_rounded_total(self):
		# 00016: grand 287.50 rounded to 288, paid 288; the dialog sent -287.50
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=287.5)], rounded=True)
		self.assertEqual(flt(sale.rounded_total), 288)
		prepared = prepare_return_invoice(sale.name)
		ret = self._return(self._payload(prepared, self._old_dialog_refund(prepared)))
		self._assert_refunded(ret, 288)

	def test_return_rounds_like_the_original_after_the_profile_changes(self):
		# Sold while the profile rounded; rounding switched off before the return.
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True)
		prepared = prepare_return_invoice(sale.name)
		self._set_rounding(False)
		ret = self._return(self._payload(prepared, 34))
		self._assert_refunded(ret, 34)

	def test_change_given_on_the_sale_is_not_refunded(self):
		# Paid 50 cash for 34 (16 change): the refund is 34, and the dialog's
		# refund rows start from what the customer kept paid (net of change).
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True, paid=50)
		self.assertEqual(flt(sale.change_amount), 16)
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(
			[(p["mode_of_payment"], flt(p["amount"])) for p in prepared["_original_invoice"]["payments"]],
			[(self.ctx.mode_of_payment, 34)],
		)
		ret = self._return(self._payload(prepared, 34))
		self._assert_refunded(ret, 34)

	def test_refund_far_from_the_return_total_is_refused(self):
		# Not a rounding difference: refused, never booked as a partial refund.
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True)
		prepared = prepare_return_invoice(sale.name)
		with self.assertRaises(frappe.ValidationError):
			self._return(self._payload(prepared, 40))

	# ------------------------------------------------------------------
	# Free rows
	# ------------------------------------------------------------------

	def _free_row_sale(self, **kwargs):
		"""2 x ITEM_A + 1 free ITEM_A (same item, BXGY), 15% VAT on top: 115.00."""
		free = dict(_line(self.ctx, ITEM_A, price_list_rate=0), rate=0, is_free_item=1)
		offer = {"free_items": [{"item_code": ITEM_A, "qty": 1, "pricing_rules": "_PNXT_TEST_RR_BXGY"}]}
		with patch.object(invoices, "_offer_evaluator", return_value=lambda *args, **kw: offer):
			sale = self._sale([_line(self.ctx, ITEM_A, qty=2), free], exclusive_tax=True, **kwargs)
		self.assertEqual(flt(sale.grand_total), 115)
		return sale

	def test_free_row_is_returned_at_zero(self):
		sale = self._free_row_sale()
		prepared = prepare_return_invoice(sale.name)
		by_rate = {flt(i["rate"]): i for i in prepared["items"]}
		paid_row, free_row = by_rate[50], by_rate[0]
		# The item's tax is shared by row, so the free row carries none
		self.assertEqual(flt(paid_row["tax_per_unit"]), 7.5)
		self.assertEqual(flt(paid_row["rate_with_tax"]), 57.5)
		self.assertEqual(flt(free_row["tax_per_unit"]), 0)
		self.assertEqual(flt(free_row["rate_with_tax"]), 0)
		self.assertEqual(self._old_dialog_refund(prepared), 115)

		ret = self._return(self._payload(prepared, 115))
		self._assert_refunded(ret, 115)
		self.assertEqual(
			sorted(flt(i.rate) for i in ret.items), [0, 50], "return rates stay locked to the original rows"
		)

	def test_free_row_overrefund_is_refused_not_booked(self):
		# The old dialog added the paid row's tax to the free row: 115 + 15
		sale = self._free_row_sale()
		prepared = prepare_return_invoice(sale.name)
		with self.assertRaises(frappe.ValidationError):
			self._return(self._payload(prepared, 130))
		self.assertFalse(
			frappe.db.exists("Sales Invoice", {"return_against": sale.name, "docstatus": 1}),
		)

	# ------------------------------------------------------------------
	# Partial and credit returns
	# ------------------------------------------------------------------

	def test_partial_return_refunds_its_rounded_share(self):
		# 3 x 23.50 = 70.50, rounded to 70. One unit back: 23.50, rounded as ERPNext rounds it.
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=23.5)], rounded=True)
		self.assertEqual(flt(sale.paid_amount), 70)
		prepared = prepare_return_invoice(sale.name)
		row = prepared["items"][0]["sales_invoice_item"]
		expected = -round_based_on_smallest_currency_fraction(-23.5, self.ctx.currency, 2)
		ret = self._return(self._payload(prepared, 23.5, qty={row: 1}))
		self.assertEqual(flt(ret.grand_total), -23.5)
		self._assert_refunded(ret, expected)

	def test_credit_return_keeps_no_payment(self):
		# "Add to Customer Credit": no payment row, the whole rounded return is the credit
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True)
		prepared = prepare_return_invoice(sale.name)
		with patch(
			"pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.credit_return_to_wallet"
		) as credit:
			ret = self._return(self._payload(prepared, 0, credit=True))
		self.assertEqual(len(ret.payments), 0)
		self.assertEqual(flt(ret.paid_amount), 0)
		self.assertEqual(flt(ret.outstanding_amount), -34)
		credit.assert_called_once()
		self.assertEqual(flt(credit.call_args.kwargs["amount"]), 34)

	# ------------------------------------------------------------------
	# Shift close
	# ------------------------------------------------------------------

	def _opening_shift(self, opening):
		shift = frappe.get_doc(
			{
				"doctype": "POS Opening Shift",
				"period_start_date": now_datetime(),
				"posting_date": nowdate(),
				"company": self.ctx.company,
				"pos_profile": self.ctx.pos_profile,
				"user": frappe.session.user,
				"balance_details": [{"mode_of_payment": self.ctx.mode_of_payment, "amount": opening}],
			}
		)
		shift.insert(ignore_permissions=True)
		shift.submit()
		return shift.name

	def test_shift_close_expects_the_cash_handed_back(self):
		shift = self._opening_shift(100)
		rounded = self._sale([_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True, shift=shift)
		free = self._free_row_sale(shift=shift)
		credit_sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=20)], shift=shift)
		# Cash in: 34 + 115 + 20
		for sale in (rounded, free):
			prepared = prepare_return_invoice(sale.name, shift)
			self._return(self._payload(prepared, self._old_dialog_refund(prepared), shift=shift))
		prepared = prepare_return_invoice(credit_sale.name, shift)
		with patch("pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.credit_return_to_wallet"):
			self._return(self._payload(prepared, 0, shift=shift, credit=True))

		opening = json.dumps(frappe.get_doc("POS Opening Shift", shift).as_dict(), default=str)
		closing = make_closing_shift_from_opening(opening)
		cash = next(
			p for p in closing["payment_reconciliation"] if p["mode_of_payment"] == self.ctx.mode_of_payment
		)
		# 34 and 115 handed back; the credit return hands back nothing
		self.assertEqual(flt(cash["expected_amount"], 2), 100 + 20)
		# Collected nets the cash refunds (34, not the unrounded 34.50)
		self.assertEqual(flt(closing["collected_amount"], 2), 20)

	# ------------------------------------------------------------------
	# Fix round 1 (Ruling 147)
	# ------------------------------------------------------------------

	def _mode(self, name, mode_type="Bank", wallet=0):
		"""A Mode of Payment on a Bank account of the test company (rolled back)."""
		abbr = frappe.get_cached_value("Company", self.ctx.company, "abbr")
		# A wallet posts against the customer, so it needs a Receivable account
		# (other than the invoice's own receivable)
		account_name = "_PNXT_TEST_RR_WALLET_AR" if wallet else "_PNXT_TEST_RR_BANK"
		sibling = f"Debtors - {abbr}" if wallet else f"Cash - {abbr}"
		account = f"{account_name} - {abbr}"
		if not frappe.db.exists("Account", account):
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": account_name,
					"company": self.ctx.company,
					"parent_account": frappe.db.get_value("Account", sibling, "parent_account"),
					"account_type": "Receivable" if wallet else "Bank",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
		existing = frappe.db.get_value("Mode of Payment", {"mode_of_payment": name}, "name")
		if existing:
			return existing
		doc = frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": name,
				"type": mode_type,
				"enabled": 1,
				"accounts": [{"company": self.ctx.company, "default_account": account}],
			}
		)
		if wallet and doc.meta.has_field("is_wallet_payment"):
			doc.is_wallet_payment = 1
		# Sites may add a mandatory company link (and name modes by it)
		if doc.meta.has_field("custom_company"):
			doc.custom_company = self.ctx.company
		doc.insert(ignore_permissions=True)
		return doc.name

	def _modes(self, doc):
		return sorted((p.mode_of_payment, flt(p.amount, 2)) for p in doc.payments if flt(p.amount))

	def test_p1_client_tax_rows_are_ignored(self):
		# A 100% tax row sent on the return: the return keeps the original's taxes (none)
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=100)])
		prepared = prepare_return_invoice(sale.name)
		tamper = {
			"charge_type": "On Net Total",
			"account_head": self.tax_account,
			"description": "tamper",
			"rate": 100,
			"included_in_print_rate": 0,
		}
		payload = self._payload(prepared, 200)
		payload["taxes"] = [tamper]
		with self.assertRaises(frappe.ValidationError):
			self._return(payload)
		payload = self._payload(prepared, 100)
		payload["taxes"] = [tamper]
		ret = self._return(payload)
		self.assertEqual(len(ret.taxes), 0)
		self._assert_refunded(ret, 100)

	def test_p3_return_takes_the_original_taxes(self):
		# Taxed 15% exclusive; the payload has no taxes and the setting is now inclusive
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=100)], exclusive_tax=True)
		self.assertEqual(flt(sale.grand_total), 115)
		prepared = prepare_return_invoice(sale.name)
		frappe.db.set_value("POS Settings", self.pos_settings, "tax_inclusive", 1)
		ret = self._return(self._payload(prepared, 115))
		self.assertEqual(
			[(t.account_head, flt(t.rate), t.included_in_print_rate) for t in ret.taxes],
			[(self.tax_account, 15, 0)],
		)
		self._assert_refunded(ret, 115)

	def test_p2_partial_returns_refund_no_more_than_paid(self):
		# 3 x 23.50 = 70.50 paid at 70; each unit rounds to 24: the last takes the remainder
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=23.5)], rounded=True)
		self.assertEqual(flt(sale.paid_amount), 70)
		refunds = []
		for expected in (24, 24, 22):
			prepared = prepare_return_invoice(sale.name)
			self.assertEqual(flt(prepared["_original_invoice"]["refundable_cash"]), 70 - sum(refunds))
			row = prepared["items"][0]["sales_invoice_item"]
			ret = self._return(self._payload(prepared, expected, qty={row: 1}))
			self.assertEqual(flt(-ret.paid_amount), expected)
			self.assertEqual(flt(ret.outstanding_amount), 0)
			refunds.append(expected)
		self.assertEqual(sum(refunds), 70)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), 0)

	def test_p2_overrefund_beyond_what_is_left_is_refused(self):
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=23.5)], rounded=True)
		for _ in range(2):
			prepared = prepare_return_invoice(sale.name)
			row = prepared["items"][0]["sales_invoice_item"]
			self._return(self._payload(prepared, 24, qty={row: 1}))
		prepared = prepare_return_invoice(sale.name)
		with self.assertRaises(frappe.ValidationError) as caught:
			self._return(self._payload(prepared, 24))
		self.assertIn("reload", str(caught.exception).lower())

	def test_p4_partly_paid_original_refunds_at_most_what_was_paid(self):
		# 100 sold, 40 paid: a full return refunds 40 and clears the 60 still owed
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=100)], paid=40)
		self.assertEqual(flt(sale.outstanding_amount), 60)
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(flt(prepared["_original_invoice"]["refundable_cash"]), 40)
		with self.assertRaises(frappe.ValidationError):
			self._return(self._payload(prepared, 100))
		ret = self._return(self._payload(prepared, 40))
		self.assertEqual(flt(-ret.paid_amount), 40)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), 0)

	def test_cash_and_card_original_refunds_each_mode(self):
		card = self._mode("_PNXT_TEST_RR_CARD")
		cash = self.ctx.mode_of_payment
		# 34.50 rounded to 34: Cash 30 (10 change) + Card 14
		sale = self._sale(
			[_line(self.ctx, ITEM_C, price_list_rate=34.5)], rounded=True, payments=[(cash, 30), (card, 14)]
		)
		self.assertEqual(flt(sale.change_amount), 10)
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(
			sorted(
				(p["mode_of_payment"], flt(p["amount"])) for p in prepared["_original_invoice"]["payments"]
			),
			sorted([(cash, 20), (card, 14)]),
		)
		# The rounding is taken up on the cash row; the card gets back what it paid
		ret = self._return(self._payload(prepared, 0, payments=[(cash, 20.5), (card, 14)]))
		self.assertEqual(self._modes(ret), sorted([(cash, -20), (card, -14)]))
		self.assertEqual(flt(ret.outstanding_amount), 0)

	def test_wallet_original_refunds_to_the_wallet(self):
		wallet = self._mode("_PNXT_TEST_RR_WALLET", wallet=1)
		cash = self.ctx.mode_of_payment
		with patch("pos_next.api.wallet.validate_wallet_payment"):
			sale = self._sale(
				[_line(self.ctx, ITEM_C, price_list_rate=34.5)],
				rounded=True,
				payments=[(cash, 10), (wallet, 24)],
			)
		prepared = prepare_return_invoice(sale.name)
		ret = self._return(self._payload(prepared, 0, payments=[(cash, 10.5), (wallet, 24)]))
		self.assertEqual(self._modes(ret), sorted([(cash, -10), (wallet, -24)]))
		self.assertEqual(flt(ret.outstanding_amount), 0)

	# ------------------------------------------------------------------
	# Fix round 2 (Ruling 151)
	# ------------------------------------------------------------------

	def _unit_returns(self, sale, sends):
		"""One-unit returns of ``sale``'s only row, refunding each of ``sends``."""
		returns = []
		for send in sends:
			prepared = prepare_return_invoice(sale.name)
			row = prepared["items"][0]["sales_invoice_item"]
			returns.append(self._return(self._payload(prepared, send, qty={row: 1})))
		return returns

	def test_p5_last_return_takes_the_remainder_when_rounding_went_down(self):
		# 3 x 22.50 = 67.50 paid at 68; each unit rounds to 22: the last refunds 24
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=22.5)], rounded=True)
		self.assertEqual(flt(sale.paid_amount), 68)
		first, second = self._unit_returns(sale, (22, 22))
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(flt(prepared["_original_invoice"]["refundable_cash"]), 24)
		last = self._return(self._payload(prepared, 24))
		for ret, expected in ((first, 22), (second, 22), (last, 24)):
			self.assertEqual(flt(-ret.paid_amount), expected)
			self.assertEqual(flt(ret.outstanding_amount), 0)
		self.assertEqual(flt(last.rounded_total), -24)
		self.assertEqual(flt(last.rounding_adjustment), -1.5)
		self.assertEqual(flt(last.write_off_amount), 0)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), 0)

	def test_p5b_last_return_refunds_the_remainder_and_no_more(self):
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=22.5)], rounded=True)
		self._unit_returns(sale, (22, 22))
		prepared = prepare_return_invoice(sale.name)
		for send in (22, 25):
			with self.assertRaises(frappe.ValidationError):
				self._return(self._payload(prepared, send))

	def test_rounding_up_last_return_takes_the_remainder_without_write_off(self):
		# 3 x 23.50 paid at 70: 24 + 24, then the last refunds 22 by its rounding
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=23.5)], rounded=True)
		last = self._unit_returns(sale, (24, 24, 22))[-1]
		self.assertEqual(flt(last.rounded_total), -22)
		self.assertEqual(flt(last.write_off_amount), 0)
		self.assertEqual(flt(last.outstanding_amount), 0)

	def test_credit_return_on_partly_paid_original_credits_what_was_paid(self):
		# 100 sold, 40 paid: "Add to Customer Credit" credits 40, the 60 owed is cleared
		sale = self._sale([_line(self.ctx, ITEM_C, price_list_rate=100)], paid=40)
		prepared = prepare_return_invoice(sale.name)
		with patch(
			"pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.credit_return_to_wallet"
		) as credit:
			ret = self._return(self._payload(prepared, 0, credit=True))
		self.assertEqual(len(ret.payments), 0)
		credit.assert_called_once()
		self.assertEqual(flt(credit.call_args.kwargs["amount"]), 40)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), -40)

	def test_return_after_a_credit_return_refunds_only_what_is_left(self):
		# 2 x 50 paid 100; one unit to credit (50), then the last unit refunds 50
		sale = self._sale([_line(self.ctx, ITEM_C, qty=2, price_list_rate=50)])
		prepared = prepare_return_invoice(sale.name)
		row = prepared["items"][0]["sales_invoice_item"]
		with patch("pos_next.pos_next.doctype.wallet_transaction.wallet_transaction.credit_return_to_wallet"):
			self._return(self._payload(prepared, 0, qty={row: 1}, credit=True))
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(flt(prepared["_original_invoice"]["refundable_cash"]), 50)
		with self.assertRaises(frappe.ValidationError):
			self._return(self._payload(prepared, 100))
		ret = self._return(self._payload(prepared, 50))
		self.assertEqual(flt(-ret.paid_amount), 50)

	def test_q8_actual_charge_residue_is_written_off_not_rounded(self):
		# 2 x 50 + Actual 10 = 110 paid; ERPNext copies the 10 onto each partial
		# return, so the last one is 60 against 50 left: 10 is a write-off, not rounding
		self._set_rounding(True)
		frappe.db.set_value("POS Settings", self.pos_settings, "tax_inclusive", 0)
		payload = {
			"doctype": "Sales Invoice",
			"is_pos": 1,
			"pos_profile": self.ctx.pos_profile,
			"company": self.ctx.company,
			"currency": self.ctx.currency,
			"customer": self.ctx.customer,
			"selling_price_list": self.ctx.price_list,
			"posting_date": nowdate(),
			"items": [_line(self.ctx, ITEM_C, qty=2, price_list_rate=50)],
			"payments": [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 0}],
			"taxes": [
				{
					"charge_type": "Actual",
					"account_head": self.tax_account,
					"description": "Delivery",
					"tax_amount": 10,
				}
			],
		}
		draft = update_invoice(json.dumps(payload))
		draft["payments"][0]["amount"] = draft.get("rounded_total") or draft["grand_total"]
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		sale = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(flt(sale.paid_amount), 110)
		self._unit_returns(sale, (60,))
		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(flt(prepared["_original_invoice"]["refundable_cash"]), 50)
		last = self._return(self._payload(prepared, 50))
		self.assertEqual(flt(-last.paid_amount), 50)
		self.assertEqual(flt(last.rounded_total), -60)
		self.assertEqual(flt(last.rounding_adjustment), 0)
		self.assertEqual(flt(last.write_off_amount), -10)
		self.assertEqual(flt(last.outstanding_amount), 0)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.name, "outstanding_amount")), 0)
