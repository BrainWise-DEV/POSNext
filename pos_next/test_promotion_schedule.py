# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for `pos_next.promotions.schedule`."""

from datetime import datetime, time
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

import pos_next  # noqa: F401 — ensure app hooks load.
from pos_next.promotions.schedule import (
	get_period,
	has_time_bound,
	is_active_at,
	normalize_schedule_fields,
	parse_time,
	resolve_moment,
	to_client_payload,
)

# 2026-08-03 is the reference "today"; 08-04 is "tomorrow".
TODAY = "2026-08-03"
TOMORROW = "2026-08-04"


def _rule(**fields):
	"""A plain dict standing in for a Pricing Rule — the helpers only use .get()."""
	return frappe._dict(fields)


def _at(day, hour, minute=0, second=0):
	return datetime(2026, 8, day, hour, minute, second)


class TestSchedulePeriod(FrappeTestCase):
	"""The times bound one continuous span, they do not repeat every day."""

	def test_valid_until_tomorrow_stays_live_through_tonight(self):
		"""The case that exposed the daily-window mistake.

		Ends tomorrow at 01:08:46, so 02:08 *today* is still inside the period —
		a daily window would have called this expired.
		"""
		rule = _rule(
			valid_from=TODAY,
			valid_upto=TOMORROW,
			pos_active_from_time="00:00:00",
			pos_active_to_time="01:08:46",
		)
		self.assertTrue(is_active_at(rule, _at(3, 2, 8, 46)))
		self.assertTrue(is_active_at(rule, _at(3, 14)))
		self.assertTrue(is_active_at(rule, _at(3, 23, 59)))
		self.assertTrue(is_active_at(rule, _at(4, 1, 8, 46)))
		self.assertFalse(is_active_at(rule, _at(4, 1, 8, 47)))
		self.assertFalse(is_active_at(rule, _at(4, 9)))

	def test_start_time_narrows_only_the_first_day(self):
		rule = _rule(
			valid_from=TODAY,
			valid_upto=TOMORROW,
			pos_active_from_time="18:00:00",
			pos_active_to_time="00:00:00",
		)
		self.assertFalse(is_active_at(rule, _at(3, 17, 59)))
		self.assertTrue(is_active_at(rule, _at(3, 18)))
		# The next day is not narrowed by the start time.
		self.assertTrue(is_active_at(rule, _at(4, 9)))
		self.assertTrue(is_active_at(rule, _at(4, 23, 59, 59)))
		self.assertFalse(is_active_at(rule, _at(5, 0)))

	def test_midnight_end_time_keeps_the_last_day_whole(self):
		"""valid_upto is inclusive in ERPNext; 00:00:00 must not truncate it."""
		rule = _rule(valid_from=TODAY, valid_upto=TODAY, pos_active_to_time="00:00:00")
		self.assertTrue(is_active_at(rule, _at(3, 0)))
		self.assertTrue(is_active_at(rule, _at(3, 23, 59, 59)))
		self.assertFalse(is_active_at(rule, _at(4, 0)))

	def test_open_ended_period(self):
		self.assertTrue(is_active_at(_rule(), _at(3, 3)))
		self.assertTrue(is_active_at(_rule(valid_from=TODAY), _at(9, 3)))
		self.assertFalse(is_active_at(_rule(valid_from=TOMORROW), _at(3, 3)))
		self.assertTrue(is_active_at(_rule(valid_upto=TOMORROW), _at(1, 3)))

	def test_get_period_endpoints(self):
		start, end = get_period(
			_rule(
				valid_from=TODAY,
				valid_upto=TOMORROW,
				pos_active_from_time="09:30:00",
				pos_active_to_time="01:08:46",
			)
		)
		self.assertEqual(start, datetime(2026, 8, 3, 9, 30))
		self.assertEqual(end, datetime(2026, 8, 4, 1, 8, 46))

	def test_has_time_bound(self):
		self.assertFalse(has_time_bound(_rule(valid_from=TODAY, valid_upto=TOMORROW)))
		self.assertFalse(
			has_time_bound(
				_rule(valid_from=TODAY, pos_active_from_time="00:00:00", valid_upto=TOMORROW)
			)
		)
		self.assertTrue(
			has_time_bound(_rule(valid_from=TODAY, pos_active_from_time="09:00:00"))
		)
		# A time without its date narrows nothing.
		self.assertFalse(has_time_bound(_rule(pos_active_to_time="09:00:00")))

	def test_client_payload(self):
		rule = _rule(
			valid_from=TODAY,
			valid_upto=TOMORROW,
			pos_active_from_time="00:00:00",
			pos_active_to_time="01:08:46",
		)
		self.assertEqual(
			to_client_payload(rule),
			{"start": "2026-08-03 00:00:00", "end": "2026-08-04 01:08:46"},
		)
		self.assertIsNone(to_client_payload(_rule(valid_from=TODAY, valid_upto=TOMORROW)))

	def test_parse_time_tolerates_every_shape(self):
		from datetime import timedelta

		self.assertEqual(parse_time("18:30:00"), time(18, 30))
		self.assertEqual(parse_time(time(18, 30)), time(18, 30))
		self.assertEqual(parse_time(timedelta(hours=18, minutes=30)), time(18, 30))
		self.assertIsNone(parse_time(None))
		self.assertIsNone(parse_time(""))

	def test_resolve_moment_prefers_the_documents_own_stamp(self):
		"""An offline sale is judged when it happened, not when it synced."""
		self.assertEqual(
			resolve_moment({"posting_date": TODAY, "posting_time": "11:30:00"}),
			datetime(2026, 8, 3, 11, 30),
		)
		self.assertIsInstance(resolve_moment({"posting_date": TODAY}), datetime)
		self.assertIsInstance(resolve_moment(None), datetime)


