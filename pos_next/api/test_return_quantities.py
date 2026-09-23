# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Regression tests for POS return quantity calculations."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pos_next.api.invoices import _resolve_prepared_return_quantities


def _flt(value, precision=None):
	if value is None:
		return 0.0
	value = float(value)
	return round(value, precision) if precision is not None else value


class TestPreparedReturnQuantities(unittest.TestCase):
	@patch("pos_next.api.invoices.flt", side_effect=_flt)
	def test_make_sales_return_remaining_qty_is_not_reduced_again(self, _mock_flt):
		item = {
			"item_code": "ITEM-1",
			"sales_invoice_item": "original-row-1",
			# make_sales_return() has already reduced 2.12 by the 0.02 previous return.
			"qty": -2.10,
		}

		original_qty, already_returned, remaining_qty = _resolve_prepared_return_quantities(
			item=item,
			returned_qty_map={"original-row-1": 0.02},
			original_qty_by_row={"original-row-1": 2.12},
			original_qty_by_item_code={"ITEM-1": 2.12},
			qty_precision=2,
		)

		self.assertEqual(original_qty, 2.12)
		self.assertEqual(already_returned, 0.02)
		self.assertEqual(remaining_qty, 2.10)

	@patch("pos_next.api.invoices.flt", side_effect=_flt)
	def test_falls_back_to_remaining_plus_returned_when_original_row_missing(self, _mock_flt):
		item = {"item_code": "ITEM-1", "qty": -2.10}

		original_qty, already_returned, remaining_qty = _resolve_prepared_return_quantities(
			item=item,
			returned_qty_map={"ITEM-1": 0.02},
			original_qty_by_row={},
			original_qty_by_item_code={},
			qty_precision=2,
		)

		self.assertEqual(original_qty, 2.12)
		self.assertEqual(already_returned, 0.02)
		self.assertEqual(remaining_qty, 2.10)


if __name__ == "__main__":
	unittest.main()
