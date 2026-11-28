# Copyright (c) 2026, BrainWise and contributors
"""pos_next's own translations win over other apps' in the POS dictionary."""

import unittest
from unittest.mock import patch

from pos_next.api import localization


class TestAppTranslationsPrecedence(unittest.TestCase):
	def test_pos_next_csv_overrides_other_apps(self):
		merged = {"Clear": "واضح", "Apply": "تقديم", "Save": "حفظ"}
		own = {"Clear": "مسح", "Apply": "تطبيق"}
		with (
			patch.object(localization.translate, "get_all_translations", return_value=merged),
			patch.object(localization.translate, "get_translations_from_apps", return_value=own) as own_apps,
			patch.object(localization.translate, "get_user_translations", return_value={"Save": "احفظ"}),
			patch.object(localization.frappe.local, "lang", "ar", create=True),
		):
			result = localization.get_app_translations()
		own_apps.assert_called_once_with("ar", ["pos_next"])
		self.assertEqual(result, {"Clear": "مسح", "Apply": "تطبيق", "Save": "احفظ"})
		self.assertEqual(merged["Clear"], "واضح")
