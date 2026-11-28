# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Fixtures for the invoice submit regression tests: stocked items, a realistic cart, a statement
counter and a business-result fingerprint of a submitted invoice. Used only by tests, which run
inside a transaction the test framework rolls back."""

import re
import time

import frappe
from frappe.utils import flt


def create_stocked_items(
	profile, count: int, prefix: str = "_PNXT_TEST_PERF_ITEM", item_group: str = "All Item Groups"
) -> list[dict]:
	"""Create ``count`` clean stock items with opening stock (rolled back later).

	Existing site stock is not used: demo/legacy ledgers can have inconsistent
	``qty_after_transaction`` values that make real submits fail.
	"""
	rows = []
	items = []
	for i in range(count):
		code = f"{prefix}-{i:04d}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"valuation_rate": 5,
			}
		).insert(ignore_permissions=True)
		rows.append({"item_code": code, "qty": 100000, "basic_rate": 5, "t_warehouse": profile.warehouse})
		items.append(frappe._dict(name=code, item_name=code, stock_uom="Nos"))

	frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": profile.company,
			"items": rows,
		}
	).submit()
	return items


def pick_sales_person() -> str | None:
	"""Some profiles require a Sales Person on every line."""
	return frappe.db.get_value("Sales Person", {"enabled": 1, "is_group": 0}, "name")


def build_invoice(profile: dict, items: list[dict], lines: int) -> dict:
	sales_person = pick_sales_person()
	rows = []
	total = 0.0
	for i in range(lines):
		it = items[i % len(items)]
		rate = 10.0 + (i % 7)
		rows.append(
			{
				"item_code": it.name,
				"item_name": it.item_name,
				"qty": 1,
				"rate": rate,
				"price_list_rate": rate,
				"uom": it.stock_uom,
				"warehouse": profile.warehouse,
				"conversion_factor": 1,
				"discount_percentage": 0,
				"discount_amount": 0,
				"sales_person": sales_person,
			}
		)
		total += rate
	return {
		"doctype": "Sales Invoice",
		"pos_profile": profile.name,
		"customer": profile.customer,
		"items": rows,
		"payments": [{"mode_of_payment": "Cash", "amount": total}],
		"is_pos": 1,
		"update_stock": 1,
	}


class QueryCounter:
	"""Count SQL statements issued through frappe.db.sql and group them by shape."""

	def __enter__(self):
		self.count = 0
		self.by_shape: dict[str, list] = {}
		self._orig = frappe.db.sql

		def counting(*args, **kwargs):
			self.count += 1
			query = args[0] if args else kwargs.get("query", "")
			shape = re.sub(r"\s+", " ", str(query))[:110]
			start = time.perf_counter()
			try:
				return self._orig(*args, **kwargs)
			finally:
				slot = self.by_shape.setdefault(shape, [0, 0.0])
				slot[0] += 1
				slot[1] += time.perf_counter() - start

		frappe.db.sql = counting
		return self

	def __exit__(self, *exc):
		frappe.db.sql = self._orig


def fingerprint(invoice_name: str) -> dict:
	"""Business-visible outcome of a submitted invoice (names/timestamps excluded)."""
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	gl = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Sales Invoice", "voucher_no": invoice_name, "is_cancelled": 0},
		fields=["account", "debit", "credit", "party", "against_voucher", "cost_center"],
		order_by="account, debit, credit",
	)
	sle = frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": "Sales Invoice", "voucher_no": invoice_name, "is_cancelled": 0},
		fields=["item_code", "warehouse", "actual_qty", "valuation_rate", "stock_value_difference"],
		order_by="item_code, actual_qty",
	)
	return {
		"docstatus": doc.docstatus,
		"status": doc.status,
		"totals": [
			flt(doc.total),
			flt(doc.net_total),
			flt(doc.grand_total),
			flt(doc.rounded_total),
			flt(doc.paid_amount),
			flt(doc.change_amount),
			flt(doc.outstanding_amount),
			flt(doc.write_off_amount),
			flt(doc.discount_amount),
		],
		"items": [
			[
				d.item_code,
				flt(d.qty),
				flt(d.rate),
				flt(d.amount),
				flt(d.net_amount),
				flt(d.discount_percentage),
				d.warehouse,
				d.cost_center,
				d.income_account,
			]
			for d in doc.items
		],
		"payments": [[p.mode_of_payment, flt(p.amount), p.account] for p in doc.payments],
		"taxes": [[t.account_head, flt(t.tax_amount)] for t in doc.taxes],
		"sales_team": [
			[t.sales_person, flt(t.allocated_percentage), flt(t.allocated_amount)] for t in doc.sales_team
		],
		"gl": [[g.account, flt(g.debit), flt(g.credit), g.party, g.cost_center] for g in gl],
		"sle": [
			[
				e.item_code,
				e.warehouse,
				flt(e.actual_qty),
				flt(e.valuation_rate),
				flt(e.stock_value_difference),
			]
			for e in sle
		],
	}
