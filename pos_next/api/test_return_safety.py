# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Return safety (returns audit 2026-11-16).

- A return row must link to its original row and must not refund above that
  row's rate, for Sales Invoice and POS Invoice, Moving Average items included
  (ERPNext's own rate check skips Moving Average).
- With a header discount, the server sets the return's discount: every return
  refunds its share of what was paid, and all returns together refund exactly
  what was paid (the last one takes the remainder).

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_return_safety'}"
"""

import json
from unittest.mock import patch

import frappe
from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, nowdate

from pos_next.api import invoices
from pos_next.api.invoices import (
	prepare_return_invoice,
	submit_invoice,
	update_invoice,
	validate_return_items,
)
from pos_next.test_promotions import ITEM_A, ITEM_B, ITEM_C, _ctx, _line, _resolve_item_group

ITEM_MA = "_PNXT_TEST_ITEM_MA"  # Moving Average valuation
ITEM_MA_PRICE = 40.0
TAX_ACCOUNT_NAME = "_PNXT_TEST_VAT"
POS_INVOICE = "_PNXT_TEST_RS_PINV"


def _ensure_moving_average_item(ctx):
	if not frappe.db.exists("Item", ITEM_MA):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM_MA,
				"item_name": "Moving Average Test Item",
				"item_group": _resolve_item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"valuation_method": "Moving Average",
			}
		)
		item.flags.from_integration = True
		item.insert(ignore_permissions=True)
	ip_filters = {"item_code": ITEM_MA, "price_list": ctx.price_list}
	if not frappe.db.exists("Item Price", ip_filters):
		frappe.get_doc({"doctype": "Item Price", **ip_filters, "price_list_rate": ITEM_MA_PRICE}).insert(
			ignore_permissions=True
		)
	stock = frappe.db.get_value("Bin", {"item_code": ITEM_MA, "warehouse": ctx.warehouse}, "actual_qty")
	if flt(stock) < 50:
		make_stock_entry(item_code=ITEM_MA, target=ctx.warehouse, qty=100, rate=20, company=ctx.company)


def _ensure_tax_account(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{TAX_ACCOUNT_NAME} - {abbr}"
	if not frappe.db.exists("Account", name):
		parent = frappe.db.get_value(
			"Account", {"company": company, "is_group": 1, "account_type": "Tax"}, "name"
		) or frappe.db.get_value(
			"Account", {"company": company, "is_group": 1, "root_type": "Liability"}, "name"
		)
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": TAX_ACCOUNT_NAME,
				"company": company,
				"parent_account": parent,
				"account_type": "Tax",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_pos_settings(pos_profile):
	"""Return (name, created) of the profile's POS Settings."""
	name = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, "name")
	if name:
		return name, False
	doc = frappe.get_doc({"doctype": "POS Settings", "pos_profile": pos_profile})
	return doc.insert(ignore_permissions=True).name, True


