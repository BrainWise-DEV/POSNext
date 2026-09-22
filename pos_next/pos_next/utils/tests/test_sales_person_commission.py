# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Unit tests for Item / Item Group / Brand Sales Person commission helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.pos_next.utils import sales_person_commission as spc


def _item(**kwargs):
	defaults = {
		"item_code": "ITEM-1",
		"item_group": "Products",
		"brand": "Acme",
		"base_net_amount": 1000.0,
		"grant_commission": 1,
		"sales_person": None,
	}
	defaults.update(kwargs)
	return defaults


class TestResolveCommissionRate(unittest.TestCase):
	def test_item_beats_item_group_and_brand(self):
		rate = spc.resolve_commission_rate(
			"SP-A",
			item_code="ITEM-1",
			item_group="Products",
			brand="Acme",
			fallback_rate=5.0,
			item_map={"ITEM-1": 25.0},
			ig_map={"Products": 12.0},
			brand_map={"Acme": 8.0},
		)
		self.assertEqual(rate, 25.0)

	def test_item_group_beats_brand_and_fallback(self):
		rate = spc.resolve_commission_rate(
			"SP-A",
			item_code="ITEM-1",
			item_group="Products",
			brand="Acme",
			fallback_rate=5.0,
			item_map={},
			ig_map={"Products": 12.0},
			brand_map={"Acme": 8.0},
		)
		self.assertEqual(rate, 12.0)

	def test_brand_beats_fallback(self):
		rate = spc.resolve_commission_rate(
			"SP-A",
			item_code="ITEM-1",
			item_group="Products",
			brand="Acme",
			fallback_rate=5.0,
			item_map={},
			ig_map={},
			brand_map={"Acme": 8.0},
		)
		self.assertEqual(rate, 8.0)

	def test_falls_back_to_general_rate(self):
		rate = spc.resolve_commission_rate(
			"SP-A",
			item_code="ITEM-1",
			item_group="Products",
			brand="Acme",
			fallback_rate=5.0,
			item_map={},
			ig_map={"Services": 12.0},
			brand_map={"Other": 8.0},
		)
		self.assertEqual(rate, 5.0)

	def test_missing_dims_use_fallback(self):
		rate = spc.resolve_commission_rate(
			"SP-A",
			item_code=None,
			item_group=None,
			brand=None,
			fallback_rate=7.5,
			item_map={"ITEM-1": 25.0},
			ig_map={"Products": 12.0},
			brand_map={"Acme": 8.0},
		)
		self.assertEqual(rate, 7.5)


class TestAllItemsHaveSalesPerson(unittest.TestCase):
	def test_all_covered(self):
		items = [_item(sales_person="SP-A"), _item(sales_person="SP-B")]
		self.assertTrue(spc.all_items_have_sales_person(items))

	def test_partial_coverage(self):
		items = [_item(sales_person="SP-A"), _item(sales_person=None)]
		self.assertFalse(spc.all_items_have_sales_person(items))

	def test_empty_cart(self):
		self.assertFalse(spc.all_items_have_sales_person([]))

	def test_free_items_ignored(self):
		items = [
			_item(sales_person="SP-A"),
			_item(sales_person=None, is_free_item=1, base_net_amount=0),
		]
		self.assertTrue(spc.all_items_have_sales_person(items))

	def test_spoofed_free_flag_with_net_still_requires_sp(self):
		items = [
			_item(sales_person=None, is_free_item=1, base_net_amount=500),
		]
		self.assertFalse(spc.all_items_have_sales_person(items))


