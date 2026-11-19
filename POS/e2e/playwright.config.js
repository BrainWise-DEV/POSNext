import { defineConfig } from "@playwright/test";

// Smoke harness for the F&F / coupons / offers UI test plan (section 6).
// Run from POS/:  yarn e2e   (UIT_BASE_URL, UIT_USER, UIT_PASSWORD must be set).
export default defineConfig({
	testDir: ".",
	// *.e2e.js, so vitest's default *.spec.js glob never picks these up.
	testMatch: "**/*.e2e.js",
	globalSetup: "./global-setup.js",
	// One shared site, one shift per user: run in order, one worker.
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 120_000,
	expect: { timeout: 15_000 },
	outputDir: "./test-results",
	reporter: [["list"], ["html", { open: "never", outputFolder: "./report" }]],
	use: {
		baseURL: process.env.UIT_BASE_URL,
		locale: "en-US",
		viewport: { width: 1440, height: 900 },
		trace: "retain-on-failure",
		screenshot: "only-on-failure",
	},
});
