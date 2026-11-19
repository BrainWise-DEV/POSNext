# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for pos_next.authorization.log — the audit trail."""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.authorization import log
from pos_next.authorization.tests.helpers import DUMMY_ACTION


class TestAuditLog(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_log_rows_are_written(self):
		# Not a row-count delta: log.record(survive_rollback=True) deliberately escapes
		# the test framework's own rollback (see log.py — that's what makes a denial
		# audit-proof even though the enclosing invoice submission rolls back), so other
		# tests in this same run can legitimately add rows around this one. Look for the
		# specific row instead of counting the whole table.
		#
		# approver=Administrator, not MANAGER: this class is intentionally self-contained
		# and creates no fixture users, and approver is a Link to User — a nonexistent
		# approver would fail Link validation inside log._insert(), which swallows every
		# exception ("auditing must not break the till"), so the row would silently never
		# be written and this assertion would fail for a completely unrelated reason.
		marker = frappe.generate_hash(length=8)
		log.record(action=DUMMY_ACTION, approver="Administrator", result=log.RESULT_GRANTED, reference=marker)
		self.assertTrue(frappe.db.exists(log.LOG_DOCTYPE, {"reference": marker, "approver": "Administrator"}))

	def test_log_is_not_writable_by_pos_roles(self):
		"""An editable audit log is not an audit log."""
		meta = frappe.get_meta(log.LOG_DOCTYPE)
		for perm in meta.permissions:
			self.assertFalse(perm.get("create"), f"{perm.role} must not create log rows")
			self.assertFalse(perm.get("write"), f"{perm.role} must not edit log rows")
			self.assertFalse(perm.get("delete"), f"{perm.role} must not delete log rows")

	def test_rule_is_system_manager_only(self):
		"""If a cashier could edit rules, they could switch off their own gate."""
		meta = frappe.get_meta("POS Authorization Rule")
		roles = {perm.role for perm in meta.permissions}
		self.assertEqual(roles, {"System Manager"})
