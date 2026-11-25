# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Report customers that share a verified email. Changes no data.

From this release a verified email belongs to one customer (enforced in
``pos_next.api.email_verification``). Rows verified before that may share an
address; they are listed in one Error Log for an administrator to review
(customer names grouped per shared email, with the email domain only).

Dry run: ``bench --site <site> execute
pos_next.patches.v2_5_0.report_duplicate_verified_emails.find_duplicates``
"""

import frappe
from frappe.query_builder.functions import Lower

LOG_TITLE = "Duplicate verified emails"


def find_duplicates() -> dict[str, list[str]]:
	"""{lowercased verified email: [customer names]} for emails verified on more than one customer."""
	if not frappe.get_meta("Customer").has_field("custom_verified_email"):
		return {}
	table = frappe.qb.DocType("Customer")
	email = Lower(table.custom_verified_email)
	rows = (
		frappe.qb.from_(table)
		.select(email.as_("email"), table.name)
		.where(table.custom_verified_email.isnotnull())
		.where(table.custom_verified_email != "")
		.orderby(email)
		.orderby(table.name)
		.run(as_dict=True)
	)
	grouped: dict[str, list[str]] = {}
	for row in rows:
		grouped.setdefault((row.email or "").strip(), []).append(row.name)
	return {key: names for key, names in grouped.items() if key and len(names) > 1}


def execute():
	duplicates = find_duplicates()
	if not duplicates:
		return
	# Domain only (no full addresses in Error Log); one line per shared email.
	lines = [f"{len(duplicates)} verified email(s) are shared by more than one customer:"]
	lines += [f"@{email.rpartition('@')[2]}: {', '.join(names)}" for email, names in duplicates.items()]
	frappe.log_error(title=LOG_TITLE, message="\n".join(lines))
