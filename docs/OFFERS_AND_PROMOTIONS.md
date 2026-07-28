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

> A Pricing Rule stores its targets in the `items` / `item_groups` / `brands`
> **child tables**. It has no scalar `item_code` / `item_group` / `brand` field —
> reading one raises `AttributeError`. Always resolve scope through
> `pos_next/promotions/scope.py`, which also handles item-group lineage (a rule on
> `Electronics` covers an item in `Electronics > Phones`).

### 4. Cross-Cart Price Modes

`apply_discount_on_price` on a Price rule switches it into a mode the per-item
engine cannot evaluate on its own, because the decision depends on the whole cart:

| Mode | Behaviour |
|---|---|
| *(blank)* | Normal — discount every matching line |
| `Min` / `Max` | Discount only the single cheapest / most expensive matching line |
| `Accumulative` | Sum the percentage of every scope row present, apply the total to each eligible line |

All three force `mixed_conditions = 1` so ERPNext evaluates the document together.
They are mutually exclusive — one field, one mode per rule.

## Promotion Types and the Interaction Matrix

`promotion_type` classifies what a promotion *is*, and the **Promotion Interaction
Matrix** (`pos_next/api/promotion_exclusions.py`) decides which lines each kind may
touch. A line is classified into a state, then looked up against the target:

| Item state | GWP | Auto Discount | Coupon |
|---|:---:|:---:|:---:|
| `eligible` | ✅ | ✅ | ✅ |
| `already_discounted` | ✅ | ❌ | ❌ |
| `excluded_brand` | ✅ | ✅ | ❌ |
| `accumulative` | ✅ | ✅ | ❌ |

`already_discounted` covers a line carrying an Item Level Discount or a manual
cashier discount. `accumulative` is the one state that lets a second discount stack:
the accumulative and Auto Discount percentages **sum** on the same line.

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

### Accumulative Discounts

Rewards a customer for buying **across** scopes: the more distinct scopes the cart
touches, the bigger the discount on *everything* in it.

**On a Promotional Scheme** (the usual route), tick **Accumulative Discount**
under `is_cumulative`. That hides the price/product discount tables and reveals
the accumulative settings — qty and amount limits, **Max Accumulated Discount %**
and **Min Scopes Required** — on the scheme itself. Then:

1. **Apply On** — `Item Code`, `Item Group` or `Brand` (not `Transaction`)
2. Give each scope row its own **Discount %** (`pos_discount_percentage`)

The checkbox is an *authoring* control. `apply_discount_on_price` on the generated
Pricing Rule stays the single source of truth for the engine, the offer payload and
the interaction matrix; `normalize_accumulative_scheme` (hooked on
`before_validate`) projects the checkbox onto it every save, so the two cannot
drift and a scheme built through the API is as correct as one built in the form.

> **The slab is hidden, not gone.** ERPNext generates Pricing Rules *from* the
> discount slabs and skips an empty child table, so a scheme with no slab saves
> clean and silently discounts nothing. The server therefore maintains exactly one
> slab behind the hidden table, injecting `rate_or_discount`, zeroed discount
> values and the mandatory `rule_description`. Those injected values are all *true*
> for this mode — none is a placeholder to dodge validation.
>
> `before_validate`, not `validate`: ERPNext's own `PromotionalScheme.validate()`
> rejects a slab-less scheme and runs ahead of every hooked `validate`.

**On a standalone Pricing Rule**, set **Apply Discount On** to `Accumulative`
directly; **Promotion Type** must be `Item Level Discount`.

Picking `Accumulative` hides the rule-level discount fields (`price_or_product_discount`,
`rate_or_discount`, `rate`, `discount_amount`, `discount_percentage`) and, on a
Scheme, the product/free-item slabs. The percentage comes from the scope rows and
nowhere else — the engine ignores the rule-level value outright, so a stale one
cannot leak into the total.

> The price discount **slab** stays visible on a Scheme even though its discount
> fields are hidden: ERPNext generates no Pricing Rule without a slab, and the slab
> is where the mode, the cap and Min Scopes Required live.

