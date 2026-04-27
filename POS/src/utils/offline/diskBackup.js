/**
 * @fileoverview QZ-Tray-backed on-disk mirror for offline queues.
 *
 * Why this exists: IndexedDB lives inside the browser profile and can
 * vanish if the cashier hits "Clear site data," reinstalls the browser,
 * or switches user accounts. To make POS data resilient against that,
 * we mirror every queued invoice and queued customer to actual files on
 * the cashier's disk via QZ Tray's `file.*` API — the same QZ Tray
 * already used for printing.
 *
 * QZ runs as a native helper: writes go through its WebSocket → JVM →
 * filesystem, so the data physically lives on disk independent of the
 * browser. Files are kept in QZ's per-origin **sandbox folder**, which
 * does NOT require certificate elevation:
 *
 *   <QZ user data>/sandbox/<origin>/pos_next/invoices/<offline_id>.json
 *   <QZ user data>/sandbox/<origin>/pos_next/customers/<offline_id>.json
 *
 * On reconnect, sync drops the file. On a browser wipe, calling
 * `restoreFromDisk()` reads them back into IndexedDB so the queue
 * resumes from where it left off.
 *
 * Best-effort: every operation is wrapped in try/catch and logged.
 * QZ being unavailable never blocks the primary IndexedDB write.
 *
 * @module utils/offline/diskBackup
 */

import qz from "qz-tray"
import { logger } from "../logger"
import { connect as connectQZ, qzConnected } from "../qzTray"
import { db } from "./db"

const log = logger.create("DiskBackup")

const ROOT = "pos_next"
const INVOICE_DIR = `${ROOT}/invoices`
const CUSTOMER_DIR = `${ROOT}/customers`

// QZ sandbox flag — `true` keeps files under QZ's per-origin sandbox so
// no certificate elevation is needed to write them.
const SANDBOX_OPTS = { sandbox: true }

let _mirroringEnabled = true

/**
 * Disable disk mirroring (e.g. user opted out). Idempotent.
 */
export function disableDiskMirror() {
	_mirroringEnabled = false
}

/**
 * Re-enable disk mirroring after a previous disable.
 */
export function enableDiskMirror() {
	_mirroringEnabled = true
}

/**
 * @returns {boolean} Whether QZ is reachable AND mirroring is on.
 */
export function isMirrorAvailable() {
	return _mirroringEnabled && !!qzConnected.value
}

/**
 * Try to ensure QZ is connected. Returns false silently if it's not
 * available so the caller can degrade to "IndexedDB only" without
 * blowing up.
 */
async function tryConnect() {
	if (!_mirroringEnabled) return false
	if (qzConnected.value) return true
	try {
		const ok = await connectQZ()
		return !!ok
	} catch (error) {
		log.warn("QZ connect failed; disk mirror unavailable", error)
		return false
	}
}

function safeName(offlineId) {
	// Defensive: keep file names clean even if a UUID library returned
	// something odd. We never trust offline_id to come from a known set.
	// Replace any non-[a-z0-9._-] with `_`, then collapse `..` so a
	// crafted id can't traverse the QZ sandbox via `../../etc/passwd`.
	return String(offlineId || "")
		.replace(/[^a-zA-Z0-9._-]/g, "_")
		.replace(/\.{2,}/g, "_")
		.slice(0, 128)
}

function invoicePath(offlineId) {
	return `${INVOICE_DIR}/${safeName(offlineId)}.json`
}

function customerPath(offlineId) {
	return `${CUSTOMER_DIR}/${safeName(offlineId)}.json`
}

/**
 * Mirror a queued offline invoice to disk via QZ.
 *
 * @param {Object} row - The row that was just written to invoice_queue.
 *   Must include {id, offline_id, data, timestamp}.
 * @returns {Promise<{mirrored: boolean, reason?: string}>}
 */
