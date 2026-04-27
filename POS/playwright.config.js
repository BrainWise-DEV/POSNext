import { defineConfig, devices } from "@playwright/test"

/**
 * Playwright config for POS Next end-to-end smoke tests.
 *
 * Strategy:
 *   - Run the Vite dev server on :8080 (auto-starts; reuses an existing one
 *     so you don't bounce hot-reload during local iteration).
 *   - Tests don't sign in to Frappe; instead they load the public /pos
 *     entry and either inspect the bundle / SW state, or hit a tiny
 *     Vite-served fixture page that exercises offline modules in a real
 *     Chromium tab.
 *
 * Run with:
 *     yarn e2e
 *     yarn e2e --headed              # see the browser
 *     yarn e2e --grep="offline"      # filter
 */

const HOST = process.env.POS_E2E_HOST || "http://localhost:8080"

export default defineConfig({
	testDir: "./tests/playwright",
	timeout: 60_000,
	expect: { timeout: 10_000 },
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	reporter: process.env.CI ? "github" : [["list"]],
	use: {
		baseURL: HOST,
		trace: "retain-on-failure",
		viewport: { width: 1280, height: 800 },
		ignoreHTTPSErrors: true,
	},
	projects: [
		{
			name: "chromium",
			use: { ...devices["Desktop Chrome"] },
		},
	],
	webServer: {
		// Reuse an already-running dev server when present so we don't
		// stomp on `yarn dev`. CI will spin one up.
		command: "yarn dev --host 0.0.0.0",
		url: HOST,
		reuseExistingServer: !process.env.CI,
		timeout: 120_000,
		stdout: "ignore",
		stderr: "pipe",
	},
})
