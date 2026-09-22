import frappe


def execute():
	"""Restore pre-offline-sync cancel behaviour for existing POS Profiles.

	``posa_allow_cancel_pos_expense`` shipped defaulting to 0 with no backfill,
	so upgrades silently lost the ability for JE owners to cancel their own
	just-submitted POS expenses. Enable it on every profile that already exists.
	"""
	if not frappe.db.has_column("POS Profile", "posa_allow_cancel_pos_expense"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabPOS Profile`
		SET posa_allow_cancel_pos_expense = 1
		WHERE IFNULL(posa_allow_cancel_pos_expense, 0) = 0
		"""
	)
