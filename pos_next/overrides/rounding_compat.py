"""
Compatibility patch for mixed Frappe/ERPNext versions.

ERPNext may call Document.round_floats_in(..., do_not_round_fields=[...]),
while older Frappe versions only support round_floats_in(doc, fieldnames=None).
This patch adds backward-compatible handling in POS Next without core edits.
"""

from __future__ import annotations


def patch_round_floats_in_compat(document_module):
	"""Patch Document.round_floats_in to accept do_not_round_fields."""

	document_cls = document_module.Document
	if getattr(document_cls, "_pos_next_round_floats_in_compat_patched", False):
		return

	original_round_floats_in = document_cls.round_floats_in

	def _patched_round_floats_in(self, doc, fieldnames=None, do_not_round_fields=None):
		if fieldnames is None and do_not_round_fields:
			excluded = set(do_not_round_fields)
			fieldnames = [
				df.fieldname
				for df in doc.meta.get("fields", {"fieldtype": ["in", ["Currency", "Float", "Percent"]]})
				if df.fieldname not in excluded
			]

		return original_round_floats_in(self, doc, fieldnames=fieldnames)

	document_cls._pos_next_original_round_floats_in = original_round_floats_in
	document_cls.round_floats_in = _patched_round_floats_in
	document_cls._pos_next_round_floats_in_compat_patched = True
