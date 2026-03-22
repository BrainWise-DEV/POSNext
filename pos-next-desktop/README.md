# POSNext Desktop — Fully Offline Electron POS

POSNext Desktop is a standalone Windows/Mac/Linux application that wraps the existing POSNext Vue 3 frontend with a local Express.js API server and SQLite database, enabling **fully offline POS operations** with bidirectional sync to ERPNext when connectivity is available.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Development](#development)
- [Building the .exe Installer](#building-the-exe-installer)
- [First-Time Setup (Data Provisioning)](#first-time-setup-data-provisioning)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [API Compatibility Layer](#api-compatibility-layer)
- [Database Schema](#database-schema)
- [Sync Engine](#sync-engine)
- [Printing](#printing)
- [Multi-Terminal Support](#multi-terminal-support)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Overview

| Feature | Web Version (POSNext) | Desktop Version (This) |
|---------|----------------------|----------------------|
| Internet required | Yes (Frappe server) | No (fully offline after setup) |
| Database | MariaDB via Frappe ORM | SQLite (local file) |
| API server | Python/Frappe | Express.js (embedded in Electron) |
| Distribution | Web browser | .exe installer (Windows), .dmg (Mac), AppImage (Linux) |
| Sync | Real-time via Socket.IO | Bidirectional batch sync to ERPNext |
| Printing | QZ Tray (Java-based) | Native Electron printing (no Java needed) |
| Barcode scanning | Works | Works (keyboard input — no change needed) |
| Frontend code changes | — | Zero (same Vue 3 components) |

### Why Desktop?

- **Unreliable internet**: Retail locations with poor connectivity
- **Standalone terminals**: Dedicated POS machines without a browser
- **Speed**: No network latency for every operation
- **Resilience**: Power/network outages don't stop sales
- **Distribution**: Simple .exe installer for IT teams

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Electron App                     │
│                                                  │
│  ┌──────────────┐     ┌──────────────────────┐  │
│  │  Main Process │     │   Renderer Process    │  │
│  │               │     │                      │  │
│  │  Express.js ──┼─────┤──► Vue 3 Frontend    │  │
│  │  (port 18420) │ HTTP│  (same POS/ code)    │  │
│  │               │     │                      │  │
│  │  SQLite DB    │     │  Pinia Stores        │  │
│  │  (pos_next.db)│     │  50+ Components      │  │
│  │               │     │  30+ Composables     │  │
│  │  Sync Engine ─┼─────┤──► ERPNext (online)  │  │
│  │  (pull/push)  │     │                      │  │
│  │               │     │                      │  │
│  │  Native Print │     │                      │  │
│  └──────────────┘     └──────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**Key insight**: The Express.js server inside Electron mimics the exact Frappe API contract (`POST /api/method/{dotted.path}` → `{message: result}`), so the Vue frontend works with **zero code changes**.

---

## Prerequisites

- **Node.js** 18+ (LTS recommended)
- **npm** 9+ or **yarn** 1.22+
- **Python 3.10+** and **Frappe Bench** (for the web version, used as sync target)
- **Windows 10+** / **macOS 12+** / **Ubuntu 20.04+** (for running the desktop app)

### For building the .exe installer:

- **Windows**: No extra requirements
- **Cross-platform builds**: Use `electron-builder` with Wine (for building Windows targets on Linux/Mac)

---

## Installation & Setup

```bash
# 1. Navigate to the desktop project
cd /path/to/frappe-bench/apps/pos_next/pos-next-desktop

# 2. Install dependencies
npm install

# 3. Build the Vue frontend for Electron
npm run build:frontend

# 4. Run in development mode
npm run dev
```

---

## Development

### Dev Mode

```bash
npm run dev
```

This starts Electron with:
- Express API server on `http://127.0.0.1:18420`
- DevTools open for debugging
- Hot reload for the main process (via nodemon if configured)

### Frontend Development

The frontend source lives in `../POS/src/`. When you modify Vue components:

```bash
# Rebuild the frontend
npm run build:frontend
```

Or use the Vite dev server for hot-reload during frontend development:

```bash
cd ../POS
npx vite --config ../pos-next-desktop/vite.config.electron.js
```

### Debugging

- **Main process**: Console output goes to terminal
- **Renderer process**: DevTools open automatically in dev mode
- **API calls**: All requests logged to console in dev mode with `[API]` prefix
- **Database**: SQLite file at `%APPDATA%/POSNext/data/pos_next.db` (Windows) or `~/.config/POSNext/data/pos_next.db` (Linux)

---

## Building the .exe Installer

### Windows

```bash
# Build frontend + package as .exe
npm run build

# Or step by step:
npm run build:frontend    # Build Vue app → renderer/
npm run build:win         # Package Electron → dist/
```

Output: `dist/POSNext Setup X.X.X.exe`

### macOS

```bash
npx electron-builder --mac
```

### Linux

```bash
npx electron-builder --linux
```

### Build Configuration

The build is configured in `package.json` under the `"build"` key and uses `electron-builder`. Key settings:

| Setting | Value | Purpose |
|---------|-------|---------|
| `appId` | `com.posnext.desktop` | Unique app identifier |
| `productName` | `POSNext` | Display name |
| `nsis.oneClick` | `false` | Shows install wizard |
| `nsis.perMachine` | `true` | Installs for all users |
| `nsis.allowToChangeInstallationDirectory` | `true` | User picks install path |

---

## First-Time Setup (Data Provisioning)

When the app launches for the first time, a setup wizard guides the user through:

1. **Enter ERPNext URL**: e.g., `https://erp.company.com`
2. **Enter API credentials**: API Key + API Secret (generated in ERPNext User settings)
3. **Select POS Profile**: Choose which POS Profile to use
4. **Download master data**: Items, prices, customers, stock — all synced to local SQLite

The initial sync downloads data in this order (respecting dependencies):

```
System Settings → Companies → POS Profiles → Payment Methods →
Tax Templates → Warehouses → Item Groups → Items (paginated) →
Item Prices → Stock (Bin) → Customers → Sales Persons → Users
```

For a catalog of ~65,000 items, the initial sync takes approximately 3-5 minutes.

### Generating API Credentials in ERPNext

1. Go to **User** → select the POS user
2. Scroll to **API Access** section
3. Click **Generate Keys**
4. Copy the **API Key** and **API Secret** (shown only once)

---

## How It Works

### Offline POS Flow

```
Open Shift → Browse Items → Add to Cart → Submit Invoice → Close Shift
    ↓             ↓              ↓              ↓              ↓
  SQLite        SQLite        In-memory      SQLite         SQLite
  pos_shifts     items        (Pinia)       invoices       pos_shifts
```

Every operation writes to local SQLite. No network calls needed.

### Online Sync Flow

```
┌─────────────┐              ┌──────────────┐
│  Desktop    │    Push      │  ERPNext     │
│  SQLite     │──────────►   │  Server      │
│             │  invoices    │              │
│             │  customers   │              │
│             │  shifts      │              │
│             │              │              │
│             │    Pull      │              │
│             │◄──────────   │              │
│             │  items       │              │
│             │  prices      │              │
│             │  stock       │              │
│             │  customers   │              │
└─────────────┘              └──────────────┘
```

- **Push**: Local invoices → ERPNext (with `offline_id` UUID for deduplication)
- **Pull**: ERPNext master data → SQLite (using `modified` timestamp for delta sync)
- **Schedule**: Auto-sync every 5 minutes when online
- **Manual**: User can trigger sync from the app

### Conflict Resolution

| Data Type | Strategy | Rationale |
|-----------|----------|-----------|
| Items, Prices, Stock | Server wins | Master data managed centrally in ERPNext |
| Customers (existing) | Server wins | May be edited from multiple terminals |
| Customers (new) | Push to server | Created locally, get server-generated name |
| Invoices | No conflict | Each terminal has unique naming series + UUID |
| Shifts | No conflict | Per-terminal, per-user |

---

## Project Structure

```
pos-next-desktop/
├── package.json                          # Dependencies, scripts, build config
├── vite.config.electron.js               # Vite build config for Electron
├── .gitignore
│
├── electron/
│   ├── main.js                           # Electron entry point
│   │                                      # - Creates BrowserWindow
│   │                                      # - Starts Express server
│   │                                      # - Sets up IPC handlers
│   │                                      # - Initializes database
│   │
│   ├── preload.js                        # Secure IPC bridge
│   │                                      # - Exposes printer, sync, app APIs
│   │                                      # - window.electronAPI namespace
│   │
│   ├── common_site_config_stub.js        # Replaces Frappe's socket config
│   │
│   ├── server/
│   │   ├── index.js                      # Express app setup
│   │   │                                  # - 82 API routes registered
│   │   │                                  # - Frappe auth compatibility
│   │   │                                  # - Static file serving
│   │   │
│   │   ├── frappe-compat.js              # Response format wrapper
│   │   │                                  # - frappeResponse(handler)
│   │   │                                  # - FrappeError class
│   │   │                                  # - registerMethod(router, path, fn)
│   │   │
│   │   ├── db/
│   │   │   ├── connection.js             # SQLite singleton (better-sqlite3)
│   │   │   │                              # - WAL mode, 64MB cache
│   │   │   │                              # - Stores in %APPDATA%/POSNext/
│   │   │   │
│   │   │   ├── schema.js                 # 30+ tables, FTS5, triggers
│   │   │   │                              # - Items, invoices, stock, shifts
│   │   │   │                              # - Full-text search index
│   │   │   │                              # - Auto-sync FTS triggers
│   │   │   │
│   │   │   └── migrations.js             # Schema version tracking
│   │   │
│   │   ├── routes/                       # API handlers (1:1 with Python)
│   │   │   ├── bootstrap.js              # get_initial_data
│   │   │   ├── items.js                  # 12 endpoints: search, barcode, stock
│   │   │   ├── invoices.js               # 18 endpoints: CRUD, submit, return
│   │   │   ├── customers.js              # 3 endpoints: CRUD + search
│   │   │   ├── shifts.js                 # 5 endpoints: open/close/reconcile
│   │   │   ├── pos_profile.js            # 14 endpoints: profiles, settings
│   │   │   ├── offers.js                 # 3 endpoints: offers, coupons
│   │   │   ├── wallet.js                 # 6 endpoints (online-preferred)
│   │   │   ├── partial_payments.js       # 6 endpoints: payment tracking
│   │   │   ├── credit_sales.js           # 5 endpoints (online-preferred)
│   │   │   ├── localization.js           # 4 endpoints: translations
│   │   │   ├── auth.js                   # 1 endpoint: password verify
│   │   │   ├── qz.js                     # 4 endpoints (stubs, native print)
│   │   │   └── utilities.js              # 1 endpoint: CSRF token
│   │   │
│   │   └── sync/
│   │       ├── engine.js                 # Sync coordinator
│   │       ├── pull.js                   # ERPNext → SQLite (paginated)
│   │       ├── push.js                   # SQLite → ERPNext (with dedup)
│   │       └── scheduler.js              # Auto-sync every 5 min
│   │
│   └── printing/
│       └── printer.js                    # Native Electron printing
│                                          # - Receipt HTML generation
│                                          # - Direct printer access
│
├── renderer/                             # (generated) Built Vue frontend
└── dist/                                 # (generated) Packaged installer
```

---

## API Compatibility Layer

The core innovation is the **Frappe API compatibility layer** in `frappe-compat.js`. It wraps Express handlers to produce the exact JSON format that `frappe-ui`'s `call()` function expects:

### Request Contract

```
POST /api/method/pos_next.api.items.get_items
Content-Type: application/json

{"search_term": "laptop", "page_length": 20}
```

### Success Response

```json
{
  "message": [
    {"item_code": "ITEM-001", "item_name": "Laptop", ...}
  ]
}
```

### Error Response

```json
{
  "exc_type": "ValidationError",
  "_error_message": "Item not found",
  "_server_messages": "[{\"message\": \"Item not found\"}]"
}
```

### Route Registration

Each Python API function maps to a JavaScript handler:

```javascript
// Python: @frappe.whitelist() def get_items(...)
// JavaScript equivalent:
registerMethod(app, "pos_next.api.items.get_items", async (params) => {
    const db = getDatabase()
    return db.prepare("SELECT * FROM items WHERE ...").all(...)
})
```

### Complete Endpoint Coverage

| Module | Endpoints | Implementation Status |
|--------|-----------|----------------------|
| `bootstrap` | 1 | Full |
| `auth` | 1 | Full |
| `items` | 12 | Full (FTS5 search, barcode, stock) |
| `invoices` | 18 | Full (submit, return, stock update) |
| `customers` | 3 | Full (CRUD + local creation) |
| `pos_profile` | 14 | Full (read), stubs (CRUD - online only) |
| `shifts` | 5 | Full (open, close, reconcile) |
| `offers` | 3 | Working (simplified rules engine) |
| `wallet` | 6 | Stubs (online-preferred) |
| `partial_payments` | 6 | Working (local tracking) |
| `credit_sales` | 5 | Stubs (online-preferred) |
| `localization` | 4 | Full (cached translations) |
| `qz` | 4 | Stubs (replaced by native printing) |
| `utilities` | 1 | Full (static CSRF) |
| **Total** | **82** | |

---

## Database Schema

### Storage

- **Engine**: SQLite via `better-sqlite3` (synchronous, fast, battle-tested)
- **Location**: `%APPDATA%/POSNext/data/pos_next.db` (Windows)
- **Size**: ~50-100MB for a 65K item catalog
- **Mode**: WAL (Write-Ahead Logging) for concurrent read performance

### Key Tables

| Table | Records (typical) | Purpose |
|-------|-------------------|---------|
| `items` | 65,000 | Product catalog |
| `item_barcodes` | 70,000 | Barcode → item lookup |
| `item_prices` | 65,000 | Price list rates |
| `stock` | 65,000 | Warehouse quantities |
| `customers` | 5,000 | Customer master |
| `invoices` | 10,000+ | Sales invoices (local) |
| `invoice_items` | 30,000+ | Line items |
| `invoice_payments` | 10,000+ | Payment details |
| `pos_shifts` | 500+ | Shift history |

### Full-Text Search

Items are indexed with SQLite FTS5 for instant search:

```sql
CREATE VIRTUAL TABLE items_fts USING fts5(item_code, item_name, description, content=items);
```

Auto-maintained via triggers on INSERT/UPDATE/DELETE.

### Schema Migrations

Version-tracked via `schema_version` table. Each app update runs pending migrations:

```javascript
const MIGRATIONS = [
    { version: 1, description: "Initial schema", up: (db) => { ... } },
    { version: 2, description: "Add branch to invoices", up: (db) => { ... } },
]
```

---

## Sync Engine

### Sync Modes

| Mode | Trigger | Direction | What |
|------|---------|-----------|------|
| Initial Provisioning | First launch | Pull only | All master data |
| Scheduled Sync | Every 5 minutes | Both | Delta updates + invoice push |
| Manual Sync | User clicks sync | Both | Same as scheduled |

### Push (Desktop → ERPNext)

Invoices are pushed using the existing `pos_next.api.invoices.submit_invoice` endpoint, which already supports `offline_id`-based deduplication. This means:

- Duplicate pushes are safe (idempotent)
- The same invoice can never be created twice on the server
- Failed pushes are retried on next sync cycle

### Pull (ERPNext → Desktop)

Uses `modified` timestamp tracking for efficient delta sync:

```
For each entity type:
  1. Read last_sync_timestamp from settings
  2. Call ERPNext API with modified > last_sync filter
  3. UPSERT changed records into SQLite
  4. Update last_sync_timestamp
```

### Authentication

Uses Frappe API key/secret authentication:

```
Authorization: token {api_key}:{api_secret}
```

No session cookies or CSRF tokens needed for server-to-server communication.

---

## Printing

### Native Electron Printing

Replaces the QZ Tray browser-based printing with Electron's built-in printing API:

- **No Java dependency** (QZ Tray requires Java)
- **Direct printer access** via `webContents.print()`
- **ESC/POS support** via `electron-pos-printer` package
- **Receipt templates** with customizable HTML

### Printer Setup

```javascript
// Available via IPC from renderer
window.electronAPI.getPrinters()      // List printers
window.electronAPI.printReceipt(html) // Print receipt
```

### Barcode Scanner

Works out of the box — barcode scanners present as keyboard input devices. The existing `searchByBarcode` flow in the Vue frontend handles keyboard input without any changes.

---

## Multi-Terminal Support

Each desktop installation gets a unique `terminal_id` (UUID) stored in the local settings table. This enables:

- **Unique invoice naming**: `POS-{TERMINAL_SHORT_ID}-00001` (no collisions between terminals)
- **Shift isolation**: Each terminal maintains its own shift lifecycle
- **Sync tracking**: Terminal ID sent with push requests for audit trail
- **Multiple terminals**: All sync to the same ERPNext instance without conflicts

---

## Configuration

### Settings Table

All configuration is stored in the `settings` table (key-value):

| Key | Example Value | Purpose |
|-----|--------------|---------|
| `erpnext_url` | `https://erp.company.com` | ERPNext server URL |
| `api_key` | `abc123...` | Frappe API key |
| `api_secret` | `xyz789...` | Frappe API secret |
| `terminal_id` | `a1b2c3d4-...` | Unique terminal UUID |
| `terminal_short_id` | `A1B2C3` | Short ID for invoice naming |
| `current_user` | `cashier@company.com` | Logged-in user |
| `setup_complete` | `1` | Whether initial sync is done |
| `last_sync` | `2026-03-22T10:30:00Z` | Last successful sync timestamp |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NODE_ENV` | `production` | Set to `development` for dev mode |
| `POS_NEXT_ENABLE_SOURCEMAP` | `false` | Enable source maps in build |

---

## Troubleshooting

### App won't start

- Check if another instance is running (port 18420 conflict)
- Delete the database file and restart for a fresh setup:
  - Windows: `%APPDATA%/POSNext/data/pos_next.db`
  - Linux: `~/.config/POSNext/data/pos_next.db`

### Sync fails

- Verify ERPNext URL is accessible from the machine
- Check API key/secret are valid (regenerate if needed)
- Check the `sync_log` table for detailed error messages
- Ensure the API user has POS permissions in ERPNext

### Invoices not appearing in ERPNext

- Check `invoices` table: `sync_status` should be `synced`
- If `failed`, check `sync_error` column for details
- Trigger manual sync and watch console output

### Items not found / barcode not scanning

- Ensure initial sync completed successfully
- Check `items` and `item_barcodes` tables have data
- Run manual sync to pull latest items

### Printing issues

- Run `window.electronAPI.getPrinters()` in DevTools to verify printer is detected
- Ensure printer drivers are installed
- Try printing a test page from Windows first

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and test locally with `npm run dev`
4. Submit a Pull Request

### Code Style

- CommonJS modules in `electron/` (Node.js main process)
- ESM in `vite.config.electron.js` and frontend code
- No TypeScript in the Electron layer (keep it simple)

### Testing

```bash
# Run frontend tests (from POS/ directory)
cd ../POS && npm test

# Manual testing checklist:
# 1. Open shift → browse items → add to cart → submit invoice → close shift
# 2. Barcode scan → item added to cart
# 3. Create invoice offline → sync → verify in ERPNext
# 4. Print receipt
```
