# POS Next Branch-Central Sync System

## Overview

POS Next Sync enables **two-way data synchronization** between a central ERPNext server and one or more branch ERPNext servers. This allows each branch to operate independently (even offline) while keeping data consistent across all sites.

```
                  CENTRAL ERPNext (cloud)
                  Authoritative for master data
                  Aggregate view of all branches
                         |
            +------------+------------+
            |                         |
     BRANCH (Cairo)            BRANCH (Alex)
     Local POS backend         Local POS backend
     Own stock, own GL         Own stock, own GL
```

### What Gets Synced

| Direction | What | Examples |
|-----------|------|---------|
| Central --> Branch | **Master data** | Items, Prices, Warehouses, POS Profiles, Users, Customers |
| Branch --> Central | **Transactions** | Sales Invoices, Payments, POS Shifts, Stock Ledger Entries |
| Both ways | **Customers** | New customers created at branch push to central; central edits pull to branch |

### Key Design Principles

1. **Branch initiates all communication** — Central is passive. Branches behind NAT/firewall only need outbound HTTPS.
2. **Eventually consistent** — Not real-time. Default intervals: masters pull every 5 minutes, transaction push every 60 seconds.
3. **Idempotent** — Every sync operation can be safely retried. `sync_uuid` on each record prevents duplicates.
4. **Version-agnostic** — The same pos_next codebase runs on both Frappe v15 and v16. A v15 central can sync with a v16 branch.

---

## Glossary

| Term | Definition |
|------|-----------|
| **Central** | The cloud/HQ ERPNext site. Authoritative source for master data (Items, Prices, etc.). Receives transaction replicas from branches. |
| **Branch** | An on-premise ERPNext site running POS. Creates transactions locally, pulls masters from central. |
| **Branch Code** | Short uppercase identifier for a branch (e.g., `CAI` for Cairo, `ALX` for Alexandria). Encoded in naming series. |
| **Sync Site Config** | The configuration DocType that defines a site's role (Branch/Central), connection settings, and sync rules. |
| **Synced DocTypes Registry** | The child table on Sync Site Config listing which DocTypes to sync, in which direction, with what strategy. |
| **Watermark** | A per-DocType timestamp marking "I've pulled all records up to this point." Used for incremental pull. |
| **Outbox** | A queue of pending changes (submit, cancel, update) waiting to be pushed from branch to central. |
| **Tombstone** | A record of a deletion. When a master is deleted on central, a tombstone tells branches to delete it too. |
| **sync_uuid** | A UUID on every synced transaction record. The global dedup key — prevents the same record from being applied twice. |
| **origin_branch** | The `branch_code` of the site that created a record. Never changes after creation. |
| **Adapter** | A Python class that knows how to serialize, validate, and apply a specific DocType during sync. |
| **Dead Letter** | An outbox row that failed too many times (default: 10). Moved to a separate queue for manual inspection. |
| **Naming Series** | Branch-coded invoice numbering (e.g., `SINV-CAI-.#####`). Set on the POS Profile. Ensures unique names across branches. |

---

## Architecture

### System Topology

```
+-----------------------------------------+     +-----------------------------------------+
|  CENTRAL (e.g., hq.example.com)         |     |  BRANCH (e.g., cairo-store.local)        |
|                                         |     |                                         |
|  Sync Site Config: role=Central         |     |  Sync Site Config: role=Branch           |
|                                         |     |    central_url = https://hq.example.com  |
|  API Endpoints:                         |     |    branch_code = CAI                     |
|    /api/method/pos_next.sync.api.       |     |                                         |
|      changes.changes_since              |     |  Scheduled Jobs (every minute):          |
|      ingest.ingest                      |     |    pull_if_due  (masters, every 5 min)   |
|      health.health                      |     |    push_if_due  (transactions, every 1m) |
|      status.get_sync_status             |     |                                         |
|                                         |     |  Outbox: queued transaction changes      |
|  Tombstone hooks: on_trash for masters  |     |  Watermarks: per-DocType pull progress   |
+-----------------------------------------+     +-----------------------------------------+
         ^                                                  |
         |          HTTPS (branch initiates)                |
         +--------------------------------------------------+
```

