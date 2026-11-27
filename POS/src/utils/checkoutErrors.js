/**
 * Tell checkout failures apart, by the real database error number where there is one.
 *
 * They are different failures and need different handling:
 *
 * - deadlock (1213): InnoDB found a cycle and rolled back the WHOLE transaction of the
 *   victim. Frappe's request handler also rolls the request back. Repeating is safe and
 *   usually succeeds at once.
 * - snapshot_conflict (1020): newer MariaDB, REPEATABLE READ: the row changed after this
 *   transaction's snapshot. Frappe reports it as QueryDeadlockError too. Same handling.
 * - lock_wait_timeout (1205): the request waited the full innodb_lock_wait_timeout (50 s
 *   by default) for a lock another transaction still holds. It is NOT retried
 *   automatically: the cashier has already waited that long, the blocker is probably still
 *   there, and a repeat would block another 50 s inside the checkout's own 60 s limit.
 *   Pressing pay again is safe (same client_request_id).
 * - frontend_timeout: this screen gave up waiting; the server may still finish.
 * - network: no usable answer at all; the outcome is unknown.
 */

import { isSubmitTimeoutError } from "@/utils/submitRequestId";

const text = (error) =>
	[
		error?.exc_type,
		error?.resourceError?.exc_type,
		error?.exception,
		error?._error_message,
		error?.message,
	]
		.filter(Boolean)
		.join(" ");

export function classifyCheckoutError(error) {
	if (!error) return { kind: "other", autoRetry: false };

	const t = text(error);
	if (isSubmitTimeoutError(error)) return { kind: "frontend_timeout", autoRetry: false };

	if (/\(?1213\b|deadlock found/i.test(t)) return { kind: "deadlock", autoRetry: true };
	if (/\(?1020\b|record has changed since last read/i.test(t))
		return { kind: "snapshot_conflict", autoRetry: true };
	if (/\(?1205\b|lock wait timeout|QueryTimeoutError/i.test(t))
		return { kind: "lock_wait_timeout", autoRetry: false };
	// Frappe raises QueryDeadlockError for 1213 and 1020; trust the type when the number is absent
	if (/QueryDeadlockError/i.test(t)) return { kind: "deadlock", autoRetry: true };

	const status = Number(error?.httpStatus);
	if (
		/failed to fetch|networkerror|network request failed|load failed|econn|timeout of \d+ms/i.test(
			t
		) ||
		error?.name === "TypeError" ||
		status === 0 ||
		[502, 503, 504].includes(status)
	)
		return { kind: "network", autoRetry: false };

	return { kind: "other", autoRetry: false };
}
