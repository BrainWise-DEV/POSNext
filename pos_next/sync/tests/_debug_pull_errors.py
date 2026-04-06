"""Debug the remaining Company and Item Group pull errors."""

import frappe
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.masters_puller import MastersPuller

# Import adapters
import pos_next.sync.adapters.item
import pos_next.sync.adapters.generic_master


def debug_company():
	"""Try pulling Company and print exact errors."""
	session = build_session_from_config()
	resp = session.get(
		"/api/method/pos_next.sync.api.changes.changes_since",
		params={"doctype": "Company", "since": "2000-01-01 00:00:00", "limit": 10},
	)
	data = resp.json().get("message", {})
	print(f"Company upserts from central: {len(data.get('upserts', []))}")
	for u in data.get("upserts", []):
		name = u.get("name")
		print(f"\n--- Company: {name} ---")
		try:
			from pos_next.sync.adapters.base import BaseSyncAdapter, _set_sync_flags
			from pos_next.sync.payload import strip_meta
			cleaned = strip_meta(u)
			if frappe.db.exists("Company", name):
				doc = frappe.get_doc("Company", name)
				_set_sync_flags(doc)
				for key, val in cleaned.items():
					if key not in ("doctype", "name", "modified", "modified_by", "creation", "owner") and not isinstance(val, list):
						doc.set(key, val)
				doc.save(ignore_permissions=True)
				print(f"  Updated OK")
			else:
				cleaned.pop("name", None)
				doc = frappe.get_doc({"doctype": "Company", "name": name, **cleaned})
				_set_sync_flags(doc)
				doc.insert(ignore_permissions=True)
				print(f"  Inserted OK")
			frappe.db.commit()
		except Exception as e:
			print(f"  ERROR: {e}")
			frappe.db.rollback()
	session.logout()


def debug_item_group():
	"""Try pulling Item Group and print exact errors."""
	session = build_session_from_config()
	resp = session.get(
		"/api/method/pos_next.sync.api.changes.changes_since",
		params={"doctype": "Item Group", "since": "2000-01-01 00:00:00", "limit": 20},
	)
	data = resp.json().get("message", {})
	print(f"Item Group upserts from central: {len(data.get('upserts', []))}")
	for u in data.get("upserts", []):
		name = u.get("name")
		print(f"\n--- Item Group: {name} ---")
		try:
			from pos_next.sync import registry
			adapter = registry.get_adapter("Item Group")
			if adapter:
				adapter.apply_incoming(u, "update")
			else:
				from pos_next.sync.adapters.base import BaseSyncAdapter, _set_sync_flags
				default = BaseSyncAdapter()
				default.doctype = "Item Group"
				default.apply_incoming(u, "update")
			frappe.db.commit()
			print(f"  OK")
		except Exception as e:
			print(f"  ERROR: {type(e).__name__}: {e}")
			frappe.db.rollback()
	session.logout()


def run_all():
	print("=== COMPANY ===")
	debug_company()
	print("\n=== ITEM GROUP ===")
	debug_item_group()
