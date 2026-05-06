import frappe
from frappe.utils import nowdate


def _link_query(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	*,
	base_filters=None,
	or_filters=None,
	extra_fields=(),
	order_by=None,
):
	"""Reusable Link autocomplete query.

	Returns tuples (name, *extra_fields) — Frappe renders columns after `name`
	as the muted description text in the autocomplete dropdown.
	"""
	filters = dict(base_filters or {})
	filters[searchfield] = ("like", f"%{txt or ''}%")
	return frappe.db.get_all(
		doctype,
		filters=filters,
		or_filters=or_filters or None,
		fields=["name", *extra_fields],
		order_by=order_by,
		limit_start=start,
		limit_page_length=page_len,
		as_list=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_batches_for_item(doctype, txt, searchfield, start, page_len, filters):
	item = (filters or {}).get("item")
	if not item:
		return []
	return _link_query(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		base_filters={"item": item, "disabled": 0},
		or_filters=[
			["expiry_date", "is", "not set"],
			["expiry_date", ">=", nowdate()],
		],
		extra_fields=["expiry_date"],
		order_by="expiry_date asc",
	)
