# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Realistic checkout workload to look for deadlocks. TEST SITES ONLY.

Several cashiers check out at the same time, like a busy shop:

* shared customers that have a loyalty program and a funded wallet, so the same
  customer is often being sold to by more than one cashier at once
* overlapping items, picked in random order, in carts of 3..max_lines lines
* a mix of payments: cash, cash + wallet ("Redeem Points", a wallet payment mode)
  and wallet only, plus a sales person on every line
* optionally, an edit of the freshly created draft before it is submitted
* the checkout runs as the cashier screen does it: ``update_invoice`` (commit) then
  ``submit_invoice`` (commit)

Each failure is classified from the application's own deadlock log
(``logs/pos_next_deadlock.log``, written by ``pos_next.diagnostics``): which operation,
which child table, which statement. Everything created is removed afterwards.

	bench --site <test-site> execute pos_next.benchmarks.workload_probe.run \
		--kwargs '{"cashiers": 12, "invoices_per_cashier": 15}'
"""

import json
import multiprocessing as mp
import os
import random
import time
from collections import Counter

import frappe

from pos_next.benchmarks.concurrent_benchmark import CUSTOMER_PREFIX

WALLET_MODE = "Redeem Points"
LOYALTY_PROGRAM = "Wallet"
WALLET_FUNDING = 1_000_000


def _setup_customers(profile, count: int) -> list[str]:
	"""Customers with the loyalty program and a valid, funded wallet for the profile's company."""
	from pos_next.pos_next.doctype.wallet.wallet import create_customer_wallet
	from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

	group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	names = []
	for i in range(count):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"{CUSTOMER_PREFIX}-{i:02d}",
				"customer_group": group,
				"territory": territory,
				"customer_type": "Individual",
				"loyalty_program": LOYALTY_PROGRAM,
			}
		).insert(ignore_permissions=True)
		wallet = frappe.db.get_value(
			"Wallet", {"customer": customer.name, "company": profile.company}, "name"
		)
		if not wallet:
			wallet = create_customer_wallet(customer.name, profile.company, "Debtors - BPD").name
		create_wallet_credit(wallet, WALLET_FUNDING, source_type="Manual Adjustment", remarks="benchmark")
		names.append(customer.name)
	return names


def _set_wallet_mode_account(company: str, account: str | None) -> str | None:
	"""Point the wallet payment mode at a receivable account (a wallet needs one).

	Returns the previous account so the caller can restore it. ``account=None`` is a no-op.
	"""
	if not account:
		return None
	mode = frappe.get_doc("Mode of Payment", WALLET_MODE)
	row = next((r for r in mode.accounts if r.company == company), None)
	previous = row.default_account if row else None
	if row is None:
		mode.append("accounts", {"company": company, "default_account": account})
	else:
		row.default_account = account
	mode.save(ignore_permissions=True)
	frappe.db.commit()
	return previous


def _payments(rng, total: float, wallet_share: float) -> tuple[list[dict], str]:
	roll = rng.random()
	if roll >= wallet_share:
		return [{"mode_of_payment": "Cash", "amount": round(total, 2)}], "cash"
	if roll < wallet_share * 0.65:
		wallet = round(total * rng.choice([0.3, 0.5, 0.7]), 2)
		return [
			{"mode_of_payment": "Cash", "amount": round(total - wallet, 2)},
			{"mode_of_payment": WALLET_MODE, "amount": wallet},
		], "cash+wallet"
	return [{"mode_of_payment": WALLET_MODE, "amount": round(total, 2)}], "wallet"


def _worker(args: dict) -> list[dict]:
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.submit_benchmark import _build_invoice

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	if args["lock_wait_s"]:
		# Session-scoped: shorten this worker's lock wait so 1205s show up in a short run.
		frappe.db.sql(f"SET SESSION innodb_lock_wait_timeout = {int(args['lock_wait_s'])}")
	for key, value in (args["conf"] or {}).items():
		frappe.conf[key] = value  # per-worker site-config overrides, to compare behaviours
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", args["pos_profile"])
	pool = [frappe._dict(name=c, item_name=c, stock_uom="Nos") for c in args["item_codes"]]
	rng = random.Random(args["seed"])

	while time.time() < args["start_at"]:
		time.sleep(0.001)

	out = []
	for n in range(args["invoices"]):
		lines = rng.randint(3, args["max_lines"])
		hot = pool[: args["hot_items"]]  # every cart contains these (fast-moving items)
		picked = hot + rng.sample(pool[args["hot_items"] :], max(lines - len(hot), 0))
		rng.shuffle(picked)  # random order
		if args["sorted_items"]:
			picked.sort(key=lambda i: i.name)  # same subset, one consistent order
		data = _build_invoice(profile, picked, lines)
		data["customer"] = rng.choice(args["customers"])
		data["po_no"] = f"_BENCHC-workload-{args['run_id']}-{args['cashier']}-{n}"
		total = sum(r["qty"] * r["rate"] for r in data["items"])
		data["payments"], kind = _payments(rng, total, args["wallet_share"])
		record = {"kind": kind, "phase": "update", "ms": 0}
		started = time.perf_counter()
		try:
			draft = invoices.update_invoice(json.dumps(data))
			frappe.db.commit()
			record["draft_ms"] = int((time.perf_counter() - started) * 1000)
			if rng.random() < args["edit_ratio"]:
				record["phase"] = "edit"
				draft["remarks"] = "benchmark edit"
				draft = invoices.update_invoice(json.dumps(draft, default=str))
				frappe.db.commit()
			record["phase"] = "submit"
			invoices.submit_invoice(invoice=json.dumps(draft, default=str), data="{}")
			frappe.db.commit()
			record["ok"] = True
		except Exception as exc:
			frappe.db.rollback()
			record["error"] = type(exc).__name__
			record["message"] = str(exc)[:100]
		record["ms"] = int((time.perf_counter() - started) * 1000)
		out.append(record)
	frappe.destroy()
	return out


