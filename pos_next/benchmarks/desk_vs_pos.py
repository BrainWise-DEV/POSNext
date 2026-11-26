# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Compare the POS cashier checkout path with the standard Desk Sales Invoice path.

TEST SITES ONLY. Single-process mode rolls everything back; the concurrent mode
lives in ``concurrent_benchmark`` and reuses the flows defined here.

What each path calls (server side; browser rendering and network are NOT measured):

* ``pos``  : what the cashier screen calls at checkout
              ``apply_offers`` -> ``update_invoice`` -> ``submit_invoice``
* ``desk`` : what the Desk form calls
              one ``get_item_details`` per row (the item_code trigger; modeled, the
              browser makes these calls while the user fills the form)
              -> ``frappe.desk.form.save.savedocs`` (Save)
              -> ``savedocs`` (Submit)
* ``desk_nohooks`` (diagnostic only, NOT an equivalent business result): the Desk
  path with POSNext's doc_events disabled, to isolate what those hooks cost.

Both paths are fed the same cart values (items, quantities, price-list rates,
discounts, header discount, coupon code, payments, taxes from the POS Profile's tax
template). ``check_equivalence`` compares the resulting invoice, stock and GL.

	bench --site <test-site> execute pos_next.benchmarks.desk_vs_pos.run \
		--kwargs '{"rounds": 5}'
