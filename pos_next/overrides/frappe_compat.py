"""Runtime compatibility patches for mixed Frappe/ERPNext versions."""

from __future__ import annotations

import inspect


def patch_round_floats_in_signature(document_class):
	"""Make Document.round_floats_in accept do_not_round_fields when missing.

	ERPNext (newer) calls:
	    doc.round_floats_in(row, do_not_round_fields=[...])

	Older Frappe implementations only accept:
	    round_floats_in(doc, fieldnames=None)
	"""

	original = getattr(document_class, "round_floats_in", None)
	if not original:
		return

	signature = inspect.signature(original)
	if "do_not_round_fields" in signature.parameters:
		return

	if getattr(document_class, "_pos_next_round_floats_signature_patched", False):
		return

	def round_floats_in(self, doc, fieldnames=None, do_not_round_fields=None):
		if do_not_round_fields:
			do_not_round_fields = set(do_not_round_fields)
			if fieldnames:
				fieldnames = [f for f in fieldnames if f not in do_not_round_fields]
			else:
				fieldnames = [
					df.fieldname
					for df in doc.meta.get(
						"fields", {"fieldtype": ["in", ["Currency", "Float", "Percent"]]}
					)
					if df.fieldname not in do_not_round_fields
				]

		return original(self, doc, fieldnames=fieldnames)

	document_class._pos_next_original_round_floats_in = original
	document_class.round_floats_in = round_floats_in
	document_class._pos_next_round_floats_signature_patched = True
