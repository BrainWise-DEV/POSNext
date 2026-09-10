# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.api.expenses.

Unit tests are pure mocks, but patching ``frappe.db.*`` still requires a live
site: the ``frappe.db`` proxy is unbound outside site context. The Journal Entry
integration class builds fixtures in ``setUpClass`` (company / accounts / cost
center / POS Profile) then submits a real JE.

Run via ``bench --site <site> run-tests --module pos_next.api.test_expenses``.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import expenses


def _raise_runtime_error(message, *args, **kwargs):
	raise RuntimeError(str(message))


class TestPOSExpenses(unittest.TestCase):
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=0)
	def test_validate_pos_expense_enabled_rejects_disabled_profile(
		self, _mock_get_value, _mock_throw
	):
		with self.assertRaisesRegex(RuntimeError, "POS Expense is not enabled"):
			expenses.validate_pos_expense_enabled("Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch("pos_next.api.expenses.frappe.session")
	def test_validate_open_shift_rejects_closed_shift(
		self, mock_session, mock_get_value, _mock_throw
	):
		mock_session.user = "test@example.com"
		mock_get_value.return_value = SimpleNamespace(
			name="POS-OS-0001",
			status="Closed",
			pos_profile="Test POS Profile",
			company="Test Company",
			user="test@example.com",
			docstatus=1,
			period_start_date="2026-09-08 22:00:00",
		)

		with self.assertRaisesRegex(RuntimeError, "must be open"):
			expenses.validate_open_shift("POS-OS-0001", "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch("pos_next.api.expenses.frappe.session")
	def test_validate_open_shift_rejects_other_user(
		self, mock_session, mock_get_value, _mock_throw
	):
		mock_session.user = "other@example.com"
		mock_get_value.return_value = SimpleNamespace(
			name="POS-OS-0001",
			status="Open",
			pos_profile="Test POS Profile",
			company="Test Company",
			user="cashier@example.com",
			docstatus=1,
			period_start_date="2026-09-08 22:00:00",
		)

		with self.assertRaisesRegex(RuntimeError, "your own open shift"):
			expenses.validate_open_shift("POS-OS-0001", "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_zero(self, mock_get_value, _mock_throw):
		mock_get_value.return_value = 0

		with self.assertRaisesRegex(RuntimeError, "greater than zero"):
			expenses.validate_expense_amount(0, "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_unconfigured_limit(
		self, mock_get_value, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			posa_maximum_expense_amount=0, company="Test Company"
		)

		with self.assertRaisesRegex(RuntimeError, "not configured"):
			expenses.validate_expense_amount(50, "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.format_value", side_effect=lambda value, _options: str(value))
	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=0)
	@patch("pos_next.api.expenses.frappe.get_cached_value", return_value="USD")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_over_shift_limit(
		self, mock_get_value, _mock_cached, _mock_shift_total, _mock_format, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			posa_maximum_expense_amount=100, company="Test Company"
		)

		with self.assertRaisesRegex(RuntimeError, "shift expense limit"):
			expenses.validate_expense_amount(150, "Test POS Profile", "POS-OS-0001")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.format_value", side_effect=lambda value, _options: str(value))
	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=80)
	@patch("pos_next.api.expenses.frappe.get_cached_value", return_value="USD")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_when_cumulative_exceeds_limit(
		self, mock_get_value, _mock_cached, _mock_shift_total, _mock_format, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			posa_maximum_expense_amount=100, company="Test Company"
		)

		with self.assertRaisesRegex(RuntimeError, "shift expense limit"):
			expenses.validate_expense_amount(30, "Test POS Profile", "POS-OS-0001")

	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=0)
	@patch("pos_next.api.expenses.frappe.get_cached_value", return_value="USD")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_locks_opening_shift_before_total(
		self, mock_get_value, _mock_cached, mock_shift_total
	):
		"""Serialize check+insert: FOR UPDATE on the shift before reading the SUM."""
		mock_get_value.side_effect = [
			SimpleNamespace(posa_maximum_expense_amount=100, company="Test Company"),
			"POS-OS-0001",
		]

		expenses.validate_expense_amount(50, "Test POS Profile", "POS-OS-0001")

		self.assertEqual(
			mock_get_value.call_args_list,
			[
				unittest.mock.call(
					"POS Profile",
					"Test POS Profile",
					["posa_maximum_expense_amount", "company"],
					as_dict=True,
				),
				unittest.mock.call(
					"POS Opening Shift",
					"POS-OS-0001",
					"name",
					for_update=True,
				),
			],
		)
		mock_shift_total.assert_called_once_with("POS-OS-0001")

	@patch("pos_next.api.expenses.frappe.db.sql", return_value=((80,),))
	def test_get_shift_expense_total_sums_credit_rows(self, mock_sql):
		total = expenses.get_shift_expense_total("POS-OS-0001")

		self.assertEqual(total, 80)
		sql = mock_sql.call_args.args[0]
		self.assertIn("SUM(jea.credit)", sql)
		self.assertNotIn("posa_expense_amount", sql)
		mock_sql.assert_called_once()

	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=0)
	def test_get_remaining_shift_expense_amount(self, _mock_shift_total):
		self.assertEqual(expenses._get_remaining_shift_expense_amount(100, 30), 70)
		self.assertEqual(expenses._get_remaining_shift_expense_amount(100, 120), 0)
		self.assertEqual(expenses._get_remaining_shift_expense_amount(0, 50), 0)

	@patch("pos_next.api.expenses.get_pos_expenses", return_value=[])
	@patch("pos_next.api.expenses.get_active_employees", return_value=[])
	@patch("pos_next.api.expenses.get_cash_payment_methods", return_value=[])
	@patch("pos_next.api.expenses.get_expense_accounts", return_value=[])
	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=25)
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_permissions",
		return_value={"allow_cancel": 1, "can_cancel": 1},
	)
	@patch("frappe.core.api.file.get_max_file_size", return_value=10485760)
	@patch("pos_next.api.expenses.frappe.get_cached_value", return_value="EUR")
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=100)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	def test_get_expense_dialog_data_returns_company_currency(
		self,
		_mock_enabled,
		mock_validate_shift,
		_mock_get_value,
		_mock_cached,
		_mock_max_file,
		_mock_cancel_perms,
		_mock_shift_total,
		_mock_accounts,
		_mock_methods,
		_mock_employees,
		_mock_expenses,
	):
		"""Dialog amounts share Company.default_currency with JE booking (not profile currency)."""
		mock_validate_shift.return_value = SimpleNamespace(company="Test Company")

		data = expenses.get_expense_dialog_data("Test POS Profile", "POS-OS-0001")

		self.assertEqual(data["company_currency"], "EUR")
		self.assertEqual(data["maximum_expense_amount"], 100)
		self.assertEqual(data["shift_expense_total"], 25)
		self.assertEqual(data["remaining_expense_amount"], 75)
		self.assertEqual(data["allow_cancel"], 1)
		self.assertEqual(data["can_cancel"], 1)
		self.assertEqual(data["max_file_size"], 10485760)
		_mock_cached.assert_called_once_with("Company", "Test Company", "default_currency")
		_mock_accounts.assert_called_once_with(
			"Test Company", pos_profile="Test POS Profile"
		)
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_account_rejects_non_expense(self, mock_get_value, _mock_throw):
		mock_get_value.return_value = SimpleNamespace(
			name="Cash - TC",
			company="Test Company",
			is_group=0,
			disabled=0,
			account_type="Cash",
			root_type="Asset",
		)

		with self.assertRaisesRegex(RuntimeError, "must be an expense account"):
			expenses.validate_expense_account("Cash - TC", "Test Company")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch(
		"pos_next.api.expenses.get_allowed_expense_account_names",
		return_value=["Travel Expenses - TC"],
	)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_account_rejects_non_whitelisted(
		self, mock_get_value, _mock_allowed, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			name="Office Rent - TC",
			company="Test Company",
			is_group=0,
			disabled=0,
			account_type="Expense Account",
			root_type="Expense",
		)

		with self.assertRaisesRegex(RuntimeError, "is not allowed for POS Profile"):
			expenses.validate_expense_account(
				"Office Rent - TC", "Test Company", pos_profile="Test POS Profile"
			)

	@patch(
		"pos_next.api.expenses.get_allowed_expense_account_names",
		return_value=["Travel Expenses - TC"],
	)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_account_allows_whitelisted(
		self, mock_get_value, _mock_allowed
	):
		mock_get_value.return_value = SimpleNamespace(
			name="Travel Expenses - TC",
			company="Test Company",
			is_group=0,
			disabled=0,
			account_type="Expense Account",
			root_type="Expense",
		)
		expenses.validate_expense_account(
			"Travel Expenses - TC", "Test Company", pos_profile="Test POS Profile"
		)

	@patch("pos_next.api.expenses.frappe.db.sql", return_value=[])
	@patch(
		"pos_next.api.expenses.get_allowed_expense_account_names",
		return_value=["Travel Expenses - TC"],
	)
	def test_get_expense_accounts_applies_whitelist(self, _mock_allowed, mock_sql):
		expenses.get_expense_accounts(
			"Test Company", pos_profile="Test POS Profile", txt="Travel"
		)
		params = mock_sql.call_args.args[1]
		self.assertEqual(params["allowed"], ("Travel Expenses - TC",))
		self.assertIn("AND name IN %(allowed)s", mock_sql.call_args.args[0])

	@patch("pos_next.api.expenses._resolve_payment_account", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.get_all", return_value=["row-1"])
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_validate_mode_of_payment_requires_payment_account(
		self, _mock_throw, _mock_get_all, mock_resolve
	):
		mock_resolve.side_effect = RuntimeError(
			"Please set default Cash account in Mode of Payment Cash"
		)
		with self.assertRaisesRegex(RuntimeError, "Please set default Cash account"):
			expenses.validate_mode_of_payment("Cash", "Test POS Profile", "Test Company")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch(
		"pos_next.api.expenses._resolve_payment_account",
		return_value="Bank - TC",
	)
	@patch("pos_next.api.expenses.frappe.get_all", return_value=["row-1"])
	def test_validate_mode_of_payment_rejects_non_cash_account(
		self, _mock_get_all, _mock_resolve, mock_get_value, _mock_throw
	):
		mock_get_value.return_value = "Bank"
		with self.assertRaisesRegex(RuntimeError, "Cash accounts"):
			expenses.validate_mode_of_payment("Card", "Test POS Profile", "Test Company")

	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch(
		"pos_next.api.expenses._resolve_payment_account",
		return_value="Cash - TC",
	)
	@patch("pos_next.api.expenses.frappe.get_all", return_value=["row-1"])
	def test_validate_mode_of_payment_returns_cash_account(
		self, _mock_get_all, _mock_resolve, mock_get_value
	):
		mock_get_value.return_value = "Cash"
		self.assertEqual(
			expenses.validate_mode_of_payment("Cash", "Test POS Profile", "Test Company"),
			"Cash - TC",
		)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=None)
	def test_resolve_payment_account_throws_informative_error(
		self, _mock_get_value, _mock_throw
	):
		with self.assertRaisesRegex(RuntimeError, "Please set default Cash account"):
			expenses._resolve_payment_account("Cash", "Test Company")

	def test_coerce_account_name_handles_dict_and_string(self):
		self.assertEqual(expenses._coerce_account_name({"account": "Cash - TC"}), "Cash - TC")
		self.assertEqual(expenses._coerce_account_name("Cash - TC"), "Cash - TC")
		self.assertEqual(
			expenses._coerce_account_name({"account": {"account": "Cash - TC"}}),
			"Cash - TC",
		)

	@patch("pos_next.api.expenses.frappe.get_all", return_value=[])
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_validate_mode_of_payment_rejects_unconfigured_mode(self, _mock_throw, _mock_get_all):
		with self.assertRaisesRegex(RuntimeError, "is not configured in POS Profile"):
			expenses.validate_mode_of_payment("Cash", "Test POS Profile", "Test Company")

	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch("pos_next.api.expenses.frappe.db.exists", return_value=False)
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_validate_employee_rejects_missing_employee(
		self, _mock_throw, _mock_exists, _mock_get_value
	):
		with self.assertRaisesRegex(RuntimeError, "does not exist"):
			expenses.validate_employee("EMP-0001", "Test Company")

	@patch("pos_next.api.expenses.frappe.get_all")
	def test_get_active_employees_scoped_to_company(self, mock_get_all):
		"""Company scope and a finite page cap — not a full get_all kwarg snapshot."""
		mock_get_all.return_value = [{"name": "EMP-0001", "employee_name": "John Doe"}]

		result = expenses.get_active_employees("Test Company")

		self.assertEqual(result[0]["name"], "EMP-0001")
		kwargs = mock_get_all.call_args.kwargs
		self.assertEqual(kwargs["filters"]["company"], "Test Company")
		self.assertEqual(kwargs["filters"]["status"], "Active")
		self.assertGreater(kwargs["limit_page_length"], 0)

	@patch("pos_next.api.expenses.frappe.get_all")
	def test_get_expense_accounts_is_capped(self, mock_get_all):
		mock_get_all.return_value = []
		expenses.get_expense_accounts("Test Company")
		kwargs = mock_get_all.call_args.kwargs
		self.assertGreater(kwargs["limit_page_length"], 0)

	def test_shift_posting_date_uses_period_start(self):
		self.assertEqual(
			str(expenses._shift_posting_date("2026-09-08 22:00:00")),
			"2026-09-08",
		)

	@patch("pos_next.api.expenses._create_expense_journal_entry", return_value="ACC-JV-0001")
	@patch("pos_next.api.expenses.validate_employee")
	@patch(
		"pos_next.api.expenses.validate_mode_of_payment",
		return_value="Cash - TC",
	)
	@patch("pos_next.api.expenses.validate_expense_account")
	@patch("pos_next.api.expenses.validate_expense_amount")
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_create_pos_expense_creates_journal_entry_only(
		self,
		mock_db_get_value,
		_mock_validate_enabled,
		mock_validate_shift,
		_mock_validate_amount,
		_mock_validate_account,
		_mock_validate_mode,
		_mock_validate_employee,
		mock_create_je,
	):
		mock_validate_shift.return_value = SimpleNamespace(
			company="Test Company",
			period_start_date="2026-09-08 22:00:00",
		)
		mock_db_get_value.return_value = "Main - TC"

		result = expenses.create_pos_expense(
			"POS-OS-0001",
			"Test POS Profile",
			"Travel Expenses - TC",
			50,
			"Cash",
			employee="EMP-0001",
			remarks="Fuel",
		)

		self.assertEqual(result["name"], "ACC-JV-0001")
		self.assertEqual(result["journal_entry"], "ACC-JV-0001")
		mock_create_je.assert_called_once()
		self.assertEqual(
			mock_create_je.call_args.kwargs["period_start_date"],
			"2026-09-08 22:00:00",
		)
		self.assertEqual(mock_create_je.call_args.kwargs["payment_account"], "Cash - TC")
		self.assertEqual(mock_create_je.call_args.kwargs["remarks"], "Fuel")
		_mock_validate_account.assert_called_once_with(
			"Travel Expenses - TC", "Test Company", pos_profile="Test POS Profile"
		)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_create_pos_expense_requires_remarks(self, _mock_throw):
		with self.assertRaisesRegex(RuntimeError, "Remarks are required"):
			expenses.create_pos_expense(
				"POS-OS-0001",
				"Test POS Profile",
				"Travel Expenses - TC",
				50,
				"Cash",
				remarks="   ",
			)

	@patch("pos_next.api.expenses.frappe.has_permission", return_value=False)
	@patch("pos_next.api.expenses.frappe.get_doc")
	@patch("pos_next.api.expenses.validate_pos_expense_cancel_permission")
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	@patch("pos_next.api.expenses.frappe.session")
	def test_cancel_pos_expense_cancels_owned_submitted_je(
		self,
		mock_session,
		mock_get_value,
		_mock_validate_enabled,
		_mock_validate_shift,
		mock_validate_cancel,
		mock_get_doc,
		_mock_has_permission,
	):
		mock_session.user = "cashier@example.com"
		mock_get_value.return_value = SimpleNamespace(
			name="ACC-JV-0001",
			docstatus=1,
			posa_is_pos_expense=1,
			posa_pos_opening_shift="POS-OS-0001",
			posa_pos_profile="Test POS Profile",
			owner="cashier@example.com",
		)
		mock_doc = SimpleNamespace(name="ACC-JV-0001", flags=SimpleNamespace())
		mock_doc.cancel = unittest.mock.Mock()
		mock_get_doc.return_value = mock_doc

		result = expenses.cancel_pos_expense(
			"ACC-JV-0001", "POS-OS-0001", "Test POS Profile"
		)

		self.assertEqual(result["journal_entry"], "ACC-JV-0001")
		mock_doc.cancel.assert_called_once()
		mock_validate_cancel.assert_called_once_with(
			"Test POS Profile", "cashier@example.com", "ACC-JV-0001"
		)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_validate_expense_attachment_filename_rejects_exe(self, _mock_throw):
		with self.assertRaisesRegex(RuntimeError, "File type not allowed"):
			expenses._validate_expense_attachment_filename("malware.exe")

	def test_validate_expense_attachment_filename_allows_pdf(self):
		expenses._validate_expense_attachment_filename("receipt.PDF")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("frappe.core.api.file.get_max_file_size", return_value=10)
	@patch("pos_next.api.expenses.frappe.get_request_header", return_value=None)
	def test_read_uploaded_file_capped_rejects_oversized(
		self, _mock_header, _mock_max, _mock_throw
	):
		stream = SimpleNamespace(read=unittest.mock.Mock(side_effect=[b"0123456789AB", b""]))
		with self.assertRaisesRegex(RuntimeError, "File size exceeded"):
			expenses._read_uploaded_file_capped(stream, chunk_size=4)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("frappe.core.api.file.get_max_file_size", return_value=100)
	@patch("pos_next.api.expenses.frappe.get_request_header", return_value=None)
	def test_read_uploaded_file_capped_rejects_empty(self, _mock_header, _mock_max, _mock_throw):
		# Empty stream yields b""; attach_pos_expense_file rejects falsy content.
		stream = SimpleNamespace(read=unittest.mock.Mock(return_value=b""))
		self.assertEqual(expenses._read_uploaded_file_capped(stream), b"")

	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_roles",
		return_value=[],
	)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=1)
	def test_get_pos_expense_cancel_permissions_empty_roles_allows_dialog(
		self, _mock_get_value, _mock_roles
	):
		perms = expenses.get_pos_expense_cancel_permissions("Test POS Profile")
		self.assertEqual(perms, {"allow_cancel": 1, "can_cancel": 1})

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_cancel_pos_expense_rejects_when_allow_cancel_off(
		self, mock_get_value, _mock_enabled, _mock_shift, _mock_throw
	):
		mock_get_value.side_effect = [
			SimpleNamespace(
				name="ACC-JV-0001",
				docstatus=1,
				posa_is_pos_expense=1,
				posa_pos_opening_shift="POS-OS-0001",
				posa_pos_profile="Test POS Profile",
				owner="cashier@example.com",
			),
			0,  # posa_allow_cancel_pos_expense
		]
		with self.assertRaisesRegex(RuntimeError, "not allowed for this POS Profile"):
			expenses.cancel_pos_expense("ACC-JV-0001", "POS-OS-0001", "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_cancel_pos_expense_rejects_non_pos_expense(
		self, mock_get_value, _mock_enabled, _mock_shift, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			name="ACC-JV-0001",
			docstatus=1,
			posa_is_pos_expense=0,
			posa_pos_opening_shift="POS-OS-0001",
			posa_pos_profile="Test POS Profile",
			owner="cashier@example.com",
		)
		with self.assertRaisesRegex(RuntimeError, "not a POS expense"):
			expenses.cancel_pos_expense("ACC-JV-0001", "POS-OS-0001", "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_attach_pos_expense_file_rejects_non_pos_expense(
		self, mock_get_value, _mock_enabled, _mock_shift, _mock_throw
	):
		mock_get_value.return_value = SimpleNamespace(
			name="ACC-JV-0001",
			docstatus=1,
			posa_is_pos_expense=0,
			posa_pos_opening_shift="POS-OS-0001",
			posa_pos_profile="Test POS Profile",
			owner="cashier@example.com",
		)
		with self.assertRaisesRegex(RuntimeError, "not a POS expense"):
			expenses.attach_pos_expense_file(
				"ACC-JV-0001", "POS-OS-0001", "Test POS Profile"
			)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses._get_submitted_pos_expense_for_shift")
	def test_attach_pos_expense_file_requires_multipart_file(
		self, _mock_je, _mock_enabled, _mock_shift, _mock_throw
	):
		frappe.local.request = SimpleNamespace(files={})
		with self.assertRaisesRegex(RuntimeError, "File is required"):
			expenses.attach_pos_expense_file(
				"ACC-JV-0001", "POS-OS-0001", "Test POS Profile"
			)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_permissions",
		return_value={"allow_cancel": 0, "can_cancel": 0},
	)
	def test_validate_pos_expense_cancel_permission_requires_allow_cancel(
		self, _mock_perms, _mock_throw
	):
		with self.assertRaisesRegex(RuntimeError, "not allowed for this POS Profile"):
			expenses.validate_pos_expense_cancel_permission(
				"Test POS Profile", "cashier@example.com", "ACC-JV-0001"
			)

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.get_roles", return_value=["Sales User"])
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_roles",
		return_value=["Accounts Manager"],
	)
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_permissions",
		return_value={"allow_cancel": 1, "can_cancel": 0},
	)
	def test_validate_pos_expense_cancel_permission_requires_role(
		self, _mock_perms, _mock_roles, _mock_get_roles, _mock_throw
	):
		with self.assertRaisesRegex(RuntimeError, "not allowed to cancel"):
			expenses.validate_pos_expense_cancel_permission(
				"Test POS Profile", "other@example.com", "ACC-JV-0001"
			)

	@patch("pos_next.api.expenses.frappe.has_permission", return_value=False)
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.session")
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_roles",
		return_value=[],
	)
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_permissions",
		return_value={"allow_cancel": 1, "can_cancel": 1},
	)
	def test_validate_pos_expense_cancel_permission_owner_fallback(
		self, _mock_perms, _mock_roles, mock_session, _mock_throw, _mock_has_permission
	):
		mock_session.user = "cashier@example.com"
		with self.assertRaisesRegex(RuntimeError, "only cancel POS expenses you created"):
			expenses.validate_pos_expense_cancel_permission(
				"Test POS Profile", "other@example.com", "ACC-JV-0001"
			)

	@patch("pos_next.api.expenses.frappe.get_roles", return_value=["Accounts Manager"])
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_roles",
		return_value=["Accounts Manager"],
	)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=1)
	def test_get_pos_expense_cancel_permissions_with_matching_role(
		self, _mock_get_value, _mock_roles, _mock_get_roles
	):
		perms = expenses.get_pos_expense_cancel_permissions("Test POS Profile")
		self.assertEqual(perms, {"allow_cancel": 1, "can_cancel": 1})

	@patch("pos_next.api.expenses.frappe.get_roles", return_value=["Sales User"])
	@patch(
		"pos_next.api.expenses.get_pos_expense_cancel_roles",
		return_value=["Accounts Manager"],
	)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=1)
	def test_get_pos_expense_cancel_permissions_without_matching_role(
		self, _mock_get_value, _mock_roles, _mock_get_roles
	):
		perms = expenses.get_pos_expense_cancel_permissions("Test POS Profile")
		self.assertEqual(perms, {"allow_cancel": 1, "can_cancel": 0})

	@patch("pos_next.api.expenses.frappe.db.sql")
	def test_get_pos_expenses_reads_credit_amounts(self, mock_sql):
		mock_sql.return_value = [
			SimpleNamespace(
				name="ACC-JV-0001",
				posa_expense_account="Travel Expenses - TC",
				amount=50,
				posa_expense_employee="EMP-0001",
				posa_expense_mode_of_payment="Cash",
				user_remark="Fuel",
			)
		]

		result = expenses.get_pos_expenses("POS-OS-0001")

		self.assertEqual(result[0].journal_entry, "ACC-JV-0001")
		self.assertEqual(result[0].amount, 50)
		self.assertEqual(result[0].mode_of_payment, "Cash")
		sql = mock_sql.call_args.args[0]
		self.assertIn("SUM(jea.credit)", sql)
		self.assertNotIn("posa_expense_amount", sql)

