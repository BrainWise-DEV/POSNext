# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""A verified email belongs to one customer; the shared verification reset helper.

Runs against the dev database (Customers are inserted and rolled back after
each test). OTP providers and customer benefit providers are fakes.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next import utils
from pos_next.api import email_verification as ev
from pos_next.integrations import otp
from pos_next.integrations.otp import OTP_PROVIDER_API
from pos_next.patches.v2_5_0 import report_duplicate_verified_emails as dup_patch

BENEFIT_HOOK = "pos_next_customer_benefit_providers"
BENEFIT_PATH = "test_verified_email_unique.benefit_provider"
EMAIL = "staff@acme.example"
ORIGINAL_GET_HOOKS = frappe.get_hooks
ORIGINAL_GET_ATTR = frappe.get_attr


def _leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def _customer(label, email=None):
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"_Test Verified Email {label} {frappe.generate_hash(length=6)}",
			"customer_type": "Individual",
			"customer_group": _leaf("Customer Group"),
			"territory": _leaf("Territory"),
			"email_id": email or "",
		}
	).insert(ignore_permissions=True)
	return doc.name


def _new_customer(test, label, email=None):
	"""Insert a customer, then forget the provider calls its insert made (on_update clears codes)."""
	name = _customer(label, email)
	if hasattr(test.provider, "clear"):
		test.provider.clear.reset_mock()
	return name


def _set_verified(customer, email, via="frappe_email"):
	# The validate hook wipes these fields on save, so write them directly.
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"custom_email_verified": 1,
			"custom_verified_email": email,
			"custom_email_verified_via": via,
			"custom_email_verified_by": "Administrator",
		},
		update_modified=False,
	)


def _verified(customer):
	return frappe.db.get_value(
		"Customer", customer, ["custom_email_verified", "custom_verified_email"], as_dict=True
	)


def _otp_provider(name="fake", with_clear=True):
	provider = SimpleNamespace(
		name=name,
		label=name,
		api=OTP_PROVIDER_API,
		requires_phone=False,
		health=MagicMock(return_value={"ok": True, "message": "", "fix_url": None}),
		send=MagicMock(return_value={"ok": True, "code": "sent", "message": ""}),
		verify=MagicMock(return_value={"ok": True, "code": "verified", "message": ""}),
	)
	if with_clear:
		provider.clear = MagicMock(return_value=None)
	return provider


class VerifiedEmailTestBase(FrappeTestCase):
	def setUp(self):
		self.on_change = MagicMock()
		benefit = {
			"is_member": lambda customer, pos_profile=None: False,
			"on_verification_change": self.on_change,
		}

		def get_hooks(hook=None, *args, **kwargs):
			if hook == BENEFIT_HOOK:
				return [BENEFIT_PATH]
			return ORIGINAL_GET_HOOKS(hook, *args, **kwargs)

		def get_attr(path):
			if path == BENEFIT_PATH:
				return lambda: benefit
			return ORIGINAL_GET_ATTR(path)

		self.provider = _otp_provider()
		for p in (
			patch.object(frappe, "get_hooks", get_hooks),
			patch.object(frappe, "get_attr", get_attr),
			patch.object(otp, "get_providers", lambda: {self.provider.name: self.provider}),
			patch.object(otp, "get_active_provider", lambda pos_profile: self.provider),
		):
			p.start()
			self.addCleanup(p.stop)
		# Rolls back the test's customers and releases the per-email locks it holds.
		self.addCleanup(frappe.db.rollback)

	def _prepare_for(self, customer, email):
		ctx = otp.OtpContext(customer=customer, email=email, pos_profile=None)
		settings = ev._OtpSettings()
		return patch.object(ev, "_prepare", return_value=(ctx, self.provider, settings, None))


