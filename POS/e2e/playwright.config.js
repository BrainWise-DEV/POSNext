import { defineConfig } from "@playwright/test";

// UI test harness for F&F / coupons / offers (plan section 6, run 3: all checks automated).
// Run from POS/:  e2e/run.sh [playwright args]   (reads the uit-* passwords from the site's private TSV
// into env vars; nothing is printed). UIT_BASE_URL defaults to http://pos-dev.localhost:8000.
const ARTIFACTS = process.env.UIT_ARTIFACTS || "./artifacts";
export default defineConfig({
	testDir: ".",
	// *.e2e.js, so vitest's default *.spec.js glob never picks these up.
	testMatch: "**/*.e2e.js",
	globalSetup: "./global-setup.js",
	// Settings are global and there is one shift per user: run in order, one worker.
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 240_000,
	expect: { timeout: 20_000 },
	outputDir: process.env.UIT_OUT || "./test-results",
	reporter: [["list"], ["html", { open: "never", outputFolder: `${ARTIFACTS}/report` }], ["json", { outputFile: `${ARTIFACTS}/results.json` }]],
	use: {
		baseURL: process.env.UIT_BASE_URL || "http://pos-dev.localhost:8000",
		locale: "en-US",
		viewport: { width: 1440, height: 900 },
		// Traces carry the session cookie: off unless UIT_TRACE=1 (local debugging only, never committed).
		trace: process.env.UIT_TRACE ? "retain-on-failure" : "off",
		screenshot: "only-on-failure",
		actionTimeout: 20_000,
	},
});
