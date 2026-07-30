"""
Miraaya / masar_miraaya Magento loyalty integration for POS Next.

When masar_miraaya is installed on the same site, POS Next delegates loyalty
balance, earn, and redeem to the client's Magento API wrappers.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

logger = logging.getLogger(__name__)

GET_BALANCE_METHOD = "masar_miraaya.api.get_customer_lp_balance"
ADD_POINTS_METHOD = "masar_miraaya.api.add_customer_lp_points"
REDEEM_POINTS_METHOD = "masar_miraaya.api.redeem_customer_lp_points"


@lru_cache(maxsize=1)
def is_miraaya_loyalty_available() -> bool:
	"""Return True when the masar_miraaya app is installed."""
	return "masar_miraaya" in frappe.get_installed_apps()


def is_magento_loyalty_mode(pos_profile: str | None = None) -> bool:
	"""Return True when Magento LP should replace the internal wallet."""
	if not is_miraaya_loyalty_available() or not pos_profile:
		return False

	from pos_next.api.wallet import get_pos_settings

	pos_settings = get_pos_settings(pos_profile)
	return bool(pos_settings and cint(pos_settings.get("enable_loyalty_program")))


def _call_miraaya(method: str, **kwargs) -> dict[str, Any]:
	if not is_miraaya_loyalty_available():
		frappe.throw(_("Magento loyalty integration is not available"))

	try:
		fn = frappe.get_attr(method)
	except Exception as exc:
		logger.exception("Failed to resolve masar_miraaya method %s", method)
		frappe.throw(_("Magento loyalty integration is misconfigured: {0}").format(exc))

	try:
		return fn(**kwargs) or {}
	except frappe.ValidationError:
		raise
	except Exception as exc:
		logger.exception("masar_miraaya call failed: %s", method)
		frappe.throw(_("Magento loyalty request failed: {0}").format(exc))


def get_lp_balance(customer: str) -> dict[str, Any]:
	"""Fetch Magento LP balance for a Frappe Customer."""
	result = _call_miraaya(GET_BALANCE_METHOD, customer=customer)
	return {
		"customer_id": result.get("customer_id"),
		"balance_points": flt(result.get("balance_points")),
		"balance_iqd": flt(result.get("balance_iqd")),
	}


def add_lp_points(customer: str, value_iqd: float) -> dict[str, Any]:
	"""Add loyalty points in Magento after a sale."""
	return _call_miraaya(ADD_POINTS_METHOD, customer=customer, value_iqd=flt(value_iqd))


def redeem_lp_points(customer: str, value_iqd: float) -> dict[str, Any]:
	"""Redeem loyalty points in Magento for a wallet/LP payment."""
	return _call_miraaya(REDEEM_POINTS_METHOD, customer=customer, value_iqd=flt(value_iqd))


def customer_has_magento_id(customer: str) -> bool:
	"""Return True when the customer is linked to Magento."""
	if not frappe.db.has_column("Customer", "custom_customer_id"):
		return False
	return bool(frappe.db.get_value("Customer", customer, "custom_customer_id"))
