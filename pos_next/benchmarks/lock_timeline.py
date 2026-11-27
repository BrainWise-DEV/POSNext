# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Timeline of one ``submit_invoice``: which locks it takes, when, and what runs while they are held.

TEST SITES ONLY; everything is rolled back. Read-only instrumentation (it wraps functions and
``frappe.db.sql`` to take timestamps; it changes no behaviour).

For one submit it prints, relative to the start of the call:

* when each lock group is FIRST taken (child-table ``FOR UPDATE`` loads and ``DELETE``s,
  ``tabBin``, ``tabCompany``, ``tabCustomer``, the stock ledger, ...) and therefore how long it is
  held (until the request ends, because nothing commits earlier)
* the phases that run INSIDE that window (validation, item details, taxes, stock posting, GL
  posting, hooks, ...) with their durations

so the work that could safely run outside the window is visible.

	bench --site <test-site> execute pos_next.benchmarks.lock_timeline.run \
		--kwargs '{"lines": 100, "repeat": 3}'
"""

import importlib
import json
import re
import statistics
import time

import frappe

from pos_next.benchmarks.submit_benchmark import _build_invoice, _create_stocked_items

PHASES = {
	"submit_invoice (whole call)": ("pos_next.api.invoices", "submit_invoice"),
	"Document.submit": ("frappe.model.document", "Document.submit"),
	"check_if_latest (stored copy loaded FOR UPDATE)": ("frappe.model.document", "Document.check_if_latest"),
	"validate (controller, all of it)": ("pos_next.overrides.sales_invoice", "CustomSalesInvoice.validate"),
	"  item details (set_missing_values)": (
		"erpnext.accounts.doctype.sales_invoice.sales_invoice",
		"SalesInvoice.set_missing_values",
	),
	"  taxes and totals": (
		"erpnext.controllers.accounts_controller",
		"AccountsController.calculate_taxes_and_totals",
	),
	"  hook: invoice validate": ("pos_next.api.sales_invoice_hooks", "validate"),
	"  hook: wallet payment validate": ("pos_next.api.wallet", "validate_wallet_payment"),
	"save children (update_children)": ("frappe.model.document", "Document.update_children"),
	"on_submit (controller, all of it)": ("pos_next.overrides.sales_invoice", "CustomSalesInvoice.on_submit"),
	"  stock ledger posting": ("erpnext.controllers.stock_controller", "StockController.make_sl_entries"),
	"  GL posting": ("erpnext.accounts.doctype.sales_invoice.sales_invoice", "SalesInvoice.make_gl_entries"),
	"hook: authorization gate": ("pos_next.authorization.gate", "enforce_document"),
	"hook: stock realtime event": ("pos_next.realtime_events", "emit_stock_update_event"),
	"hook: loyalty to wallet": ("pos_next.api.wallet", "process_loyalty_to_wallet"),
	"hook: one-time offer usage": ("pos_next.api.sales_invoice_hooks", "record_one_time_offer_usage"),
	"after submit: coupon usage": (
		"pos_next.pos_next.doctype.pos_coupon.pos_coupon",
		"increment_coupon_usage",
	),
	"after submit: retry-key complete": ("pos_next.api.invoices", "_complete_offline_sync"),
}

CHILD_TABLES = (
	"tabSales Invoice Item",
	"tabSales Invoice Payment",
	"tabSales Taxes and Charges",
	"tabSales Team",
	"tabPacked Item",
	"tabPayment Schedule",
	"tabPricing Rule Detail",
	"tabSales Invoice Timesheet",
	"tabSales Invoice Advance",
)

LOCK_GROUPS = [
	(
		"invoice + child tables: FOR UPDATE load",
		r"(?is)^select .*from `(tabSales Invoice(?: Item| Payment| Advance| Timesheet)?|tabSales Taxes and Charges|tabSales Team|tabPacked Item|tabPayment Schedule|tabPricing Rule Detail)`.* for update$",
	),
	(
		"child tables: DELETE (range scan)",
		r"(?is)^delete from `(" + "|".join(re.escape(t) for t in CHILD_TABLES) + r")`",
	),
	("stock ledger: reads FOR UPDATE", r"(?is)^select .*from `tabStock Ledger Entry`.* for update$"),
	("stock ledger: INSERT", r"(?is)^insert into `tabStock Ledger Entry`"),
	("stock quantities (tabBin UPDATE)", r"(?is)^update `tabBin`"),
	("GL: INSERT", r"(?is)^insert into `tabGL Entry`"),
	("company row (UPDATE tabCompany)", r"(?is)^update `tabCompany`"),
	("customer row (UPDATE tabCustomer)", r"(?is)^update `tabCustomer`"),
	("loyalty (INSERT Loyalty Point Entry)", r"(?is)^insert into `tabLoyalty Point Entry`"),
	("retry key row (Offline Invoice Sync)", r"(?is)(insert into|update) `tabOffline Invoice Sync`"),
]


def _resolve(module_path: str, attr_path: str):
	owner = importlib.import_module(module_path)
	parts = attr_path.split(".")
	for part in parts[:-1]:
		owner = getattr(owner, part)
	return owner, parts[-1]


class Recorder:
	def __init__(self):
		self.t0 = time.perf_counter()
		self.intervals: dict[str, list[tuple[float, float]]] = {}
		self.first_lock: dict[str, float] = {}
		self._patched = []
		self._orig_sql = None

	def now_ms(self) -> float:
		return (time.perf_counter() - self.t0) * 1000

	def __enter__(self):
		for label, (module_path, attr_path) in PHASES.items():
			try:
				owner, attr = _resolve(module_path, attr_path)
			except (ImportError, AttributeError):
				continue
			original = owner.__dict__.get(attr, getattr(owner, attr))

			def make(label=label, original=original):
				def timed(*args, **kwargs):
					start = self.now_ms()
					try:
						return original(*args, **kwargs)
					finally:
						self.intervals.setdefault(label, []).append((start, self.now_ms()))

				timed.__name__ = getattr(original, "__name__", label)
				timed.__wrapped__ = original
				return timed

			setattr(owner, attr, make())
			self._patched.append((owner, attr, original))

		self._orig_sql = frappe.db.sql
		compiled = [(name, re.compile(rx)) for name, rx in LOCK_GROUPS]

		def spy(query, *args, **kwargs):
			text = " ".join(str(query).split())
			stamp = self.now_ms()
			for name, rx in compiled:
				if name not in self.first_lock and rx.search(text):
					self.first_lock[name] = stamp
			return self._orig_sql(query, *args, **kwargs)

		frappe.db.sql = spy
		return self

	def __exit__(self, *exc):
		frappe.db.sql = self._orig_sql
		for owner, attr, original in self._patched:
			setattr(owner, attr, original)


def _one_run(profile, items, lines: int) -> dict:
	import pos_next.api.invoices as invoices

	data = _build_invoice(profile, items, lines)
	draft = invoices.update_invoice(json.dumps(data))
	with Recorder() as rec:
		invoices.submit_invoice(invoice=json.dumps(draft, default=str), data="{}")
	total = rec.intervals["submit_invoice (whole call)"][0][1]
	return {
		"total_ms": total,
		"first_lock": dict(rec.first_lock),
		"phases": {k: sum(e - s for s, e in v) for k, v in rec.intervals.items()},
		"starts": {k: min(s for s, _ in v) for k, v in rec.intervals.items()},
	}


def run(
	pos_profile: str = "Cairo Branch", lines: int = 100, repeat: int = 3, conf: dict | None = None
) -> None:
	for key, value in (conf or {}).items():
		frappe.conf[key] = value  # site-config overrides for an A/B run
	frappe.set_user("Administrator")
	profile = frappe.get_doc("POS Profile", pos_profile)
	items = _create_stocked_items(profile, lines, prefix="_BENCH-LT")
	frappe.db.savepoint("lt")
	runs = []
	for _ in range(repeat):
		try:
			runs.append(_one_run(profile, items, lines))
		finally:
			frappe.db.rollback(save_point="lt")
	frappe.db.rollback()

	def med(values):
		return statistics.median(values)

	total = med([r["total_ms"] for r in runs])
	print(
		f"\n=== submit_invoice, {lines} lines, median of {repeat}, site config {conf or '(defaults)'}: {total:.0f} ms"
	)
	print("\nLOCK GROUPS (first taken; held until the request ends and commits):")
	for name, _rx in LOCK_GROUPS:
		taken = [r["first_lock"][name] for r in runs if name in r["first_lock"]]
		if taken:
			t = med(taken)
			print(
				f"  {name:48s} taken at +{t:7.0f} ms   held for {total - t:7.0f} ms ({(total - t) / total * 100:3.0f}% of the call)"
			)
	print("\nPHASES (start offset, duration):")
	for label in PHASES:
		starts = [r["starts"][label] for r in runs if label in r["starts"]]
		if starts:
			dur = med([r["phases"][label] for r in runs if label in r["phases"]])
			print(f"  {label:50s} +{med(starts):7.0f} ms   {dur:7.0f} ms")
