# Branch ↔ Central Sync — Umbrella Architecture Design

**Status:** Draft for review
**Date:** 2026-04-05
**Scope:** Cross-cutting architecture. Sub-specs cover per-entity sync (masters, stock, transactions, conflict reconciliation) in separate documents.

---

## 1. Purpose

Enable POS Next to run as a two-tier deployment: a **central** ERPNext site that holds authoritative master data and an aggregate view of all branches, plus one or more **branch** ERPNext sites that run independently, keep selling when disconnected, and reconcile bidirectionally with central when connectivity returns.

The POS Vue client can additionally **fail over** to central when its branch ERPNext is unreachable, writing invoices directly to central as a proxy, with branch catching up on recovery.

This umbrella document fixes the architecture decisions shared across all entity-level sync work: topology, transport, change capture, identity, conflict resolution, failover semantics, observability, and security. Each entity type (Item, Customer, Sales Invoice, Stock Ledger Entry, …) will get its own sub-spec reusing these decisions.

---

## 2. Goals and non-goals

### Goals

- Two full ERPNext installs, both operational independently, reconciling bidirectionally.
- Bidirectional sync for every synced entity, with **per-entity conflict resolution rules** chosen by ops.
- POS client failover to central when branch ERPNext is down, preserving naming series and origin tagging.
- Three-source data durability during failover: central, POS client IndexedDB, branch.
- Background-worker driven; sync never blocks the POS UI.
- Branches behind NAT: all HTTPS initiated by branch; no inbound to branch required.
- Identical naming for masters across sites; branch-coded naming series for transactions.
- Observable: dashboard, alerts, dead-letter queue, conflict queue.

### Non-goals

- Syncing GL Entries (each site computes its own GL from synced source documents).
- Multi-company per branch (one branch = one company, initially).
- Print format syncing.
- User password reset UI across sites (standard Frappe reset flow at the relevant site).
- Offline-writing at branch when central is down — branch keeps running and queues; covered implicitly.

---

## 3. Topology

Two full ERPNext sites, asymmetric roles:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         CENTRAL ERPNext (cloud)                              │
│  • Authoritative for masters                                                 │
│  • Aggregate view of all branches' transactions (read-only replicas)         │
│  • Failover backend when a branch ERPNext is unreachable                     │
│  • Holds Sync Site Config records: one per registered branch                 │
└────────────────────────────────────────────────────────────────────────────┘
                          ▲                    ▲
           HTTPS push      │                    │  HTTPS (failover writes)
           (branch→central)│                    │  (POS client→central)
                          │                    │
┌────────────────────────┴────┐   ┌────────────┴────────────────────────┐
│   BRANCH ERPNext (on-prem)  │   │         POS Vue Client               │
│  • Local POS backend        │   │  Primary:  current origin (branch)   │
│  • Own stock, own GL        │   │  Failover: central_api_url           │
│  • Owns branch warehouses   │   │  Offline:  IndexedDB queue           │
│  • Pulls masters            │   │                                      │
│  • Pulls own failover txns  │   │  Health-checks per request           │
│  • Pushes transactions up   │   │  (not sticky)                        │
└─────────────────────────────┘   └──────────────────────────────────────┘
```

**Invariant:** Every HTTPS call between sites is initiated by the branch. Central is passive — it exposes endpoints and waits. Branches behind consumer-grade internet need only outbound HTTPS.

**POS client configuration:** Bootstrap API serves `central_api_url` and `origin_branch_code` to the Vue app. `branch_api_url` is the current origin (the Vue app's host), so no additional URL config is needed for the primary path.

**Three sync flows, all background-scheduled:**

| Flow | Direction | Driver | Default Interval | Payload |
|------|-----------|--------|------------------|---------|
| Push Transactions | Branch → Central | Branch cron | 60s | Outbox rows: Sales Invoice, Payment Entry, Shifts, SLEs, new Customers |
| Pull Masters | Central → Branch | Branch cron | 300s | Items, Item Prices, POS Profiles, Warehouses, Customers, Users, etc. |
| Pull Failover | Central → Branch | Branch cron | 120s | Transactions central wrote on the branch's behalf during outage |

Intervals are stored in Sync Site Config and read each cron tick; ops can retune without redeploy.

---

## 4. Sync Site Config DocType

Single DocType, **role-dependent cardinality** — singleton on a branch, multi-row on central.

### 4.1 Fields

```
site_role                      Select    "Branch" | "Central"
branch_code                    Data      e.g. "CAI", "ALX", "HQ"; unique per site
branch                         Link      ERPNext Branch
enabled                        Check