### Data Flow: Masters Pull (Central -> Branch)

```
Central                          Branch
  |                                |
  |   GET changes_since            |
  |   ?doctype=Item                |
  |   &since=2026-04-05            |
  |   &limit=100                   |
  |<-------------------------------|
  |                                |
  |   {upserts: [...],            |
  |    tombstones: [...],          |
  |    next_since: "...",          |
  |    has_more: true}             |
  |------------------------------->|
  |                                |
  |                          Apply upserts via adapter
  |                          Delete tombstoned records
  |                          Advance watermark
  |                          Repeat if has_more=true
```

**How it works:**
1. The `MastersPuller` runs every minute on the branch (self-throttled to the configured interval, default 5 minutes).
2. It reads the Synced DocTypes Registry for all `Central->Branch` rules, sorted by priority.
3. For each DocType, it calls the central's `changes_since` API with the current watermark.
4. Central returns records modified after the watermark, plus tombstones for deleted records.
5. Branch applies each record through the appropriate adapter, then advances the watermark.
6. If `has_more=true`, it fetches the next page. This continues until all changes are pulled.

### Data Flow: Transaction Push (Branch -> Central)

```
Branch                           Central
  |                                |
  |  [Sales Invoice submitted]     |
  |  -> Outbox hook fires          |
  |  -> Row added to Sync Outbox   |
  |                                |
  |  [OutboxDrainer runs]          |
  |  POST ingest                   |
  |  {doctype: "Sales Invoice",   |
  |   branch_code: "CAI",         |
  |   records: [{operation, payload}]}
  |------------------------------->|
  |                                |
  |                          Check sync_uuid (idempotent)
  |                          Apply via SalesInvoiceAdapter
  |                          Insert as read-only replica
  |                                |
  |   {results: [{status: "ok"}]} |
  |<-------------------------------|
  |                                |
  |  Mark outbox row as "acked"    |
```

**How it works:**
1. When a transaction document is submitted/cancelled on the branch, a `doc_event` hook captures it into the Sync Outbox.
2. The `OutboxDrainer` runs every minute, picks up pending outbox rows, groups them by DocType, and POSTs them to central's ingest API.
3. Central receives the batch, checks `sync_uuid` for idempotency, and applies each record via the appropriate adapter.
4. Submitted documents are inserted on central as **read-only replicas** — no `doc.submit()` is called (which would trigger GL entries, stock updates, etc.).
5. Central returns per-record status. Branch marks successful rows as "acked" and increments retry count on failures.
6. After 10 consecutive failures, the row is moved to the Dead Letter queue.

---

## Configuration

### Setting Up Central

1. Install POS Next on the central site.
2. Run `bench --site <central-site> migrate` to create Sync DocTypes.
3. Open **Sync Site Config** in the desk.
4. Set **Site Role** = `Central`, **Branch Code** = a code for the branch you're registering (e.g., `CAI`).
5. Save. The Synced DocTypes Registry will auto-populate with 32 default rules.

### Setting Up a Branch

1. Install POS Next on the branch site.
2. Run `bench --site <branch-site> migrate`.
3. Open **Sync Site Config**.
4. Set:
   - **Site Role** = `Branch`
   - **Branch Code** = e.g., `CAI`
   - **Central URL** = `https://your-central-site.com`
   - **Sync Username** = a Frappe user on central with the `POS Next Sync Agent` role
   - **Sync Password** = that user's password
5. Click **Test Sync Connection** to verify.
6. Save. Sync will begin automatically on the next scheduler tick.

### Naming Series Convention

Each branch must use a **branch-coded naming series** for transactions. This is set on the branch's POS Profile:

| Branch | Sales Invoice Series | Payment Entry Series |
|--------|---------------------|---------------------|
| Cairo Downtown | `SINV-CAI-.#####` | `PE-CAI-.#####` |
| Alexandria Port | `SINV-ALX-.#####` | `PE-ALX-.#####` |
| HQ | `SINV-HQ-.#####` | `PE-HQ-.#####` |

This ensures:
- No naming collisions between branches
- Every invoice on central can be traced back to its origin branch
- The `SalesInvoiceAdapter` validates that the naming series matches the `origin_branch`

### Sync Intervals

| Setting | Default | Where Set |
|---------|---------|-----------|
| Pull Masters Interval | 300 seconds (5 min) | Sync Site Config |
| Push Interval | 60 seconds (1 min) | Sync Site Config |
| Max Retry Attempts | 10 | `pos_next/sync/defaults.py` |

Intervals can be changed on the Sync Site Config form without restarting the server.

---

## Synced DocTypes Registry

The registry is a child table on Sync Site Config that controls which DocTypes sync and how.

### Fields

| Field | Description |
|-------|-------------|
| **DocType** | The Frappe DocType to sync (e.g., `Item`, `Sales Invoice`) |
| **Direction** | `Central->Branch` (masters), `Branch->Central` (transactions), or `Bidirectional` |
| **CDC Strategy** | `Watermark` (for pull — track by modified timestamp) or `Outbox` (for push — queue changes) |
| **Conflict Rule** | How to resolve conflicts: `Central-Wins`, `Branch-Wins`, `Last-Write-Wins`, `Field-Level-LWW`, or `Manual` |
| **Priority** | Lower number = synced first. POS Opening Shift (10) syncs before Sales Invoice (50). |
| **Batch Size** | Records per API call (default 100) |
| **Enabled** | Toggle sync for this DocType on/off |

### Default Rules (32 total)

**Masters (Central -> Branch, Watermark, Central-Wins):**
Item, Item Price, Item Group, Item Barcode, UOM, Price List, POS Profile, POS Settings, POS Offer, POS Coupon, Loyalty Program, Warehouse, Branch, Company, Currency, Mode of Payment, Sales Taxes Template, Item Tax Template, User, Role Profile, Employee, Sales Person, Customer Group

**Transactions (Branch -> Central, Outbox, Branch-Wins):**
POS Opening Shift (priority 10), POS Closing Shift (20), Sales Invoice (50), Payment Entry (50), Stock Ledger Entry (60), Offline Invoice Sync (70)

**Bidirectional:**
Customer (Outbox, Field-Level-LWW, priority 50), Wallet (60), Wallet Transaction (60)

---

## Adapters

Adapters are the per-DocType logic that handles how a record is serialized, validated, and applied during sync. Every synced DocType has an adapter registered in the adapter registry.

### Adapter Hierarchy

```
BaseSyncAdapter                   — Default: upsert by name, db_update for updates
  |
  +-- GenericMasterAdapter        — No special logic (19 simple masters)
  |
  +-- ItemAdapter                 — Child table handling, variant-aware delete
  |
  +-- ItemPriceAdapter            — Composite conflict key (item_code + price_list + uom)
  |
  +-- CustomerAdapter             — mobile_no dedup for bidirectional sync
  |
  +-- SubmittableAdapter          — docstatus-aware insert/cancel (no re-submission)
       |
       +-- SalesInvoiceAdapter    — Naming series validation, child tables
       |
       +-- PaymentEntryAdapter    — Include references child table
       |
       +-- POSOpeningShiftAdapter — Priority 10 (synced first)
       |
       +-- POSClosingShiftAdapter — Priority 20
       |
  +-- StockLedgerEntryAdapter     — Insert-only (SLEs never updated)
```

### How Adapters Work

1. **serialize(doc)** — Convert a Frappe document to a sync payload dict.
2. **validate_incoming(payload)** — Check if the incoming payload is valid (e.g., naming series matches branch).
3. **pre_apply_transform(payload)** — Clean up the payload before applying (strip meta fields, handle child tables).
4. **apply_incoming(payload, operation)** — Create or update the local record.
5. **conflict_key(payload)** — What uniquely identifies this record (default: `name`).