"""

import functools
import importlib
import json
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe.utils import flt, nowdate

from pos_next.api import invoices
from pos_next.benchmarks.submit_benchmark import _create_stocked_items, _fingerprint

MARKER_PREFIX = "_BENCHC"
PROMO_ITEM_GROUP = "Products"  # has an active 10% Pricing Rule on the test site

# ---------------------------------------------------------------------------
# Instrumentation: inclusive wall time + call count per labelled function
# ---------------------------------------------------------------------------

# label -> (module path, attribute path)
STAGE_TARGETS = {
	"pricing_rule_engine": ("erpnext.stock.get_item_details", "get_pricing_rule_for_item"),
	"set_missing_values": (
		"erpnext.accounts.doctype.sales_invoice.sales_invoice",
		"SalesInvoice.set_missing_values",
	),
	"taxes_and_totals": (
		"erpnext.controllers.accounts_controller",
		"AccountsController.calculate_taxes_and_totals",
	),
	"validate": ("pos_next.overrides.sales_invoice", "CustomSalesInvoice.validate"),
	"sales_team_commission": (
		"pos_next.overrides.sales_invoice",
		"CustomSalesInvoice.calculate_contribution",
	),
	"stock_posting": ("erpnext.controllers.stock_controller", "StockController.make_sl_entries"),
	"gl_posting": ("erpnext.accounts.doctype.sales_invoice.sales_invoice", "SalesInvoice.make_gl_entries"),
	# POS API layer only
	"pos:apply_offers": ("pos_next.api.invoices", "apply_offers"),
	"pos:stock_validation": ("pos_next.api.invoices", "_validate_stock_on_invoice"),
	"pos:stock_precheck_draft": ("pos_next.api.invoices", "_collect_stock_errors"),
	"pos:sales_team": ("pos_next.api.invoices", "_apply_pos_sales_team"),
	"pos:payment_accounts": ("pos_next.api.invoices", "_set_payment_accounts"),
	"pos:customer_dims": ("pos_next.api.invoices", "_ensure_invoice_customer"),
	"pos:item_dims": ("pos_next.api.invoices", "_apply_pos_item_accounting_dimensions"),
	# POSNext doc_events hooks (run on both paths unless disabled)
	"hook:sales_invoice_validate": ("pos_next.api.sales_invoice_hooks", "validate"),
	"hook:wallet_validate": ("pos_next.api.wallet", "validate_wallet_payment"),
	"hook:authorization_gate": ("pos_next.authorization.gate", "enforce_document"),
	"hook:stock_event": ("pos_next.realtime_events", "emit_stock_update_event"),
	"hook:loyalty_to_wallet": ("pos_next.api.wallet", "process_loyalty_to_wallet"),
	"hook:one_time_offer": ("pos_next.api.sales_invoice_hooks", "record_one_time_offer_usage"),
	"hook:invoice_created_event": ("pos_next.realtime_events", "emit_invoice_created_event"),
}


def _resolve(module_path: str, attr_path: str):
	owner = importlib.import_module(module_path)
	parts = attr_path.split(".")
	for part in parts[:-1]:
		owner = getattr(owner, part)
	return owner, parts[-1]


class Stages:
	"""Collects inclusive time (ms) and call counts per label."""

	def __init__(self):
		self.ms: dict[str, float] = defaultdict(float)
		self.calls: dict[str, int] = defaultdict(int)

	def add(self, label: str, seconds: float):
		self.ms[label] += seconds * 1000
		self.calls[label] += 1


@contextmanager
def instrument(stages: Stages):
	patched = []
	for label, (module_path, attr_path) in STAGE_TARGETS.items():
		owner, attr = _resolve(module_path, attr_path)
		original = owner.__dict__.get(attr, getattr(owner, attr))
		raw = original.__func__ if isinstance(original, staticmethod | classmethod) else original

		def make(label=label, raw=raw):
			@functools.wraps(raw)
			def timed(*args, **kwargs):
				start = time.perf_counter()
				try:
					return raw(*args, **kwargs)
				finally:
					stages.add(label, time.perf_counter() - start)

			return timed

		wrapper = make()
		setattr(owner, attr, wrapper)
		patched.append((owner, attr, original))
	try:
		yield
	finally:
		for owner, attr, original in patched:
			setattr(owner, attr, original)


class QueryProbe:
	"""Counts statements and keeps per-statement timings for slow-query reporting."""

	SLOW_MS = 100

	def __enter__(self):
		self.count = 0
		self.series_wait_ms = 0.0
		self.slow: list[tuple[int, str]] = []
		self._orig = frappe.db.sql

		def probe(*args, **kwargs):
			self.count += 1
			start = time.perf_counter()
			try:
				return self._orig(*args, **kwargs)
			finally:
				elapsed = (time.perf_counter() - start) * 1000
				if elapsed >= self.SLOW_MS:
					self.slow.append((int(elapsed), " ".join(str(args[0] if args else "").split())[:110]))
				query = str(args[0] if args else "")
				if "tabSeries" in query and "FOR UPDATE" in query.upper():
					self.series_wait_ms += elapsed

		frappe.db.sql = probe
		return self

	def __exit__(self, *exc):
		frappe.db.sql = self._orig


# ---------------------------------------------------------------------------
# Scenarios: one neutral cart description feeds both paths
# ---------------------------------------------------------------------------


def _money(value: float) -> float:
	return round(flt(value), 2)


def make_spec(name: str, profile, items: list, sales_person: str | None) -> dict:
	"""Build the cart for a scenario.

	``lines``: item_code, qty, plr (price-list rate), disc (% discount chosen by the
	cashier / coupon), item_name, uom. ``promo`` means the discount comes from the
	Pricing Rule engine instead of being typed in.
	"""

	def lines(count, disc_every=None, disc_pct=0):
		out = []
		for i in range(count):
			it = items[i % len(items)]
			plr = 10.0 + (i % 7)
			disc = disc_pct if disc_every and i % disc_every == 0 else 0
			out.append(
				{
					"item_code": it.name,
					"item_name": it.item_name,
					"qty": 1,
					"plr": plr,
					"disc": disc,
					"uom": it.stock_uom,
				}
			)
		return out

	spec = {
		"name": name,
		"profile": profile,
		"sales_person": sales_person,
		"header_discount": 0.0,
		"coupon_code": None,
		"promo": False,
		"split": False,
	}
	if name == "plain_10":
		spec["lines"] = lines(10)
	elif name == "large_100":
		spec["lines"] = lines(100)
	elif name == "discounts_split_30":
		spec["lines"] = lines(30, disc_every=3, disc_pct=15)
		spec["header_discount"] = 5.0
		spec["split"] = True
	elif name == "promo_rule_30":
		spec["lines"] = lines(30)
		spec["promo"] = True
	elif name == "promo_code_30":
		spec["lines"] = lines(30, disc_every=1, disc_pct=10)
		spec["coupon_code"] = "ANAS"
	else:
		raise ValueError(name)
	return spec


def _line_rate(line: dict) -> float:
	return _money(line["plr"] * (1 - flt(line["disc"]) / 100))


def _payments_for(spec: dict) -> tuple[list[dict], float]:
	total = sum(line["qty"] * _line_rate(line) for line in spec["lines"]) - spec["header_discount"]
	if spec["split"]:
		cash = _money(total / 2) + 5
		return (
			[
				{"mode_of_payment": "Cash", "amount": cash},
				{"mode_of_payment": "Credit Card", "amount": _money(total / 2)},
			],
			5.0,
		)
	return [{"mode_of_payment": "Cash", "amount": _money(total)}], 0.0


def _marker(spec: dict, run_id: str) -> str:
	return f"{MARKER_PREFIX}-{spec['name']}-{run_id}"[:140]


# ---------------------------------------------------------------------------
# The two flows
# ---------------------------------------------------------------------------


def _pos_invoice_data(spec: dict) -> dict:
	profile = spec["profile"]
	rows = []
	for line in spec["lines"]:
		rows.append(
			{
				"item_code": line["item_code"],
				"item_name": line["item_name"],
				"qty": line["qty"],
				"rate": _line_rate(line),
				"price_list_rate": line["plr"],
				"uom": line["uom"],
				"warehouse": profile.warehouse,
				"conversion_factor": 1,
				"discount_percentage": line["disc"],
				"discount_amount": 0,
				"sales_person": spec["sales_person"],
			}
		)
	data = {
		"doctype": "Sales Invoice",
		"pos_profile": profile.name,
		"customer": profile.customer,
		"items": rows,
		"is_pos": 1,
		"update_stock": 1,
	}
	if spec["header_discount"]:
		data["discount_amount"] = spec["header_discount"]
	if spec["coupon_code"]:
		data["coupon_code"] = spec["coupon_code"]
	return data


def run_pos(spec: dict, run_id: str, commit_between: bool = False) -> dict:
	"""Cashier checkout: apply_offers -> update_invoice -> submit_invoice."""
	data = _pos_invoice_data(spec)
	data["po_no"] = _marker(spec, run_id)
	times = {}

	start = time.perf_counter()
	offers = invoices.apply_offers(json.dumps(data))
	times["apply_offers"] = (time.perf_counter() - start) * 1000
	if spec["promo"]:
		# The cart folds the offer result back into its lines (percentage -> rate).
		for row, result in zip(data["items"], offers["items"], strict=False):
			pct = flt(result.get("discount_percentage"))
			row["discount_percentage"] = pct
			row["rate"] = _money(row["price_list_rate"] * (1 - pct / 100))
			row["pricing_rules"] = result.get("pricing_rules") or ""
		total = sum(r["qty"] * r["rate"] for r in data["items"]) - spec["header_discount"]
		payments, change = [{"mode_of_payment": "Cash", "amount": _money(total)}], 0.0
	else:
		payments, change = _payments_for(spec)
	data["payments"] = payments

	start = time.perf_counter()
	draft = invoices.update_invoice(json.dumps(data))
	times["draft"] = (time.perf_counter() - start) * 1000
	if commit_between:
		frappe.db.commit()

	start = time.perf_counter()
	submit_data = {"change_amount": change, "client_request_id": f"pos_online_{_marker(spec, run_id)}"}
	submitted = invoices.submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps(submit_data))
	times["submit"] = (time.perf_counter() - start) * 1000
	if commit_between:
		frappe.db.commit()

	times["name"] = submitted["name"]
	return times


def _desk_row_from_details(spec: dict, line: dict) -> dict:
	"""What the Desk form's item_code trigger does: ask the server, copy the answer."""
	from erpnext.stock.get_item_details import get_item_details

	profile = spec["profile"]
	args = {
		"doctype": "Sales Invoice",
		"item_code": line["item_code"],
		"company": profile.company,
		"customer": profile.customer,
		"currency": profile.currency,
		"price_list": frappe.db.get_value("POS Profile", profile.name, "selling_price_list"),
		"plc_conversion_rate": 1,
		"conversion_rate": 1,
		"qty": line["qty"],
		"uom": line["uom"],
		"warehouse": profile.warehouse,
		"pos_profile": profile.name,
		"is_pos": 1,
		"update_stock": 1,
		"transaction_date": nowdate(),
		"ignore_pricing_rule": 0,
		"child_doctype": "Sales Invoice Item",
	}
	details = get_item_details(args)
	row = {k: v for k, v in details.items() if v is not None and k not in ("doctype",)}
	row.update(
		{
			"item_code": line["item_code"],
			"qty": line["qty"],
			"uom": line["uom"],
			"warehouse": profile.warehouse,
			"conversion_factor": 1,
			"price_list_rate": line["plr"],
		}
	)
	if spec["promo"]:
		# The rate follows the pricing-rule discount the server returned, as the form's
		# client-side calculation does.
		pct = flt(details.get("discount_percentage"))
		row["discount_percentage"] = pct
		row["rate"] = _money(line["plr"] * (1 - pct / 100))
	else:
		row["discount_percentage"] = line["disc"]
		row["rate"] = _line_rate(line)
		row.pop("pricing_rules", None)
	return row


