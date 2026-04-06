# Masters Pull — Sub-Spec (Plan 2)

**Status:** Approved
**Date:** 2026-04-06
**Parent Spec:** `docs/superpowers/specs/2026-04-05-branch-central-architecture-design.md`
**Scope:** Central-side API endpoints, branch-side masters puller, first adapters, tombstone hooks, scheduler integration. First real data flow — branch pulls master data from central.

---

## 1. Purpose

After Plan 1 laid the foundation (DocTypes, module skeleton, custom fields, registry), Plan 2 delivers the first real sync flow: branch pulls master data from central. After Plan 2, changing an Item on central will automatically appear on the branch within 5 minutes.

---

## 2. Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `changes_since` API | `pos_next/sync/api/changes.py` | Central endpoint: returns upserts + tombstones since watermark |
| `health` API | `pos_next/sync/api/health.py` | Central endpoint: server time, version info |
| `MastersPuller` | `pos_next/sync/masters_puller.py` | Branch job: iterates registry, calls changes_since, applies via adapter |
| Tombstone hooks | `pos_next/sync/hooks.py` | Central: on_trash writes tombstones for synced masters |
| Item adapter | `pos_next/sync/adapters/item.py` | Serialize/apply Item with children (barcodes, etc.) |
| Item Price adapter | `pos_next/sync/adapters/item_price.py` | Composite conflict key |
| Customer adapter | `pos_next/sync/adapters/customer.py` | Bidirectional, mobile-no dedup |
| Generic master adapter | `pos_next/sync/adapters/generic_master.py` | Default upsert for ~20 simple masters |
| Scheduler | `pos_next/hooks.py` | `pull_if_due` cron every minute |

**Not in scope:** Push transactions (Plan 3), failover (Plan 3), POS client changes, Sync Status dashboard.

---

## 3. Central-side API

### 3.1 `changes_since` endpoint

**Endpoint:** `GET /api/method/pos_next.sync.api.changes.changes_since`

