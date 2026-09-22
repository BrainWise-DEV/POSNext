# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SalesPersonItemCommission(Document):
	def validate(self):
		rate = flt(self.commission_rate)
		if rate < 0 or rate > 100:
			frappe.throw(
				_("Commission Rate for Item {0} must be between 0 and 100").format(
					frappe.bold(self.item)
				)
			)

		if not self.parent or not self.item:
			return

		siblings = frappe.get_all(
			"Sales Person Item Commission",
			filters={
				"parent": self.parent,
				"parenttype": self.parenttype or "Sales Person",
				"item": self.item,
				"name": ["!=", self.name],
			},
			pluck="name",
			limit_page_length=1,
		)
		if siblings:
			frappe.throw(
				_("Commission for Item {0} is already defined for this Sales Person").format(
					frappe.bold(self.item)
				)
			)
