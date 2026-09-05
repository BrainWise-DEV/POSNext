# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pos_next.api import customer_dues


def _builder_with_result(result):
	"""A query-builder stub whose chained calls return the given rows from .run()."""

	class _Builder:
		def select(self, *_a, **_k):
			return self

		def where(self, *_a, **_k):
			return self

		def groupby(self, *_a, **_k):
			return self

		def run(self, *_a, **_k):
			return result

	return _Builder()


class TestCreditCustomersSummary(unittest.TestCase):
	@patch("pos_next.api.customer_dues.frappe.db.get_value", return_value="EGP")
	@patch("pos_next.api.customer_dues.frappe.qb.from_")
	@patch("pos_next.api.customer_dues.frappe.has_permission", return_value=True)
	def test_summary_nets_returns_against_outstanding(self, _perm, mock_from, _gv):
		# Regular invoices (is_return=0): positive outstanding per customer
		regular_rows = [
			SimpleNamespace(
				customer="CUST-A", customer_name="Mixed Customer",
				total_outstanding=382, due_count=14,
			),
			SimpleNamespace(
				customer="CUST-B", customer_name="Owes Only",
				total_outstanding=150, due_count=1,
			),
			SimpleNamespace(
				customer="CUST-C", customer_name="Fully Credited",
				total_outstanding=50, due_count=1,
			),
		]
		# Return invoices (is_return=1, outstanding<0): credit per customer
		return_rows = [
			SimpleNamespace(customer="CUST-A", total_credit=133),
			SimpleNamespace(customer="CUST-C", total_credit=50),
		]
		mock_from.side_effect = [
			_builder_with_result(regular_rows),
			_builder_with_result(return_rows),
		]

		result = customer_dues.get_credit_customers_summary(company="Sonex")

		# CUST-C is fully offset by its return credit → excluded (net_balance == 0)
		names = [c["customer"] for c in result["customers"]]
		self.assertEqual(names, ["CUST-A", "CUST-B"])  # sorted by net_balance desc

		mixed = result["customers"][0]
		self.assertEqual(mixed["total_outstanding"], 382)
		self.assertEqual(mixed["total_credit"], 133)
		self.assertEqual(mixed["net_balance"], 249)
		self.assertEqual(mixed["due_count"], 14)

		self.assertEqual(result["totals"]["customer_count"], 2)
		self.assertEqual(result["totals"]["net_balance"], 399)  # 249 + 150
		self.assertEqual(result["currency"], "EGP")

	@patch("pos_next.api.customer_dues.frappe.throw", side_effect=RuntimeError("Not permitted"))
	@patch("pos_next.api.customer_dues.frappe.has_permission", return_value=False)
	def test_summary_requires_read_permission(self, _perm, _throw):
		with self.assertRaisesRegex(RuntimeError, "Not permitted"):
			customer_dues.get_credit_customers_summary(company="Sonex")
