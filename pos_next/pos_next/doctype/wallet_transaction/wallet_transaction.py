# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, today
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController


class WalletTransaction(AccountsController):
	def validate(self):
		self.validate_wallet()
		self.validate_amount()
		self.set_customer_from_wallet()

	def validate_wallet(self):
		"""Validate wallet exists and is active"""
		if not self.wallet:
			frappe.throw(_("Wallet is required"))

		wallet_status = frappe.db.get_value("Wallet", self.wallet, "status")
		if wallet_status != "Active":
			frappe.throw(_("Wallet {0} is not active").format(self.wallet))

	def validate_amount(self):
		"""Validate amount is positive"""
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

		# For debit transactions, check if sufficient balance
		if self.transaction_type == "Debit":
			from pos_next.pos_next.doctype.wallet.wallet import get_customer_wallet_balance
			balance = get_customer_wallet_balance(self.customer, self.company)
			if flt(self.amount) > flt(balance):
				frappe.throw(
					_("Insufficient wallet balance. Available: {0}, Requested: {1}").format(
						frappe.format_value(balance, {"fieldtype": "Currency"}),
						frappe.format_value(self.amount, {"fieldtype": "Currency"})
					)
				)

	def set_customer_from_wallet(self):
		"""Fetch customer from wallet"""
		if self.wallet and not self.customer:
			self.customer = frappe.db.get_value("Wallet", self.wallet, "customer")

	def on_submit(self):
		"""Create GL entries on submit"""
		self.make_gl_entries()
		self.update_wallet_balance()

	def on_cancel(self):
		"""Reverse GL entries on cancel"""
		self.ignore_linked_doctypes = (
        "GL Entry",
		"Payment Ledger Entry"
    	)
		self.make_gl_entries(cancel=True)
		self.update_wallet_balance()

	def update_wallet_balance(self):
		"""Update the wallet's current balance"""
		wallet_doc = frappe.get_doc("Wallet", self.wallet)
		wallet_doc.update_balance()

	def make_gl_entries(self, cancel=False):
		"""Create GL entries for wallet transaction"""
		gl_entries = self.build_gl_entries()

		if gl_entries:
			make_gl_entries(
				gl_entries,
				cancel=cancel,
				update_outstanding="Yes",
				merge_entries=frappe.db.get_single_value(
					"Accounts Settings", "merge_similar_account_heads"
				)
			)

	def build_gl_entries(self):
		"""Build GL entry list based on transaction type"""
		gl_entries = []

		wallet_account = frappe.db.get_value("Wallet", self.wallet, "account")
		if not wallet_account:
			frappe.throw(_("Wallet {0} does not have an account configured").format(self.wallet))

		# Get source account based on source type
		source_account = self.get_source_account()

		if not source_account:
			frappe.throw(_("Source account is required for wallet transaction"))

		cost_center = self.cost_center or frappe.get_cached_value(
			"Company", self.company, "cost_center"
		)

		amount = flt(self.amount, self.precision("amount"))

		if self.transaction_type in ["Credit", "Loyalty Credit"]:
			# Credit to wallet (increase balance)
			# Debit source account, Credit wallet account (with party)
			gl_entries.append(
				self.get_gl_dict({
					"account": source_account,
					"debit": amount,
					"debit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Credit: {0}").format(self.name)
				})
			)
			gl_entries.append(
				self.get_gl_dict({
					"account": wallet_account,
					"party_type": "Customer",
					"party": self.customer,
					"credit": amount,
					"credit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Credit: {0}").format(self.name)
				})
			)

		elif self.transaction_type == "Debit":
			# Debit from wallet (decrease balance)
			# Debit wallet account (with party), Credit source account
			gl_entries.append(
				self.get_gl_dict({
					"account": wallet_account,
					"party_type": "Customer",
					"party": self.customer,
					"debit": amount,
					"debit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Debit: {0}").format(self.name)
				})
			)
			gl_entries.append(
				self.get_gl_dict({
					"account": source_account,
					"credit": amount,
					"credit_in_account_currency": amount,
					"cost_center": cost_center,
					"remarks": self.remarks or _("Wallet Debit: {0}").format(self.name)
				})
			)

		return gl_entries

	def get_source_account(self):
		"""Get source account based on source type"""
		if self.source_account:
			return self.source_account

		if self.source_type == "Mode of Payment" and self.source_account:
			return self.source_account

		if self.source_type == "Loyalty Program":
			# Get loyalty expense account from loyalty program or company
			loyalty_account = frappe.db.get_value(
				"Loyalty Program",
				{"company": self.company},
				"expense_account"
			)
			if loyalty_account:
				return loyalty_account

			# Fallback to company's default expense account
			return frappe.get_cached_value("Company", self.company, "default_expense_account")

		if self.source_type == "Refund":
			# Use company's default receivable account
			return frappe.get_cached_value("Company", self.company, "default_receivable_account")

		if self.source_type == "Manual Adjustment":
			# Use company's adjustment account or default expense
			return frappe.get_cached_value("Company", self.company, "default_expense_account")

		return None


