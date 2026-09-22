# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Credit Sales API
Handles credit sale operations including:
- Getting available customer credit
- Credit redemption and allocation
- Journal Entry creation for GL posting
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, nowdate, today


PAYMENT_HUB_CUSTOMER_CREDIT_MODE = "POSNext Customer Credit"
PAYMENT_HUB_MANUAL_CHANNEL = "Manual / Non-Cash"


@frappe.whitelist()
def get_customer_balance(customer, company=None):
	"""Return the customer's live receivable/credit position.

	Credit is determined from the document that *actually* carries a negative
	outstanding balance. For standalone returns that is normally the return Sales
	Invoice; for linked ERPNext returns (``update_outstanding_for_self = 0``) it
	can be the original Sales Invoice. Restricting credit to ``is_return = 1``
	therefore hides valid linked-return credit and is not safe.

	Unallocated customer advances are included as available credit so this summary
	stays consistent with :func:`get_available_credit`.
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	try:
		filters = {"customer": customer, "docstatus": 1}
		if company:
			filters["company"] = company

		rows = frappe.get_all(
			"Sales Invoice",
			filters=filters,
			fields=["is_return", "outstanding_amount"],
		)

		# Net every submitted receivable reference exactly as ERPNext currently
		# carries it. Positive outstanding on a return is unusual, but can exist on
		# legacy/broken linked-return allocations; counting it here safely offsets
		# the corresponding negative original-invoice balance and prevents phantom
		# spendable credit.
		total_outstanding = sum(
			flt(row.outstanding_amount)
			for row in rows
			if flt(row.outstanding_amount) > 0
		)
		invoice_credit = sum(
			abs(flt(row.outstanding_amount))
			for row in rows
			if flt(row.outstanding_amount) < 0
		)

		advance_filters = {
			"party": customer,
			"party_type": "Customer",
			"payment_type": "Receive",
			"docstatus": 1,
			"unallocated_amount": [">", 0],
		}
		if company:
			advance_filters["company"] = company
		advance_credit = sum(
			flt(value)
			for value in frappe.get_all(
				"Payment Entry",
				filters=advance_filters,
				pluck="unallocated_amount",
			)
		)

		total_credit = invoice_credit + advance_credit
		net_balance = total_outstanding - total_credit

		# ``total_credit`` above is the raw accounting view and intentionally
		# includes every negative outstanding document. Linked return documents can
		# retain a negative outstanding for ERPNext accounting even though POSNext
		# must NOT expose them as a second spendable Customer Credit source. Keep a
		# separate eligible/spendable value using the same resolver used by payment
		# allocation, so the Payment dialog and invoice audit field cannot display
		# phantom credit that the cashier is unable to redeem.
		available_credit = total_credit
		if company:
			available_credit = sum(
				flt(row.get("available_credit") or row.get("total_credit") or 0)
				for row in get_available_credit(customer, company)
			)

		return {
			"total_outstanding": flt(total_outstanding),
			"total_credit": flt(total_credit),
			"available_credit": flt(available_credit),
			"invoice_credit": flt(invoice_credit),
			"advance_credit": flt(advance_credit),
			"net_balance": flt(net_balance),
		}

	except Exception as e:
		frappe.log_error(
			title="Customer Balance Error",
			message=f"Customer: {customer}, Company: {company}, Error: {str(e)}\n{frappe.get_traceback()}",
		)
		return {
			"total_outstanding": 0.0,
			"total_credit": 0.0,
			"available_credit": 0.0,
			"invoice_credit": 0.0,
			"advance_credit": 0.0,
			"net_balance": 0.0,
		}


def check_credit_sale_enabled(pos_profile):
	"""
	Check if credit sale is enabled for the POS Profile.

	Args:
		pos_profile: POS Profile name

	Returns:
		bool: True if credit sale is enabled
	"""
	if not pos_profile:
		return False

	# Get POS Settings for the profile
	pos_settings = frappe.db.get_value(
		"POS Settings", {"pos_profile": pos_profile}, "allow_credit_sale", as_dict=False
	)

	return bool(pos_settings)


@frappe.whitelist()
def get_available_credit(customer, company, pos_profile=None):
	"""
	Get list of available credit sources for a customer.
	Includes:
	1. Outstanding invoices with negative outstanding (overpaid/returns)
	2. Unallocated advance payment entries

	Returns fresh data with modified timestamp for optimistic locking.
	The frontend should re-fetch before redemption to ensure data is current.

	Args:
		customer: Customer ID
		company: Company
		pos_profile: POS Profile (optional, for checking if feature is enabled)

	Returns:
		list: Available credit sources with amounts and modified timestamps
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	if not company:
		frappe.throw(_("Company is required"))

	total_credit = []

	# A negative outstanding balance is the accounting source of spendable
	# Customer Credit. For linked ERPNext returns this can live on the ORIGINAL
	# Sales Invoice; standalone returns normally carry it on the return document.
	outstanding_invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"outstanding_amount": ["<", 0],
			"docstatus": 1,
			"customer": customer,
			"company": company,
		},
		fields=[
			"name",
			"outstanding_amount",
			"is_return",
			"return_against",
			"posting_date",
			"grand_total",
			"modified",
		],
		order_by="posting_date desc, modified desc",
	)

	for row in outstanding_invoices:
		# A linked Sales Return (return_against is set) is NOT an independent
		# Customer Credit source. POSNext linked returns are created with
		# update_outstanding_for_self = 0, so the spendable credit belongs to
		# the original invoice reference. Exposing the return document itself can
		# later debit that return and turn it positive/Unpaid.
		if cint(row.is_return) and row.return_against:
			continue

		# Outstanding is negative, so make it positive for display. Standalone
		# no-invoice returns are valid here because return_against is empty.
		available_credit = -flt(row.outstanding_amount)

		if available_credit > 0:
			total_credit.append(
				{
					"type": "Invoice",
					"credit_origin": row.name,
					"total_credit": available_credit,
					"available_credit": available_credit,
					"source_type": "Sales Return" if cint(row.is_return) else "Linked Return / Overpayment",
					"posting_date": row.posting_date,
					"reference_amount": row.grand_total,
					"credit_to_redeem": 0,  # User will set this
					"modified": row.modified,  # For optimistic locking
				}
			)

	# Get unallocated advance payments
	advances = frappe.get_all(
		"Payment Entry",
		filters={
			"unallocated_amount": [">", 0],
			"party": customer,
			"company": company,
			"docstatus": 1,
			"payment_type": "Receive",
		},
		fields=["name", "unallocated_amount", "posting_date", "paid_amount", "mode_of_payment", "modified"],
		order_by="posting_date desc",
	)

	for row in advances:
		total_credit.append(
			{
				"type": "Advance",
				"credit_origin": row.name,
				"total_credit": flt(row.unallocated_amount),
				"available_credit": flt(row.unallocated_amount),
				"source_type": "Payment Entry",
				"posting_date": row.posting_date,
				"reference_amount": row.paid_amount,
				"mode_of_payment": row.mode_of_payment,
				"credit_to_redeem": 0,  # User will set this
				"modified": row.modified,  # For optimistic locking
			}
		)

	return total_credit



