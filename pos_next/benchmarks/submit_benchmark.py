# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Benchmark the POS invoice submit path (update_invoice + submit_invoice).

Run on a TEST site only::

	bench --site <test-site> execute pos_next.benchmarks.submit_benchmark.run \
		--kwargs '{"pos_profile": "Cairo Branch", "line_counts": [10, 50, 100, 200]}'

Every scenario runs inside a transaction that is rolled back at the end, so no
invoice, stock or GL data is left behind. Because nothing is committed, this
measures single-request cost (DB work, hooks, validation) but not cross-process
lock contention; use ``run_concurrent`` for that.

Output: per scenario the wall time, DB query count and the per-step timings
recorded by ``pos_next.perf.StepTimer``.
"""

import json
import time

import frappe
from frappe.utils import flt

from pos_next.api import invoices


def _create_stocked_items(
	profile, count: int, prefix: str = "_BENCH-ITEM", item_group: str = "All Item Groups"
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


def _pick_sales_person() -> str | None:
	"""Some profiles require a Sales Person on every line."""
	return frappe.db.get_value("Sales Person", {"enabled": 1, "is_group": 0}, "name")


def _build_invoice(profile: dict, items: list[dict], lines: int) -> dict:
	sales_person = _pick_sales_person()
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


class _QueryCounter:
	"""Count SQL statements issued through frappe.db.sql and group them by shape."""

	def __enter__(self):
		import re

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


def _run_once(profile, items, lines: int) -> dict:
	frappe.flags.pos_next_collect_perf = True
	frappe.flags.pos_next_perf_records = []

	data = _build_invoice(profile, items, lines)
	with _QueryCounter() as q:
		t0 = time.perf_counter()
		draft = invoices.update_invoice(json.dumps(data))
		t1 = time.perf_counter()
		result = invoices.submit_invoice(invoice=json.dumps(draft, default=str), data="{}")
		t2 = time.perf_counter()

	perf = frappe.flags.pos_next_perf_records
	return {
		"lines": lines,
		"invoice": result.get("name"),
		"grand_total": flt(result.get("grand_total")),
		"update_invoice_ms": int((t1 - t0) * 1000),
		"submit_invoice_ms": int((t2 - t1) * 1000),
		"total_ms": int((t2 - t0) * 1000),
		"queries": q.count,
		"top_queries": [
			{"n": v[0], "ms": int(v[1] * 1000), "sql": k}
			for k, v in sorted(q.by_shape.items(), key=lambda kv: -kv[1][0])[:12]
		],
		"steps": {p["op"]: p["steps_ms"] for p in perf},
	}


def run(pos_profile: str = "Cairo Branch", line_counts: list | None = None, repeat: int = 3) -> None:
	"""Single-process benchmark; rolls back after every run."""
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	counts = line_counts or [10, 50, 100, 200]
	items = _create_stocked_items(profile, max(counts))
	print(f"profile={pos_profile} warehouse={profile.warehouse} distinct_items={len(items)}")

	frappe.db.savepoint("bench_setup")
	for lines in counts:
		runs = []
		for _ in range(repeat):
			try:
				runs.append(_run_once(profile, items, lines))
			finally:
				frappe.db.rollback(save_point="bench_setup")
		best = min(runs, key=lambda r: r["total_ms"])
		print(
			json.dumps(
				{
					"lines": lines,
					"median_total_ms": sorted(r["total_ms"] for r in runs)[len(runs) // 2],
					"best": best,
				},
				indent=1,
				default=str,
			)
		)

	frappe.db.rollback()


def _fingerprint(invoice_name: str) -> dict:
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


def _fingerprint_scenarios(profile, items) -> dict:
	out = {}

	plain = _build_invoice(profile, items, 20)
	out["plain_20"] = plain

	discounted = _build_invoice(profile, items, 15)
	for i, row in enumerate(discounted["items"]):
		if i % 3 == 0:
			row["discount_percentage"] = 10
			row["rate"] = round(row["price_list_rate"] * 0.9, 2)
	discounted["discount_amount"] = 3
	paid = sum(r["qty"] * r["rate"] for r in discounted["items"]) - 3
	discounted["payments"] = [{"mode_of_payment": "Cash", "amount": paid}]
	out["discounted_15"] = discounted

	split = _build_invoice(profile, items, 8)
	total = sum(r["qty"] * r["rate"] for r in split["items"])
	split["payments"] = [
		{"mode_of_payment": "Cash", "amount": round(total / 2, 2) + 5},
		{"mode_of_payment": "Credit Card", "amount": round(total / 2, 2)},
	]
	out["split_payment_8"] = split

	header_pct = _build_invoice(profile, items, 12)
	header_pct["additional_discount_percentage"] = 7.5
	header_pct["apply_discount_on"] = "Net Total"
	total = sum(r["qty"] * r["rate"] for r in header_pct["items"]) * (1 - 0.075)
	header_pct["payments"] = [{"mode_of_payment": "Cash", "amount": round(total, 2) + 20}]
	out["header_percent_discount_12"] = header_pct

	with_free = _build_invoice(profile, items, 10)
	with_free["items"][3].update({"rate": 0, "price_list_rate": 0, "is_free_item": 1})
	with_free["items"][5].update(
		{
			"qty": 3,
			"discount_percentage": 20,
			"rate": round(with_free["items"][5]["price_list_rate"] * 0.8, 2),
		}
	)
	total = sum(r["qty"] * r["rate"] for r in with_free["items"])
	with_free["payments"] = [{"mode_of_payment": "Cash", "amount": total + 10}]
	out["free_item_and_qty_discount_10"] = with_free
	return out


def fingerprint(out_file: str, pos_profile: str = "Cairo Branch") -> None:
	"""Write the business outcome of fixed scenarios to ``out_file`` (JSON).

	Run before and after a change and diff the two files: they must be identical.
	"""
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	items = _create_stocked_items(profile, 30)
	frappe.db.savepoint("bench_fp")
	result = {}
	for label, data in _fingerprint_scenarios(profile, items).items():
		try:
			draft = invoices.update_invoice(json.dumps(data))
			submitted = invoices.submit_invoice(
				invoice=json.dumps(draft, default=str),
				data=json.dumps(
					{
						"change_amount": {
							"split_payment_8": 5,
							"header_percent_discount_12": 20,
							"free_item_and_qty_discount_10": 10,
						}.get(label, 0)
					}
				),
			)
			result[label] = _fingerprint(submitted["name"])
		finally:
			frappe.db.rollback(save_point="bench_fp")
	frappe.db.rollback()
	with open(out_file, "w") as fh:
		json.dump(result, fh, indent=1, sort_keys=True, default=str)
	print(f"wrote {out_file}")
