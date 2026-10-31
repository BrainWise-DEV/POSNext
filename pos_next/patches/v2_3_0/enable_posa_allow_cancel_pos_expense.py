import json
import os

import frappe

FIELDNAME = "posa_allow_cancel_pos_expense"


def execute():
	"""Restore pre-offline-sync cancel behaviour for existing POS Profiles.

	``posa_allow_cancel_pos_expense`` shipped defaulting to 0 with no backfill,
	so upgrades silently lost the ability for JE owners to cancel their own
	just-submitted POS expenses. Enable it on every profile that already exists.

	This patch runs in ``post_model_sync``, but ``bench migrate`` only syncs the
	app's ``custom/*.json`` (sync_customizations) after all patches. On a site
	upgrading from a version that never had the field, the column does not
	exist yet, so create POS Next's POS Profile custom fields first instead of
	returning early and being marked as done without backfilling.
	"""
	if not frappe.db.has_column("POS Profile", FIELDNAME):
		_sync_pos_profile_customizations()

	if not frappe.db.has_column("POS Profile", FIELDNAME):
		return

	frappe.db.sql(
		"""
		UPDATE `tabPOS Profile`
		SET posa_allow_cancel_pos_expense = 1
		WHERE IFNULL(posa_allow_cancel_pos_expense, 0) = 0
		"""
	)


def _sync_pos_profile_customizations():
	"""Upsert the custom fields from pos_next/pos_next/custom/pos_profile.json.

	Same call migrate makes later in sync_customizations, so running it early is
	idempotent (existing Custom Fields are updated, missing ones inserted).
	"""
	from frappe.modules.utils import sync_customizations_for_doctype

	folder = frappe.get_app_path("pos_next", "pos_next", "custom")
	filename = "pos_profile.json"
	path = os.path.join(folder, filename)
	if not os.path.exists(path):
		return

	with open(path) as f:
		data = json.load(f)

	sync_customizations_for_doctype(data, folder, filename)
	frappe.clear_cache(doctype="POS Profile")
