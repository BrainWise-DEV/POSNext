# Friends & Family Pricing Logic

## Overview

This document describes the automatic pricing and discount logic applied to the **Friends & Family** customer group in the POS Next system.

## Business Rules

When a customer belongs to the **"Friends & Family"** customer group, the following pricing logic is automatically applied:

1. **Base Rate Calculation**: The item rate is set to `buying_rate * (1 + 7%)`
   - Buying rate is fetched from the Item document (valuation_rate or standard_buying_rate)
   - A 7% markup is applied to the buying rate

2. **Discount Application**: If the standard selling price is higher than the Friends & Family rate, an automatic discount is calculated:
   - `discount_percentage = ((selling_price - friends_family_rate) / selling_price) * 100`
   - This discount is applied to each item automatically

3. **Application Points**: The Friends & Family pricing is applied at two points:
   - **During Item Selection**: When an item is selected and `get_item_details()` is called with a customer parameter
   - **During Invoice Submission**: When an invoice is submitted with a Friends & Family customer

## Implementation Details

### Files Modified

#### 1. `pos_next/api/items.py`

**New Function**: `apply_friends_family_pricing(item_detail, customer_group=None, item_doc=None)`

- Applies Friends & Family pricing to individual item details
- Checks if customer_group matches "Friends & Family"
- Calculates rate as: `buying_rate * 1.07`
- Stores pricing metadata for audit trails

**Updated Function**: `get_item_details(item_code, pos_profile, customer=None, qty=1, uom=None)`

- Now accepts `customer` parameter (previously not used)
- Fetches customer's customer_group from database
- Applies Friends & Family pricing if applicable
- Handles errors gracefully (falls back to normal pricing)

#### 2. `pos_next/api/invoices.py`

**New Function**: `apply_friends_family_pricing_to_invoice(invoice_doc, customer=None)`

- Applies Friends & Family pricing to all items in an invoice
- Iterates through invoice items and applies pricing rules
- Modifies invoice_doc in-place
- Returns boolean indicating whether pricing was applied

**Updated Function**: `submit_invoice(invoice=None, data=None)`

- Added call to `apply_friends_family_pricing_to_invoice()` before invoice submission
- Ensures all invoice items have correct Friends & Family pricing when customer group matches

## Configuration

### Constants

Located in the API files:

```python
FRIENDS_FAMILY_CUSTOMER_GROUP = "Friends & Family"
FRIENDS_FAMILY_MARKUP_PERCENTAGE = 7  # 7% markup on buying rate
```

**To modify the markup percentage**: Edit the `FRIENDS_FAMILY_MARKUP_PERCENTAGE` value in both files.

## Item Metadata

When Friends & Family pricing is applied, items are tagged with:

```python
{
    "rate": calculated_rate,  # buying_rate * 1.07
    "price_list_rate": calculated_rate,
    "discount_percentage": discount_pct,  # if applicable
    "friends_family_pricing_applied": True,
    "friends_family_base_rate": buying_rate
}
```

This allows tracking and auditing of pricing changes.

## Error Handling

The implementation includes robust error handling:

1. **Missing buying rate**: Falls back to normal pricing if item has no buying rate
2. **Customer lookup failures**: Logs error but continues with normal pricing
3. **Item fetch failures**: Individual item pricing errors don't block invoice submission

All errors are logged to Frappe's error log for debugging.

## Usage Examples

### Example 1: Customer Selection at POS

```
1. Customer selects an item at POS
2. Customer group is checked (e.g., "Friends & Family")
3. Item detail is fetched via get_item_details(customer="CUST-001")
4. Pricing is automatically adjusted:
   - If item buying rate = 100, rate is set to 107 (100 * 1.07)
   - If standard price is 150, discount = ((150-107)/150)*100 = 28.67%
```

### Example 2: Invoice Submission

```
1. Invoice is created with multiple items
2. Customer is "Friends & Family" group
3. During submit_invoice(), pricing is re-applied:
   - Each item's rate is set to buying_rate * 1.07
   - Discounts are calculated if applicable
4. Invoice is submitted with adjusted pricing
```

## Testing Checklist

To verify the implementation:

- [ ] Create a customer in "Friends & Family" group
- [ ] Add an item with buying rate (e.g., 100)
- [ ] Select item in POS with F&F customer
- [ ] Verify rate is 107 (100 * 1.07)
- [ ] Verify discount is calculated if original price is higher
- [ ] Submit invoice and verify correct amounts
- [ ] Check invoice item details for `friends_family_pricing_applied` flag

## Database Queries

### Check Customer Group

```sql
SELECT name, customer_group FROM `tabCustomer` WHERE name = 'CUST-001';
```

### Check Item Valuation Rate

```sql
SELECT name, valuation_rate, standard_buying_rate FROM `tabItem` WHERE name = 'ITEM-001';
```

## Troubleshooting

### Issue: Discount not being applied

**Solution**: Ensure the item has a buying rate (valuation_rate or standard_buying_rate) in the Item master.

### Issue: Friends & Family pricing not applied

**Solution**: 
1. Verify customer's customer_group is exactly "Friends & Family" (case-sensitive)
2. Check Frappe error log for lookup errors
3. Ensure customer parameter is passed to get_item_details()

### Issue: Inconsistent pricing between item selection and invoice

**Solution**: Pricing is applied at both points. If inconsistency occurs, check:
1. Customer's customer_group hasn't changed
2. Item's buying rate hasn't changed
3. Invoice calculation step is reaching the apply function

## Performance Considerations

- **Caching**: Uses frappe.get_cached_doc() for Item lookups
- **DB queries**: One additional query per invoice to fetch customer_group
- **Per-item overhead**: Minimal (one valuation_rate lookup per item)

## Future Enhancements

Potential improvements:

1. **Configurable markup percentage** per customer or customer group
2. **Tiered discounts** based on purchase frequency
3. **Special pricing exceptions** for specific items
4. **Bulk order discounts** combining with Friends & Family pricing
5. **Admin dashboard** to manage Friends & Family pricing rules

## Support

For issues or questions regarding Friends & Family pricing:

1. Check the error log: `Menu > Tools > Error Log`
2. Review item master: Ensure buying rates are set
3. Review customer master: Ensure customer_group is "Friends & Family"
4. Contact development team with error details and customer/item codes
