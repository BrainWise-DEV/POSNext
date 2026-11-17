# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

DOCTYPE = "One Time Customer Offer Usage"


class OneTimeCustomerOfferUsage(Document):
	pass


def usage_name(customer: str, pricing_rule: str) -> str:
	"""Name of the usage row for (customer, rule), built from the DocType's autoname format."""
	autoname = frappe.get_meta(DOCTYPE).autoname or ""
	return autoname.removeprefix("format:").format(customer=customer, pricing_rule=pricing_rule)


def is_redeemed(customer: str, pricing_rule: str) -> bool:
	"""True when ``customer`` has already used the one-time ``pricing_rule``."""
	return bool(frappe.db.exists(DOCTYPE, usage_name(customer, pricing_rule)))
