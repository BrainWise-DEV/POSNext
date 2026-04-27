# POS Next desktop shell

Tauri v2 wrapper around the existing Vue POS frontend in [../POS](../POS). Produces per-customer Windows installers that bundle the SPA and talk to a remote Frappe Cloud site over HTTPS via Tauri's Rust HTTP plugin (no browser CORS, no cookie auth — uses Frappe API key + secret stored in Stronghold).

## Prerequisites

- Node 18+ / yarn
- Rust 1.77+ (`rustup install stable`)
- On Windows build host: Microsoft Visual Studio Build Tools 2022 with the **Desktop development with C++** workload + WebView2 SDK
- On Linux/macOS build host: standard `tauri build` cross-compilation prerequisites

## Per-customer build

1. Copy `customers/_template.json` to `customers/<slug>.json`, fill in `siteUrl`, `productName`, `identifier`, `version`, optional updater config.
2. Drop the customer's logo + icon set under `assets/customers/<slug>/icons/` (32x32, 128x128, 128x128@2x, icon.icns, icon.ico).
3. From the repo root: `yarn desktop:build <slug>` → produces `desktop/dist/<slug>/POS Next-<version>-Setup.exe`.

## Local dev (against a customer's site)

```bash
# repo root
yarn desktop:dev acme
```

Spawns Vite on :8080 with `VITE_POS_TARGET=desktop` and `VITE_FRAPPE_BASE_URL=https://acme.frappe.cloud`, then `tauri dev` opens the desktop window pointed at it. Devtools are open by default in debug builds.

## How it talks to Frappe Cloud

- All API calls go through `@tauri-apps/plugin-http` (Rust-side fetch) so browser CORS doesn't apply.
- Auth: cashier logs in once with Frappe email + password → app calls `/api/method/login`, then `frappe.core.doctype.user.user.generate_keys` → stores `{api_key, api_secret}` in Stronghold (`tauri-plugin-stronghold`, encrypted on disk under `%APPDATA%\com.blazetech.posnext.<slug>\`).
- Every subsequent request adds `Authorization: token <key>:<secret>` — no cookies, no CSRF.
- Realtime (Socket.IO) is disabled in desktop builds; the existing realtime composables are no-ops.

## What lives where

- `src-tauri/` — Rust shell. `lib.rs` registers plugins (http, stronghold, store, updater, dialog, process, shell). Capabilities in `capabilities/default.json` lock the HTTP plugin to `*.frappe.cloud` and `*.erpnext.com`.
- `customers/<slug>.json` — per-customer config (gitignored except template).
- `scripts/build-customer.mjs` — reads a customer config, writes `tauri.conf.<slug>.json`, runs `vite build --mode desktop` then `tauri build`.
- `scripts/publish-update.mjs` — signs the resulting `.exe`, writes `latest.json`, ready to upload to whichever update channel the customer has.
- `keys/` — updater signing keys. Gitignored. Generate with `tauri signer generate -w keys/<slug>.key`.

## Auto-update

Disabled by default. To enable for a customer:

1. `tauri signer generate -w keys/<slug>.key` (writes `<slug>.key` and `<slug>.key.pub`).
2. Put the `.pub` content into `customers/<slug>.json` → `updater.pubkey` and set `updater.active: true` and `updater.endpoint` to the URL where you'll host `latest.json`.
3. After each release: `yarn desktop:publish <slug>` → produces `latest.json` + signed `.exe`. Upload both to the configured endpoint.
