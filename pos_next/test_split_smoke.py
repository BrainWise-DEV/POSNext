# Copyright (c) 2026, BrainWise and contributors
"""Smoke tests for Magento integration split."""

import unittest
from unittest.mock import Mock, patch

import frappe

from pos_next.integrations.registry import (
	extend_bootstrap_settings,
	get_loyalty_provider,
	is_external_loyalty_available,
	is_external_loyalty_mode,
)


class TestMagentoSplitSmoke(unittest.TestCase):
	def test_loyalty_provider_hook_registered(self):
		provider = get_loyalty_provider()
		self.assertIsNotNone(provider)
		self.assertTrue(callable(provider.get("is_available")))
		self.assertTrue(callable(provider.get("is_loyalty_mode")))
		self.assertTrue(callable(provider.get("get_balance")))

	def test_bootstrap_settings_hook_extends_flags(self):
		settings = {"magento_loyalty_available": 0, "miraaya_installed": 0}
		extend_bootstrap_settings(settings)
		self.assertIn("miraaya_installed", settings)
		self.assertIn("magento_loyalty_available", settings)

	def test_magento_doc_events_registered(self):
		hooks = frappe.get_hooks("doc_events", {}).get("Sales Invoice", {}).get("on_submit", [])
		self.assertIn(
			"magento_integration.api.magento_loyalty.redeem_magento_lp_on_submit",
			hooks,
		)
		self.assertIn(
			"magento_integration.api.magento_loyalty.add_magento_lp_on_submit",
			hooks,
		)
		self.assertNotIn(
			"pos_next.api.magento_loyalty.redeem_magento_lp_on_submit",
			hooks,
		)

	def test_pos_next_has_no_magento_module(self):
		with self.assertRaises((ImportError, ModuleNotFoundError)):
			import pos_next.api.magento_loyalty  # noqa: F401

	@patch("pos_next.api.wallet.is_external_loyalty_mode", return_value=False)
	def test_wallet_balance_without_magento_mode(self, _mock_mode):
		from pos_next.api.wallet import get_customer_wallet_balance

		with patch("pos_next.api.wallet.frappe.db.get_value", return_value=None):
			balance = get_customer_wallet_balance("CUST-TEST", "Test Company")
			self.assertEqual(balance, 0.0)

	def test_magento_lp_balance_api_callable(self):
		from magento_integration.api.magento_loyalty import get_lp_balance_for_customer

		result = get_lp_balance_for_customer("NONEXISTENT-CUSTOMER", pos_profile=None)
		self.assertIn("wallet_enabled", result)
		self.assertFalse(result.get("wallet_enabled"))

	def test_bootstrap_includes_integration_flags(self):
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
