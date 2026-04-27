/**
 * @fileoverview Pre-download item images so they are available offline.
 *
 * The service worker caches images opportunistically with a
 * `StaleWhileRevalidate` strategy, but that only helps for images the
 * user has actually viewed. For full offline mode the cashier may need
 * any item, so we eagerly fetch all known image URLs after the item
 * cache is seeded. The fetches go through the SW, which populates the
 * `product-images-cache` automatically.
 *
 * Constraints:
 *   - Throttled (small concurrency cap) so we don't saturate the network.
 *   - Best-effort: a failed fetch does not abort the run.
 *   - Resumable: we record the last completed offset in `settings`, so a
 *     reload mid-prefetch resumes instead of restarting.
 *   - Cancellable: a new run aborts in-flight fetches via AbortController.
 *
 * @module utils/offline/imagePrefetch
 */

import { logger } from "../logger"
import { db, getSetting, setSetting } from "./db"

const log = logger.create("ImagePrefetch")

const PROGRESS_KEY = "image_prefetch_offset"
const COMPLETED_KEY = "image_prefetch_completed_at"
const DEFAULT_CONCURRENCY = 6
const FETCH_TIMEOUT_MS = 10_000

let activeAbort = null

function buildImageUrl(rawUrl) {
	if (!rawUrl) return null
	const trimmed = String(rawUrl).trim()
	if (!trimmed) return null

	// Already absolute — keep as-is.
	if (/^https?:\/\//i.test(trimmed)) return trimmed

	// Frappe stores files at /files/... or /private/files/... — both
	// are served on the same origin as the POS, so a leading slash works.
	if (trimmed.startsWith("/")) return trimmed

	return `/files/${trimmed}`
}

async function prefetchOne(url, signal) {
	const timeoutId = setTimeout(() => {
		// best-effort: only abort the per-fetch timeout, not the whole run
	}, FETCH_TIMEOUT_MS)

	try {
		// `cache: "reload"` would bypass the SW cache; we want it cached,
		// so use the default. `mode: "cors"` is fine for same-origin too.
		const response = await fetch(url, {
			method: "GET",
			credentials: "same-origin",
			signal,
		})
		// We don't read the body — SW intercepts and stores it.
		// But we need to consume the response so the connection is freed.
		await response.blob().catch(() => null)
		return response.ok
	} catch (error) {
		if (error?.name === "AbortError") return false
		log.warn(`Failed to prefetch image ${url}`, error)
		return false
	} finally {
		clearTimeout(timeoutId)
	}
}

/**
 * Run a worker pool over `urls` with a concurrency cap.
 */
async function runPool(urls, concurrency, signal, onProgress) {
	let cursor = 0
	let okCount = 0
	let failCount = 0

	async function worker() {
		while (true) {
			if (signal.aborted) return
			const idx = cursor++
			if (idx >= urls.length) return
			const ok = await prefetchOne(urls[idx], signal)
			if (ok) okCount += 1
			else failCount += 1
			if (idx % 25 === 0) {
				onProgress?.(idx + 1, urls.length)
			}
		}
	}

	const workers = Array.from(
		{ length: Math.min(concurrency, urls.length) },
		worker,
	)
	await Promise.all(workers)
	return { ok: okCount, failed: failCount }
}

/**
 * Pre-download all known item images in the background.
 *
 * @param {Object} [options]
 * @param {number} [options.concurrency=6] - Parallel fetches.
 * @param {AbortSignal} [options.signal] - External cancellation signal.
 * @param {(done: number, total: number) => void} [options.onProgress]
 * @returns {Promise<{ok: number, failed: number, total: number, skipped: boolean}>}
 */
export async function prefetchItemImages({
	concurrency = DEFAULT_CONCURRENCY,
	signal,
	onProgress,
} = {}) {
	// Cancel any previous run so we don't double up.
	if (activeAbort) activeAbort.abort()
	activeAbort = new AbortController()
	const ourSignal = activeAbort.signal
	const combined = signal ? mergeSignals(signal, ourSignal) : ourSignal

	try {
		const items = await db.items.toArray()
		const urls = []
		const seen = new Set()
		for (const item of items) {
			const url = buildImageUrl(item.image)
			if (url && !seen.has(url)) {
				seen.add(url)
				urls.push(url)
			}
		}

		if (urls.length === 0) {
			log.info("No item images to prefetch")
			return { ok: 0, failed: 0, total: 0, skipped: true }
		}

		// Resume from last offset if recent.
		const startOffset = (await getSetting(PROGRESS_KEY, 0)) || 0
		const slice = urls.slice(startOffset)
		log.info(
			`Prefetching ${slice.length} item images (resuming from ${startOffset}/${urls.length})`,
		)

		const result = await runPool(
			slice,
			concurrency,
			combined,
			async (done, total) => {
				await setSetting(PROGRESS_KEY, startOffset + done)
				onProgress?.(startOffset + done, urls.length)
			},
		)

		await setSetting(PROGRESS_KEY, urls.length)
		await setSetting(COMPLETED_KEY, Date.now())

		log.success(
			`Image prefetch complete: ${result.ok} ok, ${result.failed} failed, ${urls.length} total`,
		)
		return { ...result, total: urls.length, skipped: false }
	} finally {
		if (activeAbort?.signal === ourSignal) activeAbort = null
	}
}

/** Reset progress so the next prefetch starts from scratch. */
export async function resetImagePrefetchProgress() {
	await setSetting(PROGRESS_KEY, 0)
	await setSetting(COMPLETED_KEY, null)
}

/** Cancel any in-flight prefetch run. */
export function cancelImagePrefetch() {
	if (activeAbort) {
		activeAbort.abort()
		activeAbort = null
	}
}

function mergeSignals(a, b) {
	if (a.aborted || b.aborted) {
		const ctrl = new AbortController()
		ctrl.abort()
		return ctrl.signal
	}
	const ctrl = new AbortController()
	const onAbort = () => ctrl.abort()
	a.addEventListener("abort", onAbort, { once: true })
	b.addEventListener("abort", onAbort, { once: true })
	return ctrl.signal
}