@frappe.whitelist()
def ensure_payment_hub_customer_credit_mode(company=None, pos_profile=None):
	"""Ensure Payment Hub can represent POSNext Customer Credit as a non-provider tender.

	Payment Hub v0.6.14 requires the POS Payment Session total to equal the Sales
	Invoice total.  Customer Credit is therefore represented inside the PPS as a
	captured ``Manual / Non-Cash`` allocation while POSNext remains responsible for
	the actual receivable settlement by Journal Entry / advance allocation.

	The synthetic Mode of Payment is removed from the Sales Invoice before ERPNext
	validates/submits it, so it never posts to a cash/bank account.
	"""
	if not frappe.db.exists("DocType", "Payment Hub Settings"):
		frappe.throw(_("ERPNext Payment Hub is not installed on this site."))

	mode = PAYMENT_HUB_CUSTOMER_CREDIT_MODE
	created_mode = False
	if not frappe.db.exists("Mode of Payment", mode):
		mop = frappe.new_doc("Mode of Payment")
		meta = frappe.get_meta("Mode of Payment")
		if meta.has_field("mode_of_payment"):
			mop.mode_of_payment = mode
		if meta.has_field("type"):
			mop.type = "General"
		if meta.has_field("enabled"):
			mop.enabled = 1
		mop.flags.ignore_permissions = True
		mop.insert()
		created_mode = True

	settings = frappe.get_single("Payment Hub Settings")
	target = None
	for row in getattr(settings, "payment_method_mappings", []) or []:
		if str(row.mode_of_payment or "").strip().lower() != mode.lower():
			continue
		if (row.company or None) == (company or None) and (row.pos_profile or None) == (pos_profile or None):
			target = row
			break

	changed = False
	if target is None:
		target = settings.append(
			"payment_method_mappings",
			{
				"enabled": 1,
				"mode_of_payment": mode,
				"channel": PAYMENT_HUB_MANUAL_CHANNEL,
				"company": company,
				"pos_profile": pos_profile,
				"priority": 1,
			},
		)
		changed = True
	else:
		updates = {
			"enabled": 1,
			"channel": PAYMENT_HUB_MANUAL_CHANNEL,
			"provider_account": None,
			"payment_terminal": None,
			"provider_payment_method": None,
		}
		for fieldname, value in updates.items():
			if target.get(fieldname) != value:
				target.set(fieldname, value)
				changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()

	return {
		"mode_of_payment": mode,
		"channel": PAYMENT_HUB_MANUAL_CHANNEL,
		"created_mode": created_mode,
		"mapping_updated": changed,
	}


def _get_payment_hub_credit_allocation(doc, plan):
	"""Return the PPS name and captured Customer Credit allocation total for a plan."""
	if not (
		frappe.db.exists("DocType", "POS Payment Session")
		and frappe.db.exists("DocType", "POS Payment Allocation")
	):
		return None, None

	filters = {"cart_reference": plan.cart_reference}
	if doc and getattr(doc, "name", None):
		filters["invoice_name"] = doc.name
	rows = frappe.get_all(
		"POS Payment Session",
		filters=filters,
		fields=["name"],
		order_by="modified desc",
		limit=1,
	)
	if not rows and filters.get("invoice_name"):
		filters.pop("invoice_name", None)
		rows = frappe.get_all(
			"POS Payment Session",
			filters=filters,
			fields=["name"],
			order_by="modified desc",
			limit=1,
		)
	if not rows:
		return None, 0.0

	session_name = rows[0].name
	amounts = frappe.get_all(
		"POS Payment Allocation",
		filters={
			"session": session_name,
			"status": "Captured",
			"mode_of_payment": PAYMENT_HUB_CUSTOMER_CREDIT_MODE,
		},
		pluck="amount",
	)
	return session_name, flt(sum(flt(value, 9) for value in amounts), 9)