@frappe.whitelist()
def create_wallet_credit(wallet, amount, source_type="Manual Adjustment", remarks=None,
						 reference_doctype=None, reference_name=None, submit=True):
	"""
	Create a wallet credit transaction.

	Args:
		wallet: Wallet name
		amount: Amount to credit
		source_type: Source of credit (Manual Adjustment, Loyalty Program, Refund)
		remarks: Transaction remarks
		reference_doctype: Reference document type
		reference_name: Reference document name
		submit: Whether to submit the transaction

	Returns:
		Wallet Transaction document
	"""
	wallet_doc = frappe.get_doc("Wallet", wallet)

	# Get source account based on source type
	source_account = None
	if source_type == "Loyalty Program":
		loyalty_program = frappe.db.get_value(
			"Loyalty Program",
			{"company": wallet_doc.company},
			"name"
		)
		if loyalty_program:
			source_account = frappe.db.get_value(
				"Loyalty Program", loyalty_program, "expense_account"
			)

	if not source_account:
		source_account = frappe.get_cached_value(
			"Company", wallet_doc.company, "default_expense_account"
		)

	transaction = frappe.get_doc({
		"doctype": "Wallet Transaction",
		"transaction_type": "Loyalty Credit" if source_type == "Loyalty Program" else "Credit",
		"wallet": wallet,
		"company": wallet_doc.company,
		"posting_date": today(),
		"amount": amount,
		"source_type": source_type,
		"source_account": source_account,
		"remarks": remarks,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name
	})

	transaction.insert(ignore_permissions=True)

	if submit:
		transaction.submit()

	return transaction


@frappe.whitelist()
def credit_loyalty_points_to_wallet(customer, company, loyalty_points, conversion_factor=None):
	"""
	Convert loyalty points to wallet credit.

	Args:
		customer: Customer ID
		company: Company
		loyalty_points: Number of loyalty points to convert
		conversion_factor: Points to currency conversion (optional, fetched from program if not provided)

	Returns:
		Wallet Transaction document or None
	"""
	if flt(loyalty_points) <= 0:
		return None

	# Get conversion factor from loyalty program if not provided
	if not conversion_factor:
		loyalty_program = frappe.db.get_value("Customer", customer, "loyalty_program")
		if loyalty_program:
			conversion_factor = frappe.db.get_value(
				"Loyalty Program", loyalty_program, "conversion_factor"
			)

	if not conversion_factor:
		conversion_factor = 1.0  # Default: 1 point = 1 currency

	# Calculate wallet credit amount
	credit_amount = flt(loyalty_points) * flt(conversion_factor)

	if credit_amount <= 0:
		return None

	# Get or create customer wallet
	from pos_next.pos_next.doctype.wallet.wallet import get_or_create_wallet
	wallet = get_or_create_wallet(customer, company)

	# Create wallet credit transaction
	transaction = create_wallet_credit(
		wallet=wallet["name"],
		amount=credit_amount,
		source_type="Loyalty Program",
		remarks=_("Loyalty points conversion: {0} points = {1}").format(
			loyalty_points,
			frappe.format_value(credit_amount, {"fieldtype": "Currency"})
		),
		submit=True
	)

	return transaction

