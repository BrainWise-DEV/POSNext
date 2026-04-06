# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Central-side API: serve upserts + tombstones since a watermark."""

import frappe


@frappe.whitelist()
def changes_since(doctype, since, limit=100):
	"""
	Return records modified after `since` for the given DocType,
	plus any tombstones recorded after `since`.

	Response shape:
	{
	    "upserts": [{...}, ...],
	    "tombstones": [{"reference_name": ..., "deleted_at": ...}, ...],
	    "next_since": "2026-04-06 10:00:00",
	    "has_more": true|false
	}
	"""
	limit = int(limit)

	# Fetch limit+1 to detect has_more
	records = frappe.get_all(
		doctype,
		filters={"modified": (">", since)},
		order_by="modified asc",
		limit_page_length=limit + 1,
		fields=["name"],
	)

	has_more = len(records) > limit
	records = records[:limit]

	# Serialize each record fully (with children)
	upserts = []
	for row in records:
		try:
			doc = frappe.get_doc(doctype, row.name)
			payload = doc.as_dict(convert_dates_to_str=True)
			upserts.append(payload)
		except Exception:
			# Record may have been deleted between listing and fetching
			continue

	# Compute next_since from the last upsert's modified
	next_since = None
	if upserts:
		next_since = upserts[-1].get("modified")

	# Fetch tombstones
	tombstones = frappe.get_all(
		"Sync Tombstone",
		filters={
			"reference_doctype": doctype,
			"deleted_at": (">", since),
		},
		fields=["reference_name", "deleted_at"],
		order_by="deleted_at asc",
	)
	# Convert to plain dicts
	tombstones = [{"reference_name": t.reference_name, "deleted_at": str(t.deleted_at)} for t in tombstones]

	return {
		"upserts": upserts,
		"tombstones": tombstones,
		"next_since": next_since,
		"has_more": has_more,
	}
