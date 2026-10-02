# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
QZ Tray Signing API

Provides server-side certificate and message signing for QZ Tray silent printing.
The private key never leaves the server — the browser requests signatures on demand.

Setup:
  1. Call `setup_qz_certificate` (System Manager only) to generate a self-signed
     cert + private key pair under {site}/private/qz/.
  2. Download the certificate from POS Settings and import it into QZ Tray
     on each POS machine, then restart QZ Tray.
  3. The frontend calls `get_certificate` once on connect and `sign_message`
     on every QZ Tray operation — no user interaction required.
"""

import base64
import os

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _qz_dir():
	return frappe.get_site_path("private", "qz")


def _cert_path():
	return os.path.join(_qz_dir(), "digital-certificate.crt")


def _key_path():
	return os.path.join(_qz_dir(), "private-key.pem")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_certificate():
	"""Return the public certificate PEM text for QZ Tray signing."""
	path = _cert_path()
	if not os.path.exists(path):
		frappe.throw(
			_("QZ Tray certificate not found. Ask an administrator to run Setup QZ Certificate."),
			title=_("QZ Certificate Missing"),
		)

	with open(path, "r") as f:
		return f.read()


@frappe.whitelist()
def get_certificate_download():
	"""Return the certificate PEM and company name for download."""
	path = _cert_path()
	if not os.path.exists(path):
		frappe.throw(
			_("QZ Tray certificate not found. Ask an administrator to run Setup QZ Certificate."),
			title=_("QZ Certificate Missing"),
		)

	with open(path, "r") as f:
		pem = f.read()

	company = frappe.db.get_default("company") or ""
	return {"pem": pem, "company": company}


@frappe.whitelist()
def sign_message(message):
	"""Sign a message with the private key for QZ Tray.

	Args:
		message: The string that QZ Tray sends for signing.

	Returns:
		Base64-encoded RSA-PKCS1v15-SHA512 signature.
	"""
	path = _key_path()
	if not os.path.exists(path):
		frappe.throw(
			_("QZ Tray private key not found. Ask an administrator to run Setup QZ Certificate."),
			title=_("QZ Key Missing"),
		)

	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import padding

	with open(path, "rb") as f:
		private_key = serialization.load_pem_private_key(f.read(), password=None)

	signature = private_key.sign(
		message.encode("utf-8"),
		padding.PKCS1v15(),
		hashes.SHA512(),
	)

	return base64.b64encode(signature).decode("utf-8")


@frappe.whitelist()
def setup_qz_certificate():
	"""Generate a self-signed certificate + private key for QZ Tray signing.

	System Manager only. Skips generation if both files already exist.
	Returns the path to the certificate file so the admin can download
	and import it into QZ Tray on each POS machine.
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only System Managers can set up QZ certificates."), frappe.PermissionError)

	cert_path = _cert_path()
	key_path = _key_path()

	if os.path.exists(cert_path) and os.path.exists(key_path):
		return {
			"status": "exists",
			"message": _("QZ certificate already exists."),
			"cert_path": cert_path,
		}

	# Create directory
	qz_dir = _qz_dir()
	os.makedirs(qz_dir, exist_ok=True)

	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.x509.oid import NameOID
	from datetime import datetime, timedelta, timezone

	# Generate 2048-bit RSA key
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

	# Write private key
	with open(key_path, "wb") as f:
		f.write(key.private_bytes(
			encoding=serialization.Encoding.PEM,
			format=serialization.PrivateFormat.PKCS8,
			encryption_algorithm=serialization.NoEncryption(),
		))
	os.chmod(key_path, 0o600)

	# Build self-signed certificate (valid ~31 years)
	subject = issuer = x509.Name([
		x509.NameAttribute(NameOID.COMMON_NAME, "POS Next QZ Tray Signing"),
		x509.NameAttribute(NameOID.ORGANIZATION_NAME, frappe.db.get_default("company") or "POS Next"),
	])

	now = datetime.now(timezone.utc)
	cert = (
		x509.CertificateBuilder()
		.subject_name(subject)
		.issuer_name(issuer)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now)
		.not_valid_after(now + timedelta(days=11499))
		.sign(key, hashes.SHA256())
	)

	# Write certificate
	with open(cert_path, "wb") as f:
		f.write(cert.public_bytes(serialization.Encoding.PEM))

	frappe.msgprint(
		_("QZ Tray certificate generated successfully.<br><br>"
		  "Download the certificate from POS Settings and import it into "
		  "QZ Tray on each POS machine, then restart QZ Tray."),
		title=_("QZ Certificate Ready"),
		indicator="green",
	)

	return {
		"status": "created",
		"message": _("QZ certificate generated successfully."),
		"cert_path": cert_path,
	}
