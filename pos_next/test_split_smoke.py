# Copyright (c) 2026, BrainWise and contributors
"""Smoke tests for optional-app split (Magento / promotions / Miraaya)."""

import unittest
from unittest.mock import patch

import frappe

from pos_next.integrations.registry import (
	extend_bootstrap_settings,
	get_loyalty_provider,
	is_external_loyalty_available,
	is_external_loyalty_mode,
	prepare_customer_doc,
)


def _app_installed(name: str) -> bool:
	return name in frappe.get_installed_apps()


class TestMagentoSplitSmoke(unittest.TestCase):
	def test_loyalty_provider_hook_registered(self):
		provider = get_loyalty_provider()
		if _app_installed("magento_integration"):
			self.assertIsNotNone(provider)
			self.assertTrue(callable(provider.get("is_available")))
			self.assertTrue(callable(provider.get("is_loyalty_mode")))
			self.assertTrue(callable(provider.get("get_balance")))
		else:
			self.assertIsNone(provider)
			self.assertFalse(is_external_loyalty_available())
			self.assertFalse(is_external_loyalty_mode("POS-TEST"))

	def test_bootstrap_settings_hook_extends_flags(self):
		settings = {"magento_loyalty_available": 0, "miraaya_installed": 0}
		extend_bootstrap_settings(settings)
		self.assertIn("miraaya_installed", settings)
		self.assertIn("magento_loyalty_available", settings)

	def test_magento_doc_events_registered(self):
		if not _app_installed("magento_integration"):
			self.skipTest("magento_integration is not installed")
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

	def test_prepare_customer_doc_is_generic(self):
		result = prepare_customer_doc(frappe._dict(name="CUST-TEST"), custom_is_publish=0)
		self.assertIsInstance(result, bool)

	def test_magento_lp_balance_api_callable(self):
		if not _app_installed("magento_integration"):
			self.skipTest("magento_integration is not installed")
		from magento_integration.api.magento_loyalty import get_lp_balance_for_customer

		result = get_lp_balance_for_customer("NONEXISTENT-CUSTOMER", pos_profile=None)
		self.assertIn("wallet_enabled", result)
		self.assertIn("balance_iqd", result)
		self.assertIn("balance_points", result)

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

	def test_promotions_override_when_installed(self):
		if not _app_installed("posnext_promotions"):
			self.skipTest("posnext_promotions is not installed")
		overrides = frappe.get_hooks("override_whitelisted_methods") or {}
		mapped = overrides.get("pos_next.api.gift_pool.gift_pool_item_query")
		if isinstance(mapped, (list, tuple)):
			mapped = mapped[-1] if mapped else None
		self.assertEqual(mapped, "posnext_promotions.api.gift_pool.gift_pool_item_query")
		self.assertTrue(frappe.db.exists("DocType", "POS Gift Pool Item"))


def run_smoke_tests():
	loader = unittest.TestLoader()
	suite = loader.loadTestsFromTestCase(TestMagentoSplitSmoke)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return 0 if result.wasSuccessful() else 1
