# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""HTTP transport helpers wrapping SyncSession.

Provides a factory that builds a SyncSession from the Sync Site Config record.
"""

import frappe

from pos_next.sync.auth import SyncSession
from pos_next.sync.exceptions import SyncAuthError


def build_session_from_config():
	"""
	Read the (singleton) Branch Sync Site Config and return a SyncSession.

	Raises SyncAuthError if no Branch config exists or credentials are missing.
	"""
	name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "name")
	if not name:
		raise SyncAuthError("No Branch Sync Site Config found on this site")
	cfg = frappe.get_doc("Sync Site Config", name)
	if not (cfg.central_url and cfg.sync_username and cfg.sync_password):
		raise SyncAuthError("Branch Sync Site Config missing credentials")
	password = cfg.get_password("sync_password")
	return SyncSession(
		central_url=cfg.central_url,
		username=cfg.sync_username,
		password=password,
	)