def _profile_disable_rounded_total(profile_name: str) -> int:
	value = frappe.db.get_value("POS Profile", profile_name, "disable_rounded_total")
	return 1 if value is None else int(value)


def run_desk(spec: dict, run_id: str, commit_between: bool = False) -> dict:
	"""Desk form: per-row get_item_details, then savedocs Save, then savedocs Submit."""
	from frappe.desk.form.save import savedocs

	profile = spec["profile"]
	times = {}

	start = time.perf_counter()
	rows = [_desk_row_from_details(spec, line) for line in spec["lines"]]
	times["form_fill"] = (time.perf_counter() - start) * 1000

	if spec["promo"]:
		total = sum(r["qty"] * r["rate"] for r in rows) - spec["header_discount"]
		payments, change = [{"mode_of_payment": "Cash", "amount": _money(total)}], 0.0
	else:
		payments, change = _payments_for(spec)

	doc = {
		"doctype": "Sales Invoice",
		"__islocal": 1,
		"name": "new-sales-invoice-benchdesk",
		"docstatus": 0,
		"company": profile.company,
		"customer": profile.customer,
		"pos_profile": profile.name,
		"is_pos": 1,
		"update_stock": 1,
		"set_warehouse": profile.warehouse,
		"posting_date": nowdate(),
		"po_no": _marker(spec, run_id),
		"items": rows,
		"payments": payments,
		"sales_team": (
			[{"sales_person": spec["sales_person"], "allocated_percentage": 100}]
			if spec["sales_person"]
			else []
		),
		"ignore_pricing_rule": 0,
		# Selecting a POS Profile in the Desk form copies its rounding preference onto the
		# invoice (POS checkout applies the same value, defaulting to "no rounding").
		"disable_rounded_total": _profile_disable_rounded_total(profile.name),
	}
	if spec["header_discount"]:
		doc["discount_amount"] = spec["header_discount"]
	if spec["coupon_code"]:
		doc["coupon_code"] = spec["coupon_code"]

	frappe.local.response.docs = []  # savedocs appends; never read a previous run's document
	start = time.perf_counter()
	savedocs(json.dumps(doc, default=str), "Save")
	times["draft"] = (time.perf_counter() - start) * 1000
	saved = frappe.local.response.docs[-1]
	if commit_between:
		frappe.db.commit()

	saved = dict(saved)
	saved["change_amount"] = change
	start = time.perf_counter()
	savedocs(json.dumps(saved, default=str), "Submit")
	times["submit"] = (time.perf_counter() - start) * 1000
	if commit_between:
		frappe.db.commit()

	times["name"] = saved["name"]
	return times


