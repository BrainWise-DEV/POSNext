# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

import ast
import pathlib
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import security

GUARD_NAMES = {"ensure_desk_user", "ensure_pos_user", "ensure_pos_supervisor"}


class TestSecurityGuards(FrappeTestCase):
	def test_ensure_desk_user_rejects_guest(self):
		with self.assertRaises(frappe.AuthenticationError):
			security.ensure_desk_user("Guest")

	def test_ensure_desk_user_allows_administrator(self):
		self.assertEqual(security.ensure_desk_user("Administrator"), "Administrator")

	def test_ensure_desk_user_rejects_portal_user(self):
		with patch.object(
			frappe.db,
			"get_value",
			return_value=frappe._dict(enabled=1, user_type="Website User"),
		):
			with self.assertRaises(frappe.PermissionError):
				security.ensure_desk_user("portal@example.com")

	def test_ensure_desk_user_rejects_disabled_user(self):
		with patch.object(
			frappe.db,
			"get_value",
			return_value=frappe._dict(enabled=0, user_type="System User"),
		):
			with self.assertRaises(frappe.PermissionError):
				security.ensure_desk_user("disabled@example.com")

	def test_ensure_desk_user_allows_enabled_system_user(self):
		with patch.object(
			frappe.db,
			"get_value",
			return_value=frappe._dict(enabled=1, user_type="System User"),
		):
			self.assertEqual(security.ensure_desk_user("cashier@example.com"), "cashier@example.com")

	def test_is_pos_supervisor_roles(self):
		self.assertTrue(security.is_pos_supervisor("Administrator"))
		self.assertFalse(security.is_pos_supervisor("Guest"))

		with patch("pos_next.api.security.frappe.get_roles", return_value=["Nexus POS Manager"]):
			self.assertTrue(security.is_pos_supervisor("mgr@example.com"))

		with patch("pos_next.api.security.frappe.get_roles", return_value=["System Manager"]):
			self.assertTrue(security.is_pos_supervisor("sys@example.com"))

		with patch("pos_next.api.security.frappe.get_roles", return_value=["POSNext Cashier"]):
			self.assertFalse(security.is_pos_supervisor("cashier@example.com"))

	def test_ensure_pos_supervisor_rejects_cashier(self):
		with (
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(enabled=1, user_type="System User"),
			),
			patch("pos_next.api.security.frappe.get_roles", return_value=["POSNext Cashier"]),
		):
			with self.assertRaises(frappe.PermissionError):
				security.ensure_pos_supervisor("cashier@example.com")

	def test_ensure_pos_user_requires_profile(self):
		with self.assertRaises(frappe.ValidationError):
			security.ensure_pos_user("", user="Administrator")

	def test_ensure_pos_user_allows_assigned_cashier(self):
		with (
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(enabled=1, user_type="System User"),
			),
			patch("pos_next.api.security.frappe.get_roles", return_value=["POSNext Cashier"]),
			patch.object(frappe.db, "exists", return_value="ROW-1") as mock_exists,
		):
			self.assertEqual(
				security.ensure_pos_user("Main POS", user="cashier@example.com"),
				"cashier@example.com",
			)
			mock_exists.assert_called_once_with(
				"POS Profile User", {"parent": "Main POS", "user": "cashier@example.com"}
			)

	def test_ensure_pos_user_rejects_unassigned_cashier(self):
		with (
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(enabled=1, user_type="System User"),
			),
			patch("pos_next.api.security.frappe.get_roles", return_value=["POSNext Cashier"]),
			patch.object(frappe.db, "exists", return_value=None),
		):
			with self.assertRaises(frappe.PermissionError):
				security.ensure_pos_user("Other POS", user="cashier@example.com")

	def test_ensure_pos_user_allows_supervisor_without_profile_assignment(self):
		with (
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(enabled=1, user_type="System User"),
			),
			patch("pos_next.api.security.frappe.get_roles", return_value=["Nexus POS Manager"]),
			patch.object(frappe.db, "exists", return_value=None),
		):
			self.assertEqual(
				security.ensure_pos_user("Any POS", user="manager@example.com"),
				"manager@example.com",
			)

	def test_all_non_guest_whitelisted_endpoints_have_security_guard(self):
		"""Regression guard: every non-guest @frappe.whitelist endpoint must call a security guard."""
		app_root = pathlib.Path(frappe.get_app_path("pos_next"))
		missing = []

		for path in sorted(app_root.rglob("*.py")):
			if "test_" in path.name or "__pycache__" in str(path) or path.name == "security.py":
				continue
			src = path.read_text()
			if "whitelist" not in src:
				continue
			tree = ast.parse(src)
			for node in ast.walk(tree):
				if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue
				is_whitelisted = False
				is_guest = False
				for dec in node.decorator_list:
					if isinstance(dec, ast.Call) and ast.unparse(dec.func).endswith("whitelist"):
						is_whitelisted = True
						for kw in dec.keywords:
							if (
								kw.arg == "allow_guest"
								and isinstance(kw.value, ast.Constant)
								and kw.value.value is True
							):
								is_guest = True
					elif isinstance(dec, ast.Attribute) and dec.attr == "whitelist":
						is_whitelisted = True

				if not is_whitelisted or is_guest:
					continue

				# First executable statement (after optional docstring) must invoke a guard before any try:
				body = node.body
				idx = 0
				if (
					body
					and isinstance(body[0], ast.Expr)
					and isinstance(body[0].value, ast.Constant)
					and isinstance(body[0].value.value, str)
				):
					idx = 1

				found_guard = False
				for stmt in body[idx : idx + 3]:
					if isinstance(stmt, ast.Try):
						break
					if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
						fn = stmt.value.func
						name = (
							fn.id
							if isinstance(fn, ast.Name)
							else (fn.attr if isinstance(fn, ast.Attribute) else None)
						)
						if name in GUARD_NAMES:
							found_guard = True
							break
					if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
						fn = stmt.value.func
						name = (
							fn.id
							if isinstance(fn, ast.Name)
							else (fn.attr if isinstance(fn, ast.Attribute) else None)
						)
						if name in GUARD_NAMES:
							found_guard = True
							break

				if not found_guard:
					missing.append(f"{path.relative_to(app_root)}:{node.lineno} {node.name}")

		self.assertEqual(missing, [], f"Whitelisted endpoints missing top-level security guard: {missing}")
