# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.api.customers import (
    _get_customer_assignment_context,
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

    @patch("pos_next.api.customers.frappe.db")
    def test_get_default_loyalty_program_from_settings_uses_explicit_pos_profile(self, mock_db):
        mock_db.get_value.return_value = "LOYALTY-A"

        result = get_default_loyalty_program_from_settings(pos_profile="POS-A")

        self.assertEqual(result, "LOYALTY-A")
        mock_db.get_value.assert_called_once_with(
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

    @patch("pos_next.api.customers.frappe.local", new=Mock(form_dict={"company": "Company A", "pos_profile": "POS-A"}))
    @patch("pos_next.api.customers.frappe.flags", new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None))
    def test_get_customer_assignment_context_uses_request_context(self):
        company, pos_profile = _get_customer_assignment_context()

        self.assertEqual(company, "Company A")
        self.assertEqual(pos_profile, "POS-A")

    @patch("pos_next.api.customers.frappe.flags", new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None))
    @patch("pos_next.api.customers.frappe.get_doc")
    @patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
    @patch("pos_next.api.customers.frappe.has_permission")
    def test_create_customer_uses_pos_profile_for_loyalty_assignment(
        self,
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
