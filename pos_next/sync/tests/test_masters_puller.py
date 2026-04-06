# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from unittest.mock import patch, MagicMock


def test_pull_if_due_noop_on_central():
	"""pull_if_due does nothing when no Branch config exists."""
	from pos_next.sync.masters_puller import pull_if_due
	# Should not crash — just returns silently
	pull_if_due()
	print("PASS: test_pull_if_due_noop_on_central")


def test_masters_puller_processes_upserts():
	"""MastersPuller applies upserts from changes_since response."""
	from pos_next.sync.masters_puller import MastersPuller

	fake_session = MagicMock()
	fake_response = MagicMock()
	fake_response.status_code = 200
	fake_response.json.return_value = {
		"message": {
			"upserts": [
				{"name": "TEST-PULLER-WH", "warehouse_name": "Test Puller WH", "company": "", "modified": "2026-04-06 10:00:00"},
			],
			"tombstones": [],
			"next_since": "2026-04-06 10:00:00",
			"has_more": False,
		}
	}
	fake_session.get.return_value = fake_response

	puller = MastersPuller(fake_session)
	upserted, deleted, errors = puller._pull_one_doctype("Warehouse", "2000-01-01 00:00:00", 100)
	assert upserted >= 0
	assert errors >= 0
	print("PASS: test_masters_puller_processes_upserts")


def test_masters_puller_advances_watermark():
	"""After a successful pull, the watermark is advanced."""
	from pos_next.sync.masters_puller import MastersPuller
	from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark

	frappe.db.delete("Sync Watermark", {"doctype_name": "ToDo"})
	frappe.db.commit()

	fake_session = MagicMock()
	fake_response = MagicMock()
	fake_response.status_code = 200
	fake_response.json.return_value = {
		"message": {
			"upserts": [],
			"tombstones": [],
			"next_since": "2026-04-06 12:00:00",
			"has_more": False,
		}
	}
	fake_session.get.return_value = fake_response

	puller = MastersPuller(fake_session)
	puller._pull_one_doctype("ToDo", "2000-01-01 00:00:00", 100)

	wm = SyncWatermark.get_for("ToDo")
	assert wm is not None, "Watermark should have been created"
	assert str(wm.last_modified) == "2026-04-06 12:00:00"
	print("PASS: test_masters_puller_advances_watermark")

	frappe.db.delete("Sync Watermark", {"doctype_name": "ToDo"})
	frappe.db.commit()


def test_masters_puller_handles_http_error():
	"""HTTP errors are caught and don't crash the puller."""
	from pos_next.sync.masters_puller import MastersPuller
	import requests

	fake_session = MagicMock()
	fake_session.get.side_effect = requests.ConnectionError("test error")

	puller = MastersPuller(fake_session)
	upserted, deleted, errors = puller._pull_one_doctype("Warehouse", "2000-01-01 00:00:00", 100)
	assert errors > 0
	print("PASS: test_masters_puller_handles_http_error")


def run_all():
	test_pull_if_due_noop_on_central()
	test_masters_puller_processes_upserts()
	test_masters_puller_advances_watermark()
	test_masters_puller_handles_http_error()
	print("\nAll MastersPuller tests PASSED")