─── Branch-only (when site_role=Branch) ───
central_url                    Data      https://hq.example.com
sync_username                  Data      real Frappe User at central
sync_password                  Password  encrypted at rest
push_interval_seconds          Int       default 60
pull_masters_interval_seconds  Int       default 300
pull_failover_interval_seconds Int       default 120
last_push_at                   Datetime
last_pull_masters_at           Datetime
last_pull_failover_at          Datetime
outbox_depth                   Int       read-only, live
last_sync_error                Small Text read-only
sibling_branches               Table (ro) list of other branches, synced down from central

─── Central-only (when site_role=Central) ───
registered_branch_url          Data      optional, for central→branch health ping
notes                          Small Text

─── Both roles (central is authoritative for the registry) ───
synced_doctypes                Table → Sync DocType Rule
```

### 4.2 Sync DocType Rule (child)

```
doctype        Link     the DocType to sync
direction      Select   "Central→Branch" | "Branch→Central" | "Bidirectional"
cdc_strategy   Select   "Outbox" | "Watermark"
conflict_rule  Select   "Last-Write-Wins" | "Central-Wins" | "Branch-Wins" | "Field-Level-LWW" | "Manual"
priority       Int      lower = synced earlier
enabled        Check
batch_size     Int      default 100
```

### 4.3 Cardinality enforcement

In `validate`/`before_insert`:

- If `site_role == "Branch"` and `frappe.db.count("Sync Site Config") > 0`: reject with a clear error.
- If `site_role == "Central"`: unlimited rows (one per registered branch).

### 4.4 Seeded defaults

On install, `synced_doctypes` is populated with the default list in §8. Operators can add/remove rows later.

### 4.5 Credentials & session login

Machine-to-machine auth uses **username + password session login** against central — no API keys.

Flow:

1. Sync worker reads `central_url`, `sync_username`, `sync_password` from Sync Site Config.
2. `POST {central_url}/api/method/login` with form-encoded `{usr, pwd}`.
3. Receives `sid` cookie; stores in-memory for worker process lifetime.
4. All subsequent sync requests include the `sid` cookie.
5. On 401/403, worker re-logs in and retries once.

A helper `pos_next/sync/auth.py` wraps login/session/retry so adapters never see login mechanics.

The sync user is a real Frappe User with the `POS Next Sync Agent` role (§9.2), one dedicated user per branch.

---

## 5. Change capture

### 5.1 Outbox (for transactions)

Every DocType with `cdc_strategy = "Outbox"` in the registry gets hooked through generic Frappe doc_events (`on_update`, `on_submit`, `on_cancel`, `on_trash`). Each event inserts a row into:

```
DocType: Sync Outbox
reference_doctype   Link      e.g. "Sales Invoice"
reference_name      Data
operation           Select    "insert" | "update" | "submit" | "cancel" | "delete"
payload             Long Text JSON snapshot at event time
priority            Int       from Sync DocType Rule.priority
sync_status         Select    "pending" | "syncing" | "acked" | "failed" | "dead"
attempts            Int
last_error          Small Text
next_attempt_at     Datetime  for exponential backoff
created_at          Datetime
acked_at            Datetime

Indexes: (sync_status, priority, next_attempt_at), (reference_doctype, reference_name)
```

**Auto-compaction on write** (back-pressure defense): before insert, check for an existing `pending` row on `(reference_doctype, reference_name, operation)`. If found, update that row in place instead of inserting a new one. Terminal-state operations (`submit`, `cancel`, `delete`) are never compacted — they always insert.

**Draining** (`push_outbox` scheduled job):

- Select rows ordered by `(priority ASC, created_at ASC)` where `sync_status IN ('pending','failed') AND next_attempt_at <= now()`.
- POST each to central's ingest endpoint, batching by DocType up to `batch_size`.
- On 2xx: set `sync_status='acked'`, `acked_at=now()`.
- On failure: `attempts += 1`, `next_attempt_at = now() + 2^attempts seconds`, `sync_status='failed'` with `last_error`.
- After `attempts > 10`: set `sync_status='dead'`, move to Sync Dead Letter list, alert ops.

### 5.2 Watermark + Tombstones (for masters pulled from central)

```
DocType: Sync Watermark
doctype          Link     unique; one row per pulled DocType
last_modified    Datetime max(modified) seen on last successful pull
last_pulled_at   Datetime
records_pulled   Int

DocType: Sync Tombstone   (lives on central; written by on_trash hook)
reference_doctype Link
reference_name    Data
deleted_at        Datetime
```

**Pull flow** (`pull_masters` scheduled job on branch):

For each `synced_doctypes` row where `direction` includes `Central→Branch` and `cdc_strategy='Watermark'`:

```
GET {central_url}/api/method/pos_next.sync.api.changes.changes_since
    ?doctype=Item&since=<watermark.last_modified>&limit=<batch_size>
