import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"
import { viteStaticCopy } from "vite-plugin-static-copy"

/**
 * Vite config for Electron desktop build.
 *
 * Differences from POS/vite.config.js:
 * - No frappeui plugin (no Frappe proxy needed)
 * - No VitePWA plugin (Electron handles offline natively)
 * - Output to pos-next-desktop/renderer/
 * - Base path is relative (./) for file:// protocol
 * - __ELECTRON__ flag for conditional code paths
 * - Aliased common_site_config.json import
 */

const POS_SRC = path.resolve(__dirname, "../POS/src")

export default defineConfig({
	root: path.resolve(__dirname, "../POS"),
	plugins: [
		vue(),
		viteStaticCopy({
			targets: [
				{
					src: "src/workers",
					dest: ".",
				},
			],
		}),
	],
	build: {
		outDir: path.resolve(__dirname, "renderer"),
		emptyOutDir: true,
		chunkSizeWarningLimit: 2000,
		target: "es2020", // Electron supports modern JS
		sourcemap: true,
		rollupOptions: {
			input: path.resolve(__dirname, "../POS/index.html"),
		},
	},
	worker: {
		format: "es",
		rollupOptions: {
			output: {
				format: "es",
			},
		},
	},
	resolve: {
		alias: {
			"@": POS_SRC,
			"tailwind.config.js": path.resolve(__dirname, "../POS/tailwind.config.js"),
			// Stub out the common_site_config.json import used by socket.js
			"../../../../sites/common_site_config.json": path.resolve(__dirname, "electron/common_site_config_stub.js"),
		},
	},
	define: {
		__ELECTRON__: true,
		__BUILD_VERSION__: JSON.stringify(`desktop-${Date.now()}`),
	},
	optimizeDeps: {
		include: [
			"feather-icons",
			"showdown",
			"highlight.js/lib/core",
			"interactjs",
		],
	},
})