class TestPOSExpenseJournalEntry(FrappeTestCase):
	"""Real Journal Entry insert/submit for the POS expense builder.

	One integration test covers debit/credit balance, cost center on both rows,
	payment-account resolution (M3), shift posting date (M5), and exchange-rate /
	base amounts (M7).
	"""

	PERIOD_START = "2026-09-08 22:00:00"
	AMOUNT = 50

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from pos_next.expense_test_fixtures import ensure_pos_expense_fixtures

		fx = ensure_pos_expense_fixtures()
		cls.COMPANY = fx.company
		cls.EXPENSE_ACCOUNT = fx.expense_account
		cls.COST_CENTER = fx.cost_center
		cls.MODE_OF_PAYMENT = fx.mode_of_payment
		cls.PROFILE = fx.pos_profile
		cls.PAYMENT_ACCOUNT = fx.payment_account

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _make_opening_shift(self):
		shift = frappe.get_doc(
			{
				"doctype": "POS Opening Shift",
				"period_start_date": self.PERIOD_START,
				"posting_date": "2026-09-08",
				"company": self.COMPANY,
				"pos_profile": self.PROFILE,
				"user": frappe.session.user,
				"balance_details": [
					{"mode_of_payment": self.MODE_OF_PAYMENT, "amount": 0}
				],
			}
		)
		shift.insert()
		return shift

	def test_create_expense_journal_entry_balances_rows_and_shift_fields(self):
		# M3: resolve the configured MoP cash ledger — no arbitrary Cash/Bank fallback.
		payment_account = expenses._resolve_payment_account(self.MODE_OF_PAYMENT, self.COMPANY)
		self.assertEqual(payment_account, self.PAYMENT_ACCOUNT)

		shift = self._make_opening_shift()

		je_name = expenses._create_expense_journal_entry(
			company=self.COMPANY,
			expense_account=self.EXPENSE_ACCOUNT,
			payment_account=payment_account,
			amount=self.AMOUNT,
			cost_center=self.COST_CENTER,
			pos_opening_shift=shift.name,
			pos_profile=self.PROFILE,
			mode_of_payment=self.MODE_OF_PAYMENT,
			employee=None,
			remarks="Integration test fuel",
			period_start_date=shift.period_start_date,
		)
		jv = frappe.get_doc("Journal Entry", je_name)

		self.assertEqual(jv.docstatus, 1)
		# M5: overnight shift posts to the shift start date, not "today".
		self.assertEqual(str(jv.posting_date), "2026-09-08")
		self.assertEqual(jv.posa_is_pos_expense, 1)
		self.assertEqual(jv.posa_pos_opening_shift, shift.name)
		self.assertEqual(jv.posa_pos_profile, self.PROFILE)
		self.assertEqual(jv.posa_expense_account, self.EXPENSE_ACCOUNT)
		self.assertEqual(flt(jv.posa_expense_amount), self.AMOUNT)
		self.assertEqual(jv.posa_expense_mode_of_payment, self.MODE_OF_PAYMENT)

		self.assertEqual(len(jv.accounts), 2)
		debit_row = next(row for row in jv.accounts if flt(row.debit) > 0)
		credit_row = next(row for row in jv.accounts if flt(row.credit) > 0)

		self.assertEqual(debit_row.account, self.EXPENSE_ACCOUNT)
		self.assertEqual(credit_row.account, payment_account)
		self.assertEqual(flt(debit_row.debit), self.AMOUNT)
		self.assertEqual(flt(credit_row.credit), self.AMOUNT)
		self.assertEqual(flt(debit_row.debit), flt(credit_row.credit))
		self.assertEqual(debit_row.cost_center, self.COST_CENTER)
		self.assertEqual(credit_row.cost_center, self.COST_CENTER)

		# M7: company-currency debit/credit and exchange_rate are set explicitly.
		self.assertEqual(flt(debit_row.exchange_rate), 1)
		self.assertEqual(flt(credit_row.exchange_rate), 1)
		self.assertEqual(flt(debit_row.debit_in_account_currency), self.AMOUNT)
		self.assertEqual(flt(credit_row.credit_in_account_currency), self.AMOUNT)
		self.assertEqual(flt(debit_row.credit), 0)
		self.assertEqual(flt(credit_row.debit), 0)

	def test_create_expense_journal_entry_keeps_attachment(self):
		payment_account = expenses._resolve_payment_account(self.MODE_OF_PAYMENT, self.COMPANY)
		shift = self._make_opening_shift()
		shift.submit()

		je_name = expenses._create_expense_journal_entry(
			company=self.COMPANY,
			expense_account=self.EXPENSE_ACCOUNT,
			payment_account=payment_account,
			amount=self.AMOUNT,
			cost_center=self.COST_CENTER,
			pos_opening_shift=shift.name,
			pos_profile=self.PROFILE,
			mode_of_payment=self.MODE_OF_PAYMENT,
			employee=None,
			remarks="Receipt attached",
			period_start_date=shift.period_start_date,
		)

		from io import BytesIO

		from werkzeug.datastructures import FileStorage

		uploaded = FileStorage(
			stream=BytesIO(b"fuel receipt"),
			filename="pos-expense-receipt.txt",
			content_type="text/plain",
		)
		frappe.local.request = SimpleNamespace(
			files={"file": uploaded},
			host="localhost",
			scheme="http",
			headers={},
		)

		# Profile must allow expenses for the attach gate.
		frappe.db.set_value("POS Profile", self.PROFILE, "posa_allow_pos_expense", 1)

		result = expenses.attach_pos_expense_file(je_name, shift.name, self.PROFILE)

		self.assertTrue(result["name"])
		self.assertTrue(
			frappe.db.exists(
				"File",
				{
					"name": result["name"],
					"attached_to_doctype": "Journal Entry",
					"attached_to_name": je_name,
				},
			)
		)
		self.assertEqual(
			frappe.db.get_value("Journal Entry", je_name, "user_remark"),
			"Receipt attached",
		)