```

Central returns `{upserts: [...], tombstones: [...], next_since: "<timestamp>"}`. Branch applies upserts/deletes via the adapter, then advances its watermark to `next_since`.

**Why tombstones:** a deleted row cannot be found by `modified > watermark`. Central writes a tombstone on `on_trash`; branches receive and apply it.

**Clock skew:** watermarks are set from timestamps reported by central, not branch, so branch↔central clock skew cannot cause missed records.

### 5.3 Retention

- Acknowledged outbox rows: archived to `Sync History` after 7 days; purged from history after 90 days (both configurable in Sync Site Config).
- Tombstones: retained for 90 days (long enough for any branch with a reasonable outage to catch the delete).

---

## 6. Sync engine — pluggable adapter architecture

### 6.1 Module layout

```
pos_next/sync/
├── __init__.py
├── engine.py              # SyncEngine — orchestrates push/pull cycles
├── auth.py                # login/session/retry helper
├── outbox.py              # OutboxDrainer — push_outbox job
├── masters_puller.py      # MasterPuller — pull_masters job
├── failover_puller.py     # FailoverPuller — pull_failover job
├── hooks.py               # generic doc_events handlers
├── registry.py            # reads Sync DocType Rule, returns adapter for a doctype
├── transport.py           # HTTP client + auth + retries
├── conflict.py            # resolve(local, incoming, rule) → winner
├── adapters/
│   ├── base.py            # BaseSyncAdapter (abstract)
│   ├── item.py
│   ├── item_price.py
│   ├── customer.py        # mobile-dedup logic
│   ├── pos_profile.py
│   ├── warehouse.py
│   ├── user.py
│   ├── sales_invoice.py   # validates naming series/origin_branch
│   ├── payment_entry.py
│   ├── pos_opening_shift.py  # priority=10, synced-first
│   ├── pos_closing_shift.py
│   ├── stock_ledger_entry.py
│   └── ...
└── api/
    ├── ingest.py          # central: POST endpoint for branch pushes
    ├── changes.py         # central: GET changes_since(doctype, watermark)
    ├── failover_txns.py   # central: GET failover_transactions_for_branch
    ├── metadata.py        # central: GET metadata_summary (uuid-only integrity check)
    ├── health.py          # central: GET health + server time; branch: GET reconciliation_status
    ├── confirm.py         # branch: POST confirm_sync_uuid (POS client dedup dropper)
    └── client_report.py   # branch: POST inventory (periodic uuid list) + storage_loss_event
```

### 6.2 BaseSyncAdapter interface

```python
class BaseSyncAdapter:
    doctype: str

    def serialize(self, doc) -> dict:
        """Build the sync payload. Default: doc.as_dict() including children."""

    def apply_incoming(self, payload: dict, operation: str) -> str:
        """Create/update/delete the local record. Returns local name."""

    def conflict_key(self, payload: dict) -> tuple:
        """What identifies this record across sites. Default: ('name',)."""

    def validate_incoming(self, payload: dict) -> None:
        """Raise if payload is invalid (e.g., naming series mismatch)."""

    def pre_apply_transform(self, payload: dict) -> dict:
        """Adapter hook for payload rewrites (strip server-only fields, etc.)."""
```

**The engine never special-cases a DocType.** All per-entity knowledge lives in the adapter. Engine iterates the registry, dispatches.

### 6.3 Adapter discovery

`registry.py` exposes `get_adapter(doctype) -> BaseSyncAdapter`. Adapters register themselves at import time via a decorator or module-level dict. Adding a new synced DocType = write adapter + register + add Sync DocType Rule row.

### 6.4 Two worked examples

**Customer adapter — mobile de-dup (§8):**

```python
class CustomerSyncAdapter(BaseSyncAdapter):
    doctype = "Customer"

    def conflict_key(self, payload):
        return ("mobile_no",)

    def apply_incoming(self, payload, operation):
        existing = frappe.db.get_value(
            "Customer",
            {"mobile_no": payload["mobile_no"]},
            "name",
        )
        if existing and existing != payload["name"]:
            # Canonical record exists locally under a different name;
            # caller is responsible for re-pointing any invoices.
            return existing
        return super().apply_incoming(payload, operation)
```

**Sales Invoice adapter — naming series validation (§8):**

```python
class SalesInvoiceSyncAdapter(BaseSyncAdapter):
    doctype = "Sales Invoice"

    def validate_incoming(self, payload):
        expected_branch = payload["origin_branch"]
        naming_series = payload["naming_series"]
        if expected_branch not in naming_series:
            raise ValidationError(
                f"Invoice {payload['name']}: naming series "
                f"{naming_series} does not encode origin branch {expected_branch}"
            )
