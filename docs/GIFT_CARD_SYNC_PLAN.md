# Gift Card & ERPNext Coupon Code Sync - Implementation Plan

## Overview

This feature adds optional synchronization between POS Next's gift card system and ERPNext's native Coupon Code doctype. It enables:

1. **Gift Card Product Sales** - Selling a designated item automatically creates a gift card
2. **ERPNext Integration** - Gift cards sync with ERPNext Coupon Code + Pricing Rule
3. **Gift Card Splitting** - When gift card amount > invoice total, automatically split into used/remaining
4. **Optional Customer Assignment** - Gift cards can be anonymous or assigned to a customer

---

## Architecture Comparison

### Current POS Next
```
POS Coupon (standalone)
├── coupon_code
├── discount_amount
├── customer (required for gift cards)
└── erpnext_coupon_code (unused)
```

### Proposed Architecture
```
POS Coupon
├── coupon_code
├── discount_amount
├── customer (OPTIONAL)
├── gift_card_amount (NEW)
├── coupon_code_residual (NEW - for split tracking)
└── erpnext_coupon_code (synced)
    └── ERPNext Coupon Code
        ├── gift_card_amount (custom field)
        ├── coupon_code_residual (custom field)
        └── pricing_rule
            └── ERPNext Pricing Rule
```

---

## Phase 1: Custom Fields for ERPNext Coupon Code

### Files to Create/Modify

**1.1 Create Property Setter for Coupon Code custom fields**

File: `pos_next/pos_next/custom/coupon_code.json`

```json
{
  "custom_fields": [
    {
      "fieldname": "gift_card_amount",
      "fieldtype": "Currency",
      "label": "Gift Card Amount",
      "insert_after": "pricing_rule",
      "fetch_from": "pricing_rule.discount_amount",
      "read_only": 1,
      "description": "Monetary value of the gift card"
    },
    {
      "fieldname": "coupon_code_residual",
      "fieldtype": "Link",
      "label": "Original Gift Card",
      "options": "Coupon Code",
      "insert_after": "gift_card_amount",
      "read_only": 1,
      "description": "Reference to original gift card if this was created from a split"
    },
    {
      "fieldname": "pos_coupon",
      "fieldtype": "Link",
      "label": "POS Coupon",
      "options": "POS Coupon",
      "insert_after": "coupon_code_residual",
      "read_only": 1,
      "description": "Linked POS Coupon document"
    }
  ]
}
```

**1.2 Create fixtures for custom fields**

File: `pos_next/fixtures/coupon_code_custom_fields.json`

---

## Phase 2: POS Settings - Gift Card Configuration

### Files to Modify

**2.1 Update POS Settings DocType**

File: `pos_next/pos_next/doctype/pos_settings/pos_settings.json`

Add new section "Gift Card Settings":

```json
{
  "fieldname": "section_break_gift_card",
  "fieldtype": "Section Break",
  "label": "Gift Card Settings"
},
{
  "fieldname": "enable_gift_cards",
  "fieldtype": "Check",
  "label": "Enable Gift Cards",
  "default": "0",
  "description": "Enable gift card functionality in POS"
},
{
  "fieldname": "gift_card_item",
  "fieldtype": "Link",
  "label": "Gift Card Item",
  "options": "Item",
  "depends_on": "enable_gift_cards",
  "description": "Item that represents a gift card purchase. When sold, creates a gift card coupon."
},
{
  "fieldname": "sync_with_erpnext_coupon",
  "fieldtype": "Check",
  "label": "Sync with ERPNext Coupon Code",
  "default": "1",
  "depends_on": "enable_gift_cards",
  "description": "Create ERPNext Coupon Code and Pricing Rule for accounting integration"
},
{
  "fieldname": "column_break_gift_card",
  "fieldtype": "Column Break"
},
{
  "fieldname": "enable_gift_card_splitting",
  "fieldtype": "Check",
  "label": "Enable Gift Card Splitting",
  "default": "1",
  "depends_on": "enable_gift_cards",
  "description": "When gift card amount exceeds invoice total, create a new gift card for the remaining balance"
},
{
  "fieldname": "gift_card_validity_months",
  "fieldtype": "Int",
  "label": "Gift Card Validity (Months)",
  "default": "12",
  "depends_on": "enable_gift_cards",
  "description": "Number of months a gift card is valid from creation date"
},
{
  "fieldname": "gift_card_notification",
  "fieldtype": "Link",
  "label": "Gift Card Notification",
  "options": "Notification",
  "depends_on": "enable_gift_cards",
  "description": "Notification template to send when gift card is created"
}
```

---

## Phase 3: Update POS Coupon DocType

### Files to Modify

