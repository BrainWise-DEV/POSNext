# POSNext Desktop — Implementation Plan

## 1. Problem Statement

POSNext currently requires a Frappe/ERPNext server to operate. This creates issues for:

- Retail locations with unreliable internet connectivity
- Standalone POS terminals that need to function independently
- Businesses that need resilience against network/server outages
- IT teams that prefer distributing a simple .exe installer over managing web deployments

## 2. Solution Overview

Build an **Electron desktop application** that wraps the existing POSNext Vue 3 frontend with a **local Express.js API server** backed by **SQLite**, creating a fully offline POS that syncs bidirectionally with ERPNext when connectivity is available.

### Design Principles

1. **Zero frontend changes** — The Vue frontend must work without modifying any component, store, or composable
2. **API contract fidelity** — The local Express server must exactly replicate Frappe's HTTP API contract
3. **Offline-first** — Every POS operation must work without internet after initial data provisioning
4. **Safe sync** — Invoice deduplication, conflict resolution, and data integrity during sync
5. **Simple distribution** — Single .exe installer with auto-update capability

## 3. Reference Study: Store-POS

The [Store-POS](https://github.com/tngoman/Store-POS) project was studied as a reference for desktop POS packaging patterns:

### What We Learned

| Aspect | Store-POS Approach | Our Adaptation |
|--------|-------------------|----------------|
| Desktop framework | Electron | Same — Electron |
| Local database | NeDB (embedded NoSQL) | **SQLite** via `better-sqlite3` (better for 65K+ items, JOINs, FTS) |
| API server | Express.js on port 8001 | Same pattern — Express.js on port 18420 |
| Architecture | Server + jQuery frontend | Local Express + existing Vue 3 frontend |
| Packaging | electron-packager + electron-winstaller | **electron-builder** (more modern, NSIS installer) |
| Auth | Simple username/password in NeDB | Local SQLite users + sync from ERPNext |
| Data model | 6 flat collections | 30+ relational tables (matching ERPNext doctypes) |
| Sync | None (standalone only) | **Full bidirectional sync** with ERPNext |

### Key Patterns Adopted

1. **Express inside Electron** — The core pattern of running a local HTTP server inside Electron works well for separating the frontend from backend logic
2. **File-based data persistence** — SQLite file in AppData directory for crash-resilient local storage
3. **Local invoice numbering** — Terminal-specific naming series prevents conflicts across devices
4. **Receipt generation** — HTML-based receipts printed via Electron's native printing API

### Why SQLite Over NeDB

NeDB was last updated in 2016 and has known issues with large datasets. For a POS with 65K+ items:

- **SQLite** handles complex JOINs (item + price + stock + barcode) efficiently
- **FTS5** provides instant full-text search across item catalog
- **WAL mode** allows concurrent reads during write operations
- **`better-sqlite3`** is synchronous (no callback complexity) and actively maintained

## 4. Current POSNext Architecture Analysis

### Frontend-Backend Communication

The Vue frontend communicates with the backend exclusively through two patterns:

```javascript
// Pattern 1: Direct call (via apiWrapper.js)
import { call } from './utils/apiWrapper'
const items = await call('pos_next.api.items.get_items', { search_term: 'laptop' })

// Pattern 2: Reactive resource (via frappe-ui)
import { createResource } from 'frappe-ui'
const resource = createResource({ url: 'pos_next.api.bootstrap.get_initial_data' })
```

Both patterns ultimately send:
```
POST /api/method/pos_next.api.{module}.{function}
Content-Type: application/json
X-Frappe-CSRF-Token: {token}

{...params}
```

And expect:
```json
{"message": {result}}
```

### Frappe-Specific Coupling Points

Three files in the frontend have Frappe-specific imports that need addressing:

1. **`socket.js`** — Imports `socketio_port` from `common_site_config.json`
   - **Solution**: Vite alias to a stub module that exports `socketio_port = 0`

2. **`main.js`** — Uses `frappeRequest` and `setConfig("resourceFetcher", ...)` for CSRF-aware API calls
   - **Solution**: In Electron mode, the local server doesn't require CSRF tokens — the existing CSRF logic simply passes through

3. **`csrf.js`** — CSRF token management
   - **Solution**: Local server returns a static CSRF token, existing CSRF refresh logic harmlessly no-ops

### Complete API Surface (82 Endpoints)

All endpoints were catalogued by examining the Python source:

| Module | File | Endpoints | Complexity |
|--------|------|-----------|------------|
| bootstrap | `bootstrap.py` | 1 | Low — reads config |
| auth | `auth.py` | 1 | Low — password check |
| items | `items.py` | 12 | Medium — search, stock, batch/serial |
| invoices | `invoices.py` | 18 | **High** — submit, tax calc, stock update |
| customers | `customers.py` | 3 | Low — CRUD |
| pos_profile | `pos_profile.py` | 14 | Low — read config |
| shifts | `shifts.py` | 5 | Medium — open/close/reconcile |
| offers | `offers.py` | 3 | Medium — pricing rules |
| wallet | `wallet.py` | 6 | Low (online-preferred) |
| partial_payments | `partial_payments.py` | 6 | Medium — payment tracking |
| credit_sales | `credit_sales.py` | 5 | Low (online-preferred) |
| localization | `localization.py` | 4 | Low — cached translations |
| qz | `qz.py` | 4 | N/A — replaced by native printing |
| utilities | `utilities.py` | 1 | Trivial |

### IndexedDB Schema (Existing Offline Support)

The web version already has an IndexedDB schema in `POS/src/utils/offline/db.js` with 14 stores. The SQLite schema is a **superset** of this, ensuring all offline data the frontend expects is available locally.

## 5. Implementation Phases

### Phase 1: Foundation (Weeks 1-4) ✅ COMPLETED

**Goal**: Electron app launches, Express server starts, Vue UI loads from local server.

#### Deliverables

- [x] Project scaffolding (`package.json`, directory structure)
- [x] Electron main process (`main.js`, `preload.js`)
- [x] Express server with Frappe-compat middleware (`frappe-compat.js`)
- [x] SQLite database layer (`connection.js`, `schema.js`, `migrations.js`)
- [x] All 82 API route registrations in `server/index.js`
- [x] Vite config for Electron build (`vite.config.electron.js`)
- [x] `common_site_config.json` stub for socket.js compatibility

#### Technical Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Server port | 18420 | Unlikely to conflict with common services |
| DB path | `%APPDATA%/POSNext/data/` | Standard Electron convention |
| SQLite pragmas | WAL + 64MB cache | Optimal for read-heavy POS workload |
| Context isolation | `true` | Security best practice for Electron |
| IPC bridge | `contextBridge.exposeInMainWorld` | Secure, no `nodeIntegration` needed |

---

### Phase 2: Core API Implementation (Weeks 3-8) ✅ COMPLETED

**Goal**: POS can open shift, browse items, submit invoices, close shift — all offline.

#### Tier 1 — Essential (Fully Implemented)

1. **`bootstrap.js`** — Reads settings, shift, profile, payment methods from SQLite
2. **`shifts.js`** — Full shift lifecycle: open, check, close, reconcile payments
3. **`pos_profile.js`** — Profile data, settings, taxes, warehouses, sales persons
4. **`items.js`** — FTS5 search, item group hierarchy (lft/rgt), barcode lookup, batch/serial data, stock quantities, warehouse availability
5. **`customers.js`** — Search, create (with `created_locally` flag), get details
6. **`invoices.js`** — Full lifecycle: create draft, update, submit (with stock decrement), return (with stock increment), delete draft, search, validate

#### Tier 2 — Working Implementations

7. **`offers.js`** — Coupon validation, active offers query
8. **`partial_payments.js`** — Local payment tracking and summary
9. **`localization.js`** — Cached translations from SQLite

#### Tier 3 — Stubs (Online-Preferred Features)

10. **`wallet.js`** — Balance query works locally; credit operations require online
11. **`credit_sales.js`** — Balance tracking local; redemption requires online
12. **`qz.js`** — Stubs (replaced by native Electron printing)
13. **`auth.js`** — Local password verification

#### Invoice Submission Engine

The most complex piece — ported from `invoices.py` (~200 lines of core logic):

```
submitInvoice() flow:
1. Deduplication check (offline_id UNIQUE constraint)
2. Generate terminal-specific invoice name (POS-{TERMINAL}-00001)
3. Transaction: INSERT invoice + items + payments + taxes
4. Stock update: decrement/increment based on is_return flag
5. Return full invoice with child tables
```

---

### Phase 3: Sync Engine (Weeks 6-10) ✅ COMPLETED

**Goal**: Desktop syncs bidirectionally with ERPNext when online.

#### Components Built

1. **`engine.js`** — Sync coordinator with status tracking, connection checking, and progress reporting
2. **`pull.js`** — Full and delta pull from ERPNext:
   - 13 pull functions (system settings, companies, profiles, items, prices, stock, customers, etc.)
   - Paginated item pull (500/batch with 200ms delay)
   - Delta sync via `modified > last_sync` filter
3. **`push.js`** — Push local changes to ERPNext:
   - Invoice push with `offline_id` deduplication
   - New customer sync (updates local references)
   - Shift data sync
4. **`scheduler.js`** — Auto-sync every 5 minutes when online

#### Sync Safety

- All database operations use transactions (atomic success/failure)
- Invoice push is idempotent (safe to retry)
- Sync log table provides audit trail for debugging
- Failed syncs mark records with `sync_status = 'failed'` and `sync_error`

---

### Phase 4: Hardware Integration (Weeks 8-10) ✅ COMPLETED

**Goal**: Receipts print on thermal printers, barcode scanners work.

#### Deliverables

- [x] Native printing via Electron's `webContents.print()` API
- [x] Receipt HTML template generator (`printer.js`)
- [x] IPC bridge for printer access from renderer
- [x] Barcode scanner support (keyboard input — no changes needed)

---

### Phase 5: Build & Packaging (Weeks 10-12) — READY

**Goal**: Produce a distributable .exe installer.

#### Configuration Complete

- `electron-builder` config in `package.json`
- NSIS installer (non-silent, per-machine, custom install directory)
- Windows (x64), macOS (dmg), Linux (AppImage) targets
- Auto-updater ready (`electron-updater` dependency installed)

#### To Complete

- [ ] Add application icon (`.ico`, `.icns`, `.png`) to `resources/`
- [ ] Configure auto-update feed URL (GitHub Releases or S3)
- [ ] Create setup wizard UI for first-time data provisioning
- [ ] End-to-end testing on clean Windows machine
- [ ] Code signing certificate (optional, prevents "Unknown Publisher" warning)

---

## 6. Remaining Work

### Priority 1: Setup Wizard UI

A Vue component (or simple HTML page) that guides first-time users through:
1. Entering ERPNext URL and API credentials
2. Testing the connection
3. Selecting POS Profile
4. Running initial data pull with progress bar

### Priority 2: Auto-Updates

Configure `electron-updater` with a release feed:
```javascript
const { autoUpdater } = require('electron-updater')
autoUpdater.setFeedURL({ provider: 'github', owner: 'org', repo: 'pos-next-desktop' })
autoUpdater.checkForUpdatesAndNotify()
```

### Priority 3: Tax Calculation Engine

The current implementation stores taxes from ERPNext as-is. For full offline tax calculation:
- Implement "On Net Total" percentage calculation
- Implement "On Previous Row Total" calculation
- Handle tax-inclusive pricing (reverse calculation)
- Match ERPNext's rounding behavior

### Priority 4: Comprehensive Testing

- [ ] Unit tests for each API handler against in-memory SQLite
- [ ] Integration tests: full POS flow (open shift → invoice → close shift)
- [ ] Sync tests: mock ERPNext API, verify push/pull correctness
- [ ] E2E tests: Playwright with Electron support
- [ ] Multi-terminal tests: two instances syncing to same ERPNext

### Priority 5: Advanced Features

- [ ] Product bundle availability checking
- [ ] Complex promotional schemes (Buy X Get Y, tiered pricing)
- [ ] Wallet top-up and credit management offline
- [ ] Image caching for item images
- [ ] Offline reports and analytics

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Tax calculation mismatch | Medium | High | Include full invoice data in sync; ERPNext recalculates and flags discrepancies |
| Stock overselling (multiple terminals) | Medium | Medium | Stock is advisory; `allow_negative_stock` setting exists; ERPNext reconciles on sync |
| Slow initial sync (65K items) | Low | Medium | Paginated pull with progress bar; same batch strategy as web offline sync (~3-5 min) |
| frappe-ui update breaks compatibility | Low | Medium | Pin version; the HTTP contract is stable and unlikely to change |
| ERPNext API changes across versions | Medium | Medium | Version-check during sync setup; document minimum ERPNext version |
| SQLite corruption | Very Low | High | WAL mode + NORMAL synchronous pragma; backup mechanism on app close |
| Large database size | Low | Low | 65K items = ~50-100MB; modern machines handle this easily |

---

## 8. Key Files Reference

### Files Created (in this implementation)

| File | Lines | Purpose |
|------|-------|---------|
| `electron/main.js` | 120 | Electron entry, window management, IPC |
| `electron/preload.js` | 30 | Secure IPC bridge |
| `electron/server/index.js` | 190 | Express app, all 82 routes |
| `electron/server/frappe-compat.js` | 80 | Frappe response format wrapper |
| `electron/server/db/connection.js` | 55 | SQLite singleton |
| `electron/server/db/schema.js` | 550 | 30+ tables, FTS5, triggers |
| `electron/server/db/migrations.js` | 80 | Version-tracked migrations |
| `electron/server/routes/bootstrap.js` | 120 | Initial data endpoint |
| `electron/server/routes/items.js` | 280 | Item search, barcode, stock |
| `electron/server/routes/invoices.js` | 420 | Invoice CRUD, submit, return |
| `electron/server/routes/customers.js` | 55 | Customer CRUD |
| `electron/server/routes/shifts.js` | 200 | Shift lifecycle |
| `electron/server/routes/pos_profile.js` | 140 | Profile data, settings |
| `electron/server/routes/offers.js` | 65 | Offers, coupons |
| `electron/server/routes/wallet.js` | 50 | Wallet operations |
| `electron/server/routes/partial_payments.js` | 80 | Partial payment tracking |
| `electron/server/routes/credit_sales.js` | 50 | Credit sale tracking |
| `electron/server/routes/localization.js` | 45 | Translation cache |
| `electron/server/routes/auth.js` | 25 | Password verification |
| `electron/server/routes/qz.js` | 25 | QZ Tray stubs |
| `electron/server/routes/utilities.js` | 12 | CSRF token |
| `electron/server/sync/engine.js` | 140 | Sync coordinator |
| `electron/server/sync/pull.js` | 380 | ERPNext → SQLite |
| `electron/server/sync/push.js` | 170 | SQLite → ERPNext |
| `electron/server/sync/scheduler.js` | 55 | Auto-sync scheduler |
| `electron/printing/printer.js` | 160 | Native printing |
| `vite.config.electron.js` | 65 | Electron Vite build config |
| **Total** | **~4,300** | |

### Files Referenced (in the existing POSNext codebase)

| File | Why It Matters |
|------|---------------|
| `POS/src/main.js` | API initialization via `setConfig("resourceFetcher", ...)` |
| `POS/src/utils/apiWrapper.js` | All API calls flow through `call()` |
| `POS/src/utils/offline/db.js` | IndexedDB schema — SQLite is superset |
| `POS/src/socket.js` | Imports `common_site_config.json` — aliased in Electron |
| `POS/vite.config.js` | Base for `vite.config.electron.js` fork |
| `pos_next/api/invoices.py` | Invoice submission logic to port |
| `pos_next/api/items.py` | Item query patterns to replicate |
| `pos_next/api/bootstrap.py` | Initial data contract |
| `pos_next/api/constants.py` | POS Settings field list |

---

## 9. Timeline Summary

| Phase | Status | Weeks | Key Deliverable |
|-------|--------|-------|-----------------|
| Foundation | ✅ Done | 1-4 | Electron + Express + SQLite + Vite config |
| Core API | ✅ Done | 3-8 | 82 endpoints, invoice engine, item search |
| Sync Engine | ✅ Done | 6-10 | Pull + push + scheduler + conflict resolution |
| Hardware | ✅ Done | 8-10 | Native printing, barcode (no-op) |
| Packaging | 🔧 Config Ready | 10-12 | electron-builder config, needs icons + testing |
| Testing | ⏳ Pending | 12-14 | Unit, integration, E2E, multi-terminal |
| Setup Wizard | ⏳ Pending | — | First-time provisioning UI |
