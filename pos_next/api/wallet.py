# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

"""
Wallet API for POS Next
Handles wallet payments, validation, and loyalty points conversion
"""

import frappe
from frappe import _
from frappe.utils import flt, cint


def validate_wallet_payment(doc, method=None):
	"""
	Validate wallet payment on Sales Invoice.
	Called during validate hook.
	"""
	if not doc.is_pos:
		return

	# Get wallet payment amount from payments
	wallet_amount = get_wallet_amount_from_payments(doc.payments)

	if wallet_amount <= 0:
		return

	# Get customer wallet balance
	wallet_balance = get_customer_wallet_balance(doc.customer, doc.company, exclude_invoice=doc.name)

	if wallet_amount > wallet_balance:
		frappe.throw(
			_("Insufficient wallet balance. Available: {0}, Requested: {1}").format(
				frappe.format_value(wallet_balance, {"fieldtype": "Currency"}),
				frappe.format_value(wallet_amount, {"fieldtype": "Currency"})
			),
			title=_("Wallet Balance Error")
		)


def process_loyalty_to_wallet(doc, method=None):
	"""
	Convert earned loyalty points to wallet balance after invoice submission.
	Called during on_submit hook.
	"""
	if not doc.is_pos or doc.is_return:
		return

	# Check if loyalty to wallet is enabled
	pos_settings = get_pos_settings(doc.pos_profile)
	if not pos_settings:
		return

	if not cint(pos_settings.get("enable_loyalty_program")) or not cint(pos_settings.get("loyalty_to_wallet")):
		return

	# Check if customer has loyalty program
	loyalty_program = frappe.db.get_value("Customer", doc.customer, "loyalty_program")
	if not loyalty_program:
		return

	# Check if the invoice amount meets the applicable tier's min_spent threshold.
	# Single Tier Program: the one rule's min_spent must be met.
	# Multiple Tier Program: the invoice must reach at least the lowest tier's min_spent.
	lp_doc = frappe.get_doc("Loyalty Program", loyalty_program)
	tiers = sorted(
		[d.as_dict() for d in lp_doc.collection_rules],
		key=lambda r: flt(r.get("min_spent")),
	)
	invoice_amount = abs(flt(doc.grand_total))
	matched_tier = None
	for t in tiers:
		if flt(invoice_amount) >= flt(t.get("min_spent")):
			matched_tier = t
	if not matched_tier:
		# Invoice amount below the minimum spend threshold of all tiers — no loyalty credit
		return

	# Get the loyalty points earned from this invoice
	loyalty_entry = frappe.db.get_value(
		"Loyalty Point Entry",
		{
			"invoice_type": "Sales Invoice",
			"invoice": doc.name,
			"loyalty_points": [">", 0]
		},
		["loyalty_points", "name"],
		as_dict=True
	)

	if not loyalty_entry or loyalty_entry.loyalty_points <= 0:
		return

	# Get conversion rate from Loyalty Program (standard ERPNext field)
	conversion_rate = flt(frappe.db.get_value("Loyalty Program", loyalty_program, "conversion_factor")) or 1.0

	# Calculate wallet credit amount
	credit_amount = flt(loyalty_entry.loyalty_points) * conversion_rate

	if credit_amount <= 0:
		return

	try:
		# Get or create customer wallet
		wallet = get_or_create_wallet(doc.customer, doc.company, pos_settings)

		if not wallet:
			return

		# Create wallet transaction
		from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

		transaction = create_wallet_credit(
			wallet=wallet.name,
			amount=credit_amount,
			source_type="Loyalty Program",
			remarks=_("Loyalty points conversion from {0}: {1} points = {2}").format(
				doc.name,
				loyalty_entry.loyalty_points,
				frappe.format_value(credit_amount, {"fieldtype": "Currency"})
			),
			reference_doctype="Sales Invoice",
			reference_name=doc.name,
			submit=True
		)

		frappe.msgprint(
			_("Loyalty points converted to wallet: {0} points = {1}").format(
				loyalty_entry.loyalty_points,
				frappe.format_value(credit_amount, {"fieldtype": "Currency"})
			),
			alert=True,
			indicator="green"
		)

	except Exception as e:
		frappe.log_error(
			title="Loyalty to Wallet Conversion Error",
			message=f"Invoice: {doc.name}, Error: {str(e)}\n{frappe.get_traceback()}"
		)


def get_wallet_amount_from_payments(payments):
	"""
	Calculate total wallet payment amount from invoice payments.
	"""
	wallet_amount = 0.0

	for payment in payments:
		if not payment.mode_of_payment:
			continue

		is_wallet = frappe.db.get_value(
			"Mode of Payment",
			payment.mode_of_payment,
			"is_wallet_payment"
		)

		if is_wallet:
			wallet_amount += flt(payment.amount)

	return wallet_amount


