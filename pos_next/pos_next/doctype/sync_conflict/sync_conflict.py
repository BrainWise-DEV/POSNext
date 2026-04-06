# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncConflict(Document):
	"""Manual-resolution queue entry for sync conflicts."""
	pass
