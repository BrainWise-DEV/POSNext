/**
 * Playwright smoke test — runs the offline modules in a real Chromium
 * tab against the Vite dev server.
 *
 * The dev server resolves /src/utils/offline/db.js etc. via Vite's
 * transform pipeline, so we get the real production code (no mocks,
 * no jsdom shims). The test injects an HTML page that imports those
 * modules and exercises a few invariants, then asserts on the result
 * via window properties.
 *
 * Requires the Vite dev server (auto-started by playwright.config.js).
 */

import { expect, test } from "@playwright/test"

const HARNESS_HTML = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>POS Next Harness</title></head><body>
<pre id="log">starting</pre>
<script type="module">
	const log = (m) => { document.getElementById('log').textContent += '\\n' + m }
	const results = { ok: [], fail: [] }
	try {
		const dbModule = await import('/src/utils/offline/db.js')
		const queueModule = await import('/src/utils/offline/customerQueue.js')

		const required = ['taxes', 'uoms', 'item_groups', 'brands', 'loyalty_programs', 'customer_queue']
		const tables = dbModule.db.tables.map((t) => t.name)
		const missing = required.filter((n) => !tables.includes(n))
		if (missing.length) results.fail.push('missing tables: ' + missing.join(','))
		else results.ok.push('all expected tables present')

		await dbModule.db.uoms.put({ name: 'Nos' })
		const round = await dbModule.db.uoms.get('Nos')
		if (round?.name === 'Nos') results.ok.push('uoms round-trip')
		else results.fail.push('uoms round-trip failed')

		const enq = await queueModule.enqueueOfflineCustomer({
			customer_name: 'Playwright Customer',
			mobile_no: '+15551234567',
		})
		if (enq.offline_id?.startsWith('pos_offline_')) results.ok.push('enqueue offline customer')
		else results.fail.push('enqueue offline customer (no offline_id)')

		await dbModule.db.customer_queue.clear()
		await dbModule.db.customers.clear()
		await dbModule.db.uoms.clear()

		log('done')
		window.__HARNESS_RESULT__ = results
	} catch (err) {
		results.fail.push('THREW: ' + (err?.message || err))
		log('error: ' + (err?.message || err))
		window.__HARNESS_RESULT__ = results
	}
</script>
</body></html>`

test.describe("offline modules in real chromium", () => {
	test("schema, round-trip, and customer queue work end-to-end", async ({
		page,
	}) => {
		// Hijack a Vite-served URL with our harness HTML. Vite still
		// resolves the inner /src/... module imports through its dev
		// pipeline, so we get the real code.
		await page.route("**/__pos_harness__", async (route) => {
			await route.fulfill({
				status: 200,
				contentType: "text/html",
				body: HARNESS_HTML,
			})
		})

		await page.goto("/__pos_harness__")
		await page.waitForFunction(() => !!window.__HARNESS_RESULT__, null, {
			timeout: 30_000,
		})

		const result = await page.evaluate(() => window.__HARNESS_RESULT__)
		expect(result.fail, `harness failures: ${result.fail.join(", ")}`).toEqual(
			[],
		)
		expect(result.ok).toContain("all expected tables present")
		expect(result.ok).toContain("uoms round-trip")
		expect(result.ok).toContain("enqueue offline customer")
	})

	test("the SPA entry mounts without thrown JS exceptions", async ({
		page,
	}) => {
		const pageErrors = []
		page.on("pageerror", (err) => pageErrors.push(String(err)))

		// `/` → the Vue SPA. The Login route renders without an
		// authenticated session, so this works without a Frappe login.
		// We only fail on `pageerror` (uncaught JS exceptions), NOT on
		// console errors — the app legitimately logs API failures
		// (PermissionError, translation 417) when the test runs without
		// a backend session, and those are not what this smoke checks.
		await page.goto("/", { waitUntil: "domcontentloaded" })
		await page.waitForLoadState("networkidle", { timeout: 30_000 })

		// Sanity: Vue mounted *something*. The body should have content.
		const bodyText = await page.locator("body").innerText()
		expect(bodyText.length).toBeGreaterThan(0)

		// Filter out expected backend failures from running without a
		// Frappe session: PermissionError on auth.get_logged_user,
		// ValidationError on the translation API, etc. We're smoke-
		// testing that the bundle parses and Vue mounts, NOT that the
		// API surface works without auth.
		const fatal = pageErrors.filter(
			(e) =>
				!/PermissionError|ValidationError|frappe\.auth|get_app_translations|HTTP \d|Failed to fetch/i.test(
					e,
				),
		)
		expect(
			fatal,
			`unexpected uncaught JS exceptions:\n  ${fatal.join("\n  ")}`,
		).toEqual([])
	})
})
