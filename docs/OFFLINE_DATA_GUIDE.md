# Offline Data & Durability Guide

This guide describes the offline **data subsystem** in POS Next: what gets
cached, where it lives, how it gets there, and the durability layers that
keep queued POS data alive across browser wipes and storage-pressure
eviction.

It is the companion to [OFFLINE_SYNC.md](OFFLINE_SYNC.md), which covers
the queue **sync flow** (offline_id, deduplication, retry). Read that
one for "how does an invoice make it from the queue to the server."
This one covers "what data is available to the cashier when the network
is down, and what protects it from loss."

---

## TL;DR

```
                          ┌──────────────────────────────────────┐
   In-memory caches       │  Vue / Pinia stores                  │
   (volatile)             │  (posCart, itemSearch, …)            │
                          └────────────┬─────────────────────────┘
                                       │
                          ┌────────────▼─────────────────────────┐
   Offline cache          │  IndexedDB (Dexie, db.js)            │
   (per-browser)          │  17 tables: items, customers, taxes, │
                          │  uoms, brands, item_groups,          │
                          │  loyalty_programs, item_prices,      │
                          │  payment_methods, sales_persons,     │
                          │  offers, invoice_history,            │
                          │  unpaid_invoices, translations,      │
                          │  + queues: invoice_queue,            │
                          │  payment_queue, customer_queue,      │
                          │  drafts, settings                    │
                          └────────────┬─────────────────────────┘
                                       │
       ┌───────────────────────────────┼─────────────────────────┐
       ▼                               ▼                         ▼
 ┌──────────────┐             ┌─────────────────┐         ┌─────────────┐
 │ navigator.   │             │ Service Worker  │         │ QZ Tray     │
 │ storage.     │             │ (Workbox)       │         │ file.write  │
 │ persist()    │             │ image cache,    │         │ on-disk     │
 │ "don't evict"│             │ /api SWR/NF     │         │ mirror      │
 └──────────────┘             └─────────────────┘         └─────────────┘
   Layer 1                       Layer 2                    Layer 3
   (browser hint)               (asset cache)              (truly durable)
```

The cashier's terminal keeps **three independent copies** of every queued
invoice:

1. The IndexedDB row (always — written first, source of truth)
2. The browser's persistent-storage flag prevents auto-eviction
3. A real `.json` file on disk via QZ Tray (best-effort)

That last layer is the one that survives "Clear site data," browser
reinstall, or profile wipe.

---

## What's cached for offline read

| Domain          | Table              | Source endpoint                                | Notes                                       |
| --------------- | ------------------ | ---------------------------------------------- | ------------------------------------------- |
| Items           | `items`            | `pos_next.api.items.get_items_bulk`            | Includes `attributes`, `item_uoms`, `uom_prices`, `barcodes`. Variants captured when `include_variants=1` (default for offline cache). |
| Item prices     | `item_prices`      | (embedded in items bulk + price-list rows)     | Per-UOM prices.                             |
| Customers       | `customers`        | `pos_next.api.customers.get_customers_for_offline` | **Enriched**: addresses, loyalty_points, wallet_balance. Falls back to `get_customers` on older deploys. |
| Taxes           | `taxes`            | `pos_next.api.offline_data.get_taxes`          | Sales Taxes & Charges Templates with full child rows. Indexed by `pos_profile`. |
| UOMs            | `uoms`             | `pos_next.api.offline_data.get_uoms`           | Global list.                                |
| Item groups     | `item_groups`      | `pos_next.api.items.get_item_groups`           | Used by filter dropdowns.                   |
| Brands          | `brands`           | `pos_next.api.items.get_brands`                | Used by filter dropdowns.                   |
| Loyalty rules   | `loyalty_programs` | `pos_next.api.offline_data.get_loyalty_programs` | Includes collection rules (tier × factor). |
| Payment methods | `payment_methods`  | `pos_next.api.pos_profile.get_payment_methods` | Tagged by `pos_profile`.                    |
| Sales persons   | `sales_persons`    | `pos_next.api.pos_profile.get_sales_persons`   | Tagged by `pos_profile`.                    |
| Offers          | `offers`           | (offers store)                                 | Indexed by `pos_profile`, `apply_on`, `valid_upto`. |
| Invoice history | `invoice_history`  | `pos_next.api.invoices.get_invoices`           | Last 100 invoices by default.               |
| Unpaid invoices | `unpaid_invoices`  | `pos_next.api.partial_payments.get_unpaid_invoices` | For partial-payment flows.            |
| Stock           | `stock`            | (stock sync worker, periodic)                  | `[item_code+warehouse]` compound key.       |
| Translations    | `translations`     | `pos_next.api.localization.get_app_translations` | Per-locale, 24h TTL.                      |

