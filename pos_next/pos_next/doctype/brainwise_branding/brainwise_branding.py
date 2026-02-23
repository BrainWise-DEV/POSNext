# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import ClassVar

import frappe
from frappe.model.document import Document

# MASTER KEY HASH - Only the person with the original key can disable branding
# This hash was created from: secrets.token_urlsafe(32)
# The original key must be kept secret - it is NOT stored anywhere in the code
MASTER_KEY_HASH = "a19686b133d17d0b528355ae39692a0792780a55b50707dc1a58a0e59083830d"

# Secondary protection - requires both master key AND this phrase
PROTECTION_PHRASE_HASH = "3ddb5c12a034095ff81a85bbd06623a60e81252c296b747cf9c127dc57e013a8"


class BrainWiseBranding(Document):
	# Protected fields that require master key to modify
	PROTECTED_FIELDS: ClassVar[list[str]] = [
		"enabled",
		"brand_text",
		"brand_name",
		"brand_url",
		"check_interval",
	]

	def validate(self):
		"""Validate before saving - enforce master key requirement"""
		if not self.is_new():
			# Check if any protected field has been modified
			protected_fields_changed = self._check_protected_fields_changed()

			if protected_fields_changed:
				# Master key is required for any protected field change
				if not self.master_key_provided or not self._validate_master_key():
					changed_fields = ", ".join(protected_fields_changed)
					frappe.throw(
						f"Cannot modify protected fields ({changed_fields}) without the Master Key. "
						"Provide the Master Key to make changes to branding configuration.",
						frappe.PermissionError,
					)

				# Log successful modification with master key
				frappe.log_error(
					title="BrainWise Branding - Fields Modified with Master Key",
					message=json.dumps(
						{
							"user": frappe.session.user,
							"timestamp": frappe.utils.now(),
							"ip_address": frappe.local.request_ip
							if hasattr(frappe.local, "request_ip")
							else None,
							"action": "Protected fields modified with valid master key",
							"fields_changed": protected_fields_changed,
							"old_values": {
								field: self.get_db_value(field) for field in protected_fields_changed
							},
							"new_values": {field: self.get(field) for field in protected_fields_changed},
						},
						indent=2,
						default=str,
					),
				)

		# Special handling for disabling
		if not self.enabled and not self.is_new():
			if not self.master_key_provided or not self._validate_master_key():
				frappe.throw(
					"Branding cannot be disabled without the Master Key. "
					"Contact BrainWise support if you need to disable branding.",
					frappe.PermissionError,
				)

	def _check_protected_fields_changed(self):
		"""Check if any protected fields have been modified"""
		if self.is_new():
			return []

		changed_fields = []
		for field in self.PROTECTED_FIELDS:
			old_value = self.get_db_value(field)
			new_value = self.get(field)

			# Compare values (handle different types)
			if old_value != new_value:
				changed_fields.append(field)

		return changed_fields

	def before_save(self):
		"""Generate encrypted signature and enforce protections"""
		# Always enforce enabled state unless master key provided
		if not self.enabled and not self._validate_master_key():
			self.enabled = 1

		# Generate signature
		self.generate_signature()

		# Clear master key input after validation (never store it)
		if self.master_key_provided:
			self.master_key_provided = None

	def _validate_master_key(self):
		"""Internal method to validate master key"""
		if not self.master_key_provided:
			return False

		try:
			# Parse the master key input (expecting JSON with key and phrase)
			try:
				key_data = json.loads(self.master_key_provided)
				master_key = key_data.get("key", "")
				protection_phrase = key_data.get("phrase", "")
			except (ValueError, json.JSONDecodeError):
				# If not JSON, treat as plain key
				master_key = self.master_key_provided
				protection_phrase = ""

			# Hash the provided master key
			key_hash = hashlib.sha256(master_key.encode()).hexdigest()
			phrase_hash = hashlib.sha256(protection_phrase.encode()).hexdigest()

			# Check if both match
			if key_hash == MASTER_KEY_HASH and phrase_hash == PROTECTION_PHRASE_HASH:
				# Log successful master key usage
				frappe.log_error(
					title="BrainWise Branding - Master Key Used",
					message=json.dumps(
						{
							"user": frappe.session.user,
							"timestamp": frappe.utils.now(),
							"ip_address": frappe.local.request_ip
							if hasattr(frappe.local, "request_ip")
							else None,
							"action": "Master key validated successfully",
							"enabled_state": self.enabled,
						},
						indent=2,
					),
				)
				return True

			# Log failed attempt
			frappe.log_error(
				title="BrainWise Branding - Invalid Master Key Attempt",
				message=json.dumps(
					{
						"user": frappe.session.user,
						"timestamp": frappe.utils.now(),
						"ip_address": frappe.local.request_ip
						if hasattr(frappe.local, "request_ip")
						else None,
						"action": "Invalid master key provided",
					},
					indent=2,
				),
			)
			return False

		except Exception as e:
			frappe.log_error(f"Master key validation error: {e!s}", "BrainWise Branding")
			return False

	def generate_signature(self):
		"""Generate an encrypted signature for branding validation"""
		# Create a signature from branding data
		data = {
			"brand_text": self.brand_text,
			"brand_name": self.brand_name,
			"brand_url": self.brand_url,
			"check_interval": self.check_interval,
			"timestamp": frappe.utils.now(),
			"enabled": self.enabled,
		}

		# Get or create encryption key
		if not self.encryption_key:
			self.encryption_key = secrets.token_urlsafe(32)

		# Create HMAC signature
		message = json.dumps(data, sort_keys=True)
		signature = hmac.new(self.encryption_key.encode(), message.encode(), hashlib.sha256).hexdigest()

		# Encode and store
		self.encrypted_signature = base64.b64encode(
			json.dumps({"signature": signature, "data": data}).encode()
		).decode()

	def validate_signature(self, client_data):
		"""Validate client-side data against server signature"""
		if not self.encrypted_signature:
			return False

		try:
			# Decode stored signature
			json.loads(base64.b64decode(self.encrypted_signature))

			# Check if branding data matches
			if (
				client_data.get("brand_name") != self.brand_name
				or client_data.get("brand_url") != self.brand_url
			):
				return False

			return True
		except Exception as e:
			frappe.log_error(f"Branding validation error: {e!s}", "BrainWise Branding")
			return False

	def log_tampering(self, details):
		"""Log tampering attempts"""
		if not self.log_tampering_attempts:
			return

		# Increment counter
		self.tampering_attempts = (self.tampering_attempts or 0) + 1
		self.last_validation = datetime.now()
		self.save(ignore_permissions=True)

		# Create error log
		frappe.log_error(
			title="BrainWise Branding Tampering Detected", message=json.dumps(details, indent=2, default=str)
		)


