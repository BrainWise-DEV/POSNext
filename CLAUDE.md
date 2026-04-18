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

# Frontend tests (Vitest + jsdom). No test files currently exist — infra is wired.
cd POS && yarn test                # watch mode
cd POS && yarn test:run            # single run
cd POS && yarn test:run -- path/to/file.test.js   # single file

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

The frontend does **not** define its own REST routes. It calls whitelisted Frappe methods under `pos_next.api.*` through `frappe-ui`'s `frappeRequest`. See [pos_next/api/](pos_next/api/) for the full surface (bootstrap, invoices, items, offers, customers, shifts, wallet, partial_payments, credit_sales, promotions, branding, localization, qz). Any new frontend capability typically means: add a `@frappe.whitelist()` in `pos_next/api/*.py`, then call it from `POS/src/`.

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

**Offline support** is the most complex subsystem:

- A dedicated Web Worker [POS/src/workers/offline.worker.js](POS/src/workers/offline.worker.js) is copied into the build by `vite-plugin-static-copy`. The main thread talks to it via [POS/src/utils/offline/workerClient.js](POS/src/utils/offline/workerClient.js) (RPC, health checks, crash recovery).
- Persistence uses Dexie/IndexedDB ([POS/src/utils/offline/db.js](POS/src/utils/offline/db.js)), with item caching, queued invoices, receipt cache, and translation cache split into separate modules.
- Service-worker runtime caching in [vite.config.js](POS/vite.config.js) uses different strategies per URL (CacheFirst for assets/fonts, StaleWhileRevalidate for `/files/*.{jpg,png,...}` product images, NetworkFirst for `/api/*` with a 10 s timeout). Navigation to `/pos` uses a 3 s NetworkFirst.
- CSRF token is forwarded to the worker on boot and on every refresh; offline invoice submission depends on that sync.

**Routing** ([POS/src/router.js](POS/src/router.js)) is minimal — three routes (`POSSale`, `Login`, catch-all) with an auth guard against `session.isLoggedIn`. Production base path is `/pos`.

**Aliases**: `@` → `POS/src`. `tailwind.config.js` alias is set so `frappe-ui` components can resolve it.

### Where to add things

- New server API: `pos_next/api/<module>.py` with `@frappe.whitelist()`. Keep hooks thin — business logic belongs in the module, not `hooks.py`.
- New DocType: `pos_next/pos_next/doctype/<name>/` (follow the existing pattern, including `test_<name>.py`).
- New Vue view: page in `POS/src/pages/` + route in `router.js`; prefer Pinia store over page-local state for anything shared.
- New realtime event: emit from a `doc_events` handler in `pos_next/realtime_events.py`, subscribe in a `useRealtime*.js` composable.

## Constraints worth remembering

- **Dev requires `"ignore_csrf": 1`** in `site_config.json` for the Vite dev server on :8080 to reach `/api` on :8000. Production relies on `window.csrf_token` injected by `pos.html`.
- Vite build **must** stay targeted at `../pos_next/public/pos/` with `base=/assets/pos_next/pos/` — changing either breaks asset URLs in the Jinja shell.
- ES2015 target, `chunkSizeWarningLimit` is 1500 — acceptable for this app; don't silently lower it without checking bundle impact.
- CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) currently only verifies install on a fresh bench + runs linters; backend `run-tests` is commented out. Treat `bench run-tests` as local-only until CI is re-enabled.
- License is **AGPL-3.0** — any distributed modifications inherit copyleft.
