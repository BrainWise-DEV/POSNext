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


def _find_paid_bundle_row_for_free(si_doc, free_row):
	"""Pick the paid SI item row whose bundle qty should absorb this free bundle's packed items."""
	candidates = []
	for row in si_doc.get("items"):
		if row.name == free_row.name or cint(row.is_free_item):
			continue
		if row.item_code != free_row.item_code:
			continue
		if (row.warehouse or "") != (free_row.warehouse or ""):
			continue
		candidates.append(row)
	if not candidates:
		return None
	free_idx = free_row.idx or 0
	before = [r for r in candidates if (r.idx or 0) < free_idx]
	if before:
		return max(before, key=lambda r: r.idx or 0)
	return candidates[0]


def _find_matching_packed_item_for_merge(si_doc, paid_row, component_item_code, warehouse):
	"""Match a packed item on the paid bundle line; prefer same warehouse."""
	w = warehouse or ""
	matches = []
	for pi in si_doc.get("packed_items"):
		if pi.parent_detail_docname != paid_row.name:
			continue
		if pi.parent_item != paid_row.item_code:
			continue
		if pi.item_code != component_item_code:
			continue
		matches.append(pi)
	if not matches:
		return None
	for pi in matches:
		if (pi.warehouse or "") == w:
			return pi
	return matches[0]


def _get_post_change_gl_entries_setting():
	"""
	Get post_change_gl_entries setting compatible with ERPNext v15 and v16.

	- ERPNext v15: Field is in 'Accounts Settings'
	- ERPNext v16: Field moved to ERPNext's 'POS Settings' (singleton)

	Since pos_next has its own 'POS Settings' doctype (non-singleton) that overrides
	ERPNext's, we read directly from the Singles table for v16 compatibility.

	Returns:
		int: 1 if post_change_gl_entries is enabled, 0 otherwise (default: 0)
	"""
	# Check if field exists in Accounts Settings schema (v15)
	meta = frappe.get_meta("Accounts Settings")
	if meta.has_field("post_change_gl_entries"):
		value = frappe.db.get_single_value("Accounts Settings", "post_change_gl_entries")
		return cint(value) if value is not None else 0

	# For v16, read directly from Singles table using Query Builder to avoid ORM issues
	# ERPNext's POS Settings is a singleton, data stored in Singles table
	Singles = frappe.qb.DocType("Singles")
	result = (
		frappe.qb.from_(Singles)
		.select(Singles.value)
		.where(Singles.doctype == "POS Settings")
		.where(Singles.field == "post_change_gl_entries")
		.limit(1)
		.run()
	)
	return cint(result[0][0]) if result else 0

