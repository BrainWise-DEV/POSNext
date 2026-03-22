const path = require("node:path")
const { app } = require("electron")

let db = null

/**
 * Get the path to the SQLite database file.
 * Stores in %APPDATA%/POSNext/data/ on Windows.
 */
function getDBPath() {
	const userDataPath = app ? app.getPath("userData") : path.join(require("os").homedir(), ".posnext")
	const dbDir = path.join(userDataPath, "data")

	// Ensure directory exists
	const fs = require("node:fs")
	fs.mkdirSync(dbDir, { recursive: true })

	return path.join(dbDir, "pos_next.db")
}

/**
 * Get or create the SQLite database connection singleton.
 * Uses WAL mode for better concurrent read performance.
 * @returns {import('better-sqlite3').Database}
 */
function getDatabase() {
	if (db) return db

	const Database = require("better-sqlite3")
	const dbPath = getDBPath()

	console.log(`[DB] Opening database at: ${dbPath}`)

	db = new Database(dbPath)

	// Performance optimizations
	db.pragma("journal_mode = WAL")
	db.pragma("synchronous = NORMAL")
	db.pragma("cache_size = -64000") // 64MB cache
	db.pragma("foreign_keys = ON")
	db.pragma("temp_store = MEMORY")

	return db
}

/**
 * Close the database connection.
 */
function closeDatabase() {
	if (db) {
		db.close()
		db = null
		console.log("[DB] Database connection closed")
	}
}

module.exports = { getDatabase, closeDatabase, getDBPath }
