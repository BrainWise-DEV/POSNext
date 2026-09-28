# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for customer credit from linked POS returns."""

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.query_builder.functions import Sum
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import credit_sales
from pos_next.test_promotions import (
	_resolve_customer_group,
	_resolve_item_group,
	_resolve_mode_of_payment,
	_resolve_territory,
)

CUSTOMER = "_PNXT_CREDIT_CUSTOMER"
ITEM = "_PNXT_CREDIT_ITEM"


class TestLinkedReturnCredit(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all(
			"Company",
			filters={"default_receivable_account": ["is", "set"], "default_income_account": ["is", "set"]},
			fields=["name", "default_receivable_account", "default_income_account", "cost_center"],
			order_by="creation asc",
			limit=1,
		)[0]
		cls.mode_of_payment = _resolve_mode_of_payment(cls.company.name)
		frappe.get_doc(
			doctype="Customer",
			customer_name=CUSTOMER,
			customer_group=_resolve_customer_group(),
			territory=_resolve_territory(),
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
		frappe.get_doc(
			doctype="Item", item_code=ITEM, item_group=_resolve_item_group(), stock_uom="Nos", is_stock_item=0
		).insert(ignore_permissions=True, ignore_if_duplicate=True)

	def setUp(self):
		frappe.db.savepoint("linked_return_credit")

	def tearDown(self):
		frappe.db.rollback(save_point="linked_return_credit")

	def _pos_sale(self, paid, company=None):
		c = company or self.company
		doc = frappe.get_doc(
			doctype="Sales Invoice",
			company=c.name,
			currency=frappe.get_cached_value("Company", c.name, "default_currency"),
			conversion_rate=1,
			customer=CUSTOMER,
			is_pos=1,
			debit_to=c.default_receivable_account,
			cost_center=c.cost_center,
			items=[{"item_code": ITEM, "qty": 1, "rate": 100, "income_account": c.default_income_account}],
			payments=[{"mode_of_payment": self.mode_of_payment, "amount": 100 if paid else 0}],
		)
		return doc.insert(ignore_permissions=True).submit()

	def _linked_return(self, original, update_outstanding_for_self=0):
		ret = make_return_doc("Sales Invoice", original.name)
		ret.update(
			{
				"is_pos": 1,
				"update_outstanding_for_self": update_outstanding_for_self,
				"payments": [],
				"set_posting_time": 1,
				"posting_date": original.posting_date,
				"posting_time": original.posting_time,
			}
		)
		return ret.insert(ignore_permissions=True).submit()

	def _gl_balance(self, name):
		gle = frappe.qb.DocType("GL Entry")
		query = frappe.qb.from_(gle).select(Sum(gle.debit - gle.credit))
		return flt(query.where((gle.against_voucher == name) & (gle.is_cancelled == 0)).run()[0][0])

	def _credit_sources(self, *names):
		sources = credit_sales.get_available_credit(CUSTOMER, self.company.name)
		return [(s["credit_origin"], s["available_credit"]) for s in sources if s["credit_origin"] in names]

	def test_linked_pos_return_credit_is_offered_on_the_original_invoice(self):
		original = self._pos_sale(paid=True)
		ret = self._linked_return(original)

		self.assertLess(frappe.db.get_value("Sales Invoice", ret.name, "outstanding_amount"), 0)
		self.assertEqual(self._gl_balance(ret.name), 0)
		self.assertEqual(self._credit_sources(original.name, ret.name), [(original.name, 100)])

	def test_redeeming_linked_return_credit_settles_every_ledger(self):
		original = self._pos_sale(paid=True)
		ret = self._linked_return(original)
		sale = self._pos_sale(paid=False)
		source = self._credit_sources(original.name, ret.name)[0][0]

		credit_sales.redeem_customer_credit(
			sale.name, [{"type": "Invoice", "credit_origin": source, "credit_to_redeem": 100}]
		)

		self.assertEqual([self._gl_balance(n) for n in (original.name, ret.name, sale.name)], [0, 0, 0])
		self.assertEqual(self._credit_sources(original.name, ret.name), [])
		self.assertEqual(
			str(credit_sales.get_customer_balance(CUSTOMER, self.company.name)["total_credit"]), "0.0"
		)

	def test_customer_balance_counts_linked_return_credit_once(self):
		self._linked_return(self._pos_sale(paid=True))

		balance = credit_sales.get_customer_balance(CUSTOMER, self.company.name)

		self.assertEqual((balance["total_credit"], balance["total_outstanding"]), (100, 0))

	def test_self_updating_linked_return_keeps_its_credit(self):
		original = self._pos_sale(paid=True)
		ret = self._linked_return(original, update_outstanding_for_self=1)

		self.assertEqual(self._credit_sources(original.name, ret.name), [(ret.name, 100)])

	def test_insufficient_credit_message_uses_company_currency(self):
		default_currency = frappe.defaults.get_global_default("currency")
		company = next(
			(
				c
				for c in frappe.get_all(
					"Company",
					filters={
						"default_receivable_account": ["is", "set"],
						"default_income_account": ["is", "set"],
						"default_currency": ["!=", default_currency],
					},
					fields=[
						"name",
						"default_receivable_account",
						"default_income_account",
						"cost_center",
						"default_currency",
					],
					limit=1,
				)
			),
			None,
		)
		if not company:
			self.skipTest(f"No Company with a currency other than the site default {default_currency}")
		_resolve_mode_of_payment(company.name)
		original = self._pos_sale(paid=True, company=company)
		self._linked_return(original)
		rows = [{"type": "Invoice", "credit_origin": original.name, "credit_to_redeem": 100}]
		credit_sales.redeem_customer_credit(self._pos_sale(paid=False, company=company).name, rows)

		symbol = frappe.db.get_value("Currency", company.default_currency, "symbol")
		with self.assertRaisesRegex(frappe.ValidationError, symbol):
			credit_sales.redeem_customer_credit(self._pos_sale(paid=False, company=company).name, rows)
