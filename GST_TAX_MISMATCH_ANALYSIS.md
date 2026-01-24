# GST Tax Mismatch Analysis: India Compliance vs POS Next

## Executive Summary

When creating Sales Invoices from POS Next with **Tax Inclusive Mode** enabled and amounts over Rs. 100, an error occurs:

> "GST amounts do not match the calculated values based on tax rates for the following Item rows: Row #1: CGST, SGST amount mismatch"

This document analyzes the root cause and proposes changes to **POS Next only** (not India Compliance).

---

## How India Compliance Validates GST

### Location: `india_compliance/gst_india/overrides/transaction.py` (lines 1325-1392)

India Compliance validates GST amounts on each item against calculated values:

```python
def validate_item_gst_details(self):
    invalid_rows = defaultdict(list)
    for item in self.doc.get("items"):
        for tax in GST_TAX_TYPES:  # ['cgst', 'sgst', 'igst', 'cess', 'cess_non_advol']
            expected_amt = self.get_item_tax_amount(
                item, item.get(f"{tax}_rate"), tax
            )
            diff = abs(item.get(f"{tax}_amount") - expected_amt)
            if diff > ALLOWED_TAX_DIFFERENCE:  # 1.0
                invalid_rows[item.idx].append(tax.upper())

def get_item_tax_amount(self, item, tax_rate, tax):
    precision = self.precision.get(f"{tax}_amount")
    multiplier = item.qty if tax == "cess_non_advol" else item.taxable_value / 100
    return flt(tax_rate * multiplier, precision)
```

### What India Compliance Expects on Each Item:

| Field | Description | Expected Value |
|-------|-------------|----------------|
| `taxable_value` | Net amount (excluding tax) | e.g., 72033.90 for gross 85000 @ 18% GST |
| `cgst_rate` | CGST rate percentage | e.g., 9.0 |
| `cgst_amount` | CGST amount | = taxable_value * cgst_rate / 100 |
| `sgst_rate` | SGST rate percentage | e.g., 9.0 |
| `sgst_amount` | SGST amount | = taxable_value * sgst_rate / 100 |

### Validation Formula:
```
expected_cgst_amount = taxable_value * cgst_rate / 100
expected_sgst_amount = taxable_value * sgst_rate / 100

If |item.cgst_amount - expected_cgst_amount| > 1.0 → ERROR
If |item.sgst_amount - expected_sgst_amount| > ERROR
```

---

## How POS Next Currently Handles Tax Inclusive Mode

### Frontend: `useInvoice.js`

```javascript
// In submitInvoice():
const invoiceData = {
    custom_is_this_tax_included_in_basic_rate: taxInclusive.value ? 1 : 0,
    items: rawItems.map((item) => ({
        // Tax-inclusive mode: Send gross amount (price after discount)
        rate: taxInclusive.value
            ? ((item.price_list_rate || item.rate) - (item.discount_amount || 0) / (item.quantity || 1))
            : (item.quantity > 0 ? item.amount / item.quantity : item.rate),
        // ...
    })),
}
```

### Backend: `invoices.py`

```python
# Handle tax inclusive mode from POS
tax_inclusive = cint(data.get("custom_is_this_tax_included_in_basic_rate", 0))

# Load taxes from template
invoice_doc.set_missing_values()

# Set included_in_print_rate AFTER set_missing_values()
if tax_inclusive:
    for tax in invoice_doc.get("taxes", []):
        tax.included_in_print_rate = 1

# Calculate totals
invoice_doc.calculate_taxes_and_totals()
```

---

## The Mismatch - Root Cause Analysis

### Debug Output Shows:

```
=== POS INVOICE DEBUG ===
Tax Inclusive Mode: 1
Rate sent: 85000 (gross amount including tax)

After calculate_taxes_and_totals():
- net_total: 85000.0      ← WRONG! Should be ~72033.90
- grand_total: 100300.0   ← WRONG! Should be 85000
- cgst_amount: 0.0        ← WRONG! Should be ~6483.05
- sgst_amount: 0.0        ← WRONG! Should be ~6483.05
- included_in_print_rate: 0  ← NOT PERSISTING!
```

