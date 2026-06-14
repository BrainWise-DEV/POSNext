# Copyright (c) 2024, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, today
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController
from pos_next.api.wallet import get_or_create_wallet

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
			source_gl = {
				"account": source_account,
				"debit": amount,
				"debit_in_account_currency": amount,
				"cost_center": cost_center,
				"remarks": self.remarks or _("Wallet Credit: {0}").format(self.name)
			}
			# Receivable/Payable accounts require party information
			if not hasattr(self, '_source_account_type'):
				self._source_account_type = frappe.get_cached_value("Account", source_account, "account_type")
			if self._source_account_type in ("Receivable", "Payable") and self.customer:
				source_gl["party_type"] = "Customer"
				source_gl["party"] = self.customer
			gl_entries.append(self.get_gl_dict(source_gl))
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
			debit_source_gl = {
				"account": source_account,
				"credit": amount,
				"credit_in_account_currency": amount,
				"cost_center": cost_center,
				"remarks": self.remarks or _("Wallet Debit: {0}").format(self.name)
			}
			# Receivable/Payable accounts require party information
			if not hasattr(self, '_source_account_type'):
				self._source_account_type = frappe.get_cached_value("Account", source_account, "account_type")
			if self._source_account_type in ("Receivable", "Payable") and self.customer:
				debit_source_gl["party_type"] = "Customer"
				debit_source_gl["party"] = self.customer
			gl_entries.append(self.get_gl_dict(debit_source_gl))

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
	wallet = get_or_create_wallet(customer, company, force_create=True)

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

