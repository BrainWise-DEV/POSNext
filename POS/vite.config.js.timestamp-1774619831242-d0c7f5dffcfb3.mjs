// vite.config.js
import path from "node:path";
import { promises as fs } from "node:fs";
import vue from "file:///home/nonierp/frappe-bench/apps/pos_next/POS/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import frappeui from "file:///home/nonierp/frappe-bench/apps/pos_next/POS/node_modules/frappe-ui/vite/index.js";
import { defineConfig } from "file:///home/nonierp/frappe-bench/apps/pos_next/POS/node_modules/vite/dist/node/index.js";
import { VitePWA } from "file:///home/nonierp/frappe-bench/apps/pos_next/POS/node_modules/vite-plugin-pwa/dist/index.js";
import { viteStaticCopy } from "file:///home/nonierp/frappe-bench/apps/pos_next/POS/node_modules/vite-plugin-static-copy/dist/index.js";
var __vite_injected_original_dirname = "/home/nonierp/frappe-bench/apps/pos_next/POS";
var buildVersion = process.env.POS_NEXT_BUILD_VERSION || Date.now().toString();
var enableSourceMap = process.env.POS_NEXT_ENABLE_SOURCEMAP === "true";
function posNextBuildVersionPlugin(version) {
  return {
    name: "pos-next-build-version",
    apply: "build",
    async writeBundle() {
      const versionFile = path.resolve(__vite_injected_original_dirname, "../pos_next/public/pos/version.json");
      await fs.mkdir(path.dirname(versionFile), { recursive: true });
      await fs.writeFile(
        versionFile,
        JSON.stringify(
          {
            version,
            timestamp: (/* @__PURE__ */ new Date()).toISOString(),
            buildDate: (/* @__PURE__ */ new Date()).toLocaleDateString("en-US", {
              year: "numeric",
              month: "long",
              day: "numeric"
            })
          },
          null,
          2
        ),
        "utf8"
      );
      console.log(`
\u2713 Build version written: ${version}`);
    }
  };
}
var vite_config_default = defineConfig({
  plugins: [
    posNextBuildVersionPlugin(buildVersion),
    frappeui({
      frappeProxy: true,
      jinjaBootData: true,
      lucideIcons: true,
      buildConfig: {
        indexHtmlPath: "../pos_next/www/pos.html",
        outDir: "../pos_next/public/pos",
        emptyOutDir: true,
        sourcemap: enableSourceMap
      }
    }),
    vue(),
    viteStaticCopy({
      targets: [
        {
          src: "src/workers",
          dest: "."
        }
      ]
    }),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.png", "icon.svg", "icon-maskable.svg"],
      manifest: {
        name: "POSNext",
        short_name: "POSNext",
        description: "Point of Sale system with real-time billing, stock management, and offline support",
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
            purpose: "any"
          },
          {
            src: "/assets/pos_next/pos/icon.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "any"
          },
          {
            src: "/assets/pos_next/pos/icon-maskable.svg",
            sizes: "192x192",
            type: "image/svg+xml",
            purpose: "maskable"
          },
          {
            src: "/assets/pos_next/pos/icon-maskable.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "maskable"
          }
        ]
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff,woff2}"],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        // 3 MB
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
                maxAgeSeconds: 60 * 60 * 24 * 365
                // 1 year
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
            handler: "CacheFirst",
            options: {
              cacheName: "gstatic-fonts-cache",
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365
                // 1 year
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: /\/assets\/pos_next\/pos\/.*/i,
            handler: "CacheFirst",
            options: {
              cacheName: "pos-assets-cache",
              expiration: {
                maxEntries: 500,
                maxAgeSeconds: 60 * 60 * 24 * 30
                // 30 days
              }
            }
          },
          // Cache product images with StaleWhileRevalidate for better UX
          {
            urlPattern: /\/files\/.*\.(jpg|jpeg|png|gif|webp|svg)$/i,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "product-images-cache",
              expiration: {
                maxEntries: 200,
                // Cache up to 200 product images
                maxAgeSeconds: 60 * 60 * 24 * 7
                // 7 days
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: /\/api\/.*/i,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              networkTimeoutSeconds: 10,
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24
                // 24 hours
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: ({ request, url }) => request.mode === "navigate" && url.pathname.startsWith("/pos"),
            handler: "NetworkFirst",
            options: {
              cacheName: "pos-page-cache",
              networkTimeoutSeconds: 3,
              expiration: {
                maxEntries: 1,
                maxAgeSeconds: 60 * 60 * 24
                // 24 hours
              }
            }
          }
        ],
        cleanupOutdatedCaches: true,
        skipWaiting: true,
        clientsClaim: true
      },
      devOptions: {
        enabled: true,
        type: "module"
      }
    })
  ],
  build: {
    chunkSizeWarningLimit: 1500,
    outDir: "../pos_next/public/pos",
    emptyOutDir: true,
    target: "es2015",
    sourcemap: enableSourceMap
  },
  worker: {
    format: "es",
    rollupOptions: {
      output: {
        format: "es"
      }
    }
  },
  resolve: {
    alias: {
      "@": path.resolve(__vite_injected_original_dirname, "src"),
      "tailwind.config.js": path.resolve(__vite_injected_original_dirname, "tailwind.config.js")
    }
  },
  define: {
    __BUILD_VERSION__: JSON.stringify(buildVersion)
  },
  optimizeDeps: {
    include: [
      "feather-icons",
      "showdown",
      "highlight.js/lib/core",
      "interactjs",
      "qz-tray"
    ]
  },
  server: {
    allowedHosts: true,
    port: 8080,
    proxy: {
      "^/(app|api|assets|files|printview)": {
        target: "http://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
        secure: false,
        cookieDomainRewrite: "localhost",
        router: (req) => {
          const site_name = req.headers.host.split(":")[0];
          const isLocalhost = site_name === "localhost" || site_name === "127.0.0.1";
          const targetHost = isLocalhost ? "127.0.0.1" : site_name;
          return `http://${targetHost}:8000`;
        }
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvaG9tZS9ub25pZXJwL2ZyYXBwZS1iZW5jaC9hcHBzL3Bvc19uZXh0L1BPU1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL2hvbWUvbm9uaWVycC9mcmFwcGUtYmVuY2gvYXBwcy9wb3NfbmV4dC9QT1Mvdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL2hvbWUvbm9uaWVycC9mcmFwcGUtYmVuY2gvYXBwcy9wb3NfbmV4dC9QT1Mvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgcGF0aCBmcm9tIFwibm9kZTpwYXRoXCJcbmltcG9ydCB7IHByb21pc2VzIGFzIGZzIH0gZnJvbSBcIm5vZGU6ZnNcIlxuaW1wb3J0IHZ1ZSBmcm9tIFwiQHZpdGVqcy9wbHVnaW4tdnVlXCJcbmltcG9ydCBmcmFwcGV1aSBmcm9tIFwiZnJhcHBlLXVpL3ZpdGVcIlxuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSBcInZpdGVcIlxuaW1wb3J0IHsgVml0ZVBXQSB9IGZyb20gXCJ2aXRlLXBsdWdpbi1wd2FcIlxuaW1wb3J0IHsgdml0ZVN0YXRpY0NvcHkgfSBmcm9tIFwidml0ZS1wbHVnaW4tc3RhdGljLWNvcHlcIlxuXG4vLyBHZXQgYnVpbGQgdmVyc2lvbiBmcm9tIGVudmlyb25tZW50IG9yIHVzZSB0aW1lc3RhbXBcbmNvbnN0IGJ1aWxkVmVyc2lvbiA9IHByb2Nlc3MuZW52LlBPU19ORVhUX0JVSUxEX1ZFUlNJT04gfHwgRGF0ZS5ub3coKS50b1N0cmluZygpXG5jb25zdCBlbmFibGVTb3VyY2VNYXAgPSBwcm9jZXNzLmVudi5QT1NfTkVYVF9FTkFCTEVfU09VUkNFTUFQID09PSBcInRydWVcIlxuXG4vKipcbiAqIFZpdGUgcGx1Z2luIHRvIHdyaXRlIGJ1aWxkIHZlcnNpb24gdG8gdmVyc2lvbi5qc29uIGZpbGVcbiAqIFRoaXMgZW5hYmxlcyBjYWNoZSBidXN0aW5nIGFuZCB2ZXJzaW9uIHRyYWNraW5nXG4gKi9cbmZ1bmN0aW9uIHBvc05leHRCdWlsZFZlcnNpb25QbHVnaW4odmVyc2lvbikge1xuXHRyZXR1cm4ge1xuXHRcdG5hbWU6IFwicG9zLW5leHQtYnVpbGQtdmVyc2lvblwiLFxuXHRcdGFwcGx5OiBcImJ1aWxkXCIsXG5cdFx0YXN5bmMgd3JpdGVCdW5kbGUoKSB7XG5cdFx0XHRjb25zdCB2ZXJzaW9uRmlsZSA9IHBhdGgucmVzb2x2ZShfX2Rpcm5hbWUsIFwiLi4vcG9zX25leHQvcHVibGljL3Bvcy92ZXJzaW9uLmpzb25cIilcblx0XHRcdGF3YWl0IGZzLm1rZGlyKHBhdGguZGlybmFtZSh2ZXJzaW9uRmlsZSksIHsgcmVjdXJzaXZlOiB0cnVlIH0pXG5cdFx0XHRhd2FpdCBmcy53cml0ZUZpbGUoXG5cdFx0XHRcdHZlcnNpb25GaWxlLFxuXHRcdFx0XHRKU09OLnN0cmluZ2lmeShcblx0XHRcdFx0XHR7XG5cdFx0XHRcdFx0XHR2ZXJzaW9uLFxuXHRcdFx0XHRcdFx0dGltZXN0YW1wOiBuZXcgRGF0ZSgpLnRvSVNPU3RyaW5nKCksXG5cdFx0XHRcdFx0XHRidWlsZERhdGU6IG5ldyBEYXRlKCkudG9Mb2NhbGVEYXRlU3RyaW5nKFwiZW4tVVNcIiwge1xuXHRcdFx0XHRcdFx0XHR5ZWFyOiBcIm51bWVyaWNcIixcblx0XHRcdFx0XHRcdFx0bW9udGg6IFwibG9uZ1wiLFxuXHRcdFx0XHRcdFx0XHRkYXk6IFwibnVtZXJpY1wiLFxuXHRcdFx0XHRcdFx0fSksXG5cdFx0XHRcdFx0fSxcblx0XHRcdFx0XHRudWxsLFxuXHRcdFx0XHRcdDJcblx0XHRcdFx0KSxcblx0XHRcdFx0XCJ1dGY4XCJcblx0XHRcdClcblx0XHRcdGNvbnNvbGUubG9nKGBcXG5cdTI3MTMgQnVpbGQgdmVyc2lvbiB3cml0dGVuOiAke3ZlcnNpb259YClcblx0XHR9LFxuXHR9XG59XG5cbi8vIGh0dHBzOi8vdml0ZWpzLmRldi9jb25maWcvXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuXHRwbHVnaW5zOiBbXG5cdFx0cG9zTmV4dEJ1aWxkVmVyc2lvblBsdWdpbihidWlsZFZlcnNpb24pLFxuXHRcdGZyYXBwZXVpKHtcblx0XHRcdGZyYXBwZVByb3h5OiB0cnVlLFxuXHRcdFx0amluamFCb290RGF0YTogdHJ1ZSxcblx0XHRcdGx1Y2lkZUljb25zOiB0cnVlLFxuXHRcdFx0YnVpbGRDb25maWc6IHtcblx0XHRcdFx0aW5kZXhIdG1sUGF0aDogXCIuLi9wb3NfbmV4dC93d3cvcG9zLmh0bWxcIixcblx0XHRcdFx0b3V0RGlyOiBcIi4uL3Bvc19uZXh0L3B1YmxpYy9wb3NcIixcblx0XHRcdFx0ZW1wdHlPdXREaXI6IHRydWUsXG5cdFx0XHRcdHNvdXJjZW1hcDogZW5hYmxlU291cmNlTWFwLFxuXHRcdFx0fSxcblx0XHR9KSxcblx0XHR2dWUoKSxcblx0XHR2aXRlU3RhdGljQ29weSh7XG5cdFx0XHR0YXJnZXRzOiBbXG5cdFx0XHRcdHtcblx0XHRcdFx0XHRzcmM6IFwic3JjL3dvcmtlcnNcIixcblx0XHRcdFx0XHRkZXN0OiBcIi5cIixcblx0XHRcdFx0fSxcblx0XHRcdF0sXG5cdFx0fSksXG5cdFx0Vml0ZVBXQSh7XG5cdFx0XHRyZWdpc3RlclR5cGU6IFwiYXV0b1VwZGF0ZVwiLFxuXHRcdFx0aW5jbHVkZUFzc2V0czogW1wiZmF2aWNvbi5wbmdcIiwgXCJpY29uLnN2Z1wiLCBcImljb24tbWFza2FibGUuc3ZnXCJdLFxuXHRcdFx0bWFuaWZlc3Q6IHtcblx0XHRcdFx0bmFtZTogXCJQT1NOZXh0XCIsXG5cdFx0XHRcdHNob3J0X25hbWU6IFwiUE9TTmV4dFwiLFxuXHRcdFx0XHRkZXNjcmlwdGlvbjpcblx0XHRcdFx0XHRcIlBvaW50IG9mIFNhbGUgc3lzdGVtIHdpdGggcmVhbC10aW1lIGJpbGxpbmcsIHN0b2NrIG1hbmFnZW1lbnQsIGFuZCBvZmZsaW5lIHN1cHBvcnRcIixcblx0XHRcdFx0dGhlbWVfY29sb3I6IFwiIzRGNDZFNVwiLFxuXHRcdFx0XHRiYWNrZ3JvdW5kX2NvbG9yOiBcIiNmZmZmZmZcIixcblx0XHRcdFx0ZGlzcGxheTogXCJzdGFuZGFsb25lXCIsXG5cdFx0XHRcdHNjb3BlOiBcIi9hc3NldHMvcG9zX25leHQvcG9zL1wiLFxuXHRcdFx0XHRzdGFydF91cmw6IFwiL3Bvc1wiLFxuXHRcdFx0XHRpY29uczogW1xuXHRcdFx0XHRcdHtcblx0XHRcdFx0XHRcdHNyYzogXCIvYXNzZXRzL3Bvc19uZXh0L3Bvcy9pY29uLnN2Z1wiLFxuXHRcdFx0XHRcdFx0c2l6ZXM6IFwiMTkyeDE5MlwiLFxuXHRcdFx0XHRcdFx0dHlwZTogXCJpbWFnZS9zdmcreG1sXCIsXG5cdFx0XHRcdFx0XHRwdXJwb3NlOiBcImFueVwiLFxuXHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0c3JjOiBcIi9hc3NldHMvcG9zX25leHQvcG9zL2ljb24uc3ZnXCIsXG5cdFx0XHRcdFx0XHRzaXplczogXCI1MTJ4NTEyXCIsXG5cdFx0XHRcdFx0XHR0eXBlOiBcImltYWdlL3N2Zyt4bWxcIixcblx0XHRcdFx0XHRcdHB1cnBvc2U6IFwiYW55XCIsXG5cdFx0XHRcdFx0fSxcblx0XHRcdFx0XHR7XG5cdFx0XHRcdFx0XHRzcmM6IFwiL2Fzc2V0cy9wb3NfbmV4dC9wb3MvaWNvbi1tYXNrYWJsZS5zdmdcIixcblx0XHRcdFx0XHRcdHNpemVzOiBcIjE5MngxOTJcIixcblx0XHRcdFx0XHRcdHR5cGU6IFwiaW1hZ2Uvc3ZnK3htbFwiLFxuXHRcdFx0XHRcdFx0cHVycG9zZTogXCJtYXNrYWJsZVwiLFxuXHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0c3JjOiBcIi9hc3NldHMvcG9zX25leHQvcG9zL2ljb24tbWFza2FibGUuc3ZnXCIsXG5cdFx0XHRcdFx0XHRzaXplczogXCI1MTJ4NTEyXCIsXG5cdFx0XHRcdFx0XHR0eXBlOiBcImltYWdlL3N2Zyt4bWxcIixcblx0XHRcdFx0XHRcdHB1cnBvc2U6IFwibWFza2FibGVcIixcblx0XHRcdFx0XHR9LFxuXHRcdFx0XHRdLFxuXHRcdFx0fSxcblx0XHRcdHdvcmtib3g6IHtcblx0XHRcdFx0Z2xvYlBhdHRlcm5zOiBbXCIqKi8qLntqcyxjc3MsaHRtbCxpY28scG5nLHN2Zyx3b2ZmLHdvZmYyfVwiXSxcblx0XHRcdFx0bWF4aW11bUZpbGVTaXplVG9DYWNoZUluQnl0ZXM6IDQgKiAxMDI0ICogMTAyNCwgLy8gMyBNQlxuXHRcdFx0XHRuYXZpZ2F0ZUZhbGxiYWNrOiBudWxsLFxuXHRcdFx0XHRuYXZpZ2F0ZUZhbGxiYWNrRGVueWxpc3Q6IFsvXlxcL2FwaS8sIC9eXFwvYXBwL10sXG5cdFx0XHRcdHJ1bnRpbWVDYWNoaW5nOiBbXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0dXJsUGF0dGVybjogL15odHRwczpcXC9cXC9mb250c1xcLmdvb2dsZWFwaXNcXC5jb21cXC8uKi9pLFxuXHRcdFx0XHRcdFx0aGFuZGxlcjogXCJDYWNoZUZpcnN0XCIsXG5cdFx0XHRcdFx0XHRvcHRpb25zOiB7XG5cdFx0XHRcdFx0XHRcdGNhY2hlTmFtZTogXCJnb29nbGUtZm9udHMtY2FjaGVcIixcblx0XHRcdFx0XHRcdFx0ZXhwaXJhdGlvbjoge1xuXHRcdFx0XHRcdFx0XHRcdG1heEVudHJpZXM6IDEwLFxuXHRcdFx0XHRcdFx0XHRcdG1heEFnZVNlY29uZHM6IDYwICogNjAgKiAyNCAqIDM2NSwgLy8gMSB5ZWFyXG5cdFx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0XHRcdGNhY2hlYWJsZVJlc3BvbnNlOiB7XG5cdFx0XHRcdFx0XHRcdFx0c3RhdHVzZXM6IFswLCAyMDBdLFxuXHRcdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdFx0fSxcblx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdHtcblx0XHRcdFx0XHRcdHVybFBhdHRlcm46IC9eaHR0cHM6XFwvXFwvZm9udHNcXC5nc3RhdGljXFwuY29tXFwvLiovaSxcblx0XHRcdFx0XHRcdGhhbmRsZXI6IFwiQ2FjaGVGaXJzdFwiLFxuXHRcdFx0XHRcdFx0b3B0aW9uczoge1xuXHRcdFx0XHRcdFx0XHRjYWNoZU5hbWU6IFwiZ3N0YXRpYy1mb250cy1jYWNoZVwiLFxuXHRcdFx0XHRcdFx0XHRleHBpcmF0aW9uOiB7XG5cdFx0XHRcdFx0XHRcdFx0bWF4RW50cmllczogMTAsXG5cdFx0XHRcdFx0XHRcdFx0bWF4QWdlU2Vjb25kczogNjAgKiA2MCAqIDI0ICogMzY1LCAvLyAxIHllYXJcblx0XHRcdFx0XHRcdFx0fSxcblx0XHRcdFx0XHRcdFx0Y2FjaGVhYmxlUmVzcG9uc2U6IHtcblx0XHRcdFx0XHRcdFx0XHRzdGF0dXNlczogWzAsIDIwMF0sXG5cdFx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0dXJsUGF0dGVybjogL1xcL2Fzc2V0c1xcL3Bvc19uZXh0XFwvcG9zXFwvLiovaSxcblx0XHRcdFx0XHRcdGhhbmRsZXI6IFwiQ2FjaGVGaXJzdFwiLFxuXHRcdFx0XHRcdFx0b3B0aW9uczoge1xuXHRcdFx0XHRcdFx0XHRjYWNoZU5hbWU6IFwicG9zLWFzc2V0cy1jYWNoZVwiLFxuXHRcdFx0XHRcdFx0XHRleHBpcmF0aW9uOiB7XG5cdFx0XHRcdFx0XHRcdFx0bWF4RW50cmllczogNTAwLFxuXHRcdFx0XHRcdFx0XHRcdG1heEFnZVNlY29uZHM6IDYwICogNjAgKiAyNCAqIDMwLCAvLyAzMCBkYXlzXG5cdFx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0Ly8gQ2FjaGUgcHJvZHVjdCBpbWFnZXMgd2l0aCBTdGFsZVdoaWxlUmV2YWxpZGF0ZSBmb3IgYmV0dGVyIFVYXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0dXJsUGF0dGVybjogL1xcL2ZpbGVzXFwvLipcXC4oanBnfGpwZWd8cG5nfGdpZnx3ZWJwfHN2ZykkL2ksXG5cdFx0XHRcdFx0XHRoYW5kbGVyOiBcIlN0YWxlV2hpbGVSZXZhbGlkYXRlXCIsXG5cdFx0XHRcdFx0XHRvcHRpb25zOiB7XG5cdFx0XHRcdFx0XHRcdGNhY2hlTmFtZTogXCJwcm9kdWN0LWltYWdlcy1jYWNoZVwiLFxuXHRcdFx0XHRcdFx0XHRleHBpcmF0aW9uOiB7XG5cdFx0XHRcdFx0XHRcdFx0bWF4RW50cmllczogMjAwLCAvLyBDYWNoZSB1cCB0byAyMDAgcHJvZHVjdCBpbWFnZXNcblx0XHRcdFx0XHRcdFx0XHRtYXhBZ2VTZWNvbmRzOiA2MCAqIDYwICogMjQgKiA3LCAvLyA3IGRheXNcblx0XHRcdFx0XHRcdFx0fSxcblx0XHRcdFx0XHRcdFx0Y2FjaGVhYmxlUmVzcG9uc2U6IHtcblx0XHRcdFx0XHRcdFx0XHRzdGF0dXNlczogWzAsIDIwMF0sXG5cdFx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0e1xuXHRcdFx0XHRcdFx0dXJsUGF0dGVybjogL1xcL2FwaVxcLy4qL2ksXG5cdFx0XHRcdFx0XHRoYW5kbGVyOiBcIk5ldHdvcmtGaXJzdFwiLFxuXHRcdFx0XHRcdFx0b3B0aW9uczoge1xuXHRcdFx0XHRcdFx0XHRjYWNoZU5hbWU6IFwiYXBpLWNhY2hlXCIsXG5cdFx0XHRcdFx0XHRcdG5ldHdvcmtUaW1lb3V0U2Vjb25kczogMTAsXG5cdFx0XHRcdFx0XHRcdGV4cGlyYXRpb246IHtcblx0XHRcdFx0XHRcdFx0XHRtYXhFbnRyaWVzOiAxMDAsXG5cdFx0XHRcdFx0XHRcdFx0bWF4QWdlU2Vjb25kczogNjAgKiA2MCAqIDI0LCAvLyAyNCBob3Vyc1xuXHRcdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdFx0XHRjYWNoZWFibGVSZXNwb25zZToge1xuXHRcdFx0XHRcdFx0XHRcdHN0YXR1c2VzOiBbMCwgMjAwXSxcblx0XHRcdFx0XHRcdFx0fSxcblx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0fSxcblx0XHRcdFx0XHR7XG5cdFx0XHRcdFx0XHR1cmxQYXR0ZXJuOiAoeyByZXF1ZXN0LCB1cmwgfSkgPT5cblx0XHRcdFx0XHRcdFx0cmVxdWVzdC5tb2RlID09PSBcIm5hdmlnYXRlXCIgJiYgdXJsLnBhdGhuYW1lLnN0YXJ0c1dpdGgoXCIvcG9zXCIpLFxuXHRcdFx0XHRcdFx0aGFuZGxlcjogXCJOZXR3b3JrRmlyc3RcIixcblx0XHRcdFx0XHRcdG9wdGlvbnM6IHtcblx0XHRcdFx0XHRcdFx0Y2FjaGVOYW1lOiBcInBvcy1wYWdlLWNhY2hlXCIsXG5cdFx0XHRcdFx0XHRcdG5ldHdvcmtUaW1lb3V0U2Vjb25kczogMyxcblx0XHRcdFx0XHRcdFx0ZXhwaXJhdGlvbjoge1xuXHRcdFx0XHRcdFx0XHRcdG1heEVudHJpZXM6IDEsXG5cdFx0XHRcdFx0XHRcdFx0bWF4QWdlU2Vjb25kczogNjAgKiA2MCAqIDI0LCAvLyAyNCBob3Vyc1xuXHRcdFx0XHRcdFx0XHR9LFxuXHRcdFx0XHRcdFx0fSxcblx0XHRcdFx0XHR9LFxuXHRcdFx0XHRdLFxuXHRcdFx0XHRjbGVhbnVwT3V0ZGF0ZWRDYWNoZXM6IHRydWUsXG5cdFx0XHRcdHNraXBXYWl0aW5nOiB0cnVlLFxuXHRcdFx0XHRjbGllbnRzQ2xhaW06IHRydWUsXG5cdFx0XHR9LFxuXHRcdFx0ZGV2T3B0aW9uczoge1xuXHRcdFx0XHRlbmFibGVkOiB0cnVlLFxuXHRcdFx0XHR0eXBlOiBcIm1vZHVsZVwiLFxuXHRcdFx0fSxcblx0XHR9KSxcblx0XSxcblx0YnVpbGQ6IHtcblx0XHRjaHVua1NpemVXYXJuaW5nTGltaXQ6IDE1MDAsXG5cdFx0b3V0RGlyOiBcIi4uL3Bvc19uZXh0L3B1YmxpYy9wb3NcIixcblx0XHRlbXB0eU91dERpcjogdHJ1ZSxcblx0XHR0YXJnZXQ6IFwiZXMyMDE1XCIsXG5cdFx0c291cmNlbWFwOiBlbmFibGVTb3VyY2VNYXAsXG5cdH0sXG5cdHdvcmtlcjoge1xuXHRcdGZvcm1hdDogXCJlc1wiLFxuXHRcdHJvbGx1cE9wdGlvbnM6IHtcblx0XHRcdG91dHB1dDoge1xuXHRcdFx0XHRmb3JtYXQ6IFwiZXNcIixcblx0XHRcdH0sXG5cdFx0fSxcblx0fSxcblx0cmVzb2x2ZToge1xuXHRcdGFsaWFzOiB7XG5cdFx0XHRcIkBcIjogcGF0aC5yZXNvbHZlKF9fZGlybmFtZSwgXCJzcmNcIiksXG5cdFx0XHRcInRhaWx3aW5kLmNvbmZpZy5qc1wiOiBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCBcInRhaWx3aW5kLmNvbmZpZy5qc1wiKSxcblx0XHR9LFxuXHR9LFxuXHRkZWZpbmU6IHtcblx0XHRfX0JVSUxEX1ZFUlNJT05fXzogSlNPTi5zdHJpbmdpZnkoYnVpbGRWZXJzaW9uKSxcblx0fSxcblx0b3B0aW1pemVEZXBzOiB7XG5cdFx0aW5jbHVkZTogW1xuXHRcdFx0XCJmZWF0aGVyLWljb25zXCIsXG5cdFx0XHRcInNob3dkb3duXCIsXG5cdFx0XHRcImhpZ2hsaWdodC5qcy9saWIvY29yZVwiLFxuXHRcdFx0XCJpbnRlcmFjdGpzXCIsXG5cdFx0XHRcInF6LXRyYXlcIixcblx0XHRdLFxuXHR9LFxuXHRzZXJ2ZXI6IHtcblx0XHRhbGxvd2VkSG9zdHM6IHRydWUsXG5cdFx0cG9ydDogODA4MCxcblx0XHRwcm94eToge1xuXHRcdFx0XCJeLyhhcHB8YXBpfGFzc2V0c3xmaWxlc3xwcmludHZpZXcpXCI6IHtcblx0XHRcdFx0dGFyZ2V0OiBcImh0dHA6Ly8xMjcuMC4wLjE6ODAwMFwiLFxuXHRcdFx0XHR3czogdHJ1ZSxcblx0XHRcdFx0Y2hhbmdlT3JpZ2luOiB0cnVlLFxuXHRcdFx0XHRzZWN1cmU6IGZhbHNlLFxuXHRcdFx0XHRjb29raWVEb21haW5SZXdyaXRlOiBcImxvY2FsaG9zdFwiLFxuXHRcdFx0XHRyb3V0ZXI6IChyZXEpID0+IHtcblx0XHRcdFx0XHRjb25zdCBzaXRlX25hbWUgPSByZXEuaGVhZGVycy5ob3N0LnNwbGl0KFwiOlwiKVswXVxuXHRcdFx0XHRcdC8vIFN1cHBvcnQgYm90aCBsb2NhbGhvc3QgYW5kIDEyNy4wLjAuMVxuXHRcdFx0XHRcdGNvbnN0IGlzTG9jYWxob3N0ID1cblx0XHRcdFx0XHRcdHNpdGVfbmFtZSA9PT0gXCJsb2NhbGhvc3RcIiB8fCBzaXRlX25hbWUgPT09IFwiMTI3LjAuMC4xXCJcblx0XHRcdFx0XHRjb25zdCB0YXJnZXRIb3N0ID0gaXNMb2NhbGhvc3QgPyBcIjEyNy4wLjAuMVwiIDogc2l0ZV9uYW1lXG5cdFx0XHRcdFx0cmV0dXJuIGBodHRwOi8vJHt0YXJnZXRIb3N0fTo4MDAwYFxuXHRcdFx0XHR9LFxuXHRcdFx0fSxcblx0XHR9LFxuXHR9LFxufSlcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBc1QsT0FBTyxVQUFVO0FBQ3ZVLFNBQVMsWUFBWSxVQUFVO0FBQy9CLE9BQU8sU0FBUztBQUNoQixPQUFPLGNBQWM7QUFDckIsU0FBUyxvQkFBb0I7QUFDN0IsU0FBUyxlQUFlO0FBQ3hCLFNBQVMsc0JBQXNCO0FBTi9CLElBQU0sbUNBQW1DO0FBU3pDLElBQU0sZUFBZSxRQUFRLElBQUksMEJBQTBCLEtBQUssSUFBSSxFQUFFLFNBQVM7QUFDL0UsSUFBTSxrQkFBa0IsUUFBUSxJQUFJLDhCQUE4QjtBQU1sRSxTQUFTLDBCQUEwQixTQUFTO0FBQzNDLFNBQU87QUFBQSxJQUNOLE1BQU07QUFBQSxJQUNOLE9BQU87QUFBQSxJQUNQLE1BQU0sY0FBYztBQUNuQixZQUFNLGNBQWMsS0FBSyxRQUFRLGtDQUFXLHFDQUFxQztBQUNqRixZQUFNLEdBQUcsTUFBTSxLQUFLLFFBQVEsV0FBVyxHQUFHLEVBQUUsV0FBVyxLQUFLLENBQUM7QUFDN0QsWUFBTSxHQUFHO0FBQUEsUUFDUjtBQUFBLFFBQ0EsS0FBSztBQUFBLFVBQ0o7QUFBQSxZQUNDO0FBQUEsWUFDQSxZQUFXLG9CQUFJLEtBQUssR0FBRSxZQUFZO0FBQUEsWUFDbEMsWUFBVyxvQkFBSSxLQUFLLEdBQUUsbUJBQW1CLFNBQVM7QUFBQSxjQUNqRCxNQUFNO0FBQUEsY0FDTixPQUFPO0FBQUEs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