Reference data (taxes/UOMs/loyalty) can be fetched in **one round-trip**
via `pos_next.api.offline_data.get_offline_bundle`, which returns all
three. The frontend wrapper `cacheOfflineBundleFromServer()` falls back
to per-endpoint calls if the bundle endpoint isn't deployed.

### Item images

Item images are pre-downloaded by [`imagePrefetch.js`](../POS/src/utils/offline/imagePrefetch.js)
once the item cache is seeded. The fetches go through the Workbox SW,
which stores them in the `product-images-cache` (`StaleWhileRevalidate`,
7-day max age, 200 entry cap). The prefetcher is:

- **Throttled** (default 6 concurrent fetches)
- **Resumable** (last completed offset stored in `settings.image_prefetch_offset`)
- **Cancellable** (call `cancelImagePrefetch()`)
- **Best-effort** — failures don't abort the run

Triggered automatically from `posSync.preloadDataForOffline()` after
items are cached. Manual restart via `prefetchItemImages()` from
`@/utils/offline`.

---

## Offline write queues

Two queues store work-in-progress that needs to reach the server when
connectivity returns.

### Invoice queue (`invoice_queue`)

Schema: `++id, &offline_id, timestamp, synced`

- Written by `saveOfflineInvoice()` ([sync.js](../POS/src/utils/offline/sync.js))
- Each row carries `data` (the full invoice payload), `offline_id`
  (UUID for server-side dedup), `timestamp`, `synced`, `retry_count`,
  `stock_delta`, `stock_reverted`.
- See [OFFLINE_SYNC.md](OFFLINE_SYNC.md) for the full sync state machine.

#### Optimistic stock + rollback

When an offline invoice is queued, every item's quantity is **subtracted
from local stock** so the next "available stock" display is correct.
The decrement is recorded on the queue row as `stock_delta`:

```javascript
{ stock_delta: [{ item_code: "BOX-A", warehouse: "WH-Main", qty: 3 }] }
```

If the invoice fails to sync after `MAX_RETRY_COUNT` attempts, OR is
manually deleted while still unsynced, `revertLocalStockForInvoice()`
adds the quantities back. This prevents "phantom missing stock" — the
appearance that 3 units were sold when the invoice was actually voided.

The revert is idempotent (gated by `stock_reverted: true`).

### Customer queue (`customer_queue`)

Schema: `++id, &offline_id, timestamp, synced`

Used when a cashier creates a new customer offline.
[customerQueue.js](../POS/src/utils/offline/customerQueue.js):

1. **`enqueueOfflineCustomer(payload)`**
   - Generates `offline_id`
   - Writes the queue row
   - Inserts a **placeholder** customer row in the `customers` table with
     `name = "OFFLINE-XXXXXXXX"` and `placeholder: true` so the cashier
     can pick the new customer in the same session.

2. **`syncOfflineCustomers()`** (called from `posSync.syncPending` BEFORE
   invoice sync, so an invoice referencing a placeholder can resolve to
   the real name):
   - Calls `pos_next.api.customers.replay_offline_customer` with the
     `offline_id`.
   - The endpoint is **idempotent** on `offline_id` (uses the
     `pos_next_offline_id` Custom Field if present; falls back to
     `customer_name + mobile_no` fingerprint).
   - On success: drops the placeholder, inserts the real customer
     record, deletes the queue row, removes the disk mirror.
   - On failure: bumps `retry_count`, stores `last_error`, keeps the row
     for the next replay attempt.

---

## Durability stack

Three independent layers protect the queue rows.

### Layer 1 — `navigator.storage.persist()`

[persistence.js](../POS/src/utils/offline/persistence.js)

Asks the browser to mark this origin's storage as **persistent**, meaning
it won't be evicted under storage pressure. Granted automatically when:

- The site is "installed" as a PWA, or
- Notification permission is granted, or
- The browser determines high site engagement

Called once on app boot from `main.js` via `ensurePersistentStorage()`.
Idempotent and best-effort — no-op when the API isn't supported.

**Cost:** 5 lines of code, zero ongoing runtime cost.
**Limit:** Doesn't defend against a manual "Clear site data" or browser
reinstall — that's what Layer 3 is for.

### Layer 2 — Service Worker runtime caches

Configured in [vite.config.js](../POS/vite.config.js) under `runtimeCaching`.

