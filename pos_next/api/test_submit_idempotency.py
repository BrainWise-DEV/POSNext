# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""An online submit is idempotent on its client key (UI test D-19).

The POS sends ``data.idempotency_key`` with every online Sales Invoice submit and
keeps it while it retries the same cart. When the response of a submit that
succeeded is lost, the retry returns that invoice instead of creating a second
sale. The key is reserved in the Offline Invoice Sync table (unique
``offline_id``), namespaced, and never makes the submit an offline sync.

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_submit_idempotency'}"
"""

import json
import threading
import time
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.test_promotions import ITEM_A, ITEM_PRICES, _cart_payload, _ctx, _line

PREFIX = "_PNXT_F5_"
SYNC = "Offline Invoice Sync"


def _key():
	return f"{PREFIX}{frappe.generate_hash(length=20)}"


def _discard(name):
	if not frappe.db.exists("Sales Invoice", name):
		return
	doc = frappe.get_doc("Sales Invoice", name)
	if doc.docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.cancel()
	frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)


class TestSubmitIdempotency(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")

	def _invoice(self, rate=None):
		line = _line(self.ctx, ITEM_A)
		if rate is not None:
			price = ITEM_PRICES[ITEM_A]
			line.update(
				{"rate": rate, "discount_amount": price - rate, "discount_percentage": 100 * (price - rate) / price}
			)
		payload = _cart_payload(self.ctx, [line])
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		return payload

	def _submit(self, invoice, key):
		result = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({"idempotency_key": key}))
		self.addCleanup(_discard, result["name"])
		return result

	def _count(self):
		return frappe.db.count("Sales Invoice", {"customer": self.ctx.customer, "docstatus": 1})

	def test_repeated_key_returns_the_submitted_invoice(self):
		key = _key()
		first = self._submit(self._invoice(), key)
		before = self._count()
		again = self._submit(self._invoice(), key)
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(self._count(), before, "the retry created a second invoice")
		self.assertTrue(again.get("duplicate_prevented"))
		self.assertEqual(flt(again["grand_total"]), flt(first["grand_total"]))
		self.assertNotIn("offline_id", again)

	def test_repeated_key_by_name_of_a_new_draft_returns_the_submitted_invoice(self):
		"""After a lost response the POS checks the price again (a new unpaid draft)
		and submits that draft by name with the same key."""
		key = _key()
		first = self._submit(self._invoice(), key)
		draft = update_invoice(json.dumps(dict(self._invoice(), payments=[])))
		self.addCleanup(_discard, draft["name"])
		again = self._submit(dict(self._invoice(), name=draft["name"]), key)
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)

	def test_resume_by_name_of_the_submitted_draft_returns_it(self):
		"""The POS resume path: the checked draft was submitted by the lost request; the
		retry sends that same name, with the same key and payments."""
		key = _key()
		draft = update_invoice(json.dumps(dict(self._invoice(), payments=[])))
		self.addCleanup(_discard, draft["name"])
		first = self._submit(dict(self._invoice(), name=draft["name"]), key)
		self.assertEqual(first["name"], draft["name"])
		before = self._count()
		again = self._submit(dict(self._invoice(), name=draft["name"]), key)
		self.assertEqual(again["name"], draft["name"])
		self.assertTrue(again.get("duplicate_prevented"))
		self.assertEqual(self._count(), before)

	def _offline(self, invoice, offline_id, key=None):
		invoice = dict(invoice, offline_id=offline_id)
		if key:
			invoice["idempotency_key"] = key
		result = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({}))
		self.addCleanup(_discard, result["name"])
		return result

	def test_offline_sync_with_the_key_returns_the_online_invoice(self):
		"""I-1 (Ruling 139): the response was lost, the POS went offline and queued the
		same cart with its key: the sync returns the online invoice, no second sale."""
		key = _key()
		first = self._submit(self._invoice(), key)
		before = self._count()
		offline_id = f"pos_offline_{PREFIX}{frappe.generate_hash(length=12)}"
		synced = self._offline(self._invoice(), offline_id, key)
		self.assertEqual(synced["name"], first["name"])
		self.assertEqual(synced.get("offline_id"), offline_id)
		self.assertEqual(self._count(), before)
		# The offline id now points at that invoice: a re-sync is a no-op too.
		self.assertEqual(self._offline(self._invoice(), offline_id, key)["name"], first["name"])
		self.assertEqual(self._count(), before)

	def test_offline_sync_with_a_new_key_owns_it(self):
		"""An offline sale queued with a key no online submit made: it is made once,
		and a late online retry with that key returns it."""
		key = _key()
		offline_id = f"pos_offline_{PREFIX}{frappe.generate_hash(length=12)}"
		made = self._offline(self._invoice(), offline_id, key)
		before = self._count()
		again = self._submit(self._invoice(), key)
		self.assertEqual(again["name"], made["name"])
		self.assertEqual(self._count(), before)

	def test_different_keys_are_different_sales(self):
		first = self._submit(self._invoice(), _key())
		second = self._submit(self._invoice(), _key())
		self.assertNotEqual(first["name"], second["name"])

	def test_refused_submit_keeps_the_key_free(self):
		key = _key()
		with patch.object(invoices, "_validate_stock_on_invoice", side_effect=frappe.ValidationError("refused")):
			with self.assertRaises(frappe.ValidationError):
				submit_invoice(invoice=json.dumps(self._invoice()), data=json.dumps({"idempotency_key": key}))
		result = self._submit(self._invoice(), key)
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		self.assertFalse(result.get("duplicate_prevented"))

	def test_key_never_makes_the_submit_an_offline_sync(self):
		seen = {}
		real = invoices._update_invoice

		def spy(data, offline_sync=False, submitting=False):
			seen["offline_sync"] = offline_sync
			return real(data, offline_sync=offline_sync, submitting=submitting)

		real_submit = frappe.model.document.Document.submit

		def submit_spy(doc):
			if doc.doctype == "Sales Invoice":
				seen["flag"] = doc.flags.pos_offline_sync
			return real_submit(doc)

		with patch.object(invoices, "_update_invoice", spy), patch.object(
			frappe.model.document.Document, "submit", submit_spy
		):
			self._submit(self._invoice(), _key())
		self.assertIs(seen["offline_sync"], False)
		self.assertFalse(seen["flag"])

	def test_invalid_key_refused(self):
		for bad in ("", "x" * 200, "a b", {"k": 1}):
			if bad == "":
				continue
			with self.assertRaises(frappe.ValidationError):
				submit_invoice(invoice=json.dumps(self._invoice()), data=json.dumps({"idempotency_key": bad}))


def _discard_order(name):
	if not frappe.db.exists("Sales Order", name):
		return
	doc = frappe.get_doc("Sales Order", name)
	if doc.docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.cancel()
	frappe.delete_doc("Sales Order", name, force=True, ignore_permissions=True)


class TestSalesOrderSubmitKey(FrappeTestCase):
	"""F6 item 2 (Ruling 138, F4 I-R1): the key covers a Sales Order submit too, so a
	restored or retried Sales Order cart never makes a second order."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")

	def _order(self):
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A)])
		payload.update({"doctype": "Sales Order", "delivery_date": frappe.utils.nowdate(), "payments": []})
		return payload

	def _submit(self, order, key):
		result = submit_invoice(invoice=json.dumps(order), data=json.dumps({"idempotency_key": key}))
		self.addCleanup(_discard_order, result["name"])
		return result

	def _count(self):
		return frappe.db.count("Sales Order", {"customer": self.ctx.customer, "docstatus": 1})

	def _f6_key(self):
		return f"_PNXT_F6_{frappe.generate_hash(length=20)}"

	def test_repeated_key_returns_the_submitted_order(self):
		key = self._f6_key()
		first = self._submit(self._order(), key)
		self.assertEqual(frappe.db.get_value("Sales Order", first["name"], "docstatus"), 1)
		before = self._count()
		again = self._submit(self._order(), key)
		self.assertEqual(again["name"], first["name"])
		self.assertTrue(again.get("duplicate_prevented"))
		self.assertEqual(again.get("idempotency_key"), key)
		self.assertEqual(self._count(), before, "the retry created a second Sales Order")

	def test_retry_by_name_of_a_new_order_draft_returns_the_order(self):
		"""The POS saves an order draft before each submit: the retry's new draft is not
		submitted, the first order is returned."""
		key = self._f6_key()
		first = self._submit(self._order(), key)
		draft = update_invoice(json.dumps(self._order()))
		self.addCleanup(_discard_order, draft["name"])
		again = self._submit(dict(self._order(), name=draft["name"]), key)
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(frappe.db.get_value("Sales Order", draft["name"], "docstatus"), 0)

	def test_an_order_key_is_not_an_invoice_key(self):
		"""Reserved per doctype: the same key on an invoice is another sale."""
		key = self._f6_key()
		order = self._submit(self._order(), key)
		invoice = dict(_cart_payload(self.ctx, [_line(self.ctx, ITEM_A)]))
		invoice["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		made = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({"idempotency_key": key}))
		self.addCleanup(_discard, made["name"])
		self.assertTrue(frappe.db.exists("Sales Invoice", made["name"]))
		self.assertFalse(made.get("duplicate_prevented"))
		self.assertNotEqual(made["name"], order["name"])

	def test_check_reports_the_made_order(self):
		"""The POS asks about a cleared key on reconnect (Ruling 143) under its doctype."""
		key = self._f6_key()
		order = self._submit(self._order(), key)
		answer = invoices.check_offline_invoice_synced(f"{invoices.ONLINE_ORDER_KEY_PREFIX}{key}")
		self.assertTrue(answer.get("synced"))
		self.assertEqual(answer.get("sales_invoice"), order["name"])
		self.assertTrue(invoices.ONLINE_ORDER_KEY_PREFIX.startswith(invoices.ONLINE_SUBMIT_KEY_PREFIX))

	def test_offline_sale_carrying_an_order_key_returns_the_order(self):
		"""Ruling 146 (c): offline, the cashier says it is the same sale as an order whose
		response was lost. The queued sale (a Sales Invoice payload) carries the order's
		key and its doctype: the sync returns the order, no invoice is made."""
		key = self._f6_key()
		order = self._submit(self._order(), key)
		invoice = dict(_cart_payload(self.ctx, [_line(self.ctx, ITEM_A)]))
		invoice["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		offline_id = f"pos_offline__PNXT_F6_{frappe.generate_hash(length=12)}"
		invoice.update({"offline_id": offline_id, "idempotency_key": key, "idempotency_doctype": "Sales Order"})
		before = frappe.db.count("Sales Invoice", {"customer": self.ctx.customer, "docstatus": 1})
		synced = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({}))
		if frappe.db.exists("Sales Invoice", synced["name"]):
			self.addCleanup(_discard, synced["name"])
		self.assertEqual(synced["name"], order["name"])
		self.assertTrue(synced.get("duplicate_prevented"))
		self.assertEqual(frappe.db.count("Sales Invoice", {"customer": self.ctx.customer, "docstatus": 1}), before)
		# Ruling 149: no sync row names the order under the offline id (a broken
		# Sales Invoice link in the health report); a re-sync is caught by the key.
		self.assertFalse(frappe.db.exists(SYNC, {"offline_id": offline_id}))
		again = submit_invoice(invoice=json.dumps(invoice), data=json.dumps({}))
		self.assertEqual(again["name"], order["name"])

	def test_a_key_carried_into_an_order_is_found_on_a_second_retry(self):
		"""m-e: an invoice cart's key carried into an order ([Same sale]); the order is made
		under the invoice key. A second lost response, retried with the same carry, returns
		that order instead of making a second one."""
		key = self._f6_key()
		carried = dict(self._order(), idempotency_doctype="Sales Invoice")
		first = self._submit(carried, key)
		before = self._count()
		again = self._submit(carried, key)
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(self._count(), before)

	def test_invalid_key_doctype_refused(self):
		invoice = dict(_cart_payload(self.ctx, [_line(self.ctx, ITEM_A)]))
		invoice["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		with patch.object(invoices, "_validate_stock_on_invoice", side_effect=AssertionError("not reached")):
			with self.assertRaises(frappe.ValidationError) as caught:
				submit_invoice(
					invoice=json.dumps(invoice),
					data=json.dumps({"idempotency_key": self._f6_key(), "idempotency_doctype": "Journal Entry"}),
				)
		self.assertIn("Invalid submit key", str(caught.exception))

	def test_a_cancelled_order_frees_its_key(self):
		"""The key's row points at an order that is gone: the retry makes the order (the
		row is reused although its link column holds an order name)."""
		key = self._f6_key()
		first = self._submit(self._order(), key)
		doc = frappe.get_doc("Sales Order", first["name"])
		doc.flags.ignore_permissions = True
		doc.cancel()
		again = self._submit(self._order(), key)
		self.assertNotEqual(again["name"], first["name"])
		self.assertEqual(frappe.db.get_value("Sales Order", again["name"], "docstatus"), 1)


class TestSubmittedBeforeStock(FrappeTestCase):
	"""F6 item 3 (Ruling 138, F4 re-review): saving a draft that was already submitted
	is refused as submitted, before stock is checked, so a stock error (the sale took
	the last unit) never hides it from the POS."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")

	def test_submitted_draft_refused_as_submitted_not_as_stock(self):
		line = _line(self.ctx, ITEM_A)
		payload = _cart_payload(self.ctx, [line])
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		made = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(_discard, made["name"])
		stock_error = [{"item_code": ITEM_A, "message": "_PNXT_F6_ out of stock"}]
		with patch.object(invoices, "_should_block", return_value=True), patch.object(
			invoices, "_collect_stock_errors", return_value=stock_error
		):
			with self.assertRaises(frappe.DocstatusTransitionError) as caught:
				update_invoice(json.dumps(dict(payload, name=made["name"], payments=[])))
		self.assertIn(made["name"], str(caught.exception))
		self.assertEqual(frappe.db.get_value("Sales Invoice", made["name"], "docstatus"), 1)

	def test_a_draft_still_gets_the_stock_error(self):
		"""Guard: a real draft is still refused for stock."""
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_A)])
		draft = update_invoice(json.dumps(payload))
		self.addCleanup(_discard, draft["name"])
		stock_error = [{"item_code": ITEM_A, "message": "_PNXT_F6_ out of stock"}]
		with patch.object(invoices, "_should_block", return_value=True), patch.object(
			invoices, "_collect_stock_errors", return_value=stock_error
		):
			with self.assertRaises(frappe.ValidationError) as caught:
				update_invoice(json.dumps(dict(payload, name=draft["name"])))
		self.assertNotIsInstance(caught.exception, frappe.DocstatusTransitionError)


class TestSubmitIdempotencyConcurrent(unittest.TestCase):
	"""Two requests with one key at the same time, each on its own DB connection.

	Commits on nexus.local; everything it creates is removed in tearDown."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.ctx = _ctx()
		frappe.db.commit()
		self.site = frappe.local.site
		self.names = []

	def tearDown(self):
		# Committed rows: retried, as other runs on the shared dev DB may hold locks.
		for attempt in range(5):
			frappe.db.rollback()
			try:
				for name in set(self.names):
					_discard(name)
				frappe.db.delete(SYNC, {"offline_id": ["like", f"%{PREFIX}%"]})
				frappe.db.commit()
				return
			except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
				if attempt == 4:
					raise
				time.sleep(3)

	def test_two_concurrent_requests_make_one_invoice(self):
		key = _key()
		line = _line(self.ctx, ITEM_A)
		payload = _cart_payload(self.ctx, [line])
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_A]}]
		barrier = threading.Barrier(2)
		results, errors = [], []

		def worker():
			frappe.init(site=self.site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				barrier.wait(timeout=30)
				try:
					result = submit_invoice(
						invoice=json.dumps(payload), data=json.dumps({"idempotency_key": key})
					)
					frappe.db.commit()
					results.append(result["name"])
				except Exception as error:
					frappe.db.rollback()
					errors.append(f"{type(error).__name__}: {error}")
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=worker) for _ in range(2)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		self.names.extend(results)
		frappe.db.rollback()
		submitted = frappe.get_all(
			SYNC, filters={"offline_id": ["like", f"%{key}"]}, fields=["sales_invoice", "status"]
		)
		print("CONCURRENT results", results, "errors", errors, "sync", submitted, flush=True)
		self.assertEqual(len(set(results)), 1, (results, errors))
		self.assertEqual(len(submitted), 1)
		self.assertEqual(submitted[0].sales_invoice, results[0])
		# The second request returns the first one's invoice; it is not refused.
		self.assertEqual(errors, [])
		self.assertEqual(len(results), 2)


