/**
 * @fileoverview Offline customer creation queue.
 *
 * Mirrors the offline invoice queue pattern: customers created while
 * offline get a client-side UUID (`offline_id`), are persisted to the
 * `customer_queue` IndexedDB table, and are replayed against the server
 * when connectivity returns. The replay endpoint is idempotent on
 * `offline_id` so duplicate flushes don't create duplicate records.
 *
 * @module utils/offline/customerQueue
 */

import { call } from "@/utils/apiWrapper"
import { logger } from "../logger"
import { db } from "./db"
import { generateOfflineId } from "./uuid"

const log = logger.create("CustomerQueue")

/**
 * Enqueue a customer for offline creation.
 * Stores a placeholder customer in the cache so it's selectable in the UI
 * immediately, and queues the create payload for later replay.
 *
 * @param {Object} payload - Customer fields (customer_name, mobile_no, email_id, ...).
 * @returns {Promise<{offline_id: string, placeholder_name: string}>}
 */
export async function enqueueOfflineCustomer(payload) {
	if (!payload?.customer_name) {
		throw new Error("customer_name is required to enqueue offline customer")
	}

	const offlineId = generateOfflineId()
	const placeholderName = `OFFLINE-${offlineId.slice(-8).toUpperCase()}`
	const timestamp = Date.now()

	await db.transaction("rw", "customer_queue", "customers", async () => {
		await db.customer_queue.put({
			offline_id: offlineId,
			data: payload,
			timestamp,
			synced: false,
			retry_count: 0,
		})

		// Add a placeholder to the customers cache so the cashier can pick
		// the new customer mid-session. The replay step rewrites/merges the
		// row to the real server name once online.
		await db.customers.put({
			name: placeholderName,
			customer_name: payload.customer_name,
			mobile_no: payload.mobile_no || "",
			email_id: payload.email_id || "",
			customer_group: payload.customer_group || "Individual",
			territory: payload.territory || "All Territories",
			loyalty_points: 0,
			wallet_balance: 0,
			addresses: [],
			pending_offline_id: offlineId,
			placeholder: true,
		})
	})

	// Best-effort disk mirror via QZ Tray (defense against browser wipe).
	import("./diskBackup")
		.then(({ mirrorOfflineCustomer }) =>
			mirrorOfflineCustomer({
				offline_id: offlineId,
				data: payload,
				timestamp,
				retry_count: 0,
			}),
		)
		.catch((err) => log.debug("Disk mirror skipped", err))

	log.info(
		`Enqueued offline customer "${payload.customer_name}" as ${placeholderName}`,
	)
	return { offline_id: offlineId, placeholder_name: placeholderName }
}

/**
 * Get all queued (unsynced) offline customers.
 * @returns {Promise<Array>} Queue rows ordered by timestamp asc.
 */
export async function getQueuedOfflineCustomers() {
	try {
		return await db.customer_queue
			.filter((row) => row.synced === false)
			.sortBy("timestamp")
	} catch (error) {
		log.error("Failed to read customer queue", error)
		return []
	}
}

/**
 * Replay all queued offline customers against the server.
 * Removes successfully replayed entries from the queue and rewrites the
 * placeholder customer row with the real server name.
 *
 * Best-effort per row: a failure on one customer doesn't stop the others.
 *
 * @returns {Promise<{success: number, failed: number, deduplicated: number}>}
 */
export async function syncOfflineCustomers() {
	const queue = await getQueuedOfflineCustomers()
	if (queue.length === 0) {
		return { success: 0, failed: 0, deduplicated: 0 }
	}

	let success = 0
	let failed = 0
	let deduplicated = 0

	for (const row of queue) {
		try {
			const result = await call(
				"pos_next.api.customers.replay_offline_customer",
				{
					offline_id: row.offline_id,
					customer_name: row.data.customer_name,
					mobile_no: row.data.mobile_no || null,
					email_id: row.data.email_id || null,
					customer_group: row.data.customer_group || "Individual",
					territory: row.data.territory || "All Territories",
					company: row.data.company || null,
					pos_profile: row.data.pos_profile || null,
				},
			)

			const payload = result?.message ?? result
			const realName = payload?.name
			const wasDeduped = !!payload?.deduplicated
			if (!realName) {
				throw new Error("replay_offline_customer returned no name")
			}

			await db.transaction("rw", "customer_queue", "customers", async () => {
				// Remove queue row.
				await db.customer_queue.delete(row.id)

				// Drop the placeholder; insert the real customer record.
				const placeholder = await db.customers
					.filter((c) => c.pending_offline_id === row.offline_id)
					.first()
				if (placeholder) {
					await db.customers.delete(placeholder.name)
				}
				await db.customers.put({
					...(payload.doc || {}),
					name: realName,
					addresses: payload.doc?.addresses || [],
					loyalty_points: 0,
					wallet_balance: 0,
				})
			})

			// Drop the disk mirror — customer is now on the server.
			import("./diskBackup")
				.then(({ removeMirroredCustomer }) =>
					removeMirroredCustomer(row.offline_id),
				)
				.catch(() => {})

			if (wasDeduped) deduplicated += 1
			else success += 1
		} catch (error) {
			failed += 1
			log.error(`Failed to replay offline customer ${row.offline_id}`, error)
			try {
				await db.customer_queue.update(row.id, {
					retry_count: (row.retry_count || 0) + 1,
					last_error: String(error?.message || error),
				})
			} catch (updateErr) {
				log.error("Could not bump retry count", updateErr)
			}
		}
	}

	log.info(
		`Customer queue replay complete: ${success} new, ${deduplicated} deduplicated, ${failed} failed`,
	)
	return { success, failed, deduplicated }
}
