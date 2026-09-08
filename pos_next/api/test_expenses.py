# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
		mock_get_value.return_value = 0

		with self.assertRaisesRegex(RuntimeError, "not configured"):
			expenses.validate_expense_amount(50, "Test POS Profile")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.format_value", side_effect=lambda value, _options: str(value))
	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=0)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_over_shift_limit(
		self, mock_get_value, _mock_shift_total, _mock_format, _mock_throw
	):
		mock_get_value.return_value = 100

		with self.assertRaisesRegex(RuntimeError, "shift expense limit"):
			expenses.validate_expense_amount(150, "Test POS Profile", "POS-OS-0001")

	@patch("pos_next.api.expenses.frappe.throw", side_effect=_raise_runtime_error)
	@patch("pos_next.api.expenses.frappe.format_value", side_effect=lambda value, _options: str(value))
	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=80)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_rejects_when_cumulative_exceeds_limit(
		self, mock_get_value, _mock_shift_total, _mock_format, _mock_throw
	):
		mock_get_value.return_value = 100

		with self.assertRaisesRegex(RuntimeError, "shift expense limit"):
			expenses.validate_expense_amount(30, "Test POS Profile", "POS-OS-0001")

	@patch("pos_next.api.expenses.get_shift_expense_total", return_value=0)
	@patch("pos_next.api.expenses.frappe.db.get_value")
	def test_validate_expense_amount_locks_opening_shift_before_total(
		self, mock_get_value, mock_shift_total
	):
		"""Serialize check+insert: FOR UPDATE on the shift before reading the SUM."""
		mock_get_value.side_effect = [100, "POS-OS-0001"]

		expenses.validate_expense_amount(50, "Test POS Profile", "POS-OS-0001")

		self.assertEqual(
			mock_get_value.call_args_list,
			[
				unittest.mock.call(
					"POS Profile", "Test POS Profile", "posa_maximum_expense_amount"
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
	@patch("pos_next.api.expenses.frappe.db.sql", return_value=[])
	@patch("pos_next.api.expenses.frappe.db.get_value", return_value=None)
	def test_resolve_payment_account_throws_informative_error(
		self, _mock_get_value, _mock_sql, _mock_throw
	):
		with self.assertRaisesRegex(RuntimeError, "Please set default Cash account"):
			expenses._resolve_payment_account("Cash", "Test Company", "Test POS Profile")

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
		"""Employee list is company-scoped and capped; ignore_permissions is intentional."""
		mock_get_all.return_value = [{"name": "EMP-0001", "employee_name": "John Doe"}]

		result = expenses.get_active_employees("Test Company")

		self.assertEqual(result[0]["name"], "EMP-0001")
		kwargs = mock_get_all.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"status": "Active", "company": "Test Company"})
		self.assertEqual(kwargs["fields"], ["name", "employee_name"])
		self.assertEqual(kwargs["limit_page_length"], expenses.EMPLOYEE_PAGE_LENGTH)

	@patch("pos_next.api.expenses.frappe.get_all")
	def test_get_expense_accounts_is_capped(self, mock_get_all):
		mock_get_all.return_value = []
		expenses.get_expense_accounts("Test Company")
		kwargs = mock_get_all.call_args.kwargs
		self.assertEqual(kwargs["limit_page_length"], expenses.EXPENSE_ACCOUNT_PAGE_LENGTH)

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

	@patch("pos_next.api.expenses.frappe.has_permission", return_value=False)
	@patch("pos_next.api.expenses.frappe.get_doc")
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
		self.assertTrue(mock_doc.flags.ignore_permissions)

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
