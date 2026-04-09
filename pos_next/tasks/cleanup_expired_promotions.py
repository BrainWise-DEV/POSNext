# -*- coding: utf-8 -*-
# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

"""Scheduled tasks for POS Next."""

import frappe
from frappe.utils import nowdate, getdate


def disable_expired_pricing_rules():
	"""
	Automatically disable Pricing Rules that have passed their valid_upto date.
	Runs daily to clean up expired pricing rules.
	"""
	try:
		today = nowdate()

		# Find all active pricing rules with expired valid_upto dates
		expired_rules = frappe.db.sql(
			"""
			SELECT name, title, valid_upto
			FROM `tabPricing Rule`
			WHERE disable = 0
				AND valid_upto IS NOT NULL
				AND valid_upto < %s
			""",
			(today,),
			as_dict=1
		)

		if not expired_rules:
			frappe.logger().info("No expired pricing rules found")
			return {
				"success": True,
				"disabled_count": 0,
				"message": "No expired pricing rules to disable"
			}

		disabled_count = 0
		errors = []

		for rule in expired_rules:
			try:
				# Use SQL update for better performance
				frappe.db.set_value(
					"Pricing Rule",
					rule.name,
					"disable",
					1,
					update_modified=True
				)
				disabled_count += 1

				frappe.logger().info(
					f"Disabled expired pricing rule: {rule.name} - {rule.title} "
					f"(expired: {rule.valid_upto})"
				)

			except Exception as e:
				error_msg = f"Failed to disable pricing rule {rule.name}: {str(e)}"
				frappe.logger().error(error_msg)
				errors.append(error_msg)

		# Commit all changes
		frappe.db.commit()

		# Log summary
		summary = f"Disabled {disabled_count} expired pricing rule(s)"
		if errors:
			summary += f" with {len(errors)} error(s)"

		frappe.logger().info(summary)

		return {
			"success": True,
			"disabled_count": disabled_count,
			"errors": errors,
			"message": summary
		}

	except Exception as e:
		frappe.log_error(
			title="Disable Expired Pricing Rules Error",
			message=frappe.get_traceback()
		)
		return {
			"success": False,
			"error": str(e)
		}


def disable_expired_promotional_schemes():
	"""
	Automatically disable Promotional Schemes that have passed their valid_upto date.
	Runs daily to clean up expired promotional schemes.
	"""
	try:
		# Check if Promotional Scheme doctype exists
		if not frappe.db.table_exists("Promotional Scheme"):
			frappe.logger().info("Promotional Scheme doctype does not exist, skipping...")
			return {
				"success": True,
				"disabled_count": 0,
				"message": "Promotional Scheme doctype not available"
			}

		today = nowdate()

		# Find all active promotional schemes with expired valid_upto dates
		expired_schemes = frappe.db.sql(
			"""
			SELECT name, valid_upto
			FROM `tabPromotional Scheme`
			WHERE disable = 0
				AND valid_upto IS NOT NULL
				AND valid_upto < %s
			""",
			(today,),
			as_dict=1
		)

		if not expired_schemes:
			frappe.logger().info("No expired promotional schemes found")
			return {
				"success": True,
				"disabled_count": 0,
				"message": "No expired promotional schemes to disable"
			}

		disabled_count = 0
		errors = []

		for scheme in expired_schemes:
			try:
				# Use SQL update for better performance
				frappe.db.set_value(
					"Promotional Scheme",
					scheme.name,
					"disable",
					1,
					update_modified=True
				)
				disabled_count += 1

				frappe.logger().info(
					f"Disabled expired promotional scheme: {scheme.name} "
					f"(expired: {scheme.valid_upto})"
				)

			except Exception as e:
				error_msg = f"Failed to disable promotional scheme {scheme.name}: {str(e)}"
				frappe.logger().error(error_msg)
				errors.append(error_msg)

		# Commit all changes
		frappe.db.commit()

		# Log summary
		summary = f"Disabled {disabled_count} expired promotional scheme(s)"
		if errors:
			summary += f" with {len(errors)} error(s)"

		frappe.logger().info(summary)

		return {
			"success": True,
			"disabled_count": disabled_count,
			"errors": errors,
			"message": summary
		}

	except Exception as e:
		frappe.log_error(
			title="Disable Expired Promotional Schemes Error",
			message=frappe.get_traceback()
		)
		return {
			"success": False,
			"error": str(e)
		}


def cleanup_expired_promotions():
	"""
	Master function that disables both expired pricing rules and promotional schemes.
	This is the main scheduled task that runs daily.
	"""
	frappe.logger().info("Starting cleanup of expired promotions...")

	# Disable expired pricing rules
	pricing_result = disable_expired_pricing_rules()

	# Disable expired promotional schemes
	schemes_result = disable_expired_promotional_schemes()

	# Summary log
	total_disabled = (
		pricing_result.get("disabled_count", 0) +
		schemes_result.get("disabled_count", 0)
	)

	frappe.logger().info(
		f"Cleanup completed: {total_disabled} expired promotion(s) disabled"
	)

	return {
		"success": True,
		"pricing_rules": pricing_result,
		"promotional_schemes": schemes_result,
		"total_disabled": total_disabled
	}
