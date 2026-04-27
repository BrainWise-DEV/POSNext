# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is a **Frappe/ERPNext v15 app** (`pos_next`) that ships a modern POS frontend. The repo contains two distinct code bases side by side:

- [pos_next/](pos_next/) — Python Frappe app (API, DocTypes, hooks, overrides, fixtures, server-side services). This is what `bench install-app pos_next` installs.
- [POS/](POS/) — Vue 3 / Vite / Tailwind frontend. It builds into `pos_next/public/pos/` and is served at `/pos` via the `website_route_rules` in [pos_next/hooks.py](pos_next/hooks.py).

Do not confuse them: edit Python inside `pos_next/`, edit JS/Vue inside `POS/src/`.

## Common commands

All `npm`/`yarn`/`vite`/`biome`/`vitest` commands must be run from [POS/](POS/), not from the repo root. The root [package.json](package.json) proxies `dev`/`build` into `POS/` but lint/test do not proxy.

```bash
# Frontend dev server on :8080, proxies /api,/app,/assets,/files to bench on :8000
cd POS && yarn dev                 # or: npm run dev

# Production build into ../pos_next/public/pos/ with base=/assets/pos_next/pos/
cd POS && yarn build               # also writes pos_next/public/pos/version.json

# Lint / format (Biome, tabs, double quotes, no semis)
cd POS && yarn lint                # biome check .
cd POS && yarn lint:fix            # biome check --write .
cd POS && yarn format

# Frontend tests (Vitest + jsdom + fake-indexeddb). Specs live under POS/tests/.
cd POS && yarn test                # watch mode
cd POS && yarn test:run            # single run (39 tests across the offline subsystem)
cd POS && yarn test:run -- path/to/file.test.js   # single file
cd POS && yarn test:coverage       # v8 coverage; report under POS/coverage/

# Frontend E2E (Playwright). Auto-starts the Vite dev server (reuses one
# if already running). Browser binary path: PLAYWRIGHT_BROWSERS_PATH.
cd POS && yarn e2e                 # headless
cd POS && yarn e2e:headed          # see the browser
cd POS && yarn e2e:install         # install chromium binary if missing

# Backend: run from ~/frappe-bench
bench --site <site> run-tests --app pos_next
bench --site <site> run-tests --app pos_next --module pos_next.api.test_customers

# Backend install/migrate cycle
bench --site <site> install-app pos_next
bench --site <site> migrate
bench build --app pos_next          # rebuilds assets via vite
bench --site <site> clear-cache
```

Backend Python is linted with **ruff** (config in [pyproject.toml](pyproject.toml): `target-version = py310`, tabs, double quotes, line length 110). Pre-commit hooks are set up via `pre-commit install` from the app root.

Source maps in production builds are **off by default** — set `POS_NEXT_ENABLE_SOURCEMAP=true` before `yarn build` if you need them. The build version is stamped from `POS_NEXT_BUILD_VERSION` env or `Date.now()` and is the cache-busting key surfaced by [pos_next/utils.py:get_build_version](pos_next/utils.py).

## Big-picture architecture

### Frontend → Backend integration surface

The frontend does **not** define its own REST routes. It calls whitelisted Frappe methods under `pos_next.api.*` through `frappe-ui`'s `frappeRequest`. See [pos_next/api/](pos_next/api/) for the full surface (bootstrap, invoices, items, offers, customers, shifts, wallet, partial_payments, credit_sales, promotions, branding, localization, qz, offline_data). Any new frontend capability typically means: add a `@frappe.whitelist()` in `pos_next/api/*.py`, then call it from `POS/src/`.

Reference data for offline use lives in [pos_next/api/offline_data.py](pos_next/api/offline_data.py): `get_taxes`, `get_uoms`, `get_loyalty_programs`, and the one-shot `get_offline_bundle` (taxes + UOMs + loyalty in a single round-trip). Customer enrichment for offline (addresses, loyalty points, wallet balance) and the offline customer-create replay endpoint live in [pos_next/api/customers.py](pos_next/api/customers.py): `get_customers_for_offline`, `get_customer_offline_extras`, `replay_offline_customer` (idempotent on `offline_id`, uses a `pos_next_offline_id` Custom Field on Customer when present).

Server→client realtime uses Socket.IO. Frappe document events in [hooks.py](pos_next/hooks.py) (`doc_events` on `Sales Invoice`, `Customer`, `POS Profile`) fan out through [pos_next/realtime_events.py](pos_next/realtime_events.py) and are consumed by `POS/src/composables/useRealtime*.js` plus `POS/src/socket.js`.

