# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Security hardening: verification settings are manager-only, OTP and invoice
endpoints require an allowed POS Profile, and no OTP reaches logs or Sentry.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_security_hardening'}"
"""

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from pos_next.api import bootstrap, sales_invoice_hooks
from pos_next.api import email_verification as ev
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.integrations import otp
from pos_next.integrations import otp_frappe_email as frappe_email
from pos_next.patches.v2_5_0 import pos_settings_verification_permlevel as perm_patch
from pos_next.pos_next.doctype.pos_settings.pos_settings import update_pos_settings
from pos_next.test_fixtures import ensure_pos_profile
from pos_next.test_promotions import (
	ITEM_C,
	_cart_payload,
	_ctx,
	_line,
	_resolve_customer_group,
	_resolve_territory,
)

CASHIER = "pnxt8e.cashier@example.com"
MANAGER = "pnxt8e.manager@example.com"
OTP = "482913"
CASHIER_ROLE = "POSNext Cashier"
MANAGER_ROLE = "Nexus POS Manager"


def _ensure_user(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	if role not in [r.role for r in user.roles]:
		user.add_roles(role)
	return email


def _settings_name(profile):
	name = frappe.db.get_value("POS Settings", {"pos_profile": profile})
	if name:
		return name
	return (
		frappe.get_doc({"doctype": "POS Settings", "pos_profile": profile, "enabled": 1})
		.insert(ignore_permissions=True)
		.name
	)


def _customer(email=None):
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"_PNXT_8E_{frappe.generate_hash(length=8)}",
				"customer_group": _resolve_customer_group(),
				"territory": _resolve_territory(),
				"customer_type": "Individual",
				"email_id": email,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _raising_provider():
	def boom(*args):
		raise RuntimeError(f"provider failed for {args!r} {OTP}")

	return SimpleNamespace(
		name="pnxt8e_raising",
		label="raising",
		api=otp.OTP_PROVIDER_API,
		requires_phone=False,
		health=lambda: {"ok": True, "message": "", "fix_url": None},
		send=boom,
		verify=boom,
	)


class TestSecurityHardening(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		cls.profile_a = cls.ctx.pos_profile
		cls.profile_b = ensure_pos_profile("_PNXT_TEST_SECURITY_PROFILE_B")
		_ensure_user(CASHIER, CASHIER_ROLE)
		_ensure_user(MANAGER, MANAGER_ROLE)
		profile = frappe.get_doc("POS Profile", cls.profile_a)
		if not any(u.user == CASHIER for u in profile.get("applicable_for_users", [])):
			profile.append("applicable_for_users", {"user": CASHIER})
			profile.flags.ignore_permissions = True
			profile.save()
		cls.settings_a = _settings_name(cls.profile_a)
		cls.settings_b = _settings_name(cls.profile_b)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		# Drop everything the tests wrote before committing the cleanup below.
		frappe.db.rollback()
		frappe.set_user("Administrator")
		profile = frappe.get_doc("POS Profile", cls.profile_a)
		profile.set("applicable_for_users", [u for u in profile.applicable_for_users if u.user != CASHIER])
		profile.flags.ignore_permissions = True
		profile.save()
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self._saved = {
			name: frappe.db.get_value(
				"POS Settings",
				name,
				[
					"otp_max_sends_per_hour",
					"enable_customer_email_verification",
					"require_split_name",
					"placeholder_email_domain",
					"default_phone_country",
					"hide_expected_amount",
					"otp_resend_cooldown",
				],
				as_dict=True,
			)
			for name in (self.settings_a, self.settings_b)
		}
		for name in (self.settings_a, self.settings_b):
			frappe.db.set_value("POS Settings", name, "otp_max_sends_per_hour", 5)
		self.addCleanup(self._restore_settings)
		frappe.local.pos_next_otp_providers = None
		self.addCleanup(lambda: setattr(frappe.local, "pos_next_otp_providers", None))

	def _restore_settings(self):
		frappe.set_user("Administrator")
		for name, values in self._saved.items():
			frappe.db.set_value("POS Settings", name, values, update_modified=False)

	def _limit(self, name=None):
		return frappe.db.get_value("POS Settings", name or self.settings_a, "otp_max_sends_per_hour")

	# ------------------------------------------------------------------
	# C1: verification settings are manager-only
	# ------------------------------------------------------------------

	def test_cashier_cannot_change_otp_limits(self):
		frappe.set_user(CASHIER)
		doc = frappe.get_doc("POS Settings", self.settings_a)
		doc.otp_max_sends_per_hour = 100000
		doc.save()  # Desk-style save: Frappe resets the permlevel-1 field silently
		self.assertEqual(self._limit(), 5)

		update_pos_settings(self.profile_a, json.dumps({"otp_max_sends_per_hour": 100000}))
		self.assertEqual(self._limit(), 5)

	def test_manager_can_change_otp_limits(self):
		frappe.set_user(MANAGER)
		self.assertTrue(otp.can_manage_verification())
		update_pos_settings(self.profile_a, {"otp_max_sends_per_hour": 7})
		self.assertEqual(self._limit(), 7)

		doc = frappe.get_doc("POS Settings", self.settings_a)
		doc.otp_max_sends_per_hour = 9
		doc.save()
		self.assertEqual(self._limit(), 9)

	def test_cashier_cannot_list_provider_health(self):
		frappe.set_user(CASHIER)
		self.assertFalse(otp.can_manage_verification())
		with self.assertRaises(frappe.PermissionError):
			otp.get_provider_options()
		frappe.set_user(MANAGER)
		self.assertIn("frappe_email", [p["name"] for p in otp.get_provider_options()])

	def test_onload_flag_follows_permlevel(self):
		frappe.set_user(CASHIER)
		doc = frappe.get_doc("POS Settings", self.settings_a)
		doc.run_method("onload")
		self.assertFalse(doc.get_onload().get("can_manage_verification"))
		frappe.set_user(MANAGER)
		doc = frappe.get_doc("POS Settings", self.settings_a)
		doc.run_method("onload")
		self.assertTrue(doc.get_onload().get("can_manage_verification"))

	def test_update_pos_settings_other_profile_rejected(self):
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			update_pos_settings(self.profile_b, {"otp_max_sends_per_hour": 100000})
		with self.assertRaises(frappe.PermissionError):
			update_pos_settings("", {"otp_max_sends_per_hour": 100000})
		self.assertEqual(self._limit(self.settings_b), 5)

	def test_cashier_bootstrap_still_gets_verification_fields(self):
		country = frappe.db.get_value("Country", {}, "name")
		frappe.db.set_value(
			"POS Settings",
			self.settings_a,
			{
				"require_split_name": 1,
				"placeholder_email_domain": "pos.example",
				"default_phone_country": country,
			},
		)
		frappe.set_user(CASHIER)
		shift = {
			"name": "PNXT-8E-SHIFT",
			"pos_profile": self.profile_a,
			"period_start_date": now_datetime(),
			"status": "Open",
			"pos_profile_doc": frappe.get_cached_doc("POS Profile", self.profile_a),
		}
		with patch.object(bootstrap, "_get_open_shift", return_value=shift):
			settings = bootstrap.get_initial_data()["pos_settings"]
		self.assertEqual(settings["require_split_name"], 1)
		self.assertEqual(settings["placeholder_email_domain"], "pos.example")
		self.assertEqual(settings["default_phone_country"], country)

	# ------------------------------------------------------------------
	# I1: OTP endpoints require an allowed profile
	# ------------------------------------------------------------------

	def test_missing_profile_rejected(self):
		frappe.set_user(CASHIER)
		for blank in (None, ""):
			with self.subTest(pos_profile=blank):
				with self.assertRaises(frappe.PermissionError):
					ev.send_email_otp("ANY-CUSTOMER", pos_profile=blank)
				with self.assertRaises(frappe.PermissionError):
					ev.verify_email_otp("ANY-CUSTOMER", OTP, pos_profile=blank)

	def test_foreign_profile_rejected_for_otp(self):
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			ev.send_email_otp("ANY-CUSTOMER", pos_profile=self.profile_b)
		with self.assertRaises(frappe.PermissionError):
			ev.verify_email_otp("ANY-CUSTOMER", OTP, pos_profile=self.profile_b)

	# ------------------------------------------------------------------
	# I2: invoice endpoints require an allowed profile
	# ------------------------------------------------------------------

	def _payload(self, profile, amount=0):
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C)])
		payload["pos_profile"] = profile
		payload["payments"] = (
			[{"mode_of_payment": self.ctx.mode_of_payment, "amount": amount}] if amount else []
		)
		return payload

	def test_update_invoice_foreign_profile_rejected(self):
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			update_invoice(json.dumps(self._payload(self.profile_b)))

	def test_submit_invoice_foreign_profile_rejected(self):
		frappe.set_user(CASHIER)
		offline_id = f"pos_offline_8e_{frappe.generate_hash(length=10)}"
		payload = self._payload(self.profile_b, amount=20)
		payload["offline_id"] = offline_id
		with self.assertRaises(frappe.PermissionError):
			submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		# Refused before the offline dedup: no reservation was made.
		self.assertFalse(frappe.db.exists("Offline Invoice Sync", {"offline_id": offline_id}))

	def test_update_invoice_blank_profile_rejected(self):
		frappe.set_user(CASHIER)
		for blank in (None, ""):
			with self.subTest(pos_profile=blank):
				with self.assertRaises(frappe.PermissionError):
					update_invoice(json.dumps(self._payload(blank)))
				with self.assertRaises(frappe.PermissionError):
					submit_invoice(invoice=json.dumps(self._payload(blank, amount=20)), data=json.dumps({}))

	def test_own_profile_invoice_ok(self):
		frappe.set_user(CASHIER)
		draft = update_invoice(json.dumps(self._payload(self.profile_a)))
		self.assertEqual(draft["pos_profile"], self.profile_a)
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)

	def test_other_profile_draft_cannot_be_overwritten(self):
		draft = update_invoice(json.dumps(self._payload(self.profile_b)))  # Administrator
		frappe.set_user(CASHIER)
		payload = self._payload(self.profile_a)
		payload["name"] = draft["name"]
		with self.assertRaises(frappe.PermissionError):
			update_invoice(json.dumps(payload))
		with self.assertRaises(frappe.PermissionError):
			submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "pos_profile"), self.profile_b)

	def test_payment_collected_flag_set(self):
		seen = []
		original = sales_invoice_hooks.validate

		def spy(doc, method=None):
			seen.append(doc.flags.get("pos_payment_collected"))
			return original(doc, method)

		with patch.object(sales_invoice_hooks, "validate", spy):
			update_invoice(json.dumps(self._payload(self.profile_a, amount=100)))
			self.assertIs(seen[-1], True)
			update_invoice(json.dumps(self._payload(self.profile_a)))
			self.assertIs(seen[-1], False)

			seen.clear()
			draft = update_invoice(json.dumps(self._payload(self.profile_a, amount=100)))
			submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
			self.assertTrue(seen and all(v is True for v in seen), seen)

	def test_type_hints_accept_client_shapes(self):
		"""Whitelist argument validation runs in requests and when flags.in_test is set."""
		in_test = frappe.local.flags.in_test
		frappe.local.flags.in_test = True
		self.addCleanup(setattr, frappe.local.flags, "in_test", in_test)

		# frappe-ui createResource: data as an object
		draft = update_invoice(data=self._payload(self.profile_a, amount=20))
		# sync.js: one JSON string wrapping {invoice, data}
		payload = self._payload(self.profile_a, amount=20)
		result = submit_invoice(data=json.dumps({"invoice": payload, "data": {"sales_team": []}}))
		self.assertEqual(frappe.db.get_value("Sales Invoice", result["name"], "docstatus"), 1)
		# useInvoice submit: invoice + data as JSON strings
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		update_pos_settings(self.profile_a, settings={"otp_max_sends_per_hour": 5})
		update_pos_settings(self.profile_a, settings=json.dumps({"otp_max_sends_per_hour": 5}))

	# ------------------------------------------------------------------
	# I5: no OTP in telemetry or logs
	# ------------------------------------------------------------------

	def _run_raising_provider(self):
		frappe.db.set_value("POS Settings", self.settings_a, "enable_customer_email_verification", 1)
		email = f"pnxt8e.{frappe.generate_hash(length=8)}@example.com"
		customer = _customer(email)
		provider = _raising_provider()
		with patch.object(otp, "get_active_provider", return_value=provider):
			sent = ev.send_email_otp(customer, pos_profile=self.profile_a)
			verified = ev.verify_email_otp(customer, OTP, pos_profile=self.profile_a)
		return customer, email, sent, verified

	def test_no_otp_reaches_sentry(self):
		calls = []

		def spy(message=None):
			calls.append((sys.exc_info(), message))

		with patch("frappe.utils.sentry.capture_exception", spy):
			_, _, sent, verified = self._run_raising_provider()
		self.assertEqual(sent["code"], "unavailable")
		self.assertEqual(verified["code"], "unavailable")
		self.assertEqual(calls, [], "provider failures must not reach Sentry")

	def test_error_log_has_class_name_only(self):
		since = now_datetime()
		customer, email, _, _ = self._run_raising_provider()
		logs = frappe.get_all(
			"Error Log",
			filters={"method": "Customer Email OTP provider", "creation": [">=", since]},
			pluck="error",
		)
		self.assertIn("Provider call failed: RuntimeError", logs)
		blob = "\n".join(logs)
		self.assertNotIn(OTP, blob)
		self.assertNotIn(email, blob)
		self.assertNotIn(customer, blob)

	# ------------------------------------------------------------------
	# TTL cache keys are read with expires=True (real Redis, one process)
	# ------------------------------------------------------------------

	def test_ttl_keys_fresh_in_same_process(self):
		customer = f"_PNXT_8E_CACHE_{frappe.generate_hash(length=8)}"
		ctx = otp.OtpContext(customer=customer, email="cache@example.com", pos_profile=self.profile_a)
		self.addCleanup(frappe_email.clear_code, customer)
		self.addCleanup(frappe.cache().delete_value, ev._state_key(customer))

		# A miss first: without expires=True Frappe memoises it for the process.
		self.assertEqual(frappe_email._verify(ctx, "000000")["code"], "expired")
		sent = {}
		with patch.object(frappe, "sendmail", lambda **kw: sent.update(kw["args"])):
			self.assertEqual(frappe_email._send(ctx)["code"], "sent")
		self.assertEqual(frappe_email._verify(ctx, sent["code"])["code"], "verified")
		self.assertEqual(len(sent["code"]), ev.OTP_LENGTH)

		self.assertEqual(ev._load_state(customer)["attempts"], 0)
		state = ev._load_state(customer)
		state["attempts"] = 3
		ev._save_state(customer, state)
		self.assertEqual(ev._load_state(customer)["attempts"], 3)

	def test_otp_length_constant(self):
		self.assertEqual(ev.OTP_LENGTH, 6)
		self.assertTrue(ev.OTP_RE.match("1" * ev.OTP_LENGTH))
		self.assertFalse(ev.OTP_RE.match("1" * (ev.OTP_LENGTH - 1)))
		self.assertFalse(ev.OTP_RE.match("1" * (ev.OTP_LENGTH + 1)))

	# ------------------------------------------------------------------
	# Patch: leftover fixture Custom DocPerm rows
	# ------------------------------------------------------------------

	def test_patch_plan_redundant_set_deleted(self):
		def row(name, role, level=0, **flags):
			return frappe._dict(name=name, role=role, permlevel=level, **flags)

		standard = [
			row("s1", "R1", read=1, write=1),
			row("s2", "R2", read=1),
			row("s3", "R1", 1, read=1, write=1),
			row("s4", "R3", 1, read=1, write=1),
		]
		same = [row("c1", "R2", read=1), row("c2", "R1", read=1, write=1)]
		self.assertEqual(perm_patch.plan(same, standard), (["c1", "c2"], []))
		self.assertEqual(perm_patch.plan([], standard), ([], []))

	def test_patch_plan_customised_set_kept(self):
		def row(name, role, level=0, **flags):
			return frappe._dict(name=name, role=role, permlevel=level, **flags)

		standard = [
			row("s1", "R1", read=1, write=1),
			row("s2", "R2", read=1),
			row("s3", "R1", 1, read=1, write=1),
			row("s4", "R2", 1, read=1),
			row("s5", "R3", 1, read=1, write=1),
		]
		# Subset of the DocType rows (R2 removed by the site): not redundant.
		subset = [row("c1", "R1", read=1, write=1)]
		deleted, added = perm_patch.plan(subset, standard)
		self.assertEqual(deleted, [])
		# Level 1 only for roles with level-0 read in the custom set (R1), never R2/R3.
		self.assertEqual([(r["role"], r["permlevel"], r["write"]) for r in added], [("R1", 1, 1)])
		# Edited flags: also a customisation; a role already at level 1 gets nothing.
		edited = [row("c1", "R1", read=1, write=0), row("c2", "R2", read=1), row("c3", "R1", 1, read=1)]
		deleted, added = perm_patch.plan(edited, standard)
		self.assertEqual((deleted, [r["role"] for r in added]), ([], ["R2"]))

	def test_patch_execute_both_branches(self):
		def row(name, role, level=0, **flags):
			return frappe._dict(name=name, role=role, permlevel=level, **flags)

		standard = [row("s1", "R1", read=1), row("s2", "R1", 1, read=1, write=1)]
		for custom, expect_deleted, expect_added in (
			([row("c1", "R1", read=1)], ["c1"], 0),
			([row("c1", "R1", read=1, write=1)], [], 1),
		):
			with self.subTest(custom=custom):
				tables = {"Custom DocPerm": custom, "DocPerm": standard}
				with (
					patch.object(perm_patch, "_rows", lambda dt: tables[dt]),
					patch.object(perm_patch.frappe, "delete_doc") as delete_doc,
					patch.object(perm_patch.frappe, "get_doc") as get_doc,
					patch.object(perm_patch.frappe, "clear_cache"),
				):
					perm_patch.execute()
				self.assertEqual([c.args[1] for c in delete_doc.call_args_list], expect_deleted)
				self.assertEqual(get_doc.call_count, expect_added)
				if expect_added:
					inserted = get_doc.call_args.args[0]
					self.assertEqual(
						(inserted["doctype"], inserted["role"], inserted["permlevel"]),
						("Custom DocPerm", "R1", 1),
					)

	# ------------------------------------------------------------------
	# Fix round 1
	# ------------------------------------------------------------------

	def _otp_ready_customer(self):
		frappe.db.set_value("POS Settings", self.settings_a, "enable_customer_email_verification", 1)
		return _customer(f"pnxt8e.{frappe.generate_hash(length=8)}@example.com")

	def test_db_error_in_otp_endpoint_is_unavailable_not_5xx(self):
		ok_provider = SimpleNamespace(
			name="pnxt8e_ok",
			label="ok",
			api=otp.OTP_PROVIDER_API,
			requires_phone=False,
			health=lambda: {"ok": True, "message": "", "fix_url": None},
			send=lambda ctx: {"ok": True, "code": "sent", "message": ""},
			verify=lambda ctx, code: {"ok": True, "code": "verified", "message": ""},
		)
		calls = []
		customer = self._otp_ready_customer()
		with (
			patch("frappe.utils.sentry.capture_exception", lambda message=None: calls.append(sys.exc_info())),
			patch.object(otp, "get_active_provider", return_value=ok_provider),
			patch.object(ev, "_locked_email_check", side_effect=frappe.QueryDeadlockError("deadlock " + OTP)),
		):
			res = ev.verify_email_otp(customer, OTP, pos_profile=self.profile_a)
		self.assertEqual(res["code"], "unavailable")
		self.assertNotIn(OTP, json.dumps(res))
		self.assertEqual(calls, [])

		customer = self._otp_ready_customer()  # the guard rolled the first one back
		with (
			patch("frappe.utils.sentry.capture_exception", lambda message=None: calls.append(sys.exc_info())),
			patch.object(otp, "get_active_provider", return_value=ok_provider),
			patch.object(ev, "_email_in_use", side_effect=frappe.QueryTimeoutError("timeout")),
		):
			res = ev.send_email_otp(customer, pos_profile=self.profile_a)
		self.assertEqual(res["code"], "unavailable")
		self.assertEqual(calls, [])

	def test_otp_log_insert_failure_is_swallowed(self):
		def boom():
			raise RuntimeError("x")

		with patch("pos_next.utils.log_error_without_telemetry", side_effect=RuntimeError("db down")):
			self.assertEqual(otp.call_provider(boom)["code"], "unavailable")

	def _blank_profile_draft(self, doctype="Sales Invoice"):
		if doctype == "Sales Invoice":
			name = update_invoice(json.dumps(self._payload(self.profile_a)))["name"]
			frappe.db.set_value("Sales Invoice", name, "pos_profile", None)  # as a Desk draft
			return name
		line = _line(self.ctx, ITEM_C)
		line["delivery_date"] = frappe.utils.add_days(frappe.utils.nowdate(), 1)
		return (
			frappe.get_doc(
				{
					"doctype": "Sales Order",
					"customer": self.ctx.customer,
					"company": self.ctx.company,
					"currency": self.ctx.currency,
					"selling_price_list": self.ctx.price_list,
					"delivery_date": line["delivery_date"],
					"items": [line],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_blank_profile_desk_draft_refused(self):
		name = self._blank_profile_draft()
		frappe.set_user(CASHIER)
		payload = self._payload(self.profile_a)
		payload["name"] = name
		with self.assertRaises(frappe.PermissionError):
			update_invoice(json.dumps(payload))
		with self.assertRaises(frappe.PermissionError):
			submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("Sales Invoice", name, "pos_profile"))

	def test_blank_profile_sales_order_refused(self):
		name = self._blank_profile_draft("Sales Order")
		frappe.set_user(CASHIER)
		payload = self._payload(self.profile_a)
		payload.update({"doctype": "Sales Order", "name": name})
		with self.assertRaises(frappe.PermissionError):
			update_invoice(json.dumps(payload))

	def test_non_string_profile_or_name_rejected(self):
		frappe.set_user(CASHIER)
		for key, value in (("pos_profile", [self.profile_a]), ("name", {"like": "%"}), ("name", 7)):
			with self.subTest(key=key, value=value):
				payload = self._payload(self.profile_a)
				payload[key] = value
				with self.assertRaises(frappe.PermissionError):
					update_invoice(json.dumps(payload))

	def test_offline_id_of_other_profile_refused(self):
		offline_id = f"pos_offline_8e_{frappe.generate_hash(length=10)}"
		frappe.get_doc(
			{
				"doctype": "Offline Invoice Sync",
				"offline_id": offline_id,
				"pos_profile": self.profile_b,
				"status": "Pending",
				"sales_invoice": "",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Offline Invoice Sync", {"offline_id": offline_id}, "modified", "2020-01-01")
		frappe.set_user(CASHIER)
		payload = self._payload(self.profile_a, amount=20)
		payload["offline_id"] = offline_id
		with self.assertRaises(frappe.PermissionError):
			submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))

	def test_update_pos_settings_ignores_identity_fields(self):
		owner_b = frappe.db.get_value("POS Settings", self.settings_b, "owner")
		frappe.set_user(CASHIER)
		result = update_pos_settings(
			self.profile_a,
			{
				"name": self.settings_b,
				"doctype": "POS Settings",
				"owner": "x@example.com",
				"modified": "2020-01-01",
				"pos_profile": self.profile_b,
				"hide_expected_amount": 1,
			},
		)
		frappe.set_user("Administrator")
		self.assertEqual(result["name"], self.settings_a)
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings_a, "pos_profile"), self.profile_a)
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings_b, "owner"), owner_b)
		self.assertNotEqual(frappe.db.get_value("POS Settings", self.settings_a, "owner"), "x@example.com")

	def test_cashier_writes_only_own_profile_settings(self):
		from frappe.client import set_value

		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			set_value("POS Settings", self.settings_b, "hide_expected_amount", 1)
		self.assertFalse(frappe.has_permission("POS Settings", "write", doc=self.settings_b))
		self.assertTrue(frappe.has_permission("POS Settings", "read", doc=self.settings_b))
		set_value("POS Settings", self.settings_a, "hide_expected_amount", 1)
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings_a, "hide_expected_amount"), 1)
		frappe.set_user(MANAGER)
		self.assertTrue(frappe.has_permission("POS Settings", "write", doc=self.settings_b))

	def test_can_manage_verification_admin_and_no_level_1(self):
		import copy

		self.assertTrue(otp.can_manage_verification("Administrator"))
		meta = copy.copy(frappe.get_meta("POS Settings"))
		meta.permissions = [p for p in meta.permissions if int(p.permlevel or 0) == 0]
		with patch.object(otp.frappe, "get_meta", return_value=meta):
			self.assertTrue(otp.can_manage_verification("Administrator"))
			self.assertFalse(otp.can_manage_verification(MANAGER))
		self.assertTrue(otp.can_manage_verification(MANAGER))

	# ------------------------------------------------------------------
	# Fix round 2
	# ------------------------------------------------------------------

	def test_set_value_cannot_move_other_row_to_own_profile(self):
		from frappe.client import set_value

		frappe.db.savepoint("pnxt8e_move")
		self.addCleanup(frappe.db.rollback, save_point="pnxt8e_move")
		# Profile A has no row, so the unique pos_profile constraint would not stop the move.
		frappe.db.delete("POS Settings", {"name": self.settings_a})
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			set_value(
				"POS Settings", self.settings_b, {"pos_profile": self.profile_a, "hide_expected_amount": 1}
			)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("POS Settings", self.settings_b, "pos_profile"), self.profile_b)

	def test_profile_check_db_error_is_unavailable_not_5xx(self):
		calls = []
		with (
			patch("frappe.utils.sentry.capture_exception", lambda message=None: calls.append(sys.exc_info())),
			patch.object(ev, "validate_pos_profile_access", side_effect=frappe.QueryTimeoutError("t " + OTP)),
		):
			sent = ev.send_email_otp("ANY-CUSTOMER", pos_profile=self.profile_a)
			verified = ev.verify_email_otp("ANY-CUSTOMER", OTP, pos_profile=self.profile_a)
		self.assertEqual((sent["code"], verified["code"]), ("unavailable", "unavailable"))
		self.assertNotIn(OTP, json.dumps([sent, verified]))
		self.assertEqual(calls, [])
		# A refused profile is still a 4xx PermissionError, not "unavailable".
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			ev.verify_email_otp("ANY-CUSTOMER", OTP, pos_profile=self.profile_b)

	def test_unknown_or_non_pos_doctype_refused(self):
		frappe.set_user(CASHIER)
		for doctype in ("No Such DocType 8E", "User", "POS Settings"):
			with self.subTest(doctype=doctype):
				payload = self._payload(self.profile_a)
				payload.update({"doctype": doctype, "name": "Administrator"})
				with self.assertRaises(frappe.PermissionError):
					update_invoice(json.dumps(payload))
				with self.assertRaises(frappe.PermissionError):
					submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))

	def test_missing_and_foreign_names_look_the_same(self):
		foreign = update_invoice(json.dumps(self._payload(self.profile_b)))["name"]  # Administrator
		frappe.set_user(CASHIER)
		messages = []
		for name in (foreign, "ACC-SINV-NO-SUCH-8E"):
			payload = self._payload(self.profile_a)
			payload["name"] = name
			with self.assertRaises(frappe.PermissionError) as ctx:
				update_invoice(json.dumps(payload))
			messages.append(str(ctx.exception))
		self.assertEqual(messages[0], messages[1])
