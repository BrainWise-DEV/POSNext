# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Gift Card API for POS Next

Handles:
- Gift card creation from POS Invoice (when selling gift card items)
- Gift card validation and application
- Gift card splitting (when amount > invoice total)
- ERPNext Coupon Code synchronization
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, add_months, getdate, random_string
import random
import string


# ==========================================
# Gift Card Code Generation
# ==========================================

def generate_gift_card_code():
	"""
	Generate unique gift card code in format XXXX-XXXX-XXXX

	Returns:
		str: Unique gift card code
	"""
	def segment():
		return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

	max_attempts = 100
	for _ in range(max_attempts):
		code = f"{segment()}-{segment()}-{segment()}"

		# Check uniqueness in both POS Coupon and ERPNext Coupon Code
		if not frappe.db.exists("POS Coupon", {"coupon_code": code}):
			if not frappe.db.exists("Coupon Code", {"coupon_code": code}):
				return code

	# Fallback: use hash-based code
	return frappe.generate_hash()[:12].upper()


# ==========================================
# Gift Card Settings
# ==========================================

def get_gift_card_settings(pos_profile):
	"""
	Get gift card settings for a POS Profile.

	Args:
		pos_profile: Name of the POS Profile

	Returns:
		dict: Gift card settings or None if not enabled
	"""
	if not pos_profile:
		return None

	# Get POS Settings for this profile
	pos_settings = frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile, "enabled": 1},
		[
			"enable_gift_cards",
			"gift_card_item",
			"sync_with_erpnext_coupon",
			"enable_gift_card_splitting",
			"gift_card_validity_months",
			"gift_card_notification"
		],
		as_dict=True
	)

	if not pos_settings or not pos_settings.get("enable_gift_cards"):
		return None

	return pos_settings


def is_gift_card_item(item_code, pos_profile):
	"""
	Check if an item is the designated gift card item.

	Args:
		item_code: Item code to check
		pos_profile: POS Profile name

	Returns:
		bool: True if item is the gift card item
	"""
	settings = get_gift_card_settings(pos_profile)
	if not settings:
		return False

	return settings.get("gift_card_item") == item_code


# ==========================================
# Gift Card Creation
# ==========================================

@frappe.whitelist()
def create_gift_card_from_invoice(invoice_name):
	"""
	Create gift card(s) when a gift card item is sold.
	Called after POS Invoice submission.

	Args:
		invoice_name: Name of the POS Invoice

	Returns:
		dict: Created gift card details or None
	"""
	if not invoice_name:
		return None

	invoice = frappe.get_doc("POS Invoice", invoice_name)

	# Check if invoice is submitted and paid
	if invoice.docstatus != 1:
		return None

	# Get gift card settings
	settings = get_gift_card_settings(invoice.pos_profile)
	if not settings:
		return None

	gift_card_item = settings.get("gift_card_item")
	if not gift_card_item:
		return None

	created_gift_cards = []

	# Find gift card items in the invoice
	for item in invoice.items:
		if item.item_code != gift_card_item:
			continue

		# Create gift card for each quantity
		qty = int(item.qty)
		for i in range(qty):
			gift_card = _create_single_gift_card(
				amount=flt(item.rate),
				customer=invoice.customer,
				company=invoice.company,
				source_invoice=invoice.name,
				settings=settings
			)
			if gift_card:
				created_gift_cards.append(gift_card)

	# Send notifications if configured
	if created_gift_cards and settings.get("gift_card_notification"):
		for gc in created_gift_cards:
			_send_gift_card_notification(gc, settings.get("gift_card_notification"))

	return {
		"success": True,
		"gift_cards": created_gift_cards
	}


