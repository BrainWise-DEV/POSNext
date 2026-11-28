# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Large-invoice, duplicate-prevention and instrumentation tests for the submit path.

These run against a real site (they post stock and GL) but create their own
items and opening stock in ``setUpClass``; FrappeTestCase rolls everything back.
They need a POS Profile with a warehouse, a default customer and a Cash payment
method; the test is skipped if the site has none.
"""

import json
import os
import time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.perf import StepTimer
from pos_next.tests.invoice_fixtures import (
	QueryCounter,
	build_invoice,
	create_stocked_items,
	fingerprint,
)

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
		cls.items = create_stocked_items(cls.profile, LARGE_INVOICE_LINES)

	def setUp(self):
		if not self.profile:
			self.skipTest("No POS Profile with warehouse, customer and Cash payment on this site")
		frappe.set_user("Administrator")

	def _draft(self, lines, request_id=None):
		data = build_invoice(self.profile, self.items, lines)
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

		fp = fingerprint(result["name"])
		expected_total = sum(
			flt(r["rate"]) for r in build_invoice(self.profile, self.items, LARGE_INVOICE_LINES)["items"]
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
		with QueryCounter() as counter:
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

		items = create_stocked_items(profile, 3, prefix="_BENCH-SP-ITEM")
		data = build_invoice(profile, items, 3)
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
			invoices._ensure_offline_uniqueness("pos_online_test-lock")
		lookups = [c for c in get_value.call_args_list if c.args and c.args[0] == "Offline Invoice Sync"]
		self.assertEqual(len(lookups), 1)  # missing key: one plain read, no locking read
		self.assertFalse(lookups[0].kwargs.get("for_update"))


class TestRepeatedItemDetailPass(_SubmitPathBase):
	"""Only validate's repeat of update_invoice's own pass is skipped, nothing else."""

	def _count_item_detail_passes(self, action):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

		real = SalesInvoice.set_missing_values
		with patch.object(SalesInvoice, "set_missing_values", autospec=True, side_effect=real) as parent:
			action()
		return parent.call_count

	def test_update_invoice_runs_the_pass_once_not_twice(self):
		data = json.dumps(build_invoice(self.profile, self.items, 5))
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


class TestRetryKeyLookup(FrappeTestCase):
	"""Concurrent / overlapping requests with the same key (offline_id or client_request_id)."""

	def _other_connection(self):
		import pymysql

		conn = pymysql.connect(**frappe.db.get_connection_settings())
		conn.autocommit(True)
		return conn

	def test_row_committed_after_our_snapshot_is_found_not_reported_missing(self):
		"""The reported bug: 'Offline Invoice Sync <name> not found' on an overlapping retry.

		Another request commits the sync record after this request's snapshot was taken.
		A locking read sees it; a later plain read would not.
		"""
		if frappe.db.db_type != "mariadb":
			self.skipTest("MariaDB only")

		frappe.db.sql("select count(*) from `tabItem`")  # take this transaction's snapshot
		key, name = "pos_online_test-snapshot-1", "benchsnap0001"
		other = self._other_connection()
		try:
			with other.cursor() as cur:
				cur.execute(
					"insert into `tabOffline Invoice Sync` "
					"(name, creation, modified, modified_by, owner, docstatus, idx, offline_id, status, sales_invoice) "
					"values (%s, now(6), now(6), 'Administrator', 'Administrator', 0, 0, %s, 'Failed', '')",
					(name, key),
				)
			result = invoices._ensure_offline_uniqueness(key)
			self.assertEqual(result["sync_record_name"], name)
			self.assertFalse(result["already_synced"])
			self.assertEqual(frappe.db.get_value("Offline Invoice Sync", name, "status"), "Pending")
		finally:
			frappe.db.rollback()
			with other.cursor() as cur:
				cur.execute("delete from `tabOffline Invoice Sync` where name = %s", (name,))
			other.close()

	def test_synced_invoice_is_read_with_a_current_read(self):
		sync_row = frappe._dict(
			name="syncrow1", sales_invoice="ACC-SINV-X", status="Synced", modified=frappe.utils.now_datetime()
		)
		invoice_row = frappe._dict(
			name="ACC-SINV-X",
			docstatus=1,
			grand_total=10,
			total=10,
			net_total=9,
			outstanding_amount=0,
			paid_amount=10,
			change_amount=0,
		)
		reads = []

		def fake_get_value(doctype, filters=None, fieldname=None, **kwargs):
			reads.append((doctype, kwargs.get("for_update")))
			return sync_row if doctype == "Offline Invoice Sync" else invoice_row

		with patch.object(frappe.db, "get_value", side_effect=fake_get_value):
			result = invoices._ensure_offline_uniqueness("key-1")

		self.assertTrue(result["already_synced"])
		self.assertTrue(result["invoice_data"]["duplicate_prevented"])
		self.assertEqual(result["invoice_data"]["name"], "ACC-SINV-X")
		self.assertIn(("Sales Invoice", True), reads)  # not a snapshot read
		self.assertIn(("Offline Invoice Sync", True), reads)  # existing row: locking, current read

	def test_lookup_gives_up_cleanly_instead_of_recursing_forever(self):
		with (
			patch.object(invoices, "_read_sync_record", return_value=None),
			patch.object(frappe, "get_doc") as get_doc,
		):
			get_doc.return_value.insert.side_effect = frappe.UniqueValidationError(
				"Offline Invoice Sync", "x"
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				invoices._ensure_offline_uniqueness("key-2")
		self.assertIn("currently being processed", str(ctx.exception))
		self.assertEqual(get_doc.return_value.insert.call_count, invoices.SYNC_LOOKUP_ATTEMPTS)


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
		data = build_invoice(self.profile, self.items, 3)
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


class TestDiagnosticsLoggersReallyWrite(FrappeTestCase):
	"""frappe.logger() defaults to ERROR, which silently drops warnings: check the real loggers."""

	def _read_new_lines(self, logger_name, action):
		path = frappe.get_site_path("logs", f"{logger_name}.log")
		before = os.path.getsize(path) if os.path.exists(path) else 0
		action()
		for handler in frappe.logger(logger_name).handlers:
			handler.flush()
		with open(path) as fh:
			fh.seek(before)
			return fh.read()

	def test_slow_call_warning_is_written_with_default_settings(self):
		with patch.dict(frappe.conf, {"pos_next_slow_submit_ms": 0, "pos_next_perf_log_all": 0}):
			written = self._read_new_lines("pos_next_perf", lambda: StepTimer("slow_probe").finish())
		self.assertIn("slow_probe", written)

	def test_deadlock_context_line_is_written_with_default_settings(self):
		from pos_next.diagnostics import log_lock_failure

		def action():
			try:
				raise frappe.QueryDeadlockError("synthetic")
			except frappe.QueryDeadlockError as exc:
				log_lock_failure(exc, "unit_probe")

		written = self._read_new_lines("pos_next_deadlock", action)
		self.assertIn("unit_probe", written)

	def test_blocked_statement_is_read_from_the_failing_sql_frame_without_values(self):
		from pos_next.diagnostics import describe_lock_failure

		def sql(self, query):  # same name and module path as Frappe's Database.sql
			raise frappe.QueryTimeoutError("(1205, 'Lock wait timeout exceeded')")

		sql.__code__ = sql.__code__.replace(co_filename="/x/frappe/database/database.py")
		try:
			sql(None, "SELECT `current` FROM `tabSeries` WHERE `name`='SECRET-VALUE-' FOR UPDATE")
		except frappe.QueryTimeoutError as exc:
			info = describe_lock_failure(exc, "unit")
		self.assertEqual(info["statement"], "SELECT `tabSeries` FOR UPDATE")
		self.assertNotIn("SECRET", json.dumps(info, default=str))
		self.assertEqual(
			info["kind"], "lock_wait_timeout_unknown_errno"
		)  # no MariaDB number on this synthetic error

	def test_statement_shape_never_contains_values(self):
		from pos_next.diagnostics import statement_shape

		self.assertEqual(
			statement_shape(
				"INSERT INTO `tabSales Invoice Item` (`name`, `item_code`) VALUES ('A1', 'SECRET')"
			),
			"INSERT INTO `tabSales Invoice Item`",
		)
		self.assertEqual(
			statement_shape("SELECT `current` FROM `tabSeries` WHERE `name`='ACC-SINV-2026-' FOR UPDATE"),
			"SELECT `tabSeries` FOR UPDATE",
		)
		self.assertIsNone(statement_shape(None))

	def test_failing_child_table_is_read_from_the_traceback(self):
		from pos_next.diagnostics import describe_lock_failure

		item = frappe.new_doc("Sales Invoice Item")
		item.parenttype, item.parentfield, item.idx = "Sales Invoice", "items", 7

		def db_insert(self):  # same function name Frappe uses
			raise frappe.QueryDeadlockError("synthetic")

		try:
			db_insert(item)
		except frappe.QueryDeadlockError as exc:
			info = describe_lock_failure(exc, "unit")
		self.assertEqual(info["failing"]["doctype"], "Sales Invoice Item")
		self.assertEqual(info["failing"]["parentfield"], "items")
		self.assertEqual(info["failing"]["row_idx"], 7)
		self.assertEqual(
			info["connection"]["tx_isolation_session"], info["connection"]["tx_isolation_global"]
		)


class TestDeadlockRetrySafety(_SubmitPathBase):
	"""What a deadlock victim leaves behind, and that repeating the call is safe.

	Frappe rolls the whole request back when it raises (app.py: ``rollback`` stays True and
	the ``finally`` block calls ``frappe.db.rollback()`` for POST requests). A savepoint
	stands in for that rollback here, because rolling back the whole test transaction would
	also remove the items and stock these tests need.
	"""

	def _deadlock_once_on(self, target):
		"""Raise QueryDeadlockError the first time ``target`` is called (Document.<name>)."""
		from frappe.model.document import Document

		real = getattr(Document, target)
		state = {"raised": 0}

		def flaky(doc, *args, **kwargs):
			if state["raised"] == 0 and (target != "db_insert" or doc.doctype == "Sales Invoice Item"):
				state["raised"] += 1
				raise frappe.QueryDeadlockError("(1213, 'Deadlock found when trying to get lock')")
			return real(doc, *args, **kwargs)

		return patch.object(Document, target, flaky)

	def _count(self, marker):
		return frappe.db.count("Sales Invoice", {"po_no": marker})

	def test_deadlock_while_creating_the_draft_leaves_nothing_and_retry_creates_one(self):
		marker = "_BENCHC-retry-draft"
		data = build_invoice(self.profile, self.items, 4)
		data["po_no"] = marker

		frappe.db.savepoint("before_attempt")
		with self._deadlock_once_on("db_insert"):
			with self.assertRaises(frappe.QueryDeadlockError):  # same type, not wrapped or swallowed
				invoices.update_invoice(json.dumps(data))
		frappe.db.rollback(save_point="before_attempt")
		self.assertEqual(self._count(marker), 0)

		draft = invoices.update_invoice(json.dumps(data))  # the cashier screen's retry
		self.assertEqual(self._count(marker), 1)
		self.assertEqual(draft["docstatus"], 0)

	def test_deadlock_during_submit_then_retry_with_same_key_makes_exactly_one_sale(self):
		marker, key = "_BENCHC-retry-submit", "pos_online_test-retry-submit"
		data = build_invoice(self.profile, self.items, 4)
		data["po_no"] = marker
		draft = invoices.update_invoice(json.dumps(data))
		submit_data = {"client_request_id": key}

		frappe.db.savepoint("before_attempt")
		with self._deadlock_once_on("submit"):
			with self.assertRaises(frappe.QueryDeadlockError):
				self._submit(draft, submit_data)
		frappe.db.rollback(save_point="before_attempt")
		# the failed attempt left no retry-key row behind to block the retry
		self.assertFalse(frappe.db.exists("Offline Invoice Sync", {"offline_id": key}))

		result = self._submit(draft, submit_data)  # retry, same key
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		self.assertEqual(frappe.db.count("Sales Invoice", {"po_no": marker, "docstatus": 1}), 1)
		self.assertEqual(
			frappe.db.count("Stock Ledger Entry", {"voucher_no": result["name"], "is_cancelled": 0}), 4
		)  # stock moved once
		self.assertEqual(frappe.db.get_value("Offline Invoice Sync", {"offline_id": key}, "status"), "Synced")

		# even a third, unnecessary repeat cannot make a second sale
		again = self._submit(draft, submit_data)
		self.assertEqual(again["name"], result["name"])
		self.assertTrue(again["duplicate_prevented"])

	def test_checkout_calls_never_commit_so_the_rollback_discards_everything(self):
		draft_data = build_invoice(self.profile, self.items, 3)
		with patch.object(frappe.db, "commit", side_effect=CommitCalled("commit inside checkout")):
			draft = invoices.update_invoice(json.dumps(draft_data))
			self._submit(draft, {"client_request_id": "pos_online_test-no-commit"})

	def test_realtime_events_are_deferred_until_commit(self):
		"""So a rolled-back attempt announces nothing (a full rollback clears the after-commit queue)."""
		emitted = []
		with patch.object(frappe, "publish_realtime", side_effect=lambda *a, **k: emitted.append(k)):
			draft = invoices.update_invoice(json.dumps(build_invoice(self.profile, self.items, 3)))
			self._submit(draft, {})
		self.assertTrue(emitted, "expected the checkout to emit realtime events")
		self.assertTrue(all(call.get("after_commit") for call in emitted), emitted)


class TestDbErrorClassification(FrappeTestCase):
	"""Errors are told apart by the real MariaDB error number, never by message text alone."""

	def _wrapped(self, errno, wrapper):
		import pymysql

		driver = pymysql.err.OperationalError(errno, "text")
		try:
			raise wrapper(driver) from driver
		except wrapper as exc:
			return exc

	def test_each_failure_kind_has_its_own_class(self):
		from pos_next.db_errors import classify

		cases = {
			1213: (frappe.QueryDeadlockError, "deadlock_1213"),
			1020: (frappe.QueryDeadlockError, "snapshot_conflict_1020"),  # Frappe also calls this a deadlock
			1205: (frappe.QueryTimeoutError, "lock_wait_timeout_1205"),
			3024: (Exception, "query_time_limit"),
			2013: (Exception, "connection_lost"),
		}
		for errno, (wrapper, kind) in cases.items():
			result = classify(self._wrapped(errno, wrapper))
			self.assertEqual((result["kind"], result["errno"]), (kind, errno), errno)

	def test_only_lock_errors_are_reraised_by_the_guard(self):
		from pos_next.db_errors import reraise_if_lock_error

		for errno, wrapper in ((1213, frappe.QueryDeadlockError), (1205, frappe.QueryTimeoutError)):
			with self.assertRaises(wrapper):
				reraise_if_lock_error(self._wrapped(errno, wrapper))
		reraise_if_lock_error(ValueError("not a lock error"))  # must not raise


class TestLockErrorsAreNotSwallowed(_SubmitPathBase):
	"""A lock error inside a hook that catches everything must still fail the checkout.

	Emulates what the server does (a savepoint rollback to the request start stands for
	InnoDB rolling back the whole transaction on a deadlock; a plain error for a 1205 that only
	undoes one statement) inside process_loyalty_to_wallet, which runs after the stock and
	ledger postings. Before the fix, submit_invoice returned success while the invoice was still
	a draft with no stock or GL entries (deadlock), or lost the wallet credit silently (timeout).
	"""

	def setUp(self):
		super().setUp()
		if not frappe.db.exists("Loyalty Program", "Wallet"):
			self.skipTest("Loyalty Program 'Wallet' missing")
		self.loyalty_profile = None
		for name in frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="name"):
			settings = frappe.db.get_value(
				"POS Settings",
				{"pos_profile": name},
				["enable_loyalty_program", "loyalty_to_wallet"],
				as_dict=True,
			)
			profile = frappe.get_doc("POS Profile", name)
			has_cash = any(p.mode_of_payment == "Cash" for p in profile.payments)
			if settings and settings.enable_loyalty_program and settings.loyalty_to_wallet and has_cash:
				self.loyalty_profile = profile
				break
		if not self.loyalty_profile:
			self.skipTest("No POS Profile with loyalty-to-wallet conversion enabled")
		cls = type(self)
		if getattr(cls, "_loyalty_items", None) is None:  # items and stock are created once per class
			cls._loyalty_items = create_stocked_items(self.loyalty_profile, 3, prefix="_BENCH-LOCK-ITEM")
			cls._customer_made = False
		self.loyalty_items = cls._loyalty_items

	def _loyalty_sale(self):
		if not frappe.db.exists("Customer", {"customer_name": "_BENCH-CUST-LOCK"}):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "_BENCH-CUST-LOCK",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
					"customer_type": "Individual",
					"loyalty_program": "Wallet",
				}
			).insert(ignore_permissions=True)
		customer = frappe.get_doc("Customer", {"customer_name": "_BENCH-CUST-LOCK"})
		data = build_invoice(self.loyalty_profile, self.loyalty_items, 3)
		data["customer"] = customer.name
		for row in data["items"]:
			row["rate"] = row["price_list_rate"] = 600.0  # above the program's minimum spend
		data["payments"] = [{"mode_of_payment": "Cash", "amount": 1800.0}]
		return invoices.update_invoice(json.dumps(data))

	def _victim(self, error_class, rollback_whole_transaction):
		def fail(*args, **kwargs):
			if rollback_whole_transaction:
				frappe.db.sql("rollback to savepoint request_start")
			raise error_class("lock error")

		return patch("pos_next.api.wallet.get_or_create_wallet", fail)

	def _ledger_rows(self, name):
		return (
			frappe.db.count("Stock Ledger Entry", {"voucher_no": name, "is_cancelled": 0}),
			frappe.db.count("GL Entry", {"voucher_no": name, "is_cancelled": 0}),
		)

	def test_deadlock_in_the_hook_fails_the_checkout_instead_of_returning_success(self):
		draft = self._loyalty_sale()
		frappe.db.savepoint("request_start")
		with self._victim(frappe.QueryDeadlockError, rollback_whole_transaction=True):
			with self.assertRaises(frappe.QueryDeadlockError):
				self._submit(draft, {})
		# the request handler's rollback: nothing of the failed attempt remains, and the draft is intact
		frappe.db.rollback(save_point="request_start")
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)
		self.assertEqual(self._ledger_rows(draft["name"]), (0, 0))

	def test_lock_timeout_in_the_hook_fails_the_checkout_instead_of_dropping_the_wallet_credit(self):
		draft = self._loyalty_sale()
		frappe.db.savepoint("request_start")
		with self._victim(frappe.QueryTimeoutError, rollback_whole_transaction=False):
			with self.assertRaises(frappe.QueryTimeoutError):
				self._submit(draft, {})
		# a 1205 undoes one statement only: the earlier postings are still in the open transaction,
		# which is exactly why the request MUST be rolled back as a whole
		self.assertGreater(self._ledger_rows(draft["name"])[0], 0)
		frappe.db.rollback(save_point="request_start")
		self.assertEqual(self._ledger_rows(draft["name"]), (0, 0))
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)

	def test_other_errors_in_the_hook_are_still_tolerated(self):
		"""Behaviour that is kept on purpose: a non-lock failure must not fail the sale."""
		draft = self._loyalty_sale()
		with patch("pos_next.api.wallet.get_or_create_wallet", side_effect=ValueError("bad wallet config")):
			result = self._submit(draft, {})
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)


class _RealLockBase(_SubmitPathBase):
	"""Base for 1205 tests: a real second connection holds a real lock (innodb_lock_wait_timeout = 1 s).

	One test per subclass on purpose: a savepoint rollback does not release row locks, so a lock the
	test's own transaction took in an earlier test would block the blocker connection itself.
	"""

	def setUp(self):
		super().setUp()
		if frappe.db.db_type != "mariadb":
			self.skipTest("MariaDB only")
		self.blocker = None
		frappe.db.sql("set session innodb_lock_wait_timeout = 1")

	def tearDown(self):
		self._release()
		frappe.db.sql("set session innodb_lock_wait_timeout = %s", (50,))

	def _hold(self, query, params):
		import pymysql

		self.blocker = pymysql.connect(**frappe.db.get_connection_settings())
		self.blocker.autocommit(False)
		with self.blocker.cursor() as cur:
			cur.execute(query, params)  # a locking read: the lock lives until the connection rolls back

	def _release(self):
		if self.blocker is not None:
			self.blocker.rollback()
			self.blocker.close()
			self.blocker = None

	def _series_key(self):
		key = f"ACC-SINV-{frappe.utils.nowdate()[:4]}-"
		if not frappe.db.exists("Series", key):
			self.skipTest(f"Series {key} not present")
		return key


class TestRealLockWaitTimeoutOnUpdateInvoice(_RealLockBase):
	"""update_invoice blocked on the invoice-number series row."""

	def test_update_invoice_blocked_on_the_series_row(self):
		marker = "_BENCHC-1205-draft"
		data = build_invoice(self.profile, self.items, 3)
		data["po_no"] = marker
		self._hold("select name from `tabSeries` where name = %s for update", (self._series_key(),))

		self.assertEqual(frappe.db.sql("select @@global.innodb_rollback_on_timeout")[0][0], 0)
		frappe.db.savepoint("request_start")
		frappe.db.sql(
			"insert into `tabToDo` (name, creation, modified, owner, modified_by, description) "
			"values ('_bench1205', now(), now(), 'Administrator', 'Administrator', 'marker')"
		)
		started = time.time()
		with self.assertRaises(frappe.QueryTimeoutError) as caught:
			invoices.update_invoice(json.dumps(data))
		self.assertGreaterEqual(time.time() - started, 0.9)  # it really waited for the lock

		from pos_next.db_errors import classify

		self.assertEqual(classify(caught.exception)["kind"], "lock_wait_timeout_1205")
		# 1205 undid only the blocked statement: earlier work of this request is still there ...
		self.assertTrue(frappe.db.exists("ToDo", "_bench1205"))
		# ... until the request handler rolls the whole transaction back
		frappe.db.rollback(save_point="request_start")
		self.assertFalse(frappe.db.exists("ToDo", "_bench1205"))
		self.assertEqual(frappe.db.count("Sales Invoice", {"po_no": marker}), 0)

		self._release()  # the blocker finishes; the cashier's retry now works
		draft = invoices.update_invoice(json.dumps(data))
		self.assertEqual(frappe.db.count("Sales Invoice", {"po_no": marker}), 1)
		self.assertEqual(draft["docstatus"], 0)


class TestRealLockWaitTimeoutOnSubmitInvoice(_RealLockBase):
	"""submit_invoice blocked on the Company row that every submit updates."""

	def test_submit_invoice_blocked_on_the_company_row(self):
		marker, key = "_BENCHC-1205-submit", "pos_online_test-1205-submit"
		data = build_invoice(self.profile, self.items, 3)
		data["po_no"] = marker
		draft = invoices.update_invoice(json.dumps(data))
		self._hold("select name from `tabCompany` where name = %s for update", (self.profile.company,))

		frappe.db.savepoint("request_start")
		with self.assertRaises(frappe.QueryTimeoutError):
			self._submit(draft, {"client_request_id": key})

		# statement-level rollback only: the stock postings made before the blocked UPDATE are
		# still in the open transaction, so the retry-key row and the invoice are half done ...
		self.assertGreater(
			frappe.db.count("Stock Ledger Entry", {"voucher_no": draft["name"], "is_cancelled": 0}), 0
		)
		# ... until the request is rolled back as a whole (what Frappe does for a failed POST)
		frappe.db.rollback(save_point="request_start")
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": draft["name"]}), 0)
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": draft["name"]}), 0)
		self.assertFalse(frappe.db.exists("Offline Invoice Sync", {"offline_id": key}))

		self._release()
		result = self._submit(draft, {"client_request_id": key})  # retry, same key
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		self.assertEqual(frappe.db.count("Sales Invoice", {"po_no": marker, "docstatus": 1}), 1)
		self.assertEqual(
			frappe.db.count("Stock Ledger Entry", {"voucher_no": result["name"], "is_cancelled": 0}), 3
		)
		again = self._submit(draft, {"client_request_id": key})
		self.assertTrue(again["duplicate_prevented"])  # a further repeat cannot add a second sale


class TestSaveKeepsFrappesChildTableLocking(FrappeTestCase):
	"""Guard: do NOT remove the child-table locking Frappe takes when saving an existing invoice.

	Saving an existing Sales Invoice loads the stored copy ``FOR UPDATE`` (every child table) and
	runs a ``DELETE ... WHERE parent = ...`` per child table. Under REPEATABLE READ those range locks
	block another cashier's NEW draft inserts (measured: a 1205 on ``INSERT INTO tabSales Invoice
	Item`` for as long as a submit lasted). They were removed in an experiment, which fixed that
	blocking but made concurrent submits of the same items deadlock in the stock ledger:

	    12 cashiers, 2 hot items, 144 sales:   Frappe locking   143 ok, 1 deadlock
	                                           locks removed     48 ok, 96 deadlocks (stock ledger)

	The locks also serialise submits of adjacent invoices, which ERPNext's stock ledger posting
	depends on. Overriding ``load_doc_before_save`` or ``update_child_table`` for POS invoices is
	therefore unsafe. See INVOICE_SUBMIT_PERFORMANCE_PLAN.md (section 3c).
	"""

	def test_the_overrides_that_removed_those_locks_stay_removed(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
		from frappe.model.document import Document

		from pos_next.overrides.sales_invoice import CustomSalesInvoice

		for name in ("load_doc_before_save", "update_child_table"):
			self.assertIs(
				getattr(CustomSalesInvoice, name),
				getattr(SalesInvoice, name),
				f"CustomSalesInvoice must not override {name} (see this test's docstring)",
			)
		self.assertIs(SalesInvoice.update_child_table, Document.update_child_table)


class TestItemDetailsStayInsideTheSave(_SubmitPathBase):
	"""Guard: submit_invoice must NOT refresh item details before Frappe's save takes its locks.

	Doing that refresh (about a fifth of a 100-line submit) just before the save shortened the
	locked window by ~13% and halved draft-creation latency, but it multiplied stock-ledger
	deadlocks about 80 times:

	    12 cashiers, 2 hot items, 3 seeds x 144 sales, default lock wait
	                         sales ok    1213 deadlocks (all in the stock ledger)   draft p50
	    refresh in the save    430/432                    2                          6.6 s
	    refresh before locks   273/432                  159                          3.6 s

	The timing of submits relative to each other decides whether they collide in the stock ledger;
	ERPNext's stock posting only stays safe with the current order. Do not move work across the
	point where the save takes its locks. See INVOICE_SUBMIT_PERFORMANCE_PLAN.md (section 3d).
	"""

	def test_the_refresh_happens_inside_the_save_after_the_locks(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
		from frappe.model.document import Document

		draft = invoices.update_invoice(json.dumps(build_invoice(self.profile, self.items, 4)))
		events = []
		real_missing, real_latest = SalesInvoice.set_missing_values, Document.check_if_latest

		def missing(doc, *args, **kwargs):
			events.append("item_details")
			return real_missing(doc, *args, **kwargs)

		def latest(doc, *args, **kwargs):
			events.append("locks_taken")  # check_if_latest loads the stored copy FOR UPDATE
			return real_latest(doc, *args, **kwargs)

		with patch.object(SalesInvoice, "set_missing_values", missing):
			with patch.object(Document, "check_if_latest", latest):
				self._submit(draft, {})
		order = [e for e in events if e in ("item_details", "locks_taken")]
		self.assertEqual(order[0], "locks_taken", order)
		self.assertIn("item_details", order[1:], order)


class TestSubmitWithAVanishedDraft(_SubmitPathBase):
	"""The cashier screen reuses the draft of an unchanged cart when the payment is retried.

	If that draft was removed meanwhile (cleanup of old drafts, an administrator), the submit must
	create a fresh one instead of failing on the stale name.
	"""

	def test_submit_recreates_a_deleted_draft_instead_of_failing(self):
		marker = "_BENCHC-vanished-draft"
		data = build_invoice(self.profile, self.items, 3)
		data["po_no"] = marker
		draft = invoices.update_invoice(json.dumps(data))
		frappe.delete_doc("Sales Invoice", draft["name"], force=1, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Sales Invoice", draft["name"]))

		result = self._submit(draft, {"client_request_id": "pos_online_test-vanished"})

		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		self.assertEqual(frappe.db.count("Sales Invoice", {"po_no": marker, "docstatus": 1}), 1)
		self.assertEqual(
			frappe.db.count("Stock Ledger Entry", {"voucher_no": result["name"], "is_cancelled": 0}), 3
		)


class TestStepTimer(FrappeTestCase):
	def test_records_steps_and_total(self):
		with patch.object(frappe, "logger") as get_logger:
			with patch.dict(frappe.conf, {"pos_next_perf_log_all": 1}):
				timer = StepTimer("unit", pos_profile="P")
				timer.mark("a")
				timer.mark("b")
				total = timer.finish(invoice="X")
		record = json.loads(get_logger.return_value.info.call_args.args[0])

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
