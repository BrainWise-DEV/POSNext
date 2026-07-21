# Copyright (c) 2021, Youssef Restom and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, strip, today

ONE_USE_COUPON_DOCTYPES = ("Sales Invoice", "POS Invoice")


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

		# Scope validations
		apply_scope = self.apply_scope or "All Eligible Items"
		if apply_scope == "Brand" and not self.applicable_brand:
			frappe.throw(_("Applicable Brand is required when Apply Scope is Brand"))
		if apply_scope == "Item Group" and not self.applicable_item_group:
			frappe.throw(_("Applicable Collection is required when Apply Scope is Item Group"))

		if self.maximum_use_per_customer and cint(self.maximum_use_per_customer) < 0:
			frappe.throw(_("Uses Per Customer cannot be negative"))


def check_coupon_code(coupon_code, customer=None, company=None):
	"""Validate and return coupon details"""
	res = {"coupon": None}

	if not frappe.db.exists("POS Coupon", {"coupon_code": coupon_code.upper()}):
		res["msg"] = _("Sorry, this coupon code does not exist")
		return res

	coupon = frappe.get_doc("POS Coupon", {"coupon_code": coupon_code.upper()})

	# Check if coupon is disabled
	if coupon.disabled:
		res["msg"] = _("Sorry, this coupon has been disabled")
		return res

	# Check validity dates
	if coupon.valid_from:
		if coupon.valid_from > getdate(today()):
			res["msg"] = _("Sorry, this coupon code's validity has not started")
			return res

	if coupon.valid_upto:
		if coupon.valid_upto < getdate(today()):
			res["msg"] = _("Sorry, this coupon code has expired")
			return res

	# Check usage limits
	if coupon.used and coupon.maximum_use and coupon.used >= coupon.maximum_use:
		res["msg"] = _("Sorry, this coupon code has been fully redeemed")
		return res

	# Check company
	if company and coupon.company != company:
		res["msg"] = _("Sorry, this coupon is not valid for this company")
		return res

	# Check customer (for Gift Cards)
	if coupon.coupon_type == "Gift Card" and coupon.customer:
		if not customer or coupon.customer != customer:
			res["msg"] = _("Sorry, this gift card is assigned to a specific customer")
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


def _get_per_customer_use_limit(coupon):
	"""Resolve max uses per customer. one_use implies 1 when maximum_use_per_customer is unset."""
	limit = cint(getattr(coupon, "maximum_use_per_customer", 0) or 0)
	if limit > 0:
		return limit
	if cint(getattr(coupon, "one_use", 0) or 0):
		return 1
	return 0


def _get_customer_coupon_usage_count(customer, coupon_code):
	"""Count submitted coupon usage across POSNext's actual sales doctypes."""
	used_count = 0

	for doctype in ONE_USE_COUPON_DOCTYPES:
		if not frappe.db.table_exists(doctype):
			continue

		meta = frappe.get_meta(doctype)
		if not meta.has_field("coupon_code"):
			continue

		used_count += frappe.db.count(
			doctype,
			filters={
				"customer": customer,
				"coupon_code": coupon_code,
				"docstatus": 1,
			},
		)

	return used_count


def _has_pricing_rules(item):
	"""True when the line already has offer/pricing-rule linkage."""
	pricing_rules = item.get("pricing_rules")
	if not pricing_rules:
		return False
	if isinstance(pricing_rules, str):
		return bool(pricing_rules.strip())
	if isinstance(pricing_rules, (list, tuple)):
		return len(pricing_rules) > 0
	return True


def _item_already_discounted(item):
	"""Exclusion: item already has another discount applied."""
	if flt(item.get("discount_percentage") or 0) > 0:
		return True
	if flt(item.get("discount_amount") or 0) > 0:
		return True
	if _has_pricing_rules(item):
		return True
	# Manual rate below list price
	price_list_rate = flt(item.get("price_list_rate") or 0)
	rate = flt(item.get("rate") or 0)
	if price_list_rate > 0 and rate > 0 and rate < price_list_rate:
		return True
	return False


def _get_excluded_brands(coupon):
	excluded = set()
	rows = getattr(coupon, "excluded_brands", None)
	if rows is None and hasattr(coupon, "get"):
		rows = coupon.get("excluded_brands")
	for row in rows or []:
		brand = row.get("brand") if isinstance(row, dict) else getattr(row, "brand", None)
		if brand:
			excluded.add(brand)
	return excluded


def _item_matches_scope(coupon, item):
	apply_scope = getattr(coupon, "apply_scope", None) or "All Eligible Items"
	if apply_scope == "Brand":
		return bool(item.get("brand")) and item.get("brand") == coupon.applicable_brand
	if apply_scope == "Item Group":
		return bool(item.get("item_group")) and item.get("item_group") == coupon.applicable_item_group
	return True


