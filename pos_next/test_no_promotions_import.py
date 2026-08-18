# Copyright (c) 2026, BrainWise and contributors
"""pos_next must not import posnext_promotions (compose only via Frappe hooks / Vue boot)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

POS_NEXT_PKG = Path(__file__).resolve().parent


def _python_files():
	for path in POS_NEXT_PKG.rglob("*.py"):
		if "__pycache__" in path.parts:
			continue
		yield path


class TestNoPromotionsImport(unittest.TestCase):
	def test_hooks_do_not_require_posnext_promotions(self):
		hooks = (POS_NEXT_PKG / "hooks.py").read_text()
		self.assertNotIn("posnext_promotions", hooks)
		self.assertNotIn("pos_next_promotions_provider", hooks)
		self.assertNotIn("pos_next_auth_provider", hooks)

	def test_no_python_import_of_posnext_promotions(self):
		violations = []
		for path in _python_files():
			if path.name == "test_no_promotions_import.py":
				continue
			try:
				tree = ast.parse(path.read_text(), filename=str(path))
			except SyntaxError:
				continue
			for node in ast.walk(tree):
				if isinstance(node, ast.Import):
					for alias in node.names:
						if alias.name == "posnext_promotions" or alias.name.startswith("posnext_promotions."):
							violations.append(f"{path}:{node.lineno} import {alias.name}")
				elif isinstance(node, ast.ImportFrom):
					mod = node.module or ""
					if mod == "posnext_promotions" or mod.startswith("posnext_promotions."):
						violations.append(f"{path}:{node.lineno} from {mod}")
		self.assertEqual(violations, [], "posnext_promotions imports are forbidden:\n" + "\n".join(violations))

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


if __name__ == "__main__":
	unittest.main()