### Key Patterns

**db_update for updates:** When updating an existing record, adapters use `doc.db_update()` instead of `doc.save()`. This bypasses all Frappe hooks and validations — synced data was already validated on the source site. This prevents issues like:
- Cross-version method differences (v15 vs v16)
- NestedSet recursion on tree DocTypes (Item Group)
- Link validation failures for records not yet pulled

**Docstatus-aware insert:** Submitted documents (Sales Invoice, Payment Entry) arrive at central with `docstatus=1`. The `SubmittableAdapter` inserts them directly with the docstatus already set — it never calls `doc.submit()`, which would trigger GL entries and stock updates. Central holds these as **read-only replicas**.

**sync_uuid dedup:** The ingest API checks if a record with the same `sync_uuid` already exists before applying. This makes every push idempotent — safe to retry after timeouts.

---

## DocTypes Reference

### Sync Site Config
The main configuration record. Singleton on Branch sites, one-per-branch on Central.

| Field | Branch | Central |
|-------|--------|---------|
| site_role | "Branch" | "Central" |
| branch_code | e.g., "CAI" | e.g., "CAI" (the branch being registered) |
| central_url | https://hq.example.com | — |
| sync_username | sync user on central | — |
| sync_password | encrypted | — |
| push_interval_seconds | 60 | — |
| pull_masters_interval_seconds | 300 | — |
| pull_failover_interval_seconds | 120 | — |
| synced_doctypes | 32 default rules | 32 default rules |

### Sync Outbox
Queue of pending changes to push from branch to central.

| Field | Description |
|-------|-------------|
| reference_doctype | e.g., "Sales Invoice" |
| reference_name | e.g., "SINV-CAI-00001" |
| operation | insert / update / submit / cancel / delete |
| sync_status | pending / syncing / acked / failed / dead |
| payload | Full JSON snapshot of the document |
| priority | From Sync DocType Rule |
| attempts | Number of push attempts |
| next_attempt_at | Exponential backoff: 2^attempts seconds |
| last_error | Error message from last failed attempt |

**Compaction:** Multiple updates to the same record collapse into one pending row (back-pressure defense). Terminal operations (submit, cancel, delete) always create new rows.

### Sync Watermark
One row per DocType, tracks pull progress.

| Field | Description |
|-------|-------------|
| doctype_name | e.g., "Item" |
| last_modified | Max `modified` from the last successful pull |
| last_pulled_at | When the pull happened |
| records_pulled | Count of records in last pull |

### Sync Tombstone
Records of master deletions on central, so branches can replay the delete.

### Sync Record State
Per-record tracking: stores the hash of the last synced version. If the hash matches, the record is skipped (no change).

### Sync Conflict
Manual resolution queue. When `conflict_rule = "Manual"`, both versions are stored here for human review.

### Sync Log
Append-only log of every sync operation (pull/push) with status, duration, record count, and errors.

### Sync Dead Letter
Outbox rows that exceeded the max retry count. Awaiting manual inspection and retry.

### Sync History
Archived acknowledged outbox rows (for audit trail).

---

## API Endpoints

### `changes_since` (Central)

```
GET /api/method/pos_next.sync.api.changes.changes_since
  ?doctype=Item
  &since=2026-04-05 00:00:00
  &limit=100
```

Returns modified records + tombstones since the given timestamp. Used by `MastersPuller`.

### `ingest` (Central)

```
POST /api/method/pos_next.sync.api.ingest.ingest
Body: {
  "doctype": "Sales Invoice",
  "branch_code": "CAI",
  "records": [{"operation": "submit", "payload": {...}}]
}
```

Receives pushed transactions from branches. Returns per-record status.

### `health` (Central)

```
GET /api/method/pos_next.sync.api.health.health
```

