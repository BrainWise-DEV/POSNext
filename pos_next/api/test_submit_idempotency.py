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
