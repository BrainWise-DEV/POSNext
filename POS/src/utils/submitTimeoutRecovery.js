import { logger } from "@/utils/logger";

const log = logger.create("SubmitRecovery");

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * After a client-side submit timeout, find out whether the server finished the sale.
 *
 * The first request keeps running after the client gives up, so ask the server by
 * the checkout's idempotency key a few times. Returns the invoice summary (same shape
 * submit_invoice returns) if the sale exists, or null if it could not be found in time.
 * A null result does not mean the sale failed: retrying is safe because the same key
 * makes the server return the existing invoice instead of creating another.
 *
 * @param {string|null} requestId - client_request_id of the timed-out checkout
 * @param {Object} deps
 * @param {(requestId: string) => Promise<{synced?: boolean, sales_invoice?: string, invoice?: Object}>} deps.check
 * @param {number} [deps.attempts]
 * @param {number} [deps.delayMs]
 * @param {(ms: number) => Promise<void>} [deps.sleep]
 */
export async function recoverTimedOutSubmit(
	requestId,
	{ check, attempts = 4, delayMs = 2500, sleep = defaultSleep }
) {
	if (!requestId) return null;

	for (let attempt = 0; attempt < attempts; attempt++) {
		if (attempt > 0) await sleep(delayMs);

		try {
			const result = await check(requestId);
			if (result?.synced && result.invoice) return result.invoice;
			if (result?.synced && result.sales_invoice) {
				return { name: result.sales_invoice, status: 1, client_request_id: requestId };
			}
		} catch (error) {
			log.warn("Could not check the timed-out submit, will retry", { requestId, error });
		}
	}
	return null;
}
