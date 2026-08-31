# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate

GROUP_KEY_PATTERN = re.compile(r"^[a-z0-9_]+$")


def slugify_group_key(label, fallback_idx):
	"""Derive a stable, readable group key from a label."""
	slug = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")
	return slug or f"group_{fallback_idx}"


class POSPackage(Document):
	def validate(self):
		self.assign_group_keys()
		self.validate_dates()
		self.validate_price()
		self.validate_content()
		self.validate_groups()
		self.validate_options()
		self.validate_parent_item()
		self.validate_component_items()
		self.validate_outlets()

	def assign_group_keys(self):
		"""Fill blank group keys from the label and reject malformed/duplicate ones."""
		seen = set()
		for idx, group in enumerate(self.groups or [], start=1):
			if not group.group_key:
				group.group_key = slugify_group_key(group.label, idx)

			group.group_key = group.group_key.strip().lower()

			if not GROUP_KEY_PATTERN.match(group.group_key):
				frappe.throw(
					_(
						"Row {0}: Group Key {1} may only contain lowercase letters, digits and underscores."
					).format(group.idx, frappe.bold(group.group_key))
				)

			if group.group_key in seen:
				frappe.throw(
					_("Row {0}: Group Key {1} is used more than once.").format(
						group.idx, frappe.bold(group.group_key)
					)
				)
			seen.add(group.group_key)

	def validate_dates(self):
		if self.valid_from and self.valid_upto and getdate(self.valid_from) > getdate(self.valid_upto):
			frappe.throw(_("Valid Upto cannot be earlier than Valid From."))

	def validate_price(self):
		if flt(self.base_price) < 0:
			frappe.throw(_("Base Price cannot be negative."))

	def validate_content(self):
		if not (self.items or self.groups):
			frappe.throw(_("A package needs at least one included item or one choice group."))

	def validate_groups(self):
		for group in self.groups or []:
			min_qty = cint(group.min_qty)
			max_qty = cint(group.max_qty)

			if max_qty < 1:
				frappe.throw(
					_("Row {0}: Max Qty must be at least 1 for group {1}.").format(
						group.idx, frappe.bold(group.label)
					)
				)

			if min_qty > max_qty:
				frappe.throw(
					_("Row {0}: Min Qty cannot exceed Max Qty for group {1}.").format(
						group.idx, frappe.bold(group.label)
					)
				)

			options = [o for o in (self.options or []) if o.group_key == group.group_key]
			if not options:
				frappe.throw(
					_("Group {0} has no options. Add at least one option or remove the group.").format(
						frappe.bold(group.label)
					)
				)

			# The group is unsatisfiable when every option's own cap sums below min_qty.
			capacity = sum(cint(o.max_qty) or max_qty for o in options)
			if capacity < min_qty:
				frappe.throw(
					_("Group {0} requires {1} unit(s) but its options allow at most {2}.").format(
						frappe.bold(group.label), min_qty, capacity
					)
				)

	def validate_options(self):
		group_keys = {g.group_key for g in self.groups or []}
		for option in self.options or []:
			option.group_key = (option.group_key or "").strip().lower()

			if option.group_key not in group_keys:
				frappe.throw(
					_("Row {0}: Group Key {1} does not match any choice group.").format(
						option.idx, frappe.bold(option.group_key)
					)
				)

			if flt(option.qty_per_unit) <= 0:
				frappe.throw(_("Row {0}: Qty Per Unit must be greater than zero.").format(option.idx))

	def validate_parent_item(self):
		item = frappe.db.get_value(
			"Item",
			self.parent_item,
			["is_stock_item", "is_sales_item", "is_fixed_asset", "has_batch_no", "has_serial_no", "disabled"],
			as_dict=True,
		)
		if not item:
			frappe.throw(_("Package Item {0} does not exist.").format(frappe.bold(self.parent_item)))

		if item.disabled:
			frappe.throw(_("Package Item {0} is disabled.").format(frappe.bold(self.parent_item)))

		if not item.is_sales_item:
			frappe.throw(_("Package Item {0} must be a sales item.").format(frappe.bold(self.parent_item)))

		if item.is_stock_item:
			frappe.throw(
				_(
					"Package Item {0} must be a non-stock item — stock moves on the included items, not on the package line."
				).format(frappe.bold(self.parent_item))
			)

		if item.is_fixed_asset:
			frappe.throw(_("Package Item {0} cannot be a fixed asset.").format(frappe.bold(self.parent_item)))

		if item.has_batch_no or item.has_serial_no:
			frappe.throw(
				_("Package Item {0} cannot be batch or serial tracked.").format(frappe.bold(self.parent_item))
			)

		if frappe.db.exists("Product Bundle", {"new_item_code": self.parent_item, "disabled": 0}):
			frappe.throw(
				_(
					"Item {0} is already used by a Product Bundle. Use a dedicated item for the package."
				).format(frappe.bold(self.parent_item))
			)

	def validate_component_items(self):
		"""Included items and options must be sellable items distinct from the package item."""
		rows = [("items", row) for row in (self.items or [])]
		rows += [("options", row) for row in (self.options or [])]

		for table, row in rows:
			if row.item_code == self.parent_item:
				frappe.throw(
					_("Row {0}: {1} cannot contain the Package Item itself.").format(
						row.idx, _("Included Items") if table == "items" else _("Choice Options")
					)
				)

			item = frappe.db.get_value("Item", row.item_code, ["is_sales_item", "disabled"], as_dict=True)
			if not item:
				frappe.throw(
					_("Row {0}: Item {1} does not exist.").format(row.idx, frappe.bold(row.item_code))
				)
			if item.disabled:
				frappe.throw(_("Row {0}: Item {1} is disabled.").format(row.idx, frappe.bold(row.item_code)))
			if not item.is_sales_item:
				frappe.throw(
					_("Row {0}: Item {1} is not a sales item.").format(row.idx, frappe.bold(row.item_code))
				)

			if table == "items" and flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))

	def validate_outlets(self):
		seen = set()
		for outlet in self.outlets or []:
			if outlet.pos_profile in seen:
				frappe.throw(
					_("Row {0}: POS Profile {1} is listed more than once.").format(
						outlet.idx, frappe.bold(outlet.pos_profile)
					)
				)
			seen.add(outlet.pos_profile)

			profile_company = frappe.db.get_value("POS Profile", outlet.pos_profile, "company")
			if profile_company != self.company:
				frappe.throw(
					_("Row {0}: POS Profile {1} belongs to company {2}, not {3}.").format(
						outlet.idx,
						frappe.bold(outlet.pos_profile),
						frappe.bold(profile_company),
						frappe.bold(self.company),
					)
				)
