# Copyright (c) 2020, Youssef Restom and Contributors
# See license.txt

"""Guards Opening Shift balances against payment methods not flagged
`allow_in_opening` on the POS Profile (e.g. non-cash methods like bank
transfer, which finance reconciles separately): both the dialog-data API
filter (`get_opening_dialog_data`) and the `POS Opening Shift.validate()`
server-side re-check are covered here."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime, nowdate, nowtime

from pos_next.api.shifts import get_opening_dialog_data

CASH_MODE = "_PNXT_TEST_CASH"
BANK_MODE = "_PNXT_TEST_BANK_TRANSFER"
PROFILE_NAME = "_PNXT_TEST_OPENING_SHIFT_PROFILE"


def _resolve_company():
	"""Pick the test Company. Prefer ERPNext test fixture, else the default."""
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"
	default = frappe.defaults.get_global_default("company")
	if default:
		return default
	return frappe.db.get_value("Company", {"name": ["!=", ""]}, "name")


def _resolve_warehouse(company):
	if company == "_Test Company" and frappe.db.exists("Warehouse", "_Test Warehouse - _TC"):
		return "_Test Warehouse - _TC"
	wh = frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
		order_by="creation asc",
	)
	if not wh:
		frappe.throw(f"No warehouse for company {company}.")
	return wh


def _resolve_cost_center(company):
	return frappe.db.get_value(
		"Cost Center",
		{"company": company, "is_group": 0, "disabled": 0},
		"name",
		order_by="creation asc",
	)


def _ensure_mode_of_payment(name, mop_type, company):
	"""Create the Mode of Payment (if missing) with an account wired for `company`.

	POS Profile.validate_payment_methods() (ERPNext core) requires every
	payment method to have a default account configured for the company.
	"""
	if not frappe.db.exists("Mode of Payment", name):
		frappe.get_doc(
			{"doctype": "Mode of Payment", "mode_of_payment": name, "type": mop_type, "enabled": 1}
		).insert(ignore_permissions=True)

	mop_doc = frappe.get_doc("Mode of Payment", name)
	if not any(row.company == company for row in mop_doc.accounts):
		account = frappe.db.get_value(
			"Account",
			{"company": company, "is_group": 0},
			"name",
			order_by="creation asc",
		)
		mop_doc.append("accounts", {"company": company, "default_account": account})
		mop_doc.save(ignore_permissions=True)
	return name


class TestPOSOpeningShift(FrappeTestCase):
	def setUp(self):
		self.company = _resolve_company()
		self.warehouse = _resolve_warehouse(self.company)
		self.user = "Administrator"

		_ensure_mode_of_payment(CASH_MODE, "Cash", self.company)
		_ensure_mode_of_payment(BANK_MODE, "Bank", self.company)

		if frappe.db.exists("POS Profile", PROFILE_NAME):
			frappe.delete_doc("POS Profile", PROFILE_NAME, force=True, ignore_permissions=True)

		profile = frappe.get_doc(
			{
				"doctype": "POS Profile",
				"name": PROFILE_NAME,
				"company": self.company,
				"warehouse": self.warehouse,
				"currency": frappe.get_cached_value("Company", self.company, "default_currency"),
				"write_off_account": frappe.get_cached_value("Company", self.company, "write_off_account"),
				"write_off_cost_center": _resolve_cost_center(self.company),
				"disabled": 0,
			}
		)
		profile.append(
			"payments", {"mode_of_payment": CASH_MODE, "default": 1, "allow_in_opening": 1}
		)
		profile.append(
			"payments", {"mode_of_payment": BANK_MODE, "default": 0, "allow_in_opening": 0}
		)
		profile.append("applicable_for_users", {"user": self.user, "default": 1})
		profile.insert(ignore_permissions=True)
		self.pos_profile = profile.name

	def tearDown(self):
		frappe.db.rollback()

	def _make_opening_shift(self, mode_of_payment):
		return frappe.get_doc(
			{
				"doctype": "POS Opening Shift",
				"period_start_date": get_datetime(),
				"posting_date": nowdate(),
				"posting_time": nowtime(),
				"user": self.user,
				"pos_profile": self.pos_profile,
				"company": self.company,
				"balance_details": [{"mode_of_payment": mode_of_payment, "amount": 100}],
			}
		)

	def test_rejects_balance_for_payment_method_not_allowed_in_opening(self):
		doc = self._make_opening_shift(BANK_MODE)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_allows_balance_for_payment_method_allowed_in_opening(self):
		doc = self._make_opening_shift(CASH_MODE)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.balance_details[0].mode_of_payment, CASH_MODE)

	def test_dialog_data_excludes_payment_method_not_allowed_in_opening(self):
		frappe.set_user(self.user)
		try:
			data = get_opening_dialog_data()
		finally:
			frappe.set_user("Administrator")

		modes = {
			row["mode_of_payment"]
			for row in data["payments_method"]
			if row["parent"] == self.pos_profile
		}
		self.assertIn(CASH_MODE, modes)
		self.assertNotIn(BANK_MODE, modes)