Public endpoint. Returns server time, Frappe version, POS Next version, site role. Used for connectivity checks.

### `get_sync_status` (Both)

```
GET /api/method/pos_next.sync.api.status.get_sync_status
```

Returns dashboard data: outbox stats, watermarks, recent logs, conflict count.

---

## Conflict Resolution

When the same record is modified on both central and branch, a conflict occurs. The resolution strategy is configured per DocType in the Synced DocTypes Registry.

| Strategy | Behavior |
|----------|----------|
| **Central-Wins** | Central's version always wins. Used for masters (Items, Prices). |
| **Branch-Wins** | Branch's version always wins. Used for transactions. |
| **Last-Write-Wins** | The version with the newer `modified` timestamp wins. Ties go to incoming. |
| **Field-Level-LWW** | Each field is resolved independently by timestamp. Used for Customers — if central edits the email and branch edits the phone, both changes are kept. |
| **Manual** | Neither version is applied. Both are stored in the Sync Conflict queue for human review. |

---

## Custom Fields

The sync system adds three custom fields to tracked DocTypes (Sales Invoice, Payment Entry, Stock Ledger Entry, POS Opening Shift, POS Closing Shift, Customer):

| Field | Type | Purpose |
|-------|------|---------|
| `sync_uuid` | Data (unique) | Cross-site dedup key. Auto-generated UUID4 on creation. |
| `origin_branch` | Data | The `branch_code` of the site that created this record. Never changes. |
| `synced_from_failover` | Check | Set to 1 when central writes a record as a proxy during branch outage (future feature). |

---

## Security

- **Transport:** HTTPS required for `central_url` (enforced at save time). A `POS_NEXT_SYNC_ALLOW_HTTP=1` env var bypasses this for local development only.
- **Authentication:** Session login (username + password) using a real Frappe User per branch. The `sync_password` is stored using Frappe's Password field type (encrypted at rest).
- **Authorization:** Dedicated `POS Next Sync Agent` role. Sync users should only have this role.
- **Replay protection:** `sync_uuid` dedup prevents the same record from being applied twice.
- **Branch isolation:** The ingest API validates that `branch_code` matches the authenticated user's branch.

---

## Monitoring

### Sync Status Dashboard

Open any Sync Site Config record in the desk to see:
- **Last Masters Pull** — when the last pull happened
- **Outbox** — pending, failed, dead letter counts
- **Watermarks** — per-DocType pull progress (collapsible table)
- **Recent Sync Logs** — last 10 operations with status, duration, record count

### Sync Log

Navigate to `/app/sync-log` to see the full history of sync operations.

### Sync Dead Letter

Navigate to `/app/sync-dead-letter` to see failed outbox rows that need manual attention.

### Sync Conflict

Navigate to `/app/sync-conflict` to review and resolve conflicts (when using Manual conflict rule).

---

## Troubleshooting

### "Test Sync Connection" shows "Network error"

- Verify `central_url` is correct and reachable from the branch server.
- Check that the sync user exists on central and has the `POS Next Sync Agent` role.
- If using HTTP locally, ensure `POS_NEXT_SYNC_ALLOW_HTTP=1` is set in the environment.

### Masters not pulling

1. Check Sync Site Config: is `enabled` checked? Is `pull_masters_interval_seconds` reasonable?
2. Check Sync Log for errors: `/app/sync-log`
3. Check if the scheduler is running: `bench --site <site> scheduler enable`
4. After adding the cron job, run `bench --site <site> migrate` to register it.
5. Restart bench: `bench restart` or `Ctrl+C && bench start`

### Transactions not pushing

1. Check Sync Outbox: `/app/sync-outbox` — are rows pending or failed?
2. Check `last_error` on failed rows for the specific error.
3. Check if the central's ingest endpoint is reachable.
4. Dead-lettered rows need manual attention: `/app/sync-dead-letter`

### Outbox rows stuck as "failed"

