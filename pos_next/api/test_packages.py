# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Tests for POS Package quoting and invoice rate enforcement.

Run inside the container (serial only):

    ./env/bin/python apps/pos_next/pos_next/_pn_run_tests.py pos_next.api.test_packages
"""

import json
import unittest

import frappe

from pos_next.api.packages import (
	COMPONENT_ROLE,
	PARENT_ROLE,
	get_packages,
	quote,
	validate_invoice_packages,
)

PROFILE = "_PNXT_TEST_POS_PROFILE__Test Company"
COMPANY = "_Test Company"
PACKAGE = "_PNXT Year End Laptop Package"

LAPTOP = "_PNXT_PKG_LAPTOP"
BACKPACK = "_PNXT_PKG_BACKPACK"
HEADPHONE = "_PNXT_PKG_HEADPHONE"
VOUCHER_PULSA = "_PNXT_PKG_VOUCHER_PULSA"
VOUCHER_LISTRIK = "_PNXT_PKG_VOUCHER_LISTRIK"
PARENT_ITEM = "_PNXT_PKG_PARENT"

BASE_PRICE = 10_000_000.0
BACKPACK_ADJ = 0.0
HEADPHONE_ADJ = 250_000.0
PULSA_ADJ = 50_000.0
LISTRIK_ADJ = 75_000.0


def _ensure_item(item_code, item_name, is_stock_item):
	if frappe.db.exists("Item", item_code):
		return

	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": "Nos",
			"is_stock_item": 1 if is_stock_item else 0,
			"is_sales_item": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_package():
	for code, name in (
		(LAPTOP, "PNXT Laptop"),
		(BACKPACK, "PNXT Backpack"),
		(HEADPHONE, "PNXT Headphone"),
		(VOUCHER_PULSA, "PNXT Voucher Pulsa"),
		(VOUCHER_LISTRIK, "PNXT Voucher Listrik"),
	):
		_ensure_item(code, name, is_stock_item=True)

	_ensure_item(PARENT_ITEM, "PNXT Year End Laptop Package", is_stock_item=False)

	if frappe.db.exists("POS Package", PACKAGE):
		return

	frappe.get_doc(
		{
			"doctype": "POS Package",
			"package_name": PACKAGE,
			"company": COMPANY,
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
			"parent_item": PARENT_ITEM,
			"base_price": BASE_PRICE,
			"items": [{"item_code": LAPTOP, "qty": 1}],
			"groups": [
				{"group_key": "accessory", "label": "Accessory", "min_qty": 1, "max_qty": 1},
				{"group_key": "voucher", "label": "Voucher", "min_qty": 0, "max_qty": 3},
			],
			"options": [
				{
					"group_key": "accessory",
					"item_code": BACKPACK,
					"qty_per_unit": 1,
					"price_adjustment": BACKPACK_ADJ,
				},
				{
					"group_key": "accessory",
					"item_code": HEADPHONE,
					"qty_per_unit": 1,
					"price_adjustment": HEADPHONE_ADJ,
				},
				{
					"group_key": "voucher",
					"item_code": VOUCHER_PULSA,
					"qty_per_unit": 1,
					"price_adjustment": PULSA_ADJ,
				},
				{
					"group_key": "voucher",
					"item_code": VOUCHER_LISTRIK,
					"qty_per_unit": 1,
					"price_adjustment": LISTRIK_ADJ,
				},
			],
			"outlets": [{"pos_profile": PROFILE, "enabled": 1}],
		}
	).insert(ignore_permissions=True)


def _option_id(pkg, item_code):
	for option in pkg["options"]:
		if option["item_code"] == item_code:
			return option["option_id"]
	raise AssertionError(f"option for {item_code} not found")


class TestPackageQuote(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_package()
		frappe.db.commit()
		cls.pkg = next(p for p in get_packages(PROFILE) if p["name"] == PACKAGE)

	def choices(self, accessory=None, vouchers=None):
		"""Build a choices payload. `vouchers` maps item_code -> qty."""
		out = []
		if accessory:
			out.append(
				{
					"group_key": "accessory",
					"options": [{"option_id": _option_id(self.pkg, accessory), "qty": 1}],
				}
			)
		if vouchers:
			out.append(
				{
					"group_key": "voucher",
					"options": [
						{"option_id": _option_id(self.pkg, code), "qty": qty}
						for code, qty in vouchers.items()
					],
				}
			)
		return out

	def test_mandatory_item_is_always_included(self):
		result = quote(PACKAGE, self.choices(accessory=BACKPACK), PROFILE)

		components = [line for line in result["lines"] if line["role"] == COMPONENT_ROLE]
		self.assertIn(LAPTOP, [line["item_code"] for line in components])

	def test_parent_line_carries_price_and_components_are_free(self):
		result = quote(PACKAGE, self.choices(accessory=BACKPACK), PROFILE)

		parent = result["lines"][0]
		self.assertEqual(parent["role"], PARENT_ROLE)
		self.assertEqual(parent["item_code"], PARENT_ITEM)
		self.assertEqual(parent["rate"], BASE_PRICE + BACKPACK_ADJ)

		for line in result["lines"][1:]:
			self.assertEqual(line["rate"], 0.0)

	def test_choosing_the_priced_accessory_adds_its_adjustment(self):
		result = quote(PACKAGE, self.choices(accessory=HEADPHONE), PROFILE)

		self.assertEqual(result["total"], BASE_PRICE + HEADPHONE_ADJ)

	def test_exactly_one_group_rejects_zero_picks(self):
		with self.assertRaises(frappe.ValidationError):
			quote(PACKAGE, self.choices(), PROFILE)

	def test_exactly_one_group_rejects_two_picks(self):
		choices = [
			{
				"group_key": "accessory",
				"options": [
					{"option_id": _option_id(self.pkg, BACKPACK), "qty": 1},
					{"option_id": _option_id(self.pkg, HEADPHONE), "qty": 1},
				],
			}
		]

		with self.assertRaises(frappe.ValidationError):
			quote(PACKAGE, choices, PROFILE)

	def test_optional_group_allows_zero_picks(self):
		result = quote(PACKAGE, self.choices(accessory=BACKPACK, vouchers={}), PROFILE)

		self.assertEqual(result["total"], BASE_PRICE)

	def test_voucher_group_accepts_a_mix_up_to_three(self):
		result = quote(
			PACKAGE,
			self.choices(accessory=BACKPACK, vouchers={VOUCHER_PULSA: 2, VOUCHER_LISTRIK: 1}),
			PROFILE,
		)

		self.assertEqual(result["total"], BASE_PRICE + (2 * PULSA_ADJ) + LISTRIK_ADJ)

		qty_by_item = {
			line["item_code"]: line["qty"] for line in result["lines"] if line["role"] == COMPONENT_ROLE
		}
		self.assertEqual(qty_by_item[VOUCHER_PULSA], 2)
		self.assertEqual(qty_by_item[VOUCHER_LISTRIK], 1)

	def test_voucher_group_accepts_three_of_one_option(self):
		result = quote(PACKAGE, self.choices(accessory=BACKPACK, vouchers={VOUCHER_LISTRIK: 3}), PROFILE)

		self.assertEqual(result["total"], BASE_PRICE + (3 * LISTRIK_ADJ))

	def test_voucher_group_rejects_four_units(self):
		with self.assertRaises(frappe.ValidationError):
			quote(
				PACKAGE,
				self.choices(accessory=BACKPACK, vouchers={VOUCHER_PULSA: 2, VOUCHER_LISTRIK: 2}),
				PROFILE,
			)

	def test_unknown_group_is_rejected(self):
		choices = [{"group_key": "nope", "options": [{"option_id": "x", "qty": 1}]}]

		with self.assertRaises(frappe.ValidationError):
			quote(PACKAGE, choices, PROFILE)

	def test_option_from_another_group_is_rejected(self):
		choices = [
			{
				"group_key": "accessory",
				"options": [{"option_id": _option_id(self.pkg, VOUCHER_PULSA), "qty": 1}],
			}
		]

		with self.assertRaises(frappe.ValidationError):
			quote(PACKAGE, choices, PROFILE)


class TestInvoicePackageEnforcement(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_package()
		frappe.db.commit()
		cls.pkg = next(p for p in get_packages(PROFILE) if p["name"] == PACKAGE)

	def build_invoice(self, parent_rate, snapshot_qty=1):
		"""Sales Invoice-shaped doc carrying one package instance.

		Returns ``(doc, rows)``: `_dict.items` is dict.items, so the item rows
		must be handed back separately rather than read off the doc.
		"""
		option_id = _option_id(self.pkg, HEADPHONE)
		snapshot = {"selections": [{"group_key": "accessory", "option_id": option_id, "qty": snapshot_qty}]}

		rows = [
			frappe._dict(
				{
					"item_code": PARENT_ITEM,
					"qty": 1,
					"rate": parent_rate,
					"price_list_rate": parent_rate,
					"discount_amount": 0,
					"discount_percentage": 0,
					"pos_package": PACKAGE,
					"pos_package_instance": "pkg-test-1",
					"pos_package_role": PARENT_ROLE,
					"pos_package_snapshot": json.dumps(snapshot),
				}
			),
			frappe._dict(
				{
					"item_code": LAPTOP,
					"qty": 1,
					"rate": 0,
					"price_list_rate": 0,
					"discount_amount": 0,
					"discount_percentage": 0,
					"pos_package": PACKAGE,
					"pos_package_instance": "pkg-test-1",
					"pos_package_role": COMPONENT_ROLE,
				}
			),
			frappe._dict(
				{
					"item_code": HEADPHONE,
					"qty": snapshot_qty,
					"rate": 0,
					"price_list_rate": 0,
					"discount_amount": 0,
					"discount_percentage": 0,
					"pos_package": PACKAGE,
					"pos_package_instance": "pkg-test-1",
					"pos_package_role": COMPONENT_ROLE,
				}
			),
		]

		doc = frappe._dict({"is_return": 0, "pos_profile": PROFILE})
		doc["items"] = rows
		return doc, rows

	def test_tampered_parent_rate_is_overwritten_with_the_server_quote(self):
		"""A client claiming a cheap package price must not be believed."""
		doc, rows = self.build_invoice(parent_rate=1.0)

		validate_invoice_packages(doc)

		self.assertEqual(rows[0].rate, BASE_PRICE + HEADPHONE_ADJ)
		self.assertEqual(rows[0].price_list_rate, BASE_PRICE + HEADPHONE_ADJ)

	def test_component_rates_are_forced_to_zero(self):
		doc, rows = self.build_invoice(parent_rate=BASE_PRICE + HEADPHONE_ADJ)
		rows[1].rate = 999.0

		validate_invoice_packages(doc)

		self.assertEqual(rows[1].rate, 0)
		self.assertEqual(rows[2].rate, 0)

	def test_component_qty_not_matching_the_definition_is_rejected(self):
		"""Padding a package with extra free stock must fail validation."""
		doc, rows = self.build_invoice(parent_rate=BASE_PRICE + HEADPHONE_ADJ)
		rows[1].qty = 5

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(doc)

	def test_missing_parent_row_is_rejected(self):
		doc, rows = self.build_invoice(parent_rate=BASE_PRICE)
		rows[0].pos_package_role = COMPONENT_ROLE

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(doc)

	def test_invoice_without_packages_is_untouched(self):
		row = frappe._dict({"item_code": LAPTOP, "qty": 1, "rate": 500.0})
		doc = frappe._dict({"is_return": 0, "pos_profile": PROFILE})
		doc["items"] = [row]

		validate_invoice_packages(doc)

		self.assertEqual(row.rate, 500.0)

	def test_return_without_return_against_is_rejected(self):
		"""A package credit note must name the invoice it reverses, otherwise
		there is nothing to validate its rate and contents against."""
		doc, _rows = self.build_invoice(parent_rate=1.0)
		doc.is_return = 1

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(doc)

	def test_return_of_unknown_package_instance_is_rejected(self):
		"""Returning a package that never existed on the original invoice must
		fail rather than mint a credit note out of nothing."""
		doc, _rows = self.build_invoice(parent_rate=1.0)
		doc.is_return = 1
		doc.return_against = "NON-EXISTENT-INVOICE"

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(doc)


class TestPackageGrandTotal(unittest.TestCase):
	"""Frappe runs the controller's validate (which totals the invoice) BEFORE
	app hooks, so re-pricing a row is not enough — grand_total must be
	recalculated or a tampered payload is repriced yet still charged the old sum.
	"""

	@classmethod
	def setUpClass(cls):
		_ensure_package()
		frappe.db.commit()
		cls.pkg = next(p for p in get_packages(PROFILE) if p["name"] == PACKAGE)
		cls.company = frappe.db.get_value("POS Profile", PROFILE, "company")

	def build_real_invoice(self, parent_rate):
		option_id = _option_id(self.pkg, BACKPACK)
		result = quote(
			PACKAGE,
			[{"group_key": "accessory", "options": [{"option_id": option_id, "qty": 1}]}],
			PROFILE,
		)

		inv = frappe.new_doc("Sales Invoice")
		inv.customer = frappe.db.get_value("Customer", {}, "name")
		inv.company = self.company
		inv.pos_profile = PROFILE
		inv.is_pos = 0
		inv.set_posting_time = 1

		for idx, line in enumerate(result["lines"]):
			inv.append(
				"items",
				{
					"item_code": line["item_code"],
					"qty": line["qty"],
					"rate": parent_rate if idx == 0 else 0,
					"uom": line.get("uom") or "Nos",
					"warehouse": frappe.db.get_value("POS Profile", PROFILE, "warehouse"),
					"pos_package": PACKAGE,
					"pos_package_instance": "pkg-total-check",
					"pos_package_role": line["role"],
					"pos_package_snapshot": (
						json.dumps(result["snapshot"]) if line["role"] == PARENT_ROLE else None
					),
				},
			)

		inv.set_missing_values()
		return inv, result["total"]

	def test_totals_reflect_the_server_price_not_the_payload(self):
		"""net_total, not grand_total: the fixture company may add tax on top."""
		inv, true_total = self.build_real_invoice(parent_rate=1.0)

		inv.run_method("validate")

		self.assertEqual(inv.items[0].rate, true_total)
		self.assertEqual(inv.net_total, true_total)

	def test_tampered_and_honest_payloads_total_identically(self):
		"""The whole point of re-quoting: what the client sends cannot change
		the amount charged."""
		tampered, true_total = self.build_real_invoice(parent_rate=1.0)
		tampered.run_method("validate")

		honest, _ = self.build_real_invoice(parent_rate=true_total)
		honest.run_method("validate")

		self.assertEqual(tampered.grand_total, honest.grand_total)
		self.assertEqual(tampered.net_total, true_total)


class TestReturnExportPath(unittest.TestCase):
	"""ReturnInvoiceDialog.vue builds its payload from a field whitelist, so
	package fields never survive the trip — membership is re-derived on the
	server via the row link. These tests replay that exact shape."""

	@classmethod
	def setUpClass(cls):
		_ensure_package()
		frappe.db.commit()
		cls.pkg = next(p for p in get_packages(PROFILE) if p["name"] == PACKAGE)
		cls.company = frappe.db.get_value("POS Profile", PROFILE, "company")
		cls.original, cls.rows = cls._submit_package_invoice()

	@classmethod
	def _submit_package_invoice(cls):
		option_id = _option_id(cls.pkg, BACKPACK)
		result = quote(
			PACKAGE,
			[{"group_key": "accessory", "options": [{"option_id": option_id, "qty": 1}]}],
			PROFILE,
		)

		inv = frappe.new_doc("Sales Invoice")
		inv.customer = frappe.db.get_value("Customer", {}, "name")
		inv.company = cls.company
		inv.pos_profile = PROFILE
		inv.is_pos = 0
		inv.set_posting_time = 1

		for idx, line in enumerate(result["lines"]):
			inv.append(
				"items",
				{
					"item_code": line["item_code"],
					"qty": line["qty"],
					"rate": result["total"] if idx == 0 else 0,
					"uom": line.get("uom") or "Nos",
					"warehouse": frappe.db.get_value("POS Profile", PROFILE, "warehouse"),
					"pos_package": PACKAGE,
					"pos_package_instance": "pkg-export-path",
					"pos_package_role": line["role"],
					"pos_package_snapshot": (
						json.dumps(result["snapshot"]) if line["role"] == PARENT_ROLE else None
					),
				},
			)

		inv.set_missing_values()
		inv.submit()
		return inv.name, {row.item_code: row for row in inv.items}

	@staticmethod
	def _dialog_item(row):
		"""The exact field set ReturnInvoiceDialog.vue sends per line."""
		return frappe._dict(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": -abs(row.qty),
				"rate": row.rate,
				"warehouse": row.warehouse,
				"uom": row.uom,
				"conversion_factor": 1,
				"sales_invoice_item": row.name,
			}
		)

	def _return_doc(self, items):
		doc = frappe._dict(
			{
				"is_return": 1,
				"return_against": self.original,
				"pos_profile": PROFILE,
			}
		)
		doc["items"] = items
		return doc

	def test_dialog_shaped_package_return_is_accepted_and_mirrored(self):
		items = [self._dialog_item(row) for row in self.rows.values()]
		doc = self._return_doc(items)

		validate_invoice_packages(doc)

		parent = next(i for i in doc["items"] if i.item_code == PARENT_ITEM)
		self.assertEqual(parent.rate, self.rows[PARENT_ITEM].rate)
		self.assertEqual(parent.pos_package, PACKAGE)
		self.assertEqual(parent.pos_package_instance, "pkg-export-path")
		for row in doc["items"]:
			if row.get("pos_package_role") == COMPONENT_ROLE:
				self.assertEqual(row.rate, 0)

	def test_dialog_shaped_return_with_stripped_component_is_blocked(self):
		items = [self._dialog_item(row) for code, row in self.rows.items() if code != BACKPACK]

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(self._return_doc(items))

	def test_forged_package_row_without_row_link_is_blocked(self):
		items = [self._dialog_item(row) for row in self.rows.values()]
		forged = self._dialog_item(self.rows[PARENT_ITEM])
		forged.item_code = LAPTOP
		forged.pos_package = PACKAGE
		forged.pos_package_instance = "pkg-forged"
		forged.pos_package_role = PARENT_ROLE
		forged.sales_invoice_item = None
		items.append(forged)

		with self.assertRaises(frappe.ValidationError):
			validate_invoice_packages(self._return_doc(items))


class TestPackageAccessControl(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		_ensure_package()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_get_packages_rejects_users_without_profile_access(self):
		"""pos_profile comes from the caller, so an unassigned user must not be
		able to read another outlet's packages and pricing."""
		user = frappe.db.get_value(
			"User", {"enabled": 1, "user_type": "System User", "name": ("!=", "Administrator")}, "name"
		)
		if not user:
			self.skipTest("no non-admin user available")

		frappe.set_user(user)

		with self.assertRaises(frappe.PermissionError):
			get_packages(PROFILE)


if __name__ == "__main__":
	unittest.main()