def prepare_payment_hub_credit_invoice(doc, method=None):
	"""Strip Payment Hub's synthetic Customer Credit tender before SI validation.

	The PPS keeps the Customer Credit allocation so its confirmed total can equal the
	full invoice total.  The Sales Invoice must *not* post that synthetic allocation
	as a Mode of Payment; POSNext leaves that amount outstanding and redeems the
	selected credit source atomically from ``on_submit`` instead.
	"""
	if not doc or doc.doctype != "Sales Invoice" or cint(doc.get("is_return")):
		return
	if not cint(doc.get("is_pos")):
		return

	cart_reference = str(doc.get("posa_client_request_id") or "").strip()
	if not cart_reference:
		return

	plan_name = frappe.db.get_value(
		"POS Payment Hub Credit Plan",
		{"cart_reference": cart_reference, "status": "Pending"},
		"name",
	)
	if not plan_name:
		return

	plan = frappe.get_doc("POS Payment Hub Credit Plan", plan_name)
	credit_rows = [
		row
		for row in list(doc.get("payments") or [])
		if str(row.get("mode_of_payment") or "").strip().lower()
		== PAYMENT_HUB_CUSTOMER_CREDIT_MODE.lower()
	]
	if not credit_rows:
		# prepare_pos_invoice runs before Payment Hub creates allocations, so the
		# first draft save legitimately has no synthetic Customer Credit row yet.
		return

	expected = flt(plan.credit_amount, 9)
	actual = flt(sum(flt(row.get("amount"), 9) for row in credit_rows), 9)
	if abs(actual - expected) > 0.01:
		frappe.throw(
			_("Payment Hub Customer Credit allocation mismatch. Expected: {0}, Session: {1}").format(
				frappe.format_value(expected, {"fieldtype": "Currency"}),
				frappe.format_value(actual, {"fieldtype": "Currency"}),
			)
		)

	for row in credit_rows:
		doc.remove(row)

	# If the provider remainder is zero for an edge case, allow the invoice to pass
	# POS paid-amount validation; the on_submit hook still performs the real credit
	# redemption and will fail atomically if the selected sources are unavailable.
	doc.flags.pos_next_redeemed_customer_credit = expected
	doc.flags.pos_next_payment_hub_customer_credit = expected