```

### 6.5 Scheduler

```python
# pos_next/hooks.py
scheduler_events = {
    "cron": {
        "* * * * *": [
            "pos_next.sync.outbox.drain_if_due",
            "pos_next.sync.masters_puller.pull_if_due",
            "pos_next.sync.failover_puller.pull_if_due",
        ]
    }
}
```

Jobs self-throttle by comparing `now() - last_*_at` against the configured interval. Interval changes in Sync Site Config take effect on the next tick without redeploy.

---

## 7. Identity and naming

### 7.1 Master data: identical naming across sites

All masters (Item, Customer, POS Profile, Warehouse, User, …) have **identical `name`** on branch and central. Central is the naming authority; branches apply names exactly as received.

### 7.2 Transactions: branch-coded naming series

Transaction DocTypes (Sales Invoice, Payment Entry, POS Opening Shift, POS Closing Shift, Stock Ledger Entry, …) use **naming series that encode the origin branch code**:

- Cairo Downtown → `SINV-CAI-.#####`
- Alex Port → `SINV-ALX-.#####`

The naming series is configured on the POS Profile (a master), so it is identical on both sites. When central writes failover invoices, it uses the same series the branch's POS Profile specifies — no renaming needed on branch recovery.

### 7.3 `sync_uuid` as the cross-site dedup key

Every record in a **synced transaction DocType** carries a `sync_uuid` custom field set at creation by whichever side originates the record:

- Branch-created → branch generates the UUID.
- Central-failover-created → central generates the UUID.
- POS-client IndexedDB → client generates the UUID.

Dedup check on apply:

```python
if frappe.db.exists(doctype, {"sync_uuid": payload["sync_uuid"]}):
    return  # already present via another path
```

This makes every sync operation idempotent. A record can arrive at branch via pull_failover, via IndexedDB flush, or via a POS client re-push — the first wins, others are no-ops.

### 7.4 Custom fields added

On `Sales Invoice`, `Payment Entry`, `Stock Ledger Entry`, `POS Opening Shift`, `POS Closing Shift`, `Customer`:

- `sync_uuid` — Data, unique indexed, set at creation.
- `origin_branch` — Data, never mutated after creation (the `branch_code` of the site that created it).
- `synced_from_failover` — Check, set only on central when it writes as proxy for a branch.

A one-time backfill patch populates `sync_uuid` on existing rows (idempotent: fills only where NULL).

---

## 8. Synced DocTypes registry (seeded defaults)

Populated into `Sync DocType Rule` on install. Ops can add/remove rows later.

| DocType | Direction | CDC | Conflict Rule | Priority |
|---------|-----------|-----|---------------|----------|
| Item | Central→Branch | Watermark | Central-Wins | 100 |
| Item Price | Central→Branch | Watermark | Central-Wins | 110 |
| Item Group | Central→Branch | Watermark | Central-Wins | 100 |
| Item Barcode | Central→Branch | Watermark | Central-Wins | 100 |
| UOM, UOM Conversion Detail | Central→Branch | Watermark | Central-Wins | 100 |
| Price List | Central→Branch | Watermark | Central-Wins | 100 |
| POS Profile | Central→Branch | Watermark | Central-Wins | 90 |
| POS Settings | Central→Branch | Watermark | Central-Wins | 90 |
| POS Barcode Rules | Central→Branch | Watermark | Central-Wins | 90 |
| POS Offer / POS Coupon | Central→Branch | Watermark | Central-Wins | 120 |
| Loyalty Program | Central→Branch | Watermark | Central-Wins | 120 |
| Warehouse | Central→Branch | Watermark | Central-Wins | 90 |
| Branch | Central→Branch | Watermark | Central-Wins | 90 |
| Company, Currency, Exchange Rate | Central→Branch | Watermark | Central-Wins | 80 |
| Tax Templates, Item Tax Template | Central→Branch | Watermark | Central-Wins | 110 |
| Mode of Payment, MOP Account | Central→Branch | Watermark | Central-Wins | 110 |
| User, Role Profile | Central→Branch | Watermark | Central-Wins | 80 |
| Employee, Sales Person | Central→Branch | Watermark | Central-Wins | 110 |
| Customer Group | Central→Branch | Watermark | Central-Wins | 110 |
| Customer | Bidirectional | Outbox | Field-Level-LWW (key: mobile_no) | 50 |
| POS Opening Shift | Branch→Central | Outbox | Branch-Wins | 10 |
| POS Closing Shift | Branch→Central | Outbox | Branch-Wins | 20 |
| Sales Invoice | Branch→Central | Outbox | Branch-Wins | 50 |
| Payment Entry | Branch→Central | Outbox | Branch-Wins | 50 |
| Stock Ledger Entry | Branch→Central | Outbox | Branch-Wins | 60 |
| Offline Invoice Sync | Branch→Central | Outbox | Branch-Wins | 70 |
| Wallet, Wallet Transaction | Bidirectional | Outbox | Field-Level-LWW | 60 |

Low priority number = synced earlier. POS Opening Shift (10) is synced-first so central has the shift record before failover invoices reference it.