export async function mirrorOfflineInvoice(row) {
	if (!row?.offline_id) return { mirrored: false, reason: "no_offline_id" }
	const ok = await tryConnect()
	if (!ok) return { mirrored: false, reason: "qz_unavailable" }

	try {
		const payload = JSON.stringify({
			kind: "invoice",
			version: 1,
			mirrored_at: Date.now(),
			row: {
				offline_id: row.offline_id,
				timestamp: row.timestamp,
				retry_count: row.retry_count || 0,
				stock_delta: row.stock_delta || [],
				data: row.data,
			},
		})
		await qz.file.write(invoicePath(row.offline_id), {
			data: payload,
			...SANDBOX_OPTS,
		})
		log.debug(`Mirrored invoice ${row.offline_id} to disk`)
		return { mirrored: true }
	} catch (error) {
		log.warn(
			`Failed to mirror invoice ${row.offline_id} to disk`,
			error?.message || error,
		)
		return { mirrored: false, reason: "qz_error" }
	}
}

/**
 * Mirror a queued offline customer-create to disk via QZ.
 *
 * @param {Object} row - customer_queue row.
 * @returns {Promise<{mirrored: boolean, reason?: string}>}
 */
export async function mirrorOfflineCustomer(row) {
	if (!row?.offline_id) return { mirrored: false, reason: "no_offline_id" }
	const ok = await tryConnect()
	if (!ok) return { mirrored: false, reason: "qz_unavailable" }

	try {
		const payload = JSON.stringify({
			kind: "customer",
			version: 1,
			mirrored_at: Date.now(),
			row: {
				offline_id: row.offline_id,
				timestamp: row.timestamp,
				retry_count: row.retry_count || 0,
				data: row.data,
			},
		})
		await qz.file.write(customerPath(row.offline_id), {
			data: payload,
			...SANDBOX_OPTS,
		})
		log.debug(`Mirrored customer ${row.offline_id} to disk`)
		return { mirrored: true }
	} catch (error) {
		log.warn(
			`Failed to mirror customer ${row.offline_id} to disk`,
			error?.message || error,
		)
		return { mirrored: false, reason: "qz_error" }
	}
}

/**
 * Remove a mirrored file once the queue row has been synced or deleted.
 * Best-effort: errors are logged but not thrown.
 */
export async function removeMirroredInvoice(offlineId) {
	if (!offlineId) return
	const ok = await tryConnect()
	if (!ok) return
	try {
		await qz.file.remove(invoicePath(offlineId), SANDBOX_OPTS)
	} catch (error) {
		// File may already be gone — ignore.
		log.debug(
			`Could not remove mirrored invoice ${offlineId}`,
			error?.message || error,
		)
	}
}

export async function removeMirroredCustomer(offlineId) {
	if (!offlineId) return
	const ok = await tryConnect()
	if (!ok) return
	try {
		await qz.file.remove(customerPath(offlineId), SANDBOX_OPTS)
	} catch (error) {
		log.debug(
			`Could not remove mirrored customer ${offlineId}`,
			error?.message || error,
		)
	}
}

/**
 * List all mirrored file names (without paths) under a directory.
 */
async function listDir(dir) {
	try {
		const entries = await qz.file.list(dir, SANDBOX_OPTS)
		// `qz.file.list` returns an array of strings — filenames relative to dir.
		return Array.isArray(entries)
			? entries.filter((n) => typeof n === "string" && n.endsWith(".json"))
			: []
	} catch (error) {
		// Directory may not exist yet — that's normal on a fresh install.
		log.debug(`list ${dir} failed`, error?.message || error)
		return []
	}
}

async function readJson(path) {
	try {
		const raw = await qz.file.read(path, SANDBOX_OPTS)
		// `read` returns the file contents as a string.
		if (typeof raw !== "string") return null
		return JSON.parse(raw)
	} catch (error) {
		log.warn(`Could not read ${path}`, error?.message || error)
		return null
	}
}

/**
 * @typedef {Object} RestoreResult
 * @property {boolean} ran - Whether the restore actually ran (false if QZ unavailable)
 * @property {number} invoicesRestored - New rows added to invoice_queue
 * @property {number} customersRestored - New rows added to customer_queue
 * @property {number} invoicesSkipped - Already in IndexedDB / already synced
 * @property {number} customersSkipped - Already in IndexedDB
 * @property {string[]} errors - Per-file errors
 */

