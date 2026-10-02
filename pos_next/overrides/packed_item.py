"""
Runtime patch for ERPNext packed item key matching.

Why this patch exists:
- POS Next saves Sales Invoice drafts multiple times during offer/payment flows.
- ERPNext's packed item matching can append duplicate bundle rows when keys are
  built from inconsistent identifiers across save cycles.
- We patch key generation to use a stable parent-row identifier.
"""

from __future__ import annotations


def patch_packed_item_keying(packed_item_module):
	"""Monkey-patch packed item keying to prevent duplicate bundle rows."""

	if getattr(packed_item_module, "_pos_next_packed_item_keying_patched", False):
		return

	original_get_indexed = packed_item_module.get_indexed_packed_items_table
	original_add_row = packed_item_module.add_packed_item_row

	def get_indexed_packed_items_table(doc):
		indexed_table = {}
		for packed_item in doc.get("packed_items"):
			parent_row_key = packed_item.parent_detail_docname or packed_item.idx
			key = (
				packed_item.parent_item,
				packed_item.item_code,
				parent_row_key,
			)
			indexed_table[key] = packed_item

		return indexed_table

	def add_packed_item_row(doc, packing_item, main_item_row, packed_items_table, reset):
		exists, pi_row = False, {}

		parent_row_key = main_item_row.name or main_item_row.idx
		key = (
			main_item_row.item_code,
			packing_item.item_code,
			parent_row_key,
		)
		if packed_items_table.get(key):
			pi_row, exists = packed_items_table.get(key), True

		if not exists:
			pi_row = doc.append("packed_items", {})
		elif reset:
			pi_row.idx, pi_row.name = None, None
			pi_row = doc.append("packed_items", pi_row)

		return pi_row

	# Keep a reference for traceability/debugging.
	packed_item_module._pos_next_original_get_indexed_packed_items_table = original_get_indexed
	packed_item_module._pos_next_original_add_packed_item_row = original_add_row
	packed_item_module.get_indexed_packed_items_table = get_indexed_packed_items_table
	packed_item_module.add_packed_item_row = add_packed_item_row
	packed_item_module._pos_next_packed_item_keying_patched = True
