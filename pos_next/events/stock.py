# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Real-time event handlers for stock updates.
"""

import frappe
from frappe import _

from pos_next.api.items import get_stock_quantities

def emit_stock_update_event(doc, method=None):
	"""
	Emit real-time stock update event when Sales Invoice is submitted.

	This event notifies all connected POS terminals about stock changes,
	allowing them to update their cached item quantities in real-time.

	Args:
		doc: Sales Invoice document
		method: Hook method name (on_submit, on_cancel, etc.)
	"""
	if not doc.update_stock:
		return

	# Skip if not a POS invoice (check if field exists first)
	if hasattr(doc, 'is_pos') and not doc.is_pos:
		return

	try:
		# Collect unique item codes per warehouse to avoid redundant queries
		item_codes_by_warehouse = {}
		for item in doc.items:
			item_code = getattr(item, "item_code", None)
			warehouse = getattr(item, "warehouse", None)

			# Skip rows that don't affect stock
			if not item_code or not warehouse:
				continue

			if hasattr(item, "is_stock_item") and item.is_stock_item is not None:
				if not int(item.is_stock_item):
					continue
			elif hasattr(item, "stock_qty") and not frappe.utils.flt(item.stock_qty):
				continue

			item_codes_by_warehouse.setdefault(warehouse, set()).add(item_code)

		if not item_codes_by_warehouse:
			return

		# Build stock updates with current quantities
		stock_updates = []
		warehouses = set()
		for warehouse, codes in item_codes_by_warehouse.items():
			warehouses.add(warehouse)
			# Use shared stock utility to keep logic consistent with API responses
			warehouse_updates = get_stock_quantities(list(codes), warehouse)

			# Ensure events always have numeric qty fields, even if API returns None
			for update in warehouse_updates:
				actual_qty = frappe.utils.flt(update.get("actual_qty"))
				update["actual_qty"] = actual_qty
				update["stock_qty"] = actual_qty if update.get("stock_qty") is None else update["stock_qty"]
				update["warehouse"] = update.get("warehouse") or warehouse

			stock_updates.extend(warehouse_updates)

		if not stock_updates:
			return

		# Prepare event data
		event_data = {
			"invoice_name": doc.name,
			"warehouses": list(warehouses),
			"stock_updates": stock_updates,
			"timestamp": frappe.utils.now(),
			"event_type": "cancel" if method == "on_cancel" else "submit"
		}

		# Emit event to all connected clients
		# Event name: pos_stock_update
		# Clients can subscribe to this event and filter by warehouse
		frappe.publish_realtime(
			event="pos_stock_update",
			message=event_data,
			user=None,  # Broadcast to all users
			after_commit=True  # Only emit after successful DB commit
		)

	except Exception as e:
		# Log error but don't fail the transaction
		frappe.log_error(
			title=_("Real-time Stock Update Event Error"),
			message=f"Failed to emit stock update event for {doc.name}: {str(e)}"
		)