**Parameters:**
- `doctype` — e.g. "Item"
- `since` — ISO datetime (the branch's watermark)
- `limit` — batch size (default 100)

**Response:**
```json
{
  "upserts": [
    {"name": "ITEM-001", "item_name": "Apple", "modified": "2026-04-06 10:00:00", "...": "..."},
  ],
  "tombstones": [
    {"reference_name": "ITEM-OLD", "deleted_at": "2026-04-06 09:00:00"}
  ],
  "next_since": "2026-04-06 10:00:00",
  "has_more": true
}
```

**Logic:**
1. Query `tab{doctype}` where `modified > since` ordered by `modified ASC`, limit + 1 (to detect `has_more`).
2. Query `Sync Tombstone` where `reference_doctype = doctype` and `deleted_at > since`.
3. `next_since` = max `modified` from returned upserts (branch advances its watermark to this).
4. Serialize each record via the adapter's `serialize()` method if an adapter is registered, otherwise `doc.as_dict()`.

**Security:** Whitelisted endpoint. Requires authentication — only accessible to users with `POS Next Sync Agent` role or System Manager. No branch-specific filtering needed for masters (all branches get the same masters).

### 3.2 `health` endpoint

**Endpoint:** `GET /api/method/pos_next.sync.api.health.health`

**Response:**
```json
{
  "server_time": "2026-04-06 10:00:00",
  "frappe_version": "15.97.0",
  "pos_next_version": "1.16.0",
  "site_role": "Central"
}
```

Used by branch to check connectivity and clock reference. No auth required (public).

---

## 4. Branch-side MastersPuller

**Class:** `MastersPuller` in `pos_next/sync/masters_puller.py`

### 4.1 Entry point

`pull_if_due()` — called every minute by the scheduler. Checks:
1. Is this site a Branch? (read Sync Site Config). If not, return.
2. Is `now() - last_pull_masters_at >= pull_masters_interval_seconds`? If not, return.
3. Is sync enabled? If not, return.
4. Run the pull cycle.

### 4.2 Pull cycle

1. Build a `SyncSession` via `transport.build_session_from_config()`.
2. Read Sync DocType Rules where `direction` includes `Central→Branch` and `enabled=1`, sorted by `priority ASC`.
3. For each rule:
   - Get adapter from registry (or use `BaseSyncAdapter` default).
   - Read `Sync Watermark` for this DocType (or `"2000-01-01 00:00:00"` if first pull).
   - Loop:
     - Call `changes_since(doctype, since=watermark, limit=batch_size)` via `SyncSession.get()`.
     - Apply upserts via adapter.
     - Delete tombstoned records.
     - Advance watermark to `next_since`.
     - Break when `has_more=false`.
4. Update `last_pull_masters_at` on the Sync Site Config.
5. Log result to `Sync Log`.

### 4.3 Applying upserts

For each record in the upserts list:
1. Call `adapter.validate_incoming(payload)` — skip if raises, log warning.
2. Compute hash via `payload.compute_hash(payload_dict)`.
3. Check `Sync Record State` — if hash matches `last_synced_hash`, skip (no change since last sync).
4. Call `adapter.apply_incoming(payload, "update")` — creates or updates locally.
5. Update `Sync Record State` with new hash and source="central".

### 4.4 Applying tombstones

For each tombstone:
- If the local record exists, delete it via `frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)`.
- Tombstones don't go through the adapter (delete is universal).
- Remove the corresponding `Sync Record State` row if it exists.

### 4.5 Error handling

- **Single record fails to apply:** Log to `Sync Log` with error details, skip it, continue with the rest of the batch. Don't advance watermark past the failed record's `modified` — it will be retried next cycle.
- **HTTP call to central fails:** Log error, set `last_sync_error` on Sync Site Config, stop the pull cycle. Retry next tick.
- **Network errors don't advance the watermark** — so no records are missed.

---

## 5. Adapters

### 5.1 ItemAdapter

**File:** `pos_next/sync/adapters/item.py`

- Serializes Item with child tables: Item Barcode, Item Default.
- On apply: standard upsert by name. Handles `has_variants` flag — doesn't delete template items that have local variants referencing them.
- Conflict key: `("name",)` (default).

### 5.2 ItemPriceAdapter

**File:** `pos_next/sync/adapters/item_price.py`

- Standard upsert.
- Conflict key: `("item_code", "price_list", "uom")` — Item Price names are auto-generated and may differ between sites, so identity is by the composite key.
- On apply: look up existing by composite key first. If found, update. If not, insert.

### 5.3 CustomerAdapter

**File:** `pos_next/sync/adapters/customer.py`

- Bidirectional (but in Plan 2 we only implement the pull direction — central→branch).
- Conflict key: `("mobile_no",)`.
- On apply: if a customer with the same `mobile_no` exists under a different name, return existing name (dedup — don't create duplicate). Otherwise standard upsert.

### 5.4 GenericMasterAdapter

**File:** `pos_next/sync/adapters/generic_master.py`

Covers all remaining Central→Branch masters with default `BaseSyncAdapter` behavior (upsert by name, no special logic):

POS Profile, Warehouse, Mode of Payment, Item Group, UOM, Price List, Company, Currency, Branch, Customer Group, Sales Person, Employee, User, Role Profile, Sales Taxes and Charges Template, Item Tax Template, POS Settings, POS Offer, POS Coupon, Loyalty Program, Item Barcode.

One class, registered for all these DocTypes at import time. If any later needs custom logic, extract into its own adapter file.

---

## 6. Tombstone Hooks

**File:** `pos_next/sync/hooks.py`

Register `on_trash` for every Central→Branch synced DocType:

```python
def write_tombstone_on_trash(doc, method=None):
    """on_trash hook: record deletion for branch replication."""
    from pos_next.sync.registry import get_adapter
    if not get_adapter(doc.doctype):
        return  # not a synced DocType
    SyncTombstone.record(doc.doctype, doc.name)
```

Registered via `doc_events` in `pos_next/hooks.py`. Only fires on sites where the DocType's adapter is registered (both central and branch — tombstones are useful on both sides for different flows).

---

## 7. Scheduler

Add to `pos_next/hooks.py` `scheduler_events`:

```python
scheduler_events = {
    "cron": {
        "* * * * *": [
            "pos_next.sync.masters_puller.pull_if_due",
        ]
    }
}
```

`pull_if_due` is self-throttled: compares `now() - last_pull_masters_at` against `pull_masters_interval_seconds` from Sync Site Config. On Central sites, it's a no-op (no Branch config exists).

---

## 8. Testing Strategy

### 8.1 Unit tests

- `test_changes_api.py` — mock Frappe ORM, verify `changes_since` returns correct upserts/tombstones/pagination.
- `test_masters_puller.py` — mock SyncSession HTTP responses, verify watermark advancement, error handling, skip-on-hash-match.
- `test_item_adapter.py` — verify serialize includes children, apply creates/updates correctly.
- `test_item_price_adapter.py` — verify composite conflict key lookup.
- `test_customer_adapter.py` — verify mobile_no dedup.
- `test_generic_adapter.py` — verify registration covers all expected DocTypes.

### 8.2 Integration tests (two-bench)

Using the dev environment (frappe-bench port 8000 as central, frappe-bench-16 port 8001 as branch):

1. **Happy path:** Create an Item on central → trigger pull on branch → verify Item exists on branch with correct data.
2. **Update propagation:** Update Item name/price on central → pull → verify updated on branch.
3. **Tombstone:** Delete Item on central → pull → verify deleted on branch.
4. **Pagination:** Create 150 Items on central → pull with batch_size=100 → verify all 150 arrive (two pages).
5. **Idempotency:** Pull twice → verify no duplicate records, hash-match skip works.
6. **Customer dedup:** Create Customer with same mobile_no on both sites → pull → verify single record (not duplicated).

### 8.3 Test runner

Add a `pos_next/sync/tests/run_plan2_tests.py` that runs all Plan 2 test modules.

---

## 9. End Result

After Plan 2 is implemented and deployed:

- Create/edit/delete an Item on central → within `pull_masters_interval_seconds` (default 5 min) → appears/updates/disappears on branch.
- Same for all 23+ master DocTypes in the Synced DocTypes Registry.
- Pull is paginated, idempotent, and resilient to transient network errors.
- Every pull cycle is logged to Sync Log.
- Watermarks track progress per DocType — if the branch goes offline for a day, it catches up on reconnect without missing records.
