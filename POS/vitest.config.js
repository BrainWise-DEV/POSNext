import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	test: {
		environment: "jsdom",
		globals: true,
		setupFiles: ["./tests/setup.js"],
		include: ["tests/**/*.test.js", "src/**/*.test.js"],
		coverage: {
			provider: "v8",
			reporter: ["text", "html"],
			include: ["src/utils/offline/**", "src/stores/**"],
		},
	},
})
