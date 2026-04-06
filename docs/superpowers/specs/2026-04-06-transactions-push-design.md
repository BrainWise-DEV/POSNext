# Transactions Push — Sub-Spec (Plan 3)

**Status:** Approved
**Date:** 2026-04-06
**Parent Spec:** `docs/superpowers/specs/2026-04-05-branch-central-architecture-design.md`
**Scope:** Outbox hooks, outbox drainer, central ingest API, transaction adapters, scheduler integration. Branch pushes transaction data to central.

---

## 1. Purpose

Plan 2 delivered the pull direction (central → branch masters). Plan 3 delivers the push direction: branch pushes transaction data to central via the Outbox. After Plan 3, submitting a Sales Invoice on branch will automatically appear on central within 60 seconds as a read-only replica.

---

## 2. Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Outbox hooks | `pos_next/sync/hooks_outbox.py` | Capture transaction events into Sync Outbox |
| `OutboxDrainer` | `pos_next/sync/outbox_drainer.py` | Branch job: drain pending outbox rows, POST to central |
| Ingest API | `pos_next/sync/api/ingest.py` | Central endpoint: receive and apply pushed transactions |
| Sales Invoice adapter | `pos_next/sync/adapters/sales_invoice.py` | Naming validation, child tables, docstatus-aware insert |
| Payment Entry adapter | `pos_next/sync/adapters/payment_entry.py` | Standard with references child table |
| POS Opening Shift adapter | `pos_next/sync/adapters/pos_opening_shift.py` | Simple upsert, priority 10 |
| POS Closing Shift adapter | `pos_next/sync/adapters/pos_closing_shift.py` | Simple upsert, priority 20 |
| Stock Ledger Entry adapter | `pos_next/sync/adapters/stock_ledger_entry.py` | Insert-only, no updates |
| Scheduler | `pos_next/hooks.py` | `push_if_due` cron every minute |

**Already built (Plan 1):** Sync Outbox DocType with `enqueue()` + compaction, Sync Dead Letter, Sync History, Sync Log.

**Not in scope:** POS client failover (separate plan), Sync Status dashboard (already shows outbox stats from Plan 2).

---

## 3. Outbox Hooks — Capturing Transaction Events

### 3.1 Hook function

File: `pos_next/sync/hooks_outbox.py`

A generic doc_event hook that captures document changes into the Sync Outbox:

```python
def enqueue_to_outbox(doc, method=None):
    operation = _method_to_operation(method)
    SyncOutbox.enqueue(
        reference_doctype=doc.doctype,
        reference_name=doc.name,
        operation=operation,
        payload=json.dumps(to_payload(doc)),
        priority=_get_priority(doc.doctype),
    )
```

`_method_to_operation` maps Frappe doc_event method names to outbox operations:
- `on_submit` → `"submit"`
- `on_cancel` → `"cancel"`
- `on_update` / `on_update_after_submit` → `"update"`
- `after_insert` → `"insert"`
- `on_trash` → `"delete"`

`_get_priority` reads from the Sync DocType Rule registry, cached per process.

### 3.2 Registered events

| DocType | Events | Why |
|---------|--------|-----|
| Sales Invoice | `on_submit`, `on_cancel`, `on_update_after_submit` | Core transaction |
| Payment Entry | `on_submit`, `on_cancel` | Payment records |
| POS Opening Shift | `on_submit` | Shift lifecycle |
| POS Closing Shift | `on_submit` | Shift lifecycle |
| Stock Ledger Entry | `after_insert` | SLEs are auto-created, never manually submitted |
| Customer | `on_update` | Bidirectional — branch edits push up |

These are added to `doc_events` in `pos_next/hooks.py`, merged with existing entries.

### 3.3 Guard: only enqueue on Branch sites

The hook checks if a Branch Sync Site Config exists and is enabled before enqueueing. On Central sites, the hook is a no-op.

---

## 4. OutboxDrainer — Pushing to Central

### 4.1 Entry point

`push_if_due()` — cron every minute, self-throttled by `push_interval_seconds` (default 60s from Sync Site Config).

### 4.2 Drain cycle

1. Select outbox rows: `sync_status IN ('pending', 'failed') AND (next_attempt_at IS NULL OR next_attempt_at <= now())`, ordered by `priority ASC, creation ASC`, limit to `batch_size` per DocType.
2. Group rows by `reference_doctype`.
3. For each DocType batch, POST to central's ingest endpoint:
   ```
   POST /api/method/pos_next.sync.api.ingest.ingest
   Body: {"doctype": "Sales Invoice", "branch_code": "CAI", "records": [...]}
   ```
4. Process central's per-record response:
   - `status: "ok"` → set `sync_status='acked'`, `acked_at=now()`
   - `status: "error"` → increment attempts, set backoff, record error
5. After `attempts > MAX_ATTEMPTS_BEFORE_DEAD` (10): move row to `Sync Dead Letter`, delete from outbox.
6. Update `last_push_at` on Sync Site Config.
7. Log to `Sync Log`.

### 4.3 Exponential backoff

On failure: `next_attempt_at = now() + 2^attempts seconds`. This gives:
- Attempt 1: retry after 2s
- Attempt 2: after 4s
- Attempt 5: after 32s
- Attempt 10: after ~17 minutes (then dead-lettered)

### 4.4 Dead letter handling

When a row exceeds `MAX_ATTEMPTS_BEFORE_DEAD`:
1. Copy key fields to `Sync Dead Letter` (reference_doctype, reference_name, operation, last_error, attempts, payload, moved_at).
2. Delete the outbox row.
3. The Sync Status dashboard already shows dead letter count.

---

## 5. Central Ingest API

