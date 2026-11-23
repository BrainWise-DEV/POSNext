from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.integrations import contract_gate
from pos_next.integrations.contract_gate import check

GATE = "pos_next.integrations.contract_gate.before_migrate"


def _importer(**mods):
	def importer(name):
		if name not in mods:
			raise ImportError(name)
		return mods[name]

	return importer


class TestContractGate(FrappeTestCase):
	def test_missing_attribute_reported(self):
		imp = _importer(magento_integration=SimpleNamespace())
		msgs = check({"magento_integration": (1, "0.2.0")}, ["magento_integration"], imp)
		self.assertEqual(
			msgs, ["Update magento_integration to >= 0.2.0 before migrating (an older version is installed)."]
		)

	def test_lower_version_reported(self):
		imp = _importer(posnext_promotions=SimpleNamespace(FF_CONTRACT=1))
		msgs = check({"posnext_promotions": (2, "0.2.0")}, ["posnext_promotions"], imp)
		self.assertEqual(
			msgs, ["Update posnext_promotions to >= 0.2.0 before migrating (an older version is installed)."]
		)

	def test_non_int_contract_is_old(self):
		imp = _importer(posnext_promotions=SimpleNamespace(FF_CONTRACT="2"))
		self.assertEqual(len(check({"posnext_promotions": (2, "0.2.0")}, ["posnext_promotions"], imp)), 1)

	def test_not_installed_ignored(self):
		self.assertEqual(check({"magento_integration": (1, "0.2.0")}, ["frappe"], _importer()), [])

	def test_ok_returns_empty(self):
		imp = _importer(magento_integration=SimpleNamespace(FF_CONTRACT=1))
		self.assertEqual(check({"magento_integration": (1, "0.2.0")}, ["magento_integration"], imp), [])

	def test_hook_throws_when_companion_old(self):
		imp = _importer(
			posnext_promotions=SimpleNamespace(FF_CONTRACT=1),
			magento_integration=SimpleNamespace(FF_CONTRACT=1),
		)
		apps = ["frappe", "posnext_promotions", "magento_integration"]
		with patch("frappe.get_installed_apps", return_value=apps):
			with self.assertRaises(frappe.ValidationError) as cm:
				contract_gate.before_migrate(importer=imp)
		self.assertEqual(
			str(cm.exception),
			"Update posnext_promotions to >= 0.4.0 before migrating (an older version is installed).",
		)

	def test_hook_passes_when_current(self):
		imp = _importer(
			posnext_promotions=SimpleNamespace(FF_CONTRACT=4),
			magento_integration=SimpleNamespace(FF_CONTRACT=1),
		)
		with patch("frappe.get_installed_apps", return_value=["posnext_promotions", "magento_integration"]):
			contract_gate.before_migrate(importer=imp)

	def test_contract_needs_promotions_4(self):
		"""H2: pos_next stamps a one-time offer under an "Add on top" coupon (D-R3-04 b),
		which needs posnext_promotions' contract 4: an older coupon-share check reads the
		invoice's own redemption as an earlier one and refuses the sale."""
		import pos_next

		self.assertEqual(pos_next.FF_CONTRACT, 2)
		self.assertEqual(pos_next.__version__, "2.6.0")
		self.assertEqual(contract_gate.REQUIREMENTS["posnext_promotions"], (4, "0.4.0"))
		imp = _importer(
			posnext_promotions=SimpleNamespace(FF_CONTRACT=3),
			magento_integration=SimpleNamespace(FF_CONTRACT=1),
		)
		self.assertEqual(
			check(contract_gate.REQUIREMENTS, ["posnext_promotions", "magento_integration"], imp),
			["Update posnext_promotions to >= 0.4.0 before migrating (an older version is installed)."],
		)

	def test_gate_registered_in_before_migrate_hooks(self):
		self.assertIn(GATE, frappe.get_hooks("before_migrate", app_name="pos_next"))
