# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Real-time event handlers for invoice creation.
"""

import frappe
from frappe import _

def emit_invoice_created_event(doc, method=None):
	"""
	Emit real-time event when invoice is created.

	This can be used to notify other terminals about new sales,
	update dashboards, or trigger other real-time UI updates.

	Args:
		doc: Sales Invoice document
		method: Hook method name
	"""
	if not doc.is_pos:
		return

	try:
		event_data = {
			"invoice_name": doc.name,
			"grand_total": doc.grand_total,
			"customer": doc.customer,
			"pos_profile": doc.pos_profile,
			"timestamp": frappe.utils.now(),
		}

		frappe.publish_realtime(
			event="pos_invoice_created",
			message=event_data,
			user=None,
			after_commit=True
		)

	except Exception as e:
		frappe.log_error(
			title=_("Real-time Invoice Created Event Error"),
			message=f"Failed to emit invoice created event for {doc.name}: {str(e)}"
		)