@contextmanager
def posnext_hooks_disabled():
	"""Diagnostic: run the Desk path with only frappe/erpnext doc_events."""
	original = frappe.get_doc_hooks()
	keep = ("frappe.", "erpnext.")
	filtered = {
		doctype: {
			event: [h for h in handlers if str(h).startswith(keep)] for event, handlers in events.items()
		}
		for doctype, events in original.items()
	}
	frappe.local.doc_events_hooks = filtered
	try:
		yield
	finally:
		frappe.local.doc_events_hooks = original


MODES = ("pos", "desk", "desk_nohooks")


def run_mode(mode: str, spec: dict, run_id: str, commit_between: bool = False) -> dict:
	if mode == "pos":
		return run_pos(spec, run_id, commit_between)
	if mode == "desk":
		return run_desk(spec, run_id, commit_between)
	with posnext_hooks_disabled():
		return run_desk(spec, run_id, commit_between)


# ---------------------------------------------------------------------------
# Runner (single process, everything rolled back)
# ---------------------------------------------------------------------------

SCENARIOS = ("plain_10", "large_100", "discounts_split_30", "promo_rule_30", "promo_code_30")


def _prepare(profile_name: str):
	profile = frappe.get_doc("POS Profile", profile_name)
	normal = _create_stocked_items(profile, 100, prefix="_BENCH-DVP")
	promo = _create_stocked_items(profile, 30, prefix="_BENCH-DVP-PROMO", item_group=PROMO_ITEM_GROUP)
	sales_person = frappe.db.get_value("Sales Person", {"enabled": 1, "is_group": 0}, "name")
	return profile, normal, promo, sales_person


