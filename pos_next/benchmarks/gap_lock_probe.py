# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Does a submit in progress block another cashier's NEW draft? TEST SITES ONLY.

Transaction B runs the real ``submit_invoice`` and is made to hold its locks for ``hold_s``
seconds (a sleep is injected in ``on_submit``, after Frappe has loaded the invoice and every
child table ``FOR UPDATE``). Transaction A, in this process, creates a brand new draft meanwhile.

* ``contended``: A starts while B holds its locks. If A's inserts wait, B is the blocker, and the
  application's own log says which statement A was stuck on.
* ``control``: nobody else is submitting.

A uses ``innodb_lock_wait_timeout = lock_wait_s`` so a block shows as a 1205 within seconds.
Data is committed (B is a separate process) and removed with ``concurrent_benchmark.cleanup``.

	bench --site <test-site> execute pos_next.benchmarks.gap_lock_probe.run
"""

import json
import multiprocessing as mp
import os
import time

import frappe


def _holder(args: dict) -> dict:
	"""Process B: submit a draft, sleeping inside the transaction after its locks are taken."""
	import pos_next.api.invoices as invoices
	from pos_next.overrides.sales_invoice import CustomSalesInvoice

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	for key, value in (args["conf"] or {}).items():
		frappe.conf[key] = value  # e.g. restore Frappe's stock locking for the holder
	frappe.set_user("Administrator")

	real_on_submit = CustomSalesInvoice.on_submit

	def slow_on_submit(self):
		open(args["flag"], "w").write("holding")  # tell the main process the locks are held
		time.sleep(args["hold_s"])
		return real_on_submit(self)

	CustomSalesInvoice.on_submit = slow_on_submit
	started = time.perf_counter()
	out = {}
	try:
		invoices.submit_invoice(invoice=json.dumps(args["draft"], default=str), data="{}")
		frappe.db.commit()
		out["ok"] = True
	except Exception as exc:
		frappe.db.rollback()
		out["error"] = type(exc).__name__
	out["ms"] = int((time.perf_counter() - started) * 1000)
	frappe.destroy()
	return out


def _new_draft(profile, items, label: str, lock_wait_s: int):
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.submit_benchmark import _build_invoice

	data = _build_invoice(profile, items, 3)
	data["po_no"] = f"_BENCHC-gap-{label}"
	frappe.db.sql(f"SET SESSION innodb_lock_wait_timeout = {int(lock_wait_s)}")
	started = time.perf_counter()
	try:
		invoices.update_invoice(json.dumps(data))
		frappe.db.commit()
		result = {"ok": True}
	except Exception as exc:
		frappe.db.rollback()
		result = {"error": type(exc).__name__}
	result["ms"] = int((time.perf_counter() - started) * 1000)
	frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 50")
	return result


def _last_log_entries(since_size: int) -> list[dict]:
	path = frappe.get_site_path("logs", "pos_next_deadlock.log")
	events = []
	try:
		with open(path) as fh:
			fh.seek(since_size)
			for line in fh:
				if "{" in line:
					events.append(json.loads(line[line.index("{") :]))
	except (OSError, ValueError):
		pass
	return events


def run(
	pos_profile: str = "Cairo Branch", hold_s: int = 5, lock_wait_s: int = 2, conf: dict | None = None
) -> None:
	import pos_next.api.invoices as invoices
	from pos_next.benchmarks.concurrent_benchmark import cleanup
	from pos_next.benchmarks.submit_benchmark import _build_invoice, _create_stocked_items

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	started = frappe.utils.now_datetime()
	items = _create_stocked_items(profile, 10, prefix="_BENCH-DVP")
	frappe.db.commit()
	flag = f"/tmp/pos_next_gap_probe_{os.getpid()}.flag"
	log_path = frappe.get_site_path("logs", "pos_next_deadlock.log")

	try:
		# control: nothing else running
		control = _new_draft(profile, items, "control", lock_wait_s)

		# the invoice B will submit (a draft that exists and is committed)
		data = _build_invoice(profile, items, 3)
		data["po_no"] = "_BENCHC-gap-held"
		draft = invoices.update_invoice(json.dumps(data))
		frappe.db.commit()

		if os.path.exists(flag):
			os.remove(flag)
		log_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
		with mp.get_context("spawn").Pool(1) as pool:
			pending = pool.apply_async(
				_holder,
				(
					{
						"site": site,
						"sites_path": sites_path,
						"draft": draft,
						"flag": flag,
						"hold_s": hold_s,
						"conf": conf,
					},
				),
			)
			deadline = time.time() + 60
			while not os.path.exists(flag) and time.time() < deadline:
				time.sleep(0.05)
			contended = _new_draft(profile, items, "contended", lock_wait_s)
			holder = pending.get(timeout=120)

		events = _last_log_entries(log_size)
		print(
			json.dumps(
				{
					"hold_s": hold_s,
					"holder_site_config": conf or "(defaults)",
					"session_lock_wait_s": lock_wait_s,
					"control_new_draft": control,
					"new_draft_while_another_cashier_submits": contended,
					"submit_holder": holder,
					"application_log": [
						{
							"kind": e.get("kind"),
							"operation": e.get("operation"),
							"child_table": (e.get("failing") or {}).get("doctype"),
							"blocked_statement": e.get("statement"),
							"elapsed_ms": e.get("elapsed_ms"),
						}
						for e in events
					],
				}
			)
		)
	finally:
		if os.path.exists(flag):
			os.remove(flag)
		print("cleanup:", json.dumps(cleanup(since=started)))
