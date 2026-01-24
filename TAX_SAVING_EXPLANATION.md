# Tax Saving Requirements - Complete Explanation

## What Exactly is Required to Save Taxes in Sales Invoice?

### The 5 Critical Requirements (ALL must be met):

1. **`taxes_and_charges` field must be set**
   - This is the tax template name (e.g., "Output GST In-state - TJCPL")
   - Can come from:
     - POS Profile (if taxes are selected in POS Profile)
     - Frontend (sent from POS UI)
     - Auto-detection (based on customer GST state)

2. **Taxes must be loaded from template into `doc.taxes` table**
   - Call `doc.set_taxes()` to load taxes from the template
   - This populates the `doc.taxes` child table with tax rows

3. **`included_in_print_rate = 1` MUST be set on ALL taxes (except Actual)**
   - This is the **MOST CRITICAL** requirement
   - Without this, `determine_exclusive_rate()` returns early and tax is NOT extracted
   - Must be set BEFORE `calculate_taxes_and_totals()` is called

4. **Item amounts must be set**
   - `item.amount = item.rate * item.qty` (where rate is tax-inclusive, e.g., 84000)
   - Must be set BEFORE `calculate_taxes_and_totals()`

5. **`calculate_taxes_and_totals()` MUST be called**
   - This extracts tax from item rates when `included_in_print_rate = 1`
   - Uses `determine_exclusive_rate()` to calculate:
     - `net_amount = amount / (1 + tax_fraction)`
     - `tax_amount = amount - net_amount`

## Why It Works When Taxes Are Selected in POS Profile

When taxes ARE selected in POS Profile:
1. ERPNext's `set_pos_fields()` (called by `set_missing_values()`) sets `taxes_and_charges` from POS Profile
2. ERPNext's `set_pos_fields()` then calls `set_taxes()` to load taxes (line 948-949)
3. Our `validate()` hook sets `included_in_print_rate = 1`
4. Our `validate()` hook calls `calculate_taxes_and_totals()`
5. Taxes are calculated and saved ✅

## Why It Doesn't Work When Taxes Are NOT Selected in POS Profile

When taxes are NOT selected in POS Profile:
1. Frontend sends `taxes_and_charges: "Output GST In-state - TJCPL"`
2. We set it in `update_invoice()`
3. `set_missing_values()` calls `set_pos_fields()`
4. `set_pos_fields()` overwrites `taxes_and_charges` with `None` (because POS Profile doesn't have it)
5. Our code restores it from frontend ✅ (we added this fix)
6. But `set_taxes()` might not be called if `taxes_and_charges` was None when `set_pos_fields()` ran
7. So taxes are not loaded ❌

## The Fix

Our code now:
1. **Preserves `taxes_and_charges` from frontend** before `set_missing_values()`
2. **Restores it after `set_missing_values()`** if it was cleared
3. **Manually calls `set_taxes()`** if taxes are not loaded
4. **Sets `included_in_print_rate = 1`** in both `validate()` and `before_save()` hooks
5. **Calls `calculate_taxes_and_totals()`** to extract tax from item rates

## Order of Operations (Current Implementation)

```
1. Frontend sends taxes_and_charges and custom_is_this_tax_included_in_basic_rate = 1
2. update_invoice() sets taxes_and_charges from frontend
3. update_invoice() preserves taxes_and_charges before set_missing_values()
4. set_missing_values() calls set_pos_fields()
   - If taxes in POS Profile: sets taxes_and_charges and calls set_taxes()
   - If taxes NOT in POS Profile: sets taxes_and_charges to None
5. update_invoice() restores taxes_and_charges from frontend if it was cleared
6. update_invoice() manually calls set_taxes() if taxes not loaded
7. update_invoice() sets included_in_print_rate = 1
8. update_invoice() calls calculate_taxes_and_totals()
9. submit_invoice() calls save()
10. validate() hook runs: sets included_in_print_rate = 1, calls calculate_taxes_and_totals()
11. before_save() hook runs: ensures included_in_print_rate = 1, calls calculate_taxes_and_totals()
12. Document is saved with taxes ✅
```

## Testing

After `bench restart`, create a new invoice and check:
1. Error logs for "POS Tax Debug" to see the flow
2. Sales Invoice in backend to verify taxes are saved
3. Tax amounts should be calculated (e.g., 84000 * 18% / 1.18 = ~12813.56)

## Common Issues

1. **Taxes are 0**: Check if `included_in_print_rate = 1` is set
2. **Taxes not loaded**: Check if `set_taxes()` is being called
3. **taxes_and_charges is None**: Check if it's being preserved from frontend
