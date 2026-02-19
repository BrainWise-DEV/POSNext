# -*- coding: utf-8 -*-
# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Gift Card API for POS Next

Handles:
- Gift card creation from Invoice (when selling gift card items)
- Gift card validation and application
- Gift card splitting (when amount > invoice total)
- Direct ERPNext Coupon Code integration (no POS Coupon)
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, add_months, getdate
import random
import string


# ==========================================
# Gift Card Code Generation
# ==========================================

def generate_gift_card_code():
	"""
	Generate unique gift card code in format GC-XXXX-XXXX

	Returns:
		str: Unique gift card code
	"""
	def segment():
		return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

	max_attempts = 100
	for _ in range(max_attempts):
		code = f"GC-{segment()}-{segment()}"

		# Check uniqueness in ERPNext Coupon Code only
		if not frappe.db.exists("Coupon Code", {"coupon_code": code}):
			return code

	# Fallback: use hash-based code
	return f"GC-{frappe.generate_hash()[:8].upper()}"


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
# Gift Card Creation (Direct to ERPNext Coupon Code)
# ==========================================

@frappe.whitelist()
def create_gift_card_from_invoice(doc, method=None):
	"""
	Create gift card(s) when a gift card item is sold.
	Called after POS Invoice or Sales Invoice submission.
	Creates ERPNext Coupon Code directly (no POS Coupon).

	Args:
		doc: Invoice document or invoice name
		method: Hook method name (optional)

	Returns:
		dict: Created gift card details or None
	"""
	if not doc:
		return None

	if isinstance(doc, str):
		# Try Sales Invoice first, then POS Invoice
		if frappe.db.exists("Sales Invoice", doc):
			invoice = frappe.get_doc("Sales Invoice", doc)
		else:
			invoice = frappe.get_doc("POS Invoice", doc)
	else:
		invoice = doc

	# Check if invoice is submitted
	if invoice.docstatus != 1:
		return None

	# Get POS profile
	pos_profile = getattr(invoice, 'pos_profile', None)
	if not pos_profile and invoice.doctype == "Sales Invoice":
		pos_profile = frappe.db.get_value(
			"POS Opening Entry",
			{"name": invoice.get("posa_pos_opening_shift")},
			"pos_profile"
		) if invoice.get("posa_pos_opening_shift") else None

	# Get gift card settings
	settings = get_gift_card_settings(pos_profile)
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
			gift_card = _create_gift_card(
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
	} if created_gift_cards else None