class CustomSalesInvoice(SalesInvoice):
	"""
	Custom Sales Invoice class that handles wallet payments correctly.

	When a wallet payment is made using a Receivable account, ERPNext requires
	party information in the GL entry. This override adds party_type and party
	for wallet payment methods marked with is_wallet_payment.
	"""

	def validate(self):
		"""
		Validate and correct debit_to account if it's not a valid Receivable/Payable account.
		"""
		# Check if debit_to is a valid Receivable/Payable account
		if self.debit_to:
			debit_to_account_type = frappe.db.get_value(
				"Account", self.debit_to, "account_type"
			)
			# If it's not Receivable/Payable, use the company default
			if debit_to_account_type not in ("Receivable", "Payable"):
				correct_account = frappe.db.get_value(
					"Company", self.company, "default_receivable_account"
				)
				if correct_account:
					self.debit_to = correct_account

		# Call parent validate
		super().validate()

	def make_pos_gl_entries(self, gl_entries):
		"""
		Override to add party information for wallet payment accounts.

		The standard ERPNext implementation doesn't set party_type/party for
		payment mode accounts, which causes validation errors for Receivable
		accounts (like wallet accounts).
		"""
		if cint(self.is_pos):
			skip_change_gl_entries = not _get_post_change_gl_entries_setting()

			# Ensure debit_to is a valid Receivable account
			# If it's not Receivable/Payable, try to find the correct one
			debit_to = self.debit_to
			debit_to_account_type = frappe.db.get_value(
				"Account", debit_to, "account_type"
			)
			
			if debit_to_account_type not in ("Receivable", "Payable"):
				# Try to use company default receivable account
				correct_account = frappe.db.get_value(
					"Company", self.company, "default_receivable_account"
				)
				if correct_account:
					debit_to = correct_account
					debit_to_account_type = "Receivable"

			for payment_mode in self.payments:
				if skip_change_gl_entries and payment_mode.account == self.account_for_change_amount:
					payment_mode.base_amount -= flt(self.change_amount)

				if payment_mode.amount:
					# POS, make payment entries
					# Credit entry to debit_to (customer receivable)
					credit_entry = {
						"account": debit_to,
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
					}
					# Only set party info if debit_to is a Receivable/Payable account
					if debit_to_account_type in ("Receivable", "Payable"):
						credit_entry["party_type"] = "Customer"
						credit_entry["party"] = self.customer

					gl_entries.append(
						self.get_gl_dict(
							credit_entry,
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

					debit_entry = {
						"account": payment_mode.account,
						"against": self.customer,
						"debit": payment_mode.base_amount,
						"debit_in_account_currency": payment_mode.base_amount
						if payment_mode_account_currency == self.company_currency
						else payment_mode.amount,
						"cost_center": self.cost_center,
					}
					# Only add party info if this is a wallet payment and account is Receivable/Payable
					payment_mode_account_type = frappe.db.get_value(
						"Account", payment_mode.account, "account_type"
					)
					if party_type and payment_mode_account_type in ("Receivable", "Payable"):
						debit_entry["party_type"] = party_type
						debit_entry["party"] = party

					gl_entries.append(
						self.get_gl_dict(
							debit_entry,
							payment_mode_account_currency,
							item=self,
						)
					)

			if not skip_change_gl_entries:
				if hasattr(self, "get_gle_for_change_amount"):
					# ERPNext v16+: Method renamed and returns a list of GL entries
					# that needs to be extended to the main gl_entries list
					gl_entries.extend(self.get_gle_for_change_amount())
				else:
					# ERPNext v15: Method takes gl_entries as parameter
					# and appends change amount entries directly to it
					self.make_gle_for_change_amount(gl_entries)

	def validate_pos_paid_amount(self):
		"""
		Allow pure customer-credit POS sales to submit without a payment row.

		POSNext redeems customer credit after submit through Journal Entries /
		Payment Entry allocation, so there is no real Mode of Payment row to send.
		Only bypass the core POS payment-row check when submit_invoice has explicitly
		marked the document for customer-credit redemption.
		"""
		if getattr(self.flags, "pos_next_redeemed_customer_credit", 0):
			if len(self.payments) == 0 and cint(self.is_pos) and flt(self.grand_total) > 0:
				return

		super().validate_pos_paid_amount()

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

	def update_packing_list(self):
		super().update_packing_list()
		self._combine_packed_qty_for_free_product_bundles()
		self._set_use_serial_batch_fields_on_packed_items()

	def _set_use_serial_batch_fields_on_packed_items(self):
		"""
		Force packed_items for batch/serial-tracked Items to use legacy fields path.

		ERPNext's auto-SBB creation during SLE.on_submit fails to link the bundle
		because SBB.voucher_detail_no gets remapped to the parent SI Item row name
		(set_serial_and_batch_values) while validation expects either a matching SLE
		or a Packed Item with that name. Routing through use_serial_batch_fields=1
		bypasses the broken auto-creation for the row.
		"""
		if not self.get("packed_items"):
			return
		for pi in self.get("packed_items"):
			if pi.get("serial_and_batch_bundle"):
				continue
			tracking = frappe.get_cached_value(
				"Item",
				pi.item_code,
				["has_batch_no", "has_serial_no"],
				as_dict=True,
			)
			if not tracking:
				continue
			if tracking.has_batch_no or tracking.has_serial_no:
				pi.use_serial_batch_fields = 1

	def _combine_packed_qty_for_free_product_bundles(self):
		"""
		Merge packed_items from free bundle lines into the matching paid bundle line.

		ERPNext builds packed rows per Sales Invoice Item row. For BOGO / pricing-rule
		free rows, the same product bundle often appears twice (paid + is_free_item).
		That duplicates component rows. Stock and picking should follow total bundle
		qty on one set of packed lines tied to the paid row.
		"""
		if self.is_return or not self.get("packed_items"):
			return

		free_bundle_rows = [
			row
			for row in self.get("items")
			if row.item_code and cint(row.is_free_item) and self.has_product_bundle(row.item_code)
		]
		if not free_bundle_rows:
			return

		for free_row in free_bundle_rows:
			paid_row = _find_paid_bundle_row_for_free(self, free_row)
			if not paid_row:
				continue

			to_remove = []
			for pi in list(self.get("packed_items")):
				if pi.parent_detail_docname != free_row.name or pi.parent_item != free_row.item_code:
					continue
				tgt = _find_matching_packed_item_for_merge(self, paid_row, pi.item_code, pi.warehouse)
				if tgt:
					prec = tgt.precision("qty")
					tgt.qty = flt(flt(tgt.qty) + flt(pi.qty), prec)
					to_remove.append(pi)

			for pi in to_remove:
				self.remove(pi)
