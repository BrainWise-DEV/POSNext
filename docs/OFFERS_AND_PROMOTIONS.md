# Offers and Promotions System

This document explains how POS Next integrates with ERPNext's Pricing Rules and Promotional Schemes to automatically apply discounts.

## Overview

POS Next supports automatic offer application based on cart contents. When items are added to the cart, the system:

1. Checks eligibility against available Pricing Rules/Promotional Schemes
2. Automatically applies eligible offers
3. Displays discount badges on discounted items
4. Shows total discount in the cart summary
5. Removes offers automatically when cart no longer qualifies

## Supported Offer Types

### 1. Price Discounts
- **Discount Percentage**: e.g., 10% off
- **Discount Amount**: e.g., $5 off

### 2. Product Discounts (Free Items)
- Buy X Get Y Free
- Free item with purchase

### 3. Apply On Options
- **Item Code**: Specific items only
- **Item Group**: All items in a group
- **Brand**: All items from a brand
- **Transaction**: Entire cart

## Configuration in ERPNext

### Creating a Promotional Scheme

1. Go to **Selling > Promotional Scheme**
2. Create a new scheme with:
   - **Title**: Display name (e.g., "Demo Item 10%")
   - **Apply On**: Item Group, Item Code, Brand, or Transaction
   - **Min Qty / Max Qty**: Quantity constraints
   - **Min Amt / Max Amt**: Amount constraints
   - **Discount Percentage** or **Discount Amount**

### Important: Mixed Conditions

For offers that should apply when **different items from the same group** are combined (e.g., 1 Book + 1 Camera = 2 items from "Demo Item Group"), you must enable:

```
Mixed Conditions = Yes
```

This allows ERPNext to accumulate quantities across different items in the same Item Group.

**Example:**
- Rule: "Buy 2 items from Demo Item Group, get 10% off"
- Min Qty: 2, Max Qty: 2
- Apply On: Item Group = "Demo Item Group"
- Mixed Conditions: Yes

**Without Mixed Conditions:**
- 1 Book (qty=1) + 1 Camera (qty=1) = ❌ No discount (each item checked individually)

**With Mixed Conditions:**
- 1 Book (qty=1) + 1 Camera (qty=1) = ✅ 10% discount (total qty=2 across group)

### Pricing Rule Generated

When you save a Promotional Scheme, ERPNext automatically creates underlying Pricing Rules (e.g., `PRLE-0003`). POS Next works with these generated rules.

## Frontend Architecture

### Stores

#### `posOffers.js`
Manages offer eligibility checking:
- `availableOffers`: All offers fetched from backend
- `cartSnapshot`: Current cart state for eligibility checking
- `allEligibleOffers`: Computed list of currently eligible offers
- `checkOfferEligibility(offer)`: Validates offer against cart

#### `posCart.js`
Manages offer application:
- `appliedOffers`: Currently applied offers
- `suppressOfferReapply`: Flag to prevent processing loops
- `processOffersInternal()`: Main offer processing function
- `autoApplyEligibleOffers()`: Applies new eligible offers
- `reapplyOffer()`: Validates and removes invalid offers

### Flow

```
Cart Change → Debounce (150ms) → processOffersInternal()
                                      ↓
                               Reset suppressOfferReapply
                                      ↓
                               Generate cart hash
                                      ↓
                               Skip if hash unchanged
                                      ↓
                               reapplyOffer() - Remove invalid offers
                                      ↓
                               autoApplyEligibleOffers() - Apply new offers
                                      ↓
                               Update hash
```

## Backend API

### `apply_offers(invoice_data, selected_offers)`

Located in `pos_next/api/invoices.py`

```python
@frappe.whitelist()
def apply_offers(invoice_data, selected_offers=None):
    """Calculate and apply promotional offers using ERPNext Pricing Rules."""
```

**Parameters:**
- `invoice_data`: Sales Invoice payload with items
- `selected_offers`: Optional list of specific offer names to apply

**Returns:**
```json
{
  "items": [
    {
      "item_code": "SKU010",
      "discount_percentage": 10.0,
      "discount_amount": 1.5,
      "pricing_rules": ["PRLE-0003"],
      "applied_promotional_schemes": ["Demo Item 10%"]
    }
  ],
  "free_items": [],
  "applied_pricing_rules": ["PRLE-0003"]
}
```

### Mixed Conditions Support

The API passes the document to ERPNext's pricing engine for mixed conditions:

```python
# Why we pass pricing_args twice:
# - 1st param (args): ERPNext extracts and pops 'items' from this
# - 2nd param (doc): Used by 'mixed_conditions' to access the FULL items list
#                    for quantity accumulation across different items
pricing_results = erpnext_apply_pricing_rule(pricing_args, doc=pricing_args)
```

## UI Components

### OffersDialog.vue
Displays available offers with:
- Offer title and description
- Discount amount/percentage
- Min/Max constraints
- Progress bar for min amount
- Applied/Eligible status badges

### Cart Item Badges
When an offer is applied, items show:
- 10% badge (or discount amount)
- Discounted price (crossed out original)

### Cart Summary
- Discount row showing total savings
- Updated grand total

## Troubleshooting

### Offer Not Applying

1. **Check eligibility in console:**
```javascript
const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia
const offersStore = pinia._s.get('posOffers')
console.log('Eligible:', offersStore.allEligibleOffers)
console.log('Cart snapshot:', offersStore.cartSnapshot)
```

2. **Check if suppressed:**
```javascript
const cartStore = pinia._s.get('posCart')
console.log('Suppressed:', cartStore.suppressOfferReapply)
```

3. **Force refresh:**
```javascript
cartStore.forceRefreshOffers()
```

### Mixed Items Not Triggering Offer

If 1 Book + 1 Camera doesn't trigger an "Item Group" offer:

1. Verify both items are in the same Item Group
2. Enable `Mixed Conditions` on the Pricing Rule in ERPNext
3. Ensure the backend API is passing `doc` parameter (see code above)

### Offer Removed Unexpectedly

Check the console for:
- "Offer removed: {name}. Cart no longer meets requirements."

This happens when:
- Quantity falls below `min_qty`
- Quantity exceeds `max_qty`
- Subtotal falls below `min_amt`
- Subtotal exceeds `max_amt`
- Required items removed from cart

## Testing

### Manual Testing Scenarios

1. **Same Item Quantity:**
   - Add 2 Books → Offer applies
   - Reduce to 1 Book → Offer removed

2. **Mixed Items (requires Mixed Conditions):**
   - Add 1 Book + 1 Camera → Offer applies (both in same Item Group)
   - Remove one → Offer removed

3. **Amount-based Offers:**
   - Add items until subtotal reaches min_amt → Offer applies
   - Remove items below min_amt → Offer removed

### Backend Testing

```python
from pos_next.api.invoices import apply_offers

result = apply_offers({
    "doctype": "Sales Invoice",
    "pos_profile": "Demo",
    "customer": "Walk-in Customer",
    "items": [
        {"item_code": "SKU010", "qty": 1, "rate": 15.00, "uom": "Nos"},
        {"item_code": "SKU003", "qty": 1, "rate": 299.00, "uom": "Nos"}
    ]
}, selected_offers=["PRLE-0003"])

print(result)
```

## Related Files

- Frontend:
  - `POS/src/stores/posOffers.js` - Offer eligibility store
  - `POS/src/stores/posCart.js` - Cart and offer application logic
  - `POS/src/components/sale/OffersDialog.vue` - Offers UI

- Backend:
  - `pos_next/api/invoices.py` - `apply_offers()` API
  - ERPNext: `erpnext/accounts/doctype/pricing_rule/` - Pricing engine
