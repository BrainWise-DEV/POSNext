# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Self-check of pos_next.ui_test_seed: seed twice, teardown, check.

It commits real records, so it is not a run-tests case. Run it by hand on a test site:

	bench --site <site> execute pos_next.test_ui_test_seed.run

It asserts that:
- the site starts clean;
- a second seed changes nothing;
- after teardown, check() reports zero leftovers;
- the F&F Settings and the enabled pricing rules are back to their values before the run.
"""

from __future__ import annotations

import frappe

from pos_next import ui_test_seed as uit

_ROW_META = {
	"name",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"creation",
	"modified",
	"owner",
	"modified_by",
}


def _site_image() -> dict:
	"""The site state seed may change: F&F Settings (without row names and timestamps) and the enabled rules."""
	image = {"enabled_rules": sorted(frappe.get_all("Pricing Rule", filters={"disable": 0}, pluck="name"))}
	if uit.promotions_installed():
		settings = frappe.get_doc(uit.FF_SETTINGS).as_dict(convert_dates_to_str=True, no_nulls=False)
		image["ff_settings"] = {
			key: [{k: _blank(v) for k, v in row.items() if k not in _ROW_META} for row in value]
			if isinstance(value, list)
			else _blank(value)
			for key, value in settings.items()
			if key not in ("modified", "modified_by")
		}
	return image


def _blank(value):
	"""A Select saved back as "" and one left NULL are the same setting."""
	return None if value == "" else value


def _inventory() -> dict:
	"""(doctype, name) → modified for every UIT record, plus F&F Settings."""
	found = {}
	for doctype, names in uit._named_records().items():
		for name in names:
			found[(doctype, name)] = str(frappe.db.get_value(doctype, name, "modified"))
	if uit.promotions_installed():
		found[(uit.FF_SETTINGS, uit.FF_SETTINGS)] = str(
			frappe.db.get_single_value(uit.FF_SETTINGS, "modified")
		)
	found[("disabled rules", "")] = str(
		sorted(frappe.get_all("Pricing Rule", filters={"disable": 1}, pluck="name"))
	)
	return found


def run():
	frappe.only_for("System Manager")
	start = uit.check()
	assert start["ok"], f"The site is not clean before the run: {start['leftovers']}"
	before = _site_image()

	uit.seed()
	first = _inventory()
	assert any(doctype == "Item" for doctype, _ in first), "seed created no items"
	second_result = uit.seed()
	second = _inventory()
	assert not second_result["created"], f"second seed created {second_result['created']}"
	assert not second_result["disabled_live_rules"], "second seed disabled more rules"
	assert not second_result["ff_settings_changed"], "second seed changed F&F Settings"
	changed = {key for key in first.keys() | second.keys() if first.get(key) != second.get(key)}
	assert not changed, f"second seed changed: {sorted(changed)}"

	result = uit.teardown()
	assert not result["errors"], f"teardown errors: {result['errors']}"
	end = uit.check()
	assert end["ok"], f"leftovers after teardown: {end['leftovers']}"
	after = _site_image()
	assert after == before, "settings not restored: " + ", ".join(
		k for k in before if before.get(k) != after.get(k)
	)
	print("ui_test_seed self-check passed")
	return True
