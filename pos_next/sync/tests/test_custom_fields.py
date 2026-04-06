# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


TARGET_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Stock Ledger Entry",
	"POS Opening Shift",
	"POS Closing Shift",
	"Customer",
]

EXPECTED_FIELDS = {"sync_uuid", "origin_branch", "synced_from_failover"}


def test_custom_fields_installed():
	"""All three sync custom fields are installed on every target DocType."""
	for dt in TARGET_DOCTYPES:
		for fieldname in EXPECTED_FIELDS:
			exists = frappe.db.exists(
				"Custom Field", {"dt": dt, "fieldname": fieldname}
			)
			assert exists, f"Missing custom field {fieldname} on {dt}"
	print("PASS: test_custom_fields_installed")


def test_sync_uuid_is_unique():
	"""sync_uuid has unique=1 on target DocTypes."""
	for dt in TARGET_DOCTYPES:
		cf = frappe.db.get_value(
			"Custom Field",
			{"dt": dt, "fieldname": "sync_uuid"},
			["fieldtype", "unique"],
			as_dict=True,
		)
		assert cf is not None, f"sync_uuid missing on {dt}"
		assert cf.fieldtype == "Data", f"sync_uuid should be Data on {dt}"
		assert cf.unique == 1, f"sync_uuid should be unique on {dt}"
	print("PASS: test_sync_uuid_is_unique")


def run_all():
	test_custom_fields_installed()
	test_sync_uuid_is_unique()
	print("\nAll Custom Fields tests PASSED")