def _read_deadlock_log(since_epoch: float) -> list[dict]:
	path = frappe.get_site_path("logs", "pos_next_deadlock.log")
	events = []
	try:
		with open(path) as fh:
			for line in fh:
				if "{" not in line:
					continue
				try:
					events.append(json.loads(line[line.index("{") :]))
				except ValueError:
					continue
	except OSError:
		return []
	return events


def _percentile(values: list[int], pct: float) -> int:
	if not values:
		return 0
	values = sorted(values)
	return values[min(len(values) - 1, round(pct / 100 * (len(values) - 1)))]


def run(
	pos_profile: str = "Cairo Branch",
	cashiers: int = 12,
	invoices_per_cashier: int = 15,
	max_lines: int = 25,
	pool: int = 40,
	customers: int = 4,
	edit_ratio: float = 0.1,
	wallet_share: float = 0.0,
	sorted_items: bool = False,
	hot_items: int = 0,
	lock_wait_s: int | None = None,
	conf: dict | None = None,
	seed: int = 1,
) -> None:
	from pos_next.benchmarks.concurrent_benchmark import cleanup
	from pos_next.benchmarks.submit_benchmark import _create_stocked_items

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	started = frappe.utils.now_datetime()
	started_epoch = time.time()
	codes = [i.name for i in _create_stocked_items(profile, pool, prefix="_BENCH-DVP")]
	# customers=0: everyone checks out to the POS Profile's default customer (no loyalty customers)
	cust = _setup_customers(profile, customers) if customers else [profile.customer]
	frappe.db.commit()
	run_id = str(int(time.time()))
	log_before = len(_read_deadlock_log(started_epoch))
	wallet_account = "Debtors - BPD" if wallet_share else None
	original_wallet_account = _set_wallet_mode_account(profile.company, wallet_account)
	try:
		start_at = time.time() + 3
		jobs = [
			{
				"site": site,
				"sites_path": sites_path,
				"pos_profile": pos_profile,
				"item_codes": codes,
				"customers": cust,
				"invoices": invoices_per_cashier,
				"max_lines": max_lines,
				"edit_ratio": edit_ratio,
				"wallet_share": wallet_share,
				"sorted_items": sorted_items,
				"hot_items": hot_items,
				"lock_wait_s": lock_wait_s,
				"conf": conf,
				"cashier": c,
				"seed": seed * 1000 + c,
				"run_id": run_id,
				"start_at": start_at,
			}
			for c in range(cashiers)
		]
		with mp.get_context("spawn").Pool(cashiers) as p:
			results = [r for batch in p.map(_worker, jobs) for r in batch]
		wall = time.time() - start_at

		ok = [r for r in results if r.get("ok")]
		failed = [r for r in results if "error" in r]
		by_kind = {
			kind: {
				"total": sum(1 for r in results if r["kind"] == kind),
				"failed": sum(1 for r in failed if r["kind"] == kind),
			}
			for kind in ("cash", "cash+wallet", "wallet")
		}
		app_events = _read_deadlock_log(started_epoch)[log_before:]
		located = Counter(
			(
				e.get("kind"),
				e.get("operation"),
				(e.get("failing") or {}).get("doctype"),
				(e.get("failing") or {}).get("db_call"),
				e.get("statement"),
				(e.get("connection") or {}).get("innodb_lock_wait_timeout_session"),
			)
			for e in app_events
		)
		print(
			json.dumps(
				{
					"item_order": "sorted" if sorted_items else "random",
					"pool": pool,
					"hot_items": hot_items,
					"lock_wait_s": lock_wait_s,
					"worker_site_config": conf or "(defaults)",
					"customers": customers or f"default ({profile.customer})",
					"cashiers": cashiers,
					"invoices": len(results),
					"ok": len(ok),
					"failed": len(failed),
					"failed_by_phase": dict(Counter(r["phase"] for r in failed)),
					"error_types": dict(Counter(r["error"] for r in failed)),
					"error_messages": dict(
						Counter(f"{r['phase']}: {r['message']}" for r in failed).most_common(5)
					),
					"by_payment_kind": by_kind,
					"draft_p50_ms": _percentile([r["draft_ms"] for r in results if "draft_ms" in r], 50),
					"draft_p95_ms": _percentile([r["draft_ms"] for r in results if "draft_ms" in r], 95),
					"p50_ms": _percentile([r["ms"] for r in ok], 50),
					"p95_ms": _percentile([r["ms"] for r in ok], 95),
					"invoices_per_min": round(len(ok) / wall * 60, 1) if wall else 0,
					"deadlock_log_entries": len(app_events),
					"deadlock_locations": [
						{
							"count": n,
							"kind": kind,
							"operation": op,
							"child_doctype": doctype,
							"db_call": call,
							"last_statement": stmt,
							"session_lock_wait_s": wait,
						}
						for (kind, op, doctype, call, stmt, wait), n in located.most_common()
					],
				}
			)
		)
	finally:
		# Restore the site's own configuration for the wallet payment mode.
		if wallet_account:
			mode = frappe.get_doc("Mode of Payment", WALLET_MODE)
			for row in mode.accounts:
				if row.company == profile.company:
					row.default_account = original_wallet_account
			if original_wallet_account is None:
				mode.accounts = [r for r in mode.accounts if r.company != profile.company]
			mode.save(ignore_permissions=True)
			frappe.db.commit()
			print("wallet mode account restored to:", original_wallet_account)
		print("cleanup:", json.dumps(cleanup(since=started)))
