/**
 * Where optional (satellite) apps serve the scripts the POS loads at runtime, and
 * the service-worker rule that keeps them for offline use.
 *
 * A satellite ships its POS scripts under its own `public/pos/` directory, which
 * Frappe serves at `/assets/<app>/pos/...` (posnext_promotions' offer strategies
 * are one). pos_next's own bundle lives at `/assets/pos_next/pos/` and has its own
 * cache rule, so it is left out here. Without this rule a reload while offline
 * could not load any satellite script, and every promotions offer strategy
 * (Accumulative, Min/Max, Gift Pool, GWP) would be missing offline (G7).
 *
 * Plain module with no imports: vite.config.js reads it at build time.
 */

/** Any `/assets/<app>/pos/...` script, stylesheet or data file of an app other than pos_next. */
export const SATELLITE_POS_ASSET_PATTERN = /\/assets\/(?!pos_next\/)[^/]+\/pos\/.+\.(?:js|mjs|css|json)(?:\?.*)?$/i;

/** The URL of a satellite app's POS asset (`file` relative to its `public/pos/`). */
export function satellitePosAssetUrl(app, file) {
	return `/assets/${app}/pos/${file}`;
}

/** Workbox runtime-caching rule: served from cache at once, refreshed in the background. */
export const satellitePosAssetCaching = {
	urlPattern: SATELLITE_POS_ASSET_PATTERN,
	handler: "StaleWhileRevalidate",
	options: {
		cacheName: "pos-satellite-assets-cache",
		expiration: {
			maxEntries: 50,
			maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
		},
		cacheableResponse: {
			statuses: [0, 200],
		},
	},
};
