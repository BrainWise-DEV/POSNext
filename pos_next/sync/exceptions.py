# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync engine exception hierarchy."""


class SyncError(Exception):
	"""Base class for all sync engine errors."""
	pass


class SyncAuthError(SyncError):
	"""Authentication against central failed (bad credentials, expired session)."""
	pass


class SyncTransportError(SyncError):
	"""HTTP/network-level failure talking to central."""
	pass


class SyncConflictError(SyncError):
	"""A conflict was detected and resolution is deferred to human review."""
	pass


class SyncValidationError(SyncError):
	"""Incoming payload failed adapter.validate_incoming()."""
	pass


class SyncReplayRejected(SyncError):
	"""Payload rejected because created_at is older than the replay window."""
	pass