```
Rule: Group A = 5%,  Group B = 3%,  Group C = 4%
Separate scheme: Auto Discount 10%

Cart: Phone (Group A) + Shirt (Group B)
  scopes present = {A, B}         → C contributes nothing
  accumulative   = 5 + 3 = 8%     → uniform, every eligible line
  auto discount  = 10%            → matrix permits stacking
  line total     = 18%            off price_list_rate (additive, not compounded)
  per line       = min(18%, rule cap, Item.max_discount)
```

Rules of thumb:

- A scope row counts only when a line that will **actually receive** the discount
  matches it. A line excluded by the matrix cannot inflate everyone else's total.
- The total is additive on list price, never compounded.
- Each line is capped by the rule's ceiling *and* by that Item's own `max_discount`.
- Don't list a group and its own ancestor on one rule — a line inside both counts twice.
- Validation forces `pos_only` and `mixed_conditions`, and rejects `Transaction`
  scope, empty scope tables, all-zero percentages and a non-Item-Level promotion type.

**Scheme → Rule propagation.** ERPNext rebuilds each generated rule's scope table
with `pr.append(field, {apply_on: value, "uom": uom})`, dropping custom columns
every save. `sync_scope_percentages_to_pricing_rules` (hooked on Scheme `on_update`)
re-applies the percentages afterwards.

> The POS **Promotion Management** UI cannot create these — it has no grid for
> per-row percentages. Configure them in the Frappe desk.

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

### The discount pipeline

`apply_offers` is the **only** engine that runs for a POS cart: `update_invoice`
sets `ignore_pricing_rule = 1` and clears every line's `pricing_rules` before
saving, so ERPNext never recomputes and whatever the pipeline produces is what gets
persisted. (A consequence: the Min/Max `validate` hook is a no-op for POS invoices —
it only does work for Sales Orders, Quotations, Delivery Notes and desk-created
invoices.)

Line-level passes live in `pos_next/promotions/engine.py` and run in order:

```
begin_line_discounts()        snapshot the ERPNext result as the baseline
  ↓
accumulative pass             contributes PART_ACCUMULATIVE, flags its lines
  ↓
auto discount pass            contributes PART_AUTO_DISCOUNT (matrix-gated)
  ↓
finalize_line_discounts()     discount_percentage = baseline + Σ parts, clamped
```

Passes contribute **named parts** rather than assigning `discount_percentage`:
the same source replaces its earlier value, different sources sum. Parts are
rebuilt from scratch each run, so re-running is idempotent — critical because
`validate` can fire repeatedly and additive-on-current would compound
18% → 36% → 54%.

Order matters. Accumulative runs first so its lines are flagged before the auto
pass consults the matrix; that's what lets the two stack.

> Accumulative rules carry `promotion_type = "Item Level Discount"`, and ERPNext
> tags them onto the very lines they target. Left alone the matrix would read those
> lines as `already_discounted` and the rule would lock itself out of its own scope.
> `build_matrix_type_map()` neutralises accumulative rules in the type map for
> exactly this reason.

### Offline behaviour

Offline carts recompute discounts in `posCart.js`, so accumulative maths has to
exist on both sides. To avoid duplicating the engine, `get_offers` ships the rule
declaratively and the client only sums:

```json
"accumulative_scope_field": "item_group",
"accumulative_scopes": [
  {"values": ["Electronics", "Phones", "Laptops"], "discount_percentage": 5},
  {"values": ["Apparel"], "discount_percentage": 3}
],
"max_accumulated_discount_percentage": 20,
"min_scopes_required": 2
```

Scope values are **pre-expanded server-side** (item groups → descendants, template
items → variants) so the client matches by plain lookup. Rows keep their identity
because the client counts distinct *rows* present, not distinct keys.

Known gap: the server clamps against `Item.max_discount` unconditionally, but the
client only does so when the cached item record carries that field — which it does
not today. An offline sale exceeding an item's ceiling can fail
`validate_max_discount` at sync.

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

### Accumulative Discount Not Applying

1. **Is the mode actually set?** `apply_discount_on_price` must read `Accumulative`
   on the *generated Pricing Rule*, not just the scheme.
