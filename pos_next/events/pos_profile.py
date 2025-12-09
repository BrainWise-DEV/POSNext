# -*- coding: utf-8 -*-
# Copyright (c) 2024, POS Next and contributors
# For license information, please see license.txt

"""
Real-time event handlers for POS profile updates.
"""

import frappe
from frappe import _

def emit_pos_profile_updated_event(doc, method=None):
	"""
	Emit real-time event when POS Profile is updated.

	This event notifies all connected POS terminals about configuration changes,
	particularly item group filters, allowing them to clear their cache and reload
	items automatically without manual intervention.

	Args:
		doc: POS Profile document
		method: Hook method name (on_update, validate, etc.)
	"""
	try:
		# Check if item_groups have changed by comparing with the original doc
		if doc.has_value_changed("item_groups"):
			# Extract current item groups
			current_item_groups = [{"item_group": ig.item_group} for ig in doc.get("item_groups", [])]

			# Prepare event data
			event_data = {
				"pos_profile": doc.name,
				"item_groups": current_item_groups,
				"timestamp": frappe.utils.now(),
				"change_type": "item_groups_updated"
			}

			# Emit event to all connected clients
			# Event name: pos_profile_updated
			# Clients can subscribe to this event and invalidate their cache
			frappe.publish_realtime(
				event="pos_profile_updated",
				message=event_data,
				user=None,  # Broadcast to all users
				after_commit=True  # Only emit after successful DB commit
			)

			frappe.logger().info(
				f"Emitted pos_profile_updated event for {doc.name} - item groups changed"
			)

	except Exception as e:
		# Log error but don't fail the transaction
		frappe.log_error(
			title=_("Real-time POS Profile Update Event Error"),
			message=f"Failed to emit POS profile update event for {doc.name}: {str(e)}"
		)
