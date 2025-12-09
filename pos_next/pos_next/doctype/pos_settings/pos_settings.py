# Copyright (c) 2025, Youssef Restom and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class POSSettings(Document):
	def validate(self):
		"""Validate POS Settings"""
		self._validate_discount()
		self._validate_search_limit()

	def _validate_discount(self):
		max_discount = flt(self.max_discount_allowed)
		if max_discount < 0 or max_discount > 100:
			frappe.throw("Max Discount Allowed must be between 0 and 100")

	def _validate_search_limit(self):
		if self.use_limit_search:
			search_limit = cint(self.search_limit)
			if search_limit <= 0:
				frappe.throw("Search Limit must be greater than 0")

	def on_update(self):
		"""Sync allow_negative_stock with Stock Settings"""
		self.sync_negative_stock_setting()

	def sync_negative_stock_setting(self):
		"""
		Synchronize allow_negative_stock with Stock Settings.
		"""
		current_stock_setting = cint(
			frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
		)

		if cint(self.allow_negative_stock):
			if not current_stock_setting:
				frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1, update_modified=False)
				frappe.msgprint(
					"Stock Settings 'Allow Negative Stock' has been automatically enabled.",
					indicator="green",
					alert=True
				)
		else:
			if current_stock_setting:
				other_enabled_count = frappe.db.count(
					"POS Settings",
					{
						"allow_negative_stock": 1,
						"enabled": 1,
						"name": ["!=", self.name]
					}
				)

				if other_enabled_count == 0:
					frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0, update_modified=False)
					frappe.msgprint(
						"Stock Settings 'Allow Negative Stock' has been automatically disabled.",
						indicator="orange",
						alert=True
					)


@frappe.whitelist()
def get_pos_settings(pos_profile: str):
	"""
	Get POS Settings for a specific POS Profile.
	"""
	from frappe import _

	if not pos_profile:
		return None

	_check_pos_profile_access(pos_profile, "read")

	settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile},
		"*",
		as_dict=True
	)

	if not settings:
		settings = _create_new_settings(pos_profile)

	settings["_global_allow_negative_stock"] = cint(
		frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0
	)

	return settings

def _check_pos_profile_access(pos_profile, ptype="read"):
	has_access = frappe.db.exists(
		"POS Profile User",
		{"parent": pos_profile, "user": frappe.session.user}
	)
	if not has_access and not frappe.has_permission("POS Settings", ptype):
		frappe.throw(frappe._(f"You don't have {ptype} access to this POS Profile"))

def _create_new_settings(pos_profile):
	doc = frappe.new_doc("POS Settings")
	doc.pos_profile = pos_profile
	doc.enabled = 1
	doc.insert()
	return doc.as_dict()

@frappe.whitelist()
def update_pos_settings(pos_profile: str, settings):
	"""Update POS Settings for a POS Profile"""
	import json

	if isinstance(settings, str):
		settings = json.loads(settings)

	_check_pos_profile_access(pos_profile, "write")

	# Validate updated fields safety (optional, add if specific restricted fields exist)

	existing = frappe.db.exists("POS Settings", {"pos_profile": pos_profile})

	if existing:
		doc = frappe.get_doc("POS Settings", existing)
		doc.update(settings)
		doc.save()
	else:
		doc = frappe.new_doc("POS Settings")
		doc.pos_profile = pos_profile
		doc.update(settings)
		doc.insert()

	return doc.as_dict()
