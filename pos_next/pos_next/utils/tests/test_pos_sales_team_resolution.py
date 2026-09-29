# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Site-less tests for POS sales-team resolution, returns and customer helpers.

Same mock pattern as test_sales_person_commission: no database, Frappe calls are
patched. Covers the PR #407 review fixes (offline sync, returns, submit
fallback, in-place Sales Team sync, commission table validation) plus the
return-quantity, customer and item-dimension helpers.
"""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from pos_next.api import invoices
from pos_next.api import pos_profile as pos_profile_api
from pos_next.overrides import sales_invoice as si_override
from pos_next.pos_next.utils import sales_person_commission as spc


class Row(SimpleNamespace):
	"""Child row / document stand-in with Frappe-like ``get``."""

	def get(self, key, default=None):
		return getattr(self, key, default)


class FakeDoc(Row):
	def __init__(self, **kwargs):
		kwargs.setdefault("flags", frappe._dict())
		kwargs.setdefault("items", [])
		kwargs.setdefault("sales_team", [])
		super().__init__(**kwargs)

	def append(self, key, value):
		row = Row(**value)
		if getattr(self, key, None) is None:
			setattr(self, key, [])
		getattr(self, key).append(row)
		return row


def _throw(msg, *args, **kwargs):
	raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# _resolve_submit_invoice_level_team (incl. S4 fallback to the saved draft team)
# ---------------------------------------------------------------------------


class TestResolveSubmitInvoiceLevelTeam(unittest.TestCase):
	@patch.object(spc, "load_stored_invoice_level_sales_team")
	def test_explicit_payload_team_wins_even_when_empty(self, load):
		team = [{"sales_person": "SP-A", "allocated_percentage": 100}]
		self.assertEqual(invoices._resolve_submit_invoice_level_team({}, {"sales_team": team}), team)
		self.assertEqual(
			invoices._resolve_submit_invoice_level_team({"name": "SI-1"}, {"sales_team": []}, "SI-1"), []
		)
		load.assert_not_called()

	@patch.object(spc, "load_stored_invoice_level_sales_team")
	def test_offline_payload_team_used_when_data_is_empty(self, load):
		team = [{"sales_person": "SP-A", "allocated_percentage": 100}]
		invoice = {"offline_id": "pos_offline_1", "sales_team": team}
		self.assertEqual(invoices._resolve_submit_invoice_level_team(invoice, {}), team)
		load.assert_not_called()

	@patch.object(spc, "load_stored_invoice_level_sales_team")
	def test_falls_back_to_team_saved_on_draft(self, load):
		stored = [{"sales_person": "SP-A", "allocated_percentage": 100}]
		load.return_value = stored
		# Online draft: its sales_team is the rebuilt aggregate and must be ignored
		invoice = {"name": "SI-1", "sales_team": [{"sales_person": "SP-X"}]}
		self.assertEqual(invoices._resolve_submit_invoice_level_team(invoice, {}), stored)
		load.assert_called_once_with("SI-1")

	@patch.object(spc, "load_stored_invoice_level_sales_team", return_value=None)
	def test_prefers_explicit_invoice_name(self, load):
		self.assertEqual(invoices._resolve_submit_invoice_level_team({}, None, invoice_name="SI-9"), [])
		load.assert_called_once_with("SI-9")


# ---------------------------------------------------------------------------
# _apply_pos_sales_team: B1 (offline sync) and B2 (returns)
# ---------------------------------------------------------------------------


@patch.object(spc.frappe, "throw", side_effect=_throw)
@patch.object(spc.frappe, "log_error")
@patch.object(spc, "apply_sales_team_to_invoice")
@patch.object(spc, "build_sales_team_from_items", return_value=[])
@patch.object(spc, "persist_invoice_level_sales_team")
@patch.object(spc, "validate_sales_person_assignments")
@patch.object(spc, "validate_sales_person_coverage")
@patch.object(spc, "sales_persons_enabled", return_value=True)
class TestApplyPosSalesTeam(unittest.TestCase):
	def test_offline_sync_without_sales_person_is_accepted(
		self, _enabled, coverage, assignments, persist, build, _apply, _log, _throw_mock
	):
		coverage.side_effect = RuntimeError("Sales Person is required")
		doc = FakeDoc(pos_profile="POS-1", items=[{"item_code": "A", "base_net_amount": 100}])
		doc.flags.pos_offline_sync = True

		invoices._apply_pos_sales_team(doc, sales_team_data=[], pos_profile="POS-1")

		coverage.assert_not_called()
		assignments.assert_not_called()
		build.assert_called_once_with(doc, invoice_level_team=[])
		persist.assert_called_once_with(doc, [])
		self.assertTrue(doc.flags.pos_allow_disabled_sales_persons)

	def test_online_sale_still_validated(
		self, _enabled, coverage, assignments, persist, build, _apply, _log, _throw_mock
	):
		team = [{"sales_person": "SP-A", "allocated_percentage": 100}]
		doc = FakeDoc(pos_profile="POS-1", items=[{"item_code": "A"}])

		invoices._apply_pos_sales_team(doc, sales_team_data=team, pos_profile="POS-1")

		coverage.assert_called_once_with(doc, pos_profile="POS-1", invoice_level_team=team)
		assignments.assert_called_once_with(doc, pos_profile="POS-1", invoice_level_team=team)
		self.assertFalse(doc.flags.get("pos_allow_disabled_sales_persons"))

	def test_offline_sync_drops_deleted_and_keeps_disabled_sales_persons(
		self, _enabled, coverage, assignments, persist, build, _apply, log, _throw_mock
	):
		doc = FakeDoc(
			pos_profile="POS-1",
			items=[
				{"item_code": "A", "sales_person": "SP-GONE"},
				{"item_code": "B", "sales_person": "SP-DISABLED"},
			],
		)
		doc.flags.pos_offline_sync = True
		team = [
			{"sales_person": "SP-GONE", "allocated_percentage": 50},
			{"sales_person": "SP-DISABLED", "allocated_percentage": 50},
		]
		# SP-DISABLED still exists (disabled); SP-GONE was deleted
		with patch.object(spc.frappe, "get_all", return_value=["SP-DISABLED"]) as get_all:
			invoices._apply_pos_sales_team(doc, sales_team_data=team, pos_profile="POS-1")

		get_all.assert_called_once()
		self.assertIsNone(doc.items[0]["sales_person"])
		self.assertEqual(doc.items[1]["sales_person"], "SP-DISABLED")
		self.assertEqual(doc.flags.pos_dropped_sales_persons, ["SP-GONE"])
		build.assert_called_once_with(doc, invoice_level_team=[team[1]])
		log.assert_called_once()
		coverage.assert_not_called()

	def test_return_of_invoice_without_sales_person_is_not_blocked(
		self, _enabled, coverage, assignments, persist, build, _apply, _log, _throw_mock
	):
		"""B2 regression: legacy / offline original without any Sales Person."""
		coverage.side_effect = RuntimeError("Sales Person is required")
		doc = FakeDoc(
			pos_profile="POS-1",
			is_return=1,
			return_against="SI-ORIG",
			items=[Row(item_code="A", sales_person="SP-CLIENT", sales_invoice_item="row-1")],
		)
		original_items = [frappe._dict(name="row-1", item_code="A", sales_person=None, base_net_amount=100)]

		def get_all(doctype, **kwargs):
			return {"Sales Invoice Item": original_items, "Sales Team": []}[doctype]

		with (
			patch.object(spc.frappe, "get_all", side_effect=get_all),
			patch.object(spc.frappe, "get_meta", return_value=MagicMock(has_field=lambda f: True)),
			patch.object(spc, "load_stored_invoice_level_sales_team", return_value=None),
		):
			invoices._apply_pos_sales_team(doc, sales_team_data=None, pos_profile="POS-1")

		coverage.assert_not_called()
		assignments.assert_not_called()
		persist.assert_not_called()
		# Client-supplied SP is replaced by the original's (none)
		self.assertIsNone(doc.items[0].sales_person)
		self.assertEqual(doc.flags.pos_invoice_level_sales_team, [])
		self.assertTrue(doc.flags.pos_allow_disabled_sales_persons)

	@patch.object(spc, "clear_sales_person_fields")
	@patch.object(spc, "apply_return_sales_person_from_original")
	@patch.object(spc, "original_has_sales_attribution", return_value=True)
	def test_return_mirrors_original_when_feature_disabled_since(
		self, has_attr, apply_return, clear, enabled, coverage, assignments, persist, build, *_
	):
		enabled.return_value = False
		doc = FakeDoc(pos_profile="POS-1", is_return=1, return_against="SI-ORIG")
		doc.flags.pos_invoice_level_sales_team = [{"sales_person": "SP-A", "allocated_percentage": 100}]

		with patch.object(spc.frappe, "get_all", return_value=["SP-A"]):
			invoices._apply_pos_sales_team(doc, pos_profile="POS-1")

		has_attr.assert_called_once_with("SI-ORIG")
		apply_return.assert_called_once_with(doc)
		clear.assert_not_called()
		build.assert_called_once()
		coverage.assert_not_called()

	@patch.object(spc, "clear_sales_person_fields")
	@patch.object(spc, "original_has_sales_attribution", return_value=False)
	def test_feature_disabled_clears_fields(self, has_attr, clear, enabled, *_):
		enabled.return_value = False
		sale = FakeDoc(pos_profile="POS-1")
		invoices._apply_pos_sales_team(sale, pos_profile="POS-1")
		clear.assert_called_once_with(sale)
		has_attr.assert_not_called()  # non-returns never query the original

		ret = FakeDoc(pos_profile="POS-1", is_return=1, return_against="SI-ORIG")
		invoices._apply_pos_sales_team(ret, pos_profile="POS-1")
		clear.assert_called_with(ret)


class TestOfflineFlagWiring(unittest.TestCase):
	def test_update_and_submit_mark_offline_payloads(self):
		self.assertIn(
			'invoice_doc.flags.pos_offline_sync = bool(data.get("offline_id"))',
			inspect.getsource(invoices.update_invoice),
		)
		self.assertIn(
			"invoice_doc.flags.pos_offline_sync = bool(offline_id)",
			inspect.getsource(invoices.submit_invoice),
		)


# ---------------------------------------------------------------------------
# Disabled Sales Persons: override of ERPNext validate_sales_team (B1/B2/S5)
# ---------------------------------------------------------------------------


class TestValidateSalesTeamOverride(unittest.TestCase):
	def _invoice(self, **flags):
		inv = si_override.CustomSalesInvoice.__new__(si_override.CustomSalesInvoice)
		inv.flags = frappe._dict(flags)
		return inv

	def test_disabled_check_skipped_when_flagged(self):
		team = [Row(sales_person="SP-DISABLED")]
		with patch("erpnext.controllers.selling_controller.SellingController.validate_sales_team") as parent:
			self._invoice(pos_allow_disabled_sales_persons=True).validate_sales_team(team)
			parent.assert_not_called()
			self._invoice().validate_sales_team(team)
			parent.assert_called_once_with(team)

	@patch.object(spc, "apply_item_level_contribution")
	@patch.object(spc, "needs_item_level_contribution", return_value=True)
	def test_item_level_path_runs_validate_sales_team(self, _needs, apply_contribution):
		inv = MagicMock()
		inv.flags = frappe._dict()
		inv.get.return_value = [Row(sales_person="SP-A")]
		si_override.CustomSalesInvoice.calculate_contribution(inv)
		apply_contribution.assert_called_once_with(inv)
		inv.validate_sales_team.assert_called_once_with([Row(sales_person="SP-A")])


# ---------------------------------------------------------------------------
# S5: in-place Sales Team sync and batched override lookup
# ---------------------------------------------------------------------------


class TestApplySalesTeamInPlace(unittest.TestCase):
	def test_updates_existing_rows_and_preserves_custom_fields_and_order(self):
		keep_b = Row(name="row-b", sales_person="SP-B", idx=1, custom_note="keep me", allocated_percentage=10)
		stale = Row(name="row-old", sales_person="SP-OLD", idx=2)
		keep_a = Row(name="row-a", sales_person="SP-A", idx=3, allocated_percentage=90)
		doc = FakeDoc(sales_team=[keep_b, stale, keep_a])

		spc.apply_sales_team_to_invoice(
			doc,
			[
				{"sales_person": "SP-A", "allocated_percentage": 60, "commission_rate": 5, "incentives": 3},
				{"sales_person": "SP-B", "allocated_percentage": 40, "commission_rate": 2, "incentives": 1},
				{"sales_person": "SP-NEW", "allocated_percentage": 0},
			],
		)

		self.assertEqual([r.sales_person for r in doc.sales_team], ["SP-B", "SP-A", "SP-NEW"])
		self.assertIs(doc.sales_team[0], keep_b)
		self.assertIs(doc.sales_team[1], keep_a)
		self.assertEqual(keep_b.custom_note, "keep me")
		self.assertEqual(keep_b.allocated_percentage, 40)
		self.assertEqual(keep_a.commission_rate, 5)
		self.assertEqual(keep_a.incentives, 3)
		self.assertEqual([r.idx for r in doc.sales_team], [1, 2, 3])
		self.assertNotIn(stale, doc.sales_team)

	def test_empty_rows_clear_team(self):
		doc = FakeDoc(sales_team=[Row(sales_person="SP-A", idx=1)])
		spc.apply_sales_team_to_invoice(doc, [])
		self.assertEqual(doc.sales_team, [])


class TestBatchedCommissionOverrides(unittest.TestCase):
	def _meta(self, has=True):
		return MagicMock(has_field=lambda f: has)

	def test_no_queries_without_sales_team_or_item_sales_person(self):
		doc = FakeDoc(items=[{"item_code": "A"}], sales_team=[])
		with patch.object(spc.frappe, "get_all") as get_all, patch.object(spc.frappe, "get_meta") as meta:
			self.assertFalse(spc.needs_item_level_contribution(doc))
		get_all.assert_not_called()
		meta.assert_not_called()

	def test_item_sales_person_short_circuits(self):
		doc = FakeDoc(
			items=[{"item_code": "A", "sales_person": "SP-A"}], sales_team=[Row(sales_person="SP-A")]
		)
		with patch.object(spc.frappe, "get_all") as get_all:
			self.assertTrue(spc.needs_item_level_contribution(doc))
		get_all.assert_not_called()

	def test_whole_team_checked_with_at_most_three_queries(self):
		team = [Row(sales_person=f"SP-{i}") for i in range(10)]
		doc = FakeDoc(items=[{"item_code": "A"}], sales_team=team)
		with (
			patch.object(spc.frappe, "get_meta", return_value=self._meta()),
			patch.object(spc.frappe, "get_all", return_value=[]) as get_all,
		):
			self.assertFalse(spc.needs_item_level_contribution(doc))
		self.assertEqual(get_all.call_count, 3)
		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["parent"], ["in", sorted(r.sales_person for r in team)])

	def test_stops_at_first_table_with_overrides(self):
		with (
			patch.object(spc.frappe, "get_meta", return_value=self._meta()),
			patch.object(spc.frappe, "get_all", return_value=["row"]) as get_all,
		):
			self.assertTrue(spc._any_commission_overrides(["SP-A"]))
		self.assertEqual(get_all.call_count, 1)

	def test_no_queries_when_custom_fields_missing(self):
		with (
			patch.object(spc.frappe, "get_meta", return_value=self._meta(has=False)),
			patch.object(spc.frappe, "get_all") as get_all,
		):
			self.assertFalse(spc._any_commission_overrides(["SP-A"]))
		get_all.assert_not_called()


# ---------------------------------------------------------------------------
# S2: commission table validation (Sales Person validate hook)
# ---------------------------------------------------------------------------


@patch.object(spc.frappe, "throw", side_effect=_throw)
class TestCommissionTableValidation(unittest.TestCase):
	def _sp(self, **tables):
		return FakeDoc(**tables)

	def test_valid_tables_pass(self, _t):
		spc.validate_sales_person_commission_tables(
			self._sp(
				custom_item_commissions=[{"idx": 1, "item": "A", "commission_rate": 0}],
				custom_item_group_commissions=[
					{"idx": 1, "item_group": "Phones", "commission_rate": 100},
					{"idx": 2, "item_group": "Tablets", "commission_rate": 7.5},
				],
				# Same key in a different table is fine
				custom_brand_commissions=[{"idx": 1, "brand": "Phones", "commission_rate": 3}],
			)
		)

	def test_rate_out_of_range_rejected(self, _t):
		for rate in (-1, 100.01):
			with self.assertRaises(RuntimeError) as ctx:
				spc.validate_sales_person_commission_tables(
					self._sp(custom_brand_commissions=[{"idx": 2, "brand": "Acme", "commission_rate": rate}])
				)
			self.assertIn("Row #2", str(ctx.exception))

	def test_duplicate_key_rejected_with_rows(self, _t):
		with self.assertRaises(RuntimeError) as ctx:
			spc.validate_sales_person_commission_tables(
				self._sp(
					custom_item_group_commissions=[
						{"idx": 1, "item_group": "Phones", "commission_rate": 5},
						{"idx": 2, "item_group": "Tablets", "commission_rate": 5},
						{"idx": 3, "item_group": "Phones", "commission_rate": 9},
					]
				)
			)
		self.assertIn("Row #3", str(ctx.exception))
		self.assertIn("row #1", str(ctx.exception))

	def test_blank_key_rows_ignored_for_duplicates(self, _t):
		spc.validate_sales_person_commission_tables(
			self._sp(
				custom_item_commissions=[
					{"idx": 1, "item": None, "commission_rate": 1},
					{"idx": 2, "item": None, "commission_rate": 1},
				]
			)
		)

	def test_hook_registered(self, _t):
		from pos_next import hooks

		self.assertEqual(
			hooks.doc_events["Sales Person"]["validate"],
			"pos_next.pos_next.utils.sales_person_commission.validate_sales_person_commission_tables",
		)


# ---------------------------------------------------------------------------
# S3: get_sales_persons returns picker fields only, no per-person queries
# ---------------------------------------------------------------------------


class TestGetSalesPersons(unittest.TestCase):
	def test_no_per_person_commission_queries(self):
		db = MagicMock()
		db.exists.return_value = True
		db.get_value.return_value = "Company-1"
		db.has_column.return_value = False
		rows = [frappe._dict(name="SP-A", sales_person_name="A", commission_rate=2, employee=None)]
		with (
			patch.object(frappe, "db", db),
			patch.object(frappe, "session", SimpleNamespace(user="cashier@example.com")),
			patch.object(frappe, "get_list", return_value=rows) as get_list,
			patch.object(spc, "get_sales_person_commission_maps", side_effect=AssertionError),
		):
			# Bypass the whitelist type-validation wrapper (needs a request context)
			result = inspect.unwrap(pos_profile_api.get_sales_persons)("POS-1")

		get_list.assert_called_once()
		self.assertEqual(result, rows)
		for key in ("item_commissions", "item_group_commissions", "brand_commissions"):
			self.assertNotIn(key, result[0])


# ---------------------------------------------------------------------------
# Return quantity checks (per-row)
# ---------------------------------------------------------------------------


def _orig(name, item_code, qty):
	return frappe._dict(name=name, item_code=item_code, qty=qty)


def _returned(item_code, row, qty):
	return frappe._dict(item_code=item_code, sales_invoice_item=row, returned_qty=qty)


class TestCheckReturnQuantities(unittest.TestCase):
	ORIGINAL = [_orig("r1", "A", 2), _orig("r2", "A", 3), _orig("r3", "B", 1)]

	def check(self, return_items, returned=()):
		return invoices._check_return_quantities("SI-1", self.ORIGINAL, list(returned), return_items)

	def test_valid_linked_and_unlinked_returns(self):
		self.assertEqual(
			self.check(
				[
					{"item_code": "A", "qty": -2, "sales_invoice_item": "r1"},
					{"item_code": "B", "qty": -1},
				]
			),
			{"valid": True},
		)

	def test_row_from_another_invoice_rejected(self):
		result = self.check([{"item_code": "A", "qty": -1, "sales_invoice_item": "foreign"}])
		self.assertFalse(result["valid"])
		self.assertIn("does not belong", result["message"])

	def test_item_code_must_match_linked_row(self):
		result = self.check([{"item_code": "B", "qty": -1, "sales_invoice_item": "r1"}])
		self.assertFalse(result["valid"])
		self.assertIn("does not match", result["message"])

	def test_row_limit_enforced_even_when_item_total_allows(self):
		# Item A has 5 in total, but row r1 only 2
		result = self.check([{"item_code": "A", "qty": -3, "sales_invoice_item": "r1"}])
		self.assertFalse(result["valid"])
		self.assertIn("remains on that line", result["message"])

	def test_previous_returns_reduce_row_remaining(self):
		result = self.check(
			[{"item_code": "A", "qty": -2, "sales_invoice_item": "r2"}],
			returned=[_returned("A", "r2", 2)],
		)
		self.assertFalse(result["valid"])
		self.assertIn("remains on that line", result["message"])

	def test_rows_in_same_return_accumulate(self):
		result = self.check(
			[
				{"item_code": "A", "qty": -2, "sales_invoice_item": "r2"},
				{"item_code": "A", "qty": -2, "sales_invoice_item": "r2"},
			]
		)
		self.assertFalse(result["valid"])

	def test_unlinked_over_return_by_item_total_rejected(self):
		result = self.check([{"item_code": "A", "qty": -4}], returned=[_returned("A", None, 2)])
		self.assertFalse(result["valid"])
		self.assertIn("than was sold", result["message"])


# ---------------------------------------------------------------------------
# Customer helpers (S1) and item-row customer dimension
# ---------------------------------------------------------------------------


@patch.object(frappe, "throw", side_effect=_throw)
class TestEnsureInvoiceCustomer(unittest.TestCase):
	def _db(self, customers=(), profile_default=None, customer_name="Customer Name"):
		db = MagicMock()
		db.exists.side_effect = lambda doctype, name=None: doctype == "Customer" and name in customers

		def get_value(doctype, name, field):
			if doctype == "POS Profile":
				return profile_default
			return customer_name

		db.get_value.side_effect = get_value
		return db

	def test_existing_customer_kept_and_name_filled(self, _t):
		doc = FakeDoc(customer="C-1", pos_profile="POS-1")
		with patch.object(frappe, "db", self._db(customers={"C-1"})):
			invoices._ensure_invoice_customer(doc, "POS-1")
		self.assertEqual(doc.customer, "C-1")
		self.assertEqual(doc.customer_name, "Customer Name")

	def test_blank_customer_uses_profile_default(self, _t):
		doc = FakeDoc(customer="", pos_profile="POS-1", customer_name="Walk-in")
		with patch.object(frappe, "db", self._db(customers={"WALK-IN"}, profile_default="WALK-IN")):
			invoices._ensure_invoice_customer(doc, "POS-1")
		self.assertEqual(doc.customer, "WALK-IN")
		self.assertEqual(doc.customer_name, "Walk-in")

	def test_unknown_customer_rejected_not_reattributed(self, _t):
		doc = FakeDoc(customer="Typo Customer", pos_profile="POS-1")
		with patch.object(frappe, "db", self._db(customers={"WALK-IN"}, profile_default="WALK-IN")):
			with self.assertRaises(RuntimeError) as ctx:
				invoices._ensure_invoice_customer(doc, "POS-1")
		self.assertIn("does not exist", str(ctx.exception))
		self.assertEqual(doc.customer, "Typo Customer")

	def test_no_customer_and_no_default_rejected(self, _t):
		doc = FakeDoc(customer=None, pos_profile="POS-1")
		with patch.object(frappe, "db", self._db()):
			with self.assertRaises(RuntimeError) as ctx:
				invoices._ensure_invoice_customer(doc, "POS-1")
		self.assertIn("Customer is required", str(ctx.exception))

	def test_customer_checks_run_after_auto_create(self, _t):
		"""S1: develop's auto-create must run before the customer is validated."""
		source = inspect.getsource(invoices.update_invoice)
		auto_create = source.index("Failed to create customer")
		self.assertLess(auto_create, source.index("_ensure_invoice_customer(invoice_doc, pos_profile)"))
		self.assertLess(auto_create, source.index("_validate_customer_for_receivable_payments(invoice_doc)"))
		self.assertLess(auto_create, source.index("_validate_payment_account_not_debit_to(invoice_doc)"))


