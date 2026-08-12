# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from pos_next.authorization import policy, registry


class POSAuthorizationRule(Document):

	def validate(self):
		self.validate_action()
		policy.validate_approvers(self)
		policy.validate_conditions(self)

	def validate_action(self):
		if not self.action:
			return

		if not registry.get(self.action):
			frappe.throw(
				_("{0} is not a registered authorization action.").format(frappe.bold(self.action)),
				title=_("Unknown Action"),
			)