class TestVerifiedEmailUnique(VerifiedEmailTestBase):
	def test_second_customer_same_email_rejected(self):
		a, b = _customer("A"), _customer("B")
		self.assertIsNone(ev._mark_verified(a, EMAIL, "frappe_email"))

		with self._prepare_for(b, "Staff@Acme.example"), patch.object(ev, "_audit"):
			result = ev.verify_email_otp(b, "123456", pos_profile="P1")

		self.assertFalse(result["ok"])
		self.assertEqual(result["code"], "email_in_use")
		self.assertEqual(result["message"], "This email is already verified for another customer.")
		self.assertFalse(_verified(b).custom_email_verified)
		self.assertFalse(_verified(b).custom_verified_email)

	def test_send_refused_when_email_verified_elsewhere(self):
		a, b = _customer("A"), _customer("B")
		_set_verified(a, EMAIL)

		with self._prepare_for(b, "STAFF@acme.example"), patch.object(ev, "_audit"):
			result = ev.send_email_otp(b, pos_profile="P1")

		self.assertEqual(result["code"], "email_in_use")
		self.provider.send.assert_not_called()

	def test_same_customer_reverify_ok(self):
		a = _customer("A")
		_set_verified(a, EMAIL)
		self.assertIsNone(ev._mark_verified(a, "Staff@Acme.example", "frappe_email"))
		self.assertEqual(_verified(a).custom_email_verified, 1)

	def test_email_lock_held_returns_busy(self):
		b = _customer("B")
		email = "locked@acme.example"
		lock = frappe.cache().lock(ev._email_lock_key(email), timeout=30)
		self.assertTrue(lock.acquire(blocking=False))
		try:
			result = ev._mark_verified(b, "Locked@Acme.example", "frappe_email")
		finally:
			lock.release()
		self.assertEqual(result["code"], "busy")
		self.assertFalse(_verified(b).custom_email_verified)

	def test_lock_namespaces_disjoint(self):
		self.assertNotEqual(ev._lock_key("customer", "x"), ev._lock_key("email", "x"))
		self.assertTrue(ev._email_lock_key(EMAIL).startswith(ev._lock_key("email", "")))

	def test_unverified_holder_does_not_block(self):
		# A stale custom_verified_email without the flag is not "in use".
		a, b = _customer("A"), _customer("B")
		_set_verified(a, EMAIL)
		frappe.db.set_value("Customer", a, "custom_email_verified", 0, update_modified=False)
		self.assertIsNone(ev._mark_verified(b, EMAIL, "frappe_email"))

	def test_verify_email_in_use_does_not_call_provider(self):
		a, b = _customer("A"), _customer("B")
		_set_verified(a, EMAIL)
		with self._prepare_for(b, EMAIL), patch.object(ev, "_audit"):
			result = ev.verify_email_otp(b, "123456", pos_profile="P1")
		self.assertEqual(result["code"], "email_in_use")
		self.provider.verify.assert_not_called()

	def test_verify_deadlock_at_precheck_returns_busy_code_kept(self):
		b = _customer("B")
		cache = {}
		with (
			self._prepare_for(b, EMAIL),
			patch.object(ev, "_audit"),
			patch.object(
				ev,
				"_load_state",
				lambda c: cache.setdefault("s", {"sends": [], "attempts": 0, "attempts_reset_at": 0}),
			),
			patch.object(ev, "_save_state") as save_state,
			patch.object(ev, "_email_in_use", side_effect=frappe.QueryDeadlockError("deadlock")),
		):
			result = ev.verify_email_otp(b, "123456", pos_profile="P1")
		self.assertEqual(result["code"], "busy")
		self.assertIn("try again", result["message"])
		self.provider.verify.assert_not_called()
		save_state.assert_not_called()  # no attempt counted

	def test_save_failure_after_verify_needs_new_code(self):
		b = _customer("B")
		with (
			self._prepare_for(b, EMAIL),
			patch.object(ev, "_audit"),
			patch.object(ev, "_mark_verified", side_effect=frappe.QueryDeadlockError("deadlock")),
		):
			result = ev.verify_email_otp(b, "123456", pos_profile="P1")
		self.provider.verify.assert_called_once()
		self.assertEqual(result["code"], "verification_not_saved")
		self.assertIn("new code", result["message"])

	def test_verified_email_indexed(self):
		rows = frappe.db.sql(
			"SHOW INDEX FROM `tabCustomer` WHERE Column_name='custom_verified_email'", as_dict=True
		)
		self.assertTrue(rows)
		self.assertTrue(all(int(r.Non_unique) == 1 for r in rows))

	def test_mark_verified_notifies_benefit_providers(self):
		a = _customer("A")
		self.assertIsNone(ev._mark_verified(a, "Staff@Acme.example", "frappe_email"))
		self.on_change.assert_called_once_with(a, True, "acme.example", "frappe_email")