@frappe.whitelist()
def create_payment_hub_credit_plan(
	cart_reference,
	customer,
	company,
	credit_amount,
	customer_credit_dict,
	pos_profile=None,
):
	"""Persist Customer Credit selected for a Payment Hub checkout.

	Payment Hub owns the real-money provider flow and may create/submit the Sales
	Invoice later (for example after an asynchronous payment link is paid).  The
	plan is keyed by ``posa_client_request_id`` / cart reference so the Sales
	Invoice ``on_submit`` hook can redeem the selected credit in the same database
	transaction that submits the provider-created invoice.  Payment Hub itself is
	not modified.
	"""
	import json

	cart_reference = str(cart_reference or "").strip()
	if not cart_reference:
		frappe.throw(_("Payment Hub cart reference is required."))
	if not customer or not company:
		frappe.throw(_("Customer and company are required for Customer Credit."))

	if isinstance(customer_credit_dict, str):
		customer_credit_dict = json.loads(customer_credit_dict or "[]")
	customer_credit_dict = customer_credit_dict or []
	credit_amount = flt(credit_amount, 9)
	if credit_amount <= 0 or not customer_credit_dict:
		frappe.throw(_("A positive Customer Credit allocation is required."))

	# Validate the full plan before any provider charge/session is started.  The
	# actual redemption re-validates and locks every source at invoice submit time.
	planned_total = 0.0
	seen = set()
	for row in customer_credit_dict:
		amount = flt(row.get("credit_to_redeem"), 9)
		if amount <= 0:
			continue
		credit_type = row.get("type")
		origin = row.get("credit_origin")
		if not credit_type or not origin:
			frappe.throw(_("Every Customer Credit row must include a type and source."))
		key = (credit_type, origin)
		if key in seen:
			frappe.throw(_("Customer Credit source {0} was supplied more than once.").format(origin))
		seen.add(key)

		if credit_type == "Invoice":
			source = frappe.db.get_value(
				"Sales Invoice",
				origin,
				["customer", "company", "docstatus", "outstanding_amount", "is_return", "return_against"],
				as_dict=True,
			)
			if not source or source.docstatus != 1:
				frappe.throw(_("Customer Credit source invoice {0} is not submitted.").format(origin))
			_validate_credit_source_ownership(origin, source.customer, source.company, customer, company)
			if cint(source.is_return) and source.return_against:
				frappe.throw(
					_("Linked return {0} cannot be used directly as Customer Credit.").format(origin)
				)
			available = max(0, -flt(source.outstanding_amount, 9))
			if amount > available + 0.01:
				frappe.throw(
					_("Insufficient credit available from {0}. Available: {1}, Requested: {2}").format(
						origin,
						frappe.format_value(available, {"fieldtype": "Currency"}),
						frappe.format_value(amount, {"fieldtype": "Currency"}),
					)
				)
		elif credit_type == "Advance":
			source = frappe.db.get_value(
				"Payment Entry",
				origin,
				["party", "company", "party_type", "payment_type", "docstatus", "unallocated_amount"],
				as_dict=True,
			)
			if (
				not source
				or source.docstatus != 1
				or source.party_type != "Customer"
				or source.payment_type != "Receive"
			):
				frappe.throw(_("Payment Entry {0} is not a valid customer advance.").format(origin))
			_validate_credit_source_ownership(origin, source.party, source.company, customer, company)
			if amount > flt(source.unallocated_amount, 9) + 0.01:
				frappe.throw(_("Payment Entry {0} has insufficient unallocated amount.").format(origin))
		else:
			frappe.throw(_("Unsupported Customer Credit source type: {0}").format(credit_type))
		planned_total += amount

	planned_total = flt(planned_total, 9)
	if abs(planned_total - credit_amount) > 0.01:
		frappe.throw(
			_("Customer Credit allocation mismatch. Requested: {0}, Allocated: {1}").format(
				frappe.format_value(credit_amount, {"fieldtype": "Currency"}),
				frappe.format_value(planned_total, {"fieldtype": "Currency"}),
			)
		)

	existing = frappe.db.get_value(
		"POS Payment Hub Credit Plan",
		{"cart_reference": cart_reference},
		["name", "status"],
		as_dict=True,
	)
	payload_json = json.dumps(customer_credit_dict, default=str, separators=(",", ":"))
	if existing:
		if existing.status == "Applied":
			frappe.throw(_("Customer Credit plan {0} has already been applied.").format(cart_reference))
		doc = frappe.get_doc("POS Payment Hub Credit Plan", existing.name)
	else:
		doc = frappe.new_doc("POS Payment Hub Credit Plan")
		doc.cart_reference = cart_reference

	doc.customer = customer
	doc.company = company
	doc.pos_profile = pos_profile
	doc.credit_amount = credit_amount
	doc.credit_payload = payload_json
	doc.status = "Pending"
	doc.sales_invoice = None
	doc.applied_at = None
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert()
	else:
		doc.save()

	return {"name": doc.name, "cart_reference": cart_reference, "credit_amount": credit_amount}


@frappe.whitelist()
def cancel_payment_hub_credit_plan(cart_reference):
	"""Mark an unused Payment Hub credit plan cancelled."""
	cart_reference = str(cart_reference or "").strip()
	if not cart_reference:
		return False
	name = frappe.db.get_value("POS Payment Hub Credit Plan", {"cart_reference": cart_reference}, "name")
	if not name:
		return False
	doc = frappe.get_doc("POS Payment Hub Credit Plan", name)
	if doc.status == "Applied":
		return False
	doc.status = "Cancelled"
	doc.flags.ignore_permissions = True
	doc.save()
	return True


def _apply_payment_hub_credit_plan(doc, plan):
	"""Apply one persisted Payment Hub Customer Credit plan to a submitted invoice.

	A plan is valid only when the same Payment Hub session contains the captured
	synthetic Customer Credit allocation.  This prevents an abandoned/stale plan
	from leaking into a later normal Electronic/Terminal checkout that happens to
	reuse the cart reference.
	"""
	if plan.status == "Applied":
		return {"applied": True, "sales_invoice": plan.sales_invoice or doc.name}
	if plan.status == "Cancelled":
		return {"applied": False, "cancelled": True, "sales_invoice": plan.sales_invoice or doc.name}

	_validate_credit_source_ownership(
		plan.name, plan.customer, plan.company, doc.customer, doc.company
	)

	credit_amount = flt(plan.credit_amount, 9)
	session_name, session_credit = _get_payment_hub_credit_allocation(doc, plan)
	if session_credit is not None and abs(flt(session_credit, 9) - credit_amount) > 0.01:
		plan.status = "Cancelled"
		plan.sales_invoice = doc.name
		plan.flags.ignore_permissions = True
		plan.save()
		return {
			"applied": False,
			"cancelled": True,
			"reason": "missing_or_mismatched_session_credit_allocation",
			"payment_session": session_name,
			"session_credit_amount": flt(session_credit, 9),
			"credit_amount": credit_amount,
			"sales_invoice": doc.name,
		}

	current_outstanding = flt(doc.outstanding_amount, 9)
	if current_outstanding <= 0.01 and credit_amount > 0:
		# Provider/normal payment already settled the invoice.  The plan is stale and
		# must never block Complete & Print or over-settle the customer's account.
		plan.status = "Cancelled"
		plan.sales_invoice = doc.name
		plan.flags.ignore_permissions = True
		plan.save()
		return {
			"applied": False,
			"cancelled": True,
			"reason": "invoice_already_settled",
			"sales_invoice": doc.name,
			"credit_amount": credit_amount,
		}

	import json

	credit_rows = json.loads(plan.credit_payload or "[]")
	redeem_customer_credit(
		doc.name,
		credit_rows,
		expected_credit_amount=credit_amount,
		require_full_settlement=True,
	)

	plan.status = "Applied"
	plan.sales_invoice = doc.name
	plan.applied_at = frappe.utils.now_datetime()
	plan.flags.ignore_permissions = True
	plan.save()
	return {
		"applied": True,
		"sales_invoice": doc.name,
		"credit_amount": credit_amount,
		"payment_session": session_name,
	}


def apply_pending_payment_hub_credit(doc, method=None):
	"""Sales Invoice on_submit hook for Payment Hub + Customer Credit.

	The Payment Hub draft carries ``posa_client_request_id`` equal to the POSNext
	cart reference. Payment Hub tracks Customer Credit as a synthetic captured
	manual allocation so the PPS total remains equal to the full invoice total; the
	``before_validate`` hook removes that synthetic tender from the Sales Invoice.
	This hook then atomically redeems the selected credit source against the real
	remaining receivable. Any redemption failure aborts invoice submission so
	Payment Hub's own recovery queue can safely retry the same captured session.
	"""
	if not doc or doc.doctype != "Sales Invoice" or doc.docstatus != 1 or cint(doc.is_return):
		return

	cart_reference = str(doc.get("posa_client_request_id") or "").strip()
	if not cart_reference:
		return

	plan_name = frappe.db.get_value(
		"POS Payment Hub Credit Plan",
		{"cart_reference": cart_reference, "status": "Pending"},
		"name",
	)
	if not plan_name:
		return

	plan = frappe.get_doc("POS Payment Hub Credit Plan", plan_name)
	return _apply_payment_hub_credit_plan(doc, plan)


@frappe.whitelist()
def finalize_payment_hub_credit(invoice_name, cart_reference=None):
	"""Idempotent fallback used by the POS UI after Payment Hub completion.

	Normally the Sales Invoice on_submit hook applies the plan automatically. This
	fallback also accepts the original cart reference so completion remains robust
	even if a Payment Hub version does not copy ``posa_client_request_id`` from its
	draft payload onto the final invoice.
	"""
	if not invoice_name:
		frappe.throw(_("Sales Invoice is required."))
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	if doc.docstatus != 1 or cint(doc.is_return):
		frappe.throw(_("A submitted Sales Invoice is required."))

	cart_reference = str(cart_reference or doc.get("posa_client_request_id") or "").strip()
	if not cart_reference:
		return {"applied": False, "reason": "no_cart_reference"}

	plan_name = frappe.db.get_value(
		"POS Payment Hub Credit Plan", {"cart_reference": cart_reference}, "name"
	)
	if not plan_name:
		return {"applied": False, "reason": "no_plan"}

	plan = frappe.get_doc("POS Payment Hub Credit Plan", plan_name)
	if plan.status == "Cancelled":
		frappe.throw(_("Customer Credit plan for this Payment Hub sale was cancelled."))
	if plan.status == "Applied":
		if plan.sales_invoice and plan.sales_invoice != doc.name:
			frappe.throw(_("Customer Credit plan was already applied to a different invoice."))
		return {"applied": True, "sales_invoice": plan.sales_invoice or doc.name}

	return _apply_payment_hub_credit_plan(doc, plan)

def _update_invoice_customer_credit_tracking(invoice_doc, redeemed_amount):
	"""Persist POSNext's audit/display fields after successful redemption.

	``paid_amount`` correctly stays zero for a sale settled purely by Customer
	Credit, so these dedicated fields tell Desk users how the invoice was settled.
	The remaining balance is the live *net* customer credit after this redemption.
	"""
	values = {}
	if frappe.db.has_column("Sales Invoice", "posa_redeemed_customer_credit"):
		previous = flt(
			frappe.db.get_value(
				"Sales Invoice", invoice_doc.name, "posa_redeemed_customer_credit"
			)
			or 0
		)
		values["posa_redeemed_customer_credit"] = previous + flt(redeemed_amount)

	if frappe.db.has_column("Sales Invoice", "posa_remaining_customer_credit_balance"):
		balance = get_customer_balance(invoice_doc.customer, invoice_doc.company)
		# Store only spendable credit. Raw negative outstanding on a linked return
		# can remain in ERPNext after the original-invoice credit is consumed, but
		# that linked return is intentionally excluded by get_available_credit().
		values["posa_remaining_customer_credit_balance"] = max(
			0, flt(balance.get("available_credit") or 0)
		)

	if values:
		frappe.db.set_value(
			"Sales Invoice",
			invoice_doc.name,
			values,
			update_modified=False,
		)


