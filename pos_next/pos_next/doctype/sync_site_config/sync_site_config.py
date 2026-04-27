# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import os
import re

import frappe
from frappe import _
from frappe.model.document import Document
from pos_next.sync.exceptions import SyncAuthError

# Dev escape hatch: set POS_NEXT_SYNC_ALLOW_HTTP=1 in the environment to
# permit http:// central URLs (for local multi-site bench testing).
# Never set this in production.
_ALLOW_HTTP = os.environ.get("POS_NEXT_SYNC_ALLOW_HTTP") == "1"

# Branch-prefixed naming series installed on every Branch site.
# The pattern is <PREFIX>-<branch_code>-.YYYY.-.##### — derived purely from

_BRANCH_NAMING_PREFIXES = {
	"Sales Invoice":         "SINV",
	"Payment Entry":         "PE",
	"POS Opening Shift":     "POS-OS",
	"POS Closing Shift":     "POS-CS",
	"Stock Entry":           "MAT-STE",
	"Delivery Note":         "MAT-DN",
	"Purchase Receipt":      "MAT-PRE",
	"Material Request":      "MAT-MR",
	"Stock Reconciliation":  "MAT-RECO",
}


class SyncSiteConfig(Document):
	"""
	Sync configuration record.

	Cardinality depends on site_role:
	- Branch: singleton (only one record allowed per site)
	- Central: multi-record (one per registered branch)
	"""

	def validate(self):
		self._validate_cardinality()
		self._validate_https_url()
		self._validate_branch_code()

	def _validate_cardinality(self):
		"""A Branch-role record must be singleton; Central allows many."""
		if self.site_role != "Branch":
			return
		# On insert self.name may not yet be set (before autoname runs);
		# on update self.name is the existing record's name. Either way,
		# we look for other Branch rows excluding this exact name.
		filters = {"site_role": "Branch"}
		if self.name:
			filters["name"] = ("!=", self.name)
		existing = frappe.db.get_value("Sync Site Config", filters, "name")
		if existing:
			frappe.throw(
				_(
					"Only one Sync Site Config with site_role=Branch is allowed "
					"per site. Existing record: {0}"
				).format(existing),
				title=_("Branch Config Already Exists"),
			)

	def _validate_https_url(self):
		"""central_url must use https:// scheme (unless dev bypass is set)."""
		if self.site_role != "Branch":
			return
		if not self.central_url:
			return
		if self.central_url.startswith("https://"):
			return
		if _ALLOW_HTTP and self.central_url.startswith("http://"):
			return
		frappe.throw(
			_("central_url must use https:// scheme, got: {0}").format(self.central_url),
			title=_("Insecure URL"),
		)

	def _validate_branch_code(self):
		"""branch_code must match [A-Z0-9]{2,16}."""
		if not self.branch_code:
			return
		if not re.match(r"^[A-Z0-9]{2,16}$", self.branch_code):
			frappe.throw(
				_("branch_code must be 2-16 uppercase letters/digits, got: {0}").format(
					self.branch_code
				),
				title=_("Invalid Branch Code"),
			)

	def after_insert(self):
		"""Seed the synced_doctypes registry with default rules."""
		from pos_next.sync.seeds import apply_seeds_to_config
		apply_seeds_to_config(self)

	def on_update(self):
		"""Install branch-prefixed naming series on transactional doctypes."""
		if self.site_role == "Branch":
			self._apply_branch_naming_series()

	def _apply_branch_naming_series(self):
		"""
		For each (DocType, prefix) in _BRANCH_NAMING_PREFIXES, install
		'<prefix>-<branch_code>-.YYYY.-.#####' as the default naming series.
		"""
		if not self.branch_code:
			return

		for doctype, prefix in _BRANCH_NAMING_PREFIXES.items():
			pattern = f"{prefix}-{self.branch_code}-.YYYY.-.#####"
			try:
				_install_naming_series(doctype, pattern, default=True)
			except Exception as e:
				frappe.log_error(
					"Sync Branch Naming Series",
					f"Failed to install '{pattern}' on {doctype}: {e}",
				)


def _install_naming_series(doctype, series, default=True):
	"""
	Append `series` to the doctype's `naming_series` Select options (via
	Property Setter) and optionally mark it the default.
	Idempotent: if the series is already present, only the default flag is
	updated.
	"""
	property_name = "options"
	field = "naming_series"

	ps_name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doctype, "field_name": field, "property": property_name},
		"name",
	)

	if ps_name:
		ps = frappe.get_doc("Property Setter", ps_name)
		current = (ps.value or "").splitlines()
		if series not in current:
			current.append(series)
			ps.value = "\n".join([s for s in current if s])
			ps.save(ignore_permissions=True)
	else:
		# Read the default options from the meta and prepend our series.
		meta = frappe.get_meta(doctype)
		df = meta.get_field(field)
		default_options = (df.options or "") if df else ""
		current = default_options.splitlines()
		if series not in current:
			current.append(series)
		frappe.get_doc({
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"doc_type": doctype,
			"field_name": field,
			"property": property_name,
			"property_type": "Text",
			"value": "\n".join([s for s in current if s]),
		}).insert(ignore_permissions=True)

	if default:
		frappe.db.set_default(f"{field}:{doctype}", series)

	@frappe.whitelist()
	def test_connection(self):
		"""
		Attempt authenticated API call against central and return a short status message.
		Only meaningful on Branch-role configs.
		"""
		if self.site_role != "Branch":
			return {"ok": False, "message": "Test Connection only applies to Branch role"}
		if not (self.central_url and self.sync_api_key and self.sync_api_secret):
			return {"ok": False, "message": "Fill central_url, sync_api_key, sync_api_secret first"}

		from pos_next.sync.auth import SyncSession
		from pos_next.sync.exceptions import SyncTransportError

		api_secret = self.get_password("sync_api_secret")
		session = SyncSession(
			central_url=self.central_url,
			api_key=self.sync_api_key,
			api_secret=api_secret,
		)
		try:
			resp = session.get("/api/method/frappe.auth.get_logged_user")
		except SyncAuthError as e:
			return {"ok": False, "message": f"Auth failed: {e}"}
		except SyncTransportError as e:
			return {"ok": False, "message": f"Network error: {e}"}
		except Exception as e:
			return {"ok": False, "message": f"Unexpected error: {e}"}
		return {"ok": True, "message": f"Connected to {self.central_url} with API key"}
