"""Test cross-bench connectivity: branch (dev.pos) → central (pos-central)."""

from pos_next.sync.auth import SyncSession


def test_login_to_central():
	"""Branch logs into central via SyncSession and makes an authenticated API call."""
	session = SyncSession(
		central_url="http://localhost:8000",
		username="Administrator",
		password="admin",
	)
	try:
		session.login()
		print(f"LOGIN OK — sid={session._sid[:20]}...")

		# Authenticated GET to central
		resp = session.get(
			"/api/method/frappe.client.get_count",
			params={"doctype": "Sync Site Config"},
		)
		print(f"GET response: status={resp.status_code}, body={resp.json()}")
		assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

		data = resp.json()
		assert "message" in data, f"Expected 'message' key, got: {data}"
		print(f"Central has {data['message']} Sync Site Config row(s)")

		print("PASS: test_login_to_central")
	finally:
		session.logout()
		print("LOGOUT OK")


def test_transport_from_config():
	"""Build session from Sync Site Config and verify it works."""
	from pos_next.sync.transport import build_session_from_config

	session = build_session_from_config()
	try:
		session.login()
		print(f"LOGIN via config OK — central_url={session.central_url}")

		resp = session.get(
			"/api/method/frappe.client.get_count",
			params={"doctype": "Item"},
		)
		assert resp.status_code == 200
		print(f"Central has {resp.json().get('message', '?')} Item(s)")

		print("PASS: test_transport_from_config")
	finally:
		session.logout()


def run_all():
	test_login_to_central()
	test_transport_from_config()
	print("\nAll Cross-Bench tests PASSED")
