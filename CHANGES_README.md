# POS Next Changes - Session Summary

## Date: January 22, 2026

---

## Overview

This document summarizes all changes made during this development session. Changes include:
1. Finance Lender Payments UI improvements
2. SQL query security fixes
3. Debug logging for GST troubleshooting
4. Sales Person section repositioning

---

## Files Changed

### 1. `POS/src/components/sale/PaymentDialog.vue`

**Purpose:** UI improvements for the payment dialog

**Changes:**
- **Finance Lender Payments UI:** Changed from card-based 2x2 grid layout to a compact single-line layout
  - Each payment entry now shows: Mode selector, Finance Lender search, Amount input, Reference No., Delete button all in one row
  - More space-efficient and easier to scan multiple entries
- **Sales Person Section:** Moved below the Finance Lender Payments "Total Summary" section
  - Previously was above Finance Lender Payments
  - Now appears after the total is displayed for better visual flow
- **Debug Logging:** Added `console.log` for account search debugging

**Lines Modified:** ~204-350 (Finance Lender section), ~352-488 (Sales Person section)

---

### 2. `POS/src/composables/useInvoice.js`

**Purpose:** Invoice creation and submission logic

**Changes:**
- **Tax Inclusive Flag:** Added `custom_is_this_tax_included_in_basic_rate` to invoice data sent to backend
  - Sends `1` when tax inclusive mode is enabled, `0` otherwise
- **Debug Logging:** Added extensive `console.log` statements for GST troubleshooting:
  - Logs Tax Inclusive Mode status
  - Logs Tax Rules configuration
  - Logs complete Invoice Data being sent
  - Logs raw items with tax calculation details

**Lines Modified:** ~714-771

```javascript
// Key addition:
custom_is_this_tax_included_in_basic_rate: taxInclusive.value ? 1 : 0,

// Debug logging:
console.log('=== POS TO SALES INVOICE DEBUG ===')
console.log('Tax Inclusive Mode:', taxInclusive.value)
console.log('Tax Rules:', JSON.stringify(taxRules.value, null, 2))
console.log('Invoice Data:', JSON.stringify(invoiceData, null, 2))
```

---

### 3. `pos_next/api/invoices.py`

**Purpose:** Backend API for creating Sales Invoices from POS

**Changes:**
- **Tax Inclusive Mode Handling:**
  - Reads `custom_is_this_tax_included_in_basic_rate` from POS data
  - Sets `included_in_print_rate = 1` on tax rows after `set_missing_values()`
  - Note: This fix is incomplete - see GST_TAX_MISMATCH_ANALYSIS.md
- **Debug Logging:** Added extensive `frappe.log_error()` statements:
  - Logs items before and after `calculate_taxes_and_totals()`
  - Logs taxes with `included_in_print_rate` status
  - Logs totals (net_total, grand_total, etc.)

**Lines Modified:** ~458-548

```python
# Key additions:
tax_inclusive = cint(data.get("custom_is_this_tax_included_in_basic_rate", 0))
if tax_inclusive:
    invoice_doc.custom_is_this_tax_included_in_basic_rate = 1

# After set_missing_values():
if tax_inclusive:
    for tax in invoice_doc.get("taxes", []):
        tax.included_in_print_rate = 1
```

---

### 4. `pos_next/api/finance_lender.py`

**Purpose:** API for searching accounts and finance lender customers

**Changes:**
- **SQL Query Fix:** Changed from `frappe.db.escape()` to parameterized queries
  - Previous approach caused SQL syntax errors because `escape()` adds quotes
  - New approach uses `%(param)s` placeholder syntax
- **Security Improvement:** Parameterized queries prevent SQL injection

**Full File (93 lines):**

```python
@frappe.whitelist()
def search_accounts(search_term="", company=None, limit=20):
    conditions = ["account_type IN ('Bank', 'Cash')", "is_group = 0"]
    params = {}

    if company:
        conditions.append("company = %(company)s")
        params["company"] = company

    if search_term:
        conditions.append("(name LIKE %(search_pattern)s OR account_name LIKE %(search_pattern)s)")
        params["search_pattern"] = f"%{search_term}%"

    # ... execute with parameterized query

@frappe.whitelist()
def search_finance_lenders(search_term="", limit=20):
    # Similar parameterized query implementation
```

---

## Known Issues / Incomplete Work

### GST Tax Mismatch Error (Not Fully Fixed)

**Status:** Root cause identified, fix proposed but not implemented

**Problem:** When tax inclusive mode is enabled in POS Settings, and the invoice amount is over Rs. 100, India Compliance throws:
> "GST amounts do not match the calculated values based on tax rates"

**Root Cause:**
- POS sends gross (tax-inclusive) rate to backend
- `included_in_print_rate = 1` is not persisting correctly
- ERPNext doesn't extract net amounts properly
- India Compliance validates `cgst_amount`/`sgst_amount` against `taxable_value` and finds mismatch

**Proposed Solution:** See `GST_TAX_MISMATCH_ANALYSIS.md` for detailed analysis and recommended fix.

---

## How to Test

### Finance Lender Payments
1. Open POS, add items to cart
2. Click Pay
3. In Payment Dialog, click "Add Entry" under Finance Lender Payments
4. Verify single-line layout: Mode | Finance Lender | Amount | Ref No. | Delete
5. Select Mode (Account or Customer)
6. Search and select a finance lender
7. Enter amount and reference number
8. Verify total summary shows correct sum

### Sales Person (if enabled in POS Settings)
1. Open Payment Dialog
2. Verify Sales Person section appears AFTER Finance Lender Total Summary
3. Search and add sales person(s)
4. Complete payment

### Account Search Fix
1. In Finance Lender Payments, select "Account" mode
2. Click in the search field
3. Verify Bank/Cash accounts appear in dropdown
4. Search for specific account name
5. Verify results filter correctly

---

## Rollback Instructions

If you need to revert these changes:

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git checkout POS/src/components/sale/PaymentDialog.vue
git checkout POS/src/composables/useInvoice.js
git checkout pos_next/api/invoices.py
git checkout pos_next/api/finance_lender.py
```

Or restore from backup if available.

---

## Additional Files Created

| File | Purpose |
|------|---------|
| `GST_TAX_MISMATCH_ANALYSIS.md` | Detailed analysis of GST validation issue |
| `CHANGES_README.md` | This file - summary of all changes |

---

## Contact

For questions about these changes, refer to the debug logs in Error Log (frappe) or browser console.
