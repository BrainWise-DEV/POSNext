# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Package API.

A POS Package ("Paket") sells a fixed set of items plus customer-chosen options
under one price. On the invoice it materialises as:

- one **parent** row (the non-stock package item) carrying the whole price, and
- one **component** row per included/chosen item at rate 0.

Stock therefore moves on the components while revenue sits on the parent line.

Pricing is ``base_price + sum(option.price_adjustment * qty)``.

The quote is computed here on the server and mirrored byte-for-byte by
``POS/src/utils/packageQuote.js`` so the POS can price packages while offline.
``validate_invoice_packages`` re-quotes every package on the Sales Invoice, so a
tampered or stale client payload can never set its own price.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

PARENT_ROLE = "Package"
COMPONENT_ROLE = "Package Item"

INSTANCE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,140}$")


def _parse_json(value, default):
	if value is None or value == "":
		return default
	if isinstance(value, str):
		try:
			return json.loads(value)
		except (ValueError, TypeError):
			frappe.throw(_("Malformed package payload."))
	return value


def _assert_profile_access(pos_profile):
	"""Reject callers who aren't assigned to this POS Profile.

	Both whitelisted endpoints take `pos_profile` straight from the caller, so
	without this any logged-in user could read another outlet's packages and
	pricing. Mirrors pos_next.api.pos_profile.get_pos_profile_data.
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	if frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": frappe.session.user}):
		return

	if frappe.has_permission("POS Profile", "write"):
		return

	frappe.throw(_("You don't have access to this POS Profile"), frappe.PermissionError)


def _package_is_valid_on(package, on_date):
	if package.get("valid_from") and getdate(on_date) < getdate(package["valid_from"]):
		return False
	if package.get("valid_upto") and getdate(on_date) > getdate(package["valid_upto"]):
		return False
	return True


def _serialize_package(doc):
	"""Full package definition — enough for the POS to render and price offline."""
	component_codes = {row.item_code for row in doc.items or []}
	component_codes |= {row.item_code for row in doc.options or []}
	stock_flags = (
		{
			code: cint(flag)
			for code, flag in frappe.get_all(
				"Item",
				filters={"name": ["in", list(component_codes)]},
				fields=["name", "is_stock_item"],
				as_list=True,
			)
		}
		if component_codes
		else {}
	)

	return {
		"name": doc.name,
		"package_name": doc.package_name,
		"parent_item": doc.parent_item,
		"base_price": flt(doc.base_price),
		"currency": doc.currency,
		"company": doc.company,
		"description": doc.description,
		"valid_from": str(doc.valid_from) if doc.valid_from else None,
		"valid_upto": str(doc.valid_upto) if doc.valid_upto else None,
		"items": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": flt(row.qty),
				"uom": row.uom,
				"is_stock_item": stock_flags.get(row.item_code, 1),
			}
			for row in doc.items or []
		],
		"groups": [
			{
				"group_key": row.group_key,
				"label": row.label,
				"description": row.description,
				"min_qty": cint(row.min_qty),
				"max_qty": cint(row.max_qty),
			}
			for row in doc.groups or []
		],
		"options": [
			{
				"option_id": row.name,
				"group_key": row.group_key,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty_per_unit": flt(row.qty_per_unit) or 1.0,
				"uom": row.uom,
				"price_adjustment": flt(row.price_adjustment),
				"max_qty": cint(row.max_qty),
				"is_stock_item": stock_flags.get(row.item_code, 1),
			}
			for row in doc.options or []
		],
	}


def _eligible_package_names(pos_profile, on_date=None):
	"""Names of enabled, in-date packages available on this POS Profile.

	A package with no outlet rows is available to every profile of its company;
	otherwise the profile must be listed with ``enabled = 1``.
	"""
	profile = frappe.db.get_value("POS Profile", pos_profile, ["name", "company"], as_dict=True)
	if not profile:
		frappe.throw(_("POS Profile {0} not found.").format(frappe.bold(pos_profile)))

	on_date = on_date or nowdate()

	packages = frappe.get_all(
		"POS Package",
		filters={"disabled": 0, "company": profile.company},
		fields=["name", "valid_from", "valid_upto"],
	)
	if not packages:
		return []

	names = [p.name for p in packages]

	outlet_rows = frappe.get_all(
		"POS Package Outlet",
		filters={"parent": ["in", names], "parenttype": "POS Package"},
		fields=["parent", "pos_profile", "enabled"],
	)
	restricted = {row.parent for row in outlet_rows}
	allowed = {row.parent for row in outlet_rows if row.enabled and row.pos_profile == profile.name}

	return [
		p.name
		for p in packages
		if _package_is_valid_on(p, on_date) and (p.name not in restricted or p.name in allowed)
	]


@frappe.whitelist()
def get_packages(pos_profile, on_date=None):
	"""Return every package available on this profile, fully expanded.

	The POS caches this payload in IndexedDB so package selection and pricing keep
	working offline.
	"""
	_assert_profile_access(pos_profile)

	names = _eligible_package_names(pos_profile, on_date)
	return [_serialize_package(frappe.get_cached_doc("POS Package", name)) for name in names]


def _index_choices(choices):
	"""Normalise the client payload into ``{group_key: {option_id: qty}}``."""
	indexed = {}
	for entry in choices or []:
		group_key = (entry or {}).get("group_key")
		if not group_key:
			frappe.throw(_("Each selection must reference a group."))

		bucket = indexed.setdefault(group_key, {})
		for option in entry.get("options") or []:
			option_id = (option or {}).get("option_id")
			qty = cint((option or {}).get("qty"))
			if not option_id:
				frappe.throw(_("Each selection must reference an option."))
			if qty < 0:
				frappe.throw(_("Selected quantity cannot be negative."))
			if qty:
				bucket[option_id] = bucket.get(option_id, 0) + qty
	return indexed


def quote(package_name, choices, pos_profile, warehouse=None):
	"""Validate a selection and return the priced package (non-whitelisted core).

	Returns ``{package, package_name, total, currency, lines, snapshot}`` where
	``lines[0]`` is the parent row and the rest are components at rate 0.
	"""
	if package_name not in _eligible_package_names(pos_profile):
		frappe.throw(_("Package {0} is not available on this POS Profile.").format(frappe.bold(package_name)))

	doc = frappe.get_cached_doc("POS Package", package_name)
	indexed = _index_choices(choices)

	options_by_id = {row.name: row for row in doc.options or []}
	group_keys = {group.group_key for group in doc.groups or []}

	for group_key in indexed:
		if group_key not in group_keys:
			frappe.throw(_("Unknown choice group {0}.").format(frappe.bold(group_key)))

	total = flt(doc.base_price)
	component_lines = []
	snapshot_selections = []

	for group in doc.groups or []:
		picks = indexed.get(group.group_key, {})
		picked_qty = sum(picks.values())
		min_qty = cint(group.min_qty)
		max_qty = cint(group.max_qty)

		if picked_qty < min_qty:
			frappe.throw(_("Choose at least {0} item(s) from {1}.").format(min_qty, frappe.bold(group.label)))
		if picked_qty > max_qty:
			frappe.throw(_("Choose at most {0} item(s) from {1}.").format(max_qty, frappe.bold(group.label)))

		for option_id, qty in picks.items():
			option = options_by_id.get(option_id)
			if not option or option.group_key != group.group_key:
				frappe.throw(
					_("Option {0} does not belong to {1}.").format(option_id, frappe.bold(group.label))
				)

			option_max = cint(option.max_qty)
			if option_max and qty > option_max:
				frappe.throw(
					_("You can pick at most {0} x {1}.").format(
						option_max, frappe.bold(option.item_name or option.item_code)
					)
				)

			total += flt(option.price_adjustment) * qty

			component_lines.append(
				{
					"item_code": option.item_code,
					"item_name": option.item_name,
					"qty": (flt(option.qty_per_unit) or 1.0) * qty,
					"uom": option.uom,
					"rate": 0.0,
					"role": COMPONENT_ROLE,
					"is_stock_item": cint(frappe.db.get_value("Item", option.item_code, "is_stock_item")),
				}
			)
			snapshot_selections.append(
				{
					"group_key": group.group_key,
					"group_label": group.label,
					"option_id": option_id,
					"item_code": option.item_code,
					"item_name": option.item_name,
					"qty": qty,
					"price_adjustment": flt(option.price_adjustment),
				}
			)

	for row in doc.items or []:
		component_lines.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": flt(row.qty),
				"uom": row.uom,
				"rate": 0.0,
				"role": COMPONENT_ROLE,
				"is_stock_item": cint(frappe.db.get_value("Item", row.item_code, "is_stock_item")),
			}
		)

	if total < 0:
		frappe.throw(_("Package price cannot be negative."))

	total = flt(total, frappe.get_precision("Sales Invoice Item", "rate"))

	parent_line = {
		"item_code": doc.parent_item,
		"item_name": doc.package_name,
		"qty": 1,
		"rate": total,
		"role": PARENT_ROLE,
	}

	snapshot = {
		"package": doc.name,
		"package_name": doc.package_name,
		"base_price": flt(doc.base_price),
		"total": total,
		"selections": snapshot_selections,
		"included_items": [
			{"item_code": row.item_code, "item_name": row.item_name, "qty": flt(row.qty)}
			for row in doc.items or []
		],
	}

	return {
		"package": doc.name,
		"package_name": doc.package_name,
		"parent_item": doc.parent_item,
		"currency": doc.currency,
		"total": total,
		"lines": [parent_line, *component_lines],
		"snapshot": snapshot,
	}


@frappe.whitelist()
def quote_package(package, choices, pos_profile, warehouse=None):
	"""Server-authoritative price for a package selection."""
	_assert_profile_access(pos_profile)

	return quote(package, _parse_json(choices, []), pos_profile, warehouse)


def _group_invoice_rows_by_instance(doc):
	instances = {}
	for row in doc.get("items") or []:
		instance = row.get("pos_package_instance")
		if not instance:
			continue
		instances.setdefault(instance, []).append(row)
	return instances


def _recalculate_totals(doc):
	"""Recompute invoice totals after re-pricing package rows.

	Frappe runs the controller's own ``validate`` (which calculates taxes and
	totals) BEFORE app ``doc_events`` hooks, so correcting a rate here leaves
	grand_total holding the client's figure — a tampered payload would be
	repriced yet still charged the old amount. Recalculating closes that gap.
	"""
	# `frappe._dict` returns None for unknown keys, so hasattr() is not enough.
	recalculate = getattr(doc, "calculate_taxes_and_totals", None)
	if callable(recalculate):
		recalculate()


def _restore_return_package_metadata(doc):
	"""Rebuild package fields that the return payload never carries.

	``ReturnInvoiceDialog.vue`` builds its items from a fixed field whitelist, so
	``pos_package_instance`` / ``pos_package_role`` never reach the server. Without
	restoring them a credit note looks package-free and skips every guard below —
	letting the priced parent be refunded while its components are dropped.

	Membership is re-derived from the original invoice through
	``sales_invoice_item`` (the link ERPNext itself uses for return tracking), so
	the client never gets to declare which rows belong to a package.
	"""
	rows = doc.get("items") or []

	link_names = [
		row.sales_invoice_item
		for row in rows
		if not row.get("pos_package_instance") and row.get("sales_invoice_item")
	]

	if link_names:
		sources = frappe.get_all(
			"Sales Invoice Item",
			filters={"name": ["in", link_names], "parent": doc.get("return_against")},
			fields=[
				"name",
				"pos_package",
				"pos_package_instance",
				"pos_package_role",
				"pos_package_snapshot",
			],
		)
		by_name = {source["name"]: source for source in sources}

		for row in rows:
			source = by_name.get(row.get("sales_invoice_item"))
			if not source or not source.get("pos_package_instance"):
				continue

			row.pos_package = source["pos_package"]
			row.pos_package_instance = source["pos_package_instance"]
			row.pos_package_role = source["pos_package_role"]
			row.pos_package_snapshot = source["pos_package_snapshot"]

	for row in rows:
		if row.get("pos_package_instance") and not row.get("sales_invoice_item"):
			frappe.throw(
				_(
					"Package return rows must reference the original invoice row. Create the return from the POS Return screen."
				)
			)


def _validate_return_packages(doc):
	"""Force a package credit note to mirror the invoice it returns.

	A return cannot be re-quoted (its rows are copies), so it is checked against
	the original instead. Without this, two things are possible: raising the
	parent row's qty to refund more than was sold, and deleting the component
	rows to get the money back without returning any goods.
	"""
	if not doc.get("return_against"):
		if _group_invoice_rows_by_instance(doc):
			frappe.throw(_("A package return must reference the original invoice."))
		return

	_restore_return_package_metadata(doc)

	instances = _group_invoice_rows_by_instance(doc)
	if not instances:
		return

	precision = frappe.get_precision("Sales Invoice Item", "qty") or 3

	for instance, rows in instances.items():
		original_rows = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": doc.return_against, "pos_package_instance": instance},
			fields=["item_code", "qty", "rate", "pos_package_role"],
		)
		if not original_rows:
			frappe.throw(
				_("Package {0} does not exist on invoice {1}.").format(
					frappe.bold(instance), frappe.bold(doc.return_against)
				)
			)

		parents = [r for r in rows if r.get("pos_package_role") == PARENT_ROLE]
		original_parents = [r for r in original_rows if r.get("pos_package_role") == PARENT_ROLE]
		if len(parents) != 1 or len(original_parents) != 1:
			frappe.throw(_("Package {0} must have exactly one package line.").format(frappe.bold(instance)))

		parent = parents[0]
		original_parent = original_parents[0]

		original_parent_qty = flt(original_parent["qty"])
		if not original_parent_qty:
			frappe.throw(_("Package {0} has no quantity on the original invoice.").format(instance))

		# Returns are negative; compare magnitudes.
		fraction = abs(flt(parent.qty)) / abs(original_parent_qty)
		if fraction <= 0 or fraction > 1:
			frappe.throw(
				_("You cannot return more of {0} than was sold.").format(frappe.bold(parent.item_code))
			)

		parent.rate = flt(original_parent["rate"])
		parent.price_list_rate = flt(original_parent["rate"])
		parent.discount_amount = 0
		parent.discount_percentage = 0

		expected = {}
		for row in original_rows:
			if row.get("pos_package_role") != COMPONENT_ROLE:
				continue
			expected[row["item_code"]] = expected.get(row["item_code"], 0) + flt(row["qty"])

		submitted = {}
		for row in rows:
			if row.get("pos_package_role") != COMPONENT_ROLE:
				continue
			row.rate = 0
			row.price_list_rate = 0
			row.discount_amount = 0
			row.discount_percentage = 0
			submitted[row.item_code] = submitted.get(row.item_code, 0) + abs(flt(row.qty))

		# Every component must come back in the same proportion as the parent,
		# so a partial return stays consistent and none can be dropped.
		for item_code, original_qty in expected.items():
			wanted = flt(abs(original_qty) * fraction, precision)
			got = flt(submitted.get(item_code, 0), precision)
			if wanted != got:
				frappe.throw(
					_("Package {0}: return {1} x {2} to match the package being returned (got {3}).").format(
						frappe.bold(parent.item_code), wanted, frappe.bold(item_code), got
					)
				)

		for item_code in submitted:
			if item_code not in expected:
				frappe.throw(
					_("Package {0} does not contain {1}.").format(
						frappe.bold(parent.item_code), frappe.bold(item_code)
					)
				)

	_recalculate_totals(doc)


def validate_invoice_packages(doc, method=None):
	"""Re-price every package on the invoice from its stored selection.

	Hooked on Sales Invoice ``validate``. The client sends the chosen options; the
	rates come from here, never from the payload — so an edited offline queue or a
	crafted request cannot change what a package costs.
	"""
	if doc.get("is_return"):
		_validate_return_packages(doc)
		return

	instances = _group_invoice_rows_by_instance(doc)
	if not instances:
		return

	if not doc.get("pos_profile"):
		frappe.throw(_("Packages can only be sold from a POS Profile."))

	for instance, rows in instances.items():
		if not INSTANCE_PATTERN.match(instance):
			frappe.throw(_("Invalid package reference {0}.").format(frappe.bold(instance)))

		parents = [r for r in rows if r.get("pos_package_role") == PARENT_ROLE]
		if len(parents) != 1:
			frappe.throw(
				_("Package {0} must have exactly one package line, found {1}.").format(
					frappe.bold(instance), len(parents)
				)
			)

		parent = parents[0]
		package_name = parent.get("pos_package")
		if not package_name:
			frappe.throw(
				_("Package line {0} is missing its package reference.").format(frappe.bold(instance))
			)

		selections = _parse_json(parent.get("pos_package_snapshot"), {}).get("selections") or []
		choices = {}
		for selection in selections:
			choices.setdefault(selection.get("group_key"), []).append(
				{"option_id": selection.get("option_id"), "qty": cint(selection.get("qty"))}
			)

		result = quote(
			package_name,
			[{"group_key": key, "options": options} for key, options in choices.items()],
			doc.pos_profile,
		)

		# Authoritative price on the parent, zero on every component.
		parent.rate = result["total"]
		parent.price_list_rate = result["total"]
		parent.discount_amount = 0
		parent.discount_percentage = 0
		parent.qty = 1
		parent.pos_package_snapshot = json.dumps(result["snapshot"])

		expected = {}
		for line in result["lines"][1:]:
			expected[line["item_code"]] = expected.get(line["item_code"], 0) + flt(line["qty"])

		submitted = {}
		for row in rows:
			if row.get("pos_package_role") != COMPONENT_ROLE:
				continue
			row.rate = 0
			row.price_list_rate = 0
			row.discount_amount = 0
			row.discount_percentage = 0
			submitted[row.item_code] = submitted.get(row.item_code, 0) + flt(row.qty)

		if expected != submitted:
			frappe.throw(
				_("Package {0} contents do not match its definition. Please re-add the package.").format(
					frappe.bold(result["package_name"])
				)
			)

	_recalculate_totals(doc)