class TestBuildSalesTeamFromItems(unittest.TestCase):
	def _maps_for(self, name):
		data = {
			"SP-A": {
				"item_map": {},
				"item_group_map": {"Products": 20.0},
				"brand_map": {},
				"commission_rate": 10.0,
			},
			"SP-B": {
				"item_map": {},
				"item_group_map": {},
				"brand_map": {},
				"commission_rate": 5.0,
			},
		}
		return data.get(
			name,
			{"item_map": {}, "item_group_map": {}, "brand_map": {}, "commission_rate": 0.0},
		)

	def _dims(self, item_code, cache=None):
		table = {
			"X": {"item_group": "Products", "brand": None, "grant_commission": 1},
			"Y": {"item_group": "Products", "brand": None, "grant_commission": 1},
			"ITEM-1": {"item_group": "Products", "brand": "Acme", "grant_commission": 1},
			"A": {"item_group": "Products", "brand": None, "grant_commission": 1},
			"B": {"item_group": "Gadgets", "brand": None, "grant_commission": 1},
			"GRANT-0": {"item_group": "Products", "brand": "Acme", "grant_commission": 0},
			"GRANT-1": {"item_group": "Products", "brand": "Acme", "grant_commission": 1},
			"SPOOF": {"item_group": "Products", "brand": "Acme", "grant_commission": 1},
		}
		dims = table.get(
			item_code, {"item_group": "Products", "brand": "Acme", "grant_commission": 1}
		)
		if cache is not None:
			cache[item_code] = dims
		return dims

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_item_level_sp_ignores_invoice_level(self, mock_maps, mock_dims):
		mock_maps.side_effect = self._maps_for
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[
				_item(item_code="X", item_group="Products", base_net_amount=500, sales_person=None),
				_item(item_code="Y", item_group="Products", base_net_amount=500, sales_person="SP-B"),
			],
			sales_team=[{"sales_person": "SP-A", "allocated_percentage": 100}],
			flags=SimpleNamespace(),
		)

		rows = spc.build_sales_team_from_items(invoice)
		by_sp = {r["sales_person"]: r for r in rows}

		self.assertIn("SP-A", by_sp)
		self.assertIn("SP-B", by_sp)
		# X → SP-A at IG 20%; Y → SP-B at fallback 5%
		self.assertAlmostEqual(by_sp["SP-A"]["incentives"], 500 * 20 / 100)
		self.assertAlmostEqual(by_sp["SP-B"]["incentives"], 500 * 5 / 100)
		self.assertAlmostEqual(
			by_sp["SP-A"]["allocated_percentage"] + by_sp["SP-B"]["allocated_percentage"],
			100.0,
			places=4,
		)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_item_override_used_over_group(self, mock_maps, mock_dims):
		mock_maps.return_value = {
			"item_map": {"ITEM-1": 30.0},
			"item_group_map": {"Products": 10.0},
			"brand_map": {"Acme": 15.0},
			"commission_rate": 5.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[_item(sales_person="SP-A", base_net_amount=1000)],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertAlmostEqual(rows[0]["incentives"], 300.0)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_brand_used_when_no_item_or_group(self, mock_maps, mock_dims):
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {},
			"brand_map": {"Acme": 15.0},
			"commission_rate": 5.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[_item(sales_person="SP-A", base_net_amount=1000)],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertAlmostEqual(rows[0]["incentives"], 150.0)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_all_item_level_no_invoice_team(self, mock_maps, mock_dims):
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {},
			"brand_map": {},
			"commission_rate": 10.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[
				_item(sales_person="SP-A", base_net_amount=300),
				_item(sales_person="SP-A", base_net_amount=700),
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)

		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["sales_person"], "SP-A")
		self.assertAlmostEqual(rows[0]["allocated_percentage"], 100.0)
		self.assertAlmostEqual(rows[0]["incentives"], 1000 * 10 / 100)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_mixed_rates_same_sales_person(self, mock_maps, mock_dims):
		"""Same SP: Products IG 20%, Gadgets falls back to 5%."""
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {"Products": 20.0},
			"brand_map": {},
			"commission_rate": 5.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[
				_item(
					item_code="A",
					item_group="Products",
					brand=None,
					base_net_amount=1000,
					sales_person="SP-A",
				),
				_item(
					item_code="B",
					item_group="Gadgets",
					brand=None,
					base_net_amount=1000,
					sales_person="SP-A",
				),
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)

		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertEqual(len(rows), 1)
		self.assertAlmostEqual(rows[0]["incentives"], 250.0)
		self.assertAlmostEqual(rows[0]["commission_rate"], 12.5)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_multiple_uncovered_split(self, mock_maps, mock_dims):
		def maps(name):
			return {
				"SP-A": {
					"item_map": {},
					"item_group_map": {},
					"brand_map": {},
					"commission_rate": 10.0,
				},
				"SP-B": {
					"item_map": {},
					"item_group_map": {},
					"brand_map": {},
					"commission_rate": 20.0,
				},
			}[name]

		mock_maps.side_effect = maps
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[_item(base_net_amount=1000, sales_person=None)],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		invoice_team = [
			{"sales_person": "SP-A", "allocated_percentage": 60},
			{"sales_person": "SP-B", "allocated_percentage": 40},
		]

		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=invoice_team)
		by_sp = {r["sales_person"]: r for r in rows}

		self.assertAlmostEqual(by_sp["SP-A"]["incentives"], 600 * 10 / 100)
		self.assertAlmostEqual(by_sp["SP-B"]["incentives"], 400 * 20 / 100)
		self.assertAlmostEqual(sum(r["allocated_percentage"] for r in rows), 100.0, places=4)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_skips_non_grant_commission_items(self, mock_maps, mock_dims):
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {},
			"brand_map": {},
			"commission_rate": 10.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[
				_item(item_code="GRANT-0", sales_person="SP-A", base_net_amount=500),
				_item(item_code="GRANT-1", sales_person="SP-A", base_net_amount=500),
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)

		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertAlmostEqual(rows[0]["incentives"], 50.0)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_ignores_client_spoofed_item_group(self, mock_maps, mock_dims):
		"""Client sends Gadgets but master says Products — use master."""
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {"Products": 20.0, "Gadgets": 50.0},
			"brand_map": {},
			"commission_rate": 5.0,
		}
		mock_dims.side_effect = self._dims  # SPOOF → Products

		invoice = SimpleNamespace(
			items=[
				_item(
					item_code="SPOOF",
					item_group="Gadgets",  # client spoof
					sales_person="SP-A",
					base_net_amount=1000,
				)
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertAlmostEqual(rows[0]["incentives"], 200.0)

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_commission_uses_amount_after_discount(self, mock_maps, mock_dims):
		"""Incentives must use post-discount net, not list / pre-discount amount."""
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {},
			"brand_map": {},
			"commission_rate": 10.0,
		}
		mock_dims.side_effect = self._dims

		# List 1000, 20% discount → net 800. amount left at gross to catch regressions.
		invoice = SimpleNamespace(
			items=[
				_item(
					sales_person="SP-A",
					base_net_amount=800,
					amount=1000,
					price_list_rate=1000,
					rate=800,
					qty=1,
					discount_percentage=20,
					discount_amount=200,
				)
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		self.assertAlmostEqual(rows[0]["incentives"], 80.0)  # 10% of 800, not 100

	@patch.object(spc, "_get_item_master_dims")
	@patch.object(spc, "get_sales_person_commission_maps")
	def test_commission_from_discount_fields_when_nets_unset(self, mock_maps, mock_dims):
		"""Before taxes, nets are 0 — derive post-discount from list price - discount."""
		mock_maps.return_value = {
			"item_map": {},
			"item_group_map": {},
			"brand_map": {},
			"commission_rate": 10.0,
		}
		mock_dims.side_effect = self._dims

		invoice = SimpleNamespace(
			items=[
				{
					"item_code": "ITEM-1",
					"item_group": "Products",
					"brand": "Acme",
					"grant_commission": 1,
					"sales_person": "SP-A",
					"base_net_amount": 0,
					"net_amount": 0,
					"qty": 2,
					"price_list_rate": 100,
					"rate": 100,  # not yet reduced
					"discount_percentage": 25,
					"discount_amount": 50,  # 25% of 200
					"amount": 200,
				}
			],
			sales_team=[],
			flags=SimpleNamespace(),
		)
		rows = spc.build_sales_team_from_items(invoice, invoice_level_team=[])
		# (100*2 - 50) * 10% = 15
		self.assertAlmostEqual(rows[0]["incentives"], 15.0)


class TestLineNetAmount(unittest.TestCase):
	def test_prefers_base_net_over_gross_amount(self):
		self.assertEqual(
			spc._line_net_amount(
				{
					"base_net_amount": 800,
					"amount": 1000,
					"price_list_rate": 1000,
					"discount_amount": 200,
				}
			),
			800.0,
		)

	def test_derives_from_price_list_minus_discount(self):
		self.assertEqual(
			spc._line_net_amount(
				{
					"base_net_amount": 0,
					"qty": 1,
					"price_list_rate": 500,
					"rate": 500,
					"discount_percentage": 10,
					"discount_amount": 50,
				}
			),
			450.0,
		)


class TestValidateCoverage(unittest.TestCase):
	@patch.object(spc, "sales_persons_enabled", return_value=True)
	@patch(
		"pos_next.pos_next.utils.sales_person_commission.frappe.throw",
		side_effect=RuntimeError("required"),
	)
	def test_throws_when_uncovered_and_no_invoice_team(self, _throw, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person=None)],
			sales_team=[],
			pos_profile="POS-1",
		)
		with self.assertRaisesRegex(RuntimeError, "required"):
			spc.validate_sales_person_coverage(invoice, "POS-1", invoice_level_team=[])

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	@patch(
		"pos_next.pos_next.utils.sales_person_commission.frappe.throw",
		side_effect=RuntimeError("required"),
	)
	def test_throws_when_partial_item_sp_even_if_rebuilt_team_present(self, _throw, _enabled):
		"""Regression: must not treat rebuilt sales_team as invoice-level coverage."""
		invoice = SimpleNamespace(
			items=[
				_item(sales_person="SP-A"),
				_item(sales_person=None),
			],
			# Rebuilt aggregate from a prior apply — must NOT count as coverage
			sales_team=[{"sales_person": "SP-A", "allocated_percentage": 100}],
			pos_profile="POS-1",
		)
		with self.assertRaisesRegex(RuntimeError, "required"):
			spc.validate_sales_person_coverage(invoice, "POS-1", invoice_level_team=[])

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	def test_ok_when_invoice_level_covers_uncovered_lines(self, _enabled):
		invoice = SimpleNamespace(
			items=[
				_item(sales_person="SP-A"),
				_item(sales_person=None),
			],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_coverage(
			invoice,
			"POS-1",
			invoice_level_team=[{"sales_person": "SP-B", "allocated_percentage": 100}],
		)

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	def test_ok_when_all_items_have_sp(self, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person="SP-A")],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_coverage(invoice, "POS-1", invoice_level_team=[])

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	def test_free_items_do_not_require_sp(self, _enabled):
		invoice = SimpleNamespace(
			items=[
				_item(sales_person="SP-A"),
				_item(sales_person=None, is_free_item=1, base_net_amount=0),
			],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_coverage(invoice, "POS-1", invoice_level_team=[])

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	@patch(
		"pos_next.pos_next.utils.sales_person_commission.frappe.throw",
		side_effect=RuntimeError("required"),
	)
	def test_spoofed_free_flag_with_positive_net_requires_sp(self, _throw, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person=None, is_free_item=1, base_net_amount=500)],
			sales_team=[],
			pos_profile="POS-1",
		)
		with self.assertRaisesRegex(RuntimeError, "required"):
			spc.validate_sales_person_coverage(invoice, "POS-1", invoice_level_team=[])

	@patch.object(spc, "sales_persons_enabled", return_value=False)
	def test_skipped_when_disabled(self, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person=None)],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_coverage(invoice, "POS-1")


