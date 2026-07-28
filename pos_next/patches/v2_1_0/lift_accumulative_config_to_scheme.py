# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Lift Accumulative config from the price discount slab up to the Scheme.

The slab table is hidden once ``pos_is_accumulative`` is on, which would strand
the qty/amount limits and the accumulative settings that used to be authored
there. They now live on the Promotional Scheme itself and are projected back
down on every validate (see ``normalize_accumulative_scheme``).

Existing schemes are migrated by copying the slab's values up and ticking the
checkbox, so a promotion that was live before the upgrade keeps its behaviour
instead of silently resetting to 0 / 1.
"""

import frappe
from frappe.utils import cint, flt

ACCUMULATIVE_MODE = "Accumulative"

# slab fieldname -> scheme fieldname
LIFTED_FIELDS = {
	"min_qty": "min_qty",
	"max_qty": "max_qty",
	"min_amount": "min_amount",
	"max_amount": "max_amount",
	"max_accumulated_discount_percentage": "max_accumulated_discount_percentage",
	"min_scopes_required": "min_scopes_required",
}


def execute():
	if not frappe.db.has_column("Promotional Scheme", "pos_is_accumulative"):
		return
	if not frappe.db.has_column("Promotional Scheme Price Discount", "apply_discount_on_price"):
		return

	slab_columns = [
		slab_field
		for slab_field in LIFTED_FIELDS
		if frappe.db.has_column("Promotional Scheme Price Discount", slab_field)
	]
	if not slab_columns:
		return

	slabs = frappe.get_all(
		"Promotional Scheme Price Discount",
		filters={"apply_discount_on_price": ACCUMULATIVE_MODE, "parenttype": "Promotional Scheme"},
		fields=["parent", *slab_columns],
	)
	if not slabs:
		return

	# One row per scheme; if a scheme somehow has several, the first wins — the
	# normalizer collapses it to a single row on the next save anyway.
	seen = set()
	for slab in slabs:
		scheme = slab.get("parent")
		if not scheme or scheme in seen:
			continue
		seen.add(scheme)

		values = {"pos_is_accumulative": 1}
		for slab_field in slab_columns:
			scheme_field = LIFTED_FIELDS[slab_field]
			raw = slab.get(slab_field)
			values[scheme_field] = (
				max(cint(raw) or 1, 1) if scheme_field == "min_scopes_required" else flt(raw)
			)

		frappe.db.set_value("Promotional Scheme", scheme, values, update_modified=False)

	frappe.db.commit()
