import frappe
from frappe import _

@frappe.whitelist()
def get_tables():
	"""Fetch all restaurant areas and tables."""
	areas = frappe.get_all("Restaurant Area", fields=["name", "area_name", "description"])
	tables = frappe.get_all("Restaurant Table", fields=["name", "table_name", "area", "capacity", "status"])
	return {
		"areas": areas,
		"tables": tables
	}

@frappe.whitelist()
def update_table_status(table_name, status):
	"""Update the status of a specific table."""
	if not frappe.has_permission("Restaurant Table", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Restaurant Table", table_name):
		frappe.throw(_("Table {0} not found").format(table_name))

	frappe.db.set_value("Restaurant Table", table_name, "status", status)
	return {"status": "success"}

@frappe.whitelist()
def update_kds_status(invoice_name, status):
	"""Update the KDS status of a sales invoice."""
	if not frappe.has_permission("Sales Invoice", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw(_("Invoice {0} not found").format(invoice_name))

	frappe.db.set_value("Sales Invoice", invoice_name, "kds_status", status)
	return {"status": "success"}

@frappe.whitelist()
def get_kds_orders():
	"""Fetch all pending and preparing orders for the KDS."""
	# Only fetch submitted invoices or drafts depending on how POS Next saves KDS orders.
	# Assuming here we fetch draft invoices that have a table and are not delivered.
	orders = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 0, # Drafts
			"is_pos": 1,
			"restaurant_table": ["is", "set"],
			"kds_status": ["in", ["Pending", "Preparing", "Ready"]]
		},
		fields=["name", "customer", "restaurant_table", "kds_status", "creation", "modified"]
	)

	for order in orders:
		order["items"] = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": order.name},
			fields=["item_code", "item_name", "qty", "description", "posa_special_instructions"]
		)

	return orders