def _item_line_key(item, index):
	"""Stable 0-based cart position for matching line_updates on the client."""
	return index


def _item_base_amount(item):
	"""Undiscounted line amount used for coupon eligible subtotal."""
	qty = flt(item.get("qty") or item.get("quantity") or 0)
	price_list_rate = flt(item.get("price_list_rate") or 0)
	if price_list_rate > 0 and qty > 0:
		return price_list_rate * qty
	amount = flt(item.get("amount") or 0)
	if amount > 0:
		return amount
	rate = flt(item.get("rate") or 0)
	return rate * qty


def get_coupon_eligible_items(coupon, items):
	"""
	Return cart items that pass exclusion rules and scope checks.

	Exclusion rules:
	1. Already discounted lines (when exclude_already_discounted_items is enabled)
	2-3. Free items and promo-trigger lines (pricing_rules / is_free_item)
	4. Excluded brands
	"""
	if not items:
		return []

	from pos_next.api.promotion_exclusions import is_already_discounted, mark_item_discount_flags

	exclude_discounted = cint(getattr(coupon, "exclude_already_discounted_items", 1))
	prepared_items = [frappe._dict(row) for row in items]
	if exclude_discounted:
		mark_item_discount_flags(prepared_items)

	excluded_brands = _get_excluded_brands(coupon)
	eligible = []

	for index, raw in enumerate(prepared_items):
		item = raw if isinstance(raw, dict) else dict(raw)
		# Skip free items and promo-linked lines
		if cint(item.get("is_free_item") or 0):
			continue
		if exclude_discounted and (
			is_already_discounted(item) or _item_already_discounted(item)
		):
			# Allow re-evaluating lines already tagged with this same coupon
			existing_coupon = (item.get("coupon_code") or "").upper()
			this_code = (coupon.coupon_code or "").upper()
			if not (existing_coupon and this_code and existing_coupon == this_code):
				continue
		if item.get("brand") and item.get("brand") in excluded_brands:
			continue
		if not _item_matches_scope(coupon, item):
			continue

		item = dict(item)
		item["_line_key"] = _item_line_key(item, index)
		item["_base_amount"] = _item_base_amount(item)
		if flt(item["_base_amount"]) <= 0:
			continue
		eligible.append(item)

	return eligible


def apply_coupon_to_items(coupon, items):
	"""
	Calculate per-line coupon discounts for eligible items.

	Returns dict with valid, message, eligible_item_codes, line_updates, total_discount.
	"""
	eligible = get_coupon_eligible_items(coupon, items)
	if not eligible:
		return {
			"valid": False,
			"message": _("No eligible items for this coupon"),
			"eligible_item_codes": [],
			"line_updates": [],
			"total_discount": 0,
		}

	eligible_subtotal = sum(flt(i["_base_amount"]) for i in eligible)

	if coupon.min_amount and flt(eligible_subtotal) < flt(coupon.min_amount):
		return {
			"valid": False,
			"message": _("Minimum eligible amount of {0} is required").format(
				frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})
			),
			"eligible_item_codes": [i.get("item_code") for i in eligible],
			"line_updates": [],
			"total_discount": 0,
		}

	line_updates = []
	total_discount = 0.0

	if coupon.discount_type == "Percentage":
		pct = flt(coupon.discount_percentage)
		for item in eligible:
			base = flt(item["_base_amount"])
			line_discount = flt(base) * pct / 100.0
			total_discount += line_discount
			qty = flt(item.get("qty") or item.get("quantity") or 0) or 1
			price_list_rate = flt(item.get("price_list_rate") or 0)
			if price_list_rate <= 0:
				price_list_rate = flt(item.get("rate") or 0) or (base / qty)
			new_rate = price_list_rate * (1 - pct / 100.0)
			line_updates.append(
				{
					"line_key": item["_line_key"],
					"item_code": item.get("item_code"),
					"discount_percentage": pct,
					"discount_amount": 0,
					"rate": flt(new_rate, 6),
					"amount": flt(new_rate * qty, 6),
					"coupon_code": coupon.coupon_code,
				}
			)

		# When max_amount is configured, always materialize as absolute amounts.
		# Otherwise local qty changes recalculate % and can exceed the cap before
		# the next server revalidation.
		if coupon.max_amount:
			cap = flt(coupon.max_amount)
			scale = 1.0
			if total_discount > cap and total_discount:
				scale = cap / total_discount
				total_discount = cap
			for update in line_updates:
				base_amount = next(
					(flt(i["_base_amount"]) for i in eligible if i["_line_key"] == update["line_key"]),
					0,
				)
				line_discount = flt(base_amount) * pct / 100.0 * scale
				for item in eligible:
					if item["_line_key"] == update["line_key"]:
						qty = flt(item.get("qty") or item.get("quantity") or 0) or 1
						new_amount = max(base_amount - line_discount, 0)
						update["discount_percentage"] = 0
						update["discount_amount"] = flt(line_discount, 6)
						update["rate"] = flt(new_amount / qty, 6) if qty else 0
						update["amount"] = flt(new_amount, 6)
						break
	else:
		# Fixed amount distributed across eligible lines by share of subtotal
		total_discount = flt(coupon.discount_amount)
		if coupon.max_amount and total_discount > flt(coupon.max_amount):
			total_discount = flt(coupon.max_amount)
		if total_discount > eligible_subtotal:
			total_discount = eligible_subtotal

		allocated = 0.0
		for index, item in enumerate(eligible):
			base = flt(item["_base_amount"])
			if index == len(eligible) - 1:
				line_discount = flt(total_discount - allocated, 6)
			else:
				share = base / eligible_subtotal if eligible_subtotal else 0
				line_discount = flt(total_discount * share, 6)
				allocated += line_discount

			qty = flt(item.get("qty") or item.get("quantity") or 0) or 1
			price_list_rate = flt(item.get("price_list_rate") or 0)
			if price_list_rate <= 0:
				price_list_rate = flt(item.get("rate") or 0) or (base / qty)
			# Convert line discount amount into effective rate
			new_amount = max(base - line_discount, 0)
			new_rate = new_amount / qty if qty else 0
			line_updates.append(
				{
					"line_key": item["_line_key"],
					"item_code": item.get("item_code"),
					"discount_percentage": 0,
					"discount_amount": flt(line_discount, 6),
					"rate": flt(new_rate, 6),
					"amount": flt(new_amount, 6),
					"coupon_code": coupon.coupon_code,
				}
			)

	return {
		"valid": True,
		"message": _("Coupon applied successfully"),
		"eligible_item_codes": [i.get("item_code") for i in eligible],
		"line_updates": line_updates,
		"total_discount": flt(total_discount, 6),
		"eligible_subtotal": flt(eligible_subtotal, 6),
	}