class TestItemCustomerDimension(unittest.TestCase):
	def _doc(self, **kwargs):
		kwargs.setdefault("doctype", "Sales Invoice")
		kwargs.setdefault("is_pos", 1)
		kwargs.setdefault("customer", "C-NEW")
		kwargs.setdefault("items", [Row(customer="C-OLD"), Row(customer=None)])
		return FakeDoc(**kwargs)

	def test_overwrites_stale_row_customer(self):
		doc = self._doc()
		with patch.object(frappe, "get_meta", return_value=MagicMock(has_field=lambda f: True)):
			invoices._apply_pos_item_accounting_dimensions(doc)
		self.assertEqual([r.customer for r in doc.items], ["C-NEW", "C-NEW"])

	def test_non_pos_invoice_untouched(self):
		doc = self._doc(is_pos=0)
		with patch.object(frappe, "get_meta") as meta:
			invoices._apply_pos_item_accounting_dimensions(doc)
		meta.assert_not_called()
		self.assertEqual(doc.items[0].customer, "C-OLD")

	def test_missing_item_customer_field_untouched(self):
		doc = self._doc()
		with patch.object(frappe, "get_meta", return_value=MagicMock(has_field=lambda f: False)):
			invoices._apply_pos_item_accounting_dimensions(doc)
		self.assertEqual(doc.items[0].customer, "C-OLD")


if __name__ == "__main__":
	unittest.main()