---

## 9. Conflict resolution

### 9.1 Resolution strategies

| Rule | Behavior |
|------|----------|
| Last-Write-Wins | Compare `modified`; newest wins; ties go to incoming. |
| Central-Wins | Incoming from central always wins. Incoming from branch accepted only if no local edit since last sync. |
| Branch-Wins | Incoming from branch always wins. |
| Field-Level-LWW | Per-field `modified` tracking; each field takes the newer value independently. |
| Manual | Both versions stored; Sync Conflict record created; neither applied until human resolves. |

### 9.2 Detection

On incoming apply, engine:

1. Loads local version (by `conflict_key()`).
2. Computes hash of local payload vs. incoming.
3. Hashes match → no-op.
4. Local absent → insert.
5. Local present, hashes differ → consult `Sync Record State.last_synced_hash`:
   - Local hash == `last_synced_hash` → local untouched since last sync, apply incoming directly.
   - Local hash != `last_synced_hash` → true conflict; resolve per entity's `conflict_rule`.

```
DocType: Sync Record State
reference_doctype  Link
reference_name     Data
last_synced_hash   Data         SHA256 of last-synced payload
last_synced_at     Datetime
last_synced_from   Data         "central" | branch_code
Unique: (reference_doctype, reference_name)
```

### 9.3 Manual resolution

```
DocType: Sync Conflict
reference_doctype   Link
reference_name      Data
local_payload       Long Text   JSON snapshot
incoming_payload    Long Text   JSON snapshot
incoming_from       Data
detected_at         Datetime
status              Select      "pending" | "resolved_local" | "resolved_incoming" | "resolved_merged"
resolved_by         Link → User
resolution_notes    Text
```

A resolver form shows a field-level diff and lets operators pick a winner or edit the merged record.

### 9.4 Field-Level-LWW implementation

Requires per-field timestamps. Stored as a child table `Sync Field Timestamp` keyed off (`reference_doctype`, `reference_name`, `fieldname`). Written whenever a field changes locally. Engine's field-level merge picks the newer timestamp per field.

This has storage overhead (N fields × M records × 2 rows). Applied only where `conflict_rule = Field-Level-LWW` (Customer, Wallet).

---

## 10. POS client failover to central

### 10.1 Failover decision

POS client's API wrapper tries backends in order, per request (not sticky):

```
1. Branch (current origin)  — timeout 500ms
2. Central (central_api_url) — timeout 1000ms
3. IndexedDB offline queue (existing behavior)
```

### 10.2 Client behavior — write to IndexedDB first, always

**Invariant:** every record the POS client creates exists in IndexedDB the instant the client generates it. Backend writes are layered on top.

```
POS creates invoice (with sync_uuid)
    │
    ├──▶ Write to IndexedDB first (local source of truth)
    │
    └──▶ Attempt backend write (branch → central → give up)
            │
            ▼
       update IndexedDB row with ack + backend identifier
```

IndexedDB record states:

- `queued` — created locally, no backend write attempted yet.
- `sent_to_branch` — branch ack'd.
- `sent_to_central` — central ack'd (failover path).
- `confirmed_at_branch` — branch confirmed it has the record; safe to drop.
- `failed` — exhausted retries; needs ops attention.

**Dropping records from IndexedDB:** only when branch explicitly confirms via the `confirm_sync_uuid` endpoint. Central-ack alone is NOT enough — the client must know branch has the record before discarding.

### 10.3 Central-side failover endpoint behavior

When a POS client POSTs a write request (invoice submit, payment, etc.) to central:

1. Identify origin branch from the POS Profile in the payload.
2. Write as the branch's sync user, with `origin_branch=<code>`, `synced_from_failover=1`.
3. Use the branch's naming series (carried by POS Profile → same on both sides).
4. Stock availability: check `block_on_failover_stock_unknown` on the POS Profile:
   - `true` and central's stock view is stale → reject with clear error.
   - `false` → allow, proceed.
5. Write SLE to the branch's warehouse (as proxy), tagged `synced_from_failover=1`.
6. Link to the POS Opening Shift (central already has it — shifts are priority-10 synced-first).

### 10.4 Branch recovery — three-source reconciliation

When branch comes back up, its `pull_failover` cron pulls records central wrote as proxy:

```
GET {central_url}/api/method/pos_next.sync.api.failover_txns.get_failover_transactions
    ?branch_code=CAI&since=<last_pull_failover_at>
```

Response grouped by DocType in dependency order:

1. Customer (new walk-ins created during failover)
2. POS Opening Shift updates (if any)
3. Sales Invoice + children
4. Payment Entry
5. Stock Ledger Entry
6. POS Closing Shift (if closed during failover)

Branch applies each via adapter. Idempotency via `sync_uuid`.

