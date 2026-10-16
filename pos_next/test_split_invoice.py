# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Pure helpers of pos_next.api.split_invoice (no database needed)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import split_invoice
from pos_next.api.split_invoice import (
	_allocate_payments,
	_allocate_rows,
	_prorate,
	_split_row,
	check_allocation,
)


class TestProrate(unittest.TestCase):
	def test_shares_follow_weights(self):
		self.assertEqual(_prorate(1000, [3, 1]), [750.0, 250.0])

	def test_rounding_remainder_lands_on_first_share(self):
		shares = _prorate(100, [1, 1, 1])
		self.assertEqual(shares, [33.34, 33.33, 33.33])
		self.assertAlmostEqual(sum(shares), 100)

	def test_nothing_to_share(self):
		self.assertEqual(_prorate(0, [1, 2]), [0.0, 0.0])
		self.assertEqual(_prorate(100, [0, 0]), [0.0, 0.0])


class TestAllocatePayments(unittest.TestCase):
	def test_secondary_invoice_paid_exactly_primary_keeps_change(self):
		payments = [{"mode_of_payment": "Cash", "amount": 250, "type": "Cash"}]
		rows = _allocate_payments(payments, [150, 80])
		self.assertEqual(rows[1], [{"mode_of_payment": "Cash", "amount": 80, "type": "Cash"}])
		self.assertEqual(rows[0], [{"mode_of_payment": "Cash", "amount": 170, "type": "Cash"}])

	def test_modes_shared_in_basket_proportions(self):
		payments = [
			{"mode_of_payment": "Cash", "amount": 200, "type": "Cash"},
			{"mode_of_payment": "Card", "amount": 50, "type": "Bank"},
		]
		rows = _allocate_payments(payments, [170, 80])
		self.assertEqual([(r["mode_of_payment"], r["amount"]) for r in rows[1]], [("Cash", 64), ("Card", 16)])
		self.assertEqual(
			[(r["mode_of_payment"], r["amount"]) for r in rows[0]], [("Cash", 136), ("Card", 34)]
		)

	def test_down_payment_never_pays_more_than_was_tendered(self):
		payments = [{"mode_of_payment": "Cash", "amount": 50, "type": "Cash"}]
		rows = _allocate_payments(payments, [150, 80, 40])
		self.assertEqual(rows[1], [{"mode_of_payment": "Cash", "amount": 50, "type": "Cash"}])
		self.assertEqual((rows[0], rows[2]), ([], []))

	def test_nothing_paid_leaves_every_invoice_without_payments(self):
		self.assertEqual(_allocate_payments([], [150, 80]), [[], []])

	def test_single_invoice_takes_everything(self):
		payments = [{"mode_of_payment": "Cash", "amount": 100, "type": "Cash"}]
		self.assertEqual(
			_allocate_payments(payments, [100]),
			[[{"mode_of_payment": "Cash", "amount": 100, "type": "Cash"}]],
		)


class TestSplitRow(unittest.TestCase):
	def row(self, **overrides):
		return {
			"item_code": "A",
			"qty": 25,
			"uom": "PCS",
			"conversion_factor": 1,
			"warehouse": "W1",
			"discount_amount": 250,
			**overrides,
		}

	def test_spills_to_next_warehouse_and_prorates_row_discount(self):
		remaining = {"W1": 20, "W2": 10}
		rows = _split_row(self.row(), ["W1", "W2"], remaining, set())
		self.assertEqual(
			[(r["warehouse"], r["qty"], r["discount_amount"]) for r in rows], [("W1", 20, 200), ("W2", 5, 50)]
		)
		self.assertEqual(remaining, {"W1": 0, "W2": 5})

	def test_shortfall_stays_on_first_warehouse(self):
		rows = _split_row(self.row(qty=5), ["W1", "W2"], {"W1": 1, "W2": 1}, set())
		self.assertEqual([(r["warehouse"], r["qty"]) for r in rows], [("W1", 4), ("W2", 1)])

	def test_whole_number_uom_is_not_split_into_fractions(self):
		rows = _split_row(
			self.row(qty=2, uom="BOX", conversion_factor=12), ["W1", "W2"], {"W1": 18, "W2": 24}, {"BOX"}
		)
		self.assertEqual([(r["warehouse"], r["qty"]) for r in rows], [("W1", 1), ("W2", 1)])

	def test_add_on_key_stays_on_first_chunk_only(self):
		rows = _split_row(self.row(custom_addon_key="k1"), ["W1", "W2"], {"W1": 20, "W2": 10}, set())
		self.assertEqual([r.get("custom_addon_key") for r in rows], ["k1", None])

	def test_tinting_stays_on_first_chunk_only(self):
		row = self.row(custom_hpp_tinta=15000, custom_tinting_job="J-1")
		rows = _split_row(row, ["W1", "W2"], {"W1": 20, "W2": 10}, set())
		self.assertEqual(
			[(r.get("custom_hpp_tinta"), r.get("custom_tinting_job")) for r in rows],
			[(15000, "J-1"), (None, None)],
		)


