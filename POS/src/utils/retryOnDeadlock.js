/**
 * Retry a server call that lost a database deadlock.
 *
 * When two requests lock the same rows in opposite order the database rolls one of
 * them back completely and returns QueryDeadlockError ("Internal Server Error" in the
 * dialog). Nothing of that request was kept, so repeating it is safe; for checkout the
 * repeat also carries the same client_request_id, so even if the first attempt had
 * somehow been kept the server would return that invoice instead of creating another.
 *
 * Only deadlocks are retried: validation, stock and permission errors are real answers
 * and are thrown straight away.
 */

const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function isDeadlockError(error) {
	const text = [
		error?.exc_type,
		error?.resourceError?.exc_type,
		error?.exception,
		error?._error_message,
		error?.message,
	]
		.filter(Boolean)
		.join(" ");
	return /QueryDeadlockError|deadlock found/i.test(text);
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
