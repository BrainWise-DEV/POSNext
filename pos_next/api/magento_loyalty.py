# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
Magento loyalty orchestration for POS Next.

Triggers masar_miraaya APIs on invoice submit and after payment redemption.
"""

import frappe
from frappe import _
from frappe.utils import flt

from pos_next.api.wallet import get_wallet_amount_from_payments
from pos_next.services.miraaya_loyalty import (
	add_lp_points,
	get_lp_balance,
	is_magento_loyalty_mode,
	is_miraaya_loyalty_available,
	redeem_lp_points,
)


def _has_field(doctype: str, fieldname: str) -> bool:
	return frappe.get_meta(doctype).has_field(fieldname)


@frappe.whitelist()
def get_lp_balance_for_customer(customer, pos_profile=None):
	"""Return Magento LP balance for POS UI (customer selected / cart header)."""
	if not customer or not is_miraaya_loyalty_available():
		return {"wallet_enabled": False, "balance_points": 0, "balance_iqd": 0}

	if pos_profile and not is_magento_loyalty_mode(pos_profile):
		return {"wallet_enabled": False, "balance_points": 0, "balance_iqd": 0}

	try:
		balance = get_lp_balance(customer)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Magento LP Balance Fetch Error")
		return {
			"wallet_enabled": True,
			"balance_points": 0,
			"balance_iqd": 0,
			"error": True,
		}

	return {
		"wallet_enabled": True,
		"balance_points": balance.get("balance_points", 0),
		"balance_iqd": balance.get("balance_iqd", 0),
		"magento_loyalty": True,
	}


def add_magento_lp_on_submit(doc, method=None):
	"""Earn Magento LP after a POS invoice is submitted."""
	if not doc.is_pos or doc.is_return or not doc.customer:
		return

	if not is_magento_loyalty_mode(doc.pos_profile):
		return

	value_iqd = abs(flt(doc.grand_total))
	if value_iqd <= 0:
		return

	if _has_field("Sales Invoice", "custom_lp_add_transaction_id"):
		if frappe.db.get_value("Sales Invoice", doc.name, "custom_lp_add_transaction_id"):
			return

	try:
		result = add_lp_points(doc.customer, value_iqd)
	except Exception as exc:
		frappe.log_error(
			title="Magento LP Add Points Error",
			message=f"Invoice: {doc.name}, Error: {exc!s}\n{frappe.get_traceback()}",
		)
		return

	updates = {}
	if _has_field("Sales Invoice", "custom_lp_add_transaction_id"):
		updates["custom_lp_add_transaction_id"] = result.get("transaction_id")
	if _has_field("Sales Invoice", "custom_lp_points_added"):
		updates["custom_lp_points_added"] = result.get("points_added")
	if _has_field("Sales Invoice", "custom_lp_value_iqd"):
		updates["custom_lp_value_iqd"] = result.get("value_iqd") or value_iqd

	if updates:
		frappe.db.set_value("Sales Invoice", doc.name, updates, update_modified=False)


def redeem_magento_lp_after_submit(invoice_doc):
	"""Redeem Magento LP after invoice submit when wallet payment was used."""
	if not invoice_doc.is_pos or invoice_doc.is_return or not invoice_doc.customer:
		return

	if not is_magento_loyalty_mode(invoice_doc.pos_profile):
		return

	wallet_amount = get_wallet_amount_from_payments(invoice_doc.payments)
	if wallet_amount <= 0:
		return

	if _has_field("Sales Invoice", "custom_lp_redeem_transaction_id"):
		if frappe.db.get_value("Sales Invoice", invoice_doc.name, "custom_lp_redeem_transaction_id"):
			return

	try:
		result = redeem_lp_points(invoice_doc.customer, wallet_amount)
	except Exception as exc:
		frappe.log_error(
			title="Magento LP Redeem Error",
			message=f"Invoice: {invoice_doc.name}, Error: {exc!s}\n{frappe.get_traceback()}",
		)
		frappe.msgprint(
			_("Invoice submitted successfully but loyalty redemption failed. Please contact administrator."),
			alert=True,
			indicator="orange",
		)
		return

	if _has_field("Sales Invoice", "custom_lp_redeem_transaction_id") and result.get("transaction_id"):
		frappe.db.set_value(
			"Sales Invoice",
			invoice_doc.name,
			"custom_lp_redeem_transaction_id",
			result.get("transaction_id"),
			update_modified=False,
		)
