# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Probe: do concurrent sales that share items deadlock? TEST SITES ONLY.

Several cashiers sell overlapping items (a small pool, random subset, random ORDER per
invoice) at the same time, like a busy shop. Reports errors by type and where in the
code they were raised. ``same_order=True`` is the control: identical item order.

	bench --site <test-site> execute pos_next.benchmarks.deadlock_probe.run \
		--kwargs '{"cashiers": 8, "invoices_per_cashier": 5, "lines": 20, "pool": 30}'
"""

import json
import multiprocessing as mp
import os
import random
import re
import time
from collections import Counter

import frappe


def _where(trace: str) -> str:
	"""Innermost erpnext / pos_next frames of a traceback, for locating the failing statement."""
	frames = re.findall(r'File "[^"]*?/(?:apps/)?((?:erpnext|pos_next)/[^"]+)", line (\d+), in (\w+)', trace)
	return " < ".join(f"{path.split('/')[-1]}:{func}:{line}" for path, line, func in frames[-4:][::-1])


def _worker(args: dict) -> list[dict]:
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.submit_benchmark import _build_invoice

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", args["pos_profile"])
	pool = [frappe._dict(name=c, item_name=c, stock_uom="Nos") for c in args["item_codes"]]
	rng = random.Random(args["seed"])

	while time.time() < args["start_at"]:
		time.sleep(0.001)

	out = []
	for n in range(args["invoices"]):
		picked = rng.sample(pool, args["lines"])
		if args["same_order"]:
			picked.sort(key=lambda i: i.name)
		data = _build_invoice(profile, picked, args["lines"])
		data["po_no"] = f"_BENCHC-deadlock-{args['run_id']}-{args['cashier']}-{n}"
		record = {"step": "update"}
		try:
			draft = invoices.update_invoice(json.dumps(data))
			frappe.db.commit()
			record["step"] = "submit"
			invoices.submit_invoice(invoice=json.dumps(draft, default=str), data="{}")
			frappe.db.commit()
			record["ok"] = True
		except Exception as exc:
			trace = frappe.get_traceback()
			frappe.db.rollback()
			record["error"] = type(exc).__name__
			record["where"] = _where(trace)
		out.append(record)
	frappe.destroy()
	return out


def run(
	pos_profile: str = "Cairo Branch",
	cashiers: int = 8,
	invoices_per_cashier: int = 5,
	lines: int = 20,
	pool: int = 30,
	same_order: bool = False,
) -> None:
	from pos_next.benchmarks.concurrent_benchmark import cleanup
	from pos_next.benchmarks.submit_benchmark import _create_stocked_items

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	started = frappe.utils.now_datetime()
	codes = [i.name for i in _create_stocked_items(profile, pool, prefix="_BENCH-DVP")]
	frappe.db.commit()
	run_id = str(int(time.time()))
	try:
		start_at = time.time() + 3
		jobs = [
			{
				"site": site,
				"sites_path": sites_path,
				"pos_profile": pos_profile,
				"item_codes": codes,
				"invoices": invoices_per_cashier,
				"lines": lines,
				"cashier": c,
				"seed": c + 1,
				"same_order": same_order,
				"run_id": run_id,
				"start_at": start_at,
			}
			for c in range(cashiers)
		]
		with mp.get_context("spawn").Pool(cashiers) as p:
			results = [r for batch in p.map(_worker, jobs) for r in batch]
		ok = sum(1 for r in results if r.get("ok"))
		errors = Counter((r["step"], r["error"], r["where"]) for r in results if "error" in r)
		print(
			json.dumps(
				{
					"same_order": same_order,
					"cashiers": cashiers,
					"invoices": len(results),
					"ok": ok,
					"failed": len(results) - ok,
					"errors": [
						{"count": n, "step": step, "type": err, "where": where}
						for (step, err, where), n in errors.most_common()
					],
				}
			)
		)
	finally:
		print("cleanup:", json.dumps(cleanup(since=started)))