| URL pattern                       | Strategy            | Cache name           | Notes                          |
| --------------------------------- | ------------------- | -------------------- | ------------------------------ |
| `fonts.googleapis.com`            | CacheFirst          | google-fonts-cache   | 1y, 10 entries                 |
| `fonts.gstatic.com`               | CacheFirst          | gstatic-fonts-cache  | 1y, 10 entries                 |
| `/assets/pos_next/pos/`           | CacheFirst          | pos-assets-cache     | 30d, 500 entries               |
| `/files/.*\.(jpg|png|gif|webp|svg)` | StaleWhileRevalidate | product-images-cache | 7d, 200 entries (item images) |
| `/api/`                           | NetworkFirst (10s)  | api-cache            | 24h, 100 entries               |
| `/pos` pages                      | NetworkFirst (3s)   | pos-page-cache       | navigation                     |

This protects **assets** and **opportunistic API responses**, not the
queue itself.

### Layer 3 — QZ-Tray on-disk mirror

[diskBackup.js](../POS/src/utils/offline/diskBackup.js)

The strongest layer. QZ Tray is already shipped on every cashier
terminal for printing — its `file.*` API can write straight to the host
filesystem through the JVM.

#### File layout

Files live in QZ's per-origin **sandbox folder**, so no certificate
elevation is required:

```
<QZ user data>/
  sandbox/
    <origin>/
      pos_next/
        invoices/
          <offline_id>.json    ← one file per queued invoice
          ...
        customers/
          <offline_id>.json    ← one file per queued customer
          ...
```

Each file is a JSON envelope:

```json
{
  "kind": "invoice" | "customer",
  "version": 1,
  "mirrored_at": 1714185600000,
  "row": { /* full queue row */ }
}
```

#### Lifecycle

| Trigger                                | Action                                         |
| -------------------------------------- | ---------------------------------------------- |
| Cashier saves offline invoice          | `mirrorOfflineInvoice` writes the file (async) |
| Cashier creates customer offline       | `mirrorOfflineCustomer` writes the file        |
| Server confirms invoice synced         | `removeMirroredInvoice` deletes the file       |
| Customer queue replayed                | `removeMirroredCustomer` deletes the file      |
| Cashier deletes unsynced invoice       | `removeMirroredInvoice` deletes the file       |
| App boots after a "Clear site data"    | `restoreFromDisk` re-inserts every missing row |

Every operation is wrapped in try/catch. If QZ isn't running, all calls
become no-ops — IndexedDB remains the source of truth.

#### Restore semantics

`restoreFromDisk()` is idempotent:

- Iterates every file under `pos_next/invoices/` and `pos_next/customers/`
- Looks up each `offline_id` in IndexedDB
- Inserts the row only if missing
- Marks the inserted row with `restored_from_disk_at: <timestamp>` for
  audit visibility

Returns:

```javascript
{
  ran: boolean,                  // false when QZ isn't connected
  invoicesRestored: number,
  customersRestored: number,
  invoicesSkipped: number,        // already in IndexedDB
  customersSkipped: number,
  errors: string[]
}
```

#### Triggers

- **Automatic** — fires once 5 seconds after app boot from `main.js`
  (delay gives QZ time to auto-connect from the print path).
- **Manual** — a "Restore from Disk" button in the offline-invoices
  dialog. Useful after deliberately clearing site data, or during
  support recovery.

#### Security

Filenames are sanitized: any non-`[a-zA-Z0-9._-]` is replaced with `_`,
and `..` sequences are collapsed. A crafted `offline_id` cannot escape
the QZ sandbox.

#### When QZ isn't available

- `mirrorOfflineInvoice` returns `{ mirrored: false, reason: "qz_unavailable" }`
- `restoreFromDisk` returns `{ ran: false, ... }`
- `isMirrorAvailable()` returns `false`

The cashier still has Layers 1 and 2.

---

## Backend endpoints reference

Every endpoint is a `@frappe.whitelist()` method.

### `pos_next.api.offline_data` (new)

| Method                 | Args                       | Returns                                       |
| ---------------------- | -------------------------- | --------------------------------------------- |
| `get_taxes`            | `pos_profile?`, `company?` | `[{name, title, company, is_default, taxes: [...]}, …]` |
| `get_uoms`             | —                          | `[{name, uom_name, must_be_whole_number}, …]` |
| `get_loyalty_programs` | `company?`                 | `[{name, ..., collection_rules: [...]}, …]`   |
| `get_offline_bundle`   | `pos_profile`, `company?`  | `{taxes, uoms, loyalty_programs}` (one round-trip) |

### `pos_next.api.customers` (extended)

