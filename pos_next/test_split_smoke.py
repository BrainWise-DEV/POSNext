# Copyright (c) 2026, BrainWise and contributors
"""Structural / seam tests for optional-app split (Magento / promotions / Miraaya).

These must prove the split on a bare bench (no optional apps installed).
Runtime checks of satellite apps belong in those apps' own suites.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from pos_next.integrations.registry import (
	extend_bootstrap_settings,
	get_loyalty_provider,
	is_external_loyalty_available,
	is_external_loyalty_mode,
	prepare_customer_doc,
)

POS_NEXT_PKG = Path(__file__).resolve().parent
REGISTRY_PATH = POS_NEXT_PKG / "integrations" / "registry.py"
HOOKS_PATH = POS_NEXT_PKG / "hooks.py"


def _get_hooks_literals_in_function(source: str, func_name: str) -> set[str]:
	"""String literals passed to frappe.get_hooks(...) inside a named function."""
	tree = ast.parse(source)
	found: set[str] = set()
	for node in ast.walk(tree):
		if not isinstance(node, ast.FunctionDef) or node.name != func_name:
			continue
		for child in ast.walk(node):
			if not isinstance(child, ast.Call):
				continue
			func = child.func
			is_get_hooks = (
				isinstance(func, ast.Attribute)
				and func.attr == "get_hooks"
				and isinstance(func.value, ast.Name)
				and func.value.id == "frappe"
			)
			if not is_get_hooks or not child.args:
				continue
			arg0 = child.args[0]
			if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
				found.add(arg0.value)
	return found


class TestMagentoSplitSmoke(unittest.TestCase):
	def test_registry_prepare_uses_customer_prepare_hook(self):
		hooks = _get_hooks_literals_in_function(REGISTRY_PATH.read_text(), "prepare_customer_doc")
		self.assertEqual(hooks, {"pos_next_customer_prepare"})

	def test_registry_bootstrap_uses_bootstrap_settings_hook(self):
		hooks = _get_hooks_literals_in_function(REGISTRY_PATH.read_text(), "extend_bootstrap_settings")
		self.assertEqual(hooks, {"pos_next_bootstrap_settings"})

	def test_registry_loyalty_uses_loyalty_provider_hook(self):
		hooks = _get_hooks_literals_in_function(REGISTRY_PATH.read_text(), "get_loyalty_provider")
		self.assertEqual(hooks, {"pos_next_loyalty_provider"})

	def test_prepare_customer_doc_aggregates_hook_truth(self):
		customer = frappe._dict(name="CUST-TEST")

		with patch("pos_next.integrations.registry.frappe.get_hooks", return_value=[]):
			self.assertFalse(prepare_customer_doc(customer, custom_is_publish=0))

		false_hook = MagicMock(return_value=False)
		with (
			patch(
				"pos_next.integrations.registry.frappe.get_hooks",
				return_value=["tests.prepare_false"],
			),
			patch("pos_next.integrations.registry.frappe.get_attr", return_value=false_hook),
		):
			self.assertFalse(prepare_customer_doc(customer, custom_is_publish=0))
		false_hook.assert_called_once_with(customer, custom_is_publish=0)

		true_hook = MagicMock(return_value=True)
		with (
			patch(
				"pos_next.integrations.registry.frappe.get_hooks",
				return_value=["tests.prepare_true"],
			),
			patch("pos_next.integrations.registry.frappe.get_attr", return_value=true_hook),
		):
			self.assertTrue(prepare_customer_doc(customer, custom_is_publish=1))
		true_hook.assert_called_once_with(customer, custom_is_publish=1)

	def test_extend_bootstrap_settings_invokes_registered_hooks(self):
		settings = {}

		def extender(s, pos_profile=None):
			s["miraaya_installed"] = 1
			s["magento_loyalty_available"] = 1
			s["seen_profile"] = pos_profile

		with (
			patch(
				"pos_next.integrations.registry.frappe.get_hooks",
				return_value=["tests.extend_settings"],
			),
			patch("pos_next.integrations.registry.frappe.get_attr", return_value=extender),
		):
			extend_bootstrap_settings(settings, "POS-TEST")

		self.assertEqual(settings["miraaya_installed"], 1)
		self.assertEqual(settings["magento_loyalty_available"], 1)
		self.assertEqual(settings["seen_profile"], "POS-TEST")

	def test_extend_bootstrap_settings_noop_without_hooks(self):
		settings = {"keep": 1}
		with patch("pos_next.integrations.registry.frappe.get_hooks", return_value=[]):
			extend_bootstrap_settings(settings)
		self.assertEqual(settings, {"keep": 1})

	def test_loyalty_provider_absent_without_optional_app(self):
		"""On a bare install the seam returns None; optional apps register via hooks."""
		if "magento_integration" in frappe.get_installed_apps():
			provider = get_loyalty_provider()
			self.assertIsNotNone(provider)
			self.assertTrue(callable(provider.get("is_available")))
			self.assertTrue(callable(provider.get("is_loyalty_mode")))
			self.assertTrue(callable(provider.get("get_balance")))
			return

		self.assertIsNone(get_loyalty_provider())
		self.assertFalse(is_external_loyalty_available())
		self.assertFalse(is_external_loyalty_mode("POS-TEST"))

	def test_pos_next_hooks_do_not_register_magento_handlers(self):
		hooks = HOOKS_PATH.read_text()
		self.assertNotIn("magento_integration", hooks)
		self.assertNotIn("redeem_magento_lp_on_submit", hooks)
		self.assertNotIn("add_magento_lp_on_submit", hooks)
		self.assertNotIn("pos_next.api.magento_loyalty", hooks)

	def test_pos_next_has_no_magento_module(self):
		with self.assertRaises((ImportError, ModuleNotFoundError)):
			import pos_next.api.magento_loyalty  # noqa: F401

	def test_integration_flag_defaults_live_in_constants(self):
		from pos_next.api.constants import DEFAULT_POS_SETTINGS

		self.assertIn("miraaya_installed", DEFAULT_POS_SETTINGS)
		self.assertIn("magento_loyalty_available", DEFAULT_POS_SETTINGS)
		self.assertEqual(DEFAULT_POS_SETTINGS["miraaya_installed"], 0)
		self.assertEqual(DEFAULT_POS_SETTINGS["magento_loyalty_available"], 0)

	@patch("pos_next.api.wallet.is_external_loyalty_mode", return_value=False)
	def test_wallet_balance_without_magento_mode(self, _mock_mode):
		from pos_next.api.wallet import get_customer_wallet_balance

		with patch("pos_next.api.wallet.frappe.db.get_value", return_value=None):
			balance = get_customer_wallet_balance("CUST-TEST", "Test Company")
			self.assertEqual(balance, 0.0)

	def test_wallet_info_includes_lp_aliases(self):
		from pos_next.api.wallet import get_wallet_info

		with (
			patch("pos_next.api.wallet.get_pos_settings", return_value={"enable_loyalty_program": 0}),
			patch("pos_next.api.wallet.is_external_loyalty_mode", return_value=False),
		):
			result = get_wallet_info("CUST-TEST", "Test Company", pos_profile="POS-TEST")
		self.assertIn("wallet_enabled", result)
		self.assertIn("balance_iqd", result)
		self.assertIn("balance_points", result)
		self.assertFalse(result["wallet_enabled"])

	def test_bootstrap_includes_integration_flag_defaults(self):
		from pos_next.api.bootstrap import get_initial_data

		profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="name", limit=1)
		if not profiles:
			self.skipTest("No active POS Profile on site")

		frappe.local.form_dict = frappe._dict(pos_profile=profiles[0])
		data = get_initial_data()
		settings = data.get("pos_settings") or {}
		self.assertIn("miraaya_installed", settings)
		self.assertIn("magento_loyalty_available", settings)
		self.assertTrue(data.get("success"))


def run_smoke_tests():
	loader = unittest.TestLoader()
	suite = loader.loadTestsFromTestCase(TestMagentoSplitSmoke)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return 0 if result.wasSuccessful() else 1
