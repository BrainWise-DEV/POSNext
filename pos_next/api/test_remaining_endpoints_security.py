# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import credit_sales, email_verification, invoices, promotions, qz
from pos_next.pos_next.report.sales_vs_shifts_report import sales_vs_shifts_report


class TestRemainingEndpointsSecurity(FrappeTestCase):
	def test_cleanup_old_drafts_rejects_zero_or_too_small_max_age_hours(self):
		with self.assertRaises(frappe.ValidationError):
			invoices.cleanup_old_drafts(pos_profile="Main POS", max_age_hours=0)

		with self.assertRaises(frappe.ValidationError):
			invoices.cleanup_old_drafts(pos_profile="Main POS", max_age_hours=12)

	def test_cleanup_old_drafts_scopes_non_supervisor_to_own_drafts_and_requires_profile(self):
		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
		):
			with self.assertRaises(frappe.ValidationError):
				invoices.cleanup_old_drafts(pos_profile=None, max_age_hours=48)

		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.invoices.ensure_pos_user", return_value="cashier@example.com"),
			patch("pos_next.api.invoices.is_pos_supervisor", return_value=False),
			patch("pos_next.api.invoices.frappe.get_all", return_value=[]) as mock_get_all,
		):
			invoices.cleanup_old_drafts(pos_profile="Main POS", max_age_hours=48)
			filters = mock_get_all.call_args.kwargs["filters"]
			self.assertEqual(filters["owner"], "cashier@example.com")
			self.assertEqual(filters["pos_profile"], "Main POS")

	def test_return_endpoints_reject_invalid_doctype_and_missing_permissions(self):
		with self.assertRaises(frappe.PermissionError):
			invoices.search_invoices_for_return(doctype="User")

		with (
			patch("pos_next.api.invoices.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.invoices.frappe.has_permission",
				side_effect=frappe.PermissionError("No read"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				invoices.get_returnable_invoices()
			with self.assertRaises(frappe.PermissionError):
				invoices.search_invoice_by_number("SINV-001")
			with self.assertRaises(frappe.PermissionError):
				invoices.check_invoice_return_validity("SINV-001")
			with self.assertRaises(frappe.PermissionError):
				invoices.get_invoice_for_return("SINV-001")
			with self.assertRaises(frappe.PermissionError):
				invoices.prepare_return_invoice("SINV-001")

	def test_credit_sales_endpoints_enforce_profile_and_permissions(self):
		with (
			patch("pos_next.api.credit_sales.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.credit_sales.ensure_pos_user",
				side_effect=frappe.PermissionError("No access"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				credit_sales.get_credit_sale_summary("Other POS")
			with self.assertRaises(frappe.PermissionError):
				credit_sales.get_credit_invoices("Other POS")
			with self.assertRaises(frappe.PermissionError):
				credit_sales.get_available_credit("CUST-1", "Test Co", pos_profile="Other POS")

		with (
			patch("pos_next.api.credit_sales.ensure_desk_user", return_value="cashier@example.com"),
			patch("pos_next.api.credit_sales.is_pos_supervisor", return_value=False),
			patch("pos_next.api.credit_sales.frappe.has_permission", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				credit_sales.cancel_credit_journal_entries("SINV-1")

	def test_email_otp_enforces_pos_profile_access(self):
		with (
			patch("pos_next.api.email_verification.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.email_verification.ensure_pos_user",
				side_effect=frappe.PermissionError("Denied"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				email_verification.send_email_otp("CUST-1", pos_profile="Other POS")
			with self.assertRaises(frappe.PermissionError):
				email_verification.verify_email_otp("CUST-1", "123456", pos_profile="Other POS")

	def test_qz_requires_pos_membership_and_caps_message_size(self):
		with (
			patch("pos_next.api.qz.ensure_desk_user", return_value="random_desk@example.com"),
			patch("pos_next.api.qz.is_pos_supervisor", return_value=False),
			patch.object(frappe.db, "exists", return_value=None),
		):
			with self.assertRaises(frappe.PermissionError):
				qz.get_certificate()
			with self.assertRaises(frappe.PermissionError):
				qz.get_certificate_download()
			with self.assertRaises(frappe.PermissionError):
				qz.sign_message("hello")

		with self.assertRaises(frappe.ValidationError):
			qz.sign_message("x" * (qz.MAX_QZ_MESSAGE_LENGTH + 1))

	def test_referral_endpoints_enforce_permissions(self):
		with (
			patch("pos_next.api.promotions.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.promotions.frappe.has_permission",
				side_effect=frappe.PermissionError("No Customer write"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				promotions.apply_referral_code("REF-1", "CUST-1")

		with (
			patch("pos_next.api.promotions.ensure_desk_user", return_value="cashier@example.com"),
			patch(
				"pos_next.api.promotions.check_promotion_permissions",
				side_effect=frappe.PermissionError("No promo read"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				promotions.get_referral_codes()

	def test_sales_vs_shifts_report_charts_enforce_access(self):
		with (
			patch(
				"pos_next.pos_next.report.sales_vs_shifts_report.sales_vs_shifts_report.ensure_desk_user",
				return_value="cashier@example.com",
			),
			patch(
				"pos_next.pos_next.report.sales_vs_shifts_report.sales_vs_shifts_report.ensure_pos_user",
				side_effect=frappe.PermissionError("Denied"),
			),
		):
			with self.assertRaises(frappe.PermissionError):
				sales_vs_shifts_report.get_hourly_breakdown({"pos_profile": "Other POS"})
			with self.assertRaises(frappe.PermissionError):
				sales_vs_shifts_report.get_payment_method_breakdown({"pos_profile": "Other POS"})
			with self.assertRaises(frappe.PermissionError):
				sales_vs_shifts_report.get_daily_trend({"pos_profile": "Other POS"})
