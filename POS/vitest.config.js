import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

// Standalone Vitest config (kept separate from vite.config.js so the
// frappe-ui / PWA build plugins don't run during unit tests).
export default defineConfig({
	plugins: [vue()],
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