def _spec_for(name, profile, normal, promo, sales_person):
	return make_spec(name, profile, promo if name == "promo_rule_30" else normal, sales_person)


def check_equivalence(profile_name: str = "Cairo Branch") -> dict:
	"""Run every scenario through POS and Desk and compare the business result."""
	frappe.set_user("Administrator")
	profile, normal, promo, sales_person = _prepare(profile_name)
	frappe.db.savepoint("dvp_eq")
	report = {}
	for scenario in SCENARIOS:
		prints = {}
		for mode in ("pos", "desk"):
			spec = _spec_for(scenario, profile, normal, promo, sales_person)
			try:
				name = run_mode(mode, spec, "eq")["name"]
				prints[mode] = _fingerprint(name)
			except Exception as exc:
				prints[mode] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
			finally:
				frappe.db.rollback(save_point="dvp_eq")
		diffs = {}
		if "error" in prints["pos"] or "error" in prints["desk"]:
			diffs = {"error": {m: prints[m].get("error") for m in prints}}
		else:
			for key in prints["pos"]:
				if prints["pos"][key] != prints["desk"][key]:
					diffs[key] = {"pos": prints["pos"][key], "desk": prints["desk"][key]}
		report[scenario] = {"equivalent": not diffs, "differences": diffs}
	frappe.db.rollback()
	return report