@frappe.whitelist()
def reverse_wallet_transactions_for_return(original_invoice, return_invoice):
    """
    Reverse wallet transactions linked to the original invoice when a return is made.
    
    For full returns: Cancel the linked Wallet Transaction(s)
    For partial returns: Create a proportional Debit transaction to reverse the credit
    
    Args:
        original_invoice: Original Sales Invoice name
        return_invoice: Return Sales Invoice name (is_return=1)
    """
    # Get the return invoice to calculate return ratio
    return_doc = frappe.get_doc("Sales Invoice", return_invoice)
    original_doc = frappe.get_doc("Sales Invoice", original_invoice)
    
    if not return_doc.is_return or return_doc.return_against != original_invoice:
        return
    
    # Find all submitted Wallet Transactions linked to the original invoice
    wallet_transactions = frappe.get_all(
        "Wallet Transaction",
        filters={
            "reference_doctype": "Sales Invoice",
            "reference_name": original_invoice,
            "docstatus": 1,
            "transaction_type": ["in", ["Credit", "Loyalty Credit"]]
        },
        fields=["name", "wallet", "amount", "transaction_type", "source_type",
                "source_account", "company", "customer"]
    )
    
    if not wallet_transactions:
        return
    
    # Calculate return ratio based on grand_total
    # return grand_total is negative, original is positive
    original_total = abs(flt(original_doc.grand_total))
    return_total = abs(flt(return_doc.grand_total))
    
    if original_total <= 0:
        return
    
    # Check if this is a full return (all items returned)
    return_ratio = flt(return_total / original_total, 2)
    is_full_return = return_ratio >= 0.999  # Allow small rounding tolerance
    
    for wt in wallet_transactions:
        if is_full_return:
            # Full return - cancel the wallet transaction
            try:
                wt_doc = frappe.get_doc("Wallet Transaction", wt.name)
                wt_doc.flags.ignore_permissions = True
                wt_doc.cancel()
                frappe.msgprint(
                    _("Cancelled Wallet Transaction {0} due to full return").format(wt.name),
                    alert=True, indicator="blue"
                )
            except Exception as e:
                frappe.log_error(
                    title="Wallet Transaction Cancel on Return Error",
                    message=f"WT: {wt.name}, Return: {return_invoice}, Error: {str(e)}\n{frappe.get_traceback()}"
                )
        else:
            # Partial return - create a proportional debit (reverse) transaction
            reverse_amount = flt(wt.amount * return_ratio, 2)
            
            if reverse_amount <= 0:
                continue
            
            try:
                reverse_wt = frappe.get_doc({
                    "doctype": "Wallet Transaction",
                    "transaction_type": "Debit",
                    "wallet": wt.wallet,
                    "company": wt.company,
                    "posting_date": today(),
                    "amount": reverse_amount,
                    "source_type": "Refund",
                    "source_account": wt.source_account,
                    "reference_doctype": "Sales Invoice",
                    "reference_name": return_invoice,
                    "remarks": _("Wallet reversal for return {0} against {1} (ratio: {2}%)").format(
                        return_invoice, original_invoice, round(return_ratio * 100, 1)
                    )
                })
                reverse_wt.flags.ignore_permissions = True
                reverse_wt.insert()
                reverse_wt.submit()
                
                frappe.msgprint(
                    _("Created wallet debit of {0} for partial return {1}").format(
                        frappe.format_value(reverse_amount, {"fieldtype": "Currency"}),
                        return_invoice
                    ),
                    alert=True, indicator="blue"
                )
            except Exception as e:
                frappe.log_error(
                    title="Wallet Reversal on Partial Return Error",
                    message=f"Original WT: {wt.name}, Return: {return_invoice}, "
                            f"Amount: {reverse_amount}, Error: {str(e)}\n{frappe.get_traceback()}"
                )