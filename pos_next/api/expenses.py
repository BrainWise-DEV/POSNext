# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
POS Expense API
Records expenses from active POS shifts as submitted Journal Entries.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, today


@frappe.whitelist()
def get_expense_dialog_data(pos_profile, pos_opening_shift):
	"""Return expense accounts and payment methods for the expense dialog."""
	validate_pos_expense_enabled(pos_profile)
	validate_open_shift(pos_opening_shift, pos_profile)

	company = frappe.db.get_value("POS Profile", pos_profile, "company")
	maximum_expense_amount = flt(
		frappe.db.get_value("POS Profile", pos_profile, "posa_maximum_expense_amount")
	)

	from pos_next.api.pos_profile import get_payment_methods

	return {
		"expense_accounts": get_expense_accounts(company),
		"payment_methods": get_payment_methods(pos_profile),
		"employees": get_active_employees(company),
		"maximum_expense_amount": maximum_expense_amount,
	}


@frappe.whitelist()
def create_pos_expense(
	pos_opening_shift,
	pos_profile,
	expense_account,
	amount,
	mode_of_payment,
	employee=None,
	remarks=None,
):
	"""Create and submit a Journal Entry for a POS expense."""
	amount = flt(amount)
	remarks = (remarks or "").strip()
	expense_account = _coerce_account_name(expense_account)

	validate_pos_expense_enabled(pos_profile)
	shift = validate_open_shift(pos_opening_shift, pos_profile)
	validate_expense_amount(amount, pos_profile)
	validate_expense_account(expense_account, shift.company)
	validate_mode_of_payment(mode_of_payment, pos_profile, shift.company)
	if employee:
		validate_employee(employee, shift.company)

	cost_center = frappe.db.get_value("POS Profile", pos_profile, "cost_center")
	payment_account = _ensure_account_name(
		_resolve_payment_account(mode_of_payment, shift.company),
		_("Payment Account"),
	)

	journal_entry_name = _create_expense_journal_entry(
		company=shift.company,
		expense_account=expense_account,
		payment_account=payment_account,
		amount=amount,
		cost_center=cost_center,
		pos_opening_shift=pos_opening_shift,
		pos_profile=pos_profile,
		mode_of_payment=mode_of_payment,
		employee=employee,
		remarks=remarks,
	)

	return {
		"name": journal_entry_name,
		"journal_entry": journal_entry_name,
		"amount": amount,
		"message": _("POS Expense recorded in Journal Entry {0}").format(journal_entry_name),
	}


def validate_pos_expense_enabled(pos_profile):
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	if not cint(frappe.db.get_value("POS Profile", pos_profile, "posa_allow_pos_expense")):
		frappe.throw(
			_("POS Expense is not enabled for POS Profile {0}").format(frappe.bold(pos_profile)),
			title=_("POS Expense Disabled"),
		)


def validate_open_shift(pos_opening_shift, pos_profile):
	if not pos_opening_shift:
		frappe.throw(_("POS Opening Shift is required"))

	shift = frappe.db.get_value(
		"POS Opening Shift",
		pos_opening_shift,
		["name", "status", "pos_profile", "company", "user", "docstatus"],
		as_dict=True,
	)
	if not shift or shift.docstatus != 1:
		frappe.throw(_("POS Opening Shift {0} does not exist").format(pos_opening_shift))

	if shift.status != "Open":
		frappe.throw(_("POS Opening Shift must be open to record an expense"))

	if shift.pos_profile != pos_profile:
		frappe.throw(_("POS Opening Shift does not belong to the selected POS Profile"))

	if shift.user != frappe.session.user:
		frappe.throw(_("You can only record expenses for your own open shift"))

	return shift


def validate_expense_amount(amount, pos_profile):
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	maximum_amount = flt(
		frappe.db.get_value("POS Profile", pos_profile, "posa_maximum_expense_amount")
	)
	if maximum_amount > 0 and flt(amount) > maximum_amount:
		frappe.throw(
			_("Amount {0} exceeds the maximum allowed expense amount of {1}").format(
				frappe.format_value(amount, {"fieldtype": "Currency"}),
				frappe.format_value(maximum_amount, {"fieldtype": "Currency"}),
			),
			title=_("Maximum Expense Amount Exceeded"),
		)


def validate_expense_account(expense_account, company):
	if not expense_account:
		frappe.throw(_("Expense Account is required"))

	account = frappe.db.get_value(
		"Account",
		expense_account,
		["name", "company", "is_group", "disabled", "account_type", "root_type"],
		as_dict=True,
	)
	if not account:
		frappe.throw(_("Expense Account {0} does not exist").format(expense_account))

	if account.company != company:
		frappe.throw(_("Expense Account must belong to company {0}").format(company))

	if account.is_group:
		frappe.throw(_("Expense Account must be a ledger account"))

	if account.disabled:
		frappe.throw(_("Expense Account {0} is disabled").format(expense_account))

	if account.account_type != "Expense" and account.root_type != "Expense":
		frappe.throw(_("Selected account must be an expense account"))


