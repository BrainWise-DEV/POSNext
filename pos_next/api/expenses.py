# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
POS Expense API
Records expenses from active POS shifts as submitted Journal Entries.

Permission note
---------------
Cashiers typically lack Employee / Account read permissions. get_active_employees
and get_expense_accounts therefore use ignore_permissions=True after the caller
has proven an open shift they own (via validate_open_shift). That is an intentional
trade-off: HR and chart data are scoped to the shift's company and capped, but
still visible at the till. Revisit if a narrower Employee/Account role is introduced.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, today


EXPENSE_ACCOUNT_PAGE_LENGTH = 50
EMPLOYEE_PAGE_LENGTH = 200


@frappe.whitelist()
def get_expense_dialog_data(pos_profile, pos_opening_shift):
	"""Return expense accounts and payment methods for the expense dialog."""
	validate_pos_expense_enabled(pos_profile)
	shift = validate_open_shift(pos_opening_shift, pos_profile)

	company = shift.company
	maximum_expense_amount = flt(
		frappe.db.get_value("POS Profile", pos_profile, "posa_maximum_expense_amount")
	)
	shift_expense_total = get_shift_expense_total(pos_opening_shift)
	remaining_expense_amount = _get_remaining_shift_expense_amount(
		maximum_expense_amount, shift_expense_total
	)

	return {
		"expense_accounts": get_expense_accounts(company),
		"payment_methods": get_cash_payment_methods(pos_profile),
		"employees": get_active_employees(company),
		"expenses": get_pos_expenses(pos_opening_shift),
		"maximum_expense_amount": maximum_expense_amount,
		"shift_expense_total": shift_expense_total,
		"remaining_expense_amount": remaining_expense_amount,
	}


@frappe.whitelist()
def search_expense_accounts(pos_profile, pos_opening_shift, txt=None):
	"""Server-side expense account search for the POS dialog."""
	validate_pos_expense_enabled(pos_profile)
	shift = validate_open_shift(pos_opening_shift, pos_profile)
	return get_expense_accounts(shift.company, txt=txt)


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
	validate_expense_amount(amount, pos_profile, pos_opening_shift)
	validate_expense_account(expense_account, shift.company)
	payment_account = validate_mode_of_payment(mode_of_payment, pos_profile, shift.company)
	if employee:
		validate_employee(employee, shift.company)

	cost_center = frappe.db.get_value("POS Profile", pos_profile, "cost_center")

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
		period_start_date=shift.period_start_date,
	)

	return {
		"name": journal_entry_name,
		"journal_entry": journal_entry_name,
		"amount": amount,
		"message": _("POS Expense recorded in Journal Entry {0}").format(journal_entry_name),
	}


@frappe.whitelist()
def cancel_pos_expense(journal_entry, pos_opening_shift, pos_profile):
	"""Cancel a POS expense Journal Entry while the opening shift is still open.

	Refused once the shift is closed so closing totals and payment reconciliation
	cannot silently diverge from cancelled JEs.
	"""
	if not journal_entry:
		frappe.throw(_("Journal Entry is required"))

	validate_pos_expense_enabled(pos_profile)
	validate_open_shift(pos_opening_shift, pos_profile)

	je = frappe.db.get_value(
		"Journal Entry",
		journal_entry,
		[
			"name",
			"docstatus",
			"posa_is_pos_expense",
			"posa_pos_opening_shift",
			"posa_pos_profile",
			"owner",
		],
		as_dict=True,
	)
	if not je:
		frappe.throw(_("Journal Entry {0} does not exist").format(journal_entry))

	if not cint(je.posa_is_pos_expense):
		frappe.throw(_("Journal Entry {0} is not a POS expense").format(journal_entry))

	if je.posa_pos_opening_shift != pos_opening_shift:
		frappe.throw(_("Journal Entry does not belong to the selected POS Opening Shift"))

	if je.posa_pos_profile and je.posa_pos_profile != pos_profile:
		frappe.throw(_("Journal Entry does not belong to the selected POS Profile"))

	if je.docstatus != 1:
		frappe.throw(_("Only submitted POS expenses can be cancelled"))

	if je.owner != frappe.session.user and not frappe.has_permission(
		"Journal Entry", "cancel", doc=journal_entry
	):
		frappe.throw(_("You can only cancel POS expenses you created"))

	jv_doc = frappe.get_doc("Journal Entry", journal_entry)
	jv_doc.flags.ignore_permissions = True
	jv_doc.cancel()

	return {
		"name": jv_doc.name,
		"journal_entry": jv_doc.name,
		"message": _("POS Expense {0} cancelled").format(jv_doc.name),
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
		[
			"name",
			"status",
			"pos_profile",
			"company",
			"user",
			"docstatus",
			"period_start_date",
		],
		as_dict=True,
	)
	if not shift or shift.docstatus != 1:
		frappe.throw(_("POS Opening Shift {0} does not exist").format(pos_opening_shift))

	if shift.status != "Open":
		frappe.throw(_("POS Opening Shift must be open to record or cancel an expense"))

	if shift.pos_profile != pos_profile:
		frappe.throw(_("POS Opening Shift does not belong to the selected POS Profile"))

	if shift.user != frappe.session.user:
		frappe.throw(_("You can only manage expenses for your own open shift"))

	return shift