def run(pos_profile: str = "Cairo Branch", rounds: int = 5, out_file: str | None = None) -> None:
	"""Single-cashier comparison (rolled back). Prints raw medians as JSON."""
	frappe.set_user("Administrator")
	profile, normal, promo, sales_person = _prepare(pos_profile)
	frappe.db.savepoint("dvp")
	results: dict = {}
	for round_no in range(rounds):
		for scenario in SCENARIOS:
			order = list(MODES)
			if round_no % 2:
				order.reverse()  # alternate order so load drift does not favour one mode
			for mode in order:
				spec = _spec_for(scenario, profile, normal, promo, sales_person)
				stages = Stages()
				try:
					with QueryProbe() as probe, instrument(stages):
						start = time.perf_counter()
						times = run_mode(mode, spec, f"r{round_no}")
						wall = (time.perf_counter() - start) * 1000
					results.setdefault((scenario, mode), []).append(
						{
							"wall_ms": wall,
							"times": {k: v for k, v in times.items() if k != "name"},
							"stage_ms": dict(stages.ms),
							"stage_calls": dict(stages.calls),
							"queries": probe.count,
							"series_wait_ms": probe.series_wait_ms,
							"slow": probe.slow,
						}
					)
				except Exception as exc:
					results.setdefault((scenario, mode), []).append(
						{"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
					)
				finally:
					frappe.db.rollback(save_point="dvp")
	frappe.db.rollback()

	summary = {}
	for (scenario, mode), runs in results.items():
		ok = [r for r in runs if "error" not in r]
		if not ok:
			summary.setdefault(scenario, {})[mode] = {"error": runs[0]["error"]}
			continue

		def med(getter, ok=ok):
			return statistics.median(getter(r) for r in ok)

		labels = {label for r in ok for label in r["stage_ms"]}
		summary.setdefault(scenario, {})[mode] = {
			"runs": len(ok),
			"wall_ms": med(lambda r: r["wall_ms"]),
			"times": {
				key: med(lambda r, key=key: r["times"].get(key, 0.0))
				for key in {k for r in ok for k in r["times"]}
			},
			"stage_ms": {
				label: med(lambda r, label=label: r["stage_ms"].get(label, 0.0)) for label in labels
			},
			"stage_calls": {
				label: med(lambda r, label=label: r["stage_calls"].get(label, 0)) for label in labels
			},
			"queries": med(lambda r: r["queries"]),
			"series_wait_ms": med(lambda r: r["series_wait_ms"]),
			"slow": sorted({s for r in ok for s in r["slow"]}, reverse=True)[:6],
		}
	text = json.dumps(summary, indent=1, default=str)
	if out_file:
		with open(out_file, "w") as fh:
			fh.write(text)
		print(f"wrote {out_file}")
	else:
		print(text)


# ---------------------------------------------------------------------------
# Concurrent cashiers (committed data; removed by concurrent_benchmark.cleanup)
# ---------------------------------------------------------------------------


def _concurrent_worker(args: dict) -> list[dict]:
	"""One cashier process: own connection, one request-like commit per call."""
	from pos_next.benchmarks.concurrent_benchmark import _trace_series_lock

	frappe.init(site=args["site"], sites_path=args["sites_path"])
	frappe.connect()
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", args["pos_profile"])
	items = [frappe._dict(name=c, item_name=c, stock_uom="Nos") for c in args["item_codes"]]
	spec = make_spec(args["scenario"], profile, items, args["sales_person"])

	while time.time() < args["start_at"]:
		time.sleep(0.001)

	trace = _trace_series_lock()
	out = []
	for n in range(args["count"]):
		record = {"cashier": args["cashier"], "n": n}
		start = time.perf_counter()
		try:
			run_mode(args["mode"], spec, f"{args['run_id']}-{args['cashier']}-{n}", commit_between=True)
			record["slow"], trace["slow"] = list(trace["slow"]), []
		except Exception as exc:
			frappe.db.rollback()
			record["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
			trace["slow"] = []
		record["ms"] = int((time.perf_counter() - start) * 1000)
		out.append(record)
	frappe.destroy()
	return out


def run_concurrent(
	pos_profile: str = "Cairo Branch",
	scenario: str = "large_100",
	cashiers: list | None = None,
	invoices_per_cashier: int = 3,
	modes: tuple = ("pos", "desk"),
) -> None:
	"""POS vs Desk with N cashiers at once, each selling different items."""
	import multiprocessing as mp
	import os

	from pos_next.benchmarks.concurrent_benchmark import _percentile, _slowest, cleanup

	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	site, sites_path = frappe.local.site, os.path.abspath(frappe.local.sites_path)
	levels = cashiers or [1, 4, 8]
	lines = len(
		make_spec(scenario, profile, [frappe._dict(name="x", item_name="x", stock_uom="Nos")], None)["lines"]
	)
	group = PROMO_ITEM_GROUP if scenario == "promo_rule_30" else "All Item Groups"
	sales_person = frappe.db.get_value("Sales Person", {"enabled": 1, "is_group": 0}, "name")
	run_id = str(int(time.time()))
	started = frappe.utils.now_datetime()
	pool_items = _create_stocked_items(profile, lines * max(levels), prefix="_BENCH-DVP", item_group=group)
	frappe.db.commit()
	codes = [i.name for i in pool_items]

	try:
		for level in levels:
			for mode in modes:
				frappe.db.commit()
				start_at = time.time() + 3
				jobs = [
					{
						"site": site,
						"sites_path": sites_path,
						"pos_profile": pos_profile,
						"scenario": scenario,
						"mode": mode,
						"item_codes": codes[c * lines : (c + 1) * lines],
						"sales_person": sales_person,
						"count": invoices_per_cashier,
						"cashier": c,
						"start_at": start_at,
						"run_id": f"{run_id}-{level}-{mode}",
					}
					for c in range(level)
				]
				with mp.get_context("spawn").Pool(level) as pool:
					results = [r for batch in pool.map(_concurrent_worker, jobs) for r in batch]
				wall = time.time() - start_at

				ok = [r for r in results if "error" not in r]
				errors = sorted({r["error"] for r in results if "error" in r})
				latencies = [r["ms"] for r in ok]
				slow = _slowest(ok)
				series_ms = sum(ms for _n, ms, shape in slow if "tabSeries" in shape)
				print(
					json.dumps(
						{
							"scenario": scenario,
							"cashiers": level,
							"mode": mode,
							"ok": len(ok),
							"errors": len(results) - len(ok),
							"error_samples": errors[:2],
							"p50_ms": _percentile(latencies, 50),
							"p95_ms": _percentile(latencies, 95),
							"invoices_per_min": round(len(ok) / wall * 60, 1) if wall else 0,
							"series_lock_wait_s": round(series_ms / 1000, 1),
							"slowest_statements": slow[:3],
						}
					)
				)
	finally:
		print("cleanup:", json.dumps(cleanup(since=started)))
