# Copyright (c) 2021, Youssef Restom and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import strip, flt, add_days, today


class ReferralCode(Document):
    def autoname(self):
        if not self.referral_name:
            self.referral_name = strip(self.customer) + "-" + frappe.generate_hash()[:5].upper()
            self.name = self.referral_name
        else:
            self.referral_name = strip(self.referral_name)
            self.name = self.referral_name

        if not self.referral_code:
            self.referral_code = frappe.generate_hash()[:10].upper()

    def validate(self):
        # Validate Referrer (Primary Customer) rewards
        if not self.referrer_discount_type:
            frappe.throw(_("Referrer Discount Type is required"))

        if self.referrer_discount_type == "Percentage":
            if not self.referrer_discount_percentage:
                frappe.throw(_("Referrer Discount Percentage is required"))
            if flt(self.referrer_discount_percentage) <= 0 or flt(self.referrer_discount_percentage) > 100:
                frappe.throw(_("Referrer Discount Percentage must be between 0 and 100"))
        elif self.referrer_discount_type == "Amount":
            if not self.referrer_discount_amount:
                frappe.throw(_("Referrer Discount Amount is required"))
            if flt(self.referrer_discount_amount) <= 0:
                frappe.throw(_("Referrer Discount Amount must be greater than 0"))

        # Validate Referee (New Customer) rewards
        if not self.referee_discount_type:
            frappe.throw(_("Referee Discount Type is required"))

        if self.referee_discount_type == "Percentage":
            if not self.referee_discount_percentage:
                frappe.throw(_("Referee Discount Percentage is required"))
            if flt(self.referee_discount_percentage) <= 0 or flt(self.referee_discount_percentage) > 100:
                frappe.throw(_("Referee Discount Percentage must be between 0 and 100"))
        elif self.referee_discount_type == "Amount":
            if not self.referee_discount_amount:
                frappe.throw(_("Referee Discount Amount is required"))
            if flt(self.referee_discount_amount) <= 0:
                frappe.throw(_("Referee Discount Amount must be greater than 0"))


def create_referral_code(company, customer, referrer_discount_type, referrer_discount_percentage=None,
                        referrer_discount_amount=None, referee_discount_type="Percentage",
                        referee_discount_percentage=None, referee_discount_amount=None, campaign=None):
    """
    Create a new referral code with discount configuration

    Args:
        company: Company name
        customer: Referrer customer ID
        referrer_discount_type: "Percentage" or "Amount" for referrer reward
        referrer_discount_percentage: Percentage discount for referrer (if type is Percentage)
        referrer_discount_amount: Fixed amount discount for referrer (if type is Amount)
        referee_discount_type: "Percentage" or "Amount" for referee reward
        referee_discount_percentage: Percentage discount for referee (if type is Percentage)
        referee_discount_amount: Fixed amount discount for referee (if type is Amount)
        campaign: Optional campaign name
    """
    doc = frappe.new_doc("Referral Code")
    doc.company = company
    doc.customer = customer
    doc.campaign = campaign

    # Referrer rewards
    doc.referrer_discount_type = referrer_discount_type
    doc.referrer_discount_percentage = referrer_discount_percentage
    doc.referrer_discount_amount = referrer_discount_amount

    # Referee rewards
    doc.referee_discount_type = referee_discount_type
    doc.referee_discount_percentage = referee_discount_percentage
    doc.referee_discount_amount = referee_discount_amount

    doc.insert()
    frappe.db.commit()
    return doc