def validate_expense_amount(amount, pos_profile, pos_opening_shift=None):
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	maximum_amount = flt(
		frappe.db.get_value("POS Profile", pos_profile, "posa_maximum_expense_amount")
	)
	if maximum_amount <= 0:
		frappe.throw(
			_(
				"Maximum Expense Amount is not configured on POS Profile {0}. "
				"Set a positive limit before recording expenses."
			).format(pos_profile),
			title=_("Expense Limit Not Configured"),
		)

	# Lock the opening shift so concurrent create_pos_expense calls serialize:
	# both would otherwise read the same SUM, pass the limit, and both commit.
	# Held until request commit (after JE insert/submit in the same transaction).
	if pos_opening_shift:
		frappe.db.get_value(
			"POS Opening Shift",
			pos_opening_shift,
			"name",
			for_update=True,
		)
		shift_total = get_shift_expense_total(pos_opening_shift)
	else:
		shift_total = 0

	new_shift_total = shift_total + flt(amount)
	if new_shift_total > maximum_amount:
		remaining = _get_remaining_shift_expense_amount(maximum_amount, shift_total)
		frappe.throw(
			_(
				"This expense would exceed the shift expense limit of {0}. "
				"Expenses recorded this shift: {1}. Remaining allowance: {2}"
			).format(
				frappe.format_value(maximum_amount, {"fieldtype": "Currency"}),
				frappe.format_value(shift_total, {"fieldtype": "Currency"}),
				frappe.format_value(remaining, {"fieldtype": "Currency"}),
			),
			title=_("Shift Expense Limit Exceeded"),
		)


