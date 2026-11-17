# Copyright (c) 2021, Youssef Restom and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count, Upper
from frappe.utils import cint, flt, getdate, strip, today

COUPON_OVERSHOOT_LOG_TITLE = "POS Coupon check skipped for an offline sale"
# POS Settings.offline_coupon_overshoot options
OFFLINE_OVERSHOOT_FIELD = "offline_coupon_overshoot"
OFFLINE_OVERSHOOT_REJECT = "Reject"
LIMIT_MAXIMUM_USE = "maximum_use"
LIMIT_PER_CUSTOMER = "maximum_use_per_customer"
CHECK_VALIDITY = "validity"
# Fields count_usage_on_submit reads under the row lock
_SUBMIT_COUPON_FIELDS = (
	"name",
	"coupon_code",
	"coupon_type",
	"customer",
	"company",
	"disabled",
	"valid_from",
	"valid_upto",
	"used",
	"maximum_use",
	"one_use",
)


class POSCoupon(Document):
	def autoname(self):
		self.coupon_name = strip(self.coupon_name)
		self.name = self.coupon_name

		if not self.coupon_code:
			if self.coupon_type == "Promotional":
				self.coupon_code = "".join(i for i in self.coupon_name if not i.isdigit())[0:8].upper()
			elif self.coupon_type == "Gift Card":
				self.coupon_code = frappe.generate_hash()[:10].upper()

	def validate(self):
		# Gift Card validations
		if self.coupon_type == "Gift Card":
			self.maximum_use = 1
			if not self.customer:
				frappe.throw(_("Please select the customer for Gift Card."))

		# Discount validations
		if not self.discount_type:
			frappe.throw(_("Discount Type is required"))

		if self.discount_type == "Percentage":
			if not self.discount_percentage:
				frappe.throw(_("Discount Percentage is required"))
			if flt(self.discount_percentage) <= 0 or flt(self.discount_percentage) > 100:
				frappe.throw(_("Discount Percentage must be between 0 and 100"))
		elif self.discount_type == "Amount":
			if not self.discount_amount:
				frappe.throw(_("Discount Amount is required"))
			if flt(self.discount_amount) <= 0:
				frappe.throw(_("Discount Amount must be greater than 0"))

		# Minimum amount validation
		if self.min_amount and flt(self.min_amount) < 0:
			frappe.throw(_("Minimum Amount cannot be negative"))

		# Maximum discount validation
		if self.max_amount and flt(self.max_amount) <= 0:
			frappe.throw(_("Maximum Discount Amount must be greater than 0"))

		# Date validations
		if self.valid_from and self.valid_upto:
			if getdate(self.valid_from) > getdate(self.valid_upto):
				frappe.throw(_("Valid From date cannot be after Valid Until date"))


def coupon_validity_error(coupon, customer=None, company=None) -> str | None:
	"""Why ``coupon`` cannot be used (translated), ignoring usage limits; None when it can.

	Disabled, outside its date range, another company, or a gift card of another
	customer. Shared by check_coupon_code and the re-check on submit.
	"""
	if cint(coupon.disabled):
		return _("Sorry, this coupon has been disabled")
	if coupon.valid_from and getdate(coupon.valid_from) > getdate(today()):
		return _("Sorry, this coupon code's validity has not started")
	if coupon.valid_upto and getdate(coupon.valid_upto) < getdate(today()):
		return _("Sorry, this coupon code has expired")
	if company and coupon.company != company:
		return _("Sorry, this coupon is not valid for this company")
	if coupon.coupon_type == "Gift Card" and coupon.customer:
		if not customer or coupon.customer != customer:
			return _("Sorry, this gift card is assigned to a specific customer")
	return None


def check_coupon_code(coupon_code, customer=None, company=None):
	"""Validate and return coupon details"""
	res = {"coupon": None}

	name = resolve_coupon_name(coupon_code)
	if not name:
		res["msg"] = _("Sorry, this coupon code does not exist")
		return res

	coupon = frappe.get_doc("POS Coupon", name)

	error = coupon_validity_error(coupon, customer=customer, company=company)
	if error:
		res["msg"] = error
		return res

	# Check usage limits
	if coupon.used and coupon.maximum_use and coupon.used >= coupon.maximum_use:
		res["msg"] = _("Sorry, this coupon code has been fully redeemed")
		return res

	# Per-customer usage limit
	per_customer_limit = _get_per_customer_use_limit(coupon)
	if per_customer_limit and customer:
		used_count = _get_customer_coupon_usage_count(customer, coupon.coupon_code)
		if used_count >= per_customer_limit:
			res["msg"] = _("Sorry, you have already used this coupon code the maximum number of times")
			return res

	# All validations passed
	res["coupon"] = coupon
	res["valid"] = True

	return res


def _get_per_customer_use_limit(coupon) -> int:
	"""Max uses per customer: maximum_use_per_customer wins; one_use means 1 when it is unset.

	maximum_use_per_customer is an optional field (added by another app), so it
	is read with a default.
	"""
	limit = cint(getattr(coupon, "maximum_use_per_customer", 0) or 0)
	if limit > 0:
		return limit
	if cint(getattr(coupon, "one_use", 0) or 0):
		return 1
	return 0


def resolve_coupon_name(coupon_code: str | None) -> str | None:
	"""POS Coupon name for a code, matched case-insensitively whatever the DB collation."""
	code = (coupon_code or "").strip().upper()
	if not code:
		return None
	coupon = frappe.qb.DocType("POS Coupon")
	rows = (
		frappe.qb.from_(coupon).select(coupon.name).where(Upper(coupon.coupon_code) == code).limit(1)
	).run()
	return rows[0][0] if rows else None


def customer_coupon_usage_query(customer, coupon_code, exclude_name=None, lock=False):
	"""qb COUNT of the customer's submitted Sales Invoices (returns excluded) with this coupon.

	The code is compared case-insensitively, the same way resolve_coupon_name matches.
	``exclude_name`` leaves out the invoice being submitted. ``lock`` makes it a
	locking read (FOR UPDATE), which sees rows committed after this transaction's
	snapshot was taken.
	"""
	inv = frappe.qb.DocType("Sales Invoice")
	query = (
		frappe.qb.from_(inv)
		.select(Count(inv.name))
		.where(inv.customer == customer)
		.where(Upper(inv.coupon_code) == (coupon_code or "").strip().upper())
		.where(inv.docstatus == 1)
		# A return carries the sale's coupon_code but is not another use
		.where(inv.is_return == 0)
	)
	if exclude_name:
		query = query.where(inv.name != exclude_name)
	if lock:
		query = query.for_update()
	return query


def _get_customer_coupon_usage_count(customer, coupon_code, exclude_name=None, lock=False) -> int:
	"""How many submitted sales of ``customer`` used this coupon (see customer_coupon_usage_query)."""
	# coupon_code is a Custom Field: absent until the site has synced it
	if not frappe.get_meta("Sales Invoice").has_field("coupon_code"):
		return 0
	return cint(customer_coupon_usage_query(customer, coupon_code, exclude_name, lock).run()[0][0])


def apply_coupon_discount(coupon, cart_total, net_total=None):
	"""Calculate discount amount based on coupon configuration"""
	from frappe.utils import flt

	# Determine the base amount for discount calculation
	base_amount = cart_total if coupon.apply_on == "Grand Total" else (net_total or cart_total)

	# Check minimum amount
	if coupon.min_amount and flt(base_amount) < flt(coupon.min_amount):
		return {
			"valid": False,
			"message": _("Minimum cart amount of {0} is required").format(
				frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})
			),
			"discount": 0,
		}

	# Calculate discount
	discount = 0
	if coupon.discount_type == "Percentage":
		discount = flt(base_amount) * flt(coupon.discount_percentage) / 100
	elif coupon.discount_type == "Amount":
		discount = flt(coupon.discount_amount)

	# Apply maximum discount limit
	if coupon.max_amount and flt(discount) > flt(coupon.max_amount):
		discount = flt(coupon.max_amount)

	# Ensure discount doesn't exceed cart total
	if discount > base_amount:
		discount = base_amount

	return {
		"valid": True,
		"discount": discount,
		"discount_type": coupon.discount_type,
		"discount_percentage": coupon.discount_percentage if coupon.discount_type == "Percentage" else None,
		"apply_on": coupon.apply_on,
	}


def offline_overshoot_allowed(pos_profile: str | None) -> bool:
	"""POS Settings.offline_coupon_overshoot for this profile: may an offline sync skip a coupon check?

	A blank value (settings not saved since the field was added) means the
	field's default, "Allow and log"; so does a missing field (before migrate).
	"""
	value = None
	if pos_profile:
		value = frappe.db.get_value("POS Settings", {"pos_profile": pos_profile}, OFFLINE_OVERSHOOT_FIELD)
	if not value:
		# Code deployed before migrate added the field: treat as its default
		field = frappe.get_meta("POS Settings").get_field(OFFLINE_OVERSHOOT_FIELD)
		value = field.default if field else None
	return value != OFFLINE_OVERSHOOT_REJECT


def decrement_coupon_usage(coupon_code: str) -> None:
	"""Release one use of the POS Coupon with this code, in one atomic UPDATE (never below 0)."""
	name = resolve_coupon_name(coupon_code)
	if not name:
		return
	coupon = frappe.qb.DocType("POS Coupon")
	(
		frappe.qb.update(coupon)
		.set(coupon.used, coupon.used - 1)
		.where(coupon.name == name)
		.where(coupon.used > 0)
	).run()


def _sale_coupon_code(doc) -> str:
	"""The saved coupon_code of a sale that should count usage ('' for returns)."""
	if cint(doc.get("is_return")):
		return ""
	return (doc.get("coupon_code") or "").strip()


def _failed_checks(doc, coupon) -> list[tuple[str, str]]:
	"""(check, translated reason) for each coupon check this sale fails, read under the row lock."""
	failed = []
	error = coupon_validity_error(coupon, customer=doc.get("customer"), company=doc.get("company"))
	if error:
		failed.append((CHECK_VALIDITY, error))
	if cint(coupon.maximum_use) and cint(coupon.used) >= cint(coupon.maximum_use):
		failed.append(
			(LIMIT_MAXIMUM_USE, _("Coupon {0} has reached its usage limit").format(coupon.coupon_code))
		)
	per_customer = _get_per_customer_use_limit(coupon)
	if per_customer and doc.get("customer"):
		used = _get_customer_coupon_usage_count(
			doc.customer, coupon.coupon_code, exclude_name=doc.name, lock=True
		)
		if used >= per_customer:
			failed.append(
				(
					LIMIT_PER_CUSTOMER,
					_("Customer {0} has already used coupon {1} the maximum number of times").format(
						doc.customer, coupon.coupon_code
					),
				)
			)
	return failed


def count_usage_on_submit(doc, method=None) -> None:
	"""Sales Invoice on_submit: count the coupon the saved invoice still carries.

	Every validate hook has run by now, so a coupon dropped in favour of a
	better discount is no longer on the invoice and is not counted.

	The POS Coupon row is locked (FOR UPDATE) while the coupon is re-checked
	(validity, maximum_use, and the per-customer count as a locking read) and
	``used`` is incremented, so concurrent submits are serialised. An online
	sale that fails a check is rejected. An offline sale being synced follows
	POS Settings offline_coupon_overshoot: "Reject" rejects it the same way,
	otherwise it is counted and every skipped check is written to Error Log.
	"""
	code = _sale_coupon_code(doc)
	name = resolve_coupon_name(code) if code else None
	if not name:
		return

	fields = list(_SUBMIT_COUPON_FIELDS)
	if frappe.get_meta("POS Coupon").has_field(LIMIT_PER_CUSTOMER):
		fields.append(LIMIT_PER_CUSTOMER)
	coupon = frappe.db.get_value("POS Coupon", name, fields, as_dict=True, for_update=True)

	failed = _failed_checks(doc, coupon)
	if failed:
		if not doc.flags.pos_offline_sync or not offline_overshoot_allowed(doc.get("pos_profile")):
			frappe.throw(failed[0][1], title=_("Coupon Not Applicable"))
		frappe.log_error(
			title=COUPON_OVERSHOOT_LOG_TITLE,
			message=(
				f"Coupon: {coupon.coupon_code}\n{doc.doctype}: {doc.name}\n"
				f"Customer: {doc.get('customer')}\n"
				f"Checks skipped: {', '.join(check for check, _reason in failed)}\n"
				+ "\n".join(f"{check}: {reason}" for check, reason in failed)
			),
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)

	pos_coupon = frappe.qb.DocType("POS Coupon")
	(
		frappe.qb.update(pos_coupon).set(pos_coupon.used, pos_coupon.used + 1).where(pos_coupon.name == name)
	).run()


def release_usage_on_cancel(doc, method=None) -> None:
	"""Sales Invoice on_cancel: release the use counted on submit."""
	code = _sale_coupon_code(doc)
	if code:
		decrement_coupon_usage(code)
