import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
			// Tauri plugins ship only inside the desktop bundle; under Vitest we
			// route them at stubs so vite's import-analysis can resolve the path
			// without the real packages being installed.
			"@tauri-apps/plugin-http": path.resolve(__dirname, "./tests/stubs/tauri-http.js"),
			"@tauri-apps/plugin-stronghold": path.resolve(__dirname, "./tests/stubs/tauri-stronghold.js"),
			"@tauri-apps/plugin-store": path.resolve(__dirname, "./tests/stubs/tauri-store.js"),
			"@tauri-apps/plugin-updater": path.resolve(__dirname, "./tests/stubs/tauri-updater.js"),
			"@tauri-apps/plugin-process": path.resolve(__dirname, "./tests/stubs/tauri-process.js"),
			"@tauri-apps/api/path": path.resolve(__dirname, "./tests/stubs/tauri-path.js"),
		},
	},
	define: {
		__POS_TARGET__: JSON.stringify("web"),
		__FRAPPE_BASE_URL__: JSON.stringify(""),
		__SOCKETIO_PORT__: JSON.stringify(9000),
		__BUILD_VERSION__: JSON.stringify("test"),
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
