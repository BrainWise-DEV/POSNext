# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, add_days


class ReferralCode(Document):
    """
    Manages Referral Codes for customer acquisition campaigns.
    Generates unique referral codes and tracks their usage.
    """

    def autoname(self):
        """Generate unique referral code if not provided."""
        if not self.referral_code:
            self.referral_code = frappe.generate_hash()[:10].upper()

    def validate(self):
        """Validate referral configuration."""
        self.validate_referrer_discounts()
        self.validate_referee_discounts()

    def validate_referrer_discounts(self):
        """Validate rewards for the referrer (existing customer)."""
        if not self.referrer_discount_type:
            frappe.throw(_("Referrer Discount Type is required"))

        if self.referrer_discount_type == "Percentage":
            if flt(self.referrer_discount_percentage) <= 0 or flt(self.referrer_discount_percentage) > 100:
                frappe.throw(_("Referrer Discount Percentage must be between 0 and 100"))
        elif self.referrer_discount_type == "Amount":
            if flt(self.referrer_discount_amount) <= 0:
                frappe.throw(_("Referrer Discount Amount must be greater than 0"))

    def validate_referee_discounts(self):
        """Validate rewards for the referee (new customer)."""
        if not self.referee_discount_type:
            frappe.throw(_("Referee Discount Type is required"))

        if self.referee_discount_type == "Percentage":
            if flt(self.referee_discount_percentage) <= 0 or flt(self.referee_discount_percentage) > 100:
                frappe.throw(_("Referee Discount Percentage must be between 0 and 100"))
        elif self.referee_discount_type == "Amount":
            if flt(self.referee_discount_amount) <= 0:
                frappe.throw(_("Referee Discount Amount must be greater than 0"))


def create_referral_code(company, customer, referrer_discount_type, referrer_discount_percentage=None,
                        referrer_discount_amount=None, referee_discount_type="Percentage",
                        referee_discount_percentage=None, referee_discount_amount=None, campaign=None):
    """
    Factory function to create a new referral code for a customer.
    Returns existing code if one is already active for this customer/company pair.
    """
    # Validation
    if not customer or not company:
        frappe.throw(_("Customer and Company are required"))

    # Check existing
    existing = frappe.db.get_value("Referral Code", {"customer": customer, "company": company, "enabled": 1}, "referral_code")
    if existing:
        return frappe.get_doc("Referral Code", {"referral_code": existing})

    doc = frappe.new_doc("Referral Code")
    doc.update({
        "customer": customer,
        "company": company,
        "referrer_discount_type": referrer_discount_type,
        "referrer_discount_percentage": referrer_discount_percentage,
        "referrer_discount_amount": referrer_discount_amount,
        "referee_discount_type": referee_discount_type,
        "referee_discount_percentage": referee_discount_percentage,
        "referee_discount_amount": referee_discount_amount,
        "campaign_name": campaign,
        "enabled": 1
    })

    doc.insert(ignore_permissions=True)
    return doc


def apply_referral_code(referral_code, referee_customer):
    """
    Apply a referral code for a new customer (referee).
    - Validates the code.
    - Prevents self-referral.
    - Prevents duplicate usage (one referral per customer).
    - Generates coupons for both parties.
    """
    if not referral_code:
        return {"valid": False, "message": _("Referral code is required")}

    referral_name = frappe.db.get_value("Referral Code", {"referral_code": referral_code, "enabled": 1})
    if not referral_name:
        return {"valid": False, "message": _("Invalid referral code")}

    referral = frappe.get_doc("Referral Code", referral_name)

    # Validate usage
    if referral.customer == referee_customer:
        return {"valid": False, "message": _("You cannot refer yourself")}

    # Check if this customer has already been referred by this code (prevent duplicate coupons)
    existing_coupon = frappe.db.exists("POS Coupon", {
        "customer": referee_customer,
        "coupon_type": "Promotional",
        "coupon_name": ["like", f"Ref-{referral.referral_code}%"]
    })

    if existing_coupon:
        return {"valid": False, "message": _("You have already used this referral code")}

    # Generate Referee Coupon (Immediate use)
    referee_coupon = generate_referee_coupon(referral, referee_customer)

    # Generate Referrer Coupon (Reward)
    referrer_coupon = generate_referrer_coupon(referral)

    # Update stats
    referral.total_referrals = (referral.total_referrals or 0) + 1
    referral.save(ignore_permissions=True)

    return {
        "valid": True,
        "referee_coupon": referee_coupon.coupon_code,
        "referrer_coupon": referrer_coupon.coupon_code
    }


def generate_referrer_coupon(referral):
    """Generate a Gift Card for the referrer (existing customer)"""
    return generate_coupon_from_referral(
        referral,
        recipient_customer=referral.customer,
        coupon_type="Gift Card",
        discount_type=referral.referrer_discount_type,
        percentage=referral.referrer_discount_percentage,
        amount=referral.referrer_discount_amount
    )


def generate_referee_coupon(referral, referee_customer):
    """Generate a Promotional coupon for the referee (new customer)"""
    return generate_coupon_from_referral(
        referral,
        recipient_customer=referee_customer,
        coupon_type="Promotional",
        discount_type=referral.referee_discount_type,
        percentage=referral.referee_discount_percentage,
        amount=referral.referee_discount_amount
    )

def generate_coupon_from_referral(referral, recipient_customer, coupon_type, discount_type, percentage=None, amount=None):
    """
    Generic helper to create a POS Coupon from referral data.
    Sets validity to 30 days and enforces single use.
    """
    coupon = frappe.new_doc("POS Coupon")
    # Store referral code in name for tracking/uniqueness check
    coupon.coupon_name = f"Ref-{referral.referral_code}-{coupon_type[:4]}-{frappe.generate_hash()[:5]}"
    coupon.coupon_type = coupon_type
    coupon.company = referral.company
    coupon.customer = recipient_customer

    coupon.discount_type = discount_type
    if discount_type == "Percentage":
        coupon.discount_percentage = percentage
    else:
        coupon.discount_amount = amount

    # Validity defaults (e.g., 30 days)
    coupon.valid_from = nowdate()
    coupon.valid_upto = add_days(nowdate(), 30)

    # Limits
    coupon.maximum_use = 1
    coupon.one_use = 1 # One time use per customer

    coupon.insert(ignore_permissions=True)
    return coupon
