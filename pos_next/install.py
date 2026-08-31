"""
Installation and Migration hooks for POS Next

This module relies on Frappe's fixture system for:
- Custom fields (custom_field.json)
- Roles (role.json)
- Custom DocPerm (custom_docperm.json)
- Print formats (print_format.json)

The fixtures are defined in hooks.py and synced automatically during install/migrate.
This module handles post-fixture tasks like setting defaults and clearing cache.
"""

import logging

import frappe

from pos_next.price_group_ownership import (
	ITEM_PRICE_OWNER_FIELD,
	PRICE_LIST_OWNER_FIELD,
	PROFILE_OWNER_FIELD,
	PROFILE_PREVIOUS_PRICE_LIST_FIELD,
)

# Configure logger
logger = logging.getLogger(__name__)


def after_install():
	"""Hook that runs after app installation"""
	try:
		log_message("POS Next: Running post-install setup", level="info")

		# Setup default print format for POS Profiles
		setup_default_print_format()

		ensure_price_group_custom_fields()

		# Clear cache to ensure changes take effect
		frappe.clear_cache()
		frappe.db.commit()

		log_message("POS Next: Installation completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="POS Next Installation Error", message=frappe.get_traceback())
		log_message(f"POS Next: Installation error - {e!s}", level="error")
		raise


def after_migrate():
	"""Hook that runs after bench migrate"""
	try:
		# Reclaim POS Settings if ERPNext re-imported its Single on top of ours.
		# Must run in after_migrate (not as a one-shot patch) because ERPNext's
		# doctype sync runs after pos_next's and would overwrite anything we did
		# during pre/post-model-sync.
		reclaim_pos_settings_doctype(quiet=True)

		# Setup default print format
		setup_default_print_format(quiet=True)

		ensure_price_group_custom_fields()

		# Clear cache
		frappe.clear_cache()
		frappe.db.commit()

		log_message("POS Next: Migration completed successfully", level="success")
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="POS Next Migration Error", message=frappe.get_traceback())
		log_message(f"POS Next: Migration error - {str(e)}", level="error")
		raise


def setup_default_print_format(quiet=False):
	"""
	Set POS Next Receipt as default print format for POS Profiles if not already set.

	Args:
		quiet (bool): If True, suppress detailed logs
	"""
	try:
		# Check if the print format exists
		if not frappe.db.exists("Print Format", "POS Next Receipt"):
			if not quiet:
				log_message(
					"POS Next Receipt print format not found, skipping default setup", level="warning"
				)
			return

		# Get all POS Profiles without a print format
		pos_profiles = frappe.get_all(
			"POS Profile", filters={"print_format": ["in", ["", None]]}, fields=["name"]
		)

		if pos_profiles:
			updated_count = 0
			for profile in pos_profiles:
				try:
					frappe.db.set_value(
						"POS Profile", profile.name, "print_format", "POS Next Receipt", update_modified=False
					)
					if not quiet:
						log_message(f"Set default print format for: {profile.name}", level="info", indent=1)
					updated_count += 1
				except Exception as e:
					log_message(
						f"Error updating POS Profile {profile.name}: {str(e)}", level="error", indent=1
					)

			if updated_count > 0 and not quiet:
				log_message(
					f"Updated {updated_count} POS Profile(s) with default print format", level="success"
				)

	except Exception as e:
		log_message(f"Error setting up default print format: {str(e)}", level="error")
		frappe.log_error(title="Default Print Format Setup Error", message=frappe.get_traceback())


PRICE_GROUP_CUSTOM_FIELDS = {
	"Price List": [
		{
			"fieldname": PRICE_LIST_OWNER_FIELD,
			"label": "Price Group",
			"fieldtype": "Link",
			"options": "Price Group",
			"insert_after": "price_list_name",
			"read_only": 1,
			"no_copy": 1,
		}
	],
	"Item Price": [
		{
			"fieldname": ITEM_PRICE_OWNER_FIELD,
			"label": "Price Group",
			"fieldtype": "Link",
			"options": "Price Group",
			"insert_after": "price_list",
			"read_only": 1,
			"no_copy": 1,
		}
	],
	"POS Profile": [
		{
			"fieldname": PROFILE_OWNER_FIELD,
			"label": "Price Group",
			"fieldtype": "Link",
			"options": "Price Group",
			"insert_after": "selling_price_list",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": PROFILE_PREVIOUS_PRICE_LIST_FIELD,
			"label": "Previous Price List",
			"fieldtype": "Link",
			"options": "Price List",
			"insert_after": PROFILE_OWNER_FIELD,
			"read_only": 1,
			"no_copy": 1,
		},
	],
}


