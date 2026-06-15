try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - frappe may not be installed during setup
	frappe = None

__version__ = "1.16.0"


def console(*data):
	"""Publish data to browser console for debugging"""
	if frappe:
		frappe.publish_realtime("toconsole", data, user=frappe.session.user)


# Patch get_other_conditions to exclude pos_only pricing rules from non-POS documents.
# No Frappe hook exists for non-whitelisted module-level functions (override_whitelisted_methods
# only works for @frappe.whitelist() HTTP endpoints, override_doctype_class only for DocType
# classes). This is the standard Python module init approach — runs once at import.
try:
	from erpnext.accounts.doctype.pricing_rule import utils as pr_utils

	from pos_next.overrides.pricing_rule import patch_get_other_conditions

	patch_get_other_conditions(pr_utils)
except Exception:
	pass

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
