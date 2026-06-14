# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, time_diff_in_hours, get_datetime


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	summary = get_summary(data)
	chart = get_chart_data(data)
	return columns, data, None, chart, summary


def get_columns():
	"""Return columns for the report"""
	return [
		{
			"fieldname": "offline_id",
			"label": _("Offline ID"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "sales_invoice",
			"label": _("Sales Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 150
		},
		{
			"fieldname": "pos_profile",
			"label": _("POS Profile"),
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 130
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150
		},
		{
			"fieldname": "status",
			"label": _("Sync Status"),
			"fieldtype": "Data",
			"width": 110
		},
		{
			"fieldname": "synced_at",
			"label": _("Synced At"),
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"fieldname": "invoice_created_at",
			"label": _("Invoice Created"),
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"fieldname": "sync_delay_hours",
			"label": _("Sync Delay (Hours)"),
			"fieldtype": "Float",
			"width": 150
		},
		{
			"fieldname": "health_status",
			"label": _("Health Status"),
			"fieldtype": "Data",
			"width": 130
		},
		{
			"fieldname": "error_message",
			"label": _("Error Message"),
			"fieldtype": "Text",
			"width": 200
		}
	]


def get_data(filters):
	"""Get offline sync and system health data"""
	conditions = get_conditions(filters)

	# Query to get offline sync records with related invoice data
	query = """
		SELECT
			ois.offline_id,
			ois.sales_invoice,
			ois.pos_profile,
			ois.customer,
			ois.status,
			ois.synced_at,
			si.creation as invoice_created_at,
			si.posting_date,
			si.owner as user
		FROM
			`tabOffline Invoice Sync` ois
		LEFT JOIN
			`tabSales Invoice` si ON si.name = ois.sales_invoice
		WHERE
			1=1
			{conditions}
		ORDER BY
			ois.synced_at DESC
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Calculate metrics for each record
	for row in data:
		# Calculate sync delay
		if row.synced_at and row.invoice_created_at:
			row.sync_delay_hours = flt(
				time_diff_in_hours(
					get_datetime(row.synced_at),
					get_datetime(row.invoice_created_at)
				),
				2
			)
		else:
			row.sync_delay_hours = None

		# Determine health status
		if row.status == "Failed":
			row.health_status = "🔴 Failed"
			# Try to get error from error log
			error_log = frappe.db.get_value(
				"Error Log",
				{
					"reference_doctype": "Offline Invoice Sync",
					"reference_name": row.offline_id
				},
				"error",
				order_by="creation desc"
			)
			row.error_message = error_log[:200] if error_log else "Sync failed"

		elif row.status == "Pending":
			row.health_status = "🟡 Pending"
			row.error_message = "Awaiting synchronization"

		elif row.status == "Synced":
			# Check sync delay
			if row.sync_delay_hours is not None:
				if row.sync_delay_hours > 24:
					row.health_status = "🟠 Delayed Sync"
					row.error_message = f"Synced after {row.sync_delay_hours:.1f} hours"
				elif row.sync_delay_hours > 1:
					row.health_status = "🟢 Synced (Slow)"
					row.error_message = f"Synced after {row.sync_delay_hours:.1f} hours"
				else:
					row.health_status = "✅ Synced"
					row.error_message = None
			else:
				row.health_status = "✅ Synced"
				row.error_message = None
		else:
			row.health_status = "❓ Unknown"
			row.error_message = "Unknown status"

	return data


def get_conditions(filters):
	"""Build WHERE conditions"""
	conditions = []

	if filters.get("from_date"):
		conditions.append("ois.synced_at >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("ois.synced_at <= %(to_date)s")

	if filters.get("pos_profile"):
		conditions.append("ois.pos_profile = %(pos_profile)s")

	if filters.get("status"):
		conditions.append("ois.status = %(status)s")

	if filters.get("user"):
		conditions.append("si.owner = %(user)s")

	return " AND " + " AND ".join(conditions) if conditions else ""


def get_summary(data):
	"""Generate summary statistics"""
	if not data:
		return []

	total_syncs = len(data)
	synced_count = len([d for d in data if d.status == "Synced"])
	failed_count = len([d for d in data if d.status == "Failed"])
	pending_count = len([d for d in data if d.status == "Pending"])

	# Calculate average sync delay for successful syncs
	sync_delays = [d.sync_delay_hours for d in data if d.sync_delay_hours is not None and d.status == "Synced"]
	avg_sync_delay = flt(sum(sync_delays) / len(sync_delays), 2) if sync_delays else 0

	# Calculate success rate
	success_rate = flt((synced_count / total_syncs) * 100, 2) if total_syncs > 0 else 0

	return [
		{
			"value": total_syncs,
			"label": "Total Sync Attempts",
			"indicator": "Blue",
			"datatype": "Int"
		},
		{
			"value": synced_count,
			"label": "Successfully Synced",
			"indicator": "Green",
			"datatype": "Int"
		},
		{
			"value": failed_count,
			"label": "Failed Syncs",
			"indicator": "Red" if failed_count > 0 else "Gray",
			"datatype": "Int"
		},
		{
			"value": pending_count,
			"label": "Pending Syncs",
			"indicator": "Yellow" if pending_count > 0 else "Gray",
			"datatype": "Int"
		},
		{
			"value": success_rate,
			"label": "Success Rate (%)",
			"indicator": "Green" if success_rate >= 95 else "Orange",
			"datatype": "Percent"
		},
		{
			"value": avg_sync_delay,
			"label": "Avg Sync Delay (Hours)",
			"indicator": "Green" if avg_sync_delay < 1 else "Orange",
			"datatype": "Float"
		}
	]


def get_chart_data(data):
	"""Generate chart showing sync status distribution"""
	if not data:
		return None

	# Count by status
	status_counts = {
		"Synced": 0,
		"Failed": 0,
		"Pending": 0
	}

	for row in data:
		if row.status in status_counts:
			status_counts[row.status] += 1

	return {
		"data": {
			"labels": list(status_counts.keys()),
			"datasets": [
				{
					"name": "Sync Records",
					"values": list(status_counts.values())
				}
			]
		},
		"type": "donut",
		"colors": ["#4CAF50", "#f44336", "#FFC107"]
	}
