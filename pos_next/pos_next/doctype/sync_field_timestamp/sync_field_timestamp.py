# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncFieldTimestamp(Document):
	"""Per-field modification timestamp for Field-Level-LWW conflict resolution."""
	pass
