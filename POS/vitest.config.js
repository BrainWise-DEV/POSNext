import path from "node:path"
import { defineConfig } from "vitest/config"

// Standalone Vitest config (kept separate from vite.config.js so the
// frappe-ui / PWA build plugins don't run during unit tests).
export default defineConfig({
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	test: {
		globals: true,
		environment: "jsdom",
	},
})
