# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now

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


# Seconds a redemption waits for another sale holding the same (customer, rule) key
# before it is told "already used" (Ruling 114), instead of the server's default.
LOCK_WAIT_SECONDS = 5


def redeem(customer: str, pricing_rule: str, sales_invoice: str) -> bool:
	"""Record that ``customer`` uses ``pricing_rule`` on ``sales_invoice``.

	False when the rule is already redeemed on another invoice. The row's name is
	the (customer, rule) key, so a concurrent redemption of the same rule waits on
	this insert until it commits, then finds it taken; the locking read sees the
	latest committed row, not the transaction's snapshot. The wait is at most
	``LOCK_WAIT_SECONDS`` (then ``frappe.QueryTimeoutError``); the session's own
	lock wait is restored afterwards.

	The invoice may not be in the database yet: one call that inserts it already
	submitted (``frappe.client.insert`` with docstatus 1) redeems in its
	before_submit. So the row's links (invoice, customer, rule) are not checked:
	both callers pass values the server derived. The usage row is written in the
	invoice's own transaction and goes if it does.
	"""
	usage = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"customer": customer,
			"pricing_rule": pricing_rule,
			"sales_invoice": sales_invoice,
			"redemption_date": now(),
		}
	)
	usage.flags.ignore_links = True
	previous = frappe.db.sql("select @@session.innodb_lock_wait_timeout")[0][0]
	frappe.db.sql(f"set session innodb_lock_wait_timeout = {int(LOCK_WAIT_SECONDS)}")
	try:
		usage.insert(ignore_permissions=True, ignore_if_duplicate=True)
		holder = frappe.db.get_value(
			DOCTYPE, usage_name(customer, pricing_rule), "sales_invoice", for_update=True
		)
	finally:
		frappe.db.sql(f"set session innodb_lock_wait_timeout = {int(previous)}")
	return holder == sales_invoice