def ensure_price_group_custom_fields(quiet=False):
	"""Create the Price Group ownership Custom Fields when missing.

	`hooks.py:fixtures` exports only Role and Custom DocPerm, so these fields cannot ship
	as a fixture and must be upserted here on every install and migrate.

	Validation is NOT suppressed: `CustomField.validate` computes `idx` from `insert_after`
	and runs `check_fieldname_conflicts`. Skipping it would leave every field at `idx = 0`
	and hide a genuine fieldname collision.
	"""
	created = 0
	for dt, fields in PRICE_GROUP_CUSTOM_FIELDS.items():
		if not frappe.db.exists("DocType", dt):
			log_message(f"DocType {dt} missing, skipping its Price Group fields", level="warning")
			continue
		for df in fields:
			cf_name = f"{dt}-{df['fieldname']}"
			if frappe.db.exists("Custom Field", cf_name):
				continue
			doc = frappe.get_doc(
				{
					"doctype": "Custom Field",
					"dt": dt,
					"permlevel": 0,
					"hidden": 0,
					"is_system_generated": 0,
					"module": "POS Next",
					**df,
				}
			)
			doc.insert(ignore_permissions=True)
			created += 1
			if not quiet:
				log_message(f"Created Custom Field: {cf_name}", level="info", indent=1)

	if created and not quiet:
		log_message(f"Created {created} Price Group custom field(s)", level="success")


def log_message(message, level="info", indent=0):
	"""
	Standardized logging function with consistent formatting.

	Args:
		message (str): The message to log
		level (str): Log level - info, success, warning, error
		indent (int): Indentation level (0, 1, 2, etc.)
	"""
	indent_str = "  " * indent

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

	# Also log to frappe logger
	if level == "error":
		logger.error(message)
	elif level == "warning":
		logger.warning(message)
	else:
		logger.info(message)


def reclaim_pos_settings_doctype(quiet=False):
	"""Reclaim the `POS Settings` DocType from ERPNext.

	ERPNext ships a Single `POS Settings` (module Accounts) with only
	`invoice_fields` and `pos_search_fields`. POS Next ships its own
	non-Single `POS Settings` (module POS Next) with per-profile config
	and a `barcode_rules` child table. Because ERPNext is in our
	`required_apps` its doctype sync runs after ours during `bench
	migrate`, so its JSON wins on disk unless we re-install our version
	after both apps have finished syncing.

	Runs from `after_migrate`. Idempotent: if the live doctype already
	belongs to POS Next (module == 'POS Next' and not Single), exits
	without touching anything.
	"""
	if not frappe.db.exists("DocType", "POS Settings"):
		if not quiet:
			log_message("POS Settings DocType missing, skipping reclaim", level="warning")
		return

	row = frappe.db.get_value("DocType", "POS Settings", ["module", "issingle"], as_dict=True)
	if row and row.module == "POS Next" and not row.issingle:
		if not quiet:
			log_message("POS Settings already owned by POS Next, nothing to reclaim", level="info")
		return

	if not quiet:
		log_message(
			f"Reclaiming POS Settings DocType (was module={row.module if row else '?'}, "
			f"issingle={row.issingle if row else '?'})",
			level="warning",
		)

	try:
		# Commit any open transaction first — DROP TABLE is DDL and would
		# otherwise trigger ImplicitCommitError under Frappe's safety check.
		frappe.db.commit()
		frappe.db.sql("DROP TABLE IF EXISTS `tabPOS Settings`")
		frappe.db.commit()
		frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'POS Settings'")
		frappe.db.sql("DELETE FROM `tabDocField` WHERE parent = 'POS Settings'")
		frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent = 'POS Settings'")
		frappe.db.sql("DELETE FROM `tabDocType` WHERE name = 'POS Settings'")
		frappe.db.commit()
		log_message("Dropped legacy POS Settings meta + table", level="info", indent=1)
	except Exception:
		frappe.log_error(
			title="POS Settings Reclaim Error",
			message="Failed to drop legacy POS Settings\n\n" + frappe.get_traceback(),
		)
		raise

	try:
		frappe.reload_doc("pos_next", "doctype", "pos_settings", force=True)
		frappe.reload_doc("pos_next", "doctype", "pos_barcode_rules", force=True)
		frappe.reload_doc("pos_next", "doctype", "pos_allowed_locale", force=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="POS Settings Reclaim Error",
			message="Failed to reload pos_next doctypes\n\n" + frappe.get_traceback(),
		)
		raise

	after = frappe.db.get_value("DocType", "POS Settings", ["module", "issingle"], as_dict=True)
	if not after or after.module != "POS Next" or after.issingle:
		frappe.log_error(
			title="POS Settings Reclaim Error",
			message=(
				f"Reclaim ran but doctype still wrong: {after}. "
				"ERPNext may be re-importing POS Settings later in the migration."
			),
		)
		log_message(f"Reclaim verification FAILED — doctype is now {after}", level="error")
		return

	if not quiet:
		log_message(
			f"POS Settings reclaimed (module={after.module}, issingle={after.issingle})",
			level="success",
		)
