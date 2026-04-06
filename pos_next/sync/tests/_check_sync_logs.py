import frappe


def check():
	logs = frappe.get_all(
		"Sync Log",
		fields=["operation", "status", "duration_ms", "records_touched", "error", "creation"],
		order_by="creation desc",
		limit_page_length=10,
	)
	print(f"Sync Logs: {len(logs)} total")
	for log in logs:
		print(f"  {log.creation}: {log.operation} — {log.status}, {log.records_touched} records, {log.duration_ms}ms")
		if log.error:
			print(f"    error: {log.error[:200]}")

	wm_count = frappe.db.count("Sync Watermark")
	print(f"\nWatermarks: {wm_count}")

	cfg = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, ["last_pull_masters_at", "last_sync_error"], as_dict=True)
	if cfg:
		print(f"Last pull: {cfg.last_pull_masters_at}")
		if cfg.last_sync_error:
			print(f"Last error: {cfg.last_sync_error[:200]}")
