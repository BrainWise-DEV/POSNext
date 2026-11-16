"""Integration registry for optional POS Next extension apps."""

from __future__ import annotations

import frappe


def get_loyalty_provider():
	for method_path in frappe.get_hooks("pos_next_loyalty_provider") or []:
		try:
			provider = frappe.get_attr(method_path)()
			if provider:
				return provider
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Loyalty provider hook failed: {method_path}")
	return None


def is_external_loyalty_available():
	provider = get_loyalty_provider()
	if not provider:
		return False
	is_available = provider.get("is_available")
	return bool(is_available()) if is_available else False


def is_external_loyalty_mode(pos_profile):
	provider = get_loyalty_provider()
	if not provider:
		return False
	is_loyalty_mode = provider.get("is_loyalty_mode")
	return bool(is_loyalty_mode(pos_profile)) if is_loyalty_mode else False


def get_external_loyalty_balance(customer):
	provider = get_loyalty_provider()
	if not provider:
		return None
	get_balance = provider.get("get_balance")
	return get_balance(customer) if get_balance else None


def extend_bootstrap_settings(settings, pos_profile=None):
	for method_path in frappe.get_hooks("pos_next_bootstrap_settings") or []:
		try:
			frappe.get_attr(method_path)(settings, pos_profile)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Bootstrap settings hook failed: {method_path}")


def validate_customer_create(**kwargs):
	for method_path in frappe.get_hooks("pos_next_customer_validators") or []:
		frappe.get_attr(method_path)(**kwargs)


def prepare_customer_doc(customer, **kwargs):
	sync_external_customer = False
	for method_path in frappe.get_hooks("pos_next_customer_prepare") or []:
		result = frappe.get_attr(method_path)(customer, **kwargs)
		if result:
			sync_external_customer = True
	return sync_external_customer


class ExternalCustomerRejected(frappe.ValidationError):
	"""Raised by an after-insert hook when the external system refused the customer.

	It propagates out of ``create_customer`` so the request rolls back and the
	cashier sees the external system's message, instead of keeping a customer
	that is "saved but not synced".
	"""


class ExistingCustomerFound(ExternalCustomerRejected):
	"""The email or phone already belongs to an existing customer; do not create a new one."""

	def __init__(self, message, existing_customer=None, magento_id=None):
		super().__init__(message)
		self.existing_customer = existing_customer
		self.magento_id = magento_id


def resolve_existing_customer(**kwargs):
	"""Ask integrations for an existing customer to use instead of inserting a new one.

	A hook returns ``{"message": str, "existing_customer": dict}`` or ``None``.
	"""
	for method_path in frappe.get_hooks("pos_next_customer_resolve_existing") or []:
		result = frappe.get_attr(method_path)(**kwargs)
		if result:
			return result
	return None


def after_customer_insert(customer, **kwargs):
	# Best-effort for unexpected errors (e.g. external system unreachable): the
	# customer stays. An explicit ExternalCustomerRejected fails the create.
	for method_path in frappe.get_hooks("pos_next_customer_after_insert") or []:
		try:
			frappe.get_attr(method_path)(customer, **kwargs)
		except ExternalCustomerRejected:
			raise
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Customer after_insert hook failed: {method_path}",
			)


def after_customer_update(customer, **kwargs):
	"""Let integrations sync an existing POS customer (e.g. Magento).

	ExternalCustomerRejected fails the update so the cashier sees the real
	message and the local change is rolled back. Other errors are logged and
	exposed via get_customer_sync_error.
	"""
	for method_path in frappe.get_hooks("pos_next_customer_after_update") or []:
		try:
			frappe.get_attr(method_path)(customer, **kwargs)
		except ExternalCustomerRejected:
			raise
		except Exception as exc:
			frappe.log_error(
				frappe.get_traceback(),
				f"Customer after_update hook failed: {method_path}",
			)
			record_customer_sync_error(customer.name if customer else None, exc)


# ---------------------------------------------------------------------------
# External customer registration errors
# ---------------------------------------------------------------------------
# An integration (e.g. magento_integration) records why it could not register a
# POS customer externally — typically "email already registered with a different
# mobile number". POS Next shows that message to the cashier instead of a vague
# "not synced yet" (customer create toast + email OTP).

_SYNC_ERROR_KEY = "pos_next:customer_sync_error:{0}"
_SYNC_ERROR_TTL = 30 * 24 * 3600


def record_customer_sync_error(customer, message):
	if not customer:
		return
	text = (str(message or "")).strip()[:500]
	if not text:
		clear_customer_sync_error(customer)
		return
	frappe.cache().set_value(_SYNC_ERROR_KEY.format(customer), text, expires_in_sec=_SYNC_ERROR_TTL)


def clear_customer_sync_error(customer):
	if customer:
		frappe.cache().delete_value(_SYNC_ERROR_KEY.format(customer))


def get_customer_sync_error(customer):
	if not customer:
		return None
	return frappe.cache().get_value(_SYNC_ERROR_KEY.format(customer)) or None
