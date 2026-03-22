const { initializeSchema } = require("./schema")

/**
 * Database migration system.
 *
 * Each migration has a version number and an `up` function that receives the db.
 * Migrations run in order, skipping already-applied versions.
 */

const MIGRATIONS = [
	{
		version: 1,
		description: "Initial schema",
		up: (db) => {
			initializeSchema(db)
		},
	},
	// Future migrations go here:
	// {
	//   version: 2,
	//   description: "Add new column to invoices",
	//   up: (db) => {
	//     db.exec("ALTER TABLE invoices ADD COLUMN new_field TEXT")
	//   },
	// },
]

/**
 * Run all pending migrations.
 * @param {import('better-sqlite3').Database} db
 */
function runMigrations(db) {
	// Ensure schema_version table exists (bootstrap)
	db.exec(`
		CREATE TABLE IF NOT EXISTS schema_version (
			version INTEGER PRIMARY KEY,
			applied_at TEXT NOT NULL
		)
	`)

	const getCurrentVersion = db.prepare(
		"SELECT MAX(version) as version FROM schema_version"
	)
	const insertVersion = db.prepare(
		"INSERT INTO schema_version (version, applied_at) VALUES (?, ?)"
	)

	const current = getCurrentVersion.get()
	const currentVersion = current?.version || 0

	let applied = 0
	for (const migration of MIGRATIONS) {
		if (migration.version > currentVersion) {
			console.log(`[DB] Applying migration v${migration.version}: ${migration.description}`)

			const applyMigration = db.transaction(() => {
				migration.up(db)
				insertVersion.run(migration.version, new Date().toISOString())
			})

			applyMigration()
			applied++
		}
	}

	if (applied > 0) {
		console.log(`[DB] ${applied} migration(s) applied. Current version: ${MIGRATIONS[MIGRATIONS.length - 1].version}`)
	} else {
		console.log(`[DB] Database is up to date (v${currentVersion})`)
	}
}

/**
 * Get the current schema version.
 * @param {import('better-sqlite3').Database} db
 * @returns {number}
 */
function getSchemaVersion(db) {
	try {
		const result = db.prepare("SELECT MAX(version) as version FROM schema_version").get()
		return result?.version || 0
	} catch {
		return 0
	}
}

module.exports = { runMigrations, getSchemaVersion }
