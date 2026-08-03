# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

import frappe

from pos_next.api.customers import (
	_get_customer_assignment_context,
	_prepare_customer_for_magento_publish,
	_set_customer_magento_email_fields,
	create_customer,
	get_customers,
	get_default_loyalty_program_from_settings,
)


class TestCustomersAPI(unittest.TestCase):
	@patch("pos_next.api.customers.frappe.logger")
	@patch("pos_next.api.customers.frappe.get_all")
	@patch("pos_next.api.customers.frappe.db")
	def test_get_customers_applies_search_term_filters(self, mock_db, mock_get_all, mock_logger):
		mock_logger.return_value = Mock()
		mock_get_all.return_value = []

		get_customers(search_term="john", limit=10)

		mock_get_all.assert_called_once()
		kwargs = mock_get_all.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"disabled": 0})
		self.assertEqual(
			kwargs["or_filters"],
			[
				["Customer", "name", "like", "%john%"],
				["Customer", "customer_name", "like", "%john%"],
				["Customer", "mobile_no", "like", "%john%"],
				["Customer", "email_id", "like", "%john%"],
			],
		)

	@patch("pos_next.api.customers.frappe.db.get_value")
	def test_get_default_loyalty_program_from_settings_uses_explicit_pos_profile(self, mock_get_value):
		mock_get_value.return_value = "LOYALTY-A"

		result = get_default_loyalty_program_from_settings(pos_profile="POS-A")

		self.assertEqual(result, "LOYALTY-A")
		mock_get_value.assert_called_once_with(
			"POS Settings",
			{"enabled": 1, "pos_profile": "POS-A"},
			"default_loyalty_program",
		)

	@patch("pos_next.api.customers.frappe.get_cached_value")
	@patch("pos_next.api.customers.frappe.get_all")
	def test_get_default_loyalty_program_from_settings_skips_ambiguous_company_context(
		self,
		mock_get_all,
		mock_get_cached_value,
	):
		mock_get_all.return_value = [
			Mock(pos_profile="POS-1", default_loyalty_program="LOYALTY-A"),
			Mock(pos_profile="POS-2", default_loyalty_program="LOYALTY-B"),
		]
		mock_get_cached_value.side_effect = ["Company A", "Company A"]

		result = get_default_loyalty_program_from_settings(company="Company A")

		self.assertIsNone(result)

	@patch(
		"pos_next.api.customers.frappe.local",
		new=Mock(form_dict={"company": "Company A", "pos_profile": "POS-A"}),
	)
	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	def test_get_customer_assignment_context_uses_request_context(self):
		company, pos_profile = _get_customer_assignment_context()

		self.assertEqual(company, "Company A")
		self.assertEqual(pos_profile, "POS-A")

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.frappe.has_permission")
	@patch("pos_next.api.customers.is_miraaya_loyalty_available", return_value=True)
	def test_create_customer_requires_magento_names_when_miraaya_installed(
		self,
		_mock_miraaya,
		mock_has_permission,
		mock_get_loyalty,
		mock_get_doc,
	):
		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = "LOYALTY-A"

		with self.assertRaises(frappe.ValidationError):
			create_customer(
				customer_name="John Doe",
				custom_first_name="John",
				custom_last_name="Doe",
				customer_group="Individual",
				territory="All Territories",
				pos_profile="POS-A",
			)

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers._prepare_customer_for_magento_publish")
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.frappe.has_permission")
	@patch("pos_next.api.customers.is_miraaya_loyalty_available", return_value=True)
	def test_create_customer_sets_magento_fields_when_miraaya_installed(
		self,
		_mock_miraaya,
		mock_has_permission,
		mock_get_loyalty,
		mock_get_doc,
		mock_prepare_magento,
	):
		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = "LOYALTY-A"

		customer_doc = Mock()
		customer_doc.as_dict.return_value = {"name": "CUST-0001"}
		customer_doc.reload = Mock()
		mock_get_doc.return_value = customer_doc

		with patch("pos_next.api.customers.frappe.get_meta") as mock_get_meta:
			meta = Mock()
			meta.has_field.return_value = True
			mock_get_meta.return_value = meta

			create_customer(
				customer_name="John Doe",
				custom_first_name="John",
				custom_last_name="Doe",
				email_id="john@example.com",
				customer_group="Individual",
				territory="All Territories",
				pos_profile="POS-A",
			)

		customer_doc.update.assert_called_once()
		customer_doc.insert.assert_called_once_with()
		mock_prepare_magento.assert_called_once()
		customer_doc.save.assert_called_once_with()

	@patch("pos_next.api.customers.frappe.get_meta")
	@patch("pos_next.api.customers.frappe.db.set_value")
	def test_set_customer_magento_email_fields_writes_known_fields(
		self,
		mock_set_value,
		mock_get_meta,
	):
		meta = Mock()
		meta.has_field.side_effect = lambda fieldname: fieldname in ("custom_email", "email_id")
		mock_get_meta.return_value = meta

		_set_customer_magento_email_fields("CUST-0001", "john@example.com")

		mock_set_value.assert_any_call(
			"Customer", "CUST-0001", "custom_email", "john@example.com", update_modified=False
		)
		mock_set_value.assert_any_call(
			"Customer", "CUST-0001", "email_id", "john@example.com", update_modified=False
		)

	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.frappe.db.get_value", return_value="CONTACT-1")
	@patch("pos_next.api.customers._set_customer_magento_email_fields")
	def test_prepare_customer_for_magento_publish_updates_existing_contact(
		self,
		mock_set_email_fields,
		_mock_get_value,
		mock_get_doc,
	):
		contact = Mock()
		contact.email_ids = []
		contact.first_name = ""
		contact.last_name = ""
		mock_get_doc.return_value = contact

		customer = Mock()
		customer.name = "CUST-0001"
		customer.reload = Mock()

		_prepare_customer_for_magento_publish(
			customer,
			email_id="john@example.com",
			first_name="John",
			last_name="Doe",
		)

		contact.add_email.assert_called_once_with("john@example.com", is_primary=1)
		contact.save.assert_called_once_with(ignore_permissions=True)
		mock_set_email_fields.assert_called_once_with("CUST-0001", "john@example.com")
		customer.reload.assert_called_once_with()

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.frappe.has_permission")
	@patch("pos_next.api.customers.is_miraaya_loyalty_available", return_value=False)
	def test_create_customer_uses_pos_profile_for_loyalty_assignment(
		self,
		_mock_miraaya,
		mock_has_permission,
		mock_get_loyalty,
		mock_get_doc,
	):
		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = "LOYALTY-A"

		customer_doc = Mock()
		customer_doc.as_dict.return_value = {"name": "CUST-0001", "loyalty_program": "LOYALTY-A"}
		mock_get_doc.return_value = customer_doc

		result = create_customer(
			customer_name="John Doe",
			customer_group="Individual",
			territory="All Territories",
			pos_profile="POS-A",
		)

		mock_get_loyalty.assert_called_once_with(company=None, pos_profile="POS-A")
		customer_doc.insert.assert_called_once_with()
		self.assertEqual(result["loyalty_program"], "LOYALTY-A")
