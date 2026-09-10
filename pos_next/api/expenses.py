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
still visible at the till. The same pattern applies to Journal Entry insert/cancel
and File attach for POS expenses (cashiers usually lack JE write). Revisit if a
narrower Employee/Account/Journal Entry role is introduced.
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
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	maximum_expense_amount = flt(
		frappe.db.get_value("POS Profile", pos_profile, "posa_maximum_expense_amount")
	)
	shift_expense_total = get_shift_expense_total(pos_opening_shift)
	remaining_expense_amount = _get_remaining_shift_expense_amount(
		maximum_expense_amount, shift_expense_total
	)
	cancel_perms = get_pos_expense_cancel_permissions(pos_profile)

	from frappe.core.api.file import get_max_file_size

	return {
		"expense_accounts": get_expense_accounts(company, pos_profile=pos_profile),
		"payment_methods": get_cash_payment_methods(pos_profile),
		"employees": get_active_employees(company),
		"expenses": get_pos_expenses(pos_opening_shift),
		"company_currency": company_currency,
		"maximum_expense_amount": maximum_expense_amount,
		"shift_expense_total": shift_expense_total,
		"remaining_expense_amount": remaining_expense_amount,
		"allow_cancel": cancel_perms["allow_cancel"],
		"can_cancel": cancel_perms["can_cancel"],
		"max_file_size": get_max_file_size(),
	}


@frappe.whitelist()
def search_expense_accounts(pos_profile, pos_opening_shift, txt=None):
	"""Server-side expense account search for the POS dialog."""
	validate_pos_expense_enabled(pos_profile)
	shift = validate_open_shift(pos_opening_shift, pos_profile)
	return get_expense_accounts(shift.company, txt=txt, pos_profile=pos_profile)


PENDING_EXPENSE_TIMEOUT_MINUTES = 5


@frappe.whitelist()
def create_pos_expense(
	pos_opening_shift,
	pos_profile,
	expense_account,
	amount,
	mode_of_payment,
	employee=None,
	remarks=None,
	offline_id=None,
):
	"""Create and submit a Journal Entry for a POS expense.

	``amount`` is company currency (Company.default_currency), matching
	``posa_maximum_expense_amount`` and the JE debit/credit columns.
	``remarks`` is required.

	When ``offline_id`` is set, uses Offline Expense Sync reservation/dedup
	so reconnect retries do not create a second Journal Entry.
	"""
	amount = flt(amount)
	remarks = (remarks or "").strip()
	expense_account = _coerce_account_name(expense_account)
	offline_id = cstr(offline_id).strip() or None
	sync_record_name = None

	if not remarks:
		frappe.throw(_("Remarks are required"))

	if offline_id:
		dedup = _ensure_offline_expense_uniqueness(
			offline_id=offline_id,
			pos_profile=pos_profile,
			pos_opening_shift=pos_opening_shift,
		)
		if dedup.get("already_synced"):
			return dedup["expense_data"]
		sync_record_name = dedup.get("sync_record_name")

	try:
		validate_pos_expense_enabled(pos_profile)
		shift = validate_open_shift(pos_opening_shift, pos_profile)
		validate_expense_amount(amount, pos_profile, pos_opening_shift)
		validate_expense_account(expense_account, shift.company, pos_profile=pos_profile)
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

		if offline_id:
			_complete_offline_expense_sync(sync_record_name, journal_entry_name)

		result = {
			"name": journal_entry_name,
			"journal_entry": journal_entry_name,
			"amount": amount,
			"message": _("POS Expense recorded in Journal Entry {0}").format(journal_entry_name),
		}
		if offline_id:
			result["offline_id"] = offline_id
		return result
	except Exception:
		if sync_record_name:
			_cleanup_failed_offline_expense_sync(sync_record_name)
		raise


@frappe.whitelist()
def check_offline_expense_synced(offline_id):
	"""Return whether an offline expense id already maps to a submitted JE."""
	from pos_next.pos_next.doctype.offline_expense_sync.offline_expense_sync import (
		OfflineExpenseSync,
	)

	result = OfflineExpenseSync.is_synced(offline_id)
	if not result or not isinstance(result, dict):
		return {"synced": False, "journal_entry": None, "status": None}

	if result.get("synced") and result.get("journal_entry"):
		if frappe.db.exists("Journal Entry", result["journal_entry"]):
			docstatus = frappe.db.get_value("Journal Entry", result["journal_entry"], "docstatus")
			if docstatus == 1:
				return result
		return {"synced": False, "journal_entry": None, "status": None}

	return result