@frappe.whitelist()
def get_customer_wallet_balance(customer, company=None, exclude_invoice=None):
	"""
	Get customer's available wallet balance.

	For receivable accounts:
	- Negative GL balance = customer has credit (we owe them) = positive wallet balance
	- Positive GL balance = customer owes us = no wallet balance

	Args:
		customer: Customer ID
		company: Company (optional)
		exclude_invoice: Invoice name to exclude from pending calculations

	Returns:
		float: Available wallet balance
	"""
	try:
		from erpnext.accounts.utils import get_balance_on

		filters = {"customer": customer, "status": "Active"}
		if company:
			filters["company"] = company

		wallet = frappe.db.get_value("Wallet", filters, ["name", "account"], as_dict=True)

		if not wallet:
			return 0.0

		# Get balance from GL entries
		gl_balance = get_balance_on(
			account=wallet.account,
			party_type="Customer",
			party=customer
		)

		# Negate because negative receivable balance = positive wallet credit
		wallet_balance = -flt(gl_balance)

		# Subtract pending wallet payments from open POS invoices
		pending_wallet_amount = get_pending_wallet_payments(customer, exclude_invoice)

		available_balance = flt(wallet_balance) - flt(pending_wallet_amount)

		return available_balance if available_balance > 0 else 0.0

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Wallet Balance Error")
		return 0.0


def get_pending_wallet_payments(customer, exclude_invoice=None):
	"""
	Get total wallet payments from unconsolidated/pending POS invoices.
	"""
	filters = {
		"customer": customer,
		"docstatus": ["in", [0, 1]],
		"outstanding_amount": [">", 0],
		"is_pos": 1
	}

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=["name"]
	)

	pending_amount = 0.0

	for invoice in invoices:
		if exclude_invoice and invoice.name == exclude_invoice:
			continue

		payments = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": invoice.name},
			fields=["mode_of_payment", "amount"]
		)

		for payment in payments:
			is_wallet = frappe.db.get_value(
				"Mode of Payment", payment.mode_of_payment, "is_wallet_payment"
			)
			if is_wallet:
				pending_amount += flt(payment.amount)

	return pending_amount


@frappe.whitelist()
def get_customer_wallet(customer, company=None):
	"""Get wallet details for a customer."""
	filters = {"customer": customer}
	if company:
		filters["company"] = company

	wallet = frappe.db.get_value(
		"Wallet",
		filters,
		["name", "customer", "company", "account", "status", "current_balance"],
		as_dict=True
	)

	if wallet:
		# Update balance
		wallet["balance"] = get_customer_wallet_balance(customer, company)

	return wallet


def create_wallet_on_customer_insert(doc, method=None):
	"""Hook: after_insert on Customer. Creates a wallet for the default company
	only when auto_create_wallet is enabled in POS Settings."""
	company = frappe.get_cached_value("Global Defaults", "Global Defaults", "default_company")
	if not company:
		return

	# Only auto-create wallets when a POS profile with auto_create_wallet exists
	pos_profile = frappe.db.get_value(
		"POS Profile",
		{"company": company, "disabled": 0},
		"name"
	)
	if not pos_profile:
		return

	pos_settings = get_pos_settings(pos_profile)
	if not pos_settings or not cint(pos_settings.get("auto_create_wallet")):
		return

	try:
		get_or_create_wallet(doc.name, company, pos_settings=pos_settings)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Wallet auto-create failed for {doc.name}")


@frappe.whitelist()
def get_or_create_wallet(customer, company, pos_settings=None, force_create=False):
	"""Get existing wallet or create a new one."""

	# Check if wallet exists
	wallet = frappe.db.get_value(
		"Wallet",
		{"customer": customer, "company": company},
		["name", "customer", "company", "account", "status"],
		as_dict=True
	)

	if wallet:
		return wallet

	# Check if auto-create is enabled
	if not pos_settings:
		pos_profile = frappe.db.get_value(
			"POS Profile",
			{"company": company, "disabled": 0},
			"name"
		)
		if pos_profile:
			pos_settings = get_pos_settings(pos_profile)

	if not force_create and (not pos_settings or not cint(pos_settings.get("auto_create_wallet"))):
		return None

	# Get wallet account
	wallet_account = None
	if pos_settings:
		wallet_account = pos_settings.get("wallet_account")

	if not wallet_account:
		# Try to find a receivable account with 'wallet' in name
		wallet_account = frappe.db.get_value(
			"Account",
			{
				"company": company,
				"account_type": "Receivable",
				"is_group": 0,
				"name": ["like", "%wallet%"]
			},
			"name"
		)

	if not wallet_account:
		# Use default receivable account
		wallet_account = frappe.get_cached_value("Company", company, "default_receivable_account")

	if not wallet_account:
		frappe.log_error(
			f"Cannot create wallet for {customer}: No wallet account configured",
			"Wallet Creation Error"
		)
		return None

	# Create new wallet
	try:
		wallet_doc = frappe.get_doc({
			"doctype": "Wallet",
			"customer": customer,
			"company": company,
			"account": wallet_account,
			"status": "Active"
		})
		wallet_doc.insert(ignore_permissions=True)

		return wallet_doc

	except Exception as e:
		frappe.log_error(
			f"Failed to create wallet for {customer}: {str(e)}",
			"Wallet Creation Error"
		)
		return None


