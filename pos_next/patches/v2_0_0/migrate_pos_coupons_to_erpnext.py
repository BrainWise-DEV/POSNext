# -*- coding: utf-8 -*-
# Copyright (c) 2025, POS Next and contributors
# For license information, please see license.txt

"""
Migration patch: POS Coupon → ERPNext Coupon Code

This patch migrates all POS Coupon gift cards to native ERPNext Coupon Code
with custom fields for gift card tracking. After migration, POS Coupon doctype
is no longer required for gift card functionality.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, add_months, getdate, flt


def execute():
	"""Migrate POS Coupons to ERPNext Coupon Code with Pricing Rules."""

	# Check if POS Coupon table exists
	if not frappe.db.table_exists("POS Coupon"):
		frappe.logger().info("POS Coupon table does not exist, skipping migration")
		return

	# Get all POS Coupons that are gift cards
	pos_coupons = frappe.db.sql("""
		SELECT *
		FROM `tabPOS Coupon`
		WHERE coupon_type = 'Gift Card'
		AND disabled = 0
	""", as_dict=True)

	if not pos_coupons:
		frappe.logger().info("No POS Coupon gift cards found to migrate")
		return

	migrated_count = 0
	skipped_count = 0

	for pos_coupon in pos_coupons:
		try:
			# Check if already migrated (Coupon Code with same code exists)
			existing_coupon = frappe.db.exists(
				"Coupon Code",
				{"coupon_code": pos_coupon.coupon_code}
			)

			if existing_coupon:
				# Update existing coupon with gift card fields if not set
				_update_existing_coupon(existing_coupon, pos_coupon)
				skipped_count += 1
				continue

			# Create new Pricing Rule and Coupon Code
			_create_erpnext_coupon(pos_coupon)
			migrated_count += 1

		except Exception as e:
			frappe.log_error(
				f"Migration failed for {pos_coupon.coupon_code}",
				f"Error migrating POS Coupon {pos_coupon.name}: {str(e)}\n\n{frappe.get_traceback()}"
			)

	frappe.logger().info(
		f"POS Coupon migration complete: {migrated_count} migrated, {skipped_count} already existed"
	)


def _update_existing_coupon(coupon_name: str, pos_coupon: dict):
	"""Update existing Coupon Code with gift card custom fields.

	Args:
		coupon_name: Name of existing Coupon Code
		pos_coupon: Original POS Coupon data
	"""
	# Get current values
	current = frappe.db.get_value(
		"Coupon Code",
		coupon_name,
		["pos_next_gift_card", "gift_card_amount"],
		as_dict=True
	)

	# Only update if not already marked as POS Next gift card
	if current and not current.pos_next_gift_card:
		balance = flt(pos_coupon.gift_card_amount) if pos_coupon.gift_card_amount else flt(pos_coupon.discount_amount)

		frappe.db.set_value(
			"Coupon Code",
			coupon_name,
			{
				"pos_next_gift_card": 1,
				"gift_card_amount": balance,
				"original_gift_card_amount": flt(pos_coupon.original_amount) or balance,
				"source_invoice": pos_coupon.source_invoice,
			},
			update_modified=False
		)


def _create_erpnext_coupon(pos_coupon: dict):
	"""Create ERPNext Coupon Code + Pricing Rule from POS Coupon.

	Args:
		pos_coupon: POS Coupon data to migrate
	"""
	# Determine the balance
	balance = flt(pos_coupon.gift_card_amount) if pos_coupon.gift_card_amount else flt(pos_coupon.discount_amount)
	original_amount = flt(pos_coupon.original_amount) or balance

	# Create Pricing Rule
	pricing_rule_name = f"Gift Card - {pos_coupon.coupon_code}"

	pricing_rule = frappe.get_doc({
		"doctype": "Pricing Rule",
		"title": pricing_rule_name,
		"apply_on": "Transaction",
		"price_or_product_discount": "Price",
		"rate_or_discount": "Discount Amount",
		"discount_amount": balance,
		"selling": 1,
		"buying": 0,
		"applicable_for": "",
		"company": pos_coupon.company,
		"currency": frappe.db.get_default("currency") or "CHF",
		"coupon_code_based": 1,
		"valid_from": pos_coupon.valid_from or getdate(nowdate()),
		"valid_upto": pos_coupon.valid_upto or add_months(getdate(nowdate()), 12),
		"priority": 1,
		"disable": 0,
	})
	pricing_rule.insert(ignore_permissions=True)

	# Create Coupon Code
	coupon_code = frappe.get_doc({
		"doctype": "Coupon Code",
		"coupon_name": pos_coupon.coupon_name or f"Gift Card {pos_coupon.coupon_code}",
		"coupon_code": pos_coupon.coupon_code,
		"coupon_type": "Gift Card",
		"pricing_rule": pricing_rule.name,
		"valid_from": pos_coupon.valid_from or getdate(nowdate()),
		"valid_upto": pos_coupon.valid_upto or add_months(getdate(nowdate()), 12),
		"maximum_use": 0,  # Unlimited for gift cards with balance tracking
		"used": pos_coupon.used or 0,
		"customer": pos_coupon.customer,
		# Custom fields
		"pos_next_gift_card": 1,
		"gift_card_amount": balance,
		"original_gift_card_amount": original_amount,
		"source_invoice": pos_coupon.source_invoice,
	})
	coupon_code.insert(ignore_permissions=True)

	frappe.logger().info(f"Migrated POS Coupon {pos_coupon.coupon_code} to ERPNext Coupon Code")
