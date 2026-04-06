# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Central-side API: serve upserts + tombstones since a watermark."""

import frappe
from pos_next.sync.payload import to_payload


@frappe.whitelist()
def changes_since(doctype, since, limit=100):
	"""
	Return records modified after `since` for the given DocType,
	plus any tombstones recorded after `since`.
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

	# N+1 is unavoidable here — we need full doc with children for each record.
	# The adapter's serialize() may need child tables.
	upserts = []
	for row in records:
		try:
			doc = frappe.get_doc(doctype, row.name)
			upserts.append(to_payload(doc))
		except frappe.DoesNotExistError:
			continue
		except Exception as e:
			frappe.log_error(f"changes_since serialize {doctype}/{row.name}: {e}", "Sync API")
			continue

	next_since = upserts[-1].get("modified") if upserts else None

	# Tombstones — bounded by same limit to prevent unbounded response
	tombstones = frappe.get_all(
		"Sync Tombstone",
		filters={"reference_doctype": doctype, "deleted_at": (">", since)},
		fields=["reference_name", "deleted_at"],
		order_by="deleted_at asc",
		limit_page_length=limit,
	)

	return {
		"upserts": upserts,
		"tombstones": [{"reference_name": t.reference_name, "deleted_at": str(t.deleted_at)} for t in tombstones],
		"next_since": next_since,
		"has_more": has_more,
	}