class TestAllocateRows(unittest.TestCase):
	"""The cart keeps one row per item + UOM: 2 sabun added from the store and
	2 picked by hand from the other warehouse arrive as one row of 4."""

	def allocate(self, rows, store_first=False, stock=None):
		stock = stock or {"TOKO": 2, "GUDANG": 10}
		with (
			patch.object(
				split_invoice,
				"get_session_scope",
				return_value={"branch": ["TOKO", "GUDANG"], "native": "TOKO"},
			),
			patch.object(
				split_invoice, "get_session_stock", return_value={"SABUN": {"stock_by_warehouse": stock}}
			),
			patch.object(
				split_invoice, "_warehouse_order", side_effect=lambda code, branch, native: ["TOKO", "GUDANG"]
			),
			patch.object(split_invoice, "store_stock_first", return_value=store_first),
			patch.object(split_invoice.frappe, "get_all", return_value=[]),
		):
			_allocate_rows(rows, SimpleNamespace(name="Kasir"))
		return [(r["warehouse"], r["qty"]) for r in rows]

	def row(self, **overrides):
		return {"item_code": "SABUN", "qty": 4, "uom": "PCS", "conversion_factor": 1, **overrides}

	def test_hand_picked_branch_warehouse_no_longer_pins_the_whole_row(self):
		rows = [self.row(warehouse="GUDANG", warehouse_manual=1)]
		self.assertEqual(self.allocate(rows, stock={"TOKO": 2, "GUDANG": 2}), [("GUDANG", 2), ("TOKO", 2)])

	def test_hand_picked_branch_warehouse_is_drawn_first(self):
		rows = [self.row(warehouse="GUDANG", warehouse_manual=1)]
		self.assertEqual(self.allocate(rows), [("GUDANG", 4)])

	def test_store_stock_first_empties_the_store_before_the_pick(self):
		rows = [self.row(warehouse="GUDANG", warehouse_manual=1)]
		self.assertEqual(self.allocate(rows, store_first=True), [("TOKO", 2), ("GUDANG", 2)])

	def test_hand_picked_warehouse_outside_the_branch_is_kept(self):
		rows = [self.row(warehouse="LUAR", warehouse_manual=1)]
		self.assertEqual(self.allocate(rows), [("LUAR", 4)])

	def test_hand_picked_warehouse_outside_the_branch_supplies_what_the_store_cannot(self):
		rows = [self.row(qty=3, warehouse="LUAR", warehouse_manual=1)]
		self.assertEqual(
			self.allocate(rows, store_first=True, stock={"TOKO": 2, "GUDANG": 0}),
			[("TOKO", 2), ("LUAR", 1)],
		)

	def test_add_on_ships_from_its_base_rows_first_chunk(self):
		rows = [
			self.row(warehouse="GUDANG", custom_addon_key="k"),
			{"item_code": "TINTA", "qty": 1, "warehouse": "GUDANG", "custom_addon_parent_key": "k"},
		]
		self.assertEqual(self.allocate(rows, store_first=True), [("TOKO", 2), ("GUDANG", 2), ("TOKO", 1)])


class TestCheckAllocation(unittest.TestCase):
	rows = (
		{"item_code": "SABUN", "qty": 2, "conversion_factor": 1, "warehouse": "TOKO"},
		{"item_code": "SABUN", "qty": 1, "conversion_factor": 1, "warehouse": "GUDANG"},
		{"item_code": "TINTA", "qty": 1, "warehouse": "TOKO", "custom_addon_parent_key": "k"},
	)

	def test_same_split_as_the_cart_passes(self):
		check_allocation(self.rows, [["SABUN", "TOKO", 2], ["SABUN", "GUDANG", 1]])

	def test_split_the_cart_did_not_show_is_refused(self):
		with self.assertRaises(split_invoice.frappe.ValidationError):
			check_allocation(self.rows, [["SABUN", "GUDANG", 3]])


if __name__ == "__main__":
	unittest.main()
