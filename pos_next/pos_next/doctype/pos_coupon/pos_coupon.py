# Copyright (c) 2021, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import strip, flt
from frappe.utils import getdate, today


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

    # Check one-time use per customer
    if coupon.one_use and customer:
        used_count = _get_customer_coupon_usage_count(customer, coupon.coupon_code)
        if used_count > 0:
            res["msg"] = _("Sorry, you have already used this coupon code")
            return res

    # All validations passed
    res["coupon"] = coupon
    res["valid"] = True

    return res


def _get_customer_coupon_usage_count(customer, coupon_code):
    """Count submitted coupon usage across POSNext's actual sales doctypes."""
    used_count = 0

    for doctype in ONE_USE_COUPON_DOCTYPES:
        if not frappe.db.table_exists(doctype):
            continue

        meta = frappe.get_meta(doctype)
        if not meta.has_field("coupon_code"):
            continue

        used_count += frappe.db.count(doctype, filters={
            "customer": customer,
            "coupon_code": coupon_code,
            "docstatus": 1,
        })

    return used_count


def apply_coupon_discount(coupon, cart_total, net_total=None):
    """Calculate discount amount based on coupon configuration"""
    from frappe.utils import flt

    # Determine the base amount for discount calculation
    base_amount = cart_total if coupon.apply_on == "Grand Total" else (net_total or cart_total)

    # Check minimum amount
    if coupon.min_amount and flt(base_amount) < flt(coupon.min_amount):
        return {
            "valid": False,
            "message": _("Minimum cart amount of {0} is required").format(frappe.format_value(coupon.min_amount, {"fieldtype": "Currency"})),
            "discount": 0
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
        "apply_on": coupon.apply_on
    }


def increment_coupon_usage(coupon_code):
    """Increment the usage counter for a coupon"""
    try:
        coupon = frappe.get_doc("POS Coupon", {"coupon_code": coupon_code.upper()})
        coupon.used = (coupon.used or 0) + 1
        coupon.db_set('used', coupon.used)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            title="Coupon Usage Increment Failed",
            message=f"Failed to increment usage for coupon {coupon_code}: {str(e)}"
        )


def decrement_coupon_usage(coupon_code):
    """Decrement the usage counter for a coupon (for cancelled invoices)"""
    try:
        coupon = frappe.get_doc("POS Coupon", {"coupon_code": coupon_code.upper()})
        if coupon.used and coupon.used > 0:
            coupon.used = coupon.used - 1
            coupon.db_set('used', coupon.used)
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            title="Coupon Usage Decrement Failed",
            message=f"Failed to decrement usage for coupon {coupon_code}: {str(e)}"
        )