class TestScheduleNormalizer(FrappeTestCase):
	"""Frappe fills every Time field on a new document with nowtime()."""

	def _doc(self, **fields):
		doc = frappe._dict(doctype="Pricing Rule", **fields)
		doc.set = lambda k, v: doc.__setitem__(k, v)
		return doc

	def test_resets_the_time_autofill(self):
		doc = self._doc(
			__islocal=1,
			valid_from=TODAY,
			valid_upto=TOMORROW,
			pos_active_from_time="17:55:49.316312",
			pos_active_to_time="17:55:49.316355",
		)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_from_time"], "00:00:00")
		self.assertEqual(doc["pos_active_to_time"], "00:00:00")
		self.assertFalse(has_time_bound(doc))

	def test_keeps_a_real_configuration(self):
		doc = self._doc(
			__islocal=1,
			valid_from=TODAY,
			valid_upto=TOMORROW,
			pos_active_from_time="00:00:00",
			pos_active_to_time="01:08:46",
		)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_to_time"], "01:08:46")
		self.assertTrue(has_time_bound(doc))

	def test_clears_a_time_whose_date_is_blank(self):
		"""The field is hidden without its date, so it must not stay in force."""
		doc = self._doc(
			valid_from=None,
			valid_upto=TOMORROW,
			pos_active_from_time="11:00:00",
			pos_active_to_time="01:08:46",
		)
		normalize_schedule_fields(doc)
		self.assertEqual(doc["pos_active_from_time"], "00:00:00")
		self.assertEqual(doc["pos_active_to_time"], "01:08:46")


def run_all():
	"""Run the schedule tests without `bench run-tests` wiping dev data."""
	loader = unittest.TestLoader()
	suite = unittest.TestSuite(
		loader.loadTestsFromTestCase(case)
		for case in (TestSchedulePeriod, TestScheduleNormalizer)
	)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return {
		"tests_run": result.testsRun,
		"failures": [str(f[0]) for f in result.failures],
		"errors": [str(e[0]) for e in result.errors],
		"was_successful": result.wasSuccessful(),
	}
