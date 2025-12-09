# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json
import base64
import hashlib
import secrets
from datetime import datetime
from pos_next.config.security import MASTER_KEY_HASH, PROTECTION_PHRASE_HASH

@frappe.whitelist(allow_guest=False)
def get_branding_config():
    """
    API endpoint to fetch the current branding configuration.
    Returns an obfuscated payload containing branding text, logos, and signatures.
    """
    try:
        doc = _fetch_branding_doc()
        return _build_branding_payload(doc)
    except Exception as e:
        frappe.log_error(f"Error fetching branding config: {str(e)}", "BrainWise Branding")
        return get_default_config()

def _fetch_branding_doc():
    """Fetches the singleton branding document."""
    doc = frappe.get_single("BrainWise Branding")
    # Respect the enabled state - do not auto-enable on read
    return doc

def _build_branding_payload(doc):
    """Constructs the obfuscated configuration dictionary for the client."""
    return {
        "_t": base64.b64encode(doc.brand_text.encode()).decode(),
        "_l": base64.b64encode(doc.brand_name.encode()).decode(),
        "_u": base64.b64encode(doc.brand_url.encode()).decode(),
        "_i": doc.check_interval or 10000,
        "_sig": doc.encrypted_signature,
        "_ts": frappe.utils.now(),
        "_v": doc.enable_server_validation,
        "_e": doc.enabled,  # Return actual state (1 or 0)
        "_c": "pos-footer-component", # Legacy component name
        "_s": {"p": "12px 20px"} # Legacy styling
    }

def get_default_config():
    """Return default branding configuration used as fallback."""
    return {
        "_t": base64.b64encode("Powered by".encode()).decode(),
        "_l": base64.b64encode("BrainWise".encode()).decode(),
        "_u": base64.b64encode("https://nexus.brainwise.me".encode()).decode(),
        "_i": 10000,
        "_v": True,
        "_e": 1
    }

@frappe.whitelist(allow_guest=False)
def validate_branding(client_signature=None, brand_name=None, brand_url=None):
    """
    Validate branding integrity from client-side.
    Receives what the client sees and verifies it against the server's signature.
    """
    try:
        doc = frappe.get_single("BrainWise Branding")

        # If branding is disabled by master key, skip validation
        if not doc.enabled:
             return {"valid": True, "enabled": False}

        if not doc.enable_server_validation:
            return {"valid": True, "enabled": True}

        client_data = {
            "brand_name": brand_name,
            "brand_url": brand_url
        }

        # Validate against HMAC
        is_valid = doc.validate_signature(client_data)

        if not is_valid:
            # Log the incident
            doc.log_tampering({
                "user": frappe.session.user,
                "timestamp": frappe.utils.now(),
                "client_signature": client_signature,
                "client_data": client_data,
                "ip_address": frappe.local.request_ip if hasattr(frappe.local, 'request_ip') else None
            })

        # Update last validation time via db_set to avoid heavy write/save overhead
        doc.db_set("last_validation", datetime.now())

        return {
            "valid": is_valid,
            "enabled": True,
            "timestamp": frappe.utils.now()
        }
    except Exception as e:
        frappe.log_error(f"Error validating branding: {str(e)}", "BrainWise Branding")
        return {"valid": False, "enabled": True, "error": str(e)}

@frappe.whitelist(allow_guest=False)
def log_client_event(event_type=None, details=None):
    """
    Log client-side events related to branding visibility or integrity.
    Supported events: removal, modification, hide, integrity_fail, visibility_change.
    """
    try:
        doc = frappe.get_single("BrainWise Branding")

        if not doc.log_tampering_attempts:
            return {"logged": False}

        if isinstance(details, str):
            try:
                details = json.loads(details)
            except:
                pass

        if event_type in ["removal", "modification", "hide", "integrity_fail", "visibility_change"]:
            doc.log_tampering({
                "event_type": event_type,
                "user": frappe.session.user,
                "timestamp": frappe.utils.now(),
                "details": details,
                "ip_address": frappe.local.request_ip if hasattr(frappe.local, 'request_ip') else None
            })

        return {"logged": True}
    except Exception as e:
        frappe.log_error(f"Error logging client event: {str(e)}", "BrainWise Branding")
        return {"logged": False, "error": str(e)}

@frappe.whitelist()
def verify_master_key(master_key_input):
    """
    API endpoint to verify if a provided master key is valid.
    Only accessible by System Managers.
    Does NOT modify state, just returns validation result.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Managers can verify the master key", frappe.PermissionError)

    try:
        try:
            key_data = json.loads(master_key_input)
            master_key = key_data.get("key", "")
            protection_phrase = key_data.get("phrase", "")
        except:
            master_key = master_key_input
            protection_phrase = ""

        key_hash = hashlib.sha256(master_key.encode()).hexdigest()
        phrase_hash = hashlib.sha256(protection_phrase.encode()).hexdigest()

        is_valid = (key_hash == MASTER_KEY_HASH and phrase_hash == PROTECTION_PHRASE_HASH)

        # Audit log for security monitoring
        frappe.log_error(
            title=f"BrainWise Branding - Master Key Verification {'Success' if is_valid else 'Failed'}",
            message=json.dumps({
                "user": frappe.session.user,
                "timestamp": frappe.utils.now(),
                "result": "valid" if is_valid else "invalid"
            }, indent=2)
        )

        return {
            "valid": is_valid,
            "message": "Master key is valid!" if is_valid else "Invalid master key or protection phrase"
        }

    except Exception as e:
        frappe.log_error(f"Master key verification error: {str(e)}", "BrainWise Branding")
        return {"valid": False, "error": str(e)}

@frappe.whitelist()
def generate_new_master_key():
    """
    Generate a new random master key pair.
    Only accessible by System Manager.
    WARNING: This renders the old key invalid once the hashes are updated in config.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Managers can generate master keys", frappe.PermissionError)

    new_key = secrets.token_urlsafe(32)
    new_phrase = secrets.token_urlsafe(24)

    key_hash = hashlib.sha256(new_key.encode()).hexdigest()
    phrase_hash = hashlib.sha256(new_phrase.encode()).hexdigest()

    frappe.log_error(
        title="BrainWise Branding - New Master Key Generated",
        message=json.dumps({
            "user": frappe.session.user,
            "timestamp": frappe.utils.now(),
            "warning": "New master key generated"
        }, indent=2)
    )

    return {
        "master_key": new_key,
        "protection_phrase": new_phrase,
        "key_hash": key_hash,
        "phrase_hash": phrase_hash,
        "instructions": "IMPORTANT: Update MASTER_KEY_HASH and PROTECTION_PHRASE_HASH in pos_next/config/security.py."
    }

@frappe.whitelist(allow_guest=False)
def get_tampering_stats():
    """Get tampering statistics (admin only)"""
    if not frappe.has_permission("BrainWise Branding", "read"):
         frappe.throw("Unauthorized", frappe.PermissionError)

    doc = frappe.get_single("BrainWise Branding")
    return {
        "attempts": doc.tampering_attempts or 0,
        "last_validation": doc.last_validation
    }