class TestVerificationReset(VerifiedEmailTestBase):
	def _change_email(self, customer, new_email):
		doc = frappe.get_doc("Customer", customer)
		doc.email_id = new_email
		doc.has_value_changed = lambda field: field == "email_id"
		ev.reset_email_verification_on_email_change(doc)
		return doc

	def test_email_change_calls_provider_clear(self):
		a = _new_customer(self, "A")
		_set_verified(a, EMAIL)
		doc = self._change_email(a, "new@acme.example")

		self.provider.clear.assert_called_once()
		ctx = self.provider.clear.call_args.args[0]
		self.assertEqual(ctx.customer, a)
		self.assertFalse(_verified(a).custom_email_verified)
		self.assertFalse(doc.custom_email_verified)
		self.assertIsNone(doc.custom_verified_email)

	def test_email_change_unverified_clears_codes_only(self):
		a = _new_customer(self, "A")
		self._change_email(a, "new@acme.example")
		self.provider.clear.assert_called_once()
		self.on_change.assert_not_called()

	def test_provider_without_clear_ok(self):
		self.provider = _otp_provider(with_clear=False)
		a = _new_customer(self, "A")
		_set_verified(a, EMAIL)
		with patch.object(utils, "log_error_without_telemetry") as log_error:
			self._change_email(a, "new@acme.example")
		self.assertFalse(_verified(a).custom_email_verified)
		log_error.assert_not_called()

	def test_provider_clear_error_logged_and_ignored(self):
		self.provider.clear.side_effect = RuntimeError("secret detail")
		a = _new_customer(self, "A")
		_set_verified(a, EMAIL)
		with patch.object(utils, "log_error_without_telemetry") as log_error:
			ev.reset_verification(a, "test")
		self.assertFalse(_verified(a).custom_email_verified)
		self.assertNotIn("secret detail", str(log_error.call_args))

	def test_reset_verification_public_helper(self):
		a = _new_customer(self, "A")
		_set_verified(a, EMAIL)

		ev.reset_verification(a, "admin_revoke")

		row = frappe.db.get_value("Customer", a, list(ev.VERIFICATION_FIELDS), as_dict=True)
		self.assertFalse(row.custom_email_verified)
		self.assertTrue(all(not row[f] for f in ev.VERIFICATION_FIELDS))
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Customer", "reference_name": a, "content": ["like", "%reset%"]},
			pluck="content",
		)
		self.assertEqual(len(comments), 1)
		self.assertIn("admin_revoke", comments[0])
		self.provider.clear.assert_called_once()
		self.on_change.assert_called_once_with(a, False, "acme.example", "frappe_email")

	def test_benefit_provider_error_swallowed(self):
		self.on_change.side_effect = RuntimeError("boom")
		a = _new_customer(self, "A")
		with patch.object(utils, "log_error_without_telemetry") as log_error:
			self.assertIsNone(ev._mark_verified(a, EMAIL, "frappe_email"))
		self.assertEqual(_verified(a).custom_email_verified, 1)
		log_error.assert_called_once_with("Customer benefit provider", f"{BENEFIT_PATH}: RuntimeError")


