# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The seed snapshot is found even when Frappe saved it under a changed name (D-6).

	bench --site <site> execute pos_next.dev_tests.run --kwargs "{'module': 'pos_next.test_uit_snapshot'}"
"""

import json
import unittest

import frappe

from pos_next import ui_test_seed as uit


class TestSnapshotLookup(unittest.TestCase):
	def setUp(self):
		uit._delete_snapshots()

	def tearDown(self):
		uit._delete_snapshots()
		frappe.db.rollback()

	def _file(self, file_name, payload):
		return frappe.get_doc(
			{"doctype": "File", "file_name": file_name, "is_private": 1, "content": json.dumps(payload)}
		).insert(ignore_permissions=True)

	def test_finds_a_snapshot_saved_under_a_changed_name(self):
		doc = self._file("UIT-seed-snapshotd6bce8.json", {"a": 1})
		self.assertEqual(uit._snapshot_name(), doc.name)
		self.assertEqual(uit._load_snapshot(), {"a": 1})

	def test_save_replaces_every_copy(self):
		self._file("UIT-seed-snapshot.json", {"old": 1})
		self._file("UIT-seed-snapshotabc123.json", {"old": 2})
		uit._save_snapshot({"new": 1})
		self.assertEqual(len(uit._snapshot_names()), 1)
		self.assertEqual(uit._load_snapshot(), {"new": 1})

	def test_teardown_helper_removes_every_copy(self):
		self._file("UIT-seed-snapshot.json", {"x": 1})
		self._file("UIT-seed-snapshotabc123.json", {"x": 2})
		uit._delete_snapshots()
		self.assertIsNone(uit._snapshot_name())

	def test_ignores_unrelated_files_with_the_same_prefix(self):
		doc = self._file("UIT-seed-snapshot-notes.json", {"n": 1})
		self.assertIsNone(uit._snapshot_name())
		doc.delete(ignore_permissions=True)