def get_shift_expense_total(pos_opening_shift):
	"""Return company-currency total of money that left the drawer for a shift.

	Sums Journal Entry Account credit rows (actual GL movement), not the
	writable posa_expense_amount custom field.
	"""
	if not pos_opening_shift:
		return 0

	total = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(jea.credit), 0)
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.posa_is_pos_expense = 1
		  AND je.posa_pos_opening_shift = %s
		  AND je.docstatus = 1
		  AND jea.credit > 0
		""",
		pos_opening_shift,
	)
	return flt(total[0][0] if total else 0)


def _get_remaining_shift_expense_amount(maximum_amount, shift_expense_total):
	if flt(maximum_amount) <= 0:
		return 0
	return max(0, flt(maximum_amount) - flt(shift_expense_total))


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
	"""Validate MoP on the profile and return its Cash payment account name."""
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

	payment_account = _resolve_payment_account(mode_of_payment, company, pos_profile)
	account_type = frappe.db.get_value("Account", payment_account, "account_type")
	if account_type != "Cash":
		frappe.throw(
			_(
				"POS expenses can only be paid from Cash accounts. "
				"Mode of Payment {0} resolves to {1} (account type: {2})."
			).format(
				frappe.bold(mode_of_payment),
				frappe.bold(payment_account),
				frappe.bold(account_type or _("Unknown")),
			),
			title=_("Cash Mode Required"),
		)

	return payment_account


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


def _resolve_payment_account(mode_of_payment, company, pos_profile=None):
	"""Return the configured cash/bank account for a mode of payment.

	Only uses Mode of Payment Account and (optionally) the POS Profile's
	payment-method default_account. Does not fall back to an arbitrary
	company Cash/Bank ledger.
	"""
	account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)
	if account:
		return account

	if pos_profile:
		account = frappe.db.get_value(
			"POS Payment Method",
			{"parent": pos_profile, "mode_of_payment": mode_of_payment},
			"default_account",
		)
		if account:
			return account

	# Broader profile fallback when pos_profile was not passed
	account_rows = frappe.db.sql(
		"""
		SELECT ppm.default_account
		FROM `tabPOS Payment Method` ppm
		INNER JOIN `tabPOS Profile` pp ON ppm.parent = pp.name
		WHERE ppm.mode_of_payment = %s
		  AND pp.company = %s
		  AND ppm.default_account IS NOT NULL
		  AND ppm.default_account != ''
		LIMIT 1
		""",
		(mode_of_payment, company),
	)
	if account_rows and account_rows[0][0]:
		return account_rows[0][0]

	frappe.throw(
		_(
			"Please set default Cash account in Mode of Payment {0} "
			"for company {1} before recording POS expenses."
		).format(frappe.bold(mode_of_payment), frappe.bold(company)),
		title=_("Missing Payment Account"),
	)


def get_cash_payment_methods(pos_profile):
	"""Return POS Profile payment methods whose ledger is a Cash account."""
	from pos_next.api.pos_profile import get_payment_methods

	methods = get_payment_methods(pos_profile) or []
	return [method for method in methods if (method.get("account_type") or "") == "Cash"]


def get_active_employees(company):
	"""Return active employees for the expense dialog.

	Intentional permission bypass: POS cashiers may lack Employee read permission.
	Only Active employees for the shift company are returned, capped at
	EMPLOYEE_PAGE_LENGTH. See module docstring.
	"""
	filters = {"status": "Active"}
	if company:
		filters["company"] = company

	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name"],
		order_by="employee_name asc",
		limit_page_length=EMPLOYEE_PAGE_LENGTH,
		# Cashiers often cannot read Employee; gated by open-shift ownership upstream.
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


def get_expense_accounts(company, txt=None, limit=None):
	"""Return expense ledger accounts for the company.

	Intentional permission bypass: POS cashiers may lack Account read permission.
	Results are capped (default EXPENSE_ACCOUNT_PAGE_LENGTH) and optionally
	filtered by a search term — callers should use search_expense_accounts for
	dialog search rather than shipping the whole chart.
	"""
	limit = EXPENSE_ACCOUNT_PAGE_LENGTH if limit is None else cint(limit)
	filters = {
		"company": company,
		"is_group": 0,
		"disabled": 0,
	}
	or_filters = [
		["account_type", "=", "Expense"],
		["root_type", "=", "Expense"],
	]

	txt = (txt or "").strip()
	if txt:
		# Narrow by name / account_name while keeping expense-type filter.
		# db.sql bypasses DocType permissions (same intentional till access as get_all below).
		return frappe.db.sql(
			"""
			SELECT name, account_name
			FROM `tabAccount`
			WHERE company = %(company)s
			  AND is_group = 0
			  AND disabled = 0
			  AND (account_type = 'Expense' OR root_type = 'Expense')
			  AND (name LIKE %(txt)s OR account_name LIKE %(txt)s)
			ORDER BY name
			LIMIT {limit}
			""".format(limit=cint(limit)),
			{
				"company": company,
				"txt": f"%{txt}%",
			},
			as_dict=True,
		)

	return frappe.get_all(
		"Account",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "account_name"],
		order_by="name",
		limit_page_length=limit,
		# Cashiers often cannot read Account; gated by open-shift ownership upstream.
		ignore_permissions=True,
	)


def _shift_posting_date(period_start_date):
	"""Post expenses to the shift's start date so overnight shifts stay on one GL day."""
	if period_start_date:
		return getdate(period_start_date)
	return getdate(today())


