import path from "node:path"
import { promises as fs, existsSync, readFileSync } from "node:fs"
import vue from "@vitejs/plugin-vue"
import frappeui from "frappe-ui/vite"
import { defineConfig, loadEnv } from "vite"
import { VitePWA } from "vite-plugin-pwa"
import { viteStaticCopy } from "vite-plugin-static-copy"

const buildVersion = process.env.POS_NEXT_BUILD_VERSION || Date.now().toString()
const enableSourceMap = process.env.POS_NEXT_ENABLE_SOURCEMAP === "true"

/**
 * Vite plugin to write build version to version.json file
 * This enables cache busting and version tracking
 */
function posNextBuildVersionPlugin(version) {
	return {
		name: "pos-next-build-version",
		apply: "build",
		async writeBundle() {
			const versionFile = path.resolve(__dirname, "../pos_next/public/pos/version.json")
			await fs.mkdir(path.dirname(versionFile), { recursive: true })
			await fs.writeFile(
				versionFile,
				JSON.stringify(
					{
						version,
						timestamp: new Date().toISOString(),
						buildDate: new Date().toLocaleDateString("en-US", {
							year: "numeric",
							month: "long",
							day: "numeric",
						}),
					},
					null,
					2
				),
				"utf8"
			)
			console.log(`\n✓ Build version written: ${version}`)
		},
	}
}

