import frappe


def check():
	jobs = frappe.get_all(
		"Scheduled Job Type",
		filters={"method": ["like", "%pull_if_due%"]},
		fields=["name", "method", "frequency", "cron_format", "stopped"],
	)
	print(f"Scheduled Job Types for pull_if_due: {len(jobs)}")
	for j in jobs:
		print(f"  {j.name}: method={j.method}, freq={j.frequency}, cron={j.cron_format}, stopped={j.stopped}")

	# Also check all pos_next cron jobs
	all_pos = frappe.get_all(
		"Scheduled Job Type",
		filters={"method": ["like", "%pos_next%"]},
		fields=["name", "method", "frequency", "cron_format", "stopped"],
	)
	print(f"\nAll pos_next scheduled jobs: {len(all_pos)}")
	for j in all_pos:
		print(f"  {j.method} — freq={j.frequency}, cron={j.cron_format}, stopped={j.stopped}")
