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

		return gstin_info

	except Exception as e:
		frappe.log_error(
			title="POS GSTIN Verification Error",
			message=f"Error verifying GSTIN {gstin}: {str(e)}"
		)
		# Return error message instead of throwing
		return {
			"error": True,
			"message": str(e)
		}
