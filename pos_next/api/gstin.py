"""
API endpoints for GSTIN verification and autofill in POS
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_gstin_info_for_pos(gstin):
	"""
	Fetch GSTIN information for POS customer creation.
	This bypasses the desk access check in India Compliance since POS users
	may not have desk access.

	Args:
		gstin (str): 15-character GSTIN to verify

	Returns:
		dict: GSTIN information including business name, category, status, addresses
	"""
	try:
		# Import the internal function that doesn't check desk access
		from india_compliance.gst_india.utils.gstin_info import _get_gstin_info

		# Validate GSTIN format first
		from india_compliance.gst_india.utils import validate_gstin

		gstin = validate_gstin(gstin)

		# Fetch GSTIN info (throw_error=False to return empty dict on failure)
		gstin_info = _get_gstin_info(gstin, doc={"doctype": "Customer"}, throw_error=False)

		# Check if we got any data back
		if not gstin_info or not gstin_info.get("business_name"):
			# No data returned - likely API credentials not configured
			return {
				"error": True,
				"message": _(
					"Unable to fetch GSTIN details. Please ensure India Compliance "
					"API credentials are configured in GST Settings, or fill customer "
					"details manually."
				)
			}

		return gstin_info

	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			title="POS GSTIN Verification Error",
			message=f"Error verifying GSTIN {gstin}: {error_msg}"
		)

		# Provide user-friendly error messages
		if "check digit" in error_msg.lower():
			error_msg = _("Invalid GSTIN format. Please verify the GSTIN number.")
		elif "not allowed" in error_msg.lower():
			error_msg = _("Permission denied. Please contact your system administrator.")

		return {
			"error": True,
			"message": error_msg
		}
