"""Built-in Frappe email OTP provider. send/verify are implemented in a later task."""

from types import SimpleNamespace

from pos_next.integrations.otp import OTP_PROVIDER_API


def _not_configured(*_args):
	return {"ok": False, "code": "not_configured", "message": ""}


def _health():
	return {"ok": True, "message": "", "fix_url": None}


def get_provider():
	return SimpleNamespace(
		name="frappe_email",
		label="Frappe Email",
		api=OTP_PROVIDER_API,
		requires_phone=False,
		health=_health,
		send=_not_configured,
		verify=_not_configured,
	)