def _account_row_amounts(account, amount, company, posting_date, is_debit):
	"""Build JE account row amount fields with explicit exchange rate and base amounts.

	`amount` is treated as company-currency value (same basis as the shift expense
	limit). Foreign-currency ledgers receive the converted account-currency amount.
	"""
	from erpnext.accounts.utils import get_account_currency
	from erpnext.setup.utils import get_exchange_rate

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	account_currency = get_account_currency(account) or company_currency
	base_amount = flt(amount)

	if account_currency == company_currency:
		exchange_rate = 1.0
		amount_in_account_currency = base_amount
	else:
		exchange_rate = flt(get_exchange_rate(account_currency, company_currency, posting_date))
		if not exchange_rate:
			frappe.throw(
				_("Could not determine exchange rate from {0} to {1} on {2}").format(
					account_currency, company_currency, posting_date
				)
			)
		amount_in_account_currency = flt(base_amount / exchange_rate)

	row = {
		"account": account,
		"account_currency": account_currency,
		"exchange_rate": exchange_rate,
	}
	if is_debit:
		row.update(
			{
				"debit": base_amount,
				"credit": 0,
				"debit_in_account_currency": amount_in_account_currency,
				"credit_in_account_currency": 0,
			}
		)
	else:
		row.update(
			{
				"debit": 0,
				"credit": base_amount,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": amount_in_account_currency,
			}
		)
	return row


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
	period_start_date=None,
):
	user_remark = remarks or _("POS Expense for shift {0}").format(pos_opening_shift)
	expense_account = _ensure_account_name(expense_account, _("Expense Account"))
	payment_account = _ensure_account_name(payment_account, _("Payment Account"))
	posting_date = _shift_posting_date(period_start_date)
	base_amount = flt(amount)

	expense_amounts = _account_row_amounts(
		expense_account, base_amount, company, posting_date, is_debit=True
	)
	payment_amounts = _account_row_amounts(
		payment_account, base_amount, company, posting_date, is_debit=False
	)
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	multi_currency = int(
		expense_amounts["account_currency"] != company_currency
		or payment_amounts["account_currency"] != company_currency
	)

	jv_doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": posting_date,
			"company": company,
			"multi_currency": multi_currency,
			"user_remark": user_remark,
			"posa_is_pos_expense": 1,
			"posa_pos_opening_shift": pos_opening_shift,
			"posa_pos_profile": pos_profile,
			"posa_expense_account": expense_account,
			"posa_expense_amount": base_amount,
			"posa_expense_mode_of_payment": mode_of_payment,
			"posa_expense_employee": employee,
		}
	)

	expense_row = jv_doc.append("accounts", {})
	expense_row.update(expense_amounts)
	expense_row.cost_center = cost_center

	payment_row = jv_doc.append("accounts", {})
	payment_row.update(payment_amounts)
	payment_row.cost_center = cost_center

	jv_doc.flags.ignore_permissions = True
	jv_doc.insert()
	jv_doc.submit()

	return jv_doc.name


def get_pos_expenses(pos_opening_shift):
	"""Return submitted POS expense Journal Entries for a shift.

	Amount comes from Journal Entry Account credit rows (company currency),
	not the independent posa_expense_amount custom field.
	"""
	if not pos_opening_shift:
		return []

	expenses = frappe.db.sql(
		"""
		SELECT
			je.name,
			je.posa_expense_account,
			COALESCE(SUM(jea.credit), 0) AS amount,
			je.posa_expense_employee,
			je.posa_expense_mode_of_payment,
			je.user_remark
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.posa_is_pos_expense = 1
		  AND je.posa_pos_opening_shift = %(shift)s
		  AND je.docstatus = 1
		  AND jea.credit > 0
		GROUP BY je.name
		ORDER BY je.creation ASC
		""",
		{"shift": pos_opening_shift},
		as_dict=True,
	)

	return [
		frappe._dict(
			name=expense.name,
			journal_entry=expense.name,
			expense_account=expense.posa_expense_account,
			amount=flt(expense.amount),
			employee=expense.posa_expense_employee or "",
			remarks=(expense.user_remark or "").strip(),
			mode_of_payment=expense.posa_expense_mode_of_payment,
		)
		for expense in expenses
	]
