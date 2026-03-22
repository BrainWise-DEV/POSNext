/**
 * SQLite Database Schema for POSNext Desktop
 *
 * Maps Frappe doctypes to local SQLite tables.
 * This schema is a superset of the IndexedDB schema in POS/src/utils/offline/db.js
 * to ensure full offline compatibility.
 */

const SCHEMA_SQL = `
-- ============================================================================
-- Schema Version Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- ============================================================================
-- Settings & Configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY,
    full_name TEXT,
    email TEXT,
    password_hash TEXT,
    language TEXT DEFAULT 'en',
    user_image TEXT,
    last_login TEXT,
    is_active INTEGER DEFAULT 1
);

-- ============================================================================
-- POS Configuration (from POS Profile + POS Settings doctypes)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pos_profiles (
    name TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    currency TEXT,
    warehouse TEXT,
    selling_price_list TEXT,
    customer TEXT,
    write_off_account TEXT,
    write_off_cost_center TEXT,
    write_off_limit REAL DEFAULT 0,
    print_format TEXT,
    auto_print INTEGER DEFAULT 0,
    country TEXT,
    ignore_pricing_rule INTEGER DEFAULT 0,
    disable_rounded_total INTEGER DEFAULT 0,
    disabled INTEGER DEFAULT 0,
    taxes_and_charges TEXT,
    branch TEXT,
    data_json TEXT
);

CREATE TABLE IF NOT EXISTS pos_profile_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pos_profile TEXT NOT NULL REFERENCES pos_profiles(name),
    user TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_users_user ON pos_profile_users(user);

CREATE TABLE IF NOT EXISTS pos_settings (
    name TEXT PRIMARY KEY,
    pos_profile TEXT REFERENCES pos_profiles(name),
    enabled INTEGER DEFAULT 1,
    tax_inclusive INTEGER DEFAULT 0,
    allow_user_to_edit_additional_discount INTEGER DEFAULT 0,
    allow_user_to_edit_item_discount INTEGER DEFAULT 1,
    allow_user_to_edit_rate INTEGER DEFAULT 0,
    use_percentage_discount INTEGER DEFAULT 0,
    max_discount_allowed REAL DEFAULT 0,
    allow_credit_sale INTEGER DEFAULT 0,
    allow_customer_credit_payment INTEGER DEFAULT 0,
    allow_return INTEGER DEFAULT 0,
    allow_partial_payment INTEGER DEFAULT 0,
    use_exact_amount INTEGER DEFAULT 0,
    decimal_precision TEXT DEFAULT '2',
    allow_negative_stock INTEGER DEFAULT 0,
    enable_sales_persons TEXT DEFAULT 'Disabled',
    silent_print INTEGER DEFAULT 0,
    allow_sales_order INTEGER DEFAULT 0,
    allow_select_sales_order INTEGER DEFAULT 0,
    create_only_sales_order INTEGER DEFAULT 0,
    enable_session_lock INTEGER DEFAULT 0,
    session_lock_timeout INTEGER DEFAULT 5,
    show_variants_as_items INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS companies (
    name TEXT PRIMARY KEY,
    company_name TEXT,
    default_currency TEXT,
    country TEXT,
    data_json TEXT
);

-- ============================================================================
-- System Settings (precision, number format)
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ============================================================================
-- Item Master Data
-- ============================================================================

CREATE TABLE IF NOT EXISTS items (
    item_code TEXT PRIMARY KEY,
    item_name TEXT,
    description TEXT,
    stock_uom TEXT,
    image TEXT,
    is_stock_item INTEGER DEFAULT 1,
    has_batch_no INTEGER DEFAULT 0,
    has_serial_no INTEGER DEFAULT 0,
    item_group TEXT,
    brand TEXT,
    has_variants INTEGER DEFAULT 0,
    variant_of TEXT,
    custom_company TEXT,
    disabled INTEGER DEFAULT 0,
    is_sales_item INTEGER DEFAULT 1,
    synced_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_group ON items(item_group);
CREATE INDEX IF NOT EXISTS idx_items_variant ON items(variant_of);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(item_name);

CREATE TABLE IF NOT EXISTS item_barcodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code TEXT NOT NULL REFERENCES items(item_code),
    barcode TEXT NOT NULL,
    barcode_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_barcodes_barcode ON item_barcodes(barcode);
CREATE INDEX IF NOT EXISTS idx_barcodes_item ON item_barcodes(item_code);

CREATE TABLE IF NOT EXISTS item_prices (
    price_list TEXT NOT NULL,
    item_code TEXT NOT NULL,
    price_list_rate REAL DEFAULT 0,
    currency TEXT,
    uom TEXT,
    PRIMARY KEY (price_list, item_code)
);
CREATE INDEX IF NOT EXISTS idx_prices_item ON item_prices(item_code);

CREATE TABLE IF NOT EXISTS item_groups (
    name TEXT PRIMARY KEY,
    is_group INTEGER DEFAULT 0,
    parent_item_group TEXT,
    lft INTEGER,
    rgt INTEGER,
    image TEXT
);
CREATE INDEX IF NOT EXISTS idx_groups_lft_rgt ON item_groups(lft, rgt);

CREATE TABLE IF NOT EXISTS item_uoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code TEXT NOT NULL,
    uom TEXT NOT NULL,
    conversion_factor REAL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_uoms_item ON item_uoms(item_code);

-- ============================================================================
-- Stock (Bin equivalent)
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock (
    item_code TEXT NOT NULL,
    warehouse TEXT NOT NULL,
    actual_qty REAL DEFAULT 0,
    reserved_qty REAL DEFAULT 0,
    synced_at TEXT,
    PRIMARY KEY (item_code, warehouse)
);

-- ============================================================================
-- Batch & Serial Number Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    item_code TEXT NOT NULL,
    warehouse TEXT,
    qty REAL DEFAULT 0,
    expiry_date TEXT,
    manufacturing_date TEXT,
    disabled INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_batches_item ON batches(item_code);

CREATE TABLE IF NOT EXISTS serial_numbers (
    serial_no TEXT PRIMARY KEY,
    item_code TEXT NOT NULL,
    warehouse TEXT,
    status TEXT DEFAULT 'Active'
);
CREATE INDEX IF NOT EXISTS idx_serials_item ON serial_numbers(item_code);
CREATE INDEX IF NOT EXISTS idx_serials_warehouse ON serial_numbers(warehouse);

-- ============================================================================
-- Customers
-- ============================================================================

CREATE TABLE IF NOT EXISTS customers (
    name TEXT PRIMARY KEY,
    customer_name TEXT,
    mobile_no TEXT,
    email_id TEXT,
    customer_group TEXT DEFAULT 'Individual',
    territory TEXT DEFAULT 'All Territories',
    customer_type TEXT DEFAULT 'Individual',
    loyalty_program TEXT,
    disabled INTEGER DEFAULT 0,
    synced_at TEXT,
    created_locally INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(customer_name);
CREATE INDEX IF NOT EXISTS idx_customers_mobile ON customers(mobile_no);

-- ============================================================================
-- Payment Methods
-- ============================================================================

CREATE TABLE IF NOT EXISTS payment_methods (
    mode_of_payment TEXT PRIMARY KEY,
    type TEXT DEFAULT 'Cash',
    is_wallet_payment INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pos_payment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pos_profile TEXT NOT NULL,
    mode_of_payment TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    allow_in_returns INTEGER DEFAULT 0,
    account TEXT,
    account_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_pos_payments_profile ON pos_payment_methods(pos_profile);

-- ============================================================================
-- Sales Persons
-- ============================================================================

CREATE TABLE IF NOT EXISTS sales_persons (
    name TEXT PRIMARY KEY,
    sales_person_name TEXT,
    commission_rate REAL DEFAULT 0,
    employee TEXT,
    enabled INTEGER DEFAULT 1
);

-- ============================================================================
-- Tax Templates
-- ============================================================================

CREATE TABLE IF NOT EXISTS tax_templates (
    name TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    is_default INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tax_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL REFERENCES tax_templates(name),
    account_head TEXT,
    charge_type TEXT,
    rate REAL DEFAULT 0,
    description TEXT,
    included_in_print_rate INTEGER DEFAULT 0,
    idx INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tax_rows_template ON tax_rows(template_name);

-- ============================================================================
-- Warehouses
-- ============================================================================

CREATE TABLE IF NOT EXISTS warehouses (
    name TEXT PRIMARY KEY,
    warehouse_name TEXT,
    company TEXT,
    is_group INTEGER DEFAULT 0,
    parent_warehouse TEXT
);

-- ============================================================================
-- POS Shifts
-- ============================================================================

CREATE TABLE IF NOT EXISTS pos_shifts (
    name TEXT PRIMARY KEY,
    user TEXT NOT NULL,
    pos_profile TEXT NOT NULL,
    company TEXT,
    status TEXT DEFAULT 'Open',
    period_start_date TEXT,
    posting_date TEXT,
    posting_time TEXT,
    closing_shift TEXT,
    docstatus INTEGER DEFAULT 1,
    synced_to_server INTEGER DEFAULT 0,
    server_name TEXT,
    data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_shifts_user ON pos_shifts(user, status);

CREATE TABLE IF NOT EXISTS pos_shift_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_name TEXT NOT NULL REFERENCES pos_shifts(name),
    mode_of_payment TEXT NOT NULL,
    amount REAL DEFAULT 0,
    detail_type TEXT DEFAULT 'opening'
);
CREATE INDEX IF NOT EXISTS idx_shift_details_shift ON pos_shift_details(shift_name);

-- ============================================================================
-- Invoices (Sales Invoices)
-- ============================================================================

CREATE TABLE IF NOT EXISTS invoices (
    name TEXT PRIMARY KEY,
    offline_id TEXT UNIQUE,
    customer TEXT,
    customer_name TEXT,
    pos_profile TEXT,
    company TEXT,
    currency TEXT,
    posting_date TEXT,
    posting_time TEXT,
    is_pos INTEGER DEFAULT 1,
    is_return INTEGER DEFAULT 0,
    return_against TEXT,
    update_stock INTEGER DEFAULT 1,
    total REAL DEFAULT 0,
    net_total REAL DEFAULT 0,
    grand_total REAL DEFAULT 0,
    rounded_total REAL,
    rounding_adjustment REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    additional_discount_percentage REAL DEFAULT 0,
    write_off_amount REAL DEFAULT 0,
    paid_amount REAL DEFAULT 0,
    outstanding_amount REAL DEFAULT 0,
    change_amount REAL DEFAULT 0,
    docstatus INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Draft',
    sync_status TEXT DEFAULT 'local',
    server_name TEXT,
    sync_error TEXT,
    synced_at TEXT,
    created_at TEXT,
    coupon_code TEXT,
    pos_opening_shift TEXT,
    branch TEXT,
    taxes_and_charges TEXT,
    data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(sync_status);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(posting_date);
CREATE INDEX IF NOT EXISTS idx_invoices_shift ON invoices(pos_opening_shift);
CREATE INDEX IF NOT EXISTS idx_invoices_docstatus ON invoices(docstatus);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_name TEXT NOT NULL REFERENCES invoices(name),
    item_code TEXT NOT NULL,
    item_name TEXT,
    qty REAL DEFAULT 0,
    rate REAL DEFAULT 0,
    price_list_rate REAL DEFAULT 0,
    discount_percentage REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    net_amount REAL DEFAULT 0,
    uom TEXT,
    stock_uom TEXT,
    conversion_factor REAL DEFAULT 1,
    warehouse TEXT,
    batch_no TEXT,
    serial_no TEXT,
    is_rate_manually_edited INTEGER DEFAULT 0,
    original_rate REAL,
    pricing_rules TEXT,
    idx INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inv_items_invoice ON invoice_items(invoice_name);

CREATE TABLE IF NOT EXISTS invoice_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_name TEXT NOT NULL REFERENCES invoices(name),
    mode_of_payment TEXT NOT NULL,
    amount REAL DEFAULT 0,
    account TEXT,
    type TEXT,
    idx INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inv_payments_invoice ON invoice_payments(invoice_name);

CREATE TABLE IF NOT EXISTS invoice_taxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_name TEXT NOT NULL REFERENCES invoices(name),
    account_head TEXT,
    charge_type TEXT,
    rate REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    total REAL DEFAULT 0,
    description TEXT,
    included_in_print_rate INTEGER DEFAULT 0,
    idx INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inv_taxes_invoice ON invoice_taxes(invoice_name);

-- ============================================================================
-- Offers / Promotions
-- ============================================================================

CREATE TABLE IF NOT EXISTS offers (
    name TEXT PRIMARY KEY,
    title TEXT,
    pos_profile TEXT,
    apply_on TEXT,
    applicable_for TEXT,
    selling INTEGER DEFAULT 1,
    valid_from TEXT,
    valid_upto TEXT,
    disabled INTEGER DEFAULT 0,
    data_json TEXT
);

CREATE TABLE IF NOT EXISTS coupons (
    name TEXT PRIMARY KEY,
    coupon_code TEXT UNIQUE,
    pricing_rule TEXT,
    maximum_use INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0,
    valid_from TEXT,
    valid_upto TEXT,
    data_json TEXT
);

-- ============================================================================
-- Wallet
-- ============================================================================

CREATE TABLE IF NOT EXISTS wallets (
    name TEXT PRIMARY KEY,
    customer TEXT NOT NULL,
    balance REAL DEFAULT 0,
    data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_wallets_customer ON wallets(customer);

-- ============================================================================
-- Translations
-- ============================================================================

CREATE TABLE IF NOT EXISTS translations (
    locale TEXT PRIMARY KEY,
    data_json TEXT,
    synced_at TEXT
);

-- ============================================================================
-- Sync Log
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_name TEXT,
    direction TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    synced_at TEXT NOT NULL,
    data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_log_type ON sync_log(entity_type, status);

-- ============================================================================
-- Naming Series (local invoice numbering)
-- ============================================================================

CREATE TABLE IF NOT EXISTS naming_series (
    prefix TEXT PRIMARY KEY,
    current_value INTEGER DEFAULT 0
);

-- ============================================================================
-- Full-Text Search for Items
-- ============================================================================

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    item_code,
    item_name,
    description,
    content=items,
    content_rowid=rowid
);

-- Triggers to keep FTS in sync with items table
CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, item_code, item_name, description)
    VALUES (new.rowid, new.item_code, new.item_name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, item_code, item_name, description)
    VALUES ('delete', old.rowid, old.item_code, old.item_name, old.description);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, item_code, item_name, description)
    VALUES ('delete', old.rowid, old.item_code, old.item_name, old.description);
    INSERT INTO items_fts(rowid, item_code, item_name, description)
    VALUES (new.rowid, new.item_code, new.item_name, new.description);
END;
`