### Frappe integration points to know before editing

[pos_next/hooks.py](pos_next/hooks.py) is the contract with the framework. Key extension points already used:

- `override_doctype_class` — **Sales Invoice is overridden** by [pos_next/overrides/sales_invoice.py](pos_next/overrides/sales_invoice.py). Changing invoice behavior usually means editing that subclass, not patching ERPNext.
- `standard_queries` — custom `Item` query in [pos_next/validations.py](pos_next/validations.py) (company-aware filtering).
- `doc_events` — Sales Invoice validate/submit/cancel run multiple hooks (`sales_invoice_hooks`, `wallet`, `realtime_events`). Order matters; list position is execution order.
- `fixtures` — the roles `POSNext Cashier` and `Nexus POS Manager` plus their Custom DocPerms sync on migrate. Editing permissions in the UI must be followed by `bench export-fixtures` to persist.
- `scheduler_events` — hourly/daily/monthly tasks live in [pos_next/tasks/](pos_next/tasks/) (branding monitor, promo cleanup).
- `website_route_rules` — maps `/pos/<path>` to the `pos` template ([pos_next/www/pos.html](pos_next/www/pos.html)), which is the Jinja entry that bootstraps the SPA.
- `after_install` / `after_migrate` — [pos_next/install.py](pos_next/install.py) runs post-fixture setup and cache clearing.

### Frontend architecture

Entry is [POS/src/main.js](POS/src/main.js). Startup sequence (documented in that file) is non-trivial and order-sensitive:

1. Register PWA service worker (vite-plugin-pwa, generated workbox config in [vite.config.js](POS/vite.config.js)).
2. Create Vue app + Pinia, install `frappe-ui` plugins, wrap `resourceFetcher` with a **CSRF-aware retry** ([POS/src/utils/csrf.js](POS/src/utils/csrf.js) — auto-refreshes token on 401/403, re-syncs to the offline worker).
3. CSRF fetch and user resource fetch run in parallel; the app does not mount until both settle.
4. After mount, [POS/src/stores/bootstrap.js](POS/src/stores/bootstrap.js) preloads POS profile/precision data and then initializes Socket.IO with the site name from that payload.
5. CSRF token is refreshed every 30 minutes via `setInterval`.

**State (Pinia)** lives in [POS/src/stores/](POS/src/stores/). `posCart.js` is the biggest; it uses an internal async queue (`createAsyncQueue`) to serialize cart recalculations — when adding cart mutations, enqueue through it rather than racing state directly. `posSettings`, `posShift`, `posOffers`, `posDrafts`, `posSync`, `itemSearch`, `customerSearch`, `stock` are separate concerns; reuse them instead of adding duplicate state in components.

**Composables** in [POS/src/composables/](POS/src/composables/) wrap cross-cutting UX (shift, offline status, payment numpad, session lock, QZ Tray printing, realtime subscriptions). Prefer extending these over inlining logic in `.vue` components.

**Offline support** is the most complex subsystem. See [docs/OFFLINE_DATA_GUIDE.md](docs/OFFLINE_DATA_GUIDE.md) for the full data-side reference and [docs/OFFLINE_SYNC.md](docs/OFFLINE_SYNC.md) for the queue sync state machine.

- A dedicated Web Worker [POS/src/workers/offline.worker.js](POS/src/workers/offline.worker.js) is copied into the build by `vite-plugin-static-copy`. The main thread talks to it via [POS/src/utils/offline/workerClient.js](POS/src/utils/offline/workerClient.js) (RPC, health checks, crash recovery).
- Persistence uses Dexie/IndexedDB ([POS/src/utils/offline/db.js](POS/src/utils/offline/db.js)). The schema is **auto-versioned** via a hash of `CURRENT_SCHEMA` — bump the schema by editing that object; Dexie auto-migrates on next load. Tables include items, customers, item_prices, stock, payment_methods, sales_persons, taxes, uoms, item_groups, brands, loyalty_programs, offers, invoice_history, unpaid_invoices, translations, plus the queues `invoice_queue`, `payment_queue`, `customer_queue`, `drafts`, and `settings`.
- Service-worker runtime caching in [vite.config.js](POS/vite.config.js) uses different strategies per URL (CacheFirst for assets/fonts, StaleWhileRevalidate for `/files/*.{jpg,png,...}` product images, NetworkFirst for `/api/*` with a 10 s timeout). Navigation to `/pos` uses a 3 s NetworkFirst.
- Item images are also **eagerly pre-downloaded** after item-cache seeding by [POS/src/utils/offline/imagePrefetch.js](POS/src/utils/offline/imagePrefetch.js) (throttled, resumable, cancellable), so the SW image cache covers everything in the catalog, not just what the cashier has viewed.
- CSRF token is forwarded to the worker on boot and on every refresh; offline invoice submission depends on that sync.

