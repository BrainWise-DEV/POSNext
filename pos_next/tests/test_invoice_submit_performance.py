# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Large-invoice, duplicate-prevention and instrumentation tests for the submit path.

These run against a real site (they post stock and GL) but create their own
items and opening stock in ``setUpClass``; FrappeTestCase rolls everything back.
They need a POS Profile with a warehouse, a default customer and a Cash payment
method; the test is skipped if the site has none.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.benchmarks.submit_benchmark import (
	_build_invoice,
	_create_stocked_items,
	_fingerprint,
	_QueryCounter,
)
from pos_next.perf import StepTimer

LARGE_INVOICE_LINES = 60
# Measured ~70 queries per cart line after optimisation (was ~95). The budget is
# deliberately loose; it exists to catch a return of per-row queries (N+1).
MAX_QUERIES_PER_LINE = 90


def _find_pos_profile(require_sales_persons: bool = False):
	from pos_next.pos_next.utils.sales_person_commission import sales_persons_enabled

	for name in frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="name"):
		profile = frappe.get_doc("POS Profile", name)
		has_cash = any(p.mode_of_payment == "Cash" for p in profile.payments)
		if not (profile.warehouse and profile.customer and has_cash):
			continue
		if require_sales_persons and not sales_persons_enabled(profile.name):
			continue
		return profile
	return None


class _SubmitPathBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.profile = _find_pos_profile()
		if not cls.profile:
			return
		cls.items = _create_stocked_items(cls.profile, LARGE_INVOICE_LINES)

	def setUp(self):
		if not self.profile:
			self.skipTest("No POS Profile with warehouse, customer and Cash payment on this site")
		frappe.set_user("Administrator")

	def _draft(self, lines, request_id=None):
		data = _build_invoice(self.profile, self.items, lines)
		draft = invoices.update_invoice(json.dumps(data))
		submit_data = {"client_request_id": request_id} if request_id else {}
		return draft, submit_data

	def _submit(self, draft, submit_data):
		return invoices.submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps(submit_data))


