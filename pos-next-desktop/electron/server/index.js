const express = require("express")
const cors = require("cors")
const path = require("node:path")
const { registerMethod } = require("./frappe-compat")

// Route handlers
const bootstrapRoutes = require("./routes/bootstrap")
const itemsRoutes = require("./routes/items")
const invoicesRoutes = require("./routes/invoices")
const customersRoutes = require("./routes/customers")
const posProfileRoutes = require("./routes/pos_profile")
const shiftsRoutes = require("./routes/shifts")
const offersRoutes = require("./routes/offers")
const walletRoutes = require("./routes/wallet")
const partialPaymentsRoutes = require("./routes/partial_payments")
const creditSalesRoutes = require("./routes/credit_sales")
const localizationRoutes = require("./routes/localization")
const utilitiesRoutes = require("./routes/utilities")
const authRoutes = require("./routes/auth")
const qzRoutes = require("./routes/qz")

let server = null

/**
 * Create and configure the Express application.
 */
function createApp() {
	const app = express()

	// Middleware
	app.use(cors())
	app.use(express.json({ limit: "50mb" }))
	app.use(express.urlencoded({ extended: true, limit: "50mb" }))

	// Request logging in dev mode
	if (process.env.NODE_ENV === "development") {
		app.use((req, _res, next) => {
			if (req.url.startsWith("/api/")) {
				console.log(`[API] ${req.method} ${req.url}`)
			}
			next()
		})
	}

	// =========================================================================
	// Register all API routes (82 endpoints mapped from Python backend)
	// =========================================================================

	const r = (method, handler) => registerMethod(app, method, handler)

	// --- Bootstrap (1 endpoint) ---
	r("pos_next.api.bootstrap.get_initial_data", bootstrapRoutes.getInitialData)

	// --- Auth (1 endpoint) ---
	r("pos_next.api.auth.verify_session_password", authRoutes.verifySessionPassword)

	// --- Items (12 endpoints) ---
	r("pos_next.api.items.get_items", itemsRoutes.getItems)
	r("pos_next.api.items.get_items_bulk", itemsRoutes.getItemsBulk)
	r("pos_next.api.items.get_items_count", itemsRoutes.getItemsCount)
	r("pos_next.api.items.get_item_details", itemsRoutes.getItemDetails)
	r("pos_next.api.items.get_item_groups", itemsRoutes.getItemGroups)
	r("pos_next.api.items.search_by_barcode", itemsRoutes.searchByBarcode)
	r("pos_next.api.items.get_item_stock", itemsRoutes.getItemStock)
	r("pos_next.api.items.get_batch_serial_details", itemsRoutes.getBatchSerialDetails)
	r("pos_next.api.items.get_item_variants", itemsRoutes.getItemVariants)
	r("pos_next.api.items.get_stock_quantities", itemsRoutes.getStockQuantities)
	r("pos_next.api.items.get_item_warehouse_availability", itemsRoutes.getItemWarehouseAvailability)
	r("pos_next.api.items.get_product_bundle_availability", itemsRoutes.getProductBundleAvailability)

	// --- Invoices (18 endpoints) ---
	r("pos_next.api.invoices.update_invoice", invoicesRoutes.updateInvoice)
	r("pos_next.api.invoices.submit_invoice", invoicesRoutes.submitInvoice)
	r("pos_next.api.invoices.get_invoice", invoicesRoutes.getInvoice)
	r("pos_next.api.invoices.get_invoices", invoicesRoutes.getInvoices)
	r("pos_next.api.invoices.get_draft_invoices", invoicesRoutes.getDraftInvoices)
	r("pos_next.api.invoices.delete_invoice", invoicesRoutes.deleteInvoice)
	r("pos_next.api.invoices.cleanup_old_drafts", invoicesRoutes.cleanupOldDrafts)
	r("pos_next.api.invoices.get_returnable_invoices", invoicesRoutes.getReturnableInvoices)
	r("pos_next.api.invoices.search_invoice_by_number", invoicesRoutes.searchInvoiceByNumber)
	r("pos_next.api.invoices.check_invoice_return_validity", invoicesRoutes.checkInvoiceReturnValidity)
	r("pos_next.api.invoices.get_invoice_for_return", invoicesRoutes.getInvoiceForReturn)
	r("pos_next.api.invoices.prepare_return_invoice", invoicesRoutes.prepareReturnInvoice)
	r("pos_next.api.invoices.search_invoices_for_return", invoicesRoutes.searchInvoicesForReturn)
	r("pos_next.api.invoices.apply_offers", invoicesRoutes.applyOffers)
	r("pos_next.api.invoices.validate_cart_items", invoicesRoutes.validateCartItems)
	r("pos_next.api.invoices.validate_return_items", invoicesRoutes.validateReturnItems)
	r("pos_next.api.invoices.check_offline_invoice_synced", invoicesRoutes.checkOfflineInvoiceSynced)
	r("pos_next.api.invoices.get_batch_serial_data_for_items", invoicesRoutes.getBatchSerialDataForItems)

	// --- Customers (3 endpoints) ---
	r("pos_next.api.customers.get_customers", customersRoutes.getCustomers)
	r("pos_next.api.customers.create_customer", customersRoutes.createCustomer)
	r("pos_next.api.customers.get_customer_details", customersRoutes.getCustomerDetails)

	// --- POS Profile (14 endpoints) ---
	r("pos_next.api.pos_profile.get_pos_profiles", posProfileRoutes.getPosProfiles)
	r("pos_next.api.pos_profile.get_pos_profile_data", posProfileRoutes.getPosProfileData)
	r("pos_next.api.pos_profile.get_pos_settings", posProfileRoutes.getPosSettings)
	r("pos_next.api.pos_profile.get_payment_methods", posProfileRoutes.getPaymentMethods)
	r("pos_next.api.pos_profile.get_taxes", posProfileRoutes.getTaxes)
	r("pos_next.api.pos_profile.get_warehouses", posProfileRoutes.getWarehouses)
	r("pos_next.api.pos_profile.get_default_customer", posProfileRoutes.getDefaultCustomer)
	r("pos_next.api.pos_profile.update_warehouse", posProfileRoutes.updateWarehouse)
	r("pos_next.api.pos_profile.get_wallet_payment_flags", posProfileRoutes.getWalletPaymentFlags)
	r("pos_next.api.pos_profile.get_sales_persons", posProfileRoutes.getSalesPersons)
	r("pos_next.api.pos_profile.get_create_pos_profile", posProfileRoutes.getCreatePosProfile)
	r("pos_next.api.pos_profile.create_pos_profile", posProfileRoutes.createPosProfile)
	r("pos_next.api.pos_profile.update_pos_profile", posProfileRoutes.updatePosProfile)
	r("pos_next.api.pos_profile.delete_pos_profile", posProfileRoutes.deletePosProfile)

	// --- Shifts (5 endpoints) ---
	r("pos_next.api.shifts.get_opening_dialog_data", shiftsRoutes.getOpeningDialogData)
	r("pos_next.api.shifts.check_opening_shift", shiftsRoutes.checkOpeningShift)
	r("pos_next.api.shifts.create_opening_shift", shiftsRoutes.createOpeningShift)
	r("pos_next.api.shifts.get_closing_shift_data", shiftsRoutes.getClosingShiftData)
	r("pos_next.api.shifts.submit_closing_shift", shiftsRoutes.submitClosingShift)

	// --- Offers (3 endpoints) ---
	r("pos_next.api.offers.get_offers", offersRoutes.getOffers)
	r("pos_next.api.offers.get_active_coupons", offersRoutes.getActiveCoupons)
	r("pos_next.api.offers.validate_coupon", offersRoutes.validateCoupon)

	// --- Wallet (6 endpoints) ---
	r("pos_next.api.wallet.get_customer_wallet_balance", walletRoutes.getCustomerWalletBalance)
	r("pos_next.api.wallet.get_customer_wallet", walletRoutes.getCustomerWallet)
	r("pos_next.api.wallet.get_or_create_wallet", walletRoutes.getOrCreateWallet)
	r("pos_next.api.wallet.get_wallet_payment_methods", walletRoutes.getWalletPaymentMethods)
	r("pos_next.api.wallet.get_wallet_info", walletRoutes.getWalletInfo)
	r("pos_next.api.wallet.create_manual_wallet_credit", walletRoutes.createManualWalletCredit)

	// --- Partial Payments (6 endpoints) ---
	r("pos_next.api.partial_payments.get_partial_paid_invoices", partialPaymentsRoutes.getPartialPaidInvoices)
	r("pos_next.api.partial_payments.get_unpaid_invoices", partialPaymentsRoutes.getUnpaidInvoices)
	r("pos_next.api.partial_payments.get_partial_payment_details", partialPaymentsRoutes.getPartialPaymentDetails)
	r("pos_next.api.partial_payments.add_payment_to_partial_invoice", partialPaymentsRoutes.addPaymentToPartialInvoice)
	r("pos_next.api.partial_payments.get_partial_payment_summary", partialPaymentsRoutes.getPartialPaymentSummary)
	r("pos_next.api.partial_payments.get_unpaid_summary", partialPaymentsRoutes.getUnpaidSummary)

	// --- Credit Sales (5 endpoints) ---
	r("pos_next.api.credit_sales.get_customer_balance", creditSalesRoutes.getCustomerBalance)
	r("pos_next.api.credit_sales.get_available_credit", creditSalesRoutes.getAvailableCredit)
	r("pos_next.api.credit_sales.redeem_customer_credit", creditSalesRoutes.redeemCustomerCredit)
	r("pos_next.api.credit_sales.cancel_credit_journal_entries", creditSalesRoutes.cancelCreditJournalEntries)
	r("pos_next.api.credit_sales.get_credit_sale_summary", creditSalesRoutes.getCreditSaleSummary)

	// --- QZ Tray / Printing (4 endpoints) ---
	r("pos_next.api.qz.get_certificate", qzRoutes.getCertificate)
	r("pos_next.api.qz.get_certificate_download", qzRoutes.getCertificateDownload)
	r("pos_next.api.qz.sign_message", qzRoutes.signMessage)
	r("pos_next.api.qz.setup_qz_certificate", qzRoutes.setupQzCertificate)

	// --- Localization (4 endpoints) ---
	r("pos_next.api.localization.get_app_translations", localizationRoutes.getAppTranslations)
	r("pos_next.api.localization.get_user_language", localizationRoutes.getUserLanguage)
	r("pos_next.api.localization.get_allowed_locales", localizationRoutes.getAllowedLocales)
	r("pos_next.api.localization.change_user_language", localizationRoutes.changeUserLanguage)

	// --- Utilities (1 endpoint) ---
	r("pos_next.api.utilities.get_csrf_token", utilitiesRoutes.getCsrfToken)

	// =========================================================================
	// Static file serving (Vue frontend in production)
	// =========================================================================

	const rendererPath = path.join(__dirname, "../renderer")
	app.use(express.static(rendererPath))

	// SPA fallback: serve index.html for any unmatched GET requests
	app.get("*", (_req, res) => {
		res.sendFile(path.join(rendererPath, "index.html"))
	})

	// =========================================================================
	// Frappe session endpoints (compatibility stubs)
	// =========================================================================

	// The frontend checks /api/method/frappe.auth.get_logged_user
	app.post("/api/method/frappe.auth.get_logged_user", (_req, res) => {
		const { getDatabase } = require("./db/connection")
		const db = getDatabase()
		const user = db.prepare("SELECT value FROM settings WHERE key = 'current_user'").get()
		res.json({ message: user ? user.value : "Administrator" })
	})

	// Login endpoint (local auth)
	app.post("/api/method/login", (req, res) => {
		const { usr, pwd } = req.body
		const { getDatabase } = require("./db/connection")
		const db = getDatabase()
		const user = db.prepare("SELECT * FROM users WHERE (name = ? OR email = ?) AND is_active = 1").get(usr, usr)

		if (user && user.password_hash === pwd) {
			db.prepare("UPDATE settings SET value = ? WHERE key = 'current_user'").run(user.name)
			res.json({ message: "Logged In", full_name: user.full_name })
		} else {
			res.status(401).json({ message: "Invalid credentials" })
		}
	})

	// Session info (used by frappe-ui session)
	app.get("/api/method/frappe.sessions.get_csrf_token", (_req, res) => {
		res.json({ message: "desktop-static-csrf-token" })
	})

	return app
}

/**
 * Start the Express server.
 * @param {number} port
 * @returns {Promise<void>}
 */
function startServer(port) {
	return new Promise((resolve, reject) => {
		try {
			const app = createApp()
			server = app.listen(port, "127.0.0.1", () => {
				console.log(`[Server] API server listening on http://127.0.0.1:${port}`)
				resolve()
			})
			server.on("error", reject)
		} catch (error) {
			reject(error)
		}
	})
}

/**
 * Stop the Express server.
 */
function stopServer() {
	if (server) {
		server.close()
		server = null
		console.log("[Server] API server stopped")
	}
}

module.exports = { startServer, stopServer }
