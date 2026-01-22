# RCM Tax Filtering - Issue and Fix

## The Issue

**Error**: `ValidationError: Cannot use Reverse Charge Account in Row #2 since transaction is without Reverse Charge`

**Root Cause**: 
- The tax template "Output GST RCM Out-state - TJCPL" contains both:
  1. Regular IGST: "Output Tax IGST - TJCPL" (18%)
  2. RCM IGST: "Output Tax IGST RCM - TJCPL" (-18% or with different logic)

- RCM (Reverse Charge Mechanism) taxes should ONLY be used when `is_reverse_charge = 1`
- For normal POS sales, `is_reverse_charge = 0` (default)
- India Compliance validates this and throws an error if RCM accounts are used without reverse charge

## Why This Happened

1. **Tax Template Selection**: The template "Output GST RCM Out-state - TJCPL" was selected (either manually in POS Profile or auto-detected)
2. **Tax Loading**: When taxes are loaded from this template, BOTH regular and RCM taxes are included
3. **Validation Error**: India Compliance's `validate_reverse_charge_accounts()` checks if RCM accounts are used without `is_reverse_charge = 1` and throws an error

## The Fix

We now filter out RCM taxes in **3 places**:

### 1. In `update_invoice()` (after loading taxes)
- Filters RCM taxes after `set_taxes()` loads them
- Prevents RCM taxes from being included in the invoice

### 2. In `validate()` hook
- Filters RCM taxes before setting `included_in_print_rate`
- Ensures only non-RCM taxes are processed

### 3. In `before_save()` hook
- Final check before document is saved
- Catches any RCM taxes that might have been added during save

### 4. In `get_tax_template_from_category()` (prevention)
- When auto-detecting templates, excludes RCM templates
- Prefers non-RCM templates if available

## How RCM Taxes Are Identified

1. **India Compliance Method** (preferred):
   - Uses `get_gst_accounts_by_type(company, "Sales Reverse Charge")` to get list of RCM accounts
   - Checks if `tax.account_head` is in the RCM accounts list

2. **Pattern Matching** (fallback):
   - Checks if account name contains "RCM" (case-insensitive)
   - Example: "Output Tax IGST RCM - TJCPL" → RCM tax

## Result

- Normal POS sales: Only regular taxes (IGST, CGST, SGST) are used
- RCM taxes are automatically filtered out
- No validation errors
- Taxes are calculated correctly

## Testing

After `bench restart`, create an invoice with:
- Tax template: "Output GST RCM Out-state - TJCPL"
- `is_reverse_charge = 0` (default)

Expected result:
- Only "Output Tax IGST - TJCPL" is included
- "Output Tax IGST RCM - TJCPL" is filtered out
- No validation error
- Taxes are calculated correctly