class TestUpdateCustomerDuplicate(VerifiedEmailTestBase):
	def test_update_customer_duplicate_email_rejected(self):
		from pos_next.api import customers

		a = _customer("A", "owner-a@acme.example")
		b = _customer("B", "owner-b@acme.example")
		before = frappe.db.get_value("Customer", b, ["email_id", "modified"], as_dict=True)

		def resolve(**kwargs):
			self.assertEqual(kwargs["exclude_customer"], b)
			if (kwargs.get("email_id") or "").lower() == "owner-a@acme.example":
				return {
					"message": "A customer with this email already exists.",
					"existing_customer": {"name": a},
				}
			return None

		with patch.object(customers, "resolve_existing_customer", side_effect=resolve) as resolver:
			result = customers.update_customer(b, email_id="Owner-A@acme.example")

		resolver.assert_called_once()
		self.assertTrue(result["already_exists"])
		self.assertEqual(result["existing_customer"]["name"], a)
		after = frappe.db.get_value("Customer", b, ["email_id", "modified"], as_dict=True)
		self.assertEqual(after, before)

	def test_update_customer_own_email_unchanged_ok(self):
		from pos_next.api import customers

		b = _customer("B", "owner-b@acme.example")
		with patch.object(customers, "resolve_existing_customer") as resolver:
			result = customers.update_customer(
				b, customer_name="_Test Verified Email Renamed", email_id="Owner-B@acme.example"
			)
		resolver.assert_not_called()
		self.assertNotIn("already_exists", result)
		self.assertEqual(frappe.db.get_value("Customer", b, "customer_name"), "_Test Verified Email Renamed")


class TestDuplicateReportPatch(VerifiedEmailTestBase):
	def test_existing_duplicates_reported(self):
		a, b = _customer("A"), _customer("B")
		shared = f"shared-{frappe.generate_hash(length=8)}@acme.example"
		_set_verified(a, shared)
		_set_verified(b, shared.upper())

		duplicates = dup_patch.find_duplicates()
		self.assertEqual(sorted(duplicates[shared]), sorted([a, b]))

		logs_before = frappe.db.count("Error Log", {"method": dup_patch.LOG_TITLE})
		dup_patch.execute()
		logs = frappe.get_all(
			"Error Log", filters={"method": dup_patch.LOG_TITLE}, fields=["error"], order_by="creation desc"
		)
		self.assertEqual(len(logs), logs_before + 1)
		# Customer names with the email domain only, never the full address.
		self.assertNotIn(shared.partition("@")[0], logs[0].error)
		self.assertIn("@acme.example", logs[0].error)
		self.assertIn(a, logs[0].error)
		self.assertIn(b, logs[0].error)
		self.assertEqual(_verified(a).custom_verified_email, shared)
		self.assertEqual(_verified(b).custom_verified_email, shared.upper())


class TestEmailLockLifetime(VerifiedEmailTestBase):
	"""The per-email lock outlives the ``with`` block and ends with the transaction."""

	CUSTOMER = "_Test Email Lock Lifetime"  # no row: _mark_verified updates nothing

	def _assert_held_then_released(self, end_transaction):
		email = f"lifetime-{frappe.generate_hash(length=8)}@acme.example"
		key = ev._email_lock_key(email)
		self.assertIsNone(ev._mark_verified(self.CUSTOMER, email, "frappe_email"))

		probe = frappe.cache().lock(key, timeout=30)
		self.assertFalse(probe.acquire(blocking=False), "lock released before the transaction ended")
		self.assertIn(key, ev._held_locks())

		end_transaction()

		self.assertEqual(ev._held_locks(), set())
		self.assertTrue(probe.acquire(blocking=False), "lock still held after the transaction ended")
		probe.release()

	def test_released_on_rollback(self):
		self._assert_held_then_released(frappe.db.rollback)

	def test_released_on_commit(self):
		self._assert_held_then_released(frappe.db.commit)