**Offline write queues** — invoices and customers both have idempotent queues:

- `invoice_queue` (in [POS/src/utils/offline/sync.js](POS/src/utils/offline/sync.js)) — `saveOfflineInvoice` records a `stock_delta` so a permanent sync failure or a manual delete can revert the optimistic stock decrement (`revertLocalStockForInvoice`).
- `customer_queue` (in [POS/src/utils/offline/customerQueue.js](POS/src/utils/offline/customerQueue.js)) — `enqueueOfflineCustomer` writes a placeholder customer row immediately so it's selectable mid-session; `syncOfflineCustomers` (run BEFORE invoice sync in `posSync.syncPending`) replays via `replay_offline_customer`, which is idempotent on `offline_id`.

**Three durability layers protect queued POS data:**

1. **`navigator.storage.persist()`** — [POS/src/utils/offline/persistence.js](POS/src/utils/offline/persistence.js). Asks the browser not to evict our IndexedDB under storage pressure. Fired once on boot from `main.js`.
2. **Service-worker runtime caches** — covered above; protect assets and opportunistic API responses.
3. **QZ-Tray on-disk mirror** — [POS/src/utils/offline/diskBackup.js](POS/src/utils/offline/diskBackup.js). Mirrors every queued invoice + customer to JSON files on the host filesystem via QZ Tray's sandbox file API (no certificate elevation needed). `restoreFromDisk()` re-inserts any rows missing from IndexedDB after a "Clear site data" or browser reinstall, and runs automatically 5 s after boot. A "Restore from Disk" button is exposed in the offline-invoices dialog. Best-effort: silently degrades to layers 1 + 2 when QZ isn't running.

**Routing** ([POS/src/router.js](POS/src/router.js)) is minimal — three routes (`POSSale`, `Login`, catch-all) with an auth guard against `session.isLoggedIn`. Production base path is `/pos`.

**Aliases**: `@` → `POS/src`. `tailwind.config.js` alias is set so `frappe-ui` components can resolve it.

### Where to add things

- New server API: `pos_next/api/<module>.py` with `@frappe.whitelist()`. Keep hooks thin — business logic belongs in the module, not `hooks.py`.
- New DocType: `pos_next/pos_next/doctype/<name>/` (follow the existing pattern, including `test_<name>.py`).
- New Vue view: page in `POS/src/pages/` + route in `router.js`; prefer Pinia store over page-local state for anything shared.
- New realtime event: emit from a `doc_events` handler in `pos_next/realtime_events.py`, subscribe in a `useRealtime*.js` composable.
- New offline cache: add a Dexie store to `CURRENT_SCHEMA` in [POS/src/utils/offline/db.js](POS/src/utils/offline/db.js) (auto-versioned), then add a `cacheXFromServer` + `getCachedX` pair to [POS/src/utils/offline/cache.js](POS/src/utils/offline/cache.js) and re-export from [POS/src/utils/offline/index.js](POS/src/utils/offline/index.js). Seed it from `posSync.preloadDataForOffline`.
- New offline write queue: follow the `customerQueue.js` pattern — write a placeholder/optimistic row + a queue row inside one transaction, drain via a `syncX` function gated by `isOffline()`, replay through an idempotent backend method keyed on `offline_id`, drop the disk mirror via `removeMirroredX` on success.
- New frontend test: drop a `*.test.js` under [POS/tests/](POS/tests/). [POS/tests/setup.js](POS/tests/setup.js) installs `fake-indexeddb` globally so Dexie works under jsdom; mock `@/utils/apiWrapper` for any code that calls the server.

## Constraints worth remembering

- **Dev requires `"ignore_csrf": 1`** in `site_config.json` for the Vite dev server on :8080 to reach `/api` on :8000. Production relies on `window.csrf_token` injected by `pos.html`.
- Vite build **must** stay targeted at `../pos_next/public/pos/` with `base=/assets/pos_next/pos/` — changing either breaks asset URLs in the Jinja shell.
- ES2015 target, `chunkSizeWarningLimit` is 1500 — acceptable for this app; don't silently lower it without checking bundle impact.
- CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) currently only verifies install on a fresh bench + runs linters; backend `run-tests` is commented out. Treat `bench run-tests` as local-only until CI is re-enabled.
- License is **AGPL-3.0** — any distributed modifications inherit copyleft.