/**
 * Read every mirrored file and re-insert into IndexedDB any rows that
 * are missing locally. This is the disaster-recovery path: after a
 * "Clear site data" or browser reinstall, calling this restores the
 * pending POS queues from the cashier's disk.
 *
 * Idempotent: it never overwrites an existing row, only fills gaps.
 *
 * @returns {Promise<RestoreResult>}
 */
export async function restoreFromDisk() {
	const result = {
		ran: false,
		invoicesRestored: 0,
		customersRestored: 0,
		invoicesSkipped: 0,
		customersSkipped: 0,
		errors: [],
	}

	const ok = await tryConnect()
	if (!ok) return result
	result.ran = true

	// --- Invoices ---
	const invoiceFiles = await listDir(INVOICE_DIR)
	for (const fname of invoiceFiles) {
		const path = `${INVOICE_DIR}/${fname}`
		const parsed = await readJson(path)
		if (!parsed?.row?.offline_id || !parsed.row.data) {
			result.errors.push(`${path}: malformed`)
			continue
		}
		const offlineId = parsed.row.offline_id
		try {
			const existing = await db.invoice_queue
				.where("offline_id")
				.equals(offlineId)
				.first()
			if (existing) {
				result.invoicesSkipped += 1
				continue
			}
			await db.invoice_queue.add({
				offline_id: offlineId,
				data: parsed.row.data,
				timestamp: parsed.row.timestamp || Date.now(),
				synced: false,
				retry_count: parsed.row.retry_count || 0,
				stock_delta: parsed.row.stock_delta || [],
				stock_reverted: false,
				restored_from_disk_at: Date.now(),
			})
			result.invoicesRestored += 1
		} catch (error) {
			log.error(`Restore invoice ${offlineId} failed`, error)
			result.errors.push(`${offlineId}: ${error?.message || error}`)
		}
	}

	// --- Customers ---
	const customerFiles = await listDir(CUSTOMER_DIR)
	for (const fname of customerFiles) {
		const path = `${CUSTOMER_DIR}/${fname}`
		const parsed = await readJson(path)
		if (!parsed?.row?.offline_id || !parsed.row.data) {
			result.errors.push(`${path}: malformed`)
			continue
		}
		const offlineId = parsed.row.offline_id
		try {
			const existing = await db.customer_queue
				.where("offline_id")
				.equals(offlineId)
				.first()
			if (existing) {
				result.customersSkipped += 1
				continue
			}
			await db.customer_queue.add({
				offline_id: offlineId,
				data: parsed.row.data,
				timestamp: parsed.row.timestamp || Date.now(),
				synced: false,
				retry_count: parsed.row.retry_count || 0,
				restored_from_disk_at: Date.now(),
			})
			result.customersRestored += 1
		} catch (error) {
			log.error(`Restore customer ${offlineId} failed`, error)
			result.errors.push(`${offlineId}: ${error?.message || error}`)
		}
	}

	log.success(
		`Restore complete: ${result.invoicesRestored} invoices + ${result.customersRestored} customers from disk`,
	)
	return result
}

/**
 * One-time backfill on first boot after the disk-mirror feature is
 * enabled: write any rows already in IndexedDB to disk so they are
 * protected. Safe to call repeatedly — it just rewrites the files.
 *
 * @returns {Promise<{invoices: number, customers: number}>}
 */
export async function backfillMirrorFromIndexedDB() {
	const counts = { invoices: 0, customers: 0 }
	const ok = await tryConnect()
	if (!ok) return counts

	try {
		const pendingInvoices = await db.invoice_queue
			.filter((r) => !r.synced)
			.toArray()
		for (const row of pendingInvoices) {
			const res = await mirrorOfflineInvoice(row)
			if (res.mirrored) counts.invoices += 1
		}

		const pendingCustomers = await db.customer_queue
			.filter((r) => !r.synced)
			.toArray()
		for (const row of pendingCustomers) {
			const res = await mirrorOfflineCustomer(row)
			if (res.mirrored) counts.customers += 1
		}

		log.info(
			`Backfill mirror complete: ${counts.invoices} invoices + ${counts.customers} customers`,
		)
	} catch (error) {
		log.warn("Backfill mirror failed", error)
	}

	return counts
}