class TestInvoiceSubmitPath(_SubmitPathBase):
	# -- large invoices -------------------------------------------------

	def test_large_invoice_posts_stock_and_accounts_correctly(self):
		draft, data = self._draft(LARGE_INVOICE_LINES)
		result = self._submit(draft, data)

		fp = _fingerprint(result["name"])
		expected_total = sum(
			flt(r["rate"]) for r in _build_invoice(self.profile, self.items, LARGE_INVOICE_LINES)["items"]
		)

		self.assertEqual(fp["docstatus"], 1)
		self.assertEqual(fp["status"], "Paid")
		self.assertAlmostEqual(fp["totals"][2], expected_total, places=2)  # grand_total
		self.assertAlmostEqual(fp["totals"][6], 0, places=2)  # outstanding
		self.assertEqual(len(fp["sle"]), LARGE_INVOICE_LINES)
		self.assertTrue(all(row[2] == -1 for row in fp["sle"]))
		gl_debit = sum(row[1] for row in fp["gl"])
		gl_credit = sum(row[2] for row in fp["gl"])
		self.assertAlmostEqual(gl_debit, gl_credit, places=2)

	def test_query_count_per_line_stays_bounded(self):
		draft, data = self._draft(LARGE_INVOICE_LINES)
		with _QueryCounter() as counter:
			self._submit(draft, data)
		self.assertLess(counter.count / LARGE_INVOICE_LINES, MAX_QUERIES_PER_LINE)

	# -- duplicate prevention -------------------------------------------

	def test_retry_with_same_request_id_returns_same_invoice(self):
		request_id = "pos_online_test-retry-1"
		draft_1, data = self._draft(5, request_id)
		first = self._submit(draft_1, data)

		# Client timed out and retries: new draft, same key.
		draft_2, data = self._draft(5, request_id)
		second = self._submit(draft_2, data)

		self.assertEqual(second["name"], first["name"])
		self.assertTrue(second.get("duplicate_prevented"))
		self.assertEqual(second["client_request_id"], request_id)
		self.assertNotIn("offline_id", second)

		submitted = frappe.get_all(
			"Sales Invoice",
			filters={"name": first["name"], "docstatus": 1},
			pluck="name",
		)
		self.assertEqual(len(submitted), 1)
		stock_rows = frappe.db.count(
			"Stock Ledger Entry",
			{"voucher_type": "Sales Invoice", "voucher_no": first["name"], "is_cancelled": 0},
		)
		self.assertEqual(stock_rows, 5)  # stock posted once, not twice

	def test_status_check_returns_totals_for_a_completed_checkout(self):
		"""Lets the client finish a sale whose response it never received (timeout)."""
		request_id = "pos_online_test-status-1"
		self.assertEqual(
			invoices.check_offline_invoice_synced(request_id),
			{"synced": False, "sales_invoice": None, "status": None},
		)

		draft, data = self._draft(4, request_id)
		submitted = self._submit(draft, data)

		status = invoices.check_offline_invoice_synced(request_id)
		self.assertTrue(status["synced"])
		self.assertEqual(status["sales_invoice"], submitted["name"])
		summary = status["invoice"]
		self.assertEqual(summary["name"], submitted["name"])
		self.assertEqual(summary["status"], 1)
		self.assertAlmostEqual(summary["grand_total"], submitted["grand_total"], places=2)
		self.assertAlmostEqual(summary["paid_amount"], submitted["paid_amount"], places=2)
		self.assertEqual(summary["client_request_id"], request_id)

	def test_different_request_ids_create_separate_invoices(self):
		draft_1, data_1 = self._draft(3, "pos_online_test-a")
		draft_2, data_2 = self._draft(3, "pos_online_test-b")
		self.assertNotEqual(self._submit(draft_1, data_1)["name"], self._submit(draft_2, data_2)["name"])

	def test_request_id_does_not_relax_sales_person_validation(self):
		"""Only offline_id may skip the Sales Person checks; the new key must not."""
		from pos_next.pos_next.utils.sales_person_commission import sales_persons_enabled

		profile = _find_pos_profile(require_sales_persons=True)
		if not profile:
			self.skipTest("No POS Profile with Sales Persons enabled on this site")

		items = _create_stocked_items(profile, 3, prefix="_BENCH-SP-ITEM")
		data = _build_invoice(profile, items, 3)
		for row in data["items"]:
			row.pop("sales_person", None)
		data["client_request_id"] = "pos_online_test-no-relax"
		self.assertTrue(sales_persons_enabled(profile.name))

		with self.assertRaises(frappe.ValidationError) as ctx:
			invoices.update_invoice(json.dumps(data))
		self.assertIn("Sales Person", str(ctx.exception))

	def test_malformed_request_ids_are_ignored(self):
		clean = invoices._clean_client_request_id
		self.assertEqual(clean("  abc  "), "abc")
		self.assertIsNone(clean(None))
		self.assertIsNone(clean(""))
		self.assertIsNone(clean(123))
		self.assertIsNone(clean({"a": 1}))
		self.assertIsNone(clean("x" * (invoices.CLIENT_REQUEST_ID_MAX_LENGTH + 1)))

	def test_request_id_lookup_does_not_take_gap_lock(self):
		with patch.object(frappe.db, "get_value", wraps=frappe.db.get_value) as get_value:
			invoices._ensure_offline_uniqueness("pos_online_test-lock", lock_existing=False)
		offline_lookup = [
			c for c in get_value.call_args_list if c.args and c.args[0] == "Offline Invoice Sync"
		]
		self.assertTrue(offline_lookup)
		self.assertFalse(offline_lookup[0].kwargs.get("for_update"))


