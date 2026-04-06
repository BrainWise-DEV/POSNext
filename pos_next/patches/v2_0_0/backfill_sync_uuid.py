# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Backfill sync_uuid on existing rows in sync-tracked doctypes. Idempotent."""

import uuid

import frappe


TARGET_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Stock Ledger Entry",
	"POS Opening Shift",
	"POS Closing Shift",
	"Customer",
]

BATCH_SIZE = 500


def execute():
	total_updated = 0
	for dt in TARGET_DOCTYPES:
		updated = _backfill_doctype(dt)
		total_updated += updated
		print(f"Backfilled sync_uuid: {dt} — {updated} rows")
	print(f"Total rows backfilled: {total_updated}")
	frappe.db.commit()


def _backfill_doctype(doctype_name):
	"""Fill sync_uuid where NULL or empty, in batches."""
	updated = 0
	while True:
		rows = frappe.db.sql(
			f"""
			SELECT name FROM `tab{doctype_name}`
			WHERE sync_uuid IS NULL OR sync_uuid = ''
			LIMIT {BATCH_SIZE}
			""",
			as_dict=True,
		)
		if not rows:
			break
		for row in rows:
			new_uuid = str(uuid.uuid4())
			frappe.db.sql(
				f"UPDATE `tab{doctype_name}` SET sync_uuid = %s WHERE name = %s",
				(new_uuid, row.name),
			)
		frappe.db.commit()
		updated += len(rows)
		if len(rows) < BATCH_SIZE:
			break
	return updated
