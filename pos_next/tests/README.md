# POS Next Test Suite - ERPNext Coupon Code Integration

This directory contains the test suite for the gift card and coupon refactoring that migrates from `POS Coupon` to native `ERPNext Coupon Code`.

## Test Modules

### 1. `test_gift_cards.py`
Tests for `pos_next/api/gift_cards.py`:
- **TestGiftCardCodeGeneration** - Gift card code format and uniqueness
- **TestManualGiftCardCreation** - Manual gift card creation from ERPNext UI
- **TestGiftCardApplication** - Applying gift cards to invoices
- **TestGiftCardBalanceUpdate** - Balance updates after usage
- **TestGetGiftCardsWithBalance** - Retrieving available gift cards
- **TestPricingRuleCreation** - Pricing Rule creation for gift cards

### 2. `test_coupon_validation.py`
Tests for `pos_next/api/offers.py`:
- **TestGetActiveCoupons** - Retrieve available gift cards
- **TestValidateCoupon** - Validate coupon codes
- **TestCouponValidityDates** - Expiry and validity date handling

### 3. `test_promotions_coupon.py`
Tests for `pos_next/api/promotions.py`:
- **TestCreateCoupon** - Create promotional coupons
- **TestUpdateCoupon** - Update existing coupons
- **TestDeleteCoupon** - Delete coupons
- **TestGetReferralDetails** - Get referral code details

### 4. `test_referral_code.py`
Tests for `pos_next/pos_next/doctype/referral_code/referral_code.py`:
- **TestReferralCodeCreation** - Create referral codes
- **TestReferralCouponGeneration** - Generate coupons for referrer/referee
- **TestApplyReferralCode** - Apply referral codes
- **TestReferralCodeValidation** - Validation rules

## Running Tests

### Run All Tests
```bash
bench --site [site] execute pos_next.tests.run_all_tests.run_all_tests
```

### Run Individual Test Modules
```bash
# Gift Card Tests
bench --site [site] run-tests --app pos_next --module pos_next.tests.test_gift_cards

# Coupon Validation Tests
bench --site [site] run-tests --app pos_next --module pos_next.tests.test_coupon_validation

# Promotions Tests
bench --site [site] run-tests --app pos_next --module pos_next.tests.test_promotions_coupon

# Referral Code Tests
bench --site [site] run-tests --app pos_next --module pos_next.pos_next.doctype.referral_code.test_referral_code
```

### Run Specific Test Class
```bash
bench --site [site] run-tests --app pos_next --module pos_next.tests.test_gift_cards --test pos_next.tests.test_gift_cards.TestGiftCardCodeGeneration
```

## Test Requirements

- At least one Company must exist
- At least one Customer must exist (for customer-specific tests)
- POS Profile with gift card settings (for invoice-based tests)

## Test Coverage

| Feature | Test File | Coverage |
|---------|-----------|----------|
| Gift Card Creation | test_gift_cards.py | ✓ Manual creation, From invoice |
| Gift Card Application | test_gift_cards.py | ✓ Partial, Full, Exceeds balance |
| Gift Card Splitting | test_gift_cards.py | ✓ Balance updates |
| Coupon Validation | test_coupon_validation.py | ✓ Valid, Invalid, Expired |
| Pricing Rule | test_gift_cards.py | ✓ Creation, Updates |
| Referral Coupons | test_referral_code.py | ✓ Referrer, Referee generation |
| Coupon CRUD | test_promotions_coupon.py | ✓ Create, Update, Delete |

## Notes

- Tests use `frappe.db.rollback()` for cleanup where possible
- Test data is cleaned up in `tearDownClass` methods
- Some tests may be skipped if prerequisites (customers, etc.) are not available
