# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Concurrent-cashier benchmark for the POS submit path. TEST SITES ONLY.

Unlike ``submit_benchmark`` this COMMITS data (several processes cannot share one
transaction), then removes everything it created: invoices, stock entry, ledger
rows, sync rows, bins and items, all identified by the ``_BENCHC`` prefix or the
invoice names it recorded.

	bench --site <test-site> execute pos_next.benchmarks.concurrent_benchmark.run \
		--kwargs '{"cashiers": [1, 4, 8], "invoices_per_cashier": 5, "lines": 100}'

``isolation="READ COMMITTED"`` sets the workers' session level before their first
transaction, which models the server-side setting ``transaction-isolation =
READ-COMMITTED``. It cannot be switched on from inside a request: the request's
transaction has already started by then and the change has no effect.

Every cashier sells the same items (worst case: all contend on the same Bin and
Stock Ledger rows) and the same naming series.
"""

import json
import multiprocessing as mp
import os
import time

import frappe

PREFIX = "_BENCHC-ITEM"
ITEM_PREFIXES = (PREFIX, "_BENCH-DVP")  # items created by this tool and by desk_vs_pos
SYNC_PREFIX = "pos_online_benchc"


def _trace_series_lock() -> dict:
	"""Record every SQL statement of this connection that takes >=300 ms (shows what blocks)."""
	state = {"wait": 0, "hold": 0, "acquired": None, "slow": []}
	orig_sql, orig_commit = frappe.db.sql, frappe.db.commit

	def sql(*a, **k):
		query = str(a[0] if a else k.get("query", ""))
		started = time.perf_counter()
		try:
			return _sql_inner(query, a, k)
		finally:
			elapsed = int((time.perf_counter() - started) * 1000)
			if elapsed >= 300:
				state["slow"].append((elapsed, " ".join(query.split())[:140]))

	def _sql_inner(query, a, k):
		if "tabSeries" in query and "FOR UPDATE" in query.upper():
			t0 = time.perf_counter()
			try:
				return orig_sql(*a, **k)
			finally:
				state["acquired"] = time.perf_counter()
				state["wait"] = int((state["acquired"] - t0) * 1000)
		return orig_sql(*a, **k)

	def commit(*a, **k):
		if state["acquired"] is not None:
			state["hold"] = int((time.perf_counter() - state["acquired"]) * 1000)
			state["acquired"] = None
		return orig_commit(*a, **k)

	frappe.db.sql, frappe.db.commit = sql, commit
	return state


def _worker(args: dict) -> list[dict]:
	"""One cashier process: its own DB connection, commit per invoice."""
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.submit_benchmark import _build_invoice

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	if args.get("isolation"):
		# Session-scoped, needs no special privilege; takes effect for this worker only.
		frappe.db.sql(f"SET SESSION TRANSACTION ISOLATION LEVEL {args['isolation']}")
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", args["pos_profile"])
	items = [frappe._dict(name=c, item_name=c, stock_uom="Nos") for c in args["item_codes"]]

	while time.time() < args["start_at"]:
		time.sleep(0.001)

	frappe.flags.pos_next_collect_perf = True
	lock = _trace_series_lock()
	out = []
	for n in range(args["count"]):
		frappe.flags.pos_next_perf_records = []
		data = _build_invoice(profile, items, args["lines"])
		t0 = time.perf_counter()
		rec = {"cashier": args["cashier"], "n": n}
		try:
			draft = invoices.update_invoice(json.dumps(data))
			frappe.db.commit()  # production: update_invoice is its own request and commits
			submitted = invoices.submit_invoice(
				invoice=json.dumps(draft, default=str),
				data=json.dumps(
					{"client_request_id": f"{SYNC_PREFIX}-{args['run_id']}-{args['cashier']}-{n}"}
				),
			)
			frappe.db.commit()
			rec["name"] = submitted["name"]
			rec["slow"], lock["slow"] = list(lock["slow"]), []
			rec["steps"] = {r["op"]: r["steps_ms"] for r in frappe.flags.pos_next_perf_records}
		except Exception as exc:
			frappe.db.rollback()
			rec["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
			lock["slow"] = []
		rec["ms"] = int((time.perf_counter() - t0) * 1000)
		out.append(rec)
	frappe.destroy()
	return out


def _slowest(results: list[dict]) -> list:
	"""Statements that took >=300 ms, grouped by shape (count, total ms)."""
	agg: dict[str, list] = {}
	for r in results:
		for ms, shape in r.get("slow", []):
			slot = agg.setdefault(shape, [0, 0])
			slot[0] += 1
			slot[1] += ms
	return [[n, ms, shape] for shape, (n, ms) in sorted(agg.items(), key=lambda kv: -kv[1][1])[:6]]


def _percentile(values: list[int], pct: float) -> int:
	if not values:
		return 0
	values = sorted(values)
	return values[min(len(values) - 1, int(round(pct / 100 * (len(values) - 1))))]


def _setup(profile, line_count: int) -> tuple[list[str], str]:
	from pos_next.benchmarks.submit_benchmark import _create_stocked_items

	items = _create_stocked_items(profile, line_count, prefix=PREFIX)
	frappe.db.commit()
	entry = frappe.db.get_value("Stock Entry Detail", {"item_code": items[0].name, "docstatus": 1}, "parent")
	return [i.name for i in items], entry


def _benchmark_invoices() -> list[str]:
	"""Invoices created by any benchmark run: sync rows, po_no marker, or bench items."""
	names = {
		n
		for n in frappe.get_all(
			"Offline Invoice Sync",
			filters={"offline_id": ["like", "%BENCHC%"]},
			pluck="sales_invoice",
		)
		if n
	}
	names.update(frappe.get_all("Sales Invoice", filters={"po_no": ["like", "_BENCHC%"]}, pluck="name"))
	for prefix in ITEM_PREFIXES:
		names.update(
			frappe.get_all(
				"Sales Invoice Item", filters={"item_code": ["like", f"{prefix}%"]}, pluck="parent"
			)
		)
	return sorted(names)


def _cancel_and_delete(doctype: str, name: str) -> None:
	if not frappe.db.exists(doctype, name):
		return  # already removed by an interrupted earlier cleanup
	doc = frappe.get_doc(doctype, name)
	doc.flags.ignore_permissions = True
	if doc.docstatus == 1:
		doc.cancel()
	frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
	frappe.db.commit()


def _remove_wallet_transactions(invoice_names: list[str]) -> None:
	"""Delete the loyalty-credit Wallet Transactions the invoices generated.

	Deleted directly (with their GL rows), not cancelled: cancelling re-posts GL
	through the wallet account, which fails on sites whose wallet account belongs
	to another company. Scope is strictly the benchmark's own invoices.
	"""
	if not invoice_names:
		return
	transactions = frappe.get_all(
		"Wallet Transaction",
		filters={"reference_name": ["in", invoice_names]},
		fields=["name", "wallet"],
	)
	names = [t.name for t in transactions]
	if names:
		frappe.db.delete("GL Entry", {"voucher_type": "Wallet Transaction", "voucher_no": ["in", names]})
		frappe.db.delete("Payment Ledger Entry", {"voucher_no": ["in", names]})
		frappe.db.delete("Wallet Transaction", {"name": ["in", names]})
	for wallet in {t.wallet for t in transactions}:
		frappe.get_doc("Wallet", wallet).update_balance()
	frappe.db.commit()


ERROR_LOG_METHODS = (
	"Loyalty to Wallet Conversion Error",
	"Submit Invoice Error",
	"Update Invoice Error",
)


def _remove_error_logs_for_deleted_invoices(since) -> int:
	"""Delete Error Log rows that point at Sales Invoices which no longer exist.

	Benchmark invoices are committed (so are the error rows their hooks log), then
	deleted. Only rows created since ``since`` (the start of the run) that point at
	invoices which are now gone are removed; older rows and rows about real invoices
	are left alone.
	"""
	import re

	rows = frappe.get_all(
		"Error Log",
		filters={"method": ["in", ERROR_LOG_METHODS], "creation": [">=", since]},
		fields=["name", "error"],
	)
	doomed = []
	for row in rows:
		names = set(re.findall(r"ACC-SINV-\d{4}-\d+", row.error or ""))
		if names and not any(frappe.db.exists("Sales Invoice", n) for n in names):
			doomed.append(row.name)
	if doomed:
		frappe.db.delete("Error Log", {"name": ["in", doomed]})
		frappe.db.commit()
	return len(doomed)


CUSTOMER_PREFIX = "_BENCH-CUST"


def _remove_test_customers() -> None:
	"""Delete the customers, wallets and wallet transactions workload_probe created."""
	wallets = frappe.get_all("Wallet", filters={"customer": ["like", f"{CUSTOMER_PREFIX}%"]}, pluck="name")
	if wallets:
		transactions = frappe.get_all("Wallet Transaction", filters={"wallet": ["in", wallets]}, pluck="name")
		if transactions:
			frappe.db.delete(
				"GL Entry", {"voucher_type": "Wallet Transaction", "voucher_no": ["in", transactions]}
			)
			frappe.db.delete("Payment Ledger Entry", {"voucher_no": ["in", transactions]})
			frappe.db.delete("Wallet Transaction", {"name": ["in", transactions]})
		frappe.db.delete("Wallet", {"name": ["in", wallets]})
	frappe.db.delete("GL Entry", {"party_type": "Customer", "party": ["like", f"{CUSTOMER_PREFIX}%"]})
	frappe.db.delete("Loyalty Point Entry", {"customer": ["like", f"{CUSTOMER_PREFIX}%"]})
	for name in frappe.get_all("Customer", filters={"name": ["like", f"{CUSTOMER_PREFIX}%"]}, pluck="name"):
		frappe.delete_doc("Customer", name, force=1, ignore_permissions=True)
	frappe.db.commit()


def cleanup(since=None) -> dict:
	"""Remove everything benchmark runs created; return leftover counts (all must be 0).

	Safe to re-run after a crash: it works from the sync rows and the item prefix,
	not from in-memory state. Order matters: Wallet Transactions (loyalty credit
	created on submit, with their own GL entries) go first because they link to
	the invoice and block its deletion.
	"""
	invoice_names = _benchmark_invoices()
	_remove_wallet_transactions(invoice_names)

	for name in invoice_names:
		_cancel_and_delete("Sales Invoice", name)

	stock_entries = [
		parent
		for prefix in ITEM_PREFIXES
		for parent in frappe.get_all(
			"Stock Entry Detail", filters={"item_code": ["like", f"{prefix}%"]}, pluck="parent"
		)
	]
	for entry in set(stock_entries):
		_cancel_and_delete("Stock Entry", entry)

	vouchers = [*invoice_names, *stock_entries]
	if vouchers:
		for dt in ("Stock Ledger Entry", "GL Entry", "Payment Ledger Entry"):
			frappe.db.delete(dt, {"voucher_no": ["in", vouchers]})
	for prefix in ITEM_PREFIXES:
		frappe.db.delete("Bin", {"item_code": ["like", f"{prefix}%"]})
		frappe.db.delete("Stock Ledger Entry", {"item_code": ["like", f"{prefix}%"]})
	frappe.db.delete("Offline Invoice Sync", {"offline_id": ["like", "%BENCHC%"]})
	for prefix in ITEM_PREFIXES:
		for code in frappe.get_all("Item", filters={"name": ["like", f"{prefix}%"]}, pluck="name"):
			frappe.delete_doc("Item", code, force=1, ignore_permissions=True)
	frappe.db.commit()

	# Default window: the last 6 hours. run() passes the exact start of its own run.
	since = since or frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-6)
	_remove_test_customers()
	removed_logs = _remove_error_logs_for_deleted_invoices(since)

	return {
		"error_logs_removed": removed_logs,
		"items": sum(frappe.db.count("Item", {"name": ["like", f"{p}%"]}) for p in ITEM_PREFIXES),
		"bins": sum(frappe.db.count("Bin", {"item_code": ["like", f"{p}%"]}) for p in ITEM_PREFIXES),
		"invoices": frappe.db.count("Sales Invoice", {"name": ["in", invoice_names]}) if invoice_names else 0,
		"sle": frappe.db.count("Stock Ledger Entry", {"voucher_no": ["in", vouchers]}) if vouchers else 0,
		"gl": frappe.db.count("GL Entry", {"voucher_no": ["in", vouchers]}) if vouchers else 0,
		"customers": frappe.db.count("Customer", {"name": ["like", f"{CUSTOMER_PREFIX}%"]}),
		"wallets": frappe.db.count("Wallet", {"customer": ["like", f"{CUSTOMER_PREFIX}%"]}),
		"sync_rows": frappe.db.count("Offline Invoice Sync", {"offline_id": ["like", "%BENCHC%"]}),
	}


def run(
	pos_profile: str = "Cairo Branch",
	cashiers: list | None = None,
	invoices_per_cashier: int = 5,
	lines: int = 100,
	disjoint: bool = False,
	isolation: str | None = None,
) -> None:
	"""``disjoint=True``: each cashier sells its own items, so only the naming
	series and other global rows are shared; False: everyone sells the same items."""
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	print(
		f"mode={'disjoint items' if disjoint else 'shared items'} lines={lines} isolation={isolation or 'server default'}"
	)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	run_id = str(int(time.time()))
	run_started = frappe.utils.now_datetime()
	cashier_list = cashiers or [1, 4, 8]
	item_codes, _ = _setup(profile, lines * (max(cashier_list) if disjoint else 1))
	all_names: list[str] = []
	summary = []

	try:
		for n_cashiers in cashier_list:
			frappe.db.commit()
			start_at = time.time() + 3  # let spawned workers connect first
			jobs = [
				{
					"site": site,
					"sites_path": sites_path,
					"pos_profile": pos_profile,
					"item_codes": item_codes[c * lines : (c + 1) * lines] if disjoint else item_codes,
					"count": invoices_per_cashier,
					"lines": lines,
					"cashier": c,
					"isolation": isolation,
					"start_at": start_at,
					"run_id": f"{run_id}-{n_cashiers}",
				}
				for c in range(n_cashiers)
			]
			wall0 = start_at
			with mp.get_context("spawn").Pool(n_cashiers) as pool:
				results = [r for batch in pool.map(_worker, jobs) for r in batch]
			wall = time.time() - wall0

			ok = [r for r in results if "error" not in r]
			errors = [r["error"] for r in results if "error" in r]
			all_names += [r["name"] for r in ok]
			step_median: dict[str, int] = {}
			for op in ("update_invoice", "submit_invoice"):
				for step in {k for r in ok for k in r.get("steps", {}).get(op, {})}:
					vals = [r["steps"][op][step] for r in ok if step in r.get("steps", {}).get(op, {})]
					if _percentile(vals, 50) >= 50:
						step_median[f"{op}.{step}"] = _percentile(vals, 50)
			lat = [r["ms"] for r in ok]
			summary.append(
				{
					"cashiers": n_cashiers,
					"invoices_ok": len(ok),
					"errors": len(errors),
					"error_samples": sorted(set(errors))[:3],
					"p50_ms": _percentile(lat, 50),
					"p95_ms": _percentile(lat, 95),
					"max_ms": max(lat) if lat else 0,
					"wall_s": round(wall, 1),
					"slowest_statements": _slowest(ok),
					"invoices_per_min": round(len(ok) / wall * 60, 1) if wall else 0,
					"median_step_ms(>=50)": step_median,
				}
			)
			print(json.dumps(summary[-1]))
	finally:
		leftovers = cleanup(since=run_started)
		print("cleanup leftovers (all must be 0):", json.dumps(leftovers))
