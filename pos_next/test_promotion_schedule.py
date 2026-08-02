# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for `pos_next.promotions.schedule`.

The load-bearing one is `test_sql_and_python_agree`: the window exists in two
forms — a Python check and a SQL fragment ERPNext's engine runs — and they must
answer identically or a promotion applies in the cart but not on the invoice
(or the reverse). Everything else here is a semantic pin.
"""

from datetime import datetime, time
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

import pos_next  # noqa: F401 — ensure app hooks load.
from pos_next.promotions.schedule import (
	build_sql_predicate,
	get_window,
	has_schedule,
	is_active_at,
	normalize_schedule_fields,
	parse_time,
	time_matches,
	to_client_payload,
)


def _rule(**schedule):
	"""A plain dict standing in for a Pricing Rule — the helpers only use .get()."""
	return frappe._dict(schedule)


def _at(hour, minute=0):
	return datetime(2026, 8, 3, hour, minute)


class TestScheduleSemantics(FrappeTestCase):
	def test_no_window_is_always_active(self):
		rule = _rule()
		self.assertFalse(has_schedule(rule))
		self.assertIsNone(to_client_payload(rule))
		for hour in (0, 9, 23):
			self.assertTrue(is_active_at(rule, _at(hour)))

	def test_simple_window(self):
		rule = _rule(pos_active_from_time="18:00:00", pos_active_to_time="20:00:00")
		self.assertFalse(is_active_at(rule, _at(17, 59)))
		self.assertTrue(is_active_at(rule, _at(18)))
		self.assertTrue(is_active_at(rule, _at(19)))
		self.assertTrue(is_active_at(rule, _at(20)))
		self.assertFalse(is_active_at(rule, _at(20, 1)))

	def test_window_wrapping_past_midnight(self):
		"""22:00 -> 02:00 is a union, not a range — the classic off-by-a-day bug."""
		rule = _rule(pos_active_from_time="22:00:00", pos_active_to_time="02:00:00")
		self.assertTrue(is_active_at(rule, _at(22)))
		self.assertTrue(is_active_at(rule, _at(23, 59)))
		self.assertTrue(is_active_at(rule, _at(0, 30)))
		self.assertTrue(is_active_at(rule, _at(2)))
		self.assertFalse(is_active_at(rule, _at(3)))
		self.assertFalse(is_active_at(rule, _at(12)))

	def test_equal_times_mean_all_day(self):
		"""Never-active would silently kill the promotion; validation catches the typo."""
		rule = _rule(pos_active_from_time="18:00:00", pos_active_to_time="18:00:00")
		for hour in (0, 6, 18, 23):
			self.assertTrue(is_active_at(rule, _at(hour)))

	def test_a_half_configured_window_does_not_restrict(self):
		self.assertTrue(is_active_at(_rule(pos_active_from_time="18:00:00"), _at(3)))
		self.assertTrue(is_active_at(_rule(pos_active_to_time="20:00:00"), _at(3)))

	def test_parse_time_tolerates_every_shape(self):
		from datetime import timedelta

		self.assertEqual(parse_time("18:30:00"), time(18, 30))
		self.assertEqual(parse_time(time(18, 30)), time(18, 30))
		self.assertEqual(parse_time(timedelta(hours=18, minutes=30)), time(18, 30))
		self.assertIsNone(parse_time(None))
		self.assertIsNone(parse_time(""))

	def test_client_payload_round_trip(self):
		rule = _rule(pos_active_from_time="18:00:00", pos_active_to_time="02:00:00")
		payload = to_client_payload(rule)
		self.assertEqual(payload["from_time"], "18:00:00")
		self.assertEqual(payload["to_time"], "02:00:00")

		start, end = get_window(rule)
		self.assertTrue(time_matches(start, end, time(23, 0)))
		self.assertTrue(time_matches(start, end, time(1, 0)))
		self.assertFalse(time_matches(start, end, time(12, 0)))


class TestScheduleSqlMatchesPython(FrappeTestCase):
	"""The SQL and Python forms must never disagree."""

	WINDOWS = [
		("_PNXT_SCHED_None", {}),
		(
			"_PNXT_SCHED_Day",
			{"pos_active_from_time": "09:00:00", "pos_active_to_time": "17:00:00"},
		),
		(
			"_PNXT_SCHED_Evening",
			{"pos_active_from_time": "18:00:00", "pos_active_to_time": "20:00:00"},
		),
		(
			"_PNXT_SCHED_Overnight",
			{"pos_active_from_time": "22:00:00", "pos_active_to_time": "02:00:00"},
		),
		(
			"_PNXT_SCHED_AllDayEqual",
			{"pos_active_from_time": "12:00:00", "pos_active_to_time": "12:00:00"},
		),
		(
			"_PNXT_SCHED_EarlyMorning",
			{"pos_active_from_time": "00:00:00", "pos_active_to_time": "06:00:00"},
		),
	]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
			"Company", {}, "name"
		)
		cls.names = []
		for title, schedule in cls.WINDOWS:
			existing = frappe.db.get_value("Pricing Rule", {"title": title}, "name")
			if existing:
				frappe.delete_doc("Pricing Rule", existing, force=True, ignore_permissions=True)
			doc = frappe.get_doc(
				{
					"doctype": "Pricing Rule",
					"title": title,
					# Transaction scope needs no child rows — this suite is about
					# *when* a rule runs, not what it targets.
					"apply_on": "Transaction",
					"price_or_product_discount": "Price",
					"rate_or_discount": "Discount Percentage",
					"discount_percentage": 5,
					"selling": 1,
					"company": company,
					"currency": frappe.get_cached_value("Company", company, "default_currency"),
					**schedule,
				}
			).insert(ignore_permissions=True)
			cls.names.append(doc.name)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		for name in cls.names:
			try:
				frappe.delete_doc("Pricing Rule", name, force=True, ignore_permissions=True)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDownClass()

	def _sql_active(self, when):
		values = {"names": tuple(self.names)}
		predicate = build_sql_predicate("`tabPricing Rule`", values, when=when)
		rows = frappe.db.sql(
			f"select name from `tabPricing Rule` where name in %(names)s {predicate}",
			values,
			pluck=True,
		)
		return set(rows)

	def test_sql_and_python_agree(self):
		"""Across every window x a full sweep of the day, half-hour by half-hour."""
		docs = {name: frappe.get_doc("Pricing Rule", name) for name in self.names}
		checked = 0

		for hour in range(24):
			for minute in (0, 30):
				when = _at(hour, minute)
				sql_active = self._sql_active(when)
				python_active = {name for name, doc in docs.items() if is_active_at(doc, when)}
				self.assertEqual(
					python_active,
					sql_active,
					f"SQL and Python disagree at {when:%H:%M}: "
					f"python-only={sorted(python_active - sql_active)} "
					f"sql-only={sorted(sql_active - python_active)}",
				)
				checked += 1

		self.assertEqual(checked, 48, "sweep did not cover the full day")


class TestScheduleDefaults(FrappeTestCase):
	"""Midnight-to-midnight is the unset state, and the normalizer keeps it that way.

	Frappe's `create_new.py` assigns `nowtime()` to every Time field on a new
	document — unconditionally, ignoring the field default. Left alone a new rule
	would carry a sliver of a window and silently never apply.
	"""

	def test_midnight_pair_is_unrestricted(self):
		rule = _rule(pos_active_from_time="00:00:00", pos_active_to_time="00:00:00")
		self.assertFalse(has_schedule(rule))
		self.assertIsNone(to_client_payload(rule))
		for hour in (0, 9, 17, 23):
			self.assertTrue(is_active_at(rule, _at(hour)))

	def test_equal_times_are_unrestricted(self):
		rule = _rule(pos_active_from_time="13:00:00", pos_active_to_time="13:00:00")
		self.assertFalse(has_schedule(rule))
		self.assertTrue(is_active_at(rule, _at(3)))

	def test_normalizer_resets_the_time_autofill(self):
		doc = frappe._dict(
			doctype="Pricing Rule",
			__islocal=1,
			valid_from="2026-08-01",
			valid_upto="2026-08-31",
			pos_active_from_time="17:55:49.316312",
			pos_active_to_time="17:55:49.316355",
		)
		doc.set = lambda k, v: doc.__setitem__(k, v)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_from_time"], "00:00:00")
		self.assertEqual(doc["pos_active_to_time"], "00:00:00")
		self.assertFalse(has_schedule(doc))

	def test_normalizer_keeps_a_real_window(self):
		doc = frappe._dict(
			doctype="Pricing Rule",
			__islocal=1,
			valid_from="2026-08-01",
			valid_upto="2026-08-31",
			pos_active_from_time="11:00:00",
			pos_active_to_time="12:05:38",
		)
		doc.set = lambda k, v: doc.__setitem__(k, v)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_from_time"], "11:00:00")
		self.assertTrue(has_schedule(doc))

	def test_normalizer_clears_a_time_whose_date_is_blank(self):
		"""The field is hidden without its date, so it must not stay enforced."""
		doc = frappe._dict(
			doctype="Pricing Rule",
			valid_from=None,
			valid_upto="2026-08-31",
			pos_active_from_time="11:00:00",
			pos_active_to_time="12:05:38",
		)
		doc.set = lambda k, v: doc.__setitem__(k, v)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_from_time"], "00:00:00")
		self.assertEqual(doc["pos_active_to_time"], "12:05:38")


def run_all():
	"""Run the schedule tests without `bench run-tests` wiping dev data."""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite(
		loader.loadTestsFromTestCase(case)
		for case in (TestScheduleSemantics, TestScheduleDefaults, TestScheduleSqlMatchesPython)
	)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return {
		"tests_run": result.testsRun,
		"failures": [str(f[0]) for f in result.failures],
		"errors": [str(e[0]) for e in result.errors],
		"was_successful": result.wasSuccessful(),
	}
