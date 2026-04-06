import frappe


def check():
	"""Trigger pull_if_due and check results."""
	# Import adapters
	import pos_next.sync.adapters.item
	import pos_next.sync.adapters.item_price
	import pos_next.sync.adapters.customer
	import pos_next.sync.adapters.generic_master

	print("Calling pull_if_due...")
	from pos_next.sync.masters_puller import pull_if_due
	pull_if_due()
	frappe.db.commit()
	print("Done.")

	logs = frappe.get_all("Sync Log", fields=["operation", "status", "records_touched", "duration_ms", "creation"], order_by="creation desc", limit_page_length=5)
	print(f"\nSync Logs: {len(logs)}")
	for log in logs:
		print(f"  {log.creation}: {log.operation} — {log.status}, {log.records_touched} records, {log.duration_ms}ms")

	wm_count = frappe.db.count("Sync Watermark")
	print(f"Watermarks: {wm_count}")

	cfg = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "last_pull_masters_at")
	print(f"Last pull: {cfg}")
