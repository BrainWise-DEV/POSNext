import frappe


def check():
	"""Check scheduler status and try to trigger pull manually."""
	# Check scheduler
	paused = frappe.db.get_single_value("System Settings", "scheduler_inactive") or 0
	print(f"Scheduler paused: {paused}")

	# Check if our cron is registered
	from frappe.utils.scheduler import get_scheduler_events
	events = get_scheduler_events("cron")
	print(f"Cron events: {events}")

	# Try triggering pull_if_due directly
	print("\nManually calling pull_if_due...")
	from pos_next.sync.masters_puller import pull_if_due
	pull_if_due()
	frappe.db.commit()
	print("Done.")

	# Check logs now
	logs = frappe.get_all("Sync Log", fields=["operation", "status", "records_touched", "creation"], order_by="creation desc", limit_page_length=3)
	print(f"\nSync Logs after manual trigger: {len(logs)}")
	for log in logs:
		print(f"  {log.creation}: {log.operation} — {log.status}, {log.records_touched} records")

	cfg = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "last_pull_masters_at")
	print(f"Last pull: {cfg}")