### Root Cause 1: `included_in_print_rate` Not Persisting

Even though we set `tax.included_in_print_rate = 1` after `set_missing_values()`, the debug shows it's still 0 after `calculate_taxes_and_totals()`.

**Possible reasons:**
1. `calculate_taxes_and_totals()` reloads taxes from template
2. ERPNext's tax calculation doesn't respect the flag set dynamically

### Root Cause 2: Item GST Fields Not Being Populated

India Compliance populates `cgst_amount`, `sgst_amount`, etc. on items via its `ItemGSTDetails` class:

```python
class ItemGSTDetails(GSTAccounts):
    def update_item_tax_details(self):
        # This sets item.cgst_amount, item.sgst_amount, etc.
        # It uses _item_wise_tax_details from the tax calculation
```

This happens in `before_validate` hook. But when POS Next creates invoices:
1. The gross rate is sent as `rate`
2. `calculate_taxes_and_totals()` doesn't extract net properly
3. India Compliance's `ItemGSTDetails` calculates wrong amounts
4. Validation fails

### Root Cause 3: Tax Template Mismatch

The taxes from the POS Profile's tax template may not have `included_in_print_rate = 1` configured. When `set_missing_values()` loads them, they come with `included_in_print_rate = 0`.

---

## The Solution - Proposed Changes to POS Next

### Option A: Calculate Net Amount in Frontend (Recommended)

**Change:** In tax inclusive mode, POS Next should extract the net amount before sending to backend.

**useInvoice.js:**
```javascript
// In submitInvoice():
items: rawItems.map((item) => {
    const grossRate = item.price_list_rate || item.rate;
    const discountedGross = grossRate - (item.discount_amount || 0) / (item.quantity || 1);

    // For tax inclusive: Extract net from gross
    // Net = Gross / (1 + totalTaxRate/100)
    let rate;
    if (taxInclusive.value) {
        const totalTaxRate = calculateTotalTaxRate(); // e.g., 18 for 9% CGST + 9% SGST
        rate = discountedGross / (1 + totalTaxRate / 100);
    } else {
        rate = item.quantity > 0 ? item.amount / item.quantity : item.rate;
    }

    return {
        item_code: item.item_code,
        qty: item.quantity,
        rate: rate,  // Now it's the NET rate
        // ...
    };
})
```

**Pros:**
- Simple change
- Doesn't require modifying tax templates
- Backend receives correct net amounts

**Cons:**
- Requires knowing total tax rate in frontend

### Option B: Use Tax-Inclusive Tax Templates

**Change:** Create separate tax templates with `included_in_print_rate = 1` and select them based on POS Settings.

**Steps:**
1. Create "GST Tax (Inclusive)" templates with `included_in_print_rate = 1`
2. Configure POS Profile to use these templates when tax inclusive mode is enabled
3. Remove dynamic setting of `included_in_print_rate` from `invoices.py`

**Pros:**
- Uses ERPNext's native tax handling
- More reliable

**Cons:**
- Requires creating duplicate tax templates
- Configuration overhead

### Option C: Set `included_in_print_rate` on Tax Template Level

**Change:** Instead of setting it per-row, modify the tax template loading logic.

**invoices.py:**
```python
# Before set_missing_values(), check if tax inclusive
if tax_inclusive:
    # Get the tax template from POS Profile
    tax_template = frappe.get_value("POS Profile", pos_profile, "taxes_and_charges")
    if tax_template:
        # Temporarily modify the template's items
        # Or create a runtime template with included_in_print_rate = 1
        pass

invoice_doc.set_missing_values()
```

---

## Recommended Implementation (Option A)

### File: `POS/src/composables/useInvoice.js`