def apply_coupon_discount(coupon, cart_total, net_total=None, items=None, tax_amount=0):
	"""Calculate discount amount based on coupon configuration (legacy cart-level helper)."""
	from pos_next.api.promotion_exclusions import (
		get_eligible_subtotal,
		get_excluded_subtotal,
		mark_item_discount_flags,
	)

	prepared_items = [frappe._dict(row) for row in (items or [])]
	if prepared_items:
		mark_item_discount_flags(prepared_items)

	exclude_discounted = cint(getattr(coupon, "exclude_already_discounted_items", 1))

	if prepared_items and exclude_discounted:
		if coupon.apply_on == "Grand Total":
			eligible_base = get_eligible_subtotal(prepared_items, exclude_discounted=True)
			eligible_base += flt(tax_amount) if flt(tax_amount) > 0 else 0
			excluded_base = get_excluded_subtotal(prepared_items)
		else:
			eligible_base = get_eligible_subtotal(prepared_items, exclude_discounted=True)
			excluded_base = get_excluded_subtotal(prepared_items)
		base_amount = eligible_base
	else:
		base_amount = cart_total if coupon.apply_on == "Grand Total" else (net_total or cart_total)
		eligible_base = base_amount
		excluded_base = 0

	# Check minimum amount
	if coupon.min_amount and flt(base_amount) < flt(coupon.min_amount):
		return {
			"valid": False,
			"message": _("Minimum cart amount of {0} is required").format(
				frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})
			),
			"discount": 0,
			"eligible_subtotal": eligible_base,
			"excluded_subtotal": excluded_base,
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
		"eligible_subtotal": eligible_base,
		"excluded_subtotal": excluded_base,
	}


def increment_coupon_usage(coupon_code):
	"""Increment the usage counter for a coupon"""
	try:
		coupon = frappe.get_doc("POS Coupon", {"coupon_code": coupon_code.upper()})
		coupon.used = (coupon.used or 0) + 1
		coupon.db_set("used", coupon.used)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			title="Coupon Usage Increment Failed",
			message=f"Failed to increment usage for coupon {coupon_code}: {e!s}",
		)


def decrement_coupon_usage(coupon_code):
	"""Decrement the usage counter for a coupon (for cancelled invoices)"""
	try:
		coupon = frappe.get_doc("POS Coupon", {"coupon_code": coupon_code.upper()})
		if coupon.used and coupon.used > 0:
			coupon.used = coupon.used - 1
			coupon.db_set("used", coupon.used)
			frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			title="Coupon Usage Decrement Failed",
			message=f"Failed to decrement usage for coupon {coupon_code}: {e!s}",
		)