def _is_pending_expense_expired(modified_time):
	if not modified_time:
		return True
	age_minutes = (frappe.utils.now_datetime() - modified_time).total_seconds() / 60
	return age_minutes > PENDING_EXPENSE_TIMEOUT_MINUTES


def _reuse_offline_expense_sync_record(sync_record_name):
	sync_doc = frappe.get_doc("Offline Expense Sync", sync_record_name)
	sync_doc.status = "Pending"
	sync_doc.synced_at = None
	sync_doc.flags.ignore_permissions = True
	sync_doc.save()
	return {"already_synced": False, "sync_record_name": sync_record_name}


def _ensure_offline_expense_uniqueness(offline_id, pos_profile=None, pos_opening_shift=None):
	"""Reserve or return an Offline Expense Sync row (invoice-pattern dedup)."""
	existing_sync = frappe.db.get_value(
		"Offline Expense Sync",
		{"offline_id": offline_id},
		["name", "journal_entry", "status", "modified"],
		as_dict=True,
		for_update=True,
	)

	if existing_sync:
		sync_status = existing_sync.get("status")
		sync_record_name = existing_sync.name

		if sync_status == "Pending":
			# If a JE was linked before status flipped (partial write), return it.
			if existing_sync.journal_entry and frappe.db.exists(
				"Journal Entry", existing_sync.journal_entry
			):
				je = frappe.get_doc("Journal Entry", existing_sync.journal_entry)
				if je.docstatus == 1:
					_complete_offline_expense_sync(sync_record_name, je.name)
					return {
						"already_synced": True,
						"expense_data": {
							"name": je.name,
							"journal_entry": je.name,
							"amount": flt(je.posa_expense_amount),
							"message": _("POS Expense already recorded in Journal Entry {0}").format(
								je.name
							),
							"duplicate_prevented": True,
							"offline_id": offline_id,
						},
					}
			if _is_pending_expense_expired(existing_sync.get("modified")):
				return _reuse_offline_expense_sync_record(sync_record_name)
			frappe.throw(
				_("This expense is currently being processed. Please wait."),
				exc=frappe.ValidationError,
				title="SYNC_IN_PROGRESS",
			)

		if sync_status == "Failed":
			return _reuse_offline_expense_sync_record(sync_record_name)

		if sync_status == "Synced" and existing_sync.journal_entry:
			if frappe.db.exists("Journal Entry", existing_sync.journal_entry):
				je = frappe.get_doc("Journal Entry", existing_sync.journal_entry)
				if je.docstatus == 1:
					return {
						"already_synced": True,
						"expense_data": {
							"name": je.name,
							"journal_entry": je.name,
							"amount": flt(je.posa_expense_amount),
							"message": _("POS Expense already recorded in Journal Entry {0}").format(
								je.name
							),
							"duplicate_prevented": True,
							"offline_id": offline_id,
						},
					}
			return _reuse_offline_expense_sync_record(sync_record_name)

		return _reuse_offline_expense_sync_record(sync_record_name)

	try:
		pending_sync = frappe.get_doc(
			{
				"doctype": "Offline Expense Sync",
				"offline_id": offline_id,
				"journal_entry": "",
				"pos_profile": pos_profile,
				"pos_opening_shift": pos_opening_shift,
				"status": "Pending",
			}
		)
		pending_sync.flags.ignore_permissions = True
		pending_sync.insert()
		return {"already_synced": False, "sync_record_name": pending_sync.name}
	except frappe.DuplicateEntryError:
		return _ensure_offline_expense_uniqueness(
			offline_id, pos_profile, pos_opening_shift
		)


