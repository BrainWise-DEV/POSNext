# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Audit trail for the authorization gate.

Rows are written server-side with ``ignore_permissions=True``; the DocType grants no
create/write/delete to anyone. An editable audit log is not an audit log.

Denials raised from ``before_submit`` need care: :func:`frappe.throw` rolls the request
back, which would take a freshly inserted log row with it. Those callers pass
``survive_rollback=True``, which defers the insert onto ``frappe.db.after_rollback`` —
that callback runs *after* Frappe has rolled back and opened a fresh transaction, so the
row lands cleanly without carrying any partial document state with it.
"""

import frappe
from frappe.utils import now_datetime

LOG_DOCTYPE = "POS Authorization Log"

RESULT_GRANTED = "Granted"
RESULT_INVALID_PIN = "Invalid PIN"
RESULT_NO_PIN = "No PIN Set"
RESULT_NOT_AUTHORIZED = "Not Authorized"
RESULT_LOCKED_OUT = "Locked Out"
RESULT_DENIED = "Denied"
RESULT_PIN_SET = "PIN Set"


def record(
	*,
	action: str | None = None,
	approver: str | None = None,
	result: str | None = None,
	reference: str | None = None,
	pos_profile: str | None = None,
	requested_by: str | None = None,
	survive_rollback: bool = False,
) -> None:
	"""Write one audit row. Never raises — auditing must not break the till."""
	payload = {
		"doctype": LOG_DOCTYPE,
		"timestamp": now_datetime(),
		"action": action,
		"requested_by": requested_by or frappe.session.user,
		"approver": approver,
		"result": result,
		"reference": reference,
		"pos_profile": pos_profile,
	}

	if survive_rollback:
		frappe.db.after_rollback.add(lambda: _insert(payload, commit=True))
		return

	_insert(payload)


def _insert(payload: dict, commit: bool = False) -> None:
	try:
		frappe.get_doc(payload).insert(ignore_permissions=True)
		if commit:
			frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "POS Authorization Log Error")
