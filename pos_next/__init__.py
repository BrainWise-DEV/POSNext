try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - frappe may not be installed during setup
	frappe = None

__version__ = "1.17.0"


def console(*data):
	"""Publish data to browser console for debugging"""
	if frappe:
		frappe.publish_realtime("toconsole", data, user=frappe.session.user)



# Frappe/ERPNext compatibility shim:
# ERPNext may pass do_not_round_fields to round_floats_in, but older Frappe
# versions don't accept that kwarg.
try:
	from frappe.model.document import Document

	from pos_next.overrides.frappe_compat import patch_round_floats_in_signature

	patch_round_floats_in_signature(Document)
except Exception:
	pass

# Patch packed item keying to avoid duplicate Product Bundle rows in Packed Items
# during repeated save/submit cycles in POS flows.
try:
	from erpnext.stock.doctype.packed_item import packed_item as packed_item_module

	from pos_next.overrides.packed_item import patch_packed_item_keying

	patch_packed_item_keying(packed_item_module)
except Exception:
	pass

# Patch Document.round_floats_in for ERPNext/Frappe compatibility:
# newer ERPNext may pass do_not_round_fields, while older Frappe
# only supports fieldnames.
try:
	from frappe.model import document as document_module

	from pos_next.overrides.rounding_compat import patch_round_floats_in_compat

	patch_round_floats_in_compat(document_module)
except Exception:
	pass

# Stop `bench run-tests` from wiping a working site's Item Prices. ERPNext's
# before_tests hook deletes the whole table with raw SQL and commits, leaving no
# Deleted Document trail. Opt in per site with `preserve_item_prices_in_tests`.
try:
	from erpnext.setup import utils as _erpnext_setup_utils

	from pos_next.overrides.test_setup_compat import patch_before_tests

	patch_before_tests(_erpnext_setup_utils)
except Exception:
	pass
