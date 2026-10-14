# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SalesPersonItemCommission(Document):
	# Frappe never calls validate() on child rows. Rate range and duplicate
	# checks run on the parent Sales Person instead: see
	# pos_next.pos_next.utils.sales_person_commission.validate_sales_person_commission_tables
	# (wired in hooks.py doc_events).
	pass
