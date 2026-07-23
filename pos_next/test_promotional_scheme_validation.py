# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.test_promotions import ITEM_A, _resolve_company


def _make_scheme(name, item_code, promotion_type):
	company = _resolve_company()
	scheme = frappe.get_doc(
		{
			"doctype": "Promotional Scheme",
			"name": name,
			"company": company,
			"apply_on": "Item Code",
			"selling": 1,
			"items": [{"item_code": item_code}],
			"price_discount_slabs": [
				{
					"rule_description": "Test discount",
					"rate_or_discount": "Discount Percentage",
					"discount_percentage": 10,
				}
			],
		}
	)
	if frappe.db.has_column("Promotional Scheme", "promotion_type"):
		scheme.promotion_type = promotion_type
	return scheme


class TestPromotionalSchemeValidation(FrappeTestCase):
	def tearDown(self):
		super().tearDown()
		for name in ("_PNXT_TEST_SCHEME_A", "_PNXT_TEST_SCHEME_B"):
			if frappe.db.exists("Promotional Scheme", name):
				frappe.delete_doc("Promotional Scheme", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_duplicate_promotion_type_for_same_item_is_blocked(self):
		if not frappe.db.has_column("Promotional Scheme", "promotion_type"):
			self.skipTest("promotion_type custom field is not installed")

		first = _make_scheme("_PNXT_TEST_SCHEME_A", ITEM_A, "Item Level Discount")
		first.insert(ignore_permissions=True)

		second = _make_scheme("_PNXT_TEST_SCHEME_B", ITEM_A, "Item Level Discount")
		with self.assertRaises(frappe.ValidationError):
			second.insert(ignore_permissions=True)

	def test_different_promotion_type_for_same_item_is_allowed(self):
		if not frappe.db.has_column("Promotional Scheme", "promotion_type"):
			self.skipTest("promotion_type custom field is not installed")

		first = _make_scheme("_PNXT_TEST_SCHEME_A", ITEM_A, "Item Level Discount")
		first.insert(ignore_permissions=True)

		second = _make_scheme("_PNXT_TEST_SCHEME_B", ITEM_A, "GWP")
		second.price_discount_slabs = []
		second.append(
			"product_discount_slabs",
			{
				"rule_description": "GWP",
				"free_item": ITEM_A,
				"free_qty": 1,
				"same_item": 1,
			},
		)
		second.insert(ignore_permissions=True)