| Method                         | Args                                              | Returns                                                                 |
| ------------------------------ | ------------------------------------------------- | ----------------------------------------------------------------------- |
| `get_customers_for_offline`    | `pos_profile?`, `modified_since?`, `limit?`       | Customer list enriched with `addresses[]`, `loyalty_points`, `wallet_balance`. |
| `get_customer_offline_extras`  | `customer`, `company?`                            | `{customer, addresses[], loyalty_points, wallet_balance}` for one row. |
| `replay_offline_customer`      | `offline_id`, `customer_name`, `mobile_no?`, `email_id?`, `customer_group?`, `territory?`, `company?`, `pos_profile?` | `{name, deduplicated, doc}`. Idempotent on `offline_id`.                |

The `replay_offline_customer` endpoint will use a `pos_next_offline_id`
Custom Field on the Customer DocType for strong idempotency if it
exists. Without that field, it falls back to `customer_name + mobile_no`
fingerprint matching. **Recommend adding the field via fixture for
production deployments.**

---

## Frontend module reference

All exposed via `@/utils/offline`:

```javascript
// Caches
import {
    cacheItemsFromServer, cacheCustomersFromServer,
    cacheTaxesFromServer, cacheUomsFromServer,
    cacheLoyaltyProgramsFromServer, cacheItemGroupsFromServer,
    cacheBrandsFromServer, cacheOfflineBundleFromServer,
    cachePaymentMethodsFromServer, cacheSalesPersonsFromServer,
    refreshCustomerExtrasFromServer,
} from "@/utils/offline"

// Reads
import {
    getCachedTaxes, getCachedUoms, getCachedLoyaltyPrograms,
    getCachedItemGroups, getCachedBrands,
    getCachedPaymentMethods, getCachedSalesPersons,
    getCacheStats,
} from "@/utils/offline"

// Customer queue
import {
    enqueueOfflineCustomer, getQueuedOfflineCustomers,
    syncOfflineCustomers,
} from "@/utils/offline"

// Image prefetch
import {
    prefetchItemImages, resetImagePrefetchProgress,
    cancelImagePrefetch,
} from "@/utils/offline"

// Durability layer 1 — browser persistence
import {
    requestPersistentStorage, ensurePersistentStorage,
    getPersistenceStatus,
} from "@/utils/offline"

// Durability layer 3 — QZ disk mirror
import {
    mirrorOfflineInvoice, mirrorOfflineCustomer,
    removeMirroredInvoice, removeMirroredCustomer,
    restoreFromDisk, backfillMirrorFromIndexedDB,
    isMirrorAvailable, enableDiskMirror, disableDiskMirror,
} from "@/utils/offline"
```

The disk-mirror functions are also called automatically from
`saveOfflineInvoice`, `enqueueOfflineCustomer`, the sync code paths, and
`main.js`. Direct usage is for the Restore UI and one-off operations.

---

## Bootstrap sequence

Order of operations on shift start (orchestrated by
[posSync.js](../POS/src/stores/posSync.js) `preloadDataForOffline`):

1. **Items + customers** — primary cache, blocks "ready" toast.
2. **Payment methods + sales persons** — `pos_profile`-tagged.
3. **Reference bundle** — taxes / UOMs / loyalty (one round-trip when
   the backend exposes `get_offline_bundle`, otherwise three).
4. **Item groups + brands** — for filter dropdowns.
5. **Invoice history + unpaid invoices** — for the queue UI.
6. **Item images** — background, throttled, doesn't block UX.

In parallel, on `main.js`:

- `ensurePersistentStorage()` — fire-and-forget Layer 1.
- `restoreFromDisk()` — runs 5 s after boot to pull any stranded queue
  rows back into IndexedDB.

---

## Recovery workflows

### "I cleared site data and lost a queued invoice"

1. Make sure QZ Tray is running on the terminal.
2. Open the offline-invoices dialog.
3. Click **Restore from Disk**.
4. Confirm the count in the toast.
5. Click **Sync All** if online.

If QZ Tray was never running on this terminal, the disk mirror was never
written — Layer 3 is unavailable. The invoice is lost from the cashier's
side; check the server-side `Offline Invoice Sync` DocType for
deduplication records (covered in [OFFLINE_SYNC.md](OFFLINE_SYNC.md)).

### "I'm migrating from a deploy without disk mirror"

Pre-existing queue rows weren't mirrored when they were first written.
To protect them retroactively:

```javascript
import { backfillMirrorFromIndexedDB } from "@/utils/offline"
await backfillMirrorFromIndexedDB()
// → { invoices: 12, customers: 3 }
```

Safe to run repeatedly — it just rewrites the files.

### "Stock numbers look wrong after a failed offline invoice"

Two cases:

1. **Sync failed permanently** (`retry_count >= MAX`): stock was
   automatically reverted by `handleSyncFailure`. Check the queue
   row's `stock_reverted: true` flag.
2. **Cashier deleted the unsynced invoice**: same path —
   `deleteOfflineInvoice` calls `revertLocalStockForInvoice`.

If neither flag is set and stock is still off, the bug is upstream —
investigate via `db.invoice_queue.toArray()` in the browser console.

---

## Testing

Two test suites cover the offline subsystem.

### Vitest (`POS/tests/offline/`)

39 unit tests across:

- **db-schema.test.js** — every new IndexedDB table exists, accepts rows,
  enforces unique offline_id.
- **customerQueue.test.js** — enqueue creates placeholder, replay
  removes it, dedup vs new tallied separately, retry_count bumps on
  failure.
- **cache-bootstrap.test.js** — taxes/UOMs/loyalty/groups/brands cache
  paths, bundle endpoint with per-endpoint fallback, customer fallback
  to legacy endpoint.
- **sync-stock-rollback.test.js** — `stock_delta` recorded, deleted
  unsynced invoice reverts stock, retry-cap reverts stock.
- **barcode-fallback.test.js** — offline-only path uses cache, server
  error falls through to cache, both-fail re-throws.
- **persistence.test.js** — supported / granted / refused / API-missing
  paths.
- **diskBackup.test.js** — write to sandbox path, sanitization, QZ
  unavailable returns false (never throws), restore re-inserts only
  missing rows, backfill writes every pending row.

```bash
cd POS && yarn test:run        # run all
cd POS && yarn test            # watch mode
cd POS && yarn test:coverage   # with coverage report
```

### Playwright (`POS/tests/playwright/`)

2 smoke tests against the live Vite dev server:

- **offline-modules harness** — real Chromium tab loading
  `db.js`/`customerQueue.js` through Vite's transform pipeline,
  exercising the schema + a customer-queue round-trip.
- **SPA mount smoke** — verifies the bundle parses and Vue mounts
  without uncaught JS exceptions (filters expected unauth API errors).

```bash
cd POS && yarn e2e             # auto-starts dev server
cd POS && yarn e2e:headed      # see the browser
cd POS && yarn e2e:install     # install the browser binary if missing
```

For tests that need a clean fake IndexedDB, the setup file
`POS/tests/setup.js` installs `fake-indexeddb` globally.

---

## File map

```
POS/src/utils/offline/
├── db.js                  # Dexie schema (17 tables, auto-versioned)
├── cache.js               # Server → cache wrappers (taxes, UOMs, …)
├── customerQueue.js       # Offline customer create + replay
├── diskBackup.js          # QZ-Tray on-disk mirror (Layer 3)
├── imagePrefetch.js       # Throttled item-image prefetch
├── items.js               # Item barcode helpers
├── offlineState.js        # Online/offline detection (multi-signal)
├── offlineReceiptCache.js # sessionStorage receipt payload cache
├── persistence.js         # navigator.storage.persist (Layer 1)
├── sync.js                # Invoice queue + replay
├── translationCache.js    # Per-locale translation cache
├── uuid.js                # generateOfflineId() (shared with worker)
├── workerClient.js        # Main-thread RPC to offline.worker.js
└── index.js               # Barrel exports

POS/src/workers/
└── offline.worker.js      # IndexedDB writes, search, stock sync

pos_next/api/
├── offline_data.py        # get_taxes / get_uoms / get_loyalty_programs / get_offline_bundle
├── customers.py           # + get_customers_for_offline / get_customer_offline_extras / replay_offline_customer
├── items.py               # get_items_bulk includes attributes + uoms when offline-caching
└── invoices.py            # submit_invoice + check_offline_invoice_synced (see OFFLINE_SYNC.md)

POS/tests/
├── setup.js               # fake-indexeddb, __() stub
├── offline/
│   ├── barcode-fallback.test.js
│   ├── cache-bootstrap.test.js
│   ├── customerQueue.test.js
│   ├── db-schema.test.js
│   ├── diskBackup.test.js
│   ├── persistence.test.js
│   └── sync-stock-rollback.test.js
└── playwright/
    └── offline-modules.spec.js
```

---

## See also

- [OFFLINE_SYNC.md](OFFLINE_SYNC.md) — invoice sync state machine and
  deduplication
- [STARTUP_SEQUENCE.md](STARTUP_SEQUENCE.md) — boot-time orchestration
- [PRICING_AND_SUBMISSION.md](PRICING_AND_SUBMISSION.md) — how cached
  taxes are applied during offline checkout
