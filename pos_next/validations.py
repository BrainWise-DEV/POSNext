# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _


def validate_item(doc, method):
	"""
	Validate Item doctype
	- Keep custom_company value as provided by user
	- Do not auto-fill defaults
	"""
	pass


@frappe.whitelist()
def item_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom query to filter items by company
	- If company is specified in filters, show matching company items only
	- If no company is specified, show items based on the current user's allowed companies
	"""
	import json
	from pos_next.company_isolation import get_user_companies

	# Parse filters if it's a string (when called from frontend)
	if isinstance(filters, str):
		filters = json.loads(filters)

	conditions = ["disabled = 0"]
	values = []

	if txt:
		conditions.append(f"({searchfield} LIKE %s OR item_name LIKE %s)")
		values.extend([f"%{txt}%", f"%{txt}%"])

	company = filters.get("company") if filters else None

	if company:
		conditions.append("(custom_company = %s OR custom_company IS NULL OR custom_company = '')")
		values.append(company)
	else:
		user_companies = get_user_companies()
		if user_companies:
			placeholders = ", ".join(["%s"] * len(user_companies))
			conditions.append(
				f"(custom_company IN ({placeholders}) OR custom_company IS NULL OR custom_company = '')"
			)
			values.extend(user_companies)

	query = f"""
		SELECT name, item_name, item_group
		FROM `tabItem`
		WHERE {' AND '.join(conditions)}
		ORDER BY
			CASE WHEN name LIKE %s THEN 0 ELSE 1 END,
			item_name
		LIMIT %s, %s
	"""

	values.extend([f"{txt}%", start, page_len])

	return frappe.db.sql(query, values)