Each failed row has exponential backoff (`next_attempt_at`). It will retry automatically:
- Attempt 1: retry after 2 seconds
- Attempt 5: retry after 32 seconds
- Attempt 10: dead-lettered (~17 minutes total)

### Cross-version errors

The sync system uses `db_update()` for updates and `_set_sync_flags()` for inserts to bypass Frappe validations. If you see validation errors during sync, it may be a field that exists on one Frappe version but not the other. Check the Error Log for details.

---

## File Structure

```
pos_next/sync/
  __init__.py
  defaults.py           # Constants: intervals, batch sizes, retry limits
  exceptions.py         # SyncError hierarchy
  payload.py            # Serialize, hash, strip meta fields
  registry.py           # Adapter registry: register/get/list
  auth.py               # SyncSession: login, session management, auto-relogin
  transport.py           # Build SyncSession from Sync Site Config
  conflict.py           # Conflict resolution: 5 strategies
  seeds.py              # Default Synced DocTypes Registry rules
  masters_puller.py     # Branch: pull masters from central
  outbox_drainer.py     # Branch: push transactions to central
  hooks.py              # Tombstone on_trash hooks
  hooks_uuid.py         # Auto-fill sync_uuid + origin_branch
  hooks_outbox.py       # Enqueue transaction events to outbox
  adapters/
    base.py             # BaseSyncAdapter + _set_sync_flags
    submittable.py      # SubmittableAdapter: docstatus-aware
    generic_master.py   # 19 simple masters
    item.py             # Item: variant-aware
    item_price.py       # Item Price: composite key
    customer.py         # Customer: mobile_no dedup
    sales_invoice.py    # Sales Invoice: naming series validation
    payment_entry.py    # Payment Entry
    pos_opening_shift.py
    pos_closing_shift.py
    stock_ledger_entry.py  # Insert-only
  api/
    changes.py          # Central: changes_since endpoint
    ingest.py           # Central: receive pushed transactions
    health.py           # Public: server info
    status.py           # Dashboard: sync status summary
  tests/
    run_all_tests.py    # Plan 1 test runner (11 modules)
    run_plan2_tests.py  # Plan 2 test runner (6 modules)
    run_plan3_tests.py  # Plan 3 test runner (4 modules)
    ... (21 test modules total)

pos_next/pos_next/doctype/
  sync_site_config/     # Main config DocType
  sync_doctype_rule/    # Child: per-DocType sync rules
  sync_sibling_branch/  # Child: read-only branch list
  sync_outbox/          # Pending push queue
  sync_watermark/       # Pull progress tracking
  sync_tombstone/       # Deletion records
  sync_record_state/    # Per-record hash tracking
  sync_field_timestamp/ # Per-field timestamps (for Field-Level-LWW)
  sync_conflict/        # Manual resolution queue
  sync_log/             # Operation log
  sync_dead_letter/     # Failed push queue
  sync_history/         # Archived acknowledged rows
```

---

## Development Setup

For development with two local benches:

```
frappe-bench   (port 8000) = Central  (site: pos-central)
frappe-bench-16 (port 8001) = Branch   (site: dev.pos)
```

### Quick Setup

```bash
# On frappe-bench (central):
POS_NEXT_SYNC_ALLOW_HTTP=1 bench --site pos-central execute \
  pos_next.sync.tests._setup_multi_site.setup_as_central

# On frappe-bench-16 (branch):
POS_NEXT_SYNC_ALLOW_HTTP=1 bench --site dev.pos execute \
  pos_next.sync.tests._setup_multi_site.setup_as_branch
```

### Running Tests

```bash
# All Plan 1 tests (foundation):
bench --site pos-dev execute pos_next.sync.tests.run_all_tests.run

# All Plan 2 tests (masters pull):
bench --site pos-dev execute pos_next.sync.tests.run_plan2_tests.run

# All Plan 3 tests (transaction push):
bench --site pos-dev execute pos_next.sync.tests.run_plan3_tests.run
```

Never use `bench run-tests` — it wipes site data.
