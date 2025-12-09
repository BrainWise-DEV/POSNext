# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import hashlib
import hmac
import json
import base64
from datetime import datetime
import secrets
from pos_next.config.security import MASTER_KEY_HASH, PROTECTION_PHRASE_HASH

class BrainWiseBranding(Document):
    """
    Manages branding configuration for the POS system.
    Includes security mechanisms to prevent unauthorized tampering or disabling.
    """

    # Protected fields that require master key to modify
    PROTECTED_FIELDS = ['enabled', 'brand_text', 'brand_name', 'brand_url', 'check_interval']

    def validate(self):
        """
        Validate before saving - enforce master key requirement.
        Ensures that protected fields cannot be changed without proper authorization.
        """
        self._verify_protected_field_permissions()
        self._enforce_disable_protection()

    def _verify_protected_field_permissions(self):
        """Check if any protected fields are modified and verify master key if so."""
        if not self.is_new():
            protected_fields_changed = self._check_protected_fields_changed()

            if protected_fields_changed:
                if not self.master_key_provided or not self._validate_master_key():
                    changed_fields = ', '.join(protected_fields_changed)
                    frappe.throw(
                        f"Cannot modify protected fields ({changed_fields}) without the Master Key.",
                        frappe.PermissionError
                    )

                self._log_master_key_usage(protected_fields_changed)

    def _enforce_disable_protection(self):
        """Prevent disabling the branding without the Master Key."""
        if not self.enabled and not self.is_new():
            if not self.master_key_provided or not self._validate_master_key():
                frappe.throw(
                    "Branding cannot be disabled without the Master Key.",
                    frappe.PermissionError
                )

    def _log_master_key_usage(self, protected_fields_changed):
        """Log successful use of the master key for audit purposes."""
        frappe.log_error(
            title="BrainWise Branding - Fields Modified with Master Key",
            message=json.dumps({
                "user": frappe.session.user,
                "timestamp": frappe.utils.now(),
                "fields_changed": protected_fields_changed,
                # Use db_get to retrieve the actual value from the database
                "old_values": {field: self.db_get(field) for field in protected_fields_changed},
                "new_values": {field: self.get(field) for field in protected_fields_changed}
            }, indent=2, default=str)
        )

    def _check_protected_fields_changed(self):
        """
        Identify which protected fields have been modified in this transaction.
        Returns a list of changed field names.
        """
        if self.is_new():
            return []

        changed_fields = []
        for field in self.PROTECTED_FIELDS:
            old_value = self.db_get(field)
            new_value = self.get(field)
            if old_value != new_value:
                changed_fields.append(field)

        return changed_fields

    def before_save(self):
        """
        Generate encrypted signature and enforce protections before committing to DB.
        """
        # If disabled without key (via script or direct manipulation), force re-enable
        if not self.enabled and not self._validate_master_key():
            self.enabled = 1

        # Regenerate the security signature for the current configuration
        self.generate_signature()

        # Clear master key input from memory to prevent accidental storage
        if self.master_key_provided:
            self.master_key_provided = None

    def _validate_master_key(self):
        """
        Internal method to validate the provided master key against the stored hash.
        Supports both JSON object (key + phrase) and raw key string.
        """
        if not self.master_key_provided:
            return False

        try:
            master_key, protection_phrase = self._parse_master_key()

            # Use SHA256 to verify against stored hashes
            key_hash = hashlib.sha256(master_key.encode()).hexdigest()
            phrase_hash = hashlib.sha256(protection_phrase.encode()).hexdigest()

            is_valid = (key_hash == MASTER_KEY_HASH and phrase_hash == PROTECTION_PHRASE_HASH)

            self._log_key_attempt(is_valid)
            return is_valid

        except Exception as e:
            frappe.log_error(f"Master key validation error: {str(e)}", "BrainWise Branding")
            return False

    def _parse_master_key(self):
        """Parse the master_key_provided field, handling JSON or string formats."""
        try:
            key_data = json.loads(self.master_key_provided)
            return key_data.get("key", ""), key_data.get("phrase", "")
        except:
            return self.master_key_provided, ""

    def _log_key_attempt(self, success):
        """Log validation attempts (success or failure)."""
        action = "Master key validated successfully" if success else "Invalid master key provided"
        frappe.log_error(
            title=f"BrainWise Branding - Master Key {success and 'Used' or 'Attempt'}",
            message=json.dumps({
                "user": frappe.session.user,
                "timestamp": frappe.utils.now(),
                "action": action
            }, indent=2)
        )

    def generate_signature(self):
        """
        Generate an HMAC-SHA256 signature for the current branding configuration.
        This signature is sent to the client to verify that the config hasn't been tampered with.
        """
        data = {
            "brand_text": self.brand_text,
            "brand_name": self.brand_name,
            "brand_url": self.brand_url,
            "check_interval": self.check_interval,
            "timestamp": frappe.utils.now(),
            "enabled": self.enabled
        }

        # Generate a new random key if one doesn't exist
        if not self.encryption_key:
            self.encryption_key = secrets.token_urlsafe(32)

        # Create the HMAC signature
        message = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.encryption_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Store encoded payload
        self.encrypted_signature = base64.b64encode(
            json.dumps({"signature": signature, "data": data}).encode()
        ).decode()

    def validate_signature(self, client_data):
        """
        Validate client-side data against server signature.
        Recalculates the HMAC to ensure the data is authentic and hasn't been replayed or modified.
        """
        if not self.encrypted_signature:
            return False

        try:
            stored = json.loads(base64.b64decode(self.encrypted_signature))

            # Security: Recalculate signature to verify integrity
            # This prevents attackers from replaying an old valid signature with modified data
            stored_data = stored.get("data", {})
            message = json.dumps(stored_data, sort_keys=True)
            recalc_signature = hmac.new(
                self.encryption_key.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()

            if recalc_signature != stored.get("signature"):
                return False

            # Verify that the client sees what the server has configured
            if (client_data.get("brand_name") != self.brand_name or
                client_data.get("brand_url") != self.brand_url):
                return False

            return True
        except Exception as e:
            frappe.log_error(f"Branding validation error: {str(e)}", "BrainWise Branding")
            return False

    def log_tampering(self, details):
        """
        Log tampering attempts to the database.
        Uses atomic updates to avoid race conditions or recursive save loops.
        """
        if not self.log_tampering_attempts:
            return

        # Avoid recursive save loop - use db_set to update directly
        self.db_set("tampering_attempts", (self.tampering_attempts or 0) + 1)
        self.db_set("last_validation", datetime.now())

        frappe.log_error(
            title="BrainWise Branding Tampering Detected",
            message=json.dumps(details, indent=2, default=str)
        )

# ==============================================================================
# Backward Compatibility Shims
# ==============================================================================
# The API endpoints have been moved to `pos_next.api.branding`.
# These shims ensure that any external code or old frontend versions calling
# these paths will still work by forwarding the call to the new location.

@frappe.whitelist(allow_guest=False)
def get_branding_config():
    from pos_next.api.branding import get_branding_config as _get_config
    return _get_config()

@frappe.whitelist(allow_guest=False)
def validate_branding(client_signature=None, brand_name=None, brand_url=None):
    from pos_next.api.branding import validate_branding as _validate
    return _validate(client_signature, brand_name, brand_url)

@frappe.whitelist(allow_guest=False)
def log_client_event(event_type=None, details=None):
    from pos_next.api.branding import log_client_event as _log_event
    return _log_event(event_type, details)

@frappe.whitelist()
def verify_master_key(master_key_input):
    from pos_next.api.branding import verify_master_key as _verify
    return _verify(master_key_input)

@frappe.whitelist()
def generate_new_master_key():
    from pos_next.api.branding import generate_new_master_key as _gen
    return _gen()