/** Best-effort read of the bench's socketio_port. Missing file → null. */
function readBenchSocketioPort() {
	const candidate = path.resolve(__dirname, "../../../../sites/common_site_config.json")
	if (!existsSync(candidate)) return null
	try {
		const cfg = JSON.parse(readFileSync(candidate, "utf8"))
		return cfg.socketio_port || null
	} catch {
		return null
	}
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), "")

	// Three switches drive the build:
	//   VITE_POS_TARGET     "web" (default) | "desktop"
	//   VITE_FRAPPE_BASE_URL  https://acme.frappe.cloud (desktop only)
	//   VITE_ENABLE_PWA     "false" disables PWA even in web mode
	const target = env.VITE_POS_TARGET === "desktop" ? "desktop" : "web"
	const isDesktop = target === "desktop"
	const baseUrl = env.VITE_FRAPPE_BASE_URL || ""
	const pwaEnabled = !isDesktop && env.VITE_ENABLE_PWA !== "false"
	const socketioPort = isDesktop ? null : readBenchSocketioPort()

	if (isDesktop && !baseUrl) {
		console.warn(
			"[vite] VITE_POS_TARGET=desktop without VITE_FRAPPE_BASE_URL — desktop build will have no backend",
		)
	}

	const plugins = [
		posNextBuildVersionPlugin(buildVersion),
		// frappe-ui's vite plugin injects Jinja boot data + frappe proxy. We only
		// want it on web builds; desktop runs without a same-origin Frappe shell.
		!isDesktop &&
			frappeui({
				frappeProxy: true,
				jinjaBootData: true,
				lucideIcons: true,
				buildConfig: {
					indexHtmlPath: "../pos_next/www/pos.html",
					outDir: "../pos_next/public/pos",
					emptyOutDir: true,
					sourcemap: enableSourceMap,
				},
			}),
		vue(),
		viteStaticCopy({
			targets: [
				{
					src: "src/workers",
					dest: ".",
				},
			],
		}),
		pwaEnabled &&
			VitePWA({
				registerType: "autoUpdate",
				includeAssets: ["favicon.png", "icon.svg", "icon-maskable.svg"],
				manifest: {
					name: "POSNext",
					short_name: "POSNext",
					description:
						"Point of Sale system with real-time billing, stock management, and offline support",
					theme_color: "#4F46E5",
					background_color: "#ffffff",
					display: "standalone",
					scope: "/assets/pos_next/pos/",
					start_url: "/pos",
					icons: [
						{
							src: "/assets/pos_next/pos/icon.svg",
							sizes: "192x192",
							type: "image/svg+xml",
							purpose: "any",
						},
						{
							src: "/assets/pos_next/pos/icon.svg",
							sizes: "512x512",
							type: "image/svg+xml",
							purpose: "any",
						},
						{
							src: "/assets/pos_next/pos/icon-maskable.svg",
							sizes: "192x192",
							type: "image/svg+xml",
							purpose: "maskable",
						},
						{
							src: "/assets/pos_next/pos/icon-maskable.svg",
							sizes: "512x512",
							type: "image/svg+xml",
							purpose: "maskable",
						},
					],
				},
				workbox: {
					globPatterns: ["**/*.{js,css,html,ico,png,svg,woff,woff2}"],
					maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
					navigateFallback: null,
					navigateFallbackDenylist: [/^\/api/, /^\/app/],
					runtimeCaching: [
						{
							urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
							handler: "CacheFirst",
							options: {
								cacheName: "google-fonts-cache",
								expiration: {
									maxEntries: 10,
									maxAgeSeconds: 60 * 60 * 24 * 365,
								},
								cacheableResponse: { statuses: [0, 200] },
							},
						},
						{
							urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
							handler: "CacheFirst",
							options: {
								cacheName: "gstatic-fonts-cache",
								expiration: {
									maxEntries: 10,
									maxAgeSeconds: 60 * 60 * 24 * 365,
								},
								cacheableResponse: { statuses: [0, 200] },
							},
						},
						{
							urlPattern: /\/assets\/pos_next\/pos\/.*/i,
							handler: "CacheFirst",
							options: {
								cacheName: "pos-assets-cache",
								expiration: {
									maxEntries: 500,
									maxAgeSeconds: 60 * 60 * 24 * 30,
								},
							},
						},
						{
							urlPattern: /\/files\/.*\.(jpg|jpeg|png|gif|webp|svg)$/i,
							handler: "StaleWhileRevalidate",
							options: {
								cacheName: "product-images-cache",
								expiration: {
									maxEntries: 200,
									maxAgeSeconds: 60 * 60 * 24 * 7,
								},
								cacheableResponse: { statuses: [0, 200] },
							},
						},
						{
							urlPattern: /\/api\/.*/i,
							handler: "NetworkFirst",
							options: {
								cacheName: "api-cache",
								networkTimeoutSeconds: 10,
								expiration: {
									maxEntries: 100,
									maxAgeSeconds: 60 * 60 * 24,
								},
								cacheableResponse: { statuses: [0, 200] },
							},
						},
						{
							urlPattern: ({ request, url }) =>
								request.mode === "navigate" && url.pathname.startsWith("/pos"),
							handler: "NetworkFirst",
							options: {
								cacheName: "pos-page-cache",
								networkTimeoutSeconds: 3,
								expiration: {
									maxEntries: 1,
									maxAgeSeconds: 60 * 60 * 24,
								},
							},
						},
					],
					cleanupOutdatedCaches: true,
					skipWaiting: true,
					clientsClaim: true,
				},
				devOptions: {
					enabled: pwaEnabled,
					type: "module",
				},
			}),
	].filter(Boolean)

	return {
		base: isDesktop ? "./" : undefined,
		plugins,
		build: {
			chunkSizeWarningLimit: 1500,
			outDir: isDesktop
				? "../desktop/dist-frontend"
				: "../pos_next/public/pos",
			emptyOutDir: true,
			target: "es2015",
			sourcemap: enableSourceMap,
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
				"@": path.resolve(__dirname, "src"),
				"tailwind.config.js": path.resolve(__dirname, "tailwind.config.js"),
			},
		},
		define: {
			__BUILD_VERSION__: JSON.stringify(buildVersion),
			__POS_TARGET__: JSON.stringify(target),
			__FRAPPE_BASE_URL__: JSON.stringify(baseUrl),
			__SOCKETIO_PORT__: JSON.stringify(socketioPort),
		},
		optimizeDeps: {
			include: ["feather-icons", "highlight.js/lib/core", "qz-tray"],
			esbuildOptions: {
				plugins: [
					{
						name: "ignore-virtual-icons",
						setup(build) {
							build.onResolve({ filter: /^~icons\// }, () => ({
								external: true,
							}))
						},
					},
				],
			},
		},
		server: {
			allowedHosts: true,
			host: true,
			port: 8080,
			fs: {
				allow: [
					path.resolve(__dirname, "../../.."),
					path.resolve(__dirname, ".."),
				],
			},
			warmup: {
				clientFiles: [
					"./src/main.js",
					"./src/pages/POSSale.vue",
					"./src/pages/Login.vue",
				],
			},
			proxy: isDesktop
				? undefined
				: {
						"^/(app|api|assets|files|printview)": {
							target: "http://127.0.0.1:8000",
							ws: true,
							changeOrigin: true,
							secure: false,
							cookieDomainRewrite: "localhost",
							router: (req) => {
								const site_name = req.headers.host.split(":")[0]
								const isLocalhost =
									site_name === "localhost" || site_name === "127.0.0.1"
								const targetHost = isLocalhost ? "127.0.0.1" : site_name
								return `http://${targetHost}:8000`
							},
						},
				  },
		},
	}
})
