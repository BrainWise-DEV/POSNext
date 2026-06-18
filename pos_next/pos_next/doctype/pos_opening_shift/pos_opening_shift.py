# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class POSOpeningShift(Document):
	def validate(self):
		self.validate_pos_profile_and_cashier()
		self.set_status()

	def validate_pos_profile_and_cashier(self):
		if self.company != frappe.db.get_value("POS Profile", self.pos_profile, "company"):
			frappe.throw(_(f"POS Profile {self.pos_profile} does not belongs to company {self.company}"))

		if not cint(frappe.db.get_value("User", self.user, "enabled")):
			frappe.throw(_(f"User {self.user} has been disabled. Please select valid user/cashier"))

	def on_submit(self):
		self.set_status(update=True)

	def set_status(self, update=False):
		"""Set the status of the opening shift"""
		if self.docstatus == 0:
			status = "Draft"
		elif self.docstatus == 1:
			if self.pos_closing_shift:
				status = "Closed"
			else:
				status = "Open"
		else:
			status = "Cancelled"

		if update:
			frappe.db.set_value("POS Opening Shift", self.name, "status", status)
		else:
			self.status = status