**3.1 Update pos_coupon.json**

- Make `customer` field NOT mandatory for Gift Cards
- Add new fields for gift card tracking

```json
{
  "fieldname": "customer",
  "fieldtype": "Link",
  "label": "Customer",
  "options": "Customer",
  "depends_on": "eval: doc.coupon_type == \"Gift Card\"",
  "description": "Optional: Assign gift card to a specific customer"
},
{
  "fieldname": "gift_card_amount",
  "fieldtype": "Currency",
  "label": "Gift Card Balance",
  "depends_on": "eval: doc.coupon_type == \"Gift Card\"",
  "read_only": 1,
  "description": "Current balance of the gift card"
},
{
  "fieldname": "original_amount",
  "fieldtype": "Currency",
  "label": "Original Amount",
  "depends_on": "eval: doc.coupon_type == \"Gift Card\"",
  "read_only": 1,
  "description": "Original gift card value"
},
{
  "fieldname": "coupon_code_residual",
  "fieldtype": "Link",
  "label": "Original Gift Card",
  "options": "POS Coupon",
  "read_only": 1,
  "description": "Reference to original gift card if created from split"
},
{
  "fieldname": "source_invoice",
  "fieldtype": "Link",
  "label": "Source Invoice",
  "options": "POS Invoice",
  "read_only": 1,
  "description": "POS Invoice that created this gift card"
}
```

**3.2 Update pos_coupon.py validation**

Remove mandatory customer check for Gift Cards:

```python
def validate(self):
    if self.coupon_type == "Gift Card":
        self.maximum_use = 1
        # Customer is now OPTIONAL
        # if not self.customer:
        #     frappe.throw(_("Please select the customer for Gift Card."))
```

---

## Phase 4: Gift Card API

### Files to Create

**4.1 Create new API file**

File: `pos_next/api/gift_cards.py`

```python
"""
Gift Card API for POS Next

Handles:
- Gift card creation from POS Invoice
- Gift card validation and application
- Gift card splitting
- ERPNext Coupon Code synchronization
"""

@frappe.whitelist()
def create_gift_card_from_invoice(invoice_name):
    """
    Create gift card(s) when a gift card item is sold.
    Called after POS Invoice submission.

    Args:
        invoice_name: Name of the POS Invoice

    Returns:
        dict: Created gift card details
    """
    pass

@frappe.whitelist()
def apply_gift_card(coupon_code, invoice_total, customer=None):
    """
    Apply a gift card to an invoice.

    Args:
        coupon_code: Gift card code
        invoice_total: Total invoice amount
        customer: Optional customer for validation

    Returns:
        dict: Discount amount and remaining balance info
    """
    pass

@frappe.whitelist()
def process_gift_card_on_submit(invoice_name):
    """
    Process gift card after invoice submission.
    Handles splitting if gift card amount > invoice total.

    Args:
        invoice_name: Name of the submitted POS Invoice
    """
    pass

@frappe.whitelist()
def get_gift_cards_with_balance(customer=None, company=None):
    """
    Get all gift cards with available balance.

    Args:
        customer: Optional customer filter
        company: Company filter

    Returns:
        list: Gift cards with balance > 0
    """
    pass

def create_erpnext_coupon_code(pos_coupon):
    """
    Create ERPNext Coupon Code linked to POS Coupon.
    Also creates the Pricing Rule for discount application.

    Args:
        pos_coupon: POS Coupon document

    Returns:
        Coupon Code document
    """
    pass

def create_pricing_rule_for_gift_card(amount, coupon_code, company):
    """
    Create Pricing Rule for gift card discount.

    Args:
        amount: Discount amount
        coupon_code: Coupon code string
        company: Company name

    Returns:
        Pricing Rule document
    """
    pass

def split_gift_card(original_coupon, used_amount, remaining_amount, invoice_name):
    """
    Split a gift card into used and remaining portions.

    Args:
        original_coupon: Original POS Coupon document
        used_amount: Amount being used in current transaction
        remaining_amount: Amount to keep for future use
        invoice_name: Invoice using the gift card

    Returns:
        dict: New coupon for used amount, updated original for remaining
    """
    pass

def generate_gift_card_code():
    """
    Generate unique gift card code in format XXXX-XXXX-XXXX

    Returns:
        str: Unique gift card code
    """
    import random
    import string

    def segment():
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

    code = f"{segment()}-{segment()}-{segment()}"

    # Ensure uniqueness
    while frappe.db.exists("POS Coupon", {"coupon_code": code}):
        code = f"{segment()}-{segment()}-{segment()}"

    return code
```

---

## Phase 5: Gift Card Splitting Logic

### Implementation Details

**5.1 Split Process Flow**