@frappe.whitelist(allow_guest=False)
def get_branding_config():
	"""API endpoint to get branding configuration"""
	try:
		doc = frappe.get_single("BrainWise Branding")

		# Branding is ALWAYS active unless disabled with master key
		if not doc.enabled:
			# Double check - if disabled without proper key, re-enable
			doc.enabled = 1
			doc.save(ignore_permissions=True)

		# Return obfuscated configuration
		config = {
			"_t": base64.b64encode(doc.brand_text.encode()).decode(),
			"_l": base64.b64encode(doc.brand_name.encode()).decode(),
			"_u": base64.b64encode(doc.brand_url.encode()).decode(),
			"_i": doc.check_interval or 10000,
			"_sig": doc.encrypted_signature,
			"_ts": frappe.utils.now(),
			"_v": doc.enable_server_validation,
			"_e": 1,  # Always enabled
		}

		return config
	except Exception as e:
		frappe.log_error(f"Error fetching branding config: {e!s}", "BrainWise Branding")
		# Return default config even on error
		return {
			"_t": base64.b64encode(b"Powered by").decode(),
			"_l": base64.b64encode(b"BrainWise").decode(),
			"_u": base64.b64encode(b"https://nexus.brainwise.me").decode(),
			"_i": 10000,
			"_v": True,
			"_e": 1,
		}


