# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


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
		existing = frappe.db.sql(
			"""
			SELECT name FROM `tabSync Site Config`
			WHERE site_role = 'Branch' AND name != %s
			""",
			(self.name or "",),
		)
		if existing:
			frappe.throw(
				_(
					"Only one Sync Site Config with site_role=Branch is allowed "
					"per site. Existing record: {0}"
				).format(existing[0][0]),
				title=_("Branch Config Already Exists"),
			)

	def _validate_https_url(self):
		"""central_url must use https:// scheme."""
		if self.site_role != "Branch":
			return
		if not self.central_url:
			return
		if not self.central_url.startswith("https://"):
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