@frappe.whitelist()
def redeem_customer_credit(
	invoice_name,
	customer_credit_dict,
	expected_credit_amount=None,
	require_full_settlement=False,
):
	"""Redeem Customer Credit atomically against a submitted Sales Invoice.

	The complete requested allocation is validated before any Journal Entry is
	created. Any error is raised to the caller so the surrounding Frappe request
	can roll back the invoice and all allocation entries together.
	"""
	import json

	if isinstance(customer_credit_dict, str):
		customer_credit_dict = json.loads(customer_credit_dict)

	if not invoice_name:
		frappe.throw(_("Invoice name is required"))

	if not customer_credit_dict:
		return []

	invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice_doc.docstatus != 1:
		frappe.throw(_("Invoice must be submitted to redeem credit"))

	# Normalize rows and reject duplicate sources. Duplicates make audit trails
	# ambiguous and can accidentally redeem the same credit twice.
	plan = []
	seen = set()
	for credit_row in customer_credit_dict:
		credit_to_redeem = flt(credit_row.get("credit_to_redeem", 0))
		if credit_to_redeem <= 0:
			continue
		credit_type = credit_row.get("type")
		credit_origin = credit_row.get("credit_origin")
		if not credit_type or not credit_origin:
			frappe.throw(_("Every Customer Credit row must include a type and source."))
		key = (credit_type, credit_origin)
		if key in seen:
			frappe.throw(_("Customer Credit source {0} was supplied more than once.").format(credit_origin))
		seen.add(key)
		plan.append((credit_type, credit_origin, credit_to_redeem))

	if not plan:
		return []

	planned_total = flt(sum(row[2] for row in plan), 9)
	expected_total = flt(expected_credit_amount or planned_total, 9)
	if abs(planned_total - expected_total) > 0.01:
		frappe.throw(
			_("Customer Credit allocation mismatch. Requested: {0}, Allocated: {1}").format(
				frappe.format_value(expected_total, {"fieldtype": "Currency"}),
				frappe.format_value(planned_total, {"fieldtype": "Currency"}),
			)
		)

	# After real-money POS payment rows/write-off are posted, the target invoice's
	# positive outstanding should be the amount Customer Credit needs to clear.
	current_outstanding = flt(frappe.db.get_value("Sales Invoice", invoice_name, "outstanding_amount"), 9)
	if current_outstanding < -0.01:
		frappe.throw(_("Invoice {0} is already over-allocated.").format(invoice_name))
	if planned_total > current_outstanding + 0.01:
		frappe.throw(
			_("Customer Credit exceeds invoice outstanding. Outstanding: {0}, Credit: {1}").format(
				frappe.format_value(current_outstanding, {"fieldtype": "Currency"}),
				frappe.format_value(planned_total, {"fieldtype": "Currency"}),
			)
		)

	# First validate/lock EVERY source. No JE is created until the whole plan has
	# passed validation, preventing half-completed multi-source allocations.
	for credit_type, credit_origin, credit_to_redeem in plan:
		if credit_type == "Invoice":
			_validate_and_lock_invoice_credit(
				credit_origin,
				credit_to_redeem,
				invoice_doc.customer,
				invoice_doc.company,
			)
		elif credit_type == "Advance":
			_validate_and_lock_advance_credit(
				credit_origin,
				credit_to_redeem,
				invoice_doc.customer,
				invoice_doc.company,
			)
		else:
			frappe.throw(_("Unsupported Customer Credit source type: {0}").format(credit_type))

	created_entries = []
	for credit_type, credit_origin, credit_to_redeem in plan:
		if credit_type == "Invoice":
			created_entries.append(
				_create_credit_allocation_journal_entry(
					invoice_doc, credit_origin, credit_to_redeem
				)
			)
		else:
			created_entries.append(
				_create_payment_entry_from_advance(
					invoice_doc, credit_origin, credit_to_redeem
				)
			)

	if cint(require_full_settlement):
		# Re-read from DB because JE submission updates invoice outstanding.
		remaining = flt(frappe.db.get_value("Sales Invoice", invoice_name, "outstanding_amount"), 9)
		if abs(remaining) > 0.01:
			frappe.throw(
				_("Customer Credit checkout did not fully settle invoice {0}. Remaining: {1}").format(
					invoice_name,
					frappe.format_value(remaining, {"fieldtype": "Currency"}),
				)
			)

	# Only stamp tracking fields after every allocation has succeeded. If any
	# source fails, the surrounding request raises/rolls back and these values are
	# never written.
	_update_invoice_customer_credit_tracking(invoice_doc, planned_total)

	return created_entries


def _validate_credit_source_ownership(source_name, source_customer, source_company, customer, company):
	"""Ensure a credit source belongs to the same customer and company as the target invoice."""
	if source_customer != customer:
		frappe.throw(_("Credit source {0} does not belong to customer {1}").format(source_name, customer))

	if source_company != company:
		frappe.throw(_("Credit source {0} does not belong to company {1}").format(source_name, company))