def _complete_offline_expense_sync(sync_record_name, journal_entry_name):
	if not sync_record_name:
		return
	try:
		sync_doc = frappe.get_doc("Offline Expense Sync", sync_record_name)
		sync_doc.journal_entry = journal_entry_name
		sync_doc.status = "Synced"
		sync_doc.synced_at = frappe.utils.now_datetime()
		sync_doc.flags.ignore_permissions = True
		sync_doc.save()
	except Exception as error:
		frappe.log_error(
			title="Offline Expense Sync Completion Error",
			message=(
				f"Failed to complete sync record {sync_record_name} "
				f"for Journal Entry {journal_entry_name}: {error!s}"
			),
		)
		# Re-raise so the request fails and the JE insert/submit rolls back with
		# the same transaction — avoids orphan JEs with a stuck Pending sync row.
		raise


def _cleanup_failed_offline_expense_sync(sync_record_name):
	if not sync_record_name:
		return
	try:
		sync_doc = frappe.get_doc("Offline Expense Sync", sync_record_name)
		sync_doc.status = "Failed"
		sync_doc.synced_at = frappe.utils.now_datetime()
		sync_doc.flags.ignore_permissions = True
		sync_doc.save()
	except Exception as error:
		frappe.log_error(
			title="Offline Expense Sync Cleanup Error",
			message=f"Failed to mark sync record {sync_record_name} as failed: {error!s}",
		)


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

	je = _get_submitted_pos_expense_for_shift(journal_entry, pos_opening_shift, pos_profile)
	validate_pos_expense_cancel_permission(pos_profile, je.owner, journal_entry)

	jv_doc = frappe.get_doc("Journal Entry", journal_entry)
	jv_doc.flags.ignore_permissions = True
	jv_doc.cancel()

	return {
		"name": jv_doc.name,
		"journal_entry": jv_doc.name,
		"message": _("POS Expense {0} cancelled").format(jv_doc.name),
	}


@frappe.whitelist()
def attach_pos_expense_file(journal_entry, pos_opening_shift, pos_profile):
	"""Attach the multipart ``file`` in the request to a POS expense Journal Entry.

	Cashiers typically lack Journal Entry write permission, so ``upload_file`` fails.
	This endpoint mirrors create/cancel: prove open-shift ownership and POS-expense
	markers, then insert the File with ``ignore_permissions``.

	File size is capped with ``get_max_file_size()`` before buffering the full body.
	Idempotent for the same filename + size on the same Journal Entry.
	"""
	if not journal_entry:
		frappe.throw(_("Journal Entry is required"))

	validate_pos_expense_enabled(pos_profile)
	validate_open_shift(pos_opening_shift, pos_profile)
	_get_submitted_pos_expense_for_shift(journal_entry, pos_opening_shift, pos_profile)

	files = getattr(frappe.request, "files", None) or {}
	if "file" not in files:
		frappe.throw(_("File is required"))

	uploaded = files["file"]
	filename = (getattr(uploaded, "filename", None) or "").strip()
	if not filename or not hasattr(uploaded, "stream"):
		frappe.throw(_("File is required"))

	_validate_expense_attachment_filename(filename)
	content = _read_uploaded_file_capped(uploaded.stream)
	if not content:
		frappe.throw(_("File is required"))

	# Retry after timeout: same name+size on this JE is treated as already attached.
	existing = frappe.db.get_value(
		"File",
		{
			"attached_to_doctype": "Journal Entry",
			"attached_to_name": journal_entry,
			"file_name": filename,
		},
		["name", "file_url", "file_size"],
		as_dict=True,
	)
	if existing and cint(existing.file_size) == len(content):
		return {
			"name": existing.name,
			"file_url": existing.file_url,
			"file_name": filename,
			"journal_entry": journal_entry,
			"already_attached": True,
		}

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"is_private": 1,
			"folder": "Home/Attachments",
			"attached_to_doctype": "Journal Entry",
			"attached_to_name": journal_entry,
			"content": content,
		}
	)
	file_doc.flags.ignore_permissions = True
	file_doc.insert()

	return {
		"name": file_doc.name,
		"file_url": file_doc.file_url,
		"file_name": file_doc.file_name,
		"journal_entry": journal_entry,
	}


EXPENSE_ATTACHMENT_EXTENSIONS = (
	".jpg",
	".jpeg",
	".png",
	".gif",
	".pdf",
	".txt",
	".csv",
	".doc",
	".docx",
	".xls",
	".xlsx",
	".odt",
	".ods",
)


