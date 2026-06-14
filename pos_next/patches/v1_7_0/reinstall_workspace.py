import json
from pathlib import Path

import frappe


def execute():
	"""Reinstall POSNext workspace with latest configuration."""
	app_name = "pos_next"
	workspace_dir = Path(frappe.get_app_path(app_name)) / f"{app_name}/workspace"

	# Discover all workspace JSON files
	workspace_files = list(workspace_dir.rglob("*.json"))

	if not workspace_files:
		frappe.logger().warning(f"No workspace files found in {workspace_dir}")
		return

	# Process each workspace
	for workspace_file in workspace_files:
		_reinstall_workspace_from_file(workspace_file)


def _reinstall_workspace_from_file(workspace_file: Path):
	"""Reinstall a single workspace from its JSON file.

	Args:
		workspace_file: Path to the workspace JSON file
	"""
	workspace_data = _load_workspace_data(workspace_file)
	if not workspace_data:
		return

	workspace_name = workspace_data.get("name") or workspace_data.get("label")
	if not workspace_name:
		frappe.log_error(
			title="Workspace Migration Failed",
			message=f"Workspace in {workspace_file} has no name or label"
		)
		return

	_remove_workspace(workspace_name)
	_install_workspace(workspace_data, workspace_name)


def _remove_workspace(workspace_name: str):
	"""Remove existing workspace if it exists.

	Args:
		workspace_name: Name of the workspace to remove
	"""
	if not frappe.db.exists("Workspace", workspace_name):
		frappe.logger().debug(f"Workspace '{workspace_name}' does not exist")
		return

	try:
		frappe.delete_doc("Workspace", workspace_name, force=True, ignore_permissions=True)
		frappe.logger().info(f"Removed workspace: {workspace_name}")
	except Exception:
		frappe.log_error(
			title=f"Failed to Remove Workspace: {workspace_name}",
			message=frappe.get_traceback()
		)


def _install_workspace(workspace_data: dict, workspace_name: str):
	"""Install workspace from data.

	Args:
		workspace_data: Workspace document data
		workspace_name: Name of the workspace
	"""
	try:
		workspace_doc = frappe.get_doc(workspace_data)
		workspace_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		frappe.logger().info(f"Successfully installed workspace: {workspace_name}")
	except Exception:
		frappe.log_error(
			title=f"Workspace Installation Failed: {workspace_name}",
			message=frappe.get_traceback()
		)


def _load_workspace_data(workspace_file: Path):
	"""Load and validate workspace data from JSON file.

	Args:
		workspace_file: Path to the workspace JSON file

	Returns:
		dict: Workspace document data or None if loading fails
	"""
	if not workspace_file.exists():
		frappe.log_error(
			title="Workspace File Not Found",
			message=f"Expected workspace file at: {workspace_file}"
		)
		return None

	try:
		workspace_data = json.loads(workspace_file.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		frappe.log_error(
			title="Invalid Workspace JSON",
			message=f"Failed to parse: {workspace_file}\n\n{frappe.get_traceback()}"
		)
		return None

	if not isinstance(workspace_data, list) or not workspace_data:
		frappe.log_error(
			title="Invalid Workspace Structure",
			message=f"Workspace JSON must be a non-empty array: {workspace_file}"
		)
		return None

	return workspace_data[0]
