# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.accounts.utils import get_balance_on


class Wallet(Document):
	def validate(self):
		self.validate_account_type()
		self.validate_duplicate_wallet()

	def validate_account_type(self):
		"""Wallet account must be a Receivable account"""
		if self.account:
			account_type = frappe.get_value("Account", self.account, "account_type")
			if account_type != "Receivable":
				frappe.throw(_("Wallet Account must be a Receivable type account"))

	def validate_duplicate_wallet(self):
		"""Check for duplicate wallet for same customer and company"""
		if not self.is_new():
			return
		existing = frappe.db.exists(
			"Wallet",
			{"customer": self.customer, "company": self.company, "name": ("!=", self.name)}
		)
		if existing:
			frappe.throw(_("A wallet already exists for customer {0} in company {1}").format(
				self.customer, self.company
			))

	def get_balance(self):
		"""Get current wallet balance from GL entries.

		For receivable accounts:
		- Negative balance = customer has credit (we owe them) = positive wallet balance
		- Positive balance = customer owes us = negative wallet balance (shouldn't happen)
		"""
		if not self.account or not self.customer:
			return 0.0

		balance = get_balance_on(
			account=self.account,
			party_type="Customer",
			party=self.customer
		)
		# Negate because negative receivable balance = positive wallet credit
		return -flt(balance)

	def get_available_balance(self):
		"""Get available balance (current balance minus pending wallet payments)"""
		current = self.get_balance()
		pending = get_pending_wallet_payments(self.customer)
		available = flt(current) - flt(pending)
		return available if available > 0 else 0.0

	def update_balance(self):
		"""Update the current_balance and available_balance fields"""
		self.current_balance = self.get_balance()
		self.available_balance = self.get_available_balance()
		self.db_set("current_balance", self.current_balance, update_modified=False)
		self.db_set("available_balance", self.available_balance, update_modified=False)


@frappe.whitelist()
def get_customer_wallet(customer, company=None):
	"""Get wallet for a customer"""
	filters = {"customer": customer}
	if company:
		filters["company"] = company

	wallet = frappe.db.get_value(
		"Wallet",
		filters,
		["name", "customer", "company", "account", "status"],
		as_dict=True
	)

	return wallet


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
	This prevents double-spending of wallet balance.
	"""
	# Get open Sales Invoices (draft or unconsolidated POS invoices)
	filters = {
		"customer": customer,
		"docstatus": ["in", [0, 1]],  # Draft or Submitted
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

		# Get wallet payments from this invoice
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
def create_customer_wallet(customer, company, account=None):
	"""
	Create a wallet for a customer.

	Args:
		customer: Customer ID
		company: Company
		account: Wallet account (optional, will use default if not provided)

	Returns:
		Wallet document
	"""
	# Check if wallet already exists
	existing = frappe.db.exists("Wallet", {"customer": customer, "company": company})
	if existing:
		return frappe.get_doc("Wallet", existing)

	# Get default wallet account if not provided
	if not account:
		account = get_default_wallet_account(company)

	if not account:
		frappe.throw(_("Please configure a default wallet account for company {0}").format(company))

	wallet = frappe.get_doc({
		"doctype": "Wallet",
		"customer": customer,
		"company": company,
		"account": account,
		"status": "Active"
	})
	wallet.insert(ignore_permissions=True)

	return wallet


def get_default_wallet_account(company):
	"""Get default wallet account for a company"""
	# Try to get from POS Settings
	wallet_account = frappe.db.get_value(
		"POS Settings",
		{"company": company},
		"wallet_account"
	)

	if wallet_account:
		return wallet_account

	# Fallback: Find a receivable account with 'wallet' in the name
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

	return wallet_account


@frappe.whitelist()
def get_or_create_wallet(customer, company):
	"""Get existing wallet or create a new one"""
	wallet = get_customer_wallet(customer, company)

	if not wallet:
		wallet_doc = create_customer_wallet(customer, company)
		wallet = {
			"name": wallet_doc.name,
			"customer": wallet_doc.customer,
			"company": wallet_doc.company,
			"account": wallet_doc.account,
			"status": wallet_doc.status
		}

	return wallet