class TestSubmitKeysDoNotSerialise(unittest.TestCase):
	"""I-3 (Ruling 139): reserving one key never waits on another key's open submit."""

	HOLD = 8

	def test_two_different_keys_reserve_without_waiting(self):
		site = frappe.local.site
		reserved = threading.Event()
		done = threading.Event()
		timing, errors = {}, []

		def run(key, hold):
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				if not hold:
					reserved.wait(timeout=30)
				started = time.monotonic()
				invoices._ensure_offline_uniqueness(
					f"{invoices.ONLINE_SUBMIT_KEY_PREFIX}{key}", pos_profile=None, customer=None
				)
				timing[key] = time.monotonic() - started
				if hold:
					reserved.set()
					# Keep the submit's transaction open, as a long submit does.
					done.wait(timeout=self.HOLD)
				else:
					done.set()
			except Exception as error:
				errors.append(f"{type(error).__name__}: {error}")
				reserved.set()
			finally:
				frappe.db.rollback()
				frappe.destroy()

		first, second = _key(), _key()
		threads = [threading.Thread(target=run, args=(first, True)), threading.Thread(target=run, args=(second, False))]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=120)
		print("KEYS timing", timing, "errors", errors, flush=True)
		self.assertEqual(errors, [])
		self.assertLess(timing[second], 3, "the second key waited on the first key's open reservation")