def _validate_and_lock_invoice_credit(invoice_name, amount_to_redeem, customer, company):
	"""
	Validate and lock invoice credit using SELECT FOR UPDATE.
	This prevents race conditions when multiple users try to use the same credit.

	Args:
		invoice_name: Source invoice name with credit
		amount_to_redeem: Amount being redeemed
		customer: Target invoice customer
		company: Target invoice company

	Raises:
		frappe.ValidationError: If insufficient credit available
	"""
	from frappe.query_builder import DocType

	SalesInvoice = DocType("Sales Invoice")

	# Use SELECT FOR UPDATE to lock the row
	# This blocks other transactions from reading/modifying until we commit
	query = (
		frappe.qb.from_(SalesInvoice)
		.select(
			SalesInvoice.name,
			SalesInvoice.outstanding_amount,
			SalesInvoice.customer,
			SalesInvoice.company,
			SalesInvoice.is_return,
			SalesInvoice.return_against,
		)
		.where((SalesInvoice.name == invoice_name) & (SalesInvoice.docstatus == 1))
		.for_update()
	)

	result = query.run(as_dict=True)

	if not result:
		frappe.throw(_("Credit source invoice {0} not found or not submitted").format(invoice_name))

	_validate_credit_source_ownership(
		invoice_name,
		result[0].customer,
		result[0].company,
		customer,
		company,
	)

	# Never debit a linked return as if it were a separate Customer Credit
	# source. Its return GL points back to the original invoice and debiting the
	# return itself can create a positive outstanding / Unpaid credit note.
	if cint(result[0].is_return) and result[0].return_against:
		frappe.throw(
			_(
				"Linked return {0} cannot be used directly as Customer Credit. "
				"Use the actual credit-bearing original invoice instead."
			).format(invoice_name)
		)

	current_outstanding = flt(result[0].outstanding_amount)
	available_credit = -current_outstanding  # Credit is negative outstanding

	if available_credit < amount_to_redeem:
		frappe.throw(
			_("Insufficient credit available from {0}. Available: {1}, Requested: {2}").format(
				invoice_name,
				frappe.format_value(available_credit, {"fieldtype": "Currency"}),
				frappe.format_value(amount_to_redeem, {"fieldtype": "Currency"}),
			)
		)


def _validate_and_lock_advance_credit(payment_entry_name, amount_to_redeem, customer, company):
	"""
	Validate and lock advance payment using SELECT FOR UPDATE.
	This prevents race conditions when multiple users try to use the same advance.

	Args:
		payment_entry_name: Payment Entry name with unallocated amount
		amount_to_redeem: Amount being allocated
		customer: Target invoice customer
		company: Target invoice company

	Raises:
		frappe.ValidationError: If insufficient unallocated amount
	"""
	from frappe.query_builder import DocType

	PaymentEntry = DocType("Payment Entry")

	# Use SELECT FOR UPDATE to lock the row
	query = (
		frappe.qb.from_(PaymentEntry)
		.select(
			PaymentEntry.name,
			PaymentEntry.unallocated_amount,
			PaymentEntry.party,
			PaymentEntry.company,
			PaymentEntry.party_type,
			PaymentEntry.payment_type,
		)
		.where((PaymentEntry.name == payment_entry_name) & (PaymentEntry.docstatus == 1))
		.for_update()
	)

	result = query.run(as_dict=True)

	if not result:
		frappe.throw(_("Payment Entry {0} not found or not submitted").format(payment_entry_name))

	if result[0].party_type != "Customer" or result[0].payment_type != "Receive":
		frappe.throw(_("Payment Entry {0} is not a valid customer advance").format(payment_entry_name))

	_validate_credit_source_ownership(
		payment_entry_name,
		result[0].party,
		result[0].company,
		customer,
		company,
	)

	available_amount = flt(result[0].unallocated_amount)

	if available_amount < amount_to_redeem:
		frappe.throw(
			_("Insufficient unallocated amount in {0}. Available: {1}, Requested: {2}").format(
				payment_entry_name,
				frappe.format_value(available_amount, {"fieldtype": "Currency"}),
				frappe.format_value(amount_to_redeem, {"fieldtype": "Currency"}),
			)
		)


def _create_credit_allocation_journal_entry(invoice_doc, original_invoice_name, amount):
	"""
	Create Journal Entry to allocate credit from one invoice to another.

	GL Entries Created:
	- Debit: Original Invoice Receivable Account (reduces its outstanding)
	- Credit: New Invoice Receivable Account (reduces its outstanding)

	Args:
		invoice_doc: New Sales Invoice document
		original_invoice_name: Original invoice with credit
		amount: Amount to allocate

	Returns:
		str: Journal Entry name
	"""
	# Get original invoice
	original_invoice = frappe.get_doc("Sales Invoice", original_invoice_name)

	_validate_credit_source_ownership(
		original_invoice.name,
		original_invoice.customer,
		original_invoice.company,
		invoice_doc.customer,
		invoice_doc.company,
	)

	# Get cost center
	cost_center = invoice_doc.get("cost_center") or frappe.get_cached_value(
		"Company", invoice_doc.company, "cost_center"
	)

	# Create Journal Entry
	jv_doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": today(),
			"company": invoice_doc.company,
			"user_remark": get_credit_redeem_remark(invoice_doc.name),
		}
	)

	# Debit Entry - Original Invoice (reduces outstanding)
	debit_row = jv_doc.append("accounts", {})
	debit_row.update(
		{
			"account": original_invoice.debit_to,
			"party_type": "Customer",
			"party": invoice_doc.customer,
			"reference_type": "Sales Invoice",
			"reference_name": original_invoice.name,
			"debit_in_account_currency": amount,
			"credit_in_account_currency": 0,
			"cost_center": cost_center,
		}
	)

	# Credit Entry - New Invoice (reduces outstanding)
	credit_row = jv_doc.append("accounts", {})
	credit_row.update(
		{
			"account": invoice_doc.debit_to,
			"party_type": "Customer",
			"party": invoice_doc.customer,
			"reference_type": "Sales Invoice",
			"reference_name": invoice_doc.name,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": amount,
			"cost_center": cost_center,
		}
	)

	jv_doc.flags.ignore_permissions = True
	jv_doc.save()
	jv_doc.submit()

	frappe.msgprint(_("Journal Entry {0} created for credit redemption").format(jv_doc.name), alert=True)

	return jv_doc.name