def validate_mode_of_payment(mode_of_payment, pos_profile, company):
	if not mode_of_payment:
		frappe.throw(_("Mode of Payment is required"))

	profile_modes = frappe.get_all(
		"POS Payment Method",
		filters={"parent": pos_profile, "mode_of_payment": mode_of_payment},
		pluck="name",
	)
	if not profile_modes:
		frappe.throw(
			_("Mode of Payment {0} is not configured in POS Profile {1}").format(
				frappe.bold(mode_of_payment),
				frappe.bold(pos_profile),
			)
		)

	if not _resolve_payment_account(mode_of_payment, company):
		frappe.throw(
			_("Payment account is not configured for {0}").format(frappe.bold(mode_of_payment)),
			title=_("Missing Payment Account"),
		)


def _coerce_account_name(account):
	"""Return an Account name from a string or payment-account lookup dict."""
	while isinstance(account, dict):
		account = account.get("account") or account.get("name") or account.get("value")

	if account in (None, ""):
		return None

	return cstr(account).strip() or None


def _ensure_account_name(account, label):
	account_name = _coerce_account_name(account)
	if not account_name:
		frappe.throw(
			_("{0} is required").format(label),
			title=_("Missing Account"),
		)
	return account_name


def _resolve_payment_account(mode_of_payment, company):
	"""Return the default cash/bank account name for a mode of payment."""
	try:
		from pos_next.api.invoices import get_payment_account

		account_info = get_payment_account(mode_of_payment, company)
	except Exception:
		return None

	return _coerce_account_name(account_info)


def get_active_employees(company):
	"""Return active employees for the expense dialog (POS cashiers may lack Employee read perm)."""
	filters = {"status": "Active"}
	if company:
		filters["company"] = company

	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name"],
		order_by="employee_name asc",
		limit_page_length=200,
		ignore_permissions=True,
	)


def validate_employee(employee, company):
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} does not exist").format(employee))

	employee_company = frappe.db.get_value("Employee", employee, ["company", "status"], as_dict=True)
	if not employee_company:
		frappe.throw(_("Employee {0} does not exist").format(employee))

	if employee_company.status != "Active":
		frappe.throw(_("Employee {0} is not active").format(employee))

	if company and employee_company.company and employee_company.company != company:
		frappe.throw(_("Employee {0} does not belong to company {1}").format(employee, company))


def get_expense_accounts(company):
	return frappe.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"disabled": 0,
		},
		or_filters=[
			["account_type", "=", "Expense"],
			["root_type", "=", "Expense"],
		],
		fields=["name", "account_name"],
		order_by="name",
		limit_page_length=0,
		ignore_permissions=True,
	)


def _create_expense_journal_entry(
	company,
	expense_account,
	payment_account,
	amount,
	cost_center,
	pos_opening_shift,
	pos_profile,
	mode_of_payment,
	employee,
	remarks,
):
	user_remark = remarks or _("POS Expense for shift {0}").format(pos_opening_shift)
	expense_account = _ensure_account_name(expense_account, _("Expense Account"))
	payment_account = _ensure_account_name(payment_account, _("Payment Account"))

	jv_doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": today(),
			"company": company,
			"user_remark": user_remark,
			"cheque_no": pos_opening_shift,
			"cheque_date": today(),
			"posa_is_pos_expense": 1,
			"posa_pos_opening_shift": pos_opening_shift,
			"posa_pos_profile": pos_profile,
			"posa_expense_account": expense_account,
			"posa_expense_amount": amount,
			"posa_expense_mode_of_payment": mode_of_payment,
			"posa_expense_employee": employee,
		}
	)

	expense_row = jv_doc.append("accounts", {})
	expense_row.update(
		{
			"account": expense_account,
			"debit_in_account_currency": amount,
			"credit_in_account_currency": 0,
			"cost_center": cost_center,
		}
	)

	payment_row = jv_doc.append("accounts", {})
	payment_row.update(
		{
			"account": payment_account,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": amount,
			"cost_center": cost_center,
		}
	)

	jv_doc.flags.ignore_permissions = True
	jv_doc.insert()
	jv_doc.submit()

	return jv_doc.name


def get_pos_expenses(pos_opening_shift):
	"""Return submitted POS expense Journal Entries for a shift."""
	expenses = frappe.get_all(
		"Journal Entry",
		filters={
			"posa_is_pos_expense": 1,
			"posa_pos_opening_shift": pos_opening_shift,
			"docstatus": 1,
		},
		fields=[
			"name",
			"posa_expense_account",
			"posa_expense_amount",
			"posa_expense_employee",
			"posa_expense_mode_of_payment",
			"user_remark",
		],
		order_by="creation asc",
	)

	return [
		frappe._dict(
			name=expense.name,
			journal_entry=expense.name,
			expense_account=expense.posa_expense_account,
			amount=flt(expense.posa_expense_amount),
			employee=expense.posa_expense_employee or "",
			remarks=(expense.user_remark or "").strip(),
			mode_of_payment=expense.posa_expense_mode_of_payment,
		)
		for expense in expenses
	]
