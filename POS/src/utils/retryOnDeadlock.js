/**
 * Retry a server call that lost a database deadlock.
 *
 * When two requests lock the same rows in opposite order the database rolls one of
 * them back completely and returns QueryDeadlockError ("Internal Server Error" in the
 * dialog). Nothing of that request was kept, so repeating it is safe; for checkout the
 * repeat also carries the same client_request_id, so even if the first attempt had
 * somehow been kept the server would return that invoice instead of creating another.
 *
 * Only deadlocks (1213) and snapshot conflicts (1020) are retried. Lock wait timeouts (1205),
 * validation, stock and permission errors, network failures and screen timeouts are thrown
 * straight away: see checkoutErrors.js for why each is treated as it is.
 */

import { classifyCheckoutError } from "@/utils/checkoutErrors";

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function isDeadlockError(error) {
	// 1213 and 1020 only; a lock wait timeout (1205) is deliberately NOT retried (see checkoutErrors)
	return classifyCheckoutError(error).autoRetry;
}

/**
 * @param {() => Promise<*>} fn - the call to make (receives the attempt number)
 * @param {Object} [options]
 * @param {number} [options.attempts=3] - total tries including the first
 * @param {number} [options.baseDelayMs=250] - delay grows with each attempt, plus jitter, so
 *   the colliding requests do not retry in lockstep and collide again
 * @param {(ms: number) => Promise<void>} [options.sleep]
 * @param {() => number} [options.random]
 * @param {(attempt: number, error: Error) => void} [options.onRetry]
 */
export async function retryOnDeadlock(
	fn,
	{ attempts = 3, baseDelayMs = 250, sleep = defaultSleep, random = Math.random, onRetry } = {}
) {
	for (let attempt = 1; ; attempt++) {
		try {
			return await fn(attempt);
		} catch (error) {
			if (!isDeadlockError(error) || attempt >= attempts) throw error;
			onRetry?.(attempt, error);
			await sleep(baseDelayMs * attempt + random() * baseDelayMs);
		}
	}
}