def _create_gift_card(amount, customer, company, source_invoice, settings):
	"""
	Create a gift card directly as ERPNext Coupon Code + Pricing Rule.

	Args:
		amount: Gift card value
		customer: Customer name (can be None for anonymous)
		company: Company name
		source_invoice: Source Invoice name
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

		# Create Pricing Rule first
		pricing_rule = _create_pricing_rule_for_gift_card(
			amount=flt(amount),
			coupon_code=code,
			company=company,
			valid_from=valid_from,
			valid_upto=valid_upto
		)

		if not pricing_rule:
			frappe.log_error(
				"Gift Card Creation Failed",
				f"Failed to create pricing rule for gift card {code}"
			)
			return None

		# Create ERPNext Coupon Code directly
		coupon = frappe.get_doc({
			"doctype": "Coupon Code",
			"coupon_name": f"Gift Card {code}",
			"coupon_type": "Promotional",
			"coupon_code": code,
			"pricing_rule": pricing_rule,
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"maximum_use": 0,  # Unlimited uses until balance is exhausted
			"used": 0,
			# Custom fields for POS Next
			"pos_next_gift_card": 1,
			"gift_card_amount": flt(amount),
			"original_gift_card_amount": flt(amount),
			"source_invoice": source_invoice
		})
		coupon.insert(ignore_permissions=True)

		return {
			"name": coupon.name,
			"coupon_code": code,
			"amount": flt(amount),
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"customer": customer
		}

	except Exception as e:
		frappe.log_error(
			"Gift Card Creation Failed",
			f"Failed to create gift card for invoice {source_invoice}: {str(e)}"
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
		pricing_rule_data = {
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
			"coupon_code_based": 1,
			"priority": "1"
		}

		# Only set valid_upto and is_cumulative if we have an end date
		# ERPNext requires valid_upto when is_cumulative=1
		if valid_upto:
			pricing_rule_data["valid_upto"] = valid_upto
			pricing_rule_data["is_cumulative"] = 1

		pricing_rule = frappe.get_doc(pricing_rule_data)
		pricing_rule.insert(ignore_permissions=True)

		return pricing_rule.name

	except Exception as e:
		frappe.log_error(
			"Pricing Rule Creation Failed",
			f"Failed to create pricing rule for gift card {coupon_code}: {str(e)}"
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

		coupon = frappe.get_doc("Coupon Code", gift_card_info.get("name"))

		from frappe.email.doctype.notification.notification import evaluate_alert
		notification = frappe.get_doc("Notification", notification_name)
		evaluate_alert(coupon, notification.event, notification.name)

	except Exception as e:
		frappe.log_error(
			"Gift Card Notification Failed",
			f"Failed to send notification for gift card {gift_card_info.get('coupon_code')}: {str(e)}"
		)


# ==========================================
# Manual Gift Card Creation (for ERPNext UI button)
# ==========================================

@frappe.whitelist()
def create_gift_card_manual(amount, company, customer=None, validity_months=12):
	"""
	Create a gift card manually (from ERPNext Coupon Code list button).

	Args:
		amount: Gift card value
		company: Company name
		customer: Optional customer assignment
		validity_months: Validity period in months

	Returns:
		dict: Created gift card info
	"""
	try:
		code = generate_gift_card_code()

		valid_from = nowdate()
		valid_upto = None
		if int(validity_months) > 0:
			valid_upto = add_months(valid_from, int(validity_months))

		# Create Pricing Rule
		pricing_rule = _create_pricing_rule_for_gift_card(
			amount=flt(amount),
			coupon_code=code,
			company=company,
			valid_from=valid_from,
			valid_upto=valid_upto
		)

		if not pricing_rule:
			return {"success": False, "message": _("Failed to create pricing rule")}

		# Create Coupon Code
		coupon = frappe.get_doc({
			"doctype": "Coupon Code",
			"coupon_name": f"Gift Card {code}",
			"coupon_type": "Promotional",
			"coupon_code": code,
			"pricing_rule": pricing_rule,
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"maximum_use": 0,
			"used": 0,
			"pos_next_gift_card": 1,
			"gift_card_amount": flt(amount),
			"original_gift_card_amount": flt(amount),
			"customer": customer
		})
		coupon.insert(ignore_permissions=True)

		return {
			"success": True,
			"name": coupon.name,
			"coupon_code": code,
			"amount": flt(amount),
			"valid_from": valid_from,
			"valid_upto": valid_upto
		}

	except Exception as e:
		frappe.log_error("Manual Gift Card Creation Failed", str(e))
		return {"success": False, "message": str(e)}


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
		company: Company for validation

	Returns:
		dict: Discount amount and gift card info
	"""
	coupon_code = (coupon_code or "").strip().upper()

	if not coupon_code:
		return {"success": False, "message": _("Please enter a gift card code")}

	# Get the Coupon Code from ERPNext
	coupon = frappe.db.get_value(
		"Coupon Code",
		{"coupon_code": coupon_code},
		[
			"name", "coupon_code", "coupon_type", "pricing_rule",
			"valid_from", "valid_upto", "maximum_use", "used",
			"pos_next_gift_card", "gift_card_amount", "original_gift_card_amount"
		],
		as_dict=True
	)

	if not coupon:
		return {"success": False, "message": _("Gift card not found")}

	# Check if it's a POS Next gift card
	if not coupon.get("pos_next_gift_card"):
		return {"success": False, "message": _("This is not a POS Next gift card")}

	# Check validity dates
	today = getdate(nowdate())
	if coupon.valid_from and getdate(coupon.valid_from) > today:
		return {"success": False, "message": _("Gift card is not yet valid")}
	if coupon.valid_upto and getdate(coupon.valid_upto) < today:
		return {"success": False, "message": _("Gift card has expired")}

	# Get available balance
	available_balance = flt(coupon.gift_card_amount)

	if available_balance <= 0:
		return {"success": False, "message": _("Gift card has no remaining balance")}

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
		"valid_upto": coupon.valid_upto
	}


