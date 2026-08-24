# Copyright (c) 2026, BrainWise and contributors
"""pos_next must not import optional apps (compose only via Frappe hooks / Vue boot)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

POS_NEXT_PKG = Path(__file__).resolve().parent
POS_NEXT_APP = POS_NEXT_PKG.parent
SKIP_IMPORT_FILES = {"test_no_promotions_import.py", "test_split_smoke.py"}


def _python_files():
	for path in POS_NEXT_PKG.rglob("*.py"):
		if "__pycache__" in path.parts:
			continue
		yield path


def _forbidden_imports(forbidden: str, skip_names=()):
	violations = []
	for path in _python_files():
		if path.name in skip_names:
			continue
		try:
			tree = ast.parse(path.read_text(), filename=str(path))
		except SyntaxError:
			continue
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				for alias in node.names:
					if alias.name == forbidden or alias.name.startswith(forbidden + "."):
						violations.append(f"{path}:{node.lineno} import {alias.name}")
			elif isinstance(node, ast.ImportFrom):
				mod = node.module or ""
				if mod == forbidden or mod.startswith(forbidden + "."):
					violations.append(f"{path}:{node.lineno} from {mod}")
	return violations


class TestNoPromotionsImport(unittest.TestCase):
	def test_hooks_do_not_require_posnext_promotions(self):
		hooks = (POS_NEXT_PKG / "hooks.py").read_text()
		self.assertNotIn("posnext_promotions", hooks)
		self.assertNotIn("pos_next_promotions_provider", hooks)
		self.assertNotIn("pos_next_auth_provider", hooks)

	def test_no_python_import_of_posnext_promotions(self):
		violations = _forbidden_imports("posnext_promotions", skip_names=SKIP_IMPORT_FILES)
		self.assertEqual(violations, [], "posnext_promotions imports are forbidden:\n" + "\n".join(violations))

	def test_no_python_import_of_magento_or_miraaya(self):
		for pkg in ("magento_integration", "masar_miraaya"):
			violations = _forbidden_imports(pkg, skip_names=SKIP_IMPORT_FILES)
			self.assertEqual(violations, [], f"{pkg} imports are forbidden:\n" + "\n".join(violations))

	def test_magento_registry_hook_lists_exist(self):
		hooks = (POS_NEXT_PKG / "hooks.py").read_text()
		for name in (
			"pos_next_loyalty_provider",
			"pos_next_bootstrap_settings",
			"pos_next_customer_validators",
			"pos_next_customer_prepare",
			"pos_next_customer_after_insert",
		):
			self.assertIn(f"{name} = []", hooks)

	def test_no_gift_pool_backend_on_pos_next(self):
		self.assertFalse((POS_NEXT_PKG / "api" / "gift_pool.py").exists())
		self.assertFalse((POS_NEXT_PKG / "pos_next" / "doctype" / "pos_gift_pool_item").exists())

	def test_no_miraaya_receipt_on_pos_next(self):
		self.assertFalse((POS_NEXT_PKG / "pos_next" / "print_format" / "miraaya_receipt").exists())
		uninstall = (POS_NEXT_PKG / "uninstall.py").read_text()
		self.assertNotIn("Miraaya Receipt", uninstall)

	def test_invoice_cart_uses_wallet_api(self):
		invoice_cart = (POS_NEXT_APP / "POS" / "src" / "components" / "sale" / "InvoiceCart.vue").read_text()
		self.assertIn("pos_next.api.wallet.get_wallet_info", invoice_cart)
		self.assertNotIn("magento_integration", invoice_cart)

	def test_gift_pool_vue_is_boot_gated(self):
		promo_mgmt = (POS_NEXT_APP / "POS" / "src" / "components" / "sale" / "PromotionManagement.vue").read_text()
		self.assertIn("isPromotionsAppInstalled", promo_mgmt)
		self.assertIn("Gift Pool", promo_mgmt)
		pos_cart = (POS_NEXT_APP / "POS" / "src" / "stores" / "posCart.js").read_text()
		self.assertIn("isPromotionsAppInstalled", pos_cart)
		self.assertIn("Gift Pool", pos_cart)

	def test_customer_create_uses_bootstrap_flag(self):
		dialog = (POS_NEXT_APP / "POS" / "src" / "components" / "sale" / "CreateCustomerDialog.vue").read_text()
		self.assertIn("requiresSplitCustomerName", dialog)
		self.assertNotIn("masar_miraaya", dialog)
		self.assertNotIn("magento_integration", dialog)


if __name__ == "__main__":
	unittest.main()
