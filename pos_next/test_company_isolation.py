import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
	import frappe  # noqa: F401
except ModuleNotFoundError:
	sys.modules["frappe"] = SimpleNamespace(
		defaults=SimpleNamespace(get_user_default=lambda *args, **kwargs: None),
		get_all=lambda *args, **kwargs: [],
		db=SimpleNamespace(
			get_value=lambda *args, **kwargs: None,
			escape=lambda value: f"'{value}'",
		),
		session=SimpleNamespace(user="Guest"),
	)

from pos_next import company_isolation


class TestCompanyIsolation(unittest.TestCase):
	def test_get_user_companies_combines_defaults_permissions_and_employee_company(self):
		fake_frappe = SimpleNamespace(
			defaults=SimpleNamespace(get_user_default=lambda *args, **kwargs: "Company A"),
			get_all=lambda *args, **kwargs: ["Company B", "Company A"],
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "Company C"),
			session=SimpleNamespace(user="demo@example.com"),
		)

		with patch.object(company_isolation, "frappe", fake_frappe):
			companies = company_isolation.get_user_companies("demo@example.com")

		self.assertEqual(companies, ["Company A", "Company B", "Company C"])

	def test_permission_query_conditions_restrict_by_custom_company(self):
		fake_frappe = SimpleNamespace(
			db=SimpleNamespace(escape=lambda value: f"'{value}'"),
			session=SimpleNamespace(user="demo@example.com"),
		)

		with patch(
			"pos_next.company_isolation.get_user_companies",
			return_value=["Brainwise"],
		), patch.object(company_isolation, "frappe", fake_frappe):
			condition = company_isolation.customer_permission_query_conditions(
				"demo@example.com"
			)

		self.assertEqual(condition, "`tabCustomer`.`custom_company` IN ('Brainwise')")

	def test_permission_query_conditions_return_false_condition_when_no_company(self):
		with patch(
			"pos_next.company_isolation.get_user_companies",
			return_value=[],
		):
			condition = company_isolation.supplier_permission_query_conditions(
				"demo@example.com"
			)

		self.assertEqual(condition, "1=0")

	def test_has_permission_checks_document_company(self):
		doc = {"custom_company": "Company A"}
		with patch(
			"pos_next.company_isolation.get_user_companies",
			return_value=["Company A"],
		):
			self.assertTrue(company_isolation.brand_has_permission(doc, "demo@example.com"))

		with patch(
			"pos_next.company_isolation.get_user_companies",
			return_value=["Company B"],
		):
			self.assertFalse(company_isolation.brand_has_permission(doc, "demo@example.com"))


class TestCustomCompanyFieldConfiguration(unittest.TestCase):
	def test_custom_company_fields_are_required_without_default_values(self):
		custom_dir = Path(__file__).resolve().parent / "pos_next" / "custom"
		files_to_check = [
			"item.json",
			"customer.json",
			"supplier.json",
			"item_group.json",
			"customer_group.json",
			"supplier_group.json",
			"brand.json",
			"price_list.json",
		]

		for file_name in files_to_check:
			with self.subTest(file_name=file_name):
				content = json.loads((custom_dir / file_name).read_text())
				field = next(
					row for row in content.get("custom_fields", []) if row.get("fieldname") == "custom_company"
				)
				self.assertEqual(field.get("reqd"), 1)
				self.assertIn(field.get("default"), (None, ""))