@frappe.whitelist()
def get_gift_cards_with_balance(customer=None, company=None):
	"""
	Get all POS Next gift cards with available balance.

	Args:
		customer: Optional customer filter
		company: Company filter

	Returns:
		list: Gift cards with balance > 0
	"""
	filters = {
		"coupon_type": "Promotional",
		"pos_next_gift_card": 1
	}

	# Get all POS Next gift cards
	gift_cards = frappe.get_all(
		"Coupon Code",
		filters=filters,
		fields=[
			"name", "coupon_code", "coupon_name",
			"gift_card_amount", "original_gift_card_amount",
			"valid_from", "valid_upto", "used", "maximum_use",
			"source_invoice"
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

		# Check balance
		balance = flt(gc.gift_card_amount)
		if balance <= 0:
			continue

		gc["balance"] = balance
		result.append(gc)

	return result


# ==========================================
# Gift Card Lookup Helper
# ==========================================

def _get_gift_card_coupon(coupon_ref, fields):
	"""
	Look up a Coupon Code document by either its document name or its coupon_code field value.

	The `coupon_code` column on Sales Invoice stores the Coupon Code *document name*
	(e.g. "Gift Card GC-MV2S-Y1G9"), while the `coupon_code` *field* on the Coupon
	Code doctype holds the short code (e.g. "GC-MV2S-Y1G9").  Both cases must be
	handled transparently.

	Args:
		coupon_ref: Document name OR coupon_code field value (case-insensitive).
		fields: List of fields to return.

	Returns:
		dict or None
	"""
	if not coupon_ref:
		return None

	# 1. Try by document name first (handles "Gift Card GC-…" style names).
	coupon = frappe.db.get_value("Coupon Code", coupon_ref, fields, as_dict=True)
	if coupon:
		return coupon

	# 2. Fall back to filtering by the coupon_code field value.
	coupon = frappe.db.get_value(
		"Coupon Code",
		{"coupon_code": coupon_ref},
		fields,
		as_dict=True
	)
	return coupon


# ==========================================
# Gift Card Processing on Invoice Submit
# ==========================================

@frappe.whitelist()
def process_gift_card_on_submit(doc, method=None):
	"""
	Process gift card after invoice submission.
	Updates the ERPNext Coupon Code balance.
	Handles splitting if gift card amount > invoice total.
	Also handles returns (Credit Notes) to restore gift card balance.

	Args:
		doc: Invoice document or invoice name
		method: Hook method name (optional)
	"""
	if not doc:
		return

	if isinstance(doc, str):
		if frappe.db.exists("Sales Invoice", doc):
			invoice = frappe.get_doc("Sales Invoice", doc)
		else:
			invoice = frappe.get_doc("POS Invoice", doc)
	else:
		invoice = doc

	# Handle returns (Credit Notes) - restore gift card balance
	if getattr(invoice, 'is_return', 0) and getattr(invoice, 'return_against', None):
		_process_gift_card_return(invoice)
		return

	# Get coupon code from invoice
	coupon_code = getattr(invoice, 'posa_coupon_code', None) or getattr(invoice, 'coupon_code', None)

	if not coupon_code:
		return

	coupon_code = coupon_code.strip()

	# Get the Coupon Code from ERPNext.
	# invoice.coupon_code stores the document *name* (e.g. "Gift Card GC-MV2S-Y1G9"),
	# so we must look up by name first, then fall back to the coupon_code field value.
	coupon = _get_gift_card_coupon(
		coupon_code,
		["name", "coupon_type", "pos_next_gift_card", "gift_card_amount", "pricing_rule"]
	)

	if not coupon:
		return

	# Only process POS Next gift cards
	if not coupon.get("pos_next_gift_card"):
		return

	# Get gift card settings for splitting option
	pos_profile = getattr(invoice, 'pos_profile', None)
	if not pos_profile and invoice.doctype == "Sales Invoice":
		pos_profile = frappe.db.get_value(
			"POS Opening Entry",
			{"name": invoice.get("posa_pos_opening_shift")},
			"pos_profile"
		) if invoice.get("posa_pos_opening_shift") else None

	settings = get_gift_card_settings(pos_profile)
	enable_splitting = settings.get("enable_gift_card_splitting") if settings else True

	# Calculate amounts
	gift_card_balance = flt(coupon.gift_card_amount)

	# Use posa_gift_card_amount_used if available (persisted field that ERPNext doesn't clear)
	# Fall back to discount_amount, then to gift_card_balance as last resort
	used_amount = flt(getattr(invoice, 'posa_gift_card_amount_used', 0))
	if not used_amount:
		used_amount = flt(invoice.discount_amount) if invoice.discount_amount else gift_card_balance

	if gift_card_balance <= 0:
		return

	# Process based on splitting
	if gift_card_balance > used_amount and enable_splitting:
		# Partial usage - update balance
		remaining_amount = gift_card_balance - used_amount
		_update_gift_card_balance(coupon.name, remaining_amount, coupon.pricing_rule)
	else:
		# Full usage - mark as exhausted
		_update_gift_card_balance(coupon.name, 0, coupon.pricing_rule)


def _update_gift_card_balance(coupon_name, new_balance, pricing_rule=None):
	"""
	Update gift card balance in Coupon Code and Pricing Rule.

	Args:
		coupon_name: Coupon Code name
		new_balance: New balance amount
		pricing_rule: Associated Pricing Rule name
	"""
	try:
		# Get current used count and increment it
		current_used = frappe.db.get_value("Coupon Code", coupon_name, "used") or 0

		# Update Coupon Code
		frappe.db.set_value(
			"Coupon Code",
			coupon_name,
			{
				"gift_card_amount": flt(new_balance),
				"used": current_used + 1
			}
		)

		# Update Pricing Rule
		if pricing_rule:
			frappe.db.set_value(
				"Pricing Rule",
				pricing_rule,
				"discount_amount",
				flt(new_balance)
			)

	except Exception as e:
		frappe.log_error(
			"Gift Card Balance Update Failed",
			f"Failed to update gift card {coupon_name}: {str(e)}"
		)


# ==========================================
# Gift Card Return/Cancel Handling
# ==========================================

def _process_gift_card_return(return_invoice):
	"""
	Process gift card balance restoration when a return (Credit Note) is submitted.
	Gets the gift card info from the original invoice and restores the balance.

	Args:
		return_invoice: The return invoice document (with is_return=1)
	"""
	try:
		original_invoice_name = return_invoice.return_against
		if not original_invoice_name:
			return

		# Get the original invoice to find the gift card used
		original_invoice = frappe.get_doc(return_invoice.doctype, original_invoice_name)

		# Get coupon code from original invoice
		coupon_code = getattr(original_invoice, 'posa_coupon_code', None) or getattr(original_invoice, 'coupon_code', None)

		if not coupon_code:
			return

		coupon_code = coupon_code.strip()

		# Get the Coupon Code (invoice stores the doc *name*, not just the code value).
		coupon = _get_gift_card_coupon(
			coupon_code,
			["name", "coupon_type", "pos_next_gift_card", "gift_card_amount",
			 "original_gift_card_amount", "pricing_rule"]
		)

		if not coupon:
			return

		# Only process POS Next gift cards
		if not coupon.get("pos_next_gift_card"):
			return

		# Calculate the refund amount from the return invoice
		# Use absolute value since return invoices have negative amounts
		# Get the gift card amount used from the original invoice
		refund_amount = flt(getattr(original_invoice, 'posa_gift_card_amount_used', 0))
		if not refund_amount:
			refund_amount = flt(original_invoice.discount_amount)

		# For partial returns, calculate proportionally
		# Compare return net total vs original net total (both are after discount)
		original_net = abs(flt(original_invoice.grand_total))
		return_net = abs(flt(return_invoice.grand_total))

		if original_net > 0 and return_net < original_net:
			# Partial return - calculate proportional refund
			return_ratio = return_net / original_net
			refund_amount = flt(refund_amount * return_ratio)

		if refund_amount <= 0:
			return

		current_balance = flt(coupon.gift_card_amount)
		original_amount = flt(coupon.original_gift_card_amount)

		new_balance = current_balance + refund_amount

		# Cap at original amount
		if original_amount and new_balance > original_amount:
			new_balance = original_amount

		# Update balance (don't increment used counter for returns)
		frappe.db.set_value(
			"Coupon Code",
			coupon.name,
			"gift_card_amount",
			flt(new_balance)
		)

		# Update Pricing Rule
		if coupon.pricing_rule:
			frappe.db.set_value(
				"Pricing Rule",
				coupon.pricing_rule,
				"discount_amount",
				flt(new_balance)
			)

	except Exception as e:
		frappe.log_error(
			"Gift Card Return Processing Failed",
			f"Failed to process gift card return for invoice {return_invoice.name}: {str(e)}"
		)


@frappe.whitelist()
def get_gift_cards_from_invoice(invoice_name):
	"""
	Get gift cards created from a specific invoice.

	Args:
		invoice_name: Name of the source invoice

	Returns:
		list: Gift cards created from this invoice
	"""
	if not invoice_name:
		return []

	gift_cards = frappe.get_all(
		"Coupon Code",
		filters={
			"pos_next_gift_card": 1,
			"source_invoice": invoice_name
		},
		fields=[
			"name", "coupon_code", "coupon_name",
			"gift_card_amount", "original_gift_card_amount",
			"valid_from", "valid_upto"
		],
		order_by="creation asc"
	)

	return gift_cards


@frappe.whitelist()
def process_gift_card_on_cancel(doc, method=None):
	"""
	Process gift card when invoice is cancelled.
	Restores gift card balance.

	Args:
		doc: Invoice document or invoice name
		method: Hook method name (optional)
	"""
	if not doc:
		return

	if isinstance(doc, str):
		if frappe.db.exists("Sales Invoice", doc):
			invoice = frappe.get_doc("Sales Invoice", doc)
		else:
			invoice = frappe.get_doc("POS Invoice", doc)
	else:
		invoice = doc

	# Get coupon code from invoice
	coupon_code = getattr(invoice, 'posa_coupon_code', None) or getattr(invoice, 'coupon_code', None)

	if not coupon_code:
		return

	coupon_code = coupon_code.strip()

	# Get the Coupon Code (invoice stores the doc *name*, not just the code value).
	coupon = _get_gift_card_coupon(
		coupon_code,
		["name", "coupon_type", "pos_next_gift_card", "gift_card_amount",
		 "original_gift_card_amount", "pricing_rule"]
	)

	if not coupon:
		return

	# Only process POS Next gift cards
	if not coupon.get("pos_next_gift_card"):
		return

	try:
		# Calculate restored balance
		# Use posa_gift_card_amount_used if available (persisted field that ERPNext doesn't clear)
		refund_amount = flt(getattr(invoice, 'posa_gift_card_amount_used', 0))
		if not refund_amount:
			refund_amount = flt(invoice.discount_amount)

		current_balance = flt(coupon.gift_card_amount)
		original_amount = flt(coupon.original_gift_card_amount)

		new_balance = current_balance + refund_amount

		# Cap at original amount
		if original_amount and new_balance > original_amount:
			new_balance = original_amount

		# Update balance
		_update_gift_card_balance(coupon.name, new_balance, coupon.pricing_rule)

	except Exception as e:
		frappe.log_error(
			"Gift Card Cancel Processing Failed",
			f"Failed to process gift card cancel for invoice {invoice.name}: {str(e)}"
		)