class TestRepeatedItemDetailPass(_SubmitPathBase):
	"""Only validate's repeat of update_invoice's own pass is skipped, nothing else."""

	def _count_item_detail_passes(self, action):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

		real = SalesInvoice.set_missing_values
		with patch.object(SalesInvoice, "set_missing_values", autospec=True, side_effect=real) as parent:
			action()
		return parent.call_count

	def test_update_invoice_runs_the_pass_once_not_twice(self):
		data = json.dumps(_build_invoice(self.profile, self.items, 5))
		self.assertEqual(self._count_item_detail_passes(lambda: invoices.update_invoice(data)), 1)

	def test_submit_time_validate_still_runs_the_full_pass(self):
		draft, submit_data = self._draft(5)
		calls = self._count_item_detail_passes(lambda: self._submit(draft, submit_data))
		self.assertGreaterEqual(calls, 1)

	def test_skip_is_one_shot_and_off_for_other_callers(self):
		from pos_next.overrides.sales_invoice import CustomSalesInvoice

		doc = frappe.new_doc("Sales Invoice")
		doc.flags.pos_missing_values_done = True
		with patch(
			"erpnext.accounts.doctype.sales_invoice.sales_invoice.SalesInvoice.set_missing_values"
		) as parent:
			CustomSalesInvoice.set_missing_values(doc, for_validate=True)  # consumed: skipped
			parent.assert_not_called()
			self.assertFalse(doc.flags.pos_missing_values_done)
			CustomSalesInvoice.set_missing_values(doc, for_validate=True)  # next one runs
			parent.assert_called_once()

	def test_non_validate_calls_are_never_skipped(self):
		from pos_next.overrides.sales_invoice import CustomSalesInvoice

		doc = frappe.new_doc("Sales Invoice")
		doc.flags.pos_missing_values_done = True
		with patch(
			"erpnext.accounts.doctype.sales_invoice.sales_invoice.SalesInvoice.set_missing_values"
		) as parent:
			CustomSalesInvoice.set_missing_values(doc)  # for_validate False (desk use)
			parent.assert_called_once()

	def test_override_stays_whitelisted_for_desk_calls(self):
		from pos_next.overrides.sales_invoice import CustomSalesInvoice

		self.assertIn(CustomSalesInvoice.set_missing_values, frappe.whitelisted)


class CommitCalled(BaseException):
	"""BaseException so a `except Exception` in the code under test cannot swallow it."""


class TestCouponUsageInSubmit(_SubmitPathBase):
	"""A coupon sale must not commit mid-request or leave the retry key stuck."""

	COUPON = "ANAS"

	def setUp(self):
		super().setUp()
		if not frappe.db.exists("POS Coupon", {"coupon_code": self.COUPON}):
			self.skipTest("POS Coupon ANAS not present on this site")

	def _used(self):
		return frappe.db.get_value("POS Coupon", {"coupon_code": self.COUPON}, "used") or 0

	def _coupon_invoice(self, request_id):
		data = _build_invoice(self.profile, self.items, 3)
		data["coupon_code"] = self.COUPON
		draft = invoices.update_invoice(json.dumps(data))
		return draft, {"client_request_id": request_id}

	def test_submit_never_commits_and_counts_the_coupon_once(self):
		before = self._used()
		draft, submit_data = self._coupon_invoice("pos_online_test-coupon-1")
		with patch.object(frappe.db, "commit", side_effect=CommitCalled("commit inside submit")):
			self._submit(draft, submit_data)
		self.assertEqual(self._used(), before + 1)

	def test_failed_sale_does_not_use_up_the_coupon(self):
		before = self._used()
		draft, submit_data = self._coupon_invoice("pos_online_test-coupon-2")
		with patch.object(
			invoices.frappe.model.document.Document, "submit", side_effect=frappe.ValidationError("boom")
		):
			with self.assertRaises(frappe.ValidationError):
				self._submit(draft, submit_data)
		self.assertEqual(self._used(), before)

	def test_increment_is_atomic_and_commit_free(self):
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import increment_coupon_usage

		before = self._used()
		with patch.object(frappe.db, "commit", side_effect=CommitCalled("commit")):
			increment_coupon_usage(self.COUPON)
			increment_coupon_usage(self.COUPON.lower())
		self.assertEqual(self._used(), before + 2)


class TestStepTimer(FrappeTestCase):
	def test_records_steps_and_total(self):
		frappe.flags.pos_next_collect_perf = True
		frappe.flags.pos_next_perf_records = []
		try:
			timer = StepTimer("unit", pos_profile="P")
			timer.mark("a")
			timer.mark("b")
			total = timer.finish(invoice="X")
			record = frappe.flags.pos_next_perf_records[-1]
		finally:
			frappe.flags.pos_next_collect_perf = False

		self.assertEqual(record["op"], "unit")
		self.assertEqual(set(record["steps_ms"]), {"a", "b"})
		self.assertEqual(record["invoice"], "X")
		self.assertEqual(record["total_ms"], total)

	def test_slow_call_is_logged_as_warning(self):
		with patch.object(frappe, "logger") as get_logger:
			with patch.dict(frappe.conf, {"pos_next_slow_submit_ms": 0}):
				StepTimer("slow").finish()
		get_logger.return_value.warning.assert_called_once()

	def test_logging_failure_never_breaks_the_caller(self):
		with patch.object(frappe, "logger", side_effect=RuntimeError("disk full")):
			StepTimer("x").finish()  # must not raise
