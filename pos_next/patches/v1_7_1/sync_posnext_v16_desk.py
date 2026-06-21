"""Sync POSNext v16 desk artifacts (workspace, sidebar, desktop icon)."""

from pathlib import Path

import frappe
from frappe.modules.import_file import import_file_by_path

from pos_next.patches.v1_7_0.reinstall_workspace import _reinstall_workspace_from_file


def execute():
	app_path = Path(frappe.get_app_path("pos_next"))

	workspace_file = app_path / "pos_next/workspace/posnext/posnext.json"
	if workspace_file.exists():
		_reinstall_workspace_from_file(workspace_file)

	for relative_path in (
		"workspace_sidebar/posnext.json",
		"desktop_icon/posnext.json",
	):
		file_path = app_path / relative_path
		if file_path.exists():
			import_file_by_path(str(file_path), force=True, ignore_version=True)

	frappe.clear_cache()
