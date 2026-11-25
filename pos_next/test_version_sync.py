"""The POS header shows POS/package.json's version; it must match the app release."""

import json
import os
import unittest

import pos_next

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(pos_next.__file__)))


class TestVersionSync(unittest.TestCase):
	def test_package_versions_match_the_app_release(self):
		for rel in ("package.json", os.path.join("POS", "package.json")):
			with open(os.path.join(APP_ROOT, rel), encoding="utf-8") as f:
				self.assertEqual(json.load(f)["version"], pos_next.__version__, rel)
