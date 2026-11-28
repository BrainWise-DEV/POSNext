# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Classify database errors by their real MariaDB error number, and never swallow lock errors.

Why this matters for checkout
-----------------------------
The two lock failures behave very differently:

* **1213 deadlock** (``ER_LOCK_DEADLOCK``): InnoDB found a cycle and rolled back the *whole
  transaction* of the victim. Frappe raises ``QueryDeadlockError``. Frappe also raises
  ``QueryDeadlockError`` for **1020** (``ER_CHECKREAD``, a snapshot-isolation conflict on newer
  MariaDB), so the exception type alone does not prove it was a real deadlock.
* **1205 lock wait timeout** (``ER_LOCK_WAIT_TIMEOUT``): the statement waited longer than
  ``innodb_lock_wait_timeout`` (row/table locks) or ``lock_wait_timeout`` (metadata locks). Only
  the *statement* is rolled back unless ``innodb_rollback_on_timeout`` is on; the transaction
  stays open with everything done before it. Frappe raises ``QueryTimeoutError``.

In both cases the request is only safe if the exception reaches Frappe's request handler, which
rolls the whole transaction back for POST requests. Code that catches ``Exception`` and carries on
would continue after a 1213 in a brand new transaction (the work before it is gone) and after a
1205 with a half-done one. ``reraise_if_lock_error`` is called first in such handlers so a lock
error is never swallowed on the checkout path.
"""

import frappe

ER_LOCK_DEADLOCK = 1213
ER_CHECKREAD = 1020
ER_LOCK_WAIT_TIMEOUT = 1205
ER_QUERY_TIMEOUT = (3024, 1969)  # max_statement_time exceeded (MySQL / MariaDB)
ER_CONNECTION_LOST = (2006, 2013, 2003, 2055)

LOCK_ERRORS = (frappe.QueryDeadlockError, frappe.QueryTimeoutError)


def errno_of(exc: BaseException | None) -> int | None:
	"""The MariaDB error number behind an exception, following Frappe's wrapping."""
	seen = 0
	while exc is not None and seen < 6:
		args = getattr(exc, "args", None) or ()
		if args and isinstance(args[0], int):
			return args[0]
		# frappe.QueryDeadlockError(pymysql_error) keeps the driver error as args[0]
		if args and isinstance(args[0], BaseException):
			exc = args[0]
		else:
			exc = exc.__cause__
		seen += 1
	return None


def classify(exc: BaseException) -> dict:
	"""``{"kind", "errno"}`` with kind one of the values below; never raises."""
	errno = errno_of(exc)
	if errno == ER_LOCK_DEADLOCK:
		kind = "deadlock_1213"
	elif errno == ER_CHECKREAD:
		kind = "snapshot_conflict_1020"
	elif errno == ER_LOCK_WAIT_TIMEOUT:
		kind = "lock_wait_timeout_1205"
	elif errno in ER_QUERY_TIMEOUT:
		kind = "query_time_limit"
	elif errno in ER_CONNECTION_LOST:
		kind = "connection_lost"
	elif isinstance(exc, frappe.QueryDeadlockError):
		kind = "deadlock_unknown_errno"
	elif isinstance(exc, frappe.QueryTimeoutError):
		kind = "lock_wait_timeout_unknown_errno"
	else:
		kind = "other"
	return {"kind": kind, "errno": errno}


def is_lock_error(exc: BaseException) -> bool:
	return isinstance(exc, LOCK_ERRORS)


def reraise_if_lock_error(exc: BaseException) -> None:
	"""Call first inside a broad ``except Exception``: re-raises deadlocks and lock timeouts.

	Everything else is left to the caller's handling (log and carry on, as before).
	"""
	if is_lock_error(exc):
		raise exc