def _create_single_gift_card(amount, customer, company, source_invoice, settings):
	"""
	Create a single gift card.

	Args:
		amount: Gift card value
		customer: Customer name (can be None for anonymous)
		company: Company name
		source_invoice: Source POS Invoice name
		settings: Gift card settings dict

	Returns:
		dict: Created gift card info
	"""
	try:
		code = generate_gift_card_code()
		validity_months = settings.get("gift_card_validity_months") or 12

		# Calculate validity dates
		valid_from = nowdate()
		valid_upto = None
		if validity_months > 0:
			valid_upto = add_months(valid_from, validity_months)

		# Create POS Coupon
		coupon_name = f"GC-{code}-{frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')}"

		pos_coupon = frappe.get_doc({
			"doctype": "POS Coupon",
			"coupon_name": coupon_name,
			"coupon_type": "Gift Card",
			"coupon_code": code,
			"discount_type": "Amount",
			"discount_amount": flt(amount),
			"gift_card_amount": flt(amount),
			"original_amount": flt(amount),
			"customer": customer,  # Can be None for anonymous gift cards
			"company": company,
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"maximum_use": 1,
			"used": 0,
			"source_invoice": source_invoice,
			"apply_on": "Grand Total"
		})
		pos_coupon.insert(ignore_permissions=True)

		# Sync with ERPNext Coupon Code if enabled
		erpnext_coupon = None
		if settings.get("sync_with_erpnext_coupon"):
			erpnext_coupon = _sync_to_erpnext_coupon(pos_coupon)

		return {
			"name": pos_coupon.name,
			"coupon_code": code,
			"amount": flt(amount),
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"customer": customer,
			"erpnext_coupon": erpnext_coupon
		}

	except Exception as e:
		frappe.log_error(
			"Gift Card Creation Failed",
			f"Failed to create gift card for invoice {source_invoice}: {str(e)}"
		)
		return None


def _send_gift_card_notification(gift_card_info, notification_name):
	"""
	Send notification for a created gift card.

	Args:
		gift_card_info: Dict with gift card details
		notification_name: Name of the Notification template
	"""
	try:
		if not frappe.db.exists("Notification", notification_name):
			return

		# Get the POS Coupon document
		pos_coupon = frappe.get_doc("POS Coupon", gift_card_info.get("name"))

		# Trigger the notification
		from frappe.email.doctype.notification.notification import evaluate_alert
		notification = frappe.get_doc("Notification", notification_name)
		evaluate_alert(pos_coupon, notification.event, notification.name)

	except Exception as e:
		frappe.log_error(
			"Gift Card Notification Failed",
			f"Failed to send notification for gift card {gift_card_info.get('coupon_code')}: {str(e)}"
		)


# ==========================================
# ERPNext Coupon Code Sync
# ==========================================

def _sync_to_erpnext_coupon(pos_coupon):
	"""
	Create ERPNext Coupon Code and Pricing Rule linked to POS Coupon.

	Args:
		pos_coupon: POS Coupon document

	Returns:
		str: Name of created ERPNext Coupon Code or None
	"""
	try:
		# First create the Pricing Rule
		pricing_rule = _create_pricing_rule_for_gift_card(
			amount=flt(pos_coupon.gift_card_amount or pos_coupon.discount_amount),
			coupon_code=pos_coupon.coupon_code,
			company=pos_coupon.company,
			valid_from=pos_coupon.valid_from,
			valid_upto=pos_coupon.valid_upto
		)

		if not pricing_rule:
			return None

		# Create ERPNext Coupon Code
		erpnext_coupon = frappe.get_doc({
			"doctype": "Coupon Code",
			"coupon_name": f"Gift Card {pos_coupon.coupon_code}",
			"coupon_type": "Gift Card",
			"coupon_code": pos_coupon.coupon_code,
			"pricing_rule": pricing_rule,
			"valid_from": pos_coupon.valid_from,
			"valid_upto": pos_coupon.valid_upto,
			"maximum_use": 1,
			"used": 0,
			"customer": pos_coupon.customer,
			# Custom fields
			"gift_card_amount": flt(pos_coupon.gift_card_amount or pos_coupon.discount_amount),
			"original_gift_card_amount": flt(pos_coupon.original_amount or pos_coupon.discount_amount),
			"pos_coupon": pos_coupon.name,
			"source_pos_invoice": pos_coupon.source_invoice
		})
		erpnext_coupon.insert(ignore_permissions=True)

		# Update POS Coupon with ERPNext references
		pos_coupon.db_set("erpnext_coupon_code", erpnext_coupon.name)
		pos_coupon.db_set("pricing_rule", pricing_rule)

		return erpnext_coupon.name

	except Exception as e:
		frappe.log_error(
			"ERPNext Coupon Sync Failed",
			f"Failed to sync POS Coupon {pos_coupon.name} to ERPNext: {str(e)}"
		)
		return None