def get_pos_settings(pos_profile):
	"""Get POS Settings for a profile."""
	if not pos_profile:
		return None

	return frappe.db.get_value(
		"POS Settings",
		{"pos_profile": pos_profile},
		[
			"enable_loyalty_program",
			"default_loyalty_program",
			"wallet_account",
			"auto_create_wallet",
			"loyalty_to_wallet"
		],
		as_dict=True
	)


@frappe.whitelist()
def get_wallet_payment_methods(pos_profile):
	"""Get payment methods that are wallet-enabled for a POS profile."""
	payment_methods = frappe.get_all(
		"POS Payment Method",
		filters={"parent": pos_profile},
		fields=["mode_of_payment", "default"]
	)

	wallet_methods = []
	for method in payment_methods:
		is_wallet = frappe.db.get_value(
			"Mode of Payment",
			method.mode_of_payment,
			"is_wallet_payment"
		)
		if is_wallet:
			wallet_methods.append({
				"mode_of_payment": method.mode_of_payment,
				"default": method.default,
				"is_wallet_payment": True
			})

	return wallet_methods


@frappe.whitelist()
def get_wallet_info(customer, company, pos_profile=None):
	"""
	Get comprehensive wallet information for a customer.
	Used by POS frontend.
	"""
	result = {
		"wallet_enabled": False,
		"wallet_exists": False,
		"wallet_balance": 0.0,
		"wallet_account": None,
		"wallet_name": None,
		"auto_create": False,
		"loyalty_program": None,
		"loyalty_to_wallet": False
	}

	# Check if loyalty program is enabled in POS Settings
	if pos_profile:
		pos_settings = get_pos_settings(pos_profile)
		if pos_settings:
			result["wallet_enabled"] = cint(pos_settings.get("enable_loyalty_program"))
			result["wallet_account"] = pos_settings.get("wallet_account")
			result["auto_create"] = cint(pos_settings.get("auto_create_wallet"))
			result["loyalty_program"] = pos_settings.get("default_loyalty_program")
			result["loyalty_to_wallet"] = cint(pos_settings.get("loyalty_to_wallet"))

	if not result["wallet_enabled"]:
		return result

	# Get wallet details (support both pos_next and wallete status values)
	wallet = frappe.db.get_value(
		"Wallet",
		{"customer": customer, "company": company, "status": ["in", ["Active", "active"]]},
		["name", "account"],
		as_dict=True
	)

	if wallet:
		result["wallet_exists"] = True
		result["wallet_name"] = wallet.name
		result["wallet_balance"] = get_customer_wallet_balance(customer, company)
	elif result["auto_create"]:
		# Auto-create wallet for customer if enabled
		try:
			new_wallet = get_or_create_wallet(customer, company, pos_settings)
			if new_wallet:
				result["wallet_exists"] = True
				result["wallet_name"] = new_wallet.name if hasattr(new_wallet, 'name') else new_wallet.get("name")
				result["wallet_balance"] = 0.0  # New wallet starts with 0 balance
		except Exception as e:
			frappe.log_error(
				title="Auto-create Wallet Error",
				message=f"Customer: {customer}, Company: {company}, Error: {str(e)}"
			)

	return result


@frappe.whitelist()
def create_manual_wallet_credit(customer, company, amount, remarks=None):
	"""
	Create a manual wallet credit (for admin use).

	Args:
		customer: Customer ID
		company: Company
		amount: Amount to credit
		remarks: Optional remarks

	Returns:
		Wallet Transaction document name
	"""
	frappe.has_permission("Wallet Transaction", "create", throw=True)

	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	# Manual credits should be able to create wallets even when POS auto-create is disabled.
	wallet = get_or_create_wallet(customer, company, force_create=True)

	if not wallet:
		frappe.throw(_("Could not create wallet for customer {0}").format(customer))

	from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

	transaction = create_wallet_credit(
		wallet=wallet.name if hasattr(wallet, 'name') else wallet["name"],
		amount=amount,
		source_type="Manual Adjustment",
		remarks=remarks or _("Manual wallet credit"),
		submit=True
	)

	return transaction.name
