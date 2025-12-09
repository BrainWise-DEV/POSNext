"""
Uninstallation hooks for POS Next
"""
import frappe
import logging

# Configure logger
logger = logging.getLogger(__name__)


def before_uninstall():
	"""
	Hook that runs before app uninstallation
	Cleans up custom fields, print formats, and configurations
	"""
	try:
		log_message("Starting POS Next uninstallation", level="info")

		# Remove custom fields
		remove_custom_fields()

		# Remove print formats
		remove_print_formats()

		# Reset POS Profile configurations
		reset_pos_profiles()

		# Commit all changes
		frappe.db.commit()

		log_message("POS Next uninstalled successfully", level="success")
		log_message("All custom fields and configurations have been removed", level="info")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title="POS Next Uninstallation Error",
			message=frappe.get_traceback()
		)
		log_message(f"Error during POS Next uninstallation: {str(e)}", level="error")
		raise


def remove_custom_fields():
	"""
	Remove all custom fields created by POS Next
	"""
	try:
		log_message("Removing custom fields", level="info")

		# List of custom fields to remove
		custom_fields = [
			"Sales Invoice-posa_pos_opening_shift",
			"Sales Invoice-posa_is_printed",
			# Note: Item-custom_company is shared with Nexus app
			# Only remove if Nexus is not installed
		]

		removed_count = 0
		skipped_count = 0

		# Check if Nexus app is installed
		nexus_installed = "nexus" in frappe.get_installed_apps()

		# Add Item-custom_company to removal list only if Nexus is not installed
		if not nexus_installed:
			custom_fields.append("Item-custom_company")
		else:
			log_message("Nexus app detected - preserving Item-custom_company field", level="info", indent=1)

		for field_name in custom_fields:
			try:
				if frappe.db.exists("Custom Field", field_name):
					frappe.delete_doc("Custom Field", field_name, force=True, ignore_permissions=True)
					log_message(f"Removed Custom Field: {field_name}", level="info", indent=1)
					removed_count += 1
				else:
					log_message(f"Custom Field not found: {field_name}", level="info", indent=1)
					skipped_count += 1
			except Exception as e:
				log_message(f"Error removing custom field {field_name}: {str(e)}", level="error", indent=1)

		if removed_count > 0:
			log_message(f"Removed {removed_count} custom field(s)", level="success")
		if skipped_count > 0:
			log_message(f"Skipped {skipped_count} field(s) (already removed or not found)", level="info")

	except Exception as e:
		log_message(f"Error removing custom fields: {str(e)}", level="error")
		frappe.log_error(
			title="Custom Fields Removal Error",
			message=frappe.get_traceback()
		)


def remove_print_formats():
	"""
	Remove all print formats created by POS Next
	"""
	try:
		log_message("Removing print formats", level="info")

		# List of print formats to remove
		print_formats = [
			"POS Next Receipt",
		]

		removed_count = 0
		skipped_count = 0

		for format_name in print_formats:
			try:
				if frappe.db.exists("Print Format", format_name):
					# Check if it's being used by any POS Profile
					pos_profiles_using = frappe.get_all(
						"POS Profile",
						filters={"print_format": format_name},
						fields=["name"]
					)

					if pos_profiles_using:
						# Reset those POS Profiles first
						for profile in pos_profiles_using:
							try:
								doc = frappe.get_doc("POS Profile", profile.name)
								doc.print_format = ""
								doc.flags.ignore_permissions = True
								doc.save()
								log_message(f"Reset print format for POS Profile: {profile.name}", level="info", indent=2)
							except Exception as e:
								log_message(f"Error resetting POS Profile {profile.name}: {str(e)}", level="error", indent=2)

					# Now delete the print format
					frappe.delete_doc("Print Format", format_name, force=True, ignore_permissions=True)
					log_message(f"Removed Print Format: {format_name}", level="info", indent=1)
					removed_count += 1
				else:
					log_message(f"Print Format not found: {format_name}", level="info", indent=1)
					skipped_count += 1
			except Exception as e:
				log_message(f"Error removing print format {format_name}: {str(e)}", level="error", indent=1)

		if removed_count > 0:
			log_message(f"Removed {removed_count} print format(s)", level="success")
		if skipped_count > 0:
			log_message(f"Skipped {skipped_count} format(s) (already removed or not found)", level="info")

	except Exception as e:
		log_message(f"Error removing print formats: {str(e)}", level="error")
		frappe.log_error(
			title="Print Formats Removal Error",
			message=frappe.get_traceback()
		)


def reset_pos_profiles():
	"""
	Reset POS Profile configurations set by POS Next
	"""
	try:
		log_message("Resetting POS Profile configurations", level="info")

		# Find POS Profiles using POS Next print format
		pos_profiles = frappe.get_all(
			"POS Profile",
			filters={"print_format": "POS Next Receipt"},
			fields=["name"]
		)

		if not pos_profiles:
			log_message("No POS Profiles using POS Next configurations", level="info", indent=1)
			return

		reset_count = 0
		for profile in pos_profiles:
			try:
				doc = frappe.get_doc("POS Profile", profile.name)
				doc.print_format = ""
				doc.flags.ignore_permissions = True
				doc.flags.ignore_mandatory = True
				doc.save()
				log_message(f"Reset POS Profile: {profile.name}", level="info", indent=1)
				reset_count += 1
			except Exception as e:
				log_message(f"Error resetting POS Profile {profile.name}: {str(e)}", level="error", indent=1)

		if reset_count > 0:
			log_message(f"Reset {reset_count} POS Profile(s)", level="success")

	except Exception as e:
		log_message(f"Error resetting POS Profiles: {str(e)}", level="error")
		frappe.log_error(
			title="POS Profile Reset Error",
			message=frappe.get_traceback()
		)


def log_message(message, level="info", indent=0):
	"""
	Standardized logging function with consistent formatting

	Args:
		message (str): The message to log
		level (str): Log level - info, success, warning, error
		indent (int): Indentation level (0, 1, 2, etc.)
	"""
	indent_str = "  " * indent

	# Log level prefixes
	prefixes = {
		"info": "[INFO]",
		"success": "[SUCCESS]",
		"warning": "[WARNING]",
		"error": "[ERROR]",
	}

	prefix = prefixes.get(level, "[INFO]")
	formatted_message = f"{indent_str}{prefix} {message}"

	# Print to console
	print(formatted_message)

	# Also log to frappe logger with appropriate level
	if level == "error":
		logger.error(message)
	elif level == "warning":
		logger.warning(message)
	elif level == "success":
		logger.info(f"SUCCESS: {message}")
	else:
		logger.info(message)


def get_custom_fields_for_cleanup():
	"""
	Get list of custom fields that can be safely removed
	Returns list of field names that belong to POS Next
	"""
	custom_fields = []

	# Always safe to remove (POS Next specific)
	custom_fields.extend([
		"Sales Invoice-posa_pos_opening_shift",
		"Sales Invoice-posa_is_printed",
	])

	# Conditional removal (shared with other apps)
	nexus_installed = "nexus" in frappe.get_installed_apps()
	if not nexus_installed:
		custom_fields.append("Item-custom_company")

	return custom_fields


def validate_uninstall():
	"""
	Validate that uninstall can proceed safely
	Returns True if safe to uninstall, False otherwise with reason
	"""
	try:
		# Check if there are any active POS sessions
		# This is just an example - you can add more checks

		# For now, always return True
		return True, "Safe to uninstall"

	except Exception as e:
		return False, f"Validation error: {str(e)}"
