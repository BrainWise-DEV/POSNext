# Requirements to Save Taxes in Sales Invoice (Tax-Inclusive Mode)

## Critical Requirements (ALL must be met):

1. **Taxes must be loaded from template**
   - `taxes_and_charges` field must be set
   - `doc.set_taxes()` or taxes must be in `doc.taxes` table

2. **`included_in_print_rate = 1` MUST be set on ALL taxes (except Actual)**
   - This is the KEY requirement
   - Without this, ERPNext won't extract tax from item rates
   - Must be set BEFORE `calculate_taxes_and_totals()` is called

3. **Item amounts must be set**
   - `item.amount = item.rate * item.qty` (where rate is tax-inclusive)
   - Must be set BEFORE `calculate_taxes_and_totals()`

4. **`calculate_taxes_and_totals()` MUST be called**
   - This extracts tax from item rates when `included_in_print_rate = 1`
   - Uses `determine_exclusive_rate()` to calculate net amount
   - Then calculates tax amount = item.amount - item.net_amount

5. **Taxes must persist when document is saved**
   - The `taxes` table must have rows with calculated `tax_amount`
   - Must be set before `doc.save()` is called

## Order of Operations (CRITICAL):

```
1. Load taxes from template (set_taxes())
2. Set included_in_print_rate = 1 on all taxes
3. Set item.amount = item.rate * item.qty
4. Call calculate_taxes_and_totals()
5. Save document (taxes are persisted)
```

## Common Issues:

1. **`included_in_print_rate` is reset to 0**
   - Solution: Set it in `before_save` hook (runs after all other operations)

2. **Taxes are not loaded**
   - Solution: Call `doc.set_taxes()` if `doc.taxes` is empty

3. **`calculate_taxes_and_totals()` is not called**
   - Solution: Call it explicitly after setting `included_in_print_rate = 1`

4. **Item amounts are not set**
   - Solution: Set `item.amount` before calling `calculate_taxes_and_totals()`

## ERPNext's Flow:

In ERPNext POS Invoice with tax_inclusive mode:
1. POS Profile has `tax_inclusive` field
2. When creating invoice, `set_pos_fields()` loads taxes
3. `validate()` hook sets `included_in_print_rate = 1` if tax_inclusive
4. `calculate_taxes_and_totals()` extracts tax from rates
5. Taxes are saved with the document