class TestLegacyInvoiceLevelRecovery(unittest.TestCase):
	def test_all_item_sp_returns_empty(self):
		items = [
			SimpleNamespace(sales_person="SP-A"),
			SimpleNamespace(sales_person="SP-B"),
		]
		self.assertEqual(spc._legacy_invoice_level_from_original("SI-1", items), [])

	@patch(
		"pos_next.pos_next.utils.sales_person_commission.frappe.get_all",
		return_value=[
			SimpleNamespace(sales_person="SP-A", allocated_percentage=100),
		],
	)
	def test_pure_invoice_level_uses_sales_team(self, _get_all):
		items = [
			SimpleNamespace(sales_person=None),
			SimpleNamespace(sales_person=None),
		]
		result = spc._legacy_invoice_level_from_original("SI-1", items)
		self.assertEqual(result[0]["sales_person"], "SP-A")

	def test_mixed_legacy_returns_empty(self):
		items = [
			SimpleNamespace(sales_person="SP-A"),
			SimpleNamespace(sales_person=None),
		]
		self.assertEqual(spc._legacy_invoice_level_from_original("SI-1", items), [])


class TestValidateAssignments(unittest.TestCase):
	@patch.object(spc, "sales_persons_enabled", return_value=True)
	@patch.object(spc, "get_allowed_sales_person_names", return_value={"SP-A", "SP-B"})
	@patch(
		"pos_next.pos_next.utils.sales_person_commission.frappe.throw",
		side_effect=RuntimeError("invalid"),
	)
	def test_rejects_disabled_or_unknown_sp(self, _throw, _allowed, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person="SP-DISABLED")],
			sales_team=[],
			pos_profile="POS-1",
		)
		with self.assertRaisesRegex(RuntimeError, "invalid"):
			spc.validate_sales_person_assignments(
				invoice, "POS-1", invoice_level_team=[]
			)

	@patch.object(spc, "sales_persons_enabled", return_value=True)
	@patch.object(spc, "get_allowed_sales_person_names", return_value={"SP-A", "SP-B"})
	def test_accepts_allowed_sp(self, _allowed, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person="SP-A")],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_assignments(
			invoice,
			"POS-1",
			invoice_level_team=[{"sales_person": "SP-B", "allocated_percentage": 100}],
		)

	@patch.object(spc, "sales_persons_enabled", return_value=False)
	def test_skipped_when_disabled(self, _enabled):
		invoice = SimpleNamespace(
			items=[_item(sales_person="ANYONE")],
			sales_team=[],
			pos_profile="POS-1",
		)
		spc.validate_sales_person_assignments(invoice, "POS-1")


class TestClearWhenDisabled(unittest.TestCase):
	def test_clears_item_and_team(self):
		item = SimpleNamespace(sales_person="SP-A")
		invoice = SimpleNamespace(
			items=[item],
			sales_team=[{"sales_person": "SP-A"}],
			flags=SimpleNamespace(),
		)
		spc.clear_sales_person_fields(invoice)
		self.assertIsNone(item.sales_person)
		self.assertEqual(invoice.sales_team, [])
		self.assertEqual(invoice.flags.pos_invoice_level_sales_team, [])


if __name__ == "__main__":
	unittest.main()
