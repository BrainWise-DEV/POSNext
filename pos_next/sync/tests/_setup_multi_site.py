"""
Setup helpers for the two-bench dev sync environment.

Topology:
  frappe-bench   (port 8000) → Central  (site: pos-central)
  frappe-bench-16 (port 8001) → Branch   (site: dev.pos)

Usage from each bench:
  # On frappe-bench (central):
  bench --site pos-central execute pos_next.sync.tests._setup_multi_site.setup_as_central

  # On frappe-bench-16 (branch):
  bench --site dev.pos execute pos_next.sync.tests._setup_multi_site.setup_as_branch

  # Show current config on either site:
  bench --site <site> execute pos_next.sync.tests._setup_multi_site.show_current

  # Cleanup:
  bench --site <site> execute pos_next.sync.tests._setup_multi_site.cleanup
"""
import frappe


CENTRAL_URL = "http://localhost:8000"
BRANCH_URL = "http://localhost:8001"
BRANCH_CODE = "CAI"


def setup_as_branch():
	"""Install Branch Sync Site Config on dev.pos pointing at pos-central."""
	frappe.db.delete("Sync Site Config")
	frappe.db.commit()
	doc = frappe.get_doc({
		"doctype": "Sync Site Config",
		"site_role": "Branch",
		"branch_code": BRANCH_CODE,
		"enabled": 1,
		"central_url": CENTRAL_URL,
		"sync_username": "Administrator",
		"sync_password": "admin",
		"push_interval_seconds": 60,
		"pull_masters_interval_seconds": 300,
		"pull_failover_interval_seconds": 120,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Branch config created: name={doc.name}, branch_code={BRANCH_CODE}, central={CENTRAL_URL}")


def setup_as_central():
	"""Install Central Sync Site Config on pos-central registering the CAI branch."""
	frappe.db.delete("Sync Site Config")
	frappe.db.commit()
	doc = frappe.get_doc({
		"doctype": "Sync Site Config",
		"site_role": "Central",
		"branch_code": BRANCH_CODE,
		"enabled": 1,
		"registered_branch_url": BRANCH_URL,
		"notes": f"Branch {BRANCH_CODE} (Cairo), running on frappe-bench-16 port 8001",
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"Central config created: name={doc.name}, branch_code={BRANCH_CODE}, branch_url={BRANCH_URL}")


def show_current():
	"""Print current Sync Site Config state."""
	rows = frappe.get_all(
		"Sync Site Config",
		fields=["name", "site_role", "branch_code", "enabled", "central_url", "registered_branch_url"],
	)
	print(f"Sync Site Configs on this site: {len(rows)}")
	for r in rows:
		print(f"  - {r.name}: role={r.site_role}, branch_code={r.branch_code}, enabled={r.enabled}")
		if r.central_url:
			print(f"    central_url={r.central_url}")
		if r.registered_branch_url:
			print(f"    registered_branch_url={r.registered_branch_url}")


def cleanup():
	"""Remove all Sync Site Config rows."""
	frappe.db.delete("Sync Site Config")
	frappe.db.commit()
	print("Cleaned up all Sync Site Config rows")