/**
 * Initialize the database schema.
 * @param {import('better-sqlite3').Database} db
 */
function initializeSchema(db) {
	db.exec(SCHEMA_SQL)

	// Insert default settings if not present
	const insertSetting = db.prepare(
		"INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)"
	)

	const defaults = db.transaction(() => {
		insertSetting.run("current_user", "Administrator")
		insertSetting.run("terminal_id", require("crypto").randomUUID())
		insertSetting.run("terminal_short_id", require("crypto").randomUUID().slice(0, 6).toUpperCase())
		insertSetting.run("setup_complete", "0")
		insertSetting.run("erpnext_url", "")
		insertSetting.run("api_key", "")
		insertSetting.run("api_secret", "")
		insertSetting.run("last_sync", "")

		// Default system settings
		db.prepare("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)").run("currency_precision", "2")
		db.prepare("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)").run("float_precision", "3")
		db.prepare("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)").run("rounding_method", "Commercial Rounding")
		db.prepare("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)").run("number_format", "#,###.##")

		// Default naming series
		db.prepare("INSERT OR IGNORE INTO naming_series (prefix, current_value) VALUES (?, ?)").run("POS-DESK", 0)
	})

	defaults()
	console.log("[DB] Schema initialized with defaults")
}

module.exports = { initializeSchema, SCHEMA_SQL }