def apply_referral_code(referral_code, referee_customer):
    """
    Apply a referral code - generates coupons for both referrer and referee

    Args:
        referral_code: The referral code to apply
        referee_customer: The new customer using the referral code

    Returns:
        dict with generated coupons info
    """
    # Get referral code document
    if not frappe.db.exists("Referral Code", {"referral_code": referral_code.upper()}):
        frappe.throw(_("Invalid referral code"))

    referral = frappe.get_doc("Referral Code", {"referral_code": referral_code.upper()})

    # Check if disabled
    if referral.disabled:
        frappe.throw(_("This referral code has been disabled"))

    # Check if referee has already used this referral code
    existing_coupon = frappe.db.exists("POS Coupon", {
        "referral_code": referral.name,
        "customer": referee_customer,
        "coupon_type": "Promotional"
    })

    if existing_coupon:
        frappe.throw(_("You have already used this referral code"))

    result = {
        "referrer_coupon": None,
        "referee_coupon": None
    }

    # Generate Gift Card coupon for referrer (primary customer)
    try:
        referrer_coupon = generate_referrer_coupon(referral)
        result["referrer_coupon"] = {
            "name": referrer_coupon.name,
            "coupon_code": referrer_coupon.coupon_code,
            "customer": referrer_coupon.customer
        }
    except Exception as e:
        frappe.log_error(
            title="Referrer Coupon Generation Failed",
            message=f"Failed to generate referrer coupon: {str(e)}"
        )

    # Generate Promotional coupon for referee (new customer)
    try:
        referee_coupon = generate_referee_coupon(referral, referee_customer)
        result["referee_coupon"] = {
            "name": referee_coupon.name,
            "coupon_code": referee_coupon.coupon_code,
            "customer": referee_customer
        }
    except Exception as e:
        frappe.log_error(
            title="Referee Coupon Generation Failed",
            message=f"Failed to generate referee coupon: {str(e)}"
        )
        frappe.throw(_("Failed to generate your welcome coupon"))

    # Increment referrals count
    referral.referrals_count = (referral.referrals_count or 0) + 1
    referral.save()
    frappe.db.commit()

    return result


def generate_referrer_coupon(referral):
    """Generate a Gift Card coupon for the referrer"""
    coupon = frappe.new_doc("POS Coupon")

    # Calculate validity dates
    valid_from = today()
    valid_days = referral.referrer_coupon_valid_days or 30
    valid_upto = add_days(valid_from, valid_days)

    coupon.update({
        "coupon_name": f"Referral Reward - {referral.customer} - {frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')}",
        "coupon_type": "Gift Card",
        "customer": referral.customer,
        "company": referral.company,
        "campaign": referral.campaign,
        "referral_code": referral.name,

        # Discount configuration
        "discount_type": referral.referrer_discount_type,
        "discount_percentage": flt(referral.referrer_discount_percentage) if referral.referrer_discount_type == "Percentage" else None,
        "discount_amount": flt(referral.referrer_discount_amount) if referral.referrer_discount_type == "Amount" else None,
        "min_amount": flt(referral.referrer_min_amount) if referral.referrer_min_amount else None,
        "max_amount": flt(referral.referrer_max_amount) if referral.referrer_max_amount else None,
        "apply_on": "Grand Total",

        # Validity
        "valid_from": valid_from,
        "valid_upto": valid_upto,
        "maximum_use": 1,  # Gift cards are single-use
        "one_use": 1,
    })

    coupon.insert()
    return coupon


def generate_referee_coupon(referral, referee_customer):
    """Generate a Promotional coupon for the referee (new customer)"""
    coupon = frappe.new_doc("POS Coupon")

    # Calculate validity dates
    valid_from = today()
    valid_days = referral.referee_coupon_valid_days or 30
    valid_upto = add_days(valid_from, valid_days)

    coupon.update({
        "coupon_name": f"Welcome Referral - {referee_customer} - {frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')}",
        "coupon_type": "Promotional",
        "customer": referee_customer,
        "company": referral.company,
        "campaign": referral.campaign,
        "referral_code": referral.name,

        # Discount configuration
        "discount_type": referral.referee_discount_type,
        "discount_percentage": flt(referral.referee_discount_percentage) if referral.referee_discount_type == "Percentage" else None,
        "discount_amount": flt(referral.referee_discount_amount) if referral.referee_discount_type == "Amount" else None,
        "min_amount": flt(referral.referee_min_amount) if referral.referee_min_amount else None,
        "max_amount": flt(referral.referee_max_amount) if referral.referee_max_amount else None,
        "apply_on": "Grand Total",

        # Validity
        "valid_from": valid_from,
        "valid_upto": valid_upto,
        "maximum_use": 1,  # One-time use for referee
        "one_use": 1,
    })

    coupon.insert()
    return coupon