```
Invoice Submission with Gift Card
│
├─ gift_card_amount > invoice_total?
│   │
│   ├─ YES: Split Required
│   │   ├─ Create NEW gift card for used_amount (marked as used)
│   │   ├─ Update ORIGINAL gift card:
│   │   │   ├─ gift_card_amount = remaining_amount
│   │   │   ├─ Update linked Pricing Rule discount_amount
│   │   │   └─ Add description note about split
│   │   └─ Link new card via coupon_code_residual
│   │
│   └─ NO: Full Usage
│       └─ Mark gift card as used (used = 1)
│
└─ Update ERPNext Coupon Code (if sync enabled)
```

**5.2 Database Operations**

```sql
-- When splitting a 100 CHF gift card used for 70 CHF invoice:

-- 1. Create new POS Coupon for used amount
INSERT INTO `tabPOS Coupon` (
    coupon_name, coupon_type, coupon_code,
    discount_type, discount_amount, gift_card_amount,
    coupon_code_residual, used, maximum_use
) VALUES (
    'GC-USED-70-{timestamp}', 'Gift Card', 'XXXX-XXXX-USED',
    'Amount', 70, 70,
    '{original_coupon_name}', 1, 1
);

-- 2. Update original gift card
UPDATE `tabPOS Coupon` SET
    gift_card_amount = 30,
    discount_amount = 30,
    description = CONCAT(description, '\nSplit on {date}: 70 used, 30 remaining')
WHERE name = '{original_coupon_name}';

-- 3. Update Pricing Rule
UPDATE `tabPricing Rule` SET
    discount_amount = 30
WHERE name = '{pricing_rule_name}';
```

---

## Phase 6: Frontend Components

### Files to Create/Modify

**6.1 Gift Card Selection Dialog**

File: `POS/src/components/sale/GiftCardDialog.vue`

```vue
<template>
  <Dialog v-model="isOpen" :options="{ title: __('Apply Gift Card') }">
    <template #body-content>
      <!-- Gift Card Code Input -->
      <FormControl
        v-model="giftCardCode"
        :label="__('Gift Card Code')"
        placeholder="XXXX-XXXX-XXXX"
      />

      <!-- Gift Card Info (after validation) -->
      <div v-if="giftCardInfo" class="mt-4 p-3 bg-gray-50 rounded">
        <div class="flex justify-between">
          <span>{{ __('Balance') }}</span>
          <span class="font-bold">{{ formatCurrency(giftCardInfo.balance) }}</span>
        </div>
        <div v-if="giftCardInfo.customer" class="flex justify-between mt-2">
          <span>{{ __('Customer') }}</span>
          <span>{{ giftCardInfo.customer_name }}</span>
        </div>
        <div class="flex justify-between mt-2">
          <span>{{ __('Valid Until') }}</span>
          <span>{{ giftCardInfo.valid_upto }}</span>
        </div>
      </div>

      <!-- Split Warning -->
      <div v-if="willSplit" class="mt-4 p-3 bg-yellow-50 rounded border border-yellow-200">
        <p class="text-sm text-yellow-800">
          {{ __('Gift card balance ({0}) exceeds invoice total ({1}).', [
            formatCurrency(giftCardInfo.balance),
            formatCurrency(invoiceTotal)
          ]) }}
        </p>
        <p class="text-sm text-yellow-800 mt-1">
          {{ __('Remaining {0} will be available on the same card.', [
            formatCurrency(giftCardInfo.balance - invoiceTotal)
          ]) }}
        </p>
      </div>
    </template>

    <template #actions>
      <Button @click="close">{{ __('Cancel') }}</Button>
      <Button
        variant="solid"
        :disabled="!giftCardInfo"
        @click="applyGiftCard"
      >
        {{ __('Apply Gift Card') }}
      </Button>
    </template>
  </Dialog>
</template>
```

**6.2 Gift Card Creation on Item Sale**

File: `POS/src/composables/useGiftCard.js`

```javascript
import { ref, computed } from 'vue'
import { call } from '@/utils/apiWrapper'

export function useGiftCard() {
  const giftCardSettings = ref(null)

  /**
   * Check if an item is the gift card item
   */
  function isGiftCardItem(itemCode) {
    return giftCardSettings.value?.gift_card_item === itemCode
  }

  /**
   * Create gift card after invoice submission
   */
  async function createGiftCardFromInvoice(invoiceName) {
    if (!giftCardSettings.value?.enable_gift_cards) return null

    return await call('pos_next.api.gift_cards.create_gift_card_from_invoice', {
      invoice_name: invoiceName
    })
  }

  /**
   * Apply gift card to current invoice
   */
  async function applyGiftCard(couponCode, invoiceTotal, customer) {
    return await call('pos_next.api.gift_cards.apply_gift_card', {
      coupon_code: couponCode,
      invoice_total: invoiceTotal,
      customer: customer
    })
  }

  /**
   * Get gift cards with available balance
   */
  async function getAvailableGiftCards(customer, company) {
    return await call('pos_next.api.gift_cards.get_gift_cards_with_balance', {
      customer: customer,
      company: company
    })
  }

  return {
    giftCardSettings,
    isGiftCardItem,
    createGiftCardFromInvoice,
    applyGiftCard,
    getAvailableGiftCards
  }
}
```

