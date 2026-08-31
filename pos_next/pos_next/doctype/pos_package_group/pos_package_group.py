# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class POSPackageGroup(Document):
	"""A choice group inside a POS Package.

	The customer picks between ``min_qty`` and ``max_qty`` units in total across
	the group's options. ``min_qty == max_qty == 1`` means "pick exactly one";
	``min_qty = 0, max_qty = 3`` means "pick up to three, any mix".
	"""

	pass
