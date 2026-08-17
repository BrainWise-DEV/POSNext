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
	publish_to_magento = False
	for method_path in frappe.get_hooks("pos_next_customer_prepare") or []:
		result = frappe.get_attr(method_path)(customer, **kwargs)
		if result:
			publish_to_magento = True
	return publish_to_magento


def after_customer_insert(customer, **kwargs):
	for method_path in frappe.get_hooks("pos_next_customer_after_insert") or []:
		frappe.get_attr(method_path)(customer, **kwargs)
