# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Probe: N requests submit the SAME sale (same offline_id / client_request_id) at once.

TEST SITES ONLY (commits data, then removes it with concurrent_benchmark.cleanup).
Shows which errors a double-tap / retry produces and whether exactly one invoice results.

	bench --site <test-site> execute pos_next.benchmarks.dup_submit_probe.run \
		--kwargs '{"requests": 3, "key": "offline_id"}'
"""

import json
import multiprocessing as mp
import os
import time

import frappe


def _worker(args: dict) -> dict:
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.submit_benchmark import _build_invoice

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", args["pos_profile"])
	items = [frappe._dict(name=c, item_name=c, stock_uom="Nos") for c in args["item_codes"]]
	data = _build_invoice(profile, items, 5)
	data["po_no"] = "_BENCHC-dup-probe"
	data[args["key"]] = args["dup_id"]

	while time.time() < args["start_at"] + args["worker"] * args["stagger_s"]:
		time.sleep(0.001)
	started = time.perf_counter()
	out = {"worker": args["worker"]}
	try:
		result = invoices.submit_invoice(invoice=json.dumps(data), data="{}")
		frappe.db.commit()
		out["invoice"] = result.get("name")
		out["duplicate_prevented"] = bool(result.get("duplicate_prevented"))
	except Exception as exc:
		frappe.db.rollback()
		out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
	out["ms"] = int((time.perf_counter() - started) * 1000)
	frappe.destroy()
	return out


def run(
	pos_profile: str = "Cairo Branch",
	requests: int = 3,
	key: str = "offline_id",
	rounds: int = 3,
	stagger_ms: int = 0,
) -> None:
	"""``stagger_ms``: worker N starts N*stagger_ms later, like a retry while the first is running."""
	from pos_next.benchmarks.concurrent_benchmark import cleanup
	from pos_next.benchmarks.submit_benchmark import _create_stocked_items

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	started = frappe.utils.now_datetime()
	codes = [i.name for i in _create_stocked_items(profile, 5, prefix="_BENCH-DVP")]
	frappe.db.commit()
	try:
		for rnd in range(rounds):
			start_at = time.time() + 3
			jobs = [
				{
					"site": site,
					"sites_path": sites_path,
					"pos_profile": pos_profile,
					"item_codes": codes,
					"key": key,
					"dup_id": f"{'pos_online_' if key == 'client_request_id' else ''}_BENCHC-dup-{int(time.time())}-{rnd}",
					"worker": w,
					"start_at": start_at,
					"stagger_s": stagger_ms / 1000,
				}
				for w in range(requests)
			]
			with mp.get_context("spawn").Pool(requests) as pool:
				results = pool.map(_worker, jobs)
			invoices_made = {
				r["invoice"] for r in results if "invoice" in r and not r.get("duplicate_prevented")
			}
			print(
				json.dumps(
					{
						"round": rnd,
						"key": key,
						"distinct_new_invoices": len(invoices_made),
						"results": [
							{k: v for k, v in r.items() if k != "worker"}
							for r in sorted(results, key=lambda r: r["worker"])
						],
					}
				)
			)
	finally:
		print("cleanup:", json.dumps(cleanup(since=started)))
