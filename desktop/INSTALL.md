# POS Next — Desktop installation guide

This guide covers two audiences:

- **Part A** — for the engineer who **builds** the per-customer `.exe` (one-time setup of the build machine + the workflow for cutting a release).
- **Part B** — for the cashier or IT staff who **installs** that `.exe` on the till PCs.

Skip to the part you need:

- [A. Build machine setup](#a-build-machine-setup)
- [B. End-user installation](#b-end-user-installation)
- [C. First-run login](#c-first-run-login)
- [D. Verifying offline + printing](#d-verifying-offline--printing)
- [E. Updating an existing install](#e-updating-an-existing-install)
- [F. Troubleshooting](#f-troubleshooting)

---

## A. Build machine setup

You only need to do this **once per build machine**. Anyone packaging a customer release runs through this.

### A.1 — Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 18 LTS or newer | `node --version` |
| Yarn | 1.22+ | `yarn --version` |
| Rust | 1.77+ | install via [rustup.rs](https://rustup.rs/) |
| Windows-only: VS Build Tools 2022 | latest | install with the **Desktop development with C++** workload |
| Windows-only: WebView2 SDK | latest | bundled with the build tools workload above |
| Linux build host: webkit2gtk | 4.1 | `sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev` |
| QZ Tray (optional, for printing) | 2.2+ | only on the cashier's PC, not the build machine |

> _Reference image — place a screenshot of the Visual Studio Installer with "Desktop development with C++" ticked at_ `docs/images/install-vs-build-tools.png`

```
$ rustup --version
rustup 1.27.1 (54dd3d00f 2024-04-24)

$ rustc --version
rustc 1.77.2 (25ef9e3d8 2024-04-09)
```

### A.2 — Clone + install

```bash
git clone <repo-url>
cd pos_next

# Frontend deps (pulls Vue, frappe-ui, Tauri JS plugins)
cd POS && yarn install && cd ..

# Tauri CLI (lives at desktop/ level)
cd desktop && yarn install && cd ..
```

Verify:

```bash
cd desktop && yarn tauri info
```

You should see something like:

```
[✔] Environment
    - OS: Windows 11.0.22631 X64
    - WebView2: 124.0.2478.51
    - MSVC: Visual Studio Build Tools 2022
    - rustc: 1.77.2
    - cargo: 1.77.2
[✔] Packages
    - tauri [RUST]: 2.0.6
    - @tauri-apps/cli [NPM]: 2.1.0
```

### A.3 — Define a customer

For each customer you ship to, create one config file:

```bash
cp desktop/customers/_template.json desktop/customers/acme.json
```

Edit `desktop/customers/acme.json`:

```json
{
  "slug": "acme",
  "productName": "POS Next — Acme",
  "identifier": "com.blazetech.posnext.acme",
  "version": "1.0.0",
  "siteUrl": "https://acme.frappe.cloud",
  "displayName": "Acme",
  "iconDir": "../assets/customers/acme/icons",
  "updater": {
    "active": false
  }
}
```

| Field | What it does |
|-------|--------------|
| `slug` | Used in the installer filename + the `desktop/dist/<slug>/` output directory. Lowercase, no spaces. |
| `productName` | Shown in Add/Remove Programs and on the Start menu shortcut. |
| `identifier` | Reverse-DNS bundle ID. **Each customer must have a unique value** — Tauri uses it for the app data dir and Windows registry key. |
| `version` | Semver. Bumped on every release. |
| `siteUrl` | The customer's Frappe Cloud URL. Must include `https://`. Baked into the build via `VITE_FRAPPE_BASE_URL`. |
| `iconDir` | (Optional) Path to per-customer icons. Drop `32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico` here. If absent, the default Tauri icons are used. |

> ⚠️ `customers/*.json` is gitignored — keep customer URLs out of the repo. Store them in your password manager / secrets vault if you have multiple devs building.

### A.4 — Local dev (smoke-test against the customer's site)

```bash
yarn desktop:dev acme
```

Two processes spawn:

1. Vite at `http://localhost:8080` with `VITE_POS_TARGET=desktop` and `VITE_FRAPPE_BASE_URL=https://acme.frappe.cloud`.
2. The Tauri window pointed at it. Devtools open by default in debug builds (right-click → Inspect, or F12).

You should see the login screen. **Don't** type real customer credentials here — log in with a dev/test user on the customer's site.

> _Reference image — Tauri devtools showing a request to `https://acme.frappe.cloud/api/method/...` with origin `tauri://localhost` and `Authorization: token <key>:<secret>` header at_ `docs/images/devtools-tauri-fetch.png`

```
┌──────────────────────────────────────────────────────────────┐
│ POS Next — Acme                              [_] [□] [×]     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                     Sign in to POS Next                      │
│                Access your point of sale system              │
│                                                              │
│   ┌────────────────────────────────────────────────────┐     │
│   │  User ID / Email                                   │     │
│   │  ┌──────────────────────────────────────────────┐  │     │
│   │  │ cashier@acme.com                             │  │     │
│   │  └──────────────────────────────────────────────┘  │     │
│   │  Password                                          │     │
│   │  ┌──────────────────────────────────────────────┐  │     │
│   │  │ ••••••••••••                              👁  │  │     │
│   │  └──────────────────────────────────────────────┘  │     │
│   │  ┌──────────────────────────────────────────────┐  │     │
│   │  │              Sign in                         │  │     │
│   │  └──────────────────────────────────────────────┘  │     │
│   └────────────────────────────────────────────────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### A.5 — Build the installer

You have two paths: build locally (Windows machine only) or push to GitHub Actions (works from Linux/macOS too).

#### A.5.a — Local build (Windows)

```bash
yarn desktop:build acme
```

This:

1. Reads `desktop/customers/acme.json`.
2. Runs `vite build --mode desktop` with the customer's URL → emits `desktop/dist-frontend/`.
3. Writes `desktop/src-tauri/tauri.conf.acme.json` (merged config).
4. Runs `tauri build --config tauri.conf.acme.json` → produces installers under `desktop/src-tauri/target/release/bundle/`.
5. The output you ship to the customer is:

   ```
   desktop/src-tauri/target/release/bundle/nsis/POS Next — Acme_1.0.0_x64-setup.exe
   ```

Copy that file into `desktop/dist/acme/` (manual step — kept manual so you can inspect the bundle before shipping).

> _Reference image — File Explorer showing the output bundle at_ `docs/images/build-output.png`

#### A.5.b — GitHub Actions build (any OS)

Use this if you develop on Linux/macOS, or if you want builds to be reproducible on a clean machine. The workflow lives at [.github/workflows/desktop-build.yml](../.github/workflows/desktop-build.yml).

**One-time setup per customer:**

1. Open the GitHub repo → **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and add:
   - **Name:** `CUSTOMER_CONFIG_ACME` (uppercase slug, hyphens become underscores)
   - **Value:** the entire JSON contents of your `customers/acme.json`
3. (Optional, only if `updater.active: true`) add `CUSTOMER_UPDATER_KEY_ACME` with the contents of `desktop/keys/acme.key`.
4. (Optional, code-signing) add `WIN_CODESIGN_PFX_BASE64` (base64-encoded `.pfx`) and `WIN_CODESIGN_PFX_PWD`.

**Triggering a build:**

Two ways:

- **Manual** — Actions tab → "Build desktop installer" → Run workflow → enter `acme` as customer slug → click Run. ~5 minutes later the `.exe` appears as a downloadable artifact at the bottom of the run page.
- **Tag push** — `git tag desktop-v1.0.0-acme && git push --tags`. Workflow extracts version + slug from the tag, builds, and attaches the installer to a draft GitHub Release for review before publishing.

The workflow uses GitHub-hosted `windows-latest` runners (free for public repos, ~$0.04/build for private repos at $0.008/min × 5 min).

### A.6 — Frappe Cloud user prerequisites

Before a cashier can sign in for the first time, the customer's Frappe Cloud admin needs to have:

1. **Created the cashier User** in Frappe with `POSNext Cashier` role (or `Nexus POS Manager` for supervisors). Roles are seeded automatically when `pos_next` is installed.
2. The cashier needs **API access enabled**. In Frappe → User → cashier@acme.com → ensure the user has at least one role with API access (the seeded POS roles do).
3. The desktop app calls `frappe.core.doctype.user.user.generate_keys` on first login — that endpoint requires the user to be logged in (which the prior `/api/method/login` call provides via session cookie). No special permission needed.

You do **not** need to:
- Configure CORS or `allow_cors` in `site_config.json` (we bypass browser CORS via Rust HTTP).
- Set up a custom domain or SSL (Frappe Cloud handles HTTPS).
- Generate API keys manually — the app does that on first login and stores them in Stronghold.

---

## B. End-user installation

What you hand the cashier (or their IT person):

- One file: `POS Next — Acme_1.0.0_x64-setup.exe` (or a download URL).
- A note with the cashier's Frappe email + temporary password.
- (Optional) The QZ Tray installer if they need receipt printing.

### B.1 — Windows requirements

| Requirement | Detail |
|-------------|--------|
| OS | Windows 10 1903 (May 2019) or later, or Windows 11 |
| Architecture | x64 only (most retail PCs from the last 7+ years) |
| WebView2 Runtime | Pre-installed on Windows 11 and most Win10 PCs since 2021. The installer auto-fetches it if missing. |
| Disk | ~80 MB free for app + IndexedDB cache |
| RAM | 2 GB free recommended |
| Admin rights for install | Yes (per-machine install) |
| Network | HTTPS to `*.frappe.cloud` for sync. **Offline operation works without internet** once the catalog has cached at least once. |

### B.2 — Installation steps

1. **Double-click** `POS Next — Acme_1.0.0_x64-setup.exe`.
2. If Windows SmartScreen warns "Windows protected your PC", click **More info → Run anyway**. (See [F.1](#f1--smartscreen-blocks-the-installer) for getting rid of this on subsequent releases.)
3. The NSIS installer asks where to put the app. Default is `C:\Program Files\POS Next — Acme\`. Accept it unless your IT policy says otherwise.
4. Click **Install**. Takes ~10 seconds.
5. (First install only) The installer may ask to download the Edge WebView2 Runtime — let it. ~2 minutes on slow connections.
6. Launch from the Start menu shortcut "POS Next — Acme" or the desktop icon.

> _Reference image — Windows Start menu showing the new shortcut at_ `docs/images/start-menu.png`

### B.3 — (Optional) install QZ Tray for receipt printing

Required only if the cashier prints receipts to a thermal printer (Star, Epson, etc).

1. Download QZ Tray 2.2+ from https://qz.io/download/.
2. Run the installer. Accept all defaults.
3. After install, QZ Tray runs in the system tray (look for the QZ icon).
4. The first time POS Next sends a print job, QZ shows a permission popup — tick **Always allow** for the POS Next origin and click **Allow**.

QZ Tray also enables the **on-disk backup** layer: queued offline invoices/customers get mirrored to JSON files under `%APPDATA%\QZ\sandbox\<origin>\pos_next\` so they survive a "Clear browser data" or even a Windows reset.

---

## C. First-run login

When the cashier opens the app the first time, they see the login screen (mocked above in [A.4](#a4--local-dev-smoke-test-against-the-customers-site)).

1. Enter the Frappe email + password from the credentials note.
2. Click **Sign in**.
3. What happens behind the scenes:
   - App POSTs `usr` + `pwd` to `https://<customer>.frappe.cloud/api/method/login` (via Tauri's Rust HTTP — no browser CORS).
   - On success, app calls `frappe.core.doctype.user.user.generate_keys` → receives a fresh API key + secret.
   - App stores the pair encrypted in Stronghold at `%APPDATA%\com.blazetech.posnext.<slug>\pos-next.stronghold`.
   - App fetches the user resource → bootstraps POS profile → preloads items, customers, prices, payment methods, taxes into IndexedDB.
   - First load: 30s–2 min depending on catalog size and network. Watch the bottom-right toast for "Cache ready".
4. After the first login, **subsequent app starts skip the login screen** — Stronghold-stored creds re-authenticate automatically.

> _Reference image — Sale screen with cached items loaded at_ `docs/images/sale-screen-loaded.png`

### C.1 — Logging out / switching users

There's a logout option in the user menu (top-right of the sale screen). Logout wipes Stronghold and forces a fresh login next time. Use this when:

- Handing the till to a different cashier with a different Frappe user.
- The cashier was deactivated in Frappe (the next API call will 401, but you don't have to wait for that — log them out manually).

---

## D. Verifying offline + printing

After install, do this smoke test on every till **before** putting it into service.

| # | Action | Expected |
|---|--------|----------|
| 1 | Open app → login → wait for "Cache ready" toast | Items appear in the catalog grid |
| 2 | **Disconnect the network** (unplug Ethernet, turn off Wi-Fi) | Top-right shows offline indicator within ~10s |
| 3 | Add 3 items to cart | Prices, taxes, totals all compute locally |
| 4 | Submit the invoice | Saved to offline queue, receipt prints (if QZ is set up) |
| 5 | Create a new customer | Appears in offline customer list immediately |
| 6 | **Close the app while still offline** | – |
| 7 | Reopen the app | Goes straight to sale screen (no re-login needed). Queued invoice + customer still visible in the offline dialog |
| 8 | **Reconnect the network** | Within 10s the app shows online again. Queue drains: customer first, then invoice. Both appear in the customer's Frappe Cloud Sales Invoice / Customer list within a minute |
| 9 | (If QZ Tray is running) Check `%APPDATA%\QZ\sandbox\` | A folder for the POS Next origin exists with the queued invoice JSON files |

If any step fails see [F. Troubleshooting](#f-troubleshooting).

---

## E. Updating an existing install

### E.1 — Manual update (works without configuring auto-update)

1. Build the new version on the build machine: bump `version` in `customers/<slug>.json`, run `yarn desktop:build <slug>`.
2. Send the new `.exe` to the customer.
3. They double-click it → it overwrites the existing install, **preserving Stronghold credentials and the IndexedDB cache**. No re-login, no re-sync.

### E.2 — Auto-update (one-time setup per customer)

If you want pushed updates instead of emailing installers:

```bash
# One-time: generate signing keys for this customer
cd desktop
yarn tauri signer generate -w keys/acme.key
# Outputs keys/acme.key (private) and keys/acme.key.pub (public)
```

Edit `desktop/customers/acme.json`:

```json
"updater": {
  "active": true,
  "endpoint": "https://updates.example.com/acme/latest.json",
  "pubkey": "<paste contents of acme.key.pub here>"
}
```

Now after each `yarn desktop:build acme`:

```bash
yarn desktop:publish acme
```

That signs the `.exe`, writes `desktop/dist/acme/latest.json`, and prints upload instructions. Drop both files at the configured `endpoint` (S3, R2, GitHub Releases, etc).

The desktop app polls `latest.json` on boot and every 6 hours. When a newer version exists, it shows an in-app toast → cashier clicks → app downloads + verifies signature + relaunches.

> ⚠️ **Never commit** the `keys/` directory or the `.key` files. They're gitignored already; double-check before pushing.

---

## F. Troubleshooting

### F.1 — SmartScreen blocks the installer

Cause: the `.exe` is unsigned.

Short-term fix: tell the user to click **More info → Run anyway**.

Proper fix: buy a code-signing certificate (~$200/year from DigiCert, Sectigo, etc), install it on the build machine, and add to `desktop/src-tauri/tauri.conf.json`:

```json
"bundle": {
  "windows": {
    "signCommand": "signtool sign /f cert.pfx /p $PASSWORD /tr http://timestamp.digicert.com /td sha256 /fd sha256 \"%1\""
  }
}
```

After you ship a signed installer 2–3 times, SmartScreen reputation kicks in and the warning disappears.

### F.2 — App opens but spins forever on the login screen

Open devtools (F12) → Network tab → try logging in again. Look for the `/api/method/login` request:

- **No request shown** → Tauri HTTP plugin isn't loading. Check `desktop/src-tauri/capabilities/default.json` includes the customer's domain in the `http:default` allowlist.
- **Request failed (network error)** → DNS / firewall blocks `*.frappe.cloud`. Have IT whitelist it.
- **Request returned 401** → bad credentials. Reset the cashier's Frappe password and try again.
- **Request returned 200 but app stays on login** → check the next request to `frappe.core.doctype.user.user.generate_keys`. If that 403s, the Frappe user's role doesn't have API access — add `POSNext Cashier` role.

### F.3 — Offline mode never activates / always says "online"

The pingServer hits `/api/method/pos_next.api.ping` every 30s. If your firewall returns a fake "captive portal" 200 OK page for blocked sites, the app will think it's online when it isn't. Workarounds:

- Configure the firewall to return a real DNS failure or 5xx for blocked hosts.
- Or use the manual offline toggle in the user menu — that overrides the auto-detection.

### F.4 — Queued invoices don't sync after reconnect

1. Open the offline dialog (top-right indicator → "Offline invoices").
2. Look at the per-invoice status. If they all show "Failed: <error>", click one to see the full error.
3. Common causes:
   - **Stock validation** — item went out of stock between offline submission and sync. Edit the queued invoice or delete it (rolls back the optimistic stock decrement).
   - **Customer not found** — the customer queue didn't drain first. Click "Sync customers" first, then "Sync invoices".
   - **Auth expired** — log out and back in to refresh the API key.
4. As a last resort: click "Restore from disk" — re-reads the QZ Tray on-disk mirror and re-queues everything.

### F.5 — App data location for support

When debugging on a customer's machine you may want to inspect:

- **App config + Stronghold vault**: `%APPDATA%\com.blazetech.posnext.<slug>\`
- **IndexedDB (cached items, queues)**: `%LOCALAPPDATA%\com.blazetech.posnext.<slug>\EBWebView\Default\IndexedDB\`
- **QZ disk mirror**: `%APPDATA%\QZ\sandbox\tauri-localhost\pos_next\`
- **Logs**: open the app, F12 → Console. To get a saved log, paste this in the console:

  ```js
  copy(JSON.stringify(window.posLogger.export(), null, 2))
  ```

  Then paste the result into a support ticket.

### F.6 — Reset everything (nuclear option)

If the install gets into a bad state:

1. Close the app.
2. Delete `%APPDATA%\com.blazetech.posnext.<slug>\` and `%LOCALAPPDATA%\com.blazetech.posnext.<slug>\`.
3. Relaunch — you'll be back at the login screen with an empty cache.

> ⚠️ This wipes any unsynced queued invoices that **only** exist in IndexedDB. If QZ Tray was running, the disk mirror (under `%APPDATA%\QZ\sandbox\...`) survives — re-launch with internet, log in, and click "Restore from disk" to re-queue them.

---

## Appendix — File checklist before shipping

Before you hand a `.exe` to a customer, confirm:

- [ ] `customers/<slug>.json` has the **correct** `siteUrl` (typo here = the till talks to the wrong customer's data — disaster).
- [ ] `version` field bumped from the previous release.
- [ ] `identifier` is **unique to this customer** (different `identifier` = different app data dir = won't collide with other customer installs on the same machine, useful for your own multi-customer test rig).
- [ ] `iconDir` exists and contains the customer's logo (if you customised it).
- [ ] You've smoke-tested with `yarn desktop:dev <slug>` against their site.
- [ ] You've test-installed the actual `.exe` in a clean Windows VM and run through [section D](#d-verifying-offline--printing).
- [ ] If using auto-update: `latest.json` and the signed `.exe` are uploaded to the customer's update endpoint **before** you tell them to update.
