# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.pin — hashed storage, format rules, lockout, and the
POS Authorization Settings that drive pin_length/max_failures/lockout/strict-mode.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import pin as pin_store
from pos_next.authorization.tests.helpers import CASHIER, GOOD_PIN, OTHER_PIN, OUTSIDER, make_user

SETTINGS_DOCTYPE = "POS Authorization Settings"


def _apply_settings(**fields):
	"""Update POS Authorization Settings the same way a System Manager would (a real
	save, not raw db.set_value), so get_cached_doc() is correctly invalidated rather
	than left holding a stale value.
	"""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	settings.update(fields)
	settings.save(ignore_permissions=True)


class TestPin(FrappeTestCase):
	"""Hashed storage, format rules and lockout.

	Pins pin_length/enforce_strict_pin to what these tests assume for the whole class.
	POS Authorization Settings is a real, live-editable singleton (see TestPinSettings
	below) — on an actual site, someone may well have turned strict mode off or changed
	the PIN length, and without pinning these here, that real configuration would make
	these tests fail for a reason that has nothing to do with a code regression.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(OUTSIDER)
		cls._original_settings = frappe.get_single(SETTINGS_DOCTYPE).as_dict()
		_apply_settings(pin_length=4, enforce_strict_pin=1)

	@classmethod
	def tearDownClass(cls):
		_apply_settings(
			pin_length=cls._original_settings.get("pin_length"),
			enforce_strict_pin=cls._original_settings.get("enforce_strict_pin"),
		)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		pin_store.set_pin(OUTSIDER, GOOD_PIN)
		pin_store.clear_failures(OUTSIDER)

	def test_pin_round_trips(self):
		self.assertTrue(pin_store.has_pin(OUTSIDER))
		self.assertTrue(pin_store.verify(OUTSIDER, GOOD_PIN))
		self.assertFalse(pin_store.verify(OUTSIDER, OTHER_PIN))

	def test_pin_is_stored_hashed_not_encrypted(self):
		"""encrypted=0 is Frappe's hashed lane; a Password DocField would be encrypted=1."""
		row = frappe.db.sql(
			"""select password, encrypted from `__Auth`
			   where doctype='User' and name=%s and fieldname=%s""",
			(OUTSIDER, pin_store.PIN_FIELD),
			as_dict=True,
		)
		self.assertTrue(row)
		self.assertEqual(row[0]["encrypted"], 0)
		self.assertNotEqual(row[0]["password"], GOOD_PIN)
		self.assertNotIn(GOOD_PIN, row[0]["password"])

	def test_pin_never_raises_authentication_error(self):
		"""A wrong PIN must not reach Frappe's handler, which would clear the cashier's cookies."""
		try:
			self.assertFalse(pin_store.verify(OUTSIDER, "0000"))
		except frappe.AuthenticationError:
			self.fail("verify() leaked AuthenticationError")

	def test_format_rules(self):
		for bad in ["123", "12345", "abcd", "12a4", ""]:
			with self.assertRaises(frappe.ValidationError):
				pin_store.validate_format(bad)

	def test_trivial_pins_are_refused(self):
		for bad in ["0000", "1111", "1234", "4321", "9999"]:
			with self.assertRaises(frappe.ValidationError):
				pin_store.validate_format(bad)

	def test_lockout_after_consecutive_failures(self):
		self.assertFalse(pin_store.is_locked_out(OUTSIDER))
		locked = False
		for _ in range(pin_store.max_failures()):
			locked = pin_store.register_failure(OUTSIDER)
		self.assertTrue(locked)
		self.assertTrue(pin_store.is_locked_out(OUTSIDER))

	def test_setting_a_pin_clears_the_lockout(self):
		for _ in range(pin_store.max_failures()):
			pin_store.register_failure(OUTSIDER)
		self.assertTrue(pin_store.is_locked_out(OUTSIDER))
		pin_store.set_pin(OUTSIDER, OTHER_PIN)
		self.assertFalse(pin_store.is_locked_out(OUTSIDER))

	def test_clear_pin_removes_approval_ability(self):
		pin_store.clear_pin(OUTSIDER)
		self.assertFalse(pin_store.has_pin(OUTSIDER))
		self.assertFalse(pin_store.verify(OUTSIDER, GOOD_PIN))

	def test_users_with_pin_filters_in_one_query(self):
		pin_store.set_pin(OUTSIDER, GOOD_PIN)
		pin_store.clear_pin(CASHIER)
		self.assertEqual(pin_store.users_with_pin([OUTSIDER, CASHIER]), {OUTSIDER})


class TestPinSettings(FrappeTestCase):
	"""pin_length, max_failures, lockout and strict-mode all come from POS Authorization
	Settings, not hardcoded constants — these prove settings actually drive behaviour.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(OUTSIDER)

	def setUp(self):
		frappe.set_user("Administrator")
		pin_store.clear_failures(OUTSIDER)
		# get_cached_doc() lives in Redis, outside this test framework's DB-transaction
		# rollback — a test that changes the singleton and doesn't put it back would
		# leak its values into whatever runs next, test or real site alike. Snapshot
		# here, restore via the same save() path (not raw db.set_value) in tearDown so
		# the cache is correctly invalidated, not just the row.
		self._original = frappe.get_single(SETTINGS_DOCTYPE).as_dict()

	def tearDown(self):
		_apply_settings(
			pin_length=self._original.get("pin_length"),
			max_failures=self._original.get("max_failures"),
			lockout_minutes=self._original.get("lockout_minutes"),
			enforce_strict_pin=self._original.get("enforce_strict_pin"),
		)

	def test_pin_length_is_enforced_from_settings(self):
		_apply_settings(pin_length=6)
		with self.assertRaises(frappe.ValidationError):
			pin_store.validate_format(GOOD_PIN)  # 4 digits — now too short
		pin_store.validate_format("246813")  # 6 digits, not trivial — accepted

	def test_max_failures_is_read_from_settings(self):
		_apply_settings(max_failures=2)
		self.assertFalse(pin_store.register_failure(OUTSIDER))
		self.assertTrue(pin_store.register_failure(OUTSIDER))
		self.assertTrue(pin_store.is_locked_out(OUTSIDER))

	def test_lockout_seconds_is_derived_from_minutes(self):
		_apply_settings(lockout_minutes=1)
		self.assertEqual(pin_store.lockout_seconds(), 60)

	def test_strict_mode_off_allows_a_trivial_pin(self):
		_apply_settings(enforce_strict_pin=0)
		pin_store.validate_format("1234")  # would normally be refused

	def test_strict_mode_on_refuses_trivial_pins_of_any_length(self):
		_apply_settings(pin_length=6, enforce_strict_pin=1)
		for bad in ["000000", "123456", "654321", "456789", "987654"]:
			with self.assertRaises(frappe.ValidationError):
				pin_store.validate_format(bad)

	def test_trivial_detection_is_algorithmic_not_a_fixed_list(self):
		"""Wrap-around runs (9->0, 0->9) and non-4-length pins must both be caught —
		proof this isn't just the old hardcoded list with the numbers changed.
		"""
		self.assertTrue(pin_store._is_trivial("7890"))
		self.assertTrue(pin_store._is_trivial("0987"))
		self.assertTrue(pin_store._is_trivial("56789"))
		self.assertFalse(pin_store._is_trivial("2946"))