2. **Do the scope rows carry percentages?** A row with `pos_discount_percentage = 0`
   contributes nothing; a rule where every row is zero is rejected at validate.
   After editing a Scheme, confirm `sync_scope_percentages_to_pricing_rules` copied
   them down — ERPNext wipes those columns on every scheme save.
3. **Is `Min Scopes Required` too high?** Set to 2, a cart touching one scope earns
   nothing.
4. **Is the line excluded by the matrix?** A manual cashier discount or a *different*
   item-level promotion takes the line out — and with it, that scope's contribution.
5. **Is a ceiling clamping it?** Check the rule's **Max Accumulated Discount %** and
   the Item's own `max_discount`.

### Auto Discount Not Stacking on an Accumulative Line

Expected: accumulative + auto **sum**. If the auto half is missing, check that the
accumulative pass ran first (it flags `is_accumulative_discount`) — offline, that
ordering comes from the sort in `applyOffersOffline`.

Note that an *ordinary* Item Level Discount is supposed to block Auto Discount.
Only `Accumulative` stacks.

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

4. **Accumulative:**
   - Add an item from scope A only → A's percentage alone
   - Add an item from scope B → both lines jump to A% + B%
   - Remove the B item → both fall back to A%
   - With an Auto Discount scheme also active → both lines show A% + B% + auto%

### Automated Tests

Everything lives in `pos_next/test_promotions.py`:

| Class | Covers |
|---|---|
| `TestPromotions` | Every offer shape through the full submit pipeline |
| `TestPricingRuleScope` | Child-table scope resolution, item-group lineage |
| `TestAutoDiscountScopes` | Auto Discount across Item Code / Item Group / Brand |
| `TestDiscountPipeline` | The accumulator — parts sum, clamping, idempotency |
| `TestAccumulativeDiscount` | Accumulative maths, stacking, caps, matrix flags |
| `TestAccumulativeValidation` | Config guards |
| `TestAccumulativeOfflinePayload` | What `get_offers` ships to the offline engine |

```bash
bench --site pos set-config allow_tests true
bench --site pos run-tests --module pos_next.test_promotions

# On a dev site with real data, prefer this — run-tests would wipe it:
bench --site pos execute pos_next.test_promotions.run_all
```

The submit-path tests need a Fiscal Year covering today's date, or they fail with
`FiscalYearError` regardless of promotion logic.

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

## Known Limitations

- **Min/Max vs Accumulative in one cart.** The two are mutually exclusive per rule,
  but a cart holding one of each will conflict: the Min/Max pass runs after the
  pipeline and *replaces* the discount on the line it targets rather than adding to it.
- **`Item.max_discount` offline.** Enforced server-side, best-effort on the client
  (see *Offline behaviour*).
- **No frontend tests.** `vitest` is configured but the repo has no JS test files,
  so `computeAccumulativeDiscount` is verified only against the Python it mirrors.
- **Nested scope rows double-count.** Listing a group and its ancestor on one rule
  means a line inside both contributes twice.

## Related Files

- Frontend:
  - `POS/src/stores/posOffers.js` - Offer eligibility store
  - `POS/src/stores/posCart.js` - Cart and offer application logic, offline engine
  - `POS/src/components/sale/OffersDialog.vue` - Offers UI

- Backend:
  - `pos_next/api/invoices.py` - `apply_offers()` API
  - `pos_next/promotions/engine.py` - Ordered discount pipeline and its passes
  - `pos_next/promotions/scope.py` - Pricing Rule scope resolution, item-group lineage
  - `pos_next/api/promotion_exclusions.py` - Promotion Interaction Matrix
  - `pos_next/api/offers.py` - Offer payload shipped to the client
  - `pos_next/overrides/pricing_rule.py` - Validation, Min/Max pass, Scheme→Rule sync
  - `pos_next/pos_next/custom/pricing_rule_*.json` - Per-scope `pos_discount_percentage`
  - ERPNext: `erpnext/accounts/doctype/pricing_rule/` - Pricing engine