### 5.1 Endpoint

`POST /api/method/pos_next.sync.api.ingest.ingest`

### 5.2 Request format

```json
{
  "doctype": "Sales Invoice",
  "branch_code": "CAI",
  "records": [
    {"operation": "submit", "payload": {"name": "SINV-CAI-001", "sync_uuid": "...", ...}},
    {"operation": "cancel", "payload": {"name": "SINV-CAI-002", "sync_uuid": "...", ...}}
  ]
}
```

### 5.3 Processing logic per record

1. **Branch validation:** Verify `branch_code` in request matches the authenticated sync user's configured branch code.
2. **Idempotency check:** If `sync_uuid` exists locally for this DocType, skip (return `status: "ok"` — already processed).
3. **Adapter lookup:** Get adapter for the DocType.
4. **Validate:** Call `adapter.validate_incoming(payload)`.
5. **Apply:** Call `adapter.apply_incoming(payload, operation)`.
6. **Record state:** Update `Sync Record State` with hash and source=branch_code.

### 5.4 Response format

```json
{
  "results": [
    {"name": "SINV-CAI-001", "sync_uuid": "...", "status": "ok"},
    {"name": "SINV-CAI-002", "sync_uuid": "...", "status": "error", "error": "Validation failed: ..."}
  ]
}
```

### 5.5 Security

- Requires authentication (sync user session).
- `branch_code` in request must match the sync user's branch — prevents cross-branch impersonation.
- Replay protection: `sync_uuid` dedup makes every push idempotent.

---

## 6. Transaction Adapters

### 6.1 SalesInvoiceAdapter

File: `pos_next/sync/adapters/sales_invoice.py`

- **Validate:** Check `origin_branch` is present. Optionally check naming series matches branch code.
- **Apply on central:** Insert as read-only replica with `docstatus=1`. Do NOT call `doc.submit()` — that would trigger GL entries and stock updates on central. Use `_set_sync_flags` + insert with the `docstatus` already set in payload.
- **Child tables:** Include Sales Invoice Item, Sales Taxes and Charges, Payment Schedule.
- **Cancel:** Set `docstatus=2` via `db_update`, don't call `doc.cancel()`.

### 6.2 PaymentEntryAdapter

File: `pos_next/sync/adapters/payment_entry.py`

- Standard adapter. Include Payment Entry Reference child table.
- Same docstatus-aware pattern: insert with `docstatus=1`, cancel with `docstatus=2` via `db_update`.

### 6.3 POSOpeningShiftAdapter

File: `pos_next/sync/adapters/pos_opening_shift.py`

- Simple upsert by name. Priority 10 (synced first so other records can reference the shift).
- Docstatus-aware: insert with `docstatus=1`.

### 6.4 POSClosingShiftAdapter

File: `pos_next/sync/adapters/pos_closing_shift.py`

- Simple upsert. Priority 20.
- Docstatus-aware.

### 6.5 StockLedgerEntryAdapter

File: `pos_next/sync/adapters/stock_ledger_entry.py`

- **Insert-only:** SLEs are never updated after creation. If `sync_uuid` already exists locally, skip.
- SLEs don't have docstatus (they're not submittable).
- Use `db_insert` directly — SLEs should not trigger stock balance recomputation on central.

### 6.6 Common pattern: docstatus-aware insert

All submitted-document adapters (Sales Invoice, Payment Entry, POS Opening/Closing Shift) share a common pattern:

```python
def apply_incoming(self, payload, operation):
    if operation == "cancel":
        # Set docstatus=2 without triggering cancel hooks
        doc = frappe.get_doc(self.doctype, payload["name"])
        doc.docstatus = 2
        doc.db_update()
        return doc.name
    # For submit: insert with docstatus already set in payload
    return super().apply_incoming(payload, operation)
```

This is extracted into a `SubmittableAdapter` base class that all transaction adapters inherit from.

---

## 7. Scheduler

Add to `pos_next/hooks.py` `scheduler_events.cron`:

```python
"* * * * *": [
    "pos_next.sync.masters_puller.pull_if_due",
    "pos_next.sync.outbox_drainer.push_if_due",
]
```

Both run every minute, self-throttled by their respective interval settings.

---

## 8. Testing Strategy

### 8.1 Unit tests

- `test_hooks_outbox.py` — verify events are captured into outbox with correct operation/priority.
- `test_outbox_drainer.py` — mock HTTP, verify drain cycle, backoff, dead letter.
- `test_ingest_api.py` — verify idempotency, branch validation, per-record response.
- `test_sales_invoice_adapter.py` — verify docstatus-aware insert, cancel handling.
- `test_sle_adapter.py` — verify insert-only behavior, sync_uuid skip.

### 8.2 Integration test (two-bench)

1. Submit a Sales Invoice on branch (dev.pos) → trigger push → verify appears on central (pos-dev) with `docstatus=1`.
2. Cancel the invoice on branch → push → verify `docstatus=2` on central.
3. Submit POS Opening Shift → push → verify on central.
4. Idempotency: push same invoice twice → only one record on central.
5. Dead letter: mock central returning errors 11 times → verify outbox row moved to dead letter.

---

## 9. End Result

After Plan 3:
- Submit Sales Invoice on branch → within 60 seconds → read-only replica on central
- Cancel invoice on branch → reflected on central
- POS shifts synced to central (Opening first, then Closing)
- Payment Entries synced
- Stock Ledger Entries synced (insert-only replicas)
- Customer updates pushed bidirectionally
- Full outbox lifecycle: pending → syncing → acked (or failed → dead letter)
- Combined with Plan 2: **complete bidirectional sync** for all DocTypes in the registry
