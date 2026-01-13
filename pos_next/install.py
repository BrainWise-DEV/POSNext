"""
Installation and Migration hooks for POS Next
"""
import frappe
import logging

# Configure logger
logger = logging.getLogger(__name__)


def after_install():
	"""Hook that runs after app installation"""
	try:
		log_message("Installing POS Next fixtures", level="info")
		install_fixtures()
		setup_default_print_format()
		frappe.db.commit()
		log_message("POS Next installation completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title="POS Next Installation Error",
			message=frappe.get_traceback()
		)
		log_message(f"Error during POS Next installation: {str(e)}", level="error")
		raise


def after_migrate():
	"""Hook that runs after bench migrate"""
	try:
		# Migrate runs often, so we use quiet mode to reduce noise
		install_fixtures(quiet=True)
		setup_default_print_format(quiet=True)
		frappe.db.commit()
		log_message("POS Next: Fixtures updated successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title="POS Next Migration Error",
			message=frappe.get_traceback()
		)
		log_message(f"POS Next: Migration error - {str(e)}", level="error")
		raise


def install_fixtures(quiet=False):
	"""
	Install or update fixtures from JSON files
	This includes custom fields, print formats, etc.

	Args:
		quiet (bool): If True, suppress detailed logs (useful for migrations)
	"""
	import os
	import json

	fixtures_path = frappe.get_app_path("pos_next", "fixtures")

	if not os.path.exists(fixtures_path):
		if not quiet:
			log_message(f"Fixtures directory not found: {fixtures_path}", level="warning")
		return

	# Install print format fixture
	print_format_file = os.path.join(fixtures_path, "print_format.json")
	if os.path.exists(print_format_file):
		try:
			with open(print_format_file, 'r') as f:
				print_formats = json.load(f)

			for pf in print_formats:
				install_print_format(pf, quiet=quiet)

			if not quiet:
				log_message(f"Installed print formats successfully", level="success")
		except Exception as e:
			log_message(f"Error installing print formats: {str(e)}", level="error")
			frappe.log_error(
				title="Print Format Installation Error",
				message=frappe.get_traceback()
			)

	# Install custom field fixture
	custom_field_file = os.path.join(fixtures_path, "custom_field.json")
	if os.path.exists(custom_field_file):
		try:
			with open(custom_field_file, 'r') as f:
				custom_fields = json.load(f)

			for cf in custom_fields:
				install_custom_field(cf, quiet=quiet)

			if not quiet:
				log_message(f"Installed custom fields successfully", level="success")
		except Exception as e:
			log_message(f"Error installing custom fields: {str(e)}", level="error")
			frappe.log_error(
				title="Custom Field Installation Error",
				message=frappe.get_traceback()
			)


def install_print_format(doc_dict, quiet=False):
	"""
	Install or update a print format from dict
	Updates existing print format instead of deleting (idempotent)

	Args:
		quiet (bool): If True, suppress detailed logs
	"""
	try:
		name = doc_dict.get("name")

		if frappe.db.exists("Print Format", name):
			# Update existing print format
			existing_doc = frappe.get_doc("Print Format", name)

			# Update key properties
			update_fields = ["html", "doc_type", "module", "disabled", "standard"]
			updated = False

			for field in update_fields:
				if field in doc_dict and existing_doc.get(field) != doc_dict.get(field):
					existing_doc.set(field, doc_dict.get(field))
					updated = True

			if updated:
				existing_doc.flags.ignore_permissions = True
				existing_doc.flags.ignore_mandatory = True
				existing_doc.save()
				if not quiet:
					log_message(f"Updated Print Format: {name}", level="info", indent=1)

			return existing_doc
		else:
			# Create fresh print format
			doc = frappe.get_doc(doc_dict)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.insert()
			if not quiet:
				log_message(f"Created Print Format: {doc.name}", level="info", indent=1)
			return doc

	except Exception as e:
		log_message(f"Error installing print format {doc_dict.get('name')}: {str(e)}", level="error", indent=1)
		frappe.log_error(
			title=f"Print Format Installation Error: {doc_dict.get('name')}",
			message=frappe.get_traceback()
		)


def install_custom_field(doc_dict, quiet=False):
	"""
	Install or update a custom field from dict
	Updates existing field if it exists (to avoid conflicts with other apps like Nexus)

	Args:
		quiet (bool): If True, suppress detailed logs
	"""
	try:
		name = doc_dict.get("name")

		if frappe.db.exists("Custom Field", name):
			# Update existing custom field instead of deleting
			# This prevents conflicts when multiple apps manage the same field
			existing_doc = frappe.get_doc("Custom Field", name)

			# Update only key properties that we care about
			# Don't override everything to preserve other app's customizations
			update_fields = [
				"description", "in_standard_filter", "label",
				"options", "fieldtype", "insert_after"
			]

			updated = False
			for field in update_fields:
				if field in doc_dict and existing_doc.get(field) != doc_dict.get(field):
					existing_doc.set(field, doc_dict.get(field))
					updated = True

			if updated:
				existing_doc.flags.ignore_permissions = True
				existing_doc.flags.ignore_mandatory = True
				existing_doc.save()
				if not quiet:
					log_message(f"Updated Custom Field: {name}", level="info", indent=1)

			return existing_doc
		else:
			# Create fresh custom field
			doc = frappe.get_doc(doc_dict)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.insert()
			if not quiet:
				log_message(f"Created Custom Field: {doc.name}", level="info", indent=1)
			return doc

	except Exception as e:
		log_message(f"Error installing custom field {doc_dict.get('name')}: {str(e)}", level="error", indent=1)
		frappe.log_error(
			title=f"Custom Field Installation Error: {doc_dict.get('name')}",
			message=frappe.get_traceback()
		)


def setup_default_print_format(quiet=False):
	"""
	Set POS Next Receipt as default print format for POS Profiles if not already set

	Args:
		quiet (bool): If True, suppress detailed logs
	"""
	try:
		# Check if the print format exists
		if not frappe.db.exists("Print Format", "POS Next Receipt"):
			if not quiet:
				log_message("POS Next Receipt print format not found, skipping default setup", level="warning")
			return

		# Get all POS Profiles without a print format
		pos_profiles = frappe.get_all(
			"POS Profile",
			filters={"print_format": ["in", ["", None]]},
			fields=["name"]
		)

		if pos_profiles:
			updated_count = 0
			for profile in pos_profiles:
				try:
					doc = frappe.get_doc("POS Profile", profile.name)
					doc.print_format = "POS Next Receipt"
					doc.flags.ignore_permissions = True
					doc.flags.ignore_mandatory = True
					doc.save()
					if not quiet:
						log_message(f"Set default print format for POS Profile: {profile.name}", level="info", indent=1)
					updated_count += 1
				except Exception as e:
					log_message(f"Error updating POS Profile {profile.name}: {str(e)}", level="error", indent=1)

			if updated_count > 0 and not quiet:
				log_message(f"Updated {updated_count} POS Profile(s) with default print format", level="success")

	except Exception as e:
		log_message(f"Error setting up default print format: {str(e)}", level="error")
		frappe.log_error(
			title="Default Print Format Setup Error",
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
