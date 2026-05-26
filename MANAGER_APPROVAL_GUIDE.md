# Manager Approval Implementation Guide

## Overview
Manager approval is required for:
1. **Cash Refunds** - Above configurable threshold
2. **Discounts** - Above configurable threshold

## Files Created

### 1. **ManagerApprovalDialog.vue** 
   - Location: `/POS/src/components/ManagerApprovalDialog.vue`
   - Dialog that prompts for manager username/password
   - Emits `@approved` event on success
   - Handles loading and error states

### 2. **approvals.py (Backend API)**
   - Location: `/pos_next/api/approvals.py`
   - Function: `verify_manager_approval()`
   - Verifies manager credentials and role
   - Logs approval actions in Manager Approval Log

### 3. **Manager Approval Log (DocType)**
   - Location: `/pos_next/pos_next/doctype/manager_approval_log.json`
   - Tracks all manager approvals with timestamp
   - Read-only for audit trail

## Integration Points

### In ReturnInvoiceDialog.vue (for Cash Refunds)

```vue
<!-- Add to imports -->
import ManagerApprovalDialog from '@/components/ManagerApprovalDialog.vue'

<!-- Add to template -->
<ManagerApprovalDialog
  v-model="showManagerApproval"
  approval-type="Cash Refund"
  :amount="maxRefundableAmount"
  @approved="onManagerApproved"
/>

<!-- Modify submit button handler -->
async function submitReturn() {
  // Check if cash refund requires approval
  if (needsCashRefundApproval()) {
    showManagerApproval.value = true
    return
  }
  
  // Proceed with submit if approved or doesn't need approval
  if (isApproved.value) {
    await performSubmit()
  }
}

function needsCashRefundApproval() {
  const threshold = 5000 // Configurable
  const refundAmount = maxRefundableAmount.value
  return !addToCustomerCredit.value && refundAmount > threshold
}
```

### In PaymentDialog.vue (for Additional Discounts)

```vue
<!-- Add to imports -->
import ManagerApprovalDialog from '@/components/ManagerApprovalDialog.vue'

<!-- Add to template -->
<ManagerApprovalDialog
  v-model="showDiscountApproval"
  approval-type="Discount"
  :amount="calculatedAdditionalDiscount"
  @approved="onDiscountApproved"
/>

<!-- Modify submit button handler -->
async function submitPayment() {
  // Check if discount requires approval
  if (needsDiscountApproval()) {
    showDiscountApproval.value = true
    return
  }
  
  // Proceed with submit if approved
  if (isApproved.value) {
    await performSubmit()
  }
}

function needsDiscountApproval() {
  const threshold = 1000 // Configurable
  return calculatedAdditionalDiscount.value > threshold
}
```

## Configuration

Add these to POS Settings:

```
cash_refund_approval_threshold: 5000 (amount above which approval needed)
discount_approval_threshold: 1000 (amount above which approval needed)
require_manager_approval: 1 (enable/disable feature)
```

## Security Notes

1. **Password is sent via HTTPS only** in production
2. **Stored in audit log** with timestamp and manager name
3. **Manager must have role**: "POS Manager", "System Manager", or "Nexus POS Manager"
4. **Failed attempts are logged** for security monitoring

## Usage Flow

### Cash Refund Flow:
1. User creates return invoice
2. System checks: Is refund amount > threshold?
3. If YES → Shows ManagerApprovalDialog
4. Manager enters credentials
5. Backend verifies and logs approval
6. Return is processed only after approval

### Discount Flow:
1. User applies discount > threshold
2. System checks: Is discount amount > threshold?
3. If YES → Shows ManagerApprovalDialog
4. Manager enters credentials  
5. Backend verifies and logs approval
6. Discount is applied only after approval

## Error Handling

- Invalid credentials → "Invalid username or password"
- User disabled → "User is disabled"
- Insufficient role → "Insufficient permissions for manager approval"
- Password mismatch → Logged and user notified

## Audit Trail

All approvals are logged in "Manager Approval Log" DocType with:
- Requesting user
- Approving manager
- Approval type (Cash Refund/Discount)
- Amount
- Status (Approved/Rejected)
- Timestamp