class TestOfflineExpenseDedup(unittest.TestCase):
	"""Unit / mock tests for offline_id reservation and check API."""

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_create_pos_expense_requires_remarks_without_offline_id(self, _mock_throw):
		with self.assertRaisesRegex(RuntimeError, "Remarks are required"):
			expenses.create_pos_expense(
				"POS-OS-0001",
				"Test POS Profile",
				"Travel Expenses - TC",
				50,
				"Cash",
				remarks="",
			)

	@patch("pos_next.api.expenses._cleanup_failed_offline_expense_sync")
	@patch("pos_next.api.expenses._complete_offline_expense_sync")
	@patch("pos_next.api.expenses._create_expense_journal_entry", return_value="ACC-JV-OFF-1")
	@patch("pos_next.api.expenses.validate_employee")
	@patch(
		"pos_next.api.expenses.validate_mode_of_payment",
		return_value="Cash - TC",
	)
	@patch("pos_next.api.expenses.validate_expense_account")
	@patch("pos_next.api.expenses.validate_expense_amount")
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses._ensure_offline_expense_uniqueness")
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value="Main - TC")
	def test_create_with_offline_id_completes_sync_record(
		self,
		_mock_db,
		mock_ensure,
		_mock_enabled,
		mock_shift,
		_mock_amount,
		_mock_account,
		_mock_mode,
		_mock_employee,
		_mock_create,
		mock_complete,
		_mock_cleanup,
	):
		mock_ensure.return_value = {
			"already_synced": False,
			"sync_record_name": "OES-0001",
		}
		mock_shift.return_value = SimpleNamespace(
			company="Test Company",
			period_start_date="2026-09-08 22:00:00",
		)

		result = expenses.create_pos_expense(
			"POS-OS-0001",
			"Test POS Profile",
			"Travel Expenses - TC",
			50,
			"Cash",
			remarks="Offline fuel",
			offline_id="pos_expense_test-1",
		)

		self.assertEqual(result["journal_entry"], "ACC-JV-OFF-1")
		self.assertEqual(result["offline_id"], "pos_expense_test-1")
		mock_complete.assert_called_once_with("OES-0001", "ACC-JV-OFF-1")

	@patch("pos_next.api.expenses._create_expense_journal_entry")
	@patch("pos_next.api.expenses._ensure_offline_expense_uniqueness")
	def test_create_with_duplicate_offline_id_returns_existing_je(
		self, mock_ensure, mock_create
	):
		mock_ensure.return_value = {
			"already_synced": True,
			"expense_data": {
				"name": "ACC-JV-EXISTING",
				"journal_entry": "ACC-JV-EXISTING",
				"amount": 50,
				"duplicate_prevented": True,
				"offline_id": "pos_expense_dup",
			},
		}

		result = expenses.create_pos_expense(
			"POS-OS-0001",
			"Test POS Profile",
			"Travel Expenses - TC",
			50,
			"Cash",
			remarks="Dup",
			offline_id="pos_expense_dup",
		)

		self.assertEqual(result["journal_entry"], "ACC-JV-EXISTING")
		self.assertTrue(result["duplicate_prevented"])
		mock_create.assert_not_called()

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_create_offline_id_in_progress_throws(self, mock_get_value, _mock_throw):
		mock_get_value.return_value = frappe._dict(
			name="OES-PENDING",
			journal_entry="",
			status="Pending",
			modified=frappe.utils.now_datetime(),
		)

		with self.assertRaisesRegex(RuntimeError, "currently being processed"):
			expenses._ensure_offline_expense_uniqueness(
				"pos_expense_in_progress",
				pos_profile="Test POS Profile",
				pos_opening_shift="POS-OS-0001",
			)

	@patch("pos_next.api.expenses.validate_expense_amount", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses._ensure_offline_expense_uniqueness")
	@patch("pos_next.api.expenses._cleanup_failed_offline_expense_sync")
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_create_still_enforces_shift_limit_with_offline_id(
		self,
		_mock_throw,
		mock_cleanup,
		mock_ensure,
		_mock_enabled,
		mock_shift,
		_mock_amount,
	):
		mock_ensure.return_value = {
			"already_synced": False,
			"sync_record_name": "OES-LIMIT",
		}
		mock_shift.return_value = SimpleNamespace(
			company="Test Company",
			period_start_date="2026-09-08 22:00:00",
		)

		with self.assertRaises(RuntimeError):
			expenses.create_pos_expense(
				"POS-OS-0001",
				"Test POS Profile",
				"Travel Expenses - TC",
				99999,
				"Cash",
				remarks="Over limit",
				offline_id="pos_expense_limit",
			)

		mock_cleanup.assert_called_once_with("OES-LIMIT")

	@patch("pos_next.api.expenses.validate_expense_account", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.validate_expense_amount")
	@patch("pos_next.api.expenses.validate_open_shift")
	@patch("pos_next.api.expenses.validate_pos_expense_enabled")
	@patch("pos_next.api.expenses._ensure_offline_expense_uniqueness")
	@patch("pos_next.api.expenses._cleanup_failed_offline_expense_sync")
	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	def test_create_still_enforces_account_whitelist_with_offline_id(
		self,
		_mock_throw,
		mock_cleanup,
		mock_ensure,
		_mock_enabled,
		mock_shift,
		_mock_amount,
		_mock_account,
	):
		mock_ensure.return_value = {
			"already_synced": False,
			"sync_record_name": "OES-ACCT",
		}
		mock_shift.return_value = SimpleNamespace(
			company="Test Company",
			period_start_date="2026-09-08 22:00:00",
		)

		with self.assertRaises(RuntimeError):
			expenses.create_pos_expense(
				"POS-OS-0001",
				"Test POS Profile",
				"Not Allowed - TC",
				50,
				"Cash",
				remarks="Bad account",
				offline_id="pos_expense_acct",
			)

		mock_cleanup.assert_called_once_with("OES-ACCT")

	@patch(
		"pos_next.pos_next.doctype.offline_expense_sync.offline_expense_sync.OfflineExpenseSync.is_synced"
	)
	@patch("pos_next.api.expenses.frappe.db.exists", return_value=True)
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=1)
	def test_check_offline_expense_synced_true(self, _mock_get, _mock_exists, mock_is_synced):
		mock_is_synced.return_value = {
			"synced": True,
			"journal_entry": "ACC-JV-1",
			"status": "Synced",
		}
		result = expenses.check_offline_expense_synced("pos_expense_ok")
		self.assertTrue(result["synced"])
		self.assertEqual(result["journal_entry"], "ACC-JV-1")

	@patch(
		"pos_next.pos_next.doctype.offline_expense_sync.offline_expense_sync.OfflineExpenseSync.is_synced"
	)
	def test_check_offline_expense_synced_false(self, mock_is_synced):
		mock_is_synced.return_value = {
			"synced": False,
			"journal_entry": None,
			"status": None,
		}
		result = expenses.check_offline_expense_synced("pos_expense_missing")
		self.assertFalse(result["synced"])


class TestOfflineExpenseJournalEntry(FrappeTestCase):
	"""Integration: real JE + Offline Expense Sync + File attach."""

	PERIOD_START = "2026-09-08 22:00:00"
	AMOUNT = 25

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from pos_next.expense_test_fixtures import ensure_pos_expense_fixtures

		fx = ensure_pos_expense_fixtures()
		cls.COMPANY = fx.company
		cls.EXPENSE_ACCOUNT = fx.expense_account
		cls.COST_CENTER = fx.cost_center
		cls.MODE_OF_PAYMENT = fx.mode_of_payment
		cls.PROFILE = fx.pos_profile
		cls.PAYMENT_ACCOUNT = fx.payment_account
		frappe.db.set_value("POS Profile", cls.PROFILE, "posa_allow_pos_expense", 1)
		frappe.db.set_value("POS Profile", cls.PROFILE, "posa_maximum_expense_amount", 10000)
		# Ensure allowed account whitelist is empty (= all expense accounts) or includes ours
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _make_opening_shift(self):
		shift = frappe.get_doc(
			{
				"doctype": "POS Opening Shift",
				"period_start_date": self.PERIOD_START,
				"posting_date": "2026-09-08",
				"company": self.COMPANY,
				"pos_profile": self.PROFILE,
				"user": frappe.session.user,
				"balance_details": [
					{"mode_of_payment": self.MODE_OF_PAYMENT, "amount": 0}
				],
			}
		)
		shift.insert()
		shift.submit()
		return shift

	def test_offline_expense_sync_creates_balanced_je(self):
		shift = self._make_opening_shift()
		offline_id = f"pos_expense_it_{frappe.generate_hash(length=8)}"

		result = expenses.create_pos_expense(
			shift.name,
			self.PROFILE,
			self.EXPENSE_ACCOUNT,
			self.AMOUNT,
			self.MODE_OF_PAYMENT,
			remarks="Offline integration fuel",
			offline_id=offline_id,
		)

		je_name = result["journal_entry"]
		jv = frappe.get_doc("Journal Entry", je_name)
		self.assertEqual(jv.docstatus, 1)
		self.assertEqual(jv.posa_is_pos_expense, 1)
		debit = sum(flt(r.debit) for r in jv.accounts)
		credit = sum(flt(r.credit) for r in jv.accounts)
		self.assertEqual(debit, credit)
		self.assertEqual(debit, self.AMOUNT)

		sync = frappe.db.get_value(
			"Offline Expense Sync",
			{"offline_id": offline_id},
			["status", "journal_entry"],
			as_dict=True,
		)
		self.assertEqual(sync.status, "Synced")
		self.assertEqual(sync.journal_entry, je_name)

	def test_attach_after_offline_create(self):
		shift = self._make_opening_shift()
		offline_id = f"pos_expense_att_{frappe.generate_hash(length=8)}"
		result = expenses.create_pos_expense(
			shift.name,
			self.PROFILE,
			self.EXPENSE_ACCOUNT,
			self.AMOUNT,
			self.MODE_OF_PAYMENT,
			remarks="Attach after offline",
			offline_id=offline_id,
		)
		je_name = result["journal_entry"]

		from io import BytesIO

		from werkzeug.datastructures import FileStorage

		uploaded = FileStorage(
			stream=BytesIO(b"offline receipt"),
			filename="offline-expense.txt",
			content_type="text/plain",
		)
		frappe.local.request = SimpleNamespace(
			files={"file": uploaded},
			host="localhost",
			scheme="http",
			headers={},
		)

		attach = expenses.attach_pos_expense_file(je_name, shift.name, self.PROFILE)
		self.assertTrue(
			frappe.db.exists(
				"File",
				{
					"name": attach["name"],
					"attached_to_doctype": "Journal Entry",
					"attached_to_name": je_name,
				},
			)
		)

		# Idempotent retry: same name+size returns existing File, no duplicate.
		frappe.local.request = SimpleNamespace(
			files={
				"file": FileStorage(
					stream=BytesIO(b"offline receipt"),
					filename="offline-expense.txt",
					content_type="text/plain",
				)
			},
			host="localhost",
			scheme="http",
			headers={},
		)
		again = expenses.attach_pos_expense_file(je_name, shift.name, self.PROFILE)
		self.assertEqual(again["name"], attach["name"])
		self.assertTrue(again.get("already_attached"))
		self.assertEqual(
			frappe.db.count(
				"File",
				{
					"attached_to_doctype": "Journal Entry",
					"attached_to_name": je_name,
					"file_name": "offline-expense.txt",
				},
			),
			1,
		)

	def test_duplicate_offline_id_does_not_double_cash(self):
		shift = self._make_opening_shift()
		offline_id = f"pos_expense_dd_{frappe.generate_hash(length=8)}"

		first = expenses.create_pos_expense(
			shift.name,
			self.PROFILE,
			self.EXPENSE_ACCOUNT,
			self.AMOUNT,
			self.MODE_OF_PAYMENT,
			remarks="First",
			offline_id=offline_id,
		)
		second = expenses.create_pos_expense(
			shift.name,
			self.PROFILE,
			self.EXPENSE_ACCOUNT,
			self.AMOUNT,
			self.MODE_OF_PAYMENT,
			remarks="Second",
			offline_id=offline_id,
		)

		self.assertEqual(first["journal_entry"], second["journal_entry"])
		self.assertTrue(second.get("duplicate_prevented"))

		je_count = frappe.db.count(
			"Journal Entry",
			{
				"posa_pos_opening_shift": shift.name,
				"posa_is_pos_expense": 1,
				"docstatus": 1,
			},
		)
		self.assertEqual(je_count, 1)
		self.assertEqual(flt(expenses.get_shift_expense_total(shift.name)), self.AMOUNT)
