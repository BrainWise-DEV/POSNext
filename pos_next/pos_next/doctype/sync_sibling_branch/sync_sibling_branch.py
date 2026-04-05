# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncSiblingBranch(Document):
	"""Read-only list entry for another branch, synced down from central."""
	pass
