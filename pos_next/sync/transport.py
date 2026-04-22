# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""HTTP transport helpers wrapping SyncSession."""

import frappe

from pos_next.sync.auth import SyncSession
from pos_next.sync.exceptions import SyncAuthError


def build_session_from_config():
	"""
	Read the (singleton) Branch Sync Site Config and return a SyncSession.

	Raises SyncAuthError if no Branch config exists or API credentials are missing.
	"""
	name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "name")
	if not name:
		raise SyncAuthError("No Branch Sync Site Config found on this site")
	cfg = frappe.get_doc("Sync Site Config", name)
	if not (cfg.central_url and cfg.sync_api_key and cfg.sync_api_secret):
		raise SyncAuthError("Branch Sync Site Config missing API credentials")
	api_secret = cfg.get_password("sync_api_secret")
	return SyncSession(
		central_url=cfg.central_url,
		api_key=cfg.sync_api_key,
		api_secret=api_secret,
	)