def _create_pricing_rule_for_gift_card(amount, coupon_code, company, valid_from=None, valid_upto=None):
	"""
	Create Pricing Rule for gift card discount.

	Args:
		amount: Discount amount
		coupon_code: Coupon code string
		company: Company name
		valid_from: Start date
		valid_upto: End date

	Returns:
		str: Name of created Pricing Rule or None
	"""
	try:
		pricing_rule = frappe.get_doc({
			"doctype": "Pricing Rule",
			"title": f"Gift Card {coupon_code}",
			"apply_on": "Transaction",
			"price_or_product_discount": "Price",
			"rate_or_discount": "Discount Amount",
			"discount_amount": flt(amount),
			"selling": 1,
			"buying": 0,
			"applicable_for": "",
			"company": company,
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"valid_from": valid_from or nowdate(),
			"valid_upto": valid_upto,
			"coupon_code_based": 1,
			"is_cumulative": 1,
			"priority": "1"
		})
		pricing_rule.insert(ignore_permissions=True)

		return pricing_rule.name

	except Exception as e:
		frappe.log_error(
			"Pricing Rule Creation Failed",
			f"Failed to create pricing rule for gift card {coupon_code}: {str(e)}"
		)
		return None


# ==========================================
# Gift Card Application
# ==========================================

@frappe.whitelist()
def apply_gift_card(coupon_code, invoice_total, customer=None, company=None):
	"""
	Apply a gift card to an invoice.

	Args:
		coupon_code: Gift card code
		invoice_total: Total invoice amount
		customer: Optional customer for validation

	Returns:
		dict: Discount amount and gift card info
	"""
	from pos_next.pos_next.doctype.pos_coupon.pos_coupon import check_coupon_code

	# Validate the coupon
	result = check_coupon_code(coupon_code, customer=customer, company=company)

	if not result.get("valid"):
		return {
			"success": False,
			"message": result.get("msg", _("Invalid gift card"))
		}

	coupon = result.get("coupon")

	if coupon.coupon_type != "Gift Card":
		return {
			"success": False,
			"message": _("This is not a gift card")
		}

	# Get available balance
	available_balance = flt(coupon.gift_card_amount) if coupon.gift_card_amount else flt(coupon.discount_amount)

	# Calculate discount (minimum of balance and invoice total)
	discount_amount = min(available_balance, flt(invoice_total))

	# Check if splitting will be needed
	will_split = available_balance > flt(invoice_total)
	remaining_balance = available_balance - discount_amount if will_split else 0

	return {
		"success": True,
		"coupon_code": coupon.coupon_code,
		"coupon_name": coupon.name,
		"discount_amount": discount_amount,
		"available_balance": available_balance,
		"will_split": will_split,
		"remaining_balance": remaining_balance,
		"customer": coupon.customer,
		"valid_upto": coupon.valid_upto
	}