---

## Phase 7: Hooks & Events

### Files to Modify

**7.1 Update hooks.py**

File: `pos_next/hooks.py`

```python
doc_events = {
    "POS Invoice": {
        "on_submit": [
            "pos_next.api.gift_cards.process_gift_card_on_submit",
            "pos_next.api.gift_cards.create_gift_card_from_invoice"
        ],
        "on_cancel": "pos_next.api.gift_cards.process_gift_card_on_cancel"
    },
    "POS Coupon": {
        "after_insert": "pos_next.api.gift_cards.sync_to_erpnext_coupon",
        "on_update": "pos_next.api.gift_cards.update_erpnext_coupon",
        "on_trash": "pos_next.api.gift_cards.delete_erpnext_coupon"
    }
}
```

---

## Phase 8: Migration & Patches

### Files to Create

**8.1 Add custom fields patch**

File: `pos_next/patches/v1_x/add_gift_card_custom_fields.py`

```python
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    """Add custom fields to Coupon Code for gift card support"""

    custom_fields = {
        "Coupon Code": [
            {
                "fieldname": "gift_card_amount",
                "fieldtype": "Currency",
                "label": "Gift Card Amount",
                "insert_after": "pricing_rule",
                "fetch_from": "pricing_rule.discount_amount",
                "read_only": 1
            },
            {
                "fieldname": "coupon_code_residual",
                "fieldtype": "Link",
                "label": "Original Gift Card",
                "options": "Coupon Code",
                "insert_after": "gift_card_amount",
                "read_only": 1
            },
            {
                "fieldname": "pos_coupon",
                "fieldtype": "Link",
                "label": "POS Coupon",
                "options": "POS Coupon",
                "insert_after": "coupon_code_residual",
                "read_only": 1
            }
        ]
    }

    create_custom_fields(custom_fields)
```

**8.2 Update POS Coupon patch**

File: `pos_next/patches/v1_x/update_pos_coupon_for_gift_cards.py`

```python
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    """Add gift card fields to POS Coupon"""

    # Add new fields via Property Setter or direct update
    # Update existing Gift Card coupons to set gift_card_amount
    frappe.db.sql("""
        UPDATE `tabPOS Coupon`
        SET gift_card_amount = discount_amount,
            original_amount = discount_amount
        WHERE coupon_type = 'Gift Card'
        AND gift_card_amount IS NULL
    """)
```

---

## Summary of Files to Create/Modify

### New Files
| File | Description |
|------|-------------|
| `pos_next/api/gift_cards.py` | Gift card API endpoints |
| `pos_next/patches/v1_x/add_gift_card_custom_fields.py` | Custom fields migration |
| `pos_next/patches/v1_x/update_pos_coupon_for_gift_cards.py` | POS Coupon migration |
| `POS/src/components/sale/GiftCardDialog.vue` | Gift card UI dialog |
| `POS/src/composables/useGiftCard.js` | Gift card composable |

### Modified Files
| File | Changes |
|------|---------|
| `pos_next/pos_next/doctype/pos_settings/pos_settings.json` | Add gift card settings section |
| `pos_next/pos_next/doctype/pos_coupon/pos_coupon.json` | Add gift card fields, make customer optional |
| `pos_next/pos_next/doctype/pos_coupon/pos_coupon.py` | Remove mandatory customer, add sync logic |
| `pos_next/hooks.py` | Add doc_events for gift card processing |
| `POS/src/stores/settings.js` | Load gift card settings |
| `POS/src/pages/POSSale.vue` | Integrate gift card dialog |

---

## Testing Checklist

- [ ] Create gift card by selling gift card item
- [ ] Apply gift card to invoice (amount < total)
- [ ] Apply gift card to invoice (amount > total) - test splitting
- [ ] Apply gift card to invoice (amount = total)
- [ ] Gift card with customer restriction
- [ ] Gift card without customer (anonymous)
- [ ] ERPNext Coupon Code sync verification
- [ ] Pricing Rule creation verification
- [ ] Gift card cancellation/return handling
- [ ] Offline mode compatibility