**Current Code (lines 720-733):**
```javascript
items: rawItems.map((item) => ({
    item_code: item.item_code,
    item_name: item.item_name,
    qty: item.quantity,
    rate: taxInclusive.value
        ? ((item.price_list_rate || item.rate) - (item.discount_amount || 0) / (item.quantity || 1))
        : (item.quantity > 0 ? item.amount / item.quantity : item.rate),
    // ...
})),
```

**Proposed Code:**
```javascript
items: rawItems.map((item) => {
    const grossRate = item.price_list_rate || item.rate;
    const perItemDiscount = (item.discount_amount || 0) / (item.quantity || 1);
    const discountedGross = grossRate - perItemDiscount;

    let netRate;
    if (taxInclusive.value) {
        // Tax inclusive: Extract net from gross
        // Formula: Net = Gross / (1 + TaxRate/100)
        const totalTaxRate = calculateTotalTaxRate();
        netRate = totalTaxRate > 0
            ? discountedGross / (1 + totalTaxRate / 100)
            : discountedGross;
    } else {
        // Tax exclusive: Use amount/qty or rate
        netRate = item.quantity > 0 ? item.amount / item.quantity : item.rate;
    }

    return {
        item_code: item.item_code,
        item_name: item.item_name,
        qty: item.quantity,
        rate: netRate,
        price_list_rate: grossRate,  // Keep original for reference
        // ...
    };
}),
```

### File: `pos_next/api/invoices.py`

**Remove the dynamic `included_in_print_rate` setting since we're now sending net amounts:**
```python
# Remove this block:
if tax_inclusive:
    for tax in invoice_doc.get("taxes", []):
        tax.included_in_print_rate = 1
```

---

## Alternative: Full Backend Solution

If frontend changes are not preferred, the backend can calculate the net amount:

### File: `pos_next/api/invoices.py`

```python
# After set_missing_values() but before calculate_taxes_and_totals()
if tax_inclusive:
    # Get total tax rate from loaded taxes
    total_tax_rate = 0
    for tax in invoice_doc.get("taxes", []):
        if tax.charge_type in ("On Net Total", "On Previous Row Total"):
            total_tax_rate += flt(tax.rate)

    # Convert gross rates to net rates for each item
    if total_tax_rate > 0:
        for item in invoice_doc.get("items", []):
            gross_rate = flt(item.rate)
            net_rate = gross_rate / (1 + total_tax_rate / 100)
            item.rate = net_rate
            # Don't set included_in_print_rate - we're now using net rates

invoice_doc.calculate_taxes_and_totals()
```

---

## Testing Checklist

After implementing the fix:

1. [ ] Create POS sale with tax inclusive mode enabled
2. [ ] Add item with rate = 85000 (gross)
3. [ ] Verify in backend debug log:
   - `net_total` should be ~72033.90 (for 18% GST)
   - `grand_total` should be ~85000
   - `cgst_amount` on item should be ~6483.05
   - `sgst_amount` on item should be ~6483.05
4. [ ] Submit invoice - should not show GST mismatch error
5. [ ] Verify GL entries have correct amounts
6. [ ] Test with different tax rates (5%, 12%, 18%, 28%)
7. [ ] Test with multiple items
8. [ ] Test with discounts applied

---

## Files Modified in This Session

| File | Changes |
|------|---------|
| `POS/src/composables/useInvoice.js` | Added debug logging, tax inclusive flag |
| `POS/src/components/sale/PaymentDialog.vue` | UI changes for Finance Lender Payments, moved Sales Person |
| `pos_next/api/invoices.py` | Added debug logging, tax inclusive handling attempt |
| `pos_next/api/finance_lender.py` | Fixed SQL query with parameterized queries |

---

## Summary

The GST mismatch error occurs because:
1. POS Next sends gross (tax-inclusive) rates to the backend
2. ERPNext's `included_in_print_rate` flag isn't being applied correctly
3. India Compliance expects `taxable_value` to be NET and `cgst_amount`/`sgst_amount` to match calculated values
4. When net amounts are wrong, the validation fails

**The fix:** Calculate the net amount from gross in the frontend before sending to backend, rather than relying on ERPNext to extract it.
