# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import os
import re

import frappe
from frappe import _
from frappe.model.document import Document


# Dev escape hatch: set POS_NEXT_SYNC_ALLOW_HTTP=1 in the environment to
# permit http:// central URLs (for local multi-site bench testing).
# Never set this in production.
_ALLOW_HTTP = os.environ.get("POS_NEXT_SYNC_ALLOW_HTTP") == "1"


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
