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
 * The URL carries the app's POS asset version (`?v=`, a content hash the /pos page
 * boots with as `window.posnext_asset_versions`, see pos_next/optional_apps.py), so
 * a release is a new URL: the rule can be cache-first and never serves an old copy
 * to a page that boots with the new version. An unversioned URL is not cached.
 *
 * Plain module with no imports: vite.config.js reads it at build time.
 */

/**
 * A versioned `/assets/<app>/pos/...` script, stylesheet or data file of an app other
 * than pos_next. Anchored at the path: Workbox tests same-origin routes against the
 * whole URL, so a query string naming such a path must not match.
 */
export const SATELLITE_POS_ASSET_PATTERN =
	/^(?:https?:\/\/[^/?#]+)?\/assets\/(?!pos_next\/)[^/?#]+\/pos\/[^?#]+\.(?:js|mjs|css|json)\?v=[0-9a-f]+$/i;

/** The version the page booted with for an app's POS assets, if any. */
function assetVersion(app) {
	if (typeof window === "undefined") return "";
	return String(window.posnext_asset_versions?.[app] || "");
}

/** The URL of a satellite app's POS asset (`file` relative to its `public/pos/`). */
export function satellitePosAssetUrl(app, file) {
	const version = assetVersion(app);
	const url = `/assets/${app}/pos/${file}`;
	return version ? `${url}?v=${encodeURIComponent(version)}` : url;
}

/** Workbox runtime-caching rule: one URL per version, so cache-first is safe. */
export const satellitePosAssetCaching = {
	urlPattern: SATELLITE_POS_ASSET_PATTERN,
	handler: "CacheFirst",
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