def credit_return_to_wallet(return_invoice, amount=None):
	"""
	Create a Credit wallet transaction when "Add to Customer Credit Balance"
	is enabled on a return invoice.

	The return amount is credited to the customer's wallet instead of a cash refund.
	Works for both full and partial returns — the amount is taken from the
	return invoice's grand_total (absolute value) or can be explicitly passed.

	Args:
		return_invoice: Return Sales Invoice name (is_return=1)
		amount: Explicit credit amount (optional). If not provided,
				uses abs(return_invoice.grand_total).

	Returns:
		Wallet Transaction document or None
	"""
	return_data = frappe.db.get_value(
		"Sales Invoice",
		return_invoice,
		["customer", "company", "grand_total", "is_return", "return_against"],
		as_dict=True,
	)

	if not return_data or not return_data.is_return:
		frappe.log_error(
			title="Wallet Credit on Return Error",
			message=f"Invoice {return_invoice} is not a return invoice"
		)
		return None

	customer = return_data.customer
	company = return_data.company

	# Determine credit amount: explicit amount or absolute grand_total
	credit_amount = flt(amount) if amount else abs(flt(return_data.grand_total))

	if credit_amount <= 0:
		return None

	# Get or create customer wallet
	wallet = get_or_create_wallet(customer, company, force_create=True)

	if not wallet:
		frappe.log_error(
			title="Wallet Credit on Return Error",
			message=f"Could not get or create wallet for customer {customer}, company {company}"
		)
		return None

	# Determine source account — use company's default receivable account for refunds
	source_account = frappe.get_cached_value("Company", company, "default_receivable_account")

	if not source_account:
		frappe.log_error(
			title="Wallet Credit on Return Error",
			message=f"No default receivable account for company {company}"
		)
		return None

	# Idempotency guard: if submit_invoice is retried for the same return invoice,
	# reuse the existing wallet credit transaction instead of creating duplicates.
	existing_transaction_name = frappe.db.get_value(
		"Wallet Transaction",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": return_invoice,
			"transaction_type": "Credit",
			"source_type": "Refund",
			"docstatus": ["!=", 2],
		},
		"name",
	)
	if existing_transaction_name:
		existing_transaction = frappe.get_doc("Wallet Transaction", existing_transaction_name)
		if existing_transaction.docstatus == 0:
			# Recover stuck draft created by a crashed prior attempt.
			existing_transaction.flags.ignore_permissions = True
			existing_transaction.submit()
			return existing_transaction

		if existing_transaction.docstatus == 1:
			# Check if GL entries exist — a previous attempt may have set docstatus=1
			# but failed during make_gl_entries(), leaving a broken transaction.
			has_gl = frappe.db.exists("GL Entry", {"voucher_no": existing_transaction.name})
			if has_gl:
				return existing_transaction
			# No GL entries → broken submission. Cancel and recreate below.
			# NOTE: We intentionally do NOT call frappe.db.commit() here so
			# the cancellation stays within the caller's transaction boundary
			# and can be rolled back if the subsequent re-creation fails.
			try:
				existing_transaction.flags.ignore_permissions = True
				existing_transaction.cancel()
			except Exception:
				frappe.log_error(
					title="Wallet Transaction Recovery Error",
					message=f"Could not cancel broken WT {existing_transaction.name}: {frappe.get_traceback()}"
				)
				return None

	transaction = frappe.get_doc({
		"doctype": "Wallet Transaction",
		"transaction_type": "Credit",
		"wallet": wallet["name"],
		"company": company,
		"posting_date": today(),
		"amount": credit_amount,
		"source_type": "Refund",
		"source_account": source_account,
		"reference_doctype": "Sales Invoice",
		"reference_name": return_invoice,
		"remarks": _("Return credit to wallet for {0} against {1}: {2}").format(
			return_invoice,
			return_data.return_against or "",
			frappe.format_value(credit_amount, {"fieldtype": "Currency"})
		)
	})
	transaction.flags.ignore_permissions = True
	transaction.insert(ignore_permissions=True)
	transaction.submit()

	frappe.msgprint(
		_("Credited {0} to customer wallet for return {1}").format(
			frappe.format_value(credit_amount, {"fieldtype": "Currency"}),
			return_invoice
		),
		alert=True, indicator="green"
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

	existing = frappe.db.exists("Wallet Transaction", {
		"reference_doctype": "Sales Invoice",
		"reference_name": return_invoice,
		"transaction_type": "Debit",
		"source_type": "Refund",
		"docstatus": ["!=", 2],
	})
	if existing:
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

	# return grand_total is negative, original is positive
	original_total = abs(flt(original_doc.grand_total))
	returned_amount = abs(flt(return_doc.grand_total))

	if original_total <= 0:
		return

	# Check if this is a full return
	# Keep full precision for ratio; only round the final reverse_amount
	return_ratio = returned_amount / original_total
	is_full_return = return_ratio >= 0.999  # Allow small rounding tolerance

	# Get loyalty program details for tier-aware reversal of Loyalty Credit.
	# Supports both "Single Tier Program" (one rule) and "Multiple Tier Program" (many rules).
	# Original credit: points = int(eligible_amount / collection_factor), wallet = points * conversion_factor
	loyalty_program = frappe.db.get_value("Customer", original_doc.customer, "loyalty_program")

	tiers = []
	conversion_factor = 1.0
	if loyalty_program:
		lp_doc = frappe.get_doc("Loyalty Program", loyalty_program)
		conversion_factor = flt(lp_doc.conversion_factor) or 1.0
		tiers = sorted(
			[d.as_dict() for d in lp_doc.collection_rules],
			key=lambda r: flt(r.get("min_spent")),
		)

	invoiced_amount_after_return = flt(original_total) - flt(returned_amount)

	def _find_tier(amount):
		"""Return the highest tier whose min_spent <= amount, or None."""
		matched = None
		for t in tiers:
			if flt(amount) >= flt(t.get("min_spent")):
				matched = t
		return matched

	# Determine the applicable tier for the post-return effective amount
	new_tier = _find_tier(invoiced_amount_after_return) if tiers else None

	for wt in wallet_transactions:
		# ── Decide: cancel entirely  OR  create a partial Debit ──
		should_cancel = False
		reverse_amount = 0

		if is_full_return:
			should_cancel = True

		elif wt.transaction_type == "Loyalty Credit" and tiers:
			# Tier-aware reversal for Loyalty Credit
			if not new_tier:
				# Post-return amount below the lowest tier's min_spent → reverse ALL
				should_cancel = True
			else:
				# Recalculate what the credit should be for the post-return amount
				new_cf = flt(new_tier.get("collection_factor")) or 1.0
				recalculated_points = int(flt(invoiced_amount_after_return) / new_cf)
				recalculated_credit = flt(recalculated_points) * flt(conversion_factor)
				reverse_amount = flt(flt(wt.amount) - recalculated_credit, 2)

				if flt(reverse_amount) >= flt(wt.amount):
					# Recalculated credit is zero or negative → cancel entirely
					should_cancel = True
					reverse_amount = 0

		else:
			# Regular Credit (or Loyalty Credit without tiers) → proportional reversal
			reverse_amount = flt(wt.amount * return_ratio, 2)

		# ── Execute the reversal ──
		if should_cancel:
			try:
				wt_doc = frappe.get_doc("Wallet Transaction", wt.name)
				wt_doc.flags.ignore_permissions = True
				wt_doc.cancel()
				frappe.msgprint(
					_("Cancelled Wallet Transaction {0} due to return").format(wt.name),
					alert=True, indicator="blue"
				)
			except Exception as e:
				frappe.log_error(
					title="Wallet Transaction Cancel on Return Error",
					message=f"WT: {wt.name}, Return: {return_invoice}, Error: {str(e)}\n{frappe.get_traceback()}"
				)

		elif reverse_amount > 0:
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
					"remarks": _("Wallet reversal for return {0} against {1}: returned {2}, reversed {3}").format(
						return_invoice, original_invoice,
						frappe.format_value(returned_amount, {"fieldtype": "Currency"}),
						frappe.format_value(reverse_amount, {"fieldtype": "Currency"})
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
					title="Wallet Transaction Reverse on Partial Return Error",
					message=(
						f"WT: {wt.name}, Return: {return_invoice}, "
						f"Original: {original_invoice}, Reverse Amount: {reverse_amount}, "
						f"Error: {str(e)}\n{frappe.get_traceback()}"
					)
				)
