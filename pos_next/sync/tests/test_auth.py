# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from unittest.mock import patch, MagicMock


def test_session_login_caches_sid():
	"""After login, the session cookie (sid) is held in memory."""
	from pos_next.sync.auth import SyncSession

	fake_response = MagicMock()
	fake_response.status_code = 200
	fake_response.cookies = {"sid": "test-sid-xyz"}
	fake_response.raise_for_status = MagicMock()

	with patch("pos_next.sync.auth.requests.post", return_value=fake_response) as mock_post:
		session = SyncSession(
			central_url="https://central.test",
			username="sync@test.com",
			password="pw",
		)
		session.login()
		assert session._sid == "test-sid-xyz"
		# Second call does NOT re-login
		session.login()
		assert mock_post.call_count == 1
	print("PASS: test_session_login_caches_sid")


def test_session_login_failure_raises():
	"""Failed login raises SyncAuthError."""
	from pos_next.sync.auth import SyncSession
	from pos_next.sync.exceptions import SyncAuthError
	import requests

	fake_response = MagicMock()
	fake_response.status_code = 401
	fake_response.raise_for_status = MagicMock(
		side_effect=requests.HTTPError("401 Unauthorized")
	)

	with patch("pos_next.sync.auth.requests.post", return_value=fake_response):
		session = SyncSession(
			central_url="https://central.test",
			username="sync@test.com",
			password="bad",
		)
		raised = False
		try:
			session.login()
		except SyncAuthError:
			raised = True
		assert raised
	print("PASS: test_session_login_failure_raises")


def test_session_auto_relogin_on_401():
	"""A 401 response from an authenticated request triggers one re-login + retry."""
	from pos_next.sync.auth import SyncSession

	# First login succeeds
	login_resp = MagicMock()
	login_resp.status_code = 200
	login_resp.cookies = {"sid": "sid-1"}
	login_resp.raise_for_status = MagicMock()

	# First authenticated call returns 401
	call_resp_401 = MagicMock()
	call_resp_401.status_code = 401

	# Re-login produces new sid
	login_resp_2 = MagicMock()
	login_resp_2.status_code = 200
	login_resp_2.cookies = {"sid": "sid-2"}
	login_resp_2.raise_for_status = MagicMock()

	# Retry succeeds
	call_resp_ok = MagicMock()
	call_resp_ok.status_code = 200
	call_resp_ok.json = MagicMock(return_value={"message": "ok"})
	call_resp_ok.raise_for_status = MagicMock()

	with patch("pos_next.sync.auth.requests.post") as mock_post:
		mock_post.side_effect = [login_resp, call_resp_401, login_resp_2, call_resp_ok]
		session = SyncSession(
			central_url="https://central.test",
			username="sync@test.com",
			password="pw",
		)
		session.login()
		result = session.post("/api/method/something", data={"x": 1})
		assert result.status_code == 200
		assert session._sid == "sid-2"
	print("PASS: test_session_auto_relogin_on_401")


def run_all():
	test_session_login_caches_sid()
	test_session_login_failure_raises()
	test_session_auto_relogin_on_401()
	print("\nAll Auth tests PASSED")
