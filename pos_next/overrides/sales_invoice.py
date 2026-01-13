# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Sales Invoice Override
Handles wallet payments that require party information for Receivable accounts.

"""

import frappe
from frappe.utils import cint, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.accounts.utils import get_account_currency


class CustomSalesInvoice(SalesInvoice):
	"""
	Custom Sales Invoice class that handles wallet payments correctly.

	When a wallet payment is made using a Receivable account, ERPNext requires
	party information in the GL entry. This override adds party_type and party
	for wallet payment methods marked with is_wallet_payment.
	"""

	def make_pos_gl_entries(self, gl_entries):
		"""
		Override to add party information for wallet payment accounts.

		The standard ERPNext implementation doesn't set party_type/party for
		payment mode accounts, which causes validation errors for Receivable
		accounts (like wallet accounts).
		"""
		if cint(self.is_pos):
			skip_change_gl_entries = not cint(
				frappe.db.get_single_value("Accounts Settings", "post_change_gl_entries")
			)

			for payment_mode in self.payments:
				if skip_change_gl_entries and payment_mode.account == self.account_for_change_amount:
					payment_mode.base_amount -= flt(self.change_amount)

				if payment_mode.amount:
					# POS, make payment entries
					# Credit entry to debit_to (customer receivable)
					gl_entries.append(
						self.get_gl_dict(
							{
								"account": self.debit_to,
								"party_type": "Customer",
								"party": self.customer,
								"against": payment_mode.account,
								"credit": payment_mode.base_amount,
								"credit_in_account_currency": payment_mode.base_amount
								if self.party_account_currency == self.company_currency
								else payment_mode.amount,
								"against_voucher": self.return_against
								if cint(self.is_return) and self.return_against
								else self.name,
								"against_voucher_type": self.doctype,
								"cost_center": self.cost_center,
							},
							self.party_account_currency,
							item=self,
						)
					)

					# Debit entry to payment mode account
					payment_mode_account_currency = get_account_currency(payment_mode.account)

					# Get party info for wallet payments
					party_type, party = self.get_party_and_party_type_for_pos_gl_entry(
						payment_mode.mode_of_payment, payment_mode.account
					)

					gl_entries.append(
						self.get_gl_dict(
							{
								"account": payment_mode.account,
								"party_type": party_type,
								"party": party,
								"against": self.customer,
								"debit": payment_mode.base_amount,
								"debit_in_account_currency": payment_mode.base_amount
								if payment_mode_account_currency == self.company_currency
								else payment_mode.amount,
								"cost_center": self.cost_center,
							},
							payment_mode_account_currency,
							item=self,
						)
					)

			if not skip_change_gl_entries:
				self.make_gle_for_change_amount(gl_entries)

	def get_party_and_party_type_for_pos_gl_entry(self, mode_of_payment, account):
		"""
		Get party type and party for wallet payment GL entries.

		For wallet payments (Mode of Payment with is_wallet_payment=1),
		returns Customer as party_type and the invoice customer as party.
		For regular payments, returns empty strings.
		"""
		is_wallet_mode_of_payment = frappe.db.get_value(
			"Mode of Payment", mode_of_payment, "is_wallet_payment"
		)

		party_type, party = "", ""
		if is_wallet_mode_of_payment:
			party_type, party = "Customer", self.customer

		return party_type, party
