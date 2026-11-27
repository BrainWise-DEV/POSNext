# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Two cashiers act on the SAME invoice at the same instant. TEST SITES ONLY.

The locks Frappe takes when saving an existing invoice are what stop two writers from both
succeeding. This checks that the invariant still holds, for any site-config override:

* ``submit_submit``: two ``submit_invoice`` calls for one draft (no idempotency key, the worst case)
* ``edit_submit``  : one ``update_invoice`` edit and one ``submit_invoice`` of the same draft

Invariants (printed per round): exactly one submit succeeds, the invoice is submitted exactly
once, stock moved once (one Stock Ledger Entry per line) and GL was posted once.

	bench --site <test-site> execute pos_next.benchmarks.race_probe.run \
		--kwargs '{"mode": "submit_submit", "rounds": 5, "conf": {}}'
"""

import json
import multiprocessing as mp
import os
import time

import frappe


def _worker(args: dict) -> dict:
	import pos_next.api.invoices as invoices

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	for key, value in (args["conf"] or {}).items():
		frappe.conf[key] = value
	frappe.set_user("Administrator")
	while time.time() < args["start_at"]:
		time.sleep(0.0005)
	out = {"action": args["action"]}
	try:
		if args["action"] == "submit":
			invoices.submit_invoice(invoice=json.dumps(args["draft"], default=str), data="{}")
		else:
			edited = dict(args["draft"])
			edited["remarks"] = "edited concurrently"
			invoices.update_invoice(json.dumps(edited, default=str))
		frappe.db.commit()
		out["ok"] = True
	except Exception as exc:
		frappe.db.rollback()
		out["error"] = type(exc).__name__
	frappe.destroy()
	return out


def run(
	pos_profile: str = "Cairo Branch", mode: str = "submit_submit", rounds: int = 5, conf: dict | None = None
) -> None:
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.concurrent_benchmark import cleanup
	from pos_next.benchmarks.submit_benchmark import _build_invoice, _create_stocked_items

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	started = frappe.utils.now_datetime()
	items = _create_stocked_items(profile, 6, prefix="_BENCH-DVP")
	frappe.db.commit()
	lines = 4
	actions = ("submit", "submit") if mode == "submit_submit" else ("submit", "edit")
	broken = 0
	try:
		for rnd in range(rounds):
			marker = f"_BENCHC-race-{mode}-{rnd}-{int(time.time())}"
			data = _build_invoice(profile, items, lines)
			data["po_no"] = marker
			draft = invoices.update_invoice(json.dumps(data))
			frappe.db.commit()
			start_at = time.time() + 3
			jobs = [
				{
					"site": site,
					"sites_path": sites_path,
					"draft": draft,
					"conf": conf,
					"start_at": start_at,
					"action": a,
				}
				for a in actions
			]
			with mp.get_context("spawn").Pool(2) as pool:
				results = pool.map(_worker, jobs)
			name = draft["name"]
			row = frappe.db.get_value("Sales Invoice", name, ["docstatus", "remarks"], as_dict=True)
			sle = frappe.db.count("Stock Ledger Entry", {"voucher_no": name, "is_cancelled": 0})
			gl = frappe.db.count("GL Entry", {"voucher_no": name, "is_cancelled": 0})
			submits_ok = sum(1 for r in results if r["action"] == "submit" and r.get("ok"))
			invariant_ok = submits_ok == 1 and row.docstatus == 1 and sle == lines
			broken += 0 if invariant_ok else 1
			print(
				json.dumps(
					{
						"round": rnd,
						"results": [r.get("error") or "ok" for r in results],
						"actions": [r["action"] for r in results],
						"docstatus": row.docstatus,
						"stock_ledger_rows": sle,
						"gl_rows": gl,
						"submitted_exactly_once_and_stock_moved_once": invariant_ok,
					}
				)
			)
		print(
			json.dumps(
				{
					"mode": mode,
					"site_config_overrides": conf or "(defaults)",
					"rounds": rounds,
					"rounds_with_broken_invariant": broken,
				}
			)
		)
	finally:
		print("cleanup:", json.dumps(cleanup(since=started)))
