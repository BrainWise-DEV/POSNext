# Pricing and Invoice Submission Flow

This document explains how prices, discounts, and taxes are calculated and submitted in the POS system, covering both online and offline scenarios.

---

## Table of Contents

1. [The Big Picture](#the-big-picture)
2. [Understanding Price Fields](#understanding-price-fields)
3. [Step-by-Step Flow](#step-by-step-flow)
4. [Tax Handling](#tax-handling)
5. [Discount Types](#discount-types)
6. [Online vs Offline Mode](#online-vs-offline-mode)
7. [Pricing Rules (Offers)](#pricing-rules-offers)
8. [Common Scenarios](#common-scenarios)
9. [Troubleshooting](#troubleshooting)

---

## The Big Picture

When a cashier adds items to the cart and completes a sale, the system goes through several stages:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Add Item   │ ──► │  Calculate   │ ──► │   Format     │ ──► │   Submit     │
│   to Cart    │     │   Totals     │     │   for API    │     │   Invoice    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
      │                    │                    │                     │
      ▼                    ▼                    ▼                     ▼
  Store item          Apply taxes,         Convert data         Send to ERPNext
  with original       discounts, and       to format that       for final
  price               calculate totals     ERPNext expects      processing
```

### Key Principle

> **The POS always preserves the original price** (`price_list_rate`) and calculates discounts separately. This allows the UI to show "was $100, now $80" and ensures accurate reporting.

---

## Understanding Price Fields

The system uses several price-related fields. Here's what each one means:

| Field | What It Represents | Example |
|-------|-------------------|---------|
| **price_list_rate** | Original price before any discount | $100.00 |
| **discount_percentage** | Discount applied (as percentage) | 20% |
| **discount_amount** | Discount in currency | $20.00 |
| **rate** | Price sent to ERPNext (after discount) | $80.00 |
| **amount** | Total for this line (rate × quantity) | $160.00 (for qty 2) |
| **tax_amount** | Tax calculated for this item | $12.00 |

### Visual Example

```
Item: Premium Coffee
┌─────────────────────────────────────────────────────┐
│  Original Price (price_list_rate):     $100.00     │
│  Discount (20%):                       -$20.00     │
│  ─────────────────────────────────────────────     │
│  Rate sent to ERPNext:                  $80.00     │
│  Quantity:                                  ×2     │
│  ─────────────────────────────────────────────     │
│  Line Total (amount):                  $160.00     │
│  Tax (15%):                            +$24.00     │
│  ─────────────────────────────────────────────     │
│  Line Grand Total:                     $184.00     │
└─────────────────────────────────────────────────────┘
```

---

## Step-by-Step Flow

### Stage 1: Adding Item to Cart

When a cashier scans or selects an item:

1. System fetches item details (name, price, tax settings)
2. Creates a cart entry with:
   - `price_list_rate` = original price from price list
   - `rate` = same as price_list_rate (no discount yet)
   - `quantity` = 1 (or selected quantity)
   - `discount_percentage` = 0
   - `discount_amount` = 0

### Stage 2: Calculating Totals

Every time the cart changes (add, remove, quantity change, discount applied):

1. **For each item:**
   - Calculate base amount = `price_list_rate × quantity`
   - Apply discount = base amount × discount percentage
   - Calculate net amount = base amount - discount
   - Calculate tax based on tax mode (see [Tax Handling](#tax-handling))

2. **For the cart:**
   - Sum all item amounts → Subtotal
   - Sum all item taxes → Total Tax
   - Sum all item discounts → Total Discount
   - Apply any cart-level discount (coupons)
   - Calculate Grand Total

### Stage 3: Preparing for Submission

Before sending to ERPNext, the system:

1. **Calculates the backend rate:**
   - Tax Exclusive: `rate = net amount ÷ quantity`
   - Tax Inclusive: `rate = price_list_rate - (discount ÷ quantity)`

2. **Formats pricing rules:**
   - Converts array `["RULE-001", "RULE-002"]` to string `"RULE-001,RULE-002"`
   - ERPNext requires this specific format

3. **Prepares the final payload** with all required fields

### Stage 4: Backend Processing

When ERPNext receives the invoice:

1. **Validates the data**
2. **Reverse-calculates price_list_rate** (safety check):
   - If rate is $80 with 20% discount, confirms price_list_rate should be $100
   - Formula: `price_list_rate = rate ÷ (1 - discount% ÷ 100)`
3. **Creates draft invoice**
4. **Submits and updates stock**

---

## Tax Handling

The system supports two tax modes, configured in POS Settings:

### Tax Exclusive (Default)

Prices do **NOT** include tax. Tax is added on top.

```
Customer sees:
┌─────────────────────────────┐
│  Subtotal:         $100.00  │
│  Discount (10%):   -$10.00  │
│  Net:               $90.00  │
│  Tax (15%):        +$13.50  │  ← Tax added
│  ─────────────────────────  │
│  Grand Total:      $103.50  │
└─────────────────────────────┘
```

### Tax Inclusive

Prices **ALREADY** include tax. Tax is extracted for reporting.

```
Customer sees:
┌─────────────────────────────┐
│  Subtotal:         $100.00  │  ← Already includes tax
│  Discount (10%):   -$10.00  │
│  ─────────────────────────  │
│  Grand Total:       $90.00  │  ← No tax added!
│                             │
│  (Tax portion: $11.74)      │  ← For reports only
└─────────────────────────────┘
```

### How Tax Inclusive Extraction Works

When prices include tax, the system extracts it:

```
Gross Amount = $90.00 (after discount)
Tax Rate = 15%

Net Amount = $90 ÷ 1.15 = $78.26
Tax Amount = $90 - $78.26 = $11.74
```

---

## Discount Types

### 1. Item-Level Discounts

Applied to individual items, usually from:
- **Pricing Rules** (automatic offers)
- **Manual entry** by cashier

```
Item: Laptop
Original: $1,000
Discount: 15% (from "Summer Sale" pricing rule)
Final: $850
```

### 2. Cart-Level Discounts (Coupons)

Applied to the entire cart total:

```
Subtotal: $500
Coupon "SAVE50": -$50
New Subtotal: $450
```

### 3. How Discounts Stack

```
┌─────────────────────────────────────────────────┐
│  Item Price:                        $100.00     │
│  Item Discount (Pricing Rule 10%):  -$10.00     │
│  ───────────────────────────────────────────    │
│  Item Subtotal:                      $90.00     │
│                                                 │
│  Cart Subtotal (3 items):           $270.00     │
│  Cart Discount (Coupon 5%):         -$13.50     │
│  ───────────────────────────────────────────    │
│  Net Total:                         $256.50     │
│  Tax (15%):                         +$38.48     │
│  ───────────────────────────────────────────    │
│  Grand Total:                       $294.98     │
└─────────────────────────────────────────────────┘
```

---

## Online vs Offline Mode

### Online Mode

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│   POS   │ ──► │   API   │ ──► │ ERPNext │
│  Client │     │  Call   │     │ Server  │
└─────────┘     └─────────┘     └─────────┘
     │                               │
     └───────── Immediate ───────────┘
                Response
```

1. Cashier completes sale
2. POS sends invoice data to server
3. Server creates and submits invoice
4. POS shows success with invoice number

### Offline Mode

```
┌─────────┐     ┌─────────┐            ┌─────────┐     ┌─────────┐
│   POS   │ ──► │ IndexDB │   ~~~►     │  Sync   │ ──► │ ERPNext │
│  Client │     │ (Local) │  (Later)   │ Process │     │ Server  │
└─────────┘     └─────────┘            └─────────┘     └─────────┘
```

1. Cashier completes sale
2. POS saves invoice to local database (IndexedDB)
3. POS shows "Saved Offline" message
4. **When internet returns:**
   - Sync process reads pending invoices
   - Sends each to server
   - Marks as synced when successful

### Preventing Duplicate Invoices

Each offline invoice gets a unique ID (`offline_id`). When syncing:

1. Check if this ID was already synced
2. If yes → Skip (already submitted)
3. If no → Submit and record the ID

This prevents the same sale from being submitted twice even if:
- Network drops during submission
- User retries manually
- Multiple browser tabs try to sync

---

## Pricing Rules (Offers)

Pricing Rules are ERPNext's way of handling promotions. Here's how they flow:

### When Customer is Eligible

```
┌──────────────────────────────────────────────────────────────────┐
│                        OFFER CHECK FLOW                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Cart Changes                                                 │
│         │                                                        │
│         ▼                                                        │
│  2. POS checks: "Are there eligible offers?"                     │
│         │                                                        │
│         ├── No ──► No discount applied                           │
│         │                                                        │
│         ▼ Yes                                                    │
│  3. Send cart data to server                                     │
│         │                                                        │
│         ▼                                                        │
│  4. Server evaluates pricing rules                               │
│         │                                                        │
│         ▼                                                        │
│  5. Server returns discounts per item                            │
│         │                                                        │
│         ▼                                                        │
│  6. POS applies discounts to cart                                │
│         │                                                        │
│         ▼                                                        │
│  7. Customer sees updated prices                                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Offline Offer Handling

When offline, the POS applies offers locally using cached rules:

1. Check if item matches offer criteria (item code, group, brand)
2. Check quantity/amount thresholds
3. Apply discount percentage or amount
4. Mark which pricing rule was applied

**Note:** Complex offers (like "Buy from Group A, get discount on Group B") may not work offline. They'll be validated when synced.

---

## Common Scenarios

### Scenario 1: Simple Sale

```
Cashier Action                    System Response
─────────────────────────────────────────────────────────────
Scan item "Coffee" ($5.00)    →   Cart: 1× Coffee = $5.00
Scan item "Muffin" ($3.00)    →   Cart: 2 items = $8.00
Press "Pay"                   →   Payment dialog opens
Select "Cash"                 →   Records cash payment
Press "Complete"              →   Invoice SI-00123 created
```

### Scenario 2: Sale with Discount

```
Cashier Action                    System Response
─────────────────────────────────────────────────────────────
Scan item "Laptop" ($1,000)   →   Cart: 1× Laptop = $1,000
                              →   "Summer Sale" offer detected!
                              →   10% discount applied
                              →   Cart: 1× Laptop = $900
Press "Pay"                   →   Grand Total: $900 + tax
```

### Scenario 3: Offline Sale

```
Cashier Action                    System Response
─────────────────────────────────────────────────────────────
[Internet disconnects]        →   POS shows "Offline" indicator
Scan items                    →   Cart works normally
Press "Pay"                   →   Payment works normally
Press "Complete"              →   "Saved Offline - Will sync later"
                              →   Sale stored locally

[Internet returns]            →   Auto-sync starts
                              →   "1 invoice synced"
                              →   Invoice SI-00124 created
```

### Scenario 4: Tax Inclusive Store

```
Store Setting: Tax Inclusive = Yes
Tax Rate: 15%

Cashier Action                    System Response
─────────────────────────────────────────────────────────────
Scan item "Book" ($115)       →   Cart shows: $115.00
                              →   (Tax included: $15.00)
Press "Pay"                   →   Customer pays: $115.00
                              →   Tax reported: $15.00
                              →   Net revenue: $100.00
```

---

## Troubleshooting

### Problem: Discount Applied Twice

**Symptoms:** Invoice shows double the expected discount.

**Cause:** Both POS and ERPNext applying the same pricing rule.

**Solution:** The system sets `ignore_pricing_rule = 1` on invoices to prevent ERPNext from re-applying. If this happens, check that this flag is being set correctly.

### Problem: Tax Calculation Mismatch

**Symptoms:** Tax on invoice doesn't match POS display.

**Cause:** Tax mode (inclusive/exclusive) differs between POS and ERPNext settings.

**Solution:** Ensure POS Settings `tax_inclusive` matches your ERPNext tax template configuration.

### Problem: Offer Not Applied

**Symptoms:** Customer should get a discount but doesn't.

**Possible Causes:**
1. Pricing Rule not active (check dates)
2. Customer doesn't meet criteria (check customer group)
3. Quantity threshold not met
4. Offline mode can't evaluate complex rules

**Solution:** Check Pricing Rule conditions in ERPNext. Try online mode to verify.

### Problem: Offline Invoice Created Twice

**Symptoms:** Same sale appears twice after sync.

**Cause:** `offline_id` not being preserved or checked.

**Solution:** Each offline invoice must have a unique `offline_id`. The sync process checks this before submission. If duplicates occur, check the deduplication logic.

### Problem: Price Shows Zero

**Symptoms:** Item added but price is $0.00.

**Possible Causes:**
1. Item not in the selling price list
2. Price list currency mismatch
3. Item marked as "not for sale"

**Solution:** Check Item Price in ERPNext. Ensure the POS Profile's price list contains the item.

---

## Summary

| Stage | What Happens | Key Function |
|-------|--------------|--------------|
| Add to Cart | Store original price | `addItem()` |
| Calculate | Apply discounts and tax | `recalculateItem()` |
| Format | Prepare for ERPNext | `formatItemsForSubmission()` |
| Submit (Online) | Send to server | `submitInvoice()` |
| Save (Offline) | Store locally | `saveOfflineInvoice()` |
| Sync | Send offline invoices | `syncInvoiceToServer()` |
| Backend | Create ERPNext invoice | `submit_invoice()` |

### Golden Rules

1. **Always preserve original price** in `price_list_rate`
2. **Calculate discounts separately** - never modify the original price
3. **Use the same formatting** for online and offline submissions
4. **Include `offline_id`** for all offline invoices
5. **Convert pricing rules to strings** before sending to ERPNext
