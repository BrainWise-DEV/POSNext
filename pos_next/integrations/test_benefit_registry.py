from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next import utils
from pos_next.integrations import registry

HOOK = "pos_next_customer_benefit_providers"
PATH = "x.benefit_provider"


def _run(providers, customer="CUST-1", pos_profile="P1"):
	hooks = {HOOK: list(providers)} if providers else {}
	attrs = {path: fn for path, fn in providers.items()} if providers else {}
	with (
		patch.object(frappe, "get_hooks", lambda k, *a, **kw: hooks.get(k, [])),
		patch.object(frappe, "get_attr", lambda p: attrs[p]),
		patch.object(utils, "log_error_without_telemetry") as log_error,
	):
		return registry.is_benefit_member(customer, pos_profile), log_error


def _rates(providers, doc):
	hooks = {HOOK: list(providers)} if providers else {}
	with (
		patch.object(frappe, "get_hooks", lambda k, *a, **kw: hooks.get(k, [])),
		patch.object(frappe, "get_attr", lambda p: providers[p]),
		patch.object(utils, "log_error_without_telemetry") as log_error,
	):
		return registry.fnf_line_rates(doc), log_error


class TestBenefitRegistry(FrappeTestCase):
	def test_no_provider_false(self):
		result, log_error = _run({})
		self.assertFalse(result)
		log_error.assert_not_called()

	def test_provider_true(self):
		seen = []

		def is_member(customer, pos_profile=None):
			seen.append((customer, pos_profile))
			return True

		result, _ = _run({PATH: lambda: {"is_member": is_member}})
		self.assertIs(result, True)
		self.assertEqual(seen, [("CUST-1", "P1")])

	def test_provider_false(self):
		result, _ = _run({PATH: lambda: {"is_member": lambda c, pos_profile=None: False}})
		self.assertIs(result, False)

	def test_no_customer_false(self):
		result, _ = _run({PATH: lambda: {"is_member": lambda c, pos_profile=None: True}}, customer=None)
		self.assertFalse(result)

	def test_provider_exception_false_and_logged(self):
		def boom(customer, pos_profile=None):
			raise RuntimeError("secret-customer-data")

		result, log_error = _run({PATH: lambda: {"is_member": boom}})
		self.assertIs(result, False)
		# Path and exception class only: never the exception text.
		log_error.assert_called_once_with("Customer benefit provider", f"{PATH}: RuntimeError")

	def test_second_provider_used_after_first_fails(self):
		def boom():
			raise RuntimeError("x")

		result, _ = _run({PATH: boom, "y.p": lambda: {"is_member": lambda c, pos_profile=None: True}})
		self.assertIs(result, True)

	def test_fnf_line_rates_provider_exception_returns_empty(self):
		"""A failing ``fnf_line_rates`` explains nothing ({}), is logged by path and class only,
		and the next provider still answers."""

		def boom(doc):
			raise RuntimeError("secret-customer-data")

		doc = frappe._dict(doctype="Sales Invoice", items=[])
		rates, log_error = _rates({PATH: lambda: {"fnf_line_rates": boom}}, doc)
		self.assertEqual(rates, {})
		log_error.assert_called_once_with("Customer benefit provider", f"{PATH}: RuntimeError")
		rates, _ = _rates(
			{PATH: lambda: {"fnf_line_rates": boom}, "y.p": lambda: {"fnf_line_rates": lambda d: {"r1": 14}}},
			doc,
		)
		self.assertEqual(rates, {"r1": 14.0})

	def test_fnf_line_rates_without_provider_key_is_empty(self):
		doc = frappe._dict(doctype="Sales Invoice", items=[])
		self.assertEqual(_rates({}, doc)[0], {})
		self.assertEqual(_rates({PATH: lambda: {"is_member": lambda c, pos_profile=None: True}}, doc)[0], {})

	def test_fnf_line_rates_keeps_the_lowest_rate_and_drops_bad_values(self):
		doc = frappe._dict(doctype="Sales Invoice", items=[])
		rates, _ = _rates(
			{
				PATH: lambda: {"fnf_line_rates": lambda d: {"r1": 15, "r2": "x", "r3": None, "r4": -1}},
				"y.p": lambda: {"fnf_line_rates": lambda d: {"r1": 14}},
			},
			doc,
		)
		self.assertEqual(rates, {"r1": 14.0, "r4": 0.0})

	def test_no_get_attr_of_promotions(self):
		source = (Path(registry.__file__).parent.parent / "api" / "email_verification.py").read_text()
		self.assertNotIn("posnext_promotions", source)