class TestKeyCheckSeesInFlight(unittest.TestCase):
	"""Ruling 149 (C-1): asking about a key never reports a submit that is still running
	as "not made". The check probes by inserting the reservation in a savepoint (a record
	lock through the unique index, no gap lock) and rolls it back; a Pending or
	uncommitted reservation answers as in flight, which the POS treats as no answer."""

	HOLD = 3

	def setUp(self):
		frappe.set_user("Administrator")
		self.ids = []

	def tearDown(self):
		frappe.db.rollback()
		for offline_id in self.ids:
			frappe.db.delete(SYNC, {"offline_id": offline_id})
		frappe.db.commit()

	def _id(self):
		offline_id = f"{invoices.ONLINE_SUBMIT_KEY_PREFIX}_PNXT_F6_{frappe.generate_hash(length=16)}"
		self.ids.append(offline_id)
		return offline_id

	def test_a_pending_reservation_is_in_flight(self):
		offline_id = self._id()
		invoices._insert_sync_reservation(offline_id)
		frappe.db.commit()
		answer = invoices.check_offline_invoice_synced(offline_id)
		self.assertFalse(answer.get("synced"))
		self.assertTrue(answer.get("in_flight"), answer)

	def test_a_key_never_made_is_not_in_flight(self):
		answer = invoices.check_offline_invoice_synced(self._id())
		self.assertFalse(answer.get("synced"))
		self.assertFalse(answer.get("in_flight"))
		self.assertEqual(frappe.db.count(SYNC, {"offline_id": self.ids[-1]}), 0, "the probe left a row")

	def test_an_uncommitted_reservation_is_waited_for_and_reported_in_flight(self):
		"""The first submit is still running: its reservation is not committed yet."""
		offline_id = self._id()
		site = frappe.local.site
		reserved = threading.Event()
		errors = []

		def hold():
			frappe.init(site=site)
			frappe.connect()
			try:
				frappe.set_user("Administrator")
				invoices._insert_sync_reservation(offline_id)
				reserved.set()
				time.sleep(self.HOLD)
				frappe.db.commit()  # the reservation lands (still Pending: the submit goes on)
			except Exception as error:
				errors.append(f"{type(error).__name__}: {error}")
				reserved.set()
			finally:
				frappe.destroy()

		thread = threading.Thread(target=hold)
		thread.start()
		reserved.wait(timeout=30)
		frappe.db.rollback()
		started = time.monotonic()
		answer = invoices.check_offline_invoice_synced(offline_id)
		waited = time.monotonic() - started
		thread.join(timeout=60)
		self.assertEqual(errors, [])
		self.assertFalse(answer.get("synced"))
		self.assertTrue(answer.get("in_flight"), answer)
		self.assertGreater(waited, self.HOLD - 1, "the check did not wait for the open reservation")


class TestSyncHealthReport(FrappeTestCase):
	"""I-2: the offline sync report never counts online submit keys."""

	def test_online_keys_left_out(self):
		from pos_next.pos_next.report.offline_sync_and_system_health_report import (
			offline_sync_and_system_health_report as report,
		)

		offline_id = f"pos_offline_{PREFIX}{frappe.generate_hash(length=12)}"
		online_id = f"{invoices.ONLINE_SUBMIT_KEY_PREFIX}{_key()}"
		for name in (offline_id, online_id):
			doc = frappe.get_doc({"doctype": SYNC, "offline_id": name, "status": "Synced"})
			doc.flags.ignore_permissions = True
			doc.insert()
		_columns, data, _msg, chart, summary = report.execute({})
		ids = {row.offline_id for row in data}
		self.assertIn(offline_id, ids)
		self.assertFalse([i for i in ids if i.startswith(invoices.ONLINE_SUBMIT_KEY_PREFIX)])
		total = next(s["value"] for s in summary if s["label"] == "Total Sync Attempts")
		self.assertEqual(total, len(data))
		self.assertEqual(sum(chart["data"]["datasets"][0]["values"]), len(data))