@frappe.whitelist()
def get_gift_cards_with_balance(customer=None, company=None):
	"""
	Get all gift cards with available balance.

	Args:
		customer: Optional customer filter
		company: Company filter

	Returns:
		list: Gift cards with balance > 0
	"""
	filters = {
		"coupon_type": "Gift Card",
		"disabled": 0
	}

	if company:
		filters["company"] = company

	# Get all gift cards
	gift_cards = frappe.get_all(
		"POS Coupon",
		filters=filters,
		fields=[
			"name", "coupon_code", "coupon_name", "customer", "customer_name",
			"gift_card_amount", "original_amount", "discount_amount",
			"valid_from", "valid_upto", "used", "maximum_use"
		],
		order_by="creation desc"
	)

	# Filter by balance and validity
	today = getdate(nowdate())
	result = []

	for gc in gift_cards:
		# Check validity dates
		if gc.valid_from and getdate(gc.valid_from) > today:
			continue
		if gc.valid_upto and getdate(gc.valid_upto) < today:
			continue

		# Check usage
		if gc.used and gc.maximum_use and gc.used >= gc.maximum_use:
			continue

		# Check balance
		balance = flt(gc.gift_card_amount) if gc.gift_card_amount else flt(gc.discount_amount)
		if balance <= 0:
			continue

		# Check customer filter (if customer specified, show both assigned and anonymous)
		if customer and gc.customer and gc.customer != customer:
			continue

		gc["balance"] = balance
		result.append(gc)

	return result


# ==========================================
# Gift Card Splitting
# ==========================================

@frappe.whitelist()
def process_gift_card_on_submit(invoice_name):
	"""
	Process gift card after invoice submission.
	Handles splitting if gift card amount > invoice total.

	Args:
		invoice_name: Name of the submitted POS Invoice
	"""
	if not invoice_name:
		return

	invoice = frappe.get_doc("POS Invoice", invoice_name)

	# Check if a coupon was used
	if not invoice.coupon_code:
		return

	# Get the POS Coupon
	coupon = frappe.db.get_value(
		"POS Coupon",
		{"coupon_code": invoice.coupon_code.upper()},
		["name", "coupon_type", "gift_card_amount", "discount_amount"],
		as_dict=True
	)

	if not coupon or coupon.coupon_type != "Gift Card":
		return

	# Get gift card settings
	settings = get_gift_card_settings(invoice.pos_profile)
	if not settings:
		return

	# Calculate amounts
	gift_card_balance = flt(coupon.gift_card_amount) if coupon.gift_card_amount else flt(coupon.discount_amount)
	used_amount = flt(invoice.discount_amount) if invoice.discount_amount else gift_card_balance

	# Check if splitting is needed and enabled
	if gift_card_balance > used_amount and settings.get("enable_gift_card_splitting"):
		remaining_amount = gift_card_balance - used_amount
		_split_gift_card(coupon.name, used_amount, remaining_amount, invoice.name, settings)
	else:
		# Full usage - mark as used
		_mark_gift_card_used(coupon.name)


def _split_gift_card(coupon_name, used_amount, remaining_amount, invoice_name, settings):
	"""
	Split a gift card into used and remaining portions.

	Args:
		coupon_name: Original POS Coupon name
		used_amount: Amount being used in current transaction
		remaining_amount: Amount to keep for future use
		invoice_name: Invoice using the gift card
		settings: Gift card settings

	Returns:
		dict: Split result info
	"""
	try:
		original_coupon = frappe.get_doc("POS Coupon", coupon_name)

		# Update original coupon with remaining balance
		original_coupon.gift_card_amount = flt(remaining_amount)
		original_coupon.discount_amount = flt(remaining_amount)

		# Add note about the split
		split_note = _(
			"\n\n---\nSplit on {date}: {used} used for invoice {invoice}, {remaining} remaining."
		).format(
			date=nowdate(),
			used=frappe.format_value(used_amount, {"fieldtype": "Currency"}),
			invoice=invoice_name,
			remaining=frappe.format_value(remaining_amount, {"fieldtype": "Currency"})
		)
		original_coupon.description = (original_coupon.description or "") + split_note
		original_coupon.save(ignore_permissions=True)

		# Update ERPNext Coupon Code if synced
		if settings.get("sync_with_erpnext_coupon") and original_coupon.erpnext_coupon_code:
			_update_erpnext_coupon_amount(original_coupon.erpnext_coupon_code, remaining_amount)

		frappe.db.commit()

		return {
			"success": True,
			"remaining_balance": remaining_amount,
			"used_amount": used_amount
		}

	except Exception as e:
		frappe.log_error(
			"Gift Card Split Failed",
			f"Failed to split gift card {coupon_name}: {str(e)}"
		)
		return None