### 10.5 Reconciliation-gated IndexedDB flush

**Rule:** POS clients may NOT flush historical IndexedDB records to branch until branch is **provably fully reconciled with central** for branch-originated records. Otherwise branch could receive a record via IndexedDB that central doesn't have yet — violating "central is the aggregate."

Branch exposes:

```
GET /api/method/pos_next.sync.api.health.reconciliation_status
→ {
    "branch_code": "CAI",
    "reconciled_with_central": true|false,
    "pending_failover_pulls": 0,
    "last_reconciled_at": "...",
    "last_central_check_at": "..."
}
```

Branch computes `reconciled_with_central` on each pull_failover cycle by asking central for its metadata_summary (uuid-only) for `origin_branch=CAI` and comparing to local. Empty diff → reconciled.

POS client checks this flag before flushing; if false, client holds IndexedDB records passively. New invoices still flow normally to branch when branch is up.

### 10.6 Metadata integrity check

```
GET {central_url}/api/method/pos_next.sync.api.metadata.metadata_summary
    ?branch_code=CAI&opening_shift=POS-OPE-CAI-00042
→ [{"doctype": "Sales Invoice", "name": "SINV-CAI-...", "sync_uuid": "..."}, ...]
```

Returns uuid-only metadata for lightweight cross-checking without full payloads.

### 10.7 Close-shift guard (three-source agreement)

```python
def can_close_shift(opening_shift):
    central_uuids = fetch_central_metadata_summary(opening_shift.name)
    client_uuids  = fetch_pending_indexeddb_uuids_for_shift(opening_shift.name)
    local_uuids   = frappe.get_all(..., pluck="sync_uuid")

    expected = set(central_uuids) | set(client_uuids)
    missing  = expected - set(local_uuids)

    if missing:
        raise ValidationError(
            f"Cannot close: {len(missing)} failover invoices still missing. "
            f"Retry in a minute."
        )
    if pending_indexeddb_flushes_for_shift(opening_shift):
        raise ValidationError("Cannot close: POS clients still flushing offline queue.")
    return branch_side_reconciliation(opening_shift)
```

### 10.8 Client-side protections against IndexedDB loss

| Protection | Prevents | UX |
|------------|----------|------|
| Block incognito/private mode | Tab-close wipe | Blocking screen on POS boot |
| `navigator.storage.persist()` | Quota eviction | Silent on success; warn on fail |
| Failover banner | Accidental clear | Persistent header banner when IndexedDB has unconfirmed rows |
| `beforeunload` guard | Accidental tab close | Native browser confirmation dialog |
| Health indicator | Awareness | Header widget with backend + IndexedDB state |
| Size-drop detector | Detect loss after fact | Compare current vs. `posnext_idb_size` in localStorage on boot; alert on large drop |
| Periodic inventory ping (60s during failover) | Server-side visibility | Background POST; no user UI |

Failover banner example:

```
┌──────────────────────────────────────────────────────┐
│ ⚠ FAILOVER MODE — DO NOT CLOSE THIS TAB              │
│ Branch ERPNext offline. 23 invoices held locally.    │
│ Status: writing to central | IndexedDB: 23 pending   │
└──────────────────────────────────────────────────────┘
```

---

## 11. Observability

### 11.1 Sync Status dashboard

New Frappe page at `/app/sync-status`:

- Outbox depth (pending / failed / dead).
- Last push_outbox, pull_masters, pull_failover timestamps.
- `reconciled_with_central` flag.
- Active POS client count + total IndexedDB pending across clients.
- Recent Sync Log errors (last 10).
- Conflict Queue count.

### 11.2 Supporting DocTypes

- `Sync Log` — append-only, one row per sync operation (push/pull) with status, duration, records touched, error.
- `Sync Conflict` — manual-resolution queue (§9.3).
- `Sync Dead Letter` — outbox rows that exceeded max retries, awaiting ops.
- `Sync History` — archived acknowledged outbox rows (§5.3).

### 11.3 Alerts

| Condition | Severity |
|-----------|----------|
| Outbox depth > 1000 for > 10 min | Warning |
| Outbox depth > 10000 | Critical |
| Last push older than 5 × push_interval_seconds | Warning |
| Last push older than 30 min | Critical |
| Any Sync Dead Letter row | Warning |
| New Sync Conflict row | Warning (notify conflict-resolver role) |
| Branch reports reconciled_with_central=false for > 30 min post-failover | Critical |
| POS client reports suspicious_storage_loss event | Critical |

Recipients configured in Sync Site Config (Link to User or Role).

---

## 12. Security