def _create_payment_entry_from_advance(invoice_doc, payment_entry_name, amount):
	"""
	Allocate existing advance Payment Entry to invoice.
	Updates the Payment Entry to add reference to the invoice.

	Args:
		invoice_doc: Sales Invoice document
		payment_entry_name: Payment Entry with unallocated amount
		amount: Amount to allocate

	Returns:
		str: Payment Entry name
	"""
	# Get payment entry
	payment_entry = frappe.get_doc("Payment Entry", payment_entry_name)

	if payment_entry.party_type != "Customer" or payment_entry.payment_type != "Receive":
		frappe.throw(_("Payment Entry {0} is not a valid customer advance").format(payment_entry_name))

	_validate_credit_source_ownership(
		payment_entry.name,
		payment_entry.party,
		payment_entry.company,
		invoice_doc.customer,
		invoice_doc.company,
	)

	# Check if already allocated
	if payment_entry.unallocated_amount < amount:
		frappe.throw(_("Payment Entry {0} has insufficient unallocated amount").format(payment_entry_name))

	# Add reference to invoice
	payment_entry.append(
		"references",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice_doc.name,
			"total_amount": invoice_doc.grand_total,
			"outstanding_amount": invoice_doc.outstanding_amount,
			"allocated_amount": amount,
		},
	)

	# Recalculate unallocated amount
	payment_entry.set_amounts()

	payment_entry.flags.ignore_permissions = True
	payment_entry.flags.ignore_validate_update_after_submit = True
	payment_entry.save()

	frappe.msgprint(_("Payment Entry {0} allocated to invoice").format(payment_entry.name), alert=True)

	return payment_entry.name


def get_credit_redeem_remark(invoice_name):
	"""Get remark for credit redemption journal entry."""
	return f"POS Next credit redemption for invoice {invoice_name}"


@frappe.whitelist()
def cancel_credit_journal_entries(invoice_name):
	"""
	Cancel journal entries created for credit redemption when invoice is cancelled.

	Args:
		invoice_name: Sales Invoice name
	"""
	remark = get_credit_redeem_remark(invoice_name)

	# Find linked journal entries
	linked_journal_entries = frappe.get_all(
		"Journal Entry", filters={"docstatus": 1, "user_remark": remark}, pluck="name"
	)

	cancelled_count = 0
	for journal_entry_name in linked_journal_entries:
		try:
			je_doc = frappe.get_doc("Journal Entry", journal_entry_name)

			# Verify it references this invoice
			has_reference = any(
				d.reference_type == "Sales Invoice" and d.reference_name == invoice_name
				for d in je_doc.accounts
			)

			if not has_reference:
				continue

			je_doc.flags.ignore_permissions = True
			je_doc.cancel()
			cancelled_count += 1
		except Exception as e:
			frappe.log_error(
				f"Failed to cancel Journal Entry {journal_entry_name}: {str(e)}",
				"Credit Sale JE Cancellation",
			)

	if cancelled_count > 0:
		frappe.msgprint(
			_("Cancelled {0} credit redemption journal entries").format(cancelled_count), alert=True
		)

	return cancelled_count


@frappe.whitelist()
def get_credit_sale_summary(pos_profile):
	"""
	Get summary of credit sales for a POS Profile.

	Args:
		pos_profile: POS Profile name

	Returns:
		dict: Summary statistics
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	# Get credit sales (outstanding > 0)
	summary = frappe.db.sql(
		"""
		SELECT
			COUNT(*) as count,
			SUM(outstanding_amount) as total_outstanding,
			SUM(grand_total) as total_amount,
			SUM(paid_amount) as total_paid
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
			AND outstanding_amount > 0
			AND is_return = 0
	""",
		{"pos_profile": pos_profile},
		as_dict=True,
	)

	return summary[0] if summary else {"count": 0, "total_outstanding": 0, "total_amount": 0, "total_paid": 0}


@frappe.whitelist()
def get_credit_invoices(pos_profile, limit=100):
	"""
	Get list of credit sale invoices (with outstanding amount).

	Args:
		pos_profile: POS Profile name
		limit: Maximum number of invoices to return

	Returns:
		list: Credit sale invoices
	"""
	if not pos_profile:
		frappe.throw(_("POS Profile is required"))

	# Check if user has access to this POS Profile
	has_access = frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": frappe.session.user})

	if not has_access and not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("You don't have access to this POS Profile"))

	# Query for credit invoices
	invoices = frappe.db.sql(
		"""
		SELECT
			name,
			customer,
			customer_name,
			posting_date,
			posting_time,
			grand_total,
			paid_amount,
			outstanding_amount,
			status,
			docstatus
		FROM
			`tabSales Invoice`
		WHERE
			pos_profile = %(pos_profile)s
			AND docstatus = 1
			AND is_pos = 1
			AND outstanding_amount > 0
			AND is_return = 0
		ORDER BY
			posting_date DESC,
			posting_time DESC
		LIMIT %(limit)s
	""",
		{"pos_profile": pos_profile, "limit": limit},
		as_dict=True,
	)

	return invoices
