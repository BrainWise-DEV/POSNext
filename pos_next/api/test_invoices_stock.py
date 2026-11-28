# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Unit tests for POS invoice stock validation aggregation keys."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pos_next.api.invoices import _collect_stock_errors


def _row(item_code, warehouse, qty, batch_no="", **extra):
	return {
		"item_code": item_code,
		"warehouse": warehouse,
		"qty": qty,
		"conversion_factor": 1,
		"batch_no": batch_no,
		**extra,
	}


class TestCollectStockErrorsBatchKey(unittest.TestCase):
	@patch("pos_next.api.invoices._get_item_negative_stock_allow_set", return_value=set())
	@patch("pos_next.api.invoices._get_available_stock")
	def test_does_not_oversell_by_checking_wrong_batch(self, mock_avail, _mock_allow):
		"""Demand on BATCH-A must not be validated against BATCH-B stock.

		Regression: aggregating only by (item_code, warehouse) summed both
		rows and compared the total to whichever sample row was last — often
		the larger batch — which allowed overselling the smaller batch.
		"""

		def avail(item):
			return {"BATCH-A": 3.0, "BATCH-B": 10.0}.get(item.get("batch_no") or "", 0.0)

		mock_avail.side_effect = avail

		errors = _collect_stock_errors(
			[
				_row("SKU-1", "Stores - X", 5, "BATCH-A"),
				_row("SKU-1", "Stores - X", 5, "BATCH-B"),
			]
		)

		self.assertEqual(len(errors), 1)
		self.assertEqual(errors[0]["item_code"], "SKU-1")
		self.assertEqual(errors[0]["batch_no"], "BATCH-A")
		self.assertEqual(errors[0]["requested_qty"], 5.0)
		self.assertEqual(errors[0]["available_qty"], 3.0)

	@patch("pos_next.api.invoices._get_item_negative_stock_allow_set", return_value=set())
	@patch("pos_next.api.invoices._get_available_stock")
	def test_same_batch_paid_and_free_rows_are_summed(self, mock_avail, _mock_allow):
		mock_avail.return_value = 3.0

		errors = _collect_stock_errors(
			[
				_row("SKU-1", "Stores - X", 2, "BATCH-A"),
				_row("SKU-1", "Stores - X", 2, "BATCH-A", is_free_item=1),
			]
		)

		self.assertEqual(len(errors), 1)
		self.assertEqual(errors[0]["batch_no"], "BATCH-A")
		self.assertEqual(errors[0]["requested_qty"], 4.0)
		self.assertEqual(errors[0]["available_qty"], 3.0)

	@patch("pos_next.api.invoices._get_item_negative_stock_allow_set", return_value=set())
	@patch("pos_next.api.invoices._get_available_stock")
	def test_non_batch_rows_still_aggregate_by_item_and_warehouse(self, mock_avail, _mock_allow):
		mock_avail.return_value = 5.0

		errors = _collect_stock_errors(
			[
				_row("SKU-1", "Stores - X", 3),
				_row("SKU-1", "Stores - X", 1, is_free_item=1),
			]
		)

		self.assertEqual(errors, [])
		mock_avail.assert_called_once()

		errors_over = _collect_stock_errors(
			[
				_row("SKU-1", "Stores - X", 4),
				_row("SKU-1", "Stores - X", 2, is_free_item=1),
			]
		)
		self.assertEqual(len(errors_over), 1)
		self.assertNotIn("batch_no", errors_over[0])
		self.assertEqual(errors_over[0]["requested_qty"], 6.0)