- **Transport:** HTTPS only. `central_url` with scheme other than `https` rejected at save.
- **Authentication:** Session login (username + password) using a real Frappe User per branch; `sync_password` stored as Frappe Password fieldtype (at-rest encrypted via site key).
- **Authorization:** Dedicated role `POS Next Sync Agent`, granted only read/write on registry-listed DocTypes. A Permission Query Condition restricts the sync user to records where `origin_branch = <this user's branch_code>` on branch-scoped DocTypes — prevents a compromised branch from writing records tagged as another branch's.
- **Replay protection:** Ingest endpoint rejects payloads whose `created_at` is older than 24 hours (configurable) or whose `sync_uuid` has already been processed.
- **Audit:** Sync Log is append-only; `owner` is always the sync user.
- **Secret handling:** `sync_password` never appears in logs, API responses, or error messages. Rotation = update Sync Site Config; takes effect on next worker cycle (re-login).

---

## 13. Testing strategy

### 13.1 Unit tests (per adapter)

Each `BaseSyncAdapter` subclass has test cases for `serialize`, `apply_incoming`, `conflict_key`, `validate_incoming`, `pre_apply_transform`, using mocked Frappe ORM. Fast, isolated.

### 13.2 Integration tests (per sync flow)

Dual-site fixture: two Frappe sites on the same bench (`branch.test` + `central.test`), real HTTP between them. Test suites cover push-transactions, pull-masters, pull-failover independently.

### 13.3 End-to-end scenario tests

1. **Happy path:** branch creates invoice → push → central has it with correct sync_uuid, origin_branch.
2. **Master update:** central updates Item Price → pull on branch → branch has it; no conflict.
3. **Conflict — Field-Level-LWW:** both sides edit Customer different fields → merged record has both edits.
4. **Conflict — Central-Wins:** both sides edit Item Price → central wins; branch's change appears in Sync Conflict only if configured.
5. **Failover write:** POS writes to central → branch pulls → branch has it → sync_uuid matches.
6. **Three-source recovery:** POS wrote to central AND stored in IndexedDB → branch recovers → pull_failover → client flushes → all sync_uuids present exactly once on branch.
7. **Close-shift guard:** missing failover records → close refused; complete → close succeeds.
8. **Outbox back-pressure:** 5000 outbox rows + compaction → drain completes, no duplicates.
9. **Reconciliation gate:** branch not yet reconciled → client refuses to flush IndexedDB.
10. **IndexedDB loss detection:** simulate storage clear → size-drop alert fires → report reaches central.

### 13.4 Test environment

Bench script stands up `branch.test` + `central.test` sites; seed fixtures install reciprocal Sync Site Config on both. A single `bench run-sync-tests` entry point runs all suites.

### 13.5 Load/soak (post-MVP)

- 10k outbox rows × hourly push cycles for 24h.
- 50 concurrent POS clients during simulated failover.

---

## 14. Install & rollout

### 14.1 Install tasks

1. Create DocTypes: Sync Site Config, Sync DocType Rule, Sync Outbox, Sync Watermark, Sync Tombstone, Sync Record State, Sync Field Timestamp, Sync Conflict, Sync Log, Sync Dead Letter, Sync History.
2. Seed default `synced_doctypes` rules.
3. Add custom fields: `sync_uuid`, `origin_branch`, `synced_from_failover` on target DocTypes.
4. Backfill `sync_uuid` on existing transaction rows (idempotent patch).
5. Create role `POS Next Sync Agent` with seeded permissions + permission query conditions.
6. Register scheduled jobs in hooks.py.

### 14.2 First-run UX

1. System Manager opens Sync Site Config.
2. Selects `site_role` (Branch or Central).
3. Fills central URL + sync user + sync password (branch) OR fills registered branches (central).
4. Clicks **"Test Sync Connection"** — sync worker calls `health` endpoint immediately and shows result.
5. Saves. Sync workers begin at next cron tick.

---

## 15. Dev Environment Topology

### 15.1 Two-bench setup

Development and integration testing uses two separate Frappe benches on the same machine, each on its own port:

```
┌─────────────────────────────────────────┐     ┌─────────────────────────────────────────┐
│  frappe-bench (port 8000)               │     │  frappe-bench-16 (port 8001)            │
│  Frappe v15 · Python 3.10               │     │  Frappe v16+ · Python 3.14              │
│                                         │     │                                         │
│  Site: pos-central                      │     │  Site: dev.pos                           │
│  Role: CENTRAL                          │     │  Role: BRANCH                            │
│  ERPNext: v15                           │     │  ERPNext: v16                             │
│  pos_next: feat/sync-foundation         │     │  pos_next: feat/sync-foundation           │
│                                         │     │                                         │
│  Sync Site Config:                      │     │  Sync Site Config:                       │
│    site_role = Central                  │     │    site_role = Branch                     │
│    branch_code = CAI                    │     │    branch_code = CAI                      │
│    registered_branch_url =              │     │    central_url = http://localhost:8000     │
│      http://localhost:8001              │     │    sync_username = Administrator           │
└─────────────────────────────────────────┘     └─────────────────────────────────────────┘
              ▲                                                │
              │          HTTP (localhost, different ports)      │
              └────────────────────────────────────────────────┘
```

