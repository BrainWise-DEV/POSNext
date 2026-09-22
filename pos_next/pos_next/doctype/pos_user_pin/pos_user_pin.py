# Copyright (c) 2026, POS Next contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class POSUserPIN(Document):
    def validate(self):
        if not self.user:
            frappe.throw(_("User is required."))

        user_enabled = frappe.db.get_value("User", self.user, "enabled")
        if not user_enabled:
            frappe.throw(_("POS PIN cannot be enabled for a disabled user."))

        # Frappe Password fields are encrypted in __Auth. During edits the
        # browser may send the masked sentinel; validate only a newly entered PIN.
        raw_pin = (self.pos_pin or "").strip()
        if raw_pin and set(raw_pin) != {"*"}:
            if not re.fullmatch(r"\d{4,6}", raw_pin):
                frappe.throw(_("POS PIN must contain 4 to 6 digits."))

        if self.enabled:
            try:
                existing_pin = self.get_password("pos_pin", raise_exception=False)
            except TypeError:
                existing_pin = self.get_password("pos_pin") if self.pos_pin else None
            if not raw_pin and not existing_pin:
                frappe.throw(_("Enter a POS PIN before enabling this record."))