def _validate_expense_attachment_filename(filename):
	lower = filename.lower()
	if not any(lower.endswith(ext) for ext in EXPENSE_ATTACHMENT_EXTENSIONS):
		frappe.throw(
			_("File type not allowed. Use JPG, PNG, GIF, PDF, TXT, CSV, or Office documents."),
			title=_("Invalid Attachment"),
		)


def _read_uploaded_file_capped(stream, chunk_size=1024 * 1024):
	"""Read upload stream up to system max file size; refuse oversized bodies early."""
	from frappe.core.api.file import get_max_file_size

	max_size = get_max_file_size()
	content_length = frappe.get_request_header("Content-Length")
	if content_length and cint(content_length) > max_size:
		frappe.throw(
			_("File size exceeded the maximum allowed size of {0} MB").format(
				max_size / 1048576
			),
			title=_("File Too Large"),
		)

	chunks = []
	total = 0
	while True:
		chunk = stream.read(chunk_size)
		if not chunk:
			break
		total += len(chunk)
		if total > max_size:
			frappe.throw(
				_("File size exceeded the maximum allowed size of {0} MB").format(
					max_size / 1048576
				),
				title=_("File Too Large"),
			)
		chunks.append(chunk)

	return b"".join(chunks) if chunks else b""


def _get_submitted_pos_expense_for_shift(journal_entry, pos_opening_shift, pos_profile):
	"""Return JE row if it is a submitted POS expense for this open shift/profile."""
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
		frappe.throw(_("Only submitted POS expenses are allowed"))

	return je


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
	"""Validate amount and shift limit in company currency.

	The cashier-typed amount, ``posa_maximum_expense_amount``, and JE debit/credit
	all share Company.default_currency — not POS Profile.currency.
	"""
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	profile = frappe.db.get_value(
		"POS Profile",
		pos_profile,
		["posa_maximum_expense_amount", "company"],
		as_dict=True,
	)
	maximum_amount = flt(profile.posa_maximum_expense_amount if profile else 0)
	if maximum_amount <= 0:
		frappe.throw(
			_(
				"Maximum Expense Amount is not configured on POS Profile {0}. "
				"Set a positive limit before recording expenses."
			).format(pos_profile),
			title=_("Expense Limit Not Configured"),
		)

	company_currency = None
	if profile and profile.company:
		company_currency = frappe.get_cached_value(
			"Company", profile.company, "default_currency"
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
		currency_df = {"fieldtype": "Currency", "options": company_currency}
		frappe.throw(
			_(
				"This expense would exceed the shift expense limit of {0}. "
				"Expenses recorded this shift: {1}. Remaining allowance: {2}"
			).format(
				frappe.format_value(maximum_amount, currency_df),
				frappe.format_value(shift_total, currency_df),
				frappe.format_value(remaining, currency_df),
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


def validate_expense_account(expense_account, company, pos_profile=None):
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

	allowed = get_allowed_expense_account_names(pos_profile) if pos_profile else None
	if allowed is not None and expense_account not in allowed:
		frappe.throw(
			_("Expense Account {0} is not allowed for POS Profile {1}").format(
				frappe.bold(expense_account),
				frappe.bold(pos_profile),
			)
		)


def validate_pos_expense_cancel_permission(pos_profile, je_owner, journal_entry):
	"""Enforce Allow Cancel + optional Cancel Roles, else owner / JE Cancel perm.

	Cancel is only available on the caller's own open shift (see validate_open_shift).
	Cancel Roles therefore filter which roles on that shift may cancel — they do not
	grant cross-shift supervisor cancel from POS.
	"""
	perms = get_pos_expense_cancel_permissions(pos_profile)
	if not perms["allow_cancel"]:
		frappe.throw(_("Cancelling POS expenses is not allowed for this POS Profile"))

	cancel_roles = get_pos_expense_cancel_roles(pos_profile)
	if cancel_roles:
		if not set(frappe.get_roles()).intersection(cancel_roles):
			frappe.throw(_("You are not allowed to cancel POS expenses"))
		return

	if je_owner != frappe.session.user and not frappe.has_permission(
		"Journal Entry", "cancel", doc=journal_entry
	):
		frappe.throw(_("You can only cancel POS expenses you created"))


def get_pos_expense_cancel_permissions(pos_profile):
	"""Return whether cancel is enabled on the profile and allowed for the current user.

	When Allow Cancel is on and Cancel Roles are empty, ``can_cancel`` is True for the
	dialog: every shift owner sees Cancel, and cancel-time still enforces JE owner
	(or Journal Entry Cancel permission). Configure Cancel Roles to restrict further.
	"""
	allow_cancel = cint(
		frappe.db.get_value("POS Profile", pos_profile, "posa_allow_cancel_pos_expense")
	)
	if not allow_cancel:
		return {"allow_cancel": 0, "can_cancel": 0}

	cancel_roles = get_pos_expense_cancel_roles(pos_profile)
	if cancel_roles:
		can_cancel = 1 if set(frappe.get_roles()).intersection(cancel_roles) else 0
	else:
		can_cancel = 1

	return {"allow_cancel": 1, "can_cancel": can_cancel}


def get_pos_expense_cancel_roles(pos_profile):
	if not pos_profile:
		return []
	return frappe.get_all(
		"POS Expense Cancel Role",
		filters={"parent": pos_profile, "parenttype": "POS Profile"},
		pluck="role",
	)


def get_allowed_expense_account_names(pos_profile):
	"""Return allowed account names, or None when the profile has no whitelist."""
	if not pos_profile:
		return None
	accounts = frappe.get_all(
		"POS Profile Expense Account",
		filters={"parent": pos_profile, "parenttype": "POS Profile"},
		pluck="account",
	)
	accounts = [name for name in accounts if name]
	return accounts or None


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

	payment_account = _resolve_payment_account(mode_of_payment, company)
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


def _resolve_payment_account(mode_of_payment, company):
	"""Return the configured cash/bank account for a mode of payment.

	Only uses Mode of Payment Account. POS Payment Method has no default_account
	field (ERPNext v15), and get_cash_payment_methods already filters modes via
	that join — so profile fallbacks here can only fire on the misconfig path.
	Does not fall back to an arbitrary company Cash/Bank ledger.
	"""
	account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)
	if account:
		return account

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


def get_expense_accounts(company, txt=None, limit=None, pos_profile=None):
	"""Return expense ledger accounts for the company.

	Intentional permission bypass: POS cashiers may lack Account read permission.
	Results are capped (default EXPENSE_ACCOUNT_PAGE_LENGTH) and optionally
	filtered by a search term — callers should use search_expense_accounts for
	dialog search rather than shipping the whole chart.

	When ``pos_profile`` has Allowed Expense Accounts rows, results are restricted
	to that whitelist (empty table keeps all expense ledgers).
	"""
	limit = EXPENSE_ACCOUNT_PAGE_LENGTH if limit is None else cint(limit)
	allowed = get_allowed_expense_account_names(pos_profile) if pos_profile else None

	txt = (txt or "").strip()
	if txt or allowed is not None:
		# db.sql bypasses DocType permissions (same intentional till access as get_all below).
		params = {
			"company": company,
			"txt": f"%{txt}%",
		}
		allowed_clause = ""
		if allowed is not None:
			allowed_clause = "AND name IN %(allowed)s"
			params["allowed"] = tuple(allowed)

		txt_clause = ""
		if txt:
			txt_clause = "AND (name LIKE %(txt)s OR account_name LIKE %(txt)s)"

		return frappe.db.sql(
			f"""
			SELECT name, account_name
			FROM `tabAccount`
			WHERE company = %(company)s
			  AND is_group = 0
			  AND disabled = 0
			  AND (account_type = 'Expense' OR root_type = 'Expense')
			  {allowed_clause}
			  {txt_clause}
			ORDER BY name
			LIMIT {cint(limit)}
			""",
			params,
			as_dict=True,
		)

	filters = {
		"company": company,
		"is_group": 0,
		"disabled": 0,
	}
	or_filters = [
		["account_type", "=", "Expense"],
		["root_type", "=", "Expense"],
	]

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
	user_remark = remarks
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