class TestReturnSafety(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		_ensure_moving_average_item(cls.ctx)
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
		frappe.db.delete("POS Invoice Item", {"parent": POS_INVOICE})
		frappe.db.delete("POS Invoice", {"name": POS_INVOICE})
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		# The sales carry a manual invoice discount (Task 8m: it needs the setting).
		field = "allow_user_to_edit_additional_discount"
		saved = frappe.db.get_value("POS Settings", self.pos_settings, field)
		frappe.db.set_value("POS Settings", self.pos_settings, field, 1)
		self.addCleanup(frappe.db.set_value, "POS Settings", self.pos_settings, field, saved)

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

	def _set_tax_inclusive(self, value):
		frappe.db.set_value("POS Settings", self.pos_settings, "tax_inclusive", value)

	def _sale(self, lines, inclusive=None, discount_amount=0, rounded=False):
		"""Submit a POS Sales Invoice through the POS API, fully paid."""
		frappe.db.set_value("POS Profile", self.ctx.pos_profile, "disable_rounded_total", 0 if rounded else 1)
		frappe.clear_document_cache("POS Profile", self.ctx.pos_profile)
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
		if inclusive is not None:
			self._set_tax_inclusive(1 if inclusive else 0)
			payload["taxes"] = [
				{
					"charge_type": "On Net Total",
					"account_head": self.tax_account,
					"description": "VAT 15%",
					"rate": 15,
					"included_in_print_rate": 1 if inclusive else 0,
				}
			]
		if discount_amount:
			payload["discount_amount"] = discount_amount
			payload["apply_discount_on"] = "Grand Total"

		draft = update_invoice(json.dumps(payload))
		draft["payments"][0]["amount"] = draft.get("rounded_total") or draft["grand_total"]
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(doc.docstatus, 1)
		return doc

	def _submit_return(self, payload):
		ret = submit_invoice(invoice=json.dumps(payload, default=str), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", ret["name"])
		self.assertEqual(doc.docstatus, 1)
		return doc

	def _frontend_return_payload(self, prepared, qty=None):
		"""Build the return exactly as ReturnInvoiceDialog.vue does.

		``qty``: item_code -> qty to return (default: everything left). The
		refund is the dialog's returnTotal: per row, round(qty x rate_with_tax).
		"""
		qty = qty or {}
		rows = [
			dict(i, return_qty=qty.get(i["item_code"], i["remaining_qty"]))
			for i in prepared["items"]
			if qty.get(i["item_code"], i["remaining_qty"])
		]
		refund = flt(sum(flt(r["return_qty"] * flt(r["rate_with_tax"] or r["rate"]), 2) for r in rows), 2)
		return {
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
			],
			"payments": [{"mode_of_payment": self.ctx.mode_of_payment, "amount": -abs(refund)}],
		}, refund

	def _rows(self, invoice, rate_overrides=None, drop_link=()):
		"""Return rows for every line of ``invoice`` (qty 1 each)."""
		rate_overrides = rate_overrides or {}
		rows = []
		for item in invoice.items:
			row = {
				"item_code": item.item_code,
				"qty": -1,
				"rate": rate_overrides.get(item.item_code, item.rate),
			}
			if item.item_code not in drop_link:
				row["sales_invoice_item"] = item.name
			rows.append(row)
		return rows

	def _make_pos_invoice(self):
		"""Write a submitted POS Invoice straight to the DB (no POS Opening Entry needed)."""
		frappe.db.delete("POS Invoice Item", {"parent": POS_INVOICE})
		frappe.db.delete("POS Invoice", {"name": POS_INVOICE})
		doc = frappe.get_doc(
			{
				"doctype": "POS Invoice",
				"name": POS_INVOICE,
				"company": self.ctx.company,
				"customer": self.ctx.customer,
				"currency": self.ctx.currency,
				"posting_date": nowdate(),
				"docstatus": 1,
				"items": [
					{"name": f"{POS_INVOICE}-r1", "item_code": ITEM_A, "qty": 2, "rate": 50},
					{"name": f"{POS_INVOICE}-r2", "item_code": ITEM_MA, "qty": 1, "rate": ITEM_MA_PRICE},
				],
			}
		)
		doc.db_insert()
		for idx, row in enumerate(doc.items, start=1):
			row.parent, row.parenttype, row.parentfield, row.idx = POS_INVOICE, "POS Invoice", "items", idx
			row.docstatus = 1
			row.db_insert()
		return doc

	# ------------------------------------------------------------------
	# Rate lock
	# ------------------------------------------------------------------

	def test_return_rate_above_original_rejected(self):
		sale = self._sale([_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_MA, price_list_rate=ITEM_MA_PRICE)])

		# Sales Invoice, ordinary item
		result = validate_return_items(sale.name, self._rows(sale, {ITEM_A: 50.01}))
		self.assertFalse(result["valid"])
		self.assertIn("Row #1", result["message"])
		self.assertIn("higher than the rate", result["message"])

		# Sales Invoice, Moving Average item (ERPNext would let this through)
		result = validate_return_items(sale.name, self._rows(sale, {ITEM_MA: ITEM_MA_PRICE + 1}))
		self.assertFalse(result["valid"])
		self.assertIn("Row #2", result["message"])
		self.assertIn(ITEM_MA, result["message"])

		# At the original rate the same rows pass
		self.assertEqual(validate_return_items(sale.name, self._rows(sale)), {"valid": True})

		# Through the POS API the return is refused, not saved
		prepared = prepare_return_invoice(sale.name)
		payload, _refund = self._frontend_return_payload(prepared)
		for row in payload["items"]:
			if row["item_code"] == ITEM_MA:
				row["rate"] = ITEM_MA_PRICE * 2
		with self.assertRaises(frappe.ValidationError) as caught:
			submit_invoice(invoice=json.dumps(payload, default=str), data=json.dumps({}))
		self.assertIn("higher than the rate", str(caught.exception))

		# POS Invoice (link field is pos_invoice_item)
		pinv = self._make_pos_invoice()
		rows = [
			{"item_code": ITEM_A, "qty": -1, "rate": 50, "pos_invoice_item": pinv.items[0].name},
			{"item_code": ITEM_MA, "qty": -1, "rate": 45, "pos_invoice_item": pinv.items[1].name},
		]
		result = validate_return_items(pinv.name, rows, doctype="POS Invoice")
		self.assertFalse(result["valid"])
		self.assertIn("Row #2", result["message"])
		rows[1]["rate"] = ITEM_MA_PRICE
		self.assertEqual(validate_return_items(pinv.name, rows, doctype="POS Invoice"), {"valid": True})

	def test_return_row_without_link_rejected(self):
		sale = self._sale([_line(self.ctx, ITEM_A), _line(self.ctx, ITEM_B)])
		result = validate_return_items(sale.name, self._rows(sale, drop_link=(ITEM_B,)))
		self.assertFalse(result["valid"])
		self.assertIn("Row #2", result["message"])
		self.assertIn("not linked", result["message"])

		# A POS Invoice row carrying the Sales Invoice link is not linked either
		pinv = self._make_pos_invoice()
		rows = [{"item_code": ITEM_A, "qty": -1, "rate": 50, "sales_invoice_item": pinv.items[0].name}]
		result = validate_return_items(pinv.name, rows, doctype="POS Invoice")
		self.assertFalse(result["valid"])
		self.assertIn("Row #1", result["message"])
		self.assertIn("not linked", result["message"])

	# ------------------------------------------------------------------
	# Refund amount
	# ------------------------------------------------------------------

	def test_inclusive_tax_header_discount_refund_equals_paid(self):
		# 2 x 50 + 1 x 80 = 180 incl. 15% VAT, less a 18.00 header (coupon) discount
		sale = self._sale(
			[_line(self.ctx, ITEM_A, qty=2), _line(self.ctx, ITEM_B)],
			inclusive=True,
			discount_amount=18,
		)
		self.assertTrue(all(t.included_in_print_rate for t in sale.taxes))
		self.assertEqual(flt(sale.discount_amount), 18)
		self.assertEqual(flt(sale.grand_total), 162)
		self.assertEqual(flt(sale.paid_amount), 162)

		prepared = prepare_return_invoice(sale.name)
		# Line rates stay at the original rates; the server sets the discount.
		self.assertEqual({i["item_code"]: i["rate"] for i in prepared["items"]}, {ITEM_A: 50.0, ITEM_B: 80.0})
		# The dict carries no header discount a caller could send back.
		self.assertEqual(flt(prepared["discount_amount"]), 0)
		self.assertEqual(flt(prepared["additional_discount_percentage"]), 0)

		payload, refund = self._frontend_return_payload(prepared)
		self.assertEqual(refund, flt(sale.paid_amount, 2))
		# A client-sent discount is replaced by the server's.
		payload["discount_amount"] = -50
		payload["apply_discount_on"] = "Net Total"
		ret_doc = self._submit_return(payload)
		self.assertEqual(flt(ret_doc.discount_amount), -18)
		self.assertEqual(ret_doc.apply_discount_on, "Grand Total")
		self.assertEqual(flt(-ret_doc.grand_total, 2), flt(sale.paid_amount, 2))
		self.assertEqual(flt(-ret_doc.paid_amount, 2), flt(sale.paid_amount, 2))

	def test_uneven_header_discount_full_return_refunds_paid(self):
		# 3 x 33.33 = 99.99 less 10.00: 89.99 paid, and 10 / 3 is not a whole cent
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=33.33)], discount_amount=10)
		self.assertEqual(flt(sale.paid_amount), 89.99)

		payload, refund = self._frontend_return_payload(prepare_return_invoice(sale.name))
		self.assertEqual(refund, 89.99)
		ret_doc = self._submit_return(payload)
		self.assertEqual(flt(ret_doc.discount_amount), -10)
		self.assertEqual(flt(-ret_doc.grand_total, 2), 89.99)

	def test_partial_returns_sum_to_paid(self):
		sale = self._sale([_line(self.ctx, ITEM_C, qty=3, price_list_rate=33.33)], discount_amount=10)

		payload, refund = self._frontend_return_payload(prepare_return_invoice(sale.name), {ITEM_C: 1})
		first = self._submit_return(payload)
		self.assertEqual(flt(first.discount_amount), -3.33)
		self.assertEqual(flt(-first.grand_total, 2), 30.0)
		self.assertEqual(refund, 30.0)

		prepared = prepare_return_invoice(sale.name)
		self.assertEqual(prepared["items"][0]["remaining_qty"], 2)
		payload, refund = self._frontend_return_payload(prepared)
		second = self._submit_return(payload)
		# The return that completes the invoice takes the rest of the discount
		self.assertEqual(flt(second.discount_amount), -6.67)
		self.assertEqual(flt(-second.grand_total, 2), 59.99)
		self.assertEqual(refund, 59.99)

		self.assertEqual(flt(-(first.grand_total + second.grand_total), 2), flt(sale.paid_amount, 2))

	def test_free_item_never_returned_discount_still_sums_to_paid(self):
		# 3 x 33.33 + a free item (no weight), less 10.00; three single returns
		# of the paid item, the free item kept: the third takes the remainder.
		free = dict(_line(self.ctx, ITEM_A, price_list_rate=0), rate=0, is_free_item=1)
		# The free item comes from an offer (free rows must be backed, Task 8i).
		offer = {"free_items": [{"item_code": ITEM_A, "qty": 1, "pricing_rules": "_PNXT_TEST_RS_GIFT"}]}
		with patch.object(invoices, "_offer_evaluator", return_value=lambda *args, **kwargs: offer):
			sale = self._sale(
				[_line(self.ctx, ITEM_C, qty=3, price_list_rate=33.33), free], discount_amount=10
			)
		self.assertEqual(flt(sale.paid_amount), 89.99)

		discounts, refunds = [], []
		for _ in range(3):
			prepared = prepare_return_invoice(sale.name)
			payload, refund = self._frontend_return_payload(prepared, {ITEM_C: 1, ITEM_A: 0})
			ret = self._submit_return(payload)
			discounts.append(flt(-ret.discount_amount))
			refunds.append(flt(-ret.grand_total, 2))
			self.assertEqual(refund, refunds[-1])

		self.assertEqual(discounts, [3.33, 3.33, 3.34])
		self.assertEqual(flt(sum(discounts), 2), 10)
		self.assertEqual(flt(sum(refunds), 2), flt(sale.paid_amount, 2))

	def _round_to_whole_units(self):
		"""ERPNext rounds to the currency's smallest fraction (USD: 0.01, so 89.99 stays)."""
		currency = self.ctx.currency
		saved = frappe.db.get_value("Currency", currency, "smallest_currency_fraction_value")

		def restore():
			frappe.db.set_value("Currency", currency, "smallest_currency_fraction_value", saved)
			frappe.clear_document_cache("Currency", currency)

		self.addCleanup(restore)
		frappe.db.set_value("Currency", currency, "smallest_currency_fraction_value", 1)
		frappe.clear_document_cache("Currency", currency)

	def test_rounded_total_full_return_refunds_paid(self):
		# Rounding on, to whole units: 89.99 is rounded to 90.00 and 90.00 is paid.
		self._round_to_whole_units()
		sale = self._sale(
			[_line(self.ctx, ITEM_C, qty=3, price_list_rate=33.33)], discount_amount=10, rounded=True
		)
		self.assertEqual(flt(sale.grand_total), 89.99)
		self.assertEqual(flt(sale.rounded_total), 90)
		self.assertEqual(flt(sale.paid_amount), 90)

		payload, refund = self._frontend_return_payload(prepare_return_invoice(sale.name))
		# The rows add up to 89.99; the return is rounded the same way as the sale,
		# so the dialog refunds 90.00 (D-R2-16, returnRefund.js).
		self.assertEqual(refund, 89.99)
		payload["payments"][0]["amount"] = -90
		ret_doc = self._submit_return(payload)
		self.assertEqual(flt(ret_doc.grand_total), -89.99)
		self.assertEqual(flt(-ret_doc.rounded_total, 2), flt(sale.paid_amount, 2))
		self.assertEqual(flt(-ret_doc.paid_amount, 2), flt(sale.paid_amount, 2))

	def test_normal_return_unchanged(self):
		# Exclusive tax, no header discount: return rates are the original rates.
		sale = self._sale([_line(self.ctx, ITEM_A, qty=2), _line(self.ctx, ITEM_B)], inclusive=False)
		self.assertFalse(any(t.included_in_print_rate for t in sale.taxes))
		self.assertEqual(flt(sale.grand_total), 207)

		prepared = prepare_return_invoice(sale.name)
		by_code = {i["item_code"]: i for i in prepared["items"]}
		self.assertEqual(by_code[ITEM_A]["rate"], 50.0)
		self.assertEqual(by_code[ITEM_B]["rate"], 80.0)
		self.assertEqual(by_code[ITEM_A]["rate_with_tax"], 57.5)
		self.assertEqual(by_code[ITEM_B]["rate_with_tax"], 92.0)

		payload, refund = self._frontend_return_payload(prepared)
		self.assertEqual(flt(refund, 2), flt(sale.grand_total, 2))
		self.assertEqual(validate_return_items(sale.name, payload["items"]), {"valid": True})
