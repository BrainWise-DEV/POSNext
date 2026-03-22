const { getDatabase } = require("../db/connection")

/**
 * Wallet API - replaces pos_next.api.wallet
 * Local wallet operations against SQLite.
 */

async function getCustomerWalletBalance(params) {
	const db = getDatabase()
	const { customer } = params

	const wallet = db.prepare("SELECT balance FROM wallets WHERE customer = ?").get(customer)
	return wallet?.balance || 0
}

async function getCustomerWallet(params) {
	const db = getDatabase()
	const { customer } = params

	return db.prepare("SELECT * FROM wallets WHERE customer = ?").get(customer) || null
}

async function getOrCreateWallet(params) {
	const db = getDatabase()
	const { customer } = params

	let wallet = db.prepare("SELECT * FROM wallets WHERE customer = ?").get(customer)
	if (!wallet) {
		const name = `WALLET-${Date.now()}`
		db.prepare("INSERT INTO wallets (name, customer, balance) VALUES (?, ?, 0)").run(name, customer)
		wallet = db.prepare("SELECT * FROM wallets WHERE name = ?").get(name)
	}

	return wallet
}

async function getWalletPaymentMethods() {
	return []
}

async function getWalletInfo(params) {
	return { has_wallet: false, balance: 0 }
}

async function createManualWalletCredit() {
	const { FrappeError } = require("../frappe-compat")
	throw new FrappeError("Wallet credit requires internet connection", { httpStatus: 503 })
}

module.exports = {
	getCustomerWalletBalance,
	getCustomerWallet,
	getOrCreateWallet,
	getWalletPaymentMethods,
	getWalletInfo,
	createManualWalletCredit,
}
