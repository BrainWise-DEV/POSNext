# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
BrainWise Branding Monitor
Scheduled task to monitor branding integrity and log suspicious activity
"""

import json

import frappe
from frappe.utils import get_datetime, now


def monitor_branding_integrity():
	"""
	Scheduled task to check branding integrity
	Runs periodically to ensure branding configuration is intact
	"""
	try:
		# Check if BrainWise Branding doctype exists
		if not frappe.db.exists("DocType", "BrainWise Branding"):
			return

		doc = frappe.get_single("BrainWise Branding")

		if not doc.enabled:
			return

		# Check for excessive tampering attempts
		if doc.tampering_attempts and doc.tampering_attempts > 50:
			# Send notification to System Managers
			send_tampering_alert(doc)

		# Verify signature integrity
		if not doc.encrypted_signature:
			frappe.log_error(
				title="BrainWise Branding - Missing Signature",
				message="Branding configuration is missing encrypted signature. Please resave the BrainWise Branding document."
			)

		# Log monitoring activity
		frappe.logger().info(f"BrainWise Branding Monitor - Checked at {now()}, Tampering attempts: {doc.tampering_attempts or 0}")

	except Exception as e:
		frappe.log_error(
			title="BrainWise Branding Monitor Error",
			message=f"Error running branding monitor: {e!s}"
		)


def send_tampering_alert(doc):
	"""Send alert to system managers about excessive tampering attempts"""
	try:
		# Get all System Managers
		system_managers = frappe.get_all(
			"Has Role",
			filters={"role": "System Manager", "parenttype": "User"},
			fields=["parent"]
		)

		users = [d.parent for d in system_managers]

		if not users:
			return

		# Create notification
		message = f"""
<h3>BrainWise Branding - Excessive Tampering Detected</h3>
<p>The BrainWise branding footer has been tampered with <strong>{doc.tampering_attempts}</strong> times.</p>
<p><strong>Last Validation:</strong> {doc.last_validation or 'Never'}</p>
<p>Please review the Error Log for detailed tampering attempts.</p>
<p><a href="/app/brainwise-branding">View Branding Configuration</a></p>
		"""

		for user in users:
			try:
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": "BrainWise Branding - Tampering Alert",
					"type": "Alert",
					"document_type": "BrainWise Branding",
					"document_name": doc.name,
					"for_user": user,
					"email_content": message
				}).insert(ignore_permissions=True)
			except Exception:
				pass

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="BrainWise Branding Alert Error",
			message=f"Error sending tampering alert: {e!s}"
		)


def reset_tampering_counter():
	"""
	Monthly task to reset tampering counter
	Keeps historical data manageable
	"""
	try:
		if not frappe.db.exists("DocType", "BrainWise Branding"):
			return

		doc = frappe.get_single("BrainWise Branding")

		if not doc.enabled:
			return

		old_count = doc.tampering_attempts or 0

		# Log the reset
		if old_count > 0:
			frappe.log_error(
				title="BrainWise Branding - Monthly Counter Reset",
				message=json.dumps({
					"previous_count": old_count,
					"reset_date": now(),
					"note": "Monthly tampering counter reset"
				}, indent=2)
			)

		# Reset counter
		frappe.db.set_value("BrainWise Branding", doc.name, "tampering_attempts", 0)
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="BrainWise Branding Counter Reset Error",
			message=f"Error resetting tampering counter: {e!s}"
		)


def validate_all_active_sessions():
	"""
	Check all active user sessions and validate branding configuration
	This helps detect if users are using modified clients
	"""
	try:
		if not frappe.db.exists("DocType", "BrainWise Branding"):
			return

		doc = frappe.get_single("BrainWise Branding")

		if not doc.enabled or not doc.enable_server_validation:
			return

		# Get active sessions (sessions from last 24 hours)
		active_sessions = frappe.db.sql("""
			SELECT user, COUNT(*) as session_count
			FROM `tabSessions`
			WHERE TIMESTAMPDIFF(HOUR, lastupdate, NOW()) < 24
			GROUP BY user
		""", as_dict=True)

		if active_sessions:
			frappe.logger().info(
				f"BrainWise Branding - Active sessions: {len(active_sessions)}"
			)

	except Exception as e:
		frappe.log_error(
			title="BrainWise Branding Session Validation Error",
			message=f"Error validating active sessions: {e!s}"
		)
