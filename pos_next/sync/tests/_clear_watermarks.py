import frappe


def clear():
	frappe.db.delete("Sync Watermark")
	frappe.db.delete("Sync Record State")
	frappe.db.commit()
	print("Cleared all watermarks and record states")
