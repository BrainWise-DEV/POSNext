"""Utility helpers shared across the POS Next backend."""

from __future__ import annotations

import json
import time
from pathlib import Path

import frappe
from frappe import _

from pos_next import __version__ as app_version

_BASE_DIR = Path(__file__).resolve().parent
_VERSION_FILE = _BASE_DIR / "public" / "pos" / "version.json"
_MANIFEST_FILE = _BASE_DIR / "public" / "pos" / "manifest.webmanifest"
_FALLBACK_VERSION: str | None = None


def _read_version_file() -> str | None:
	"""
	Read version from version.json file.

	Returns:
		str | None: Version string or None if file doesn't exist or is invalid
	"""
	if not _VERSION_FILE.exists():
		return None
	try:
		data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError, ValueError):
		return None
	version = data.get("version") or data.get("buildVersion")
	return str(version) if version else None


def _manifest_mtime_version() -> str | None:
	"""
	Get version based on manifest file modification time.

	Returns:
		str | None: Version string based on mtime or None if file doesn't exist
	"""
	if not _MANIFEST_FILE.exists():
		return None
	try:
		return str(int(_MANIFEST_FILE.stat().st_mtime))
	except OSError:
		return None


def get_build_version() -> str:
	"""
	Return a string that uniquely identifies the current asset build.

	This function tries multiple strategies to get a unique build version:
	1. Read from version.json (generated during build)
	2. Use manifest.webmanifest modification time
	3. Fall back to app version + timestamp

	Returns:
		str: Unique build version identifier
	"""
	# Try reading from version.json first
	version = _read_version_file()
	if version:
		return version

	# Fall back to manifest modification time
	mtime_version = _manifest_mtime_version()
	if mtime_version:
		return mtime_version

	# Ultimate fallback: app version + timestamp
	global _FALLBACK_VERSION
	if _FALLBACK_VERSION is None:
		_FALLBACK_VERSION = f"{app_version}-{int(time.time())}"
	return _FALLBACK_VERSION


def get_app_version() -> str:
	"""
	Get the application version from __init__.py

	Returns:
		str: Application version
	"""
	return app_version


def validate_pos_profile_access(pos_profile: str, exc: type[Exception] = frappe.ValidationError) -> None:
	"""Ensure the session user may act through this POS Profile.

	The profile name is caller-supplied and decides scoping and limits (allowed
	item groups, OTP limits / provider), so an unvalidated name would let a
	caller pick the least restrictive profile. Users assigned to the profile, or
	who can administer POS Profiles, pass. ``exc`` is the exception class to
	raise.
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"), exc)

	is_assigned = frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": frappe.session.user})
	# Users who can administer POS Profiles are not constrained by them.
	if not is_assigned and not frappe.has_permission("POS Profile", "write"):
		frappe.throw(_("You don't have access to this POS Profile"), exc)


def log_error_without_telemetry(title: str, message: str) -> None:
	"""Write an Error Log row with a fixed ``message`` and never send it to Sentry.

	``frappe.log_error`` also calls ``capture_exception``, whose Sentry scope
	carries the request body (and, inside an ``except`` block, frame locals).
	On OTP and provider paths that body holds the code, so those paths log
	here, outside any ``except`` block, with only an exception class name.
	"""
	doc = frappe.get_doc(doctype="Error Log", method=title, error=message)
	if frappe.flags.read_only:
		doc.deferred_insert()
	else:
		doc.insert(ignore_permissions=True)
