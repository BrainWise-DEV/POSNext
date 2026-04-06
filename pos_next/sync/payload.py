# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Payload serialization, hashing, and meta-stripping helpers."""

import hashlib
import json


# Fields we strip before hashing (they change on every save, aren't semantic)
META_FIELDS = {
	"modified",
	"modified_by",
	"owner",
	"creation",
	"idx",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
}


def strip_meta(payload):
	"""Return a copy of payload with server-side meta fields removed."""
	return {k: v for k, v in payload.items() if k not in META_FIELDS}


def compute_hash(payload):
	"""
	Return SHA256 hex of a canonical JSON serialization of the payload,
	excluding meta fields. Key order does not affect the hash.
	"""
	clean = strip_meta(payload)
	canonical = json.dumps(clean, sort_keys=True, default=str, ensure_ascii=True)
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_payload(doc):
	"""
	Convert a Frappe Document to a sync payload dict.
	Includes children via Frappe's as_dict(); caller strips meta as needed.
	"""
	if hasattr(doc, "as_dict"):
		return doc.as_dict(convert_dates_to_str=True)
	return dict(doc)
