# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Manager Approval APIs

This module provides functionality for manager-level approvals
for high-value transactions like cash refunds and discounts.
"""

import frappe
from frappe import _
from frappe.utils import now


@frappe.whitelist()
def verify_manager_approval(username, password, approval_type, amount):
	"""
	Verify that a user with manager/admin role can approve high-value transactions.

	This function validates:
	1. User exists and is enabled
	2. Password is correct
	3. User has required role (POS Manager or System Manager)
	4. Logs the approval action

	Args:
		username: Username to verify
		password: User's password (plain text - should be HTTPS only)
		approval_type: Type of approval needed ("Cash Refund", "Discount", etc.)
		amount: Amount being approved

	Returns:
		dict: {
			success: bool,
			message: str,
			manager: str (username if successful),
			timestamp: datetime
		}

	Raises:
		ValidationError: If credentials are invalid or insufficient permissions
	"""

	if not username or not password:
		return {
			"success": False,
			"message": _("Username and password are required"),
		}

	# Check if user exists
	user = frappe.db.get_value(
		"User",
		username,
		["name", "enabled", "first_name"],
		as_dict=True,
	)

	if not user:
		frappe.log_error(
			f"Manager approval failed: User {username} not found",
			"Manager Approval Error",
		)
		return {
			"success": False,
			"message": _("Invalid username or password"),
		}
	

	# Check if user is enabled
	if not user.get("enabled"):
		frappe.log_error(
			f"Manager approval failed: User {username} is disabled",
			"Manager Approval Error",
		)
		return {
			"success": False,
			"message": _("User is disabled"),
		}

	# Verify password using Frappe's built-in method
	try:
		from frappe.utils.password import check_password
		# check_password raises an exception if password is incorrect
		check_password(username, password)
	except Exception as error:
		frappe.log_error(
			f"Manager approval failed: Invalid password for user {username}",
			"Manager Approval Error",
		)
		return {
			"success": False,
			"message": _("Invalid username or password"),
		}

	# Check if user has required role
	user_roles = frappe.get_roles(username)
	required_roles = ["POS Manager", "System Manager", "Nexus POS Manager"]

	has_permission = any(role in user_roles for role in required_roles)

	if not has_permission:
		frappe.log_error(
			f"Manager approval failed: User {username} lacks required role. Has: {user_roles}",
			"Manager Approval Error",
		)
		return {
			"success": False,
			"message": _("Insufficient permissions for manager approval"),
		}

	# Log the approval action
	try:
		approval_log = frappe.get_doc(
			{
				"doctype": "Manager Approval Log",
				"user": frappe.session.user,  # Current user requesting approval
				"manager": username,  # Manager granting approval
				"approval_type": approval_type,
				"amount": amount,
				"status": "Approved",
				"timestamp": now(),
			}
		)
		approval_log.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as error:
		frappe.log_error(
			f"Error logging manager approval: {str(error)}",
			"Manager Approval Log Error",
		)
		# Don't fail approval if logging fails

	return {
		"success": True,
		"message": _("Approval granted"),
		"manager": user.get("first_name") or username,
		"timestamp": now(),
	}
