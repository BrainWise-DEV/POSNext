# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class POSPackageOption(Document):
	"""A selectable item inside a POS Package Group.

	``price_adjustment`` is added to the package base price for each unit picked;
	it may be negative. ``max_qty`` caps repeats of this single option (0 = only
	the group's own max applies).
	"""

	pass
