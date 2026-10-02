# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Keep ``bench run-tests`` from wiping a working site's Item Prices.

ERPNext's ``before_tests`` hook (``erpnext/setup/utils.py``) runs

	frappe.db.sql("delete from `tabItem Price`")

unconditionally and then commits. Frappe fires that hook at the start of *every*
``bench run-tests`` invocation — narrowing the run with ``--module`` or
``--doctype`` picks which tests execute, not whether the hook runs — so a single
test run against a site holding real data destroys every Item Price on it.

Because the wipe is raw SQL it never goes through ``delete_doc``: no
``Deleted Document`` rows and no ``Version`` history are written, so the records
cannot be reconstructed afterwards. Only a database backup gets them back.

Frappe ships ``--skip-before-tests`` for this, but it has to be remembered on
every command and forgetting once is unrecoverable. When
``preserve_item_prices_in_tests`` is set in the site's ``site_config.json`` this
patch snapshots the rows, lets ERPNext's setup run untouched, then puts back
whatever it removed. Sites that leave the flag unset — CI, throwaway test sites
— keep stock ERPNext behaviour, which the ERPNext suite itself relies on.

Item Price is a flat DocType (no child tables), so a row-level copy is a
faithful snapshot. The restore deliberately avoids ``CREATE``/``DROP TABLE``:
Frappe raises ``ImplicitCommitError`` for DDL issued while a transaction holds
writes, which is exactly the state ``before_tests`` runs in.
"""

from __future__ import annotations

import frappe

SITE_CONFIG_FLAG = "preserve_item_prices_in_tests"

# Chunked so a large price list cannot trip MAX_WRITES_PER_TRANSACTION.
RESTORE_CHUNK_SIZE = 500


def _preserve_enabled() -> bool:
	try:
		return bool(frappe.conf.get(SITE_CONFIG_FLAG))
	except Exception:
		return False


def _restore_item_prices(rows) -> None:
	"""Put snapshotted rows back, leaving anything created meanwhile intact.

	``REPLACE`` rather than ``INSERT``: ERPNext's own test records may have
	recreated some of these primary keys by the time we run.
	"""
	if not rows:
		return

	columns = list(rows[0].keys())
	collist = ", ".join(f"`{column}`" for column in columns)
	row_placeholder = "(" + ", ".join(["%s"] * len(columns)) + ")"

	for start in range(0, len(rows), RESTORE_CHUNK_SIZE):
		chunk = rows[start : start + RESTORE_CHUNK_SIZE]
		values = []
		for row in chunk:
			values.extend(row[column] for column in columns)
		frappe.db.sql(
			f"REPLACE INTO `tabItem Price` ({collist}) VALUES "
			+ ", ".join([row_placeholder] * len(chunk)),
			values,
		)
		frappe.db.commit()


def patch_before_tests(utils_module) -> None:
	"""Wrap ``erpnext.setup.utils.before_tests`` so it cannot drop Item Prices.

	The hook is resolved by dotted path at call time (``frappe.get_attr``), so
	rebinding the module attribute here is enough — no ERPNext file is edited.
	"""
	original = getattr(utils_module, "before_tests", None)
	if original is None or getattr(original, "_pos_next_preserves_item_prices", False):
		return

	def before_tests_preserving_item_prices():
		if not _preserve_enabled():
			return original()

		try:
			snapshot = frappe.db.sql("SELECT * FROM `tabItem Price`", as_dict=True)
		except Exception:
			# Never let the guard itself break a test run.
			return original()

		try:
			return original()
		finally:
			try:
				_restore_item_prices(snapshot)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(), "POS Next: failed to restore Item Prices after before_tests"
				)

	before_tests_preserving_item_prices._pos_next_preserves_item_prices = True
	utils_module.before_tests = before_tests_preserving_item_prices
