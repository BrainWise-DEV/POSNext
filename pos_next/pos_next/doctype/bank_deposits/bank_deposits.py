# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class BankDeposits(Document):
	def validate(self):
		if not self.posting_date:
			self.posting_date = today()

		self.validate_pos_profile()
		self.validate_pos_closing_shift()
		self.validate_deposit_amount()
		self.validate_bank_receipt()

	def validate_pos_profile(self):
		if frappe.db.get_value("POS Profile", self.pos_profile, "disabled"):
			frappe.throw(
				_("POS Profile {0} is not active").format(frappe.bold(self.pos_profile)),
				title=_("Invalid POS Profile"),
			)

	def validate_pos_closing_shift(self):
		shift = frappe.db.get_value(
			"POS Closing Shift",
			self.pos_closing_shift,
			["docstatus", "pos_profile", "pos_opening_shift"],
			as_dict=True,
		)
		if not shift:
			frappe.throw(_("POS Closing Shift {0} does not exist").format(self.pos_closing_shift))

		if shift.docstatus != 1:
			frappe.throw(_("POS Closing Shift must be submitted"))

		opening_status = frappe.db.get_value("POS Opening Shift", shift.pos_opening_shift, "status")
		if opening_status != "Closed":
			frappe.throw(_("POS Closing Shift must be closed"))

		if shift.pos_profile != self.pos_profile:
			frappe.throw(_("POS Closing Shift does not belong to the selected POS Profile"))

		existing = frappe.db.exists(
			"Bank Deposits",
			{
				"pos_closing_shift": self.pos_closing_shift,
				"name": ["!=", self.name],
				"docstatus": ["!=", 2],
			},
		)
		if existing:
			frappe.throw(
				_("Bank Deposit {0} already exists for this shift").format(frappe.bold(existing)),
				title=_("Duplicate Bank Deposit"),
			)

	def validate_deposit_amount(self):
		if flt(self.deposit_amount) <= 0:
			frappe.throw(_("Deposit Amount must be greater than zero"))

	def validate_bank_receipt(self):
		if not self.bank_transaction_doc:
			frappe.throw(_("Bank Transaction Document is required"))

	def on_submit(self):
		frappe.db.set_value(
			"POS Closing Shift",
			self.pos_closing_shift,
			"custom_bank_deposit",
			self.name,
			update_modified=False,
		)

	def on_cancel(self):
		frappe.db.set_value(
			"POS Closing Shift",
			self.pos_closing_shift,
			"custom_bank_deposit",
			None,
			update_modified=False,
		)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_pos_closing_shifts(doctype, txt, searchfield, start, page_len, filters):
	"""Return submitted, closed POS Closing Shifts without an existing Bank Deposit."""
	pos_profile = (filters or {}).get("pos_profile")
	profile_condition = "AND pcs.pos_profile = %(pos_profile)s" if pos_profile else ""

	return frappe.db.sql(
		f"""
		SELECT pcs.name
		FROM `tabPOS Closing Shift` pcs
		INNER JOIN `tabPOS Opening Shift` pos ON pos.name = pcs.pos_opening_shift
		WHERE pcs.docstatus = 1
			AND pos.status = 'Closed'
			AND pcs.name NOT IN (
				SELECT bd.pos_closing_shift
				FROM `tabBank Deposits` bd
				WHERE bd.docstatus != 2
					AND bd.pos_closing_shift IS NOT NULL
			)
			{profile_condition}
			AND pcs.name LIKE %(txt)s
		ORDER BY pcs.period_end_date DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"txt": f"%{txt}%",
			"start": start,
			"page_len": page_len,
			"pos_profile": pos_profile,
		},
	)