**Why two benches, not two sites on one bench:** Different Frappe/ERPNext major versions (v15 vs v16) cannot coexist on a single bench. Two benches also give us separate Redis, separate workers, and separate ports — closer to production topology.

**No Host header routing needed:** Each bench binds a different port (`webserver_port` in `common_site_config.json`), so `http://localhost:8000` always resolves to frappe-bench and `http://localhost:8001` to frappe-bench-16.

**`POS_NEXT_SYNC_ALLOW_HTTP=1`:** Required in dev since transport is `http://localhost`. This env var bypasses the HTTPS enforcement on `central_url` in Sync Site Config validation. Never set in production.

### 15.2 Version-agnostic sync protocol

The sync HTTP API is a **stable contract** independent of Frappe/ERPNext version. The same pos_next codebase runs on both v15 and v16.

**Design principles:**

- **Single codebase:** pos_next already handles v15/v16 differences at runtime (e.g., `fix: support ERPNext v15/v16 change amount GL entry method`). The sync module follows the same pattern — no version-specific forks.
- **pos_next-owned endpoints:** All sync API lives under `pos_next.sync.api.*`, not Frappe's generic `/api/resource/`. This isolates the protocol from Frappe ORM version differences.
- **Explicit payload schema:** Adapters serialize using explicit field lists defined by pos_next, not Frappe's `as_dict()`. Internal/version-specific fields are stripped.
- **Runtime version detection:** Where Frappe/ERPNext field names or behaviors differ between versions, pos_next detects the running version at runtime and adapts (e.g., `hasattr(doc, 'field_v16') or doc.field_v15`).

This means a v15 central can sync with a v16 branch and vice versa — branches in the field may upgrade at different times.

### 15.3 Bootstrap procedure

To set up a new branch site for sync testing:

```bash
# 1. Ensure the bench has Frappe + ERPNext + pos_next installed
#    pos_next must be on the feat/sync-foundation branch (or later)

# 2. Run migrate to create Sync DocTypes
bench --site <site> migrate

# 3. Configure as branch (pointing at central)
POS_NEXT_SYNC_ALLOW_HTTP=1 bench --site <site> execute \
  pos_next.sync.tests._setup_multi_site.setup_as_branch

# 4. Configure central to know about this branch
POS_NEXT_SYNC_ALLOW_HTTP=1 bench --site <central-site> execute \
  pos_next.sync.tests._setup_multi_site.setup_as_central
```

Helper functions in `pos_next/sync/tests/_setup_multi_site.py`:
- `setup_as_branch()` — creates Branch Sync Site Config pointing at `http://localhost:8000`
- `setup_as_central()` — creates Central Sync Site Config registering branch at `http://localhost:8001`
- `show_current()` — prints current Sync Site Config state
- `cleanup()` — removes all Sync Site Config rows

### 15.4 Running both benches

```bash
# Terminal 1 — Central (port 8000)
cd /home/ubuntu/frappe-bench && bench start

# Terminal 2 — Branch (port 8001)
cd /home/ubuntu/frappe-bench-16 && bench start
```

Both must be running for cross-site sync operations.

---

## 16. Open items for sub-specs

These are intentionally left to per-entity sub-specs:

- **Masters sub-spec:** exact fields serialized per master, handling of child tables (e.g. Item Barcodes, POS Profile payments), tombstone semantics per entity.
- **Stock sub-spec:** exact SLE payload shape, failover-SLE reconciliation rules, Material Transfer handling.
- **Transactions sub-spec:** Sales Invoice child table handling, Payment Entry references, POS Opening/Closing Shift details.
- **Conflict reconciliation sub-spec:** Sync Conflict resolver UI, manual-merge UX, bulk-resolve tooling.

---

## 17. Glossary

- **Branch:** a branch ERPNext site (on-prem, behind consumer internet).
- **Central:** the cloud ERPNext site; authoritative for masters, aggregate for transactions.
- **Failover:** POS Vue client bypassing its branch and writing directly to central.
- **Failover pull:** branch retrieving its own records from central post-recovery.
- **Outbox:** table of pending change events at the source site.
- **Watermark:** the per-DocType `last_modified` marker for pull cycles.
- **Tombstone:** record of a delete that pulled-from sites need to replay.
- **sync_uuid:** globally unique identifier for a synced transaction record; generated at creation.
- **origin_branch:** the `branch_code` of the site that originated the record.
- **Reconciled with central:** branch's local view of its own records equals central's view (by uuid set).
- **Sync user:** dedicated real Frappe User whose credentials machine-to-machine sync uses.