@frappe.whitelist(allow_guest=False)
def validate_branding(client_signature=None, brand_name=None, brand_url=None):
	"""Validate branding integrity from client"""
	try:
		doc = frappe.get_single("BrainWise Branding")

		# Force enable if disabled
		if not doc.enabled:
			doc.enabled = 1
			doc.save(ignore_permissions=True)

		if not doc.enable_server_validation:
			return {"valid": True, "enabled": True}

		client_data = {"brand_name": brand_name, "brand_url": brand_url}

		is_valid = doc.validate_signature(client_data)

		if not is_valid:
			# Log tampering attempt
			doc.log_tampering(
				{
					"user": frappe.session.user,
					"timestamp": frappe.utils.now(),
					"client_signature": client_signature,
					"client_data": client_data,
					"ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
				}
			)

		# Update last validation time
		doc.last_validation = datetime.now()
		doc.save(ignore_permissions=True)

		return {"valid": is_valid, "enabled": True, "timestamp": frappe.utils.now()}
	except Exception as e:
		frappe.log_error(f"Error validating branding: {e!s}", "BrainWise Branding")
		return {"valid": False, "enabled": True, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def log_client_event(event_type=None, details=None):
	"""Log client-side events (clicks, removals, modifications)"""
	try:
		doc = frappe.get_single("BrainWise Branding")

		if not doc.log_tampering_attempts:
			return {"logged": False}

		# Parse details if string
		if isinstance(details, str):
			try:
				details = json.loads(details)
			except (ValueError, json.JSONDecodeError):
				pass

		# Log different event types
		if event_type in ["removal", "modification", "hide", "integrity_fail", "visibility_change"]:
			doc.log_tampering(
				{
					"event_type": event_type,
					"user": frappe.session.user,
					"timestamp": frappe.utils.now(),
					"details": details,
					"ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
				}
			)

		return {"logged": True}
	except Exception as e:
		frappe.log_error(f"Error logging client event: {e!s}", "BrainWise Branding")
		return {"logged": False, "error": str(e)}


@frappe.whitelist()
def verify_master_key(master_key_input):
	"""
	API endpoint to verify master key
	This allows System Managers to test if they have the correct key
	Returns True/False without making any changes
	"""
	# Only System Managers can check
	if "System Manager" not in frappe.get_roles():
		frappe.throw("Only System Managers can verify the master key", frappe.PermissionError)

	try:
		# Parse the master key input
		try:
			key_data = json.loads(master_key_input)
			master_key = key_data.get("key", "")
			protection_phrase = key_data.get("phrase", "")
		except (ValueError, json.JSONDecodeError):
			master_key = master_key_input
			protection_phrase = ""

		# Hash and compare
		key_hash = hashlib.sha256(master_key.encode()).hexdigest()
		phrase_hash = hashlib.sha256(protection_phrase.encode()).hexdigest()

		is_valid = key_hash == MASTER_KEY_HASH and phrase_hash == PROTECTION_PHRASE_HASH

		# Log the verification attempt
		frappe.log_error(
			title=f"BrainWise Branding - Master Key Verification {'Success' if is_valid else 'Failed'}",
			message=json.dumps(
				{
					"user": frappe.session.user,
					"timestamp": frappe.utils.now(),
					"result": "valid" if is_valid else "invalid",
					"ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
				},
				indent=2,
			),
		)

		return {
			"valid": is_valid,
			"message": "Master key is valid!" if is_valid else "Invalid master key or protection phrase",
		}

	except Exception as e:
		frappe.log_error(f"Master key verification error: {e!s}", "BrainWise Branding")
		return {"valid": False, "error": str(e)}


@frappe.whitelist()
def generate_new_master_key():
	"""
	Generate a new master key pair (for initial setup only)
	Only accessible by System Manager
	WARNING: This should only be used during initial setup!
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw("Only System Managers can generate master keys", frappe.PermissionError)

	# Generate new random key and phrase
	new_key = secrets.token_urlsafe(32)
	new_phrase = secrets.token_urlsafe(24)

	# Generate hashes
	key_hash = hashlib.sha256(new_key.encode()).hexdigest()
	phrase_hash = hashlib.sha256(new_phrase.encode()).hexdigest()

	# Log this generation
	frappe.log_error(
		title="BrainWise Branding - New Master Key Generated",
		message=json.dumps(
			{
				"user": frappe.session.user,
				"timestamp": frappe.utils.now(),
				"warning": "New master key generated - previous key is now invalid",
				"ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
			},
			indent=2,
		),
	)

	return {
		"master_key": new_key,
		"protection_phrase": new_phrase,
		"key_hash": key_hash,
		"phrase_hash": phrase_hash,
		"instructions": "IMPORTANT: Save these securely! Update MASTER_KEY_HASH and PROTECTION_PHRASE_HASH in brainwise_branding.py with the hashes provided above.",
	}