def _mark_gift_card_used(coupon_name):
	"""
	Mark a gift card as fully used.

	Args:
		coupon_name: POS Coupon name
	"""
	try:
		coupon = frappe.get_doc("POS Coupon", coupon_name)
		coupon.used = 1
		coupon.gift_card_amount = 0
		coupon.save(ignore_permissions=True)

		# Update ERPNext Coupon Code if synced
		if coupon.erpnext_coupon_code:
			frappe.db.set_value("Coupon Code", coupon.erpnext_coupon_code, {
				"used": 1,
				"gift_card_amount": 0
			})

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			"Gift Card Mark Used Failed",
			f"Failed to mark gift card {coupon_name} as used: {str(e)}"
		)


def _update_erpnext_coupon_amount(erpnext_coupon_name, new_amount):
	"""
	Update ERPNext Coupon Code and its Pricing Rule with new amount.

	Args:
		erpnext_coupon_name: ERPNext Coupon Code name
		new_amount: New gift card amount
	"""
	try:
		erpnext_coupon = frappe.get_doc("Coupon Code", erpnext_coupon_name)
		erpnext_coupon.gift_card_amount = flt(new_amount)
		erpnext_coupon.save(ignore_permissions=True)

		# Update linked Pricing Rule
		if erpnext_coupon.pricing_rule:
			frappe.db.set_value("Pricing Rule", erpnext_coupon.pricing_rule, "discount_amount", flt(new_amount))

	except Exception as e:
		frappe.log_error(
			"ERPNext Coupon Update Failed",
			f"Failed to update ERPNext Coupon {erpnext_coupon_name}: {str(e)}"
		)


# ==========================================
# Gift Card Return/Cancel Handling
# ==========================================

@frappe.whitelist()
def process_gift_card_on_cancel(invoice_name):
	"""
	Process gift card when invoice is cancelled.
	Restores gift card balance if it was partially used.

	Args:
		invoice_name: Name of the cancelled POS Invoice
	"""
	if not invoice_name:
		return

	invoice = frappe.get_doc("POS Invoice", invoice_name)

	# Check if a coupon was used
	if not invoice.coupon_code:
		return

	# Get the POS Coupon
	coupon_name = frappe.db.get_value(
		"POS Coupon",
		{"coupon_code": invoice.coupon_code.upper()},
		"name"
	)

	if not coupon_name:
		return

	try:
		coupon = frappe.get_doc("POS Coupon", coupon_name)

		if coupon.coupon_type != "Gift Card":
			return

		# Restore balance
		refund_amount = flt(invoice.discount_amount)
		current_balance = flt(coupon.gift_card_amount)
		new_balance = current_balance + refund_amount

		# Cap at original amount
		if coupon.original_amount and new_balance > flt(coupon.original_amount):
			new_balance = flt(coupon.original_amount)

		coupon.gift_card_amount = new_balance
		coupon.discount_amount = new_balance
		coupon.used = 0  # Reset used flag

		# Add note
		cancel_note = _(
			"\n\n---\nInvoice {invoice} cancelled on {date}. {amount} restored to balance."
		).format(
			invoice=invoice_name,
			date=nowdate(),
			amount=frappe.format_value(refund_amount, {"fieldtype": "Currency"})
		)
		coupon.description = (coupon.description or "") + cancel_note
		coupon.save(ignore_permissions=True)

		# Update ERPNext Coupon Code if synced
		if coupon.erpnext_coupon_code:
			_update_erpnext_coupon_amount(coupon.erpnext_coupon_code, new_balance)
			frappe.db.set_value("Coupon Code", coupon.erpnext_coupon_code, "used", 0)

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			"Gift Card Cancel Processing Failed",
			f"Failed to process gift card cancel for invoice {invoice_name}: {str(e)}"
		)
