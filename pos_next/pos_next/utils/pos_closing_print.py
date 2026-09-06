from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe.query_builder import DocType
from frappe.utils import flt
from pypika import Order
from pypika.functions import Sum


def _as_closing_doc(doc):
	if isinstance(doc, str):
		return frappe.get_doc("POS Closing Shift", doc)
	return doc


def _collect_parent_targets(pos_transactions: Iterable) -> set[tuple[str, str]]:
	sales_invoice_targets: set[tuple[str, str]] = set()
	pos_invoices: set[str] = set()

	for row in pos_transactions or []:
		sales_invoice = row.get("sales_invoice")
		pos_invoice = row.get("pos_invoice")

		if sales_invoice:
			sales_invoice_targets.add((sales_invoice, "Sales Invoice"))
			continue

		if pos_invoice:
			pos_invoices.add(pos_invoice)

	return sales_invoice_targets | _get_pos_invoice_parent_targets(pos_invoices)


def _get_pos_invoice_parent_targets(pos_invoices: set[str]) -> set[tuple[str, str]]:
	if not pos_invoices:
		return set()

	targets: set[tuple[str, str]] = set()
	rows = frappe.get_all(
		"POS Invoice",
		filters={"name": ["in", list(pos_invoices)]},
		fields=["name", "consolidated_invoice"],
		limit_page_length=0,
	)

	for row in rows:
		consolidated_invoice = row.get("consolidated_invoice")
		if consolidated_invoice:
			targets.add((consolidated_invoice, "Sales Invoice"))
		else:
			targets.add((row.get("name"), "POS Invoice"))

	return targets


def _fetch_items_for_targets(parent_targets: set[tuple[str, str]]) -> list[dict]:
	if not parent_targets:
		return []

	sales_invoice_item = DocType("Sales Invoice Item")
	amount_sum = Sum(sales_invoice_item.amount)
	qty_sum = Sum(sales_invoice_item.qty)

	condition = None
	for parent, parenttype in sorted(parent_targets):
		current = (sales_invoice_item.parent == parent) & (sales_invoice_item.parenttype == parenttype)
		condition = current if condition is None else (condition | current)

	query = (
		frappe.qb.from_(sales_invoice_item)
		.select(
			sales_invoice_item.item_code,
			sales_invoice_item.item_name,
			qty_sum.as_("qty"),
			amount_sum.as_("amount"),
		)
		.where(condition)
		.groupby(sales_invoice_item.item_code, sales_invoice_item.item_name)
		.orderby(amount_sum, order=Order.desc)
	)

	return query.run(as_dict=True)


def get_items_sold(doc) -> list[dict]:
	closing_doc = _as_closing_doc(doc)
	parent_targets = _collect_parent_targets(closing_doc.get("pos_transactions"))
	items = _fetch_items_for_targets(parent_targets)

	return [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"qty": flt(row.get("qty")),
			"amount": flt(row.get("amount")),
		}
		for row in items
	]
