/**
 * G7: the service worker keeps satellite POS scripts (promotions' offline offer
 * strategies) for an offline reload, by pattern, not by one hard-coded file, and
 * one URL per asset version, so cache-first never serves a stale release.
 * @vitest-environment jsdom
 */
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { afterEach, describe, expect, it } from "vitest"
import {
	SATELLITE_POS_ASSET_PATTERN,
	satellitePosAssetCaching,
	satellitePosAssetUrl,
} from "@/utils/offline/satelliteAssets"

const here = dirname(fileURLToPath(import.meta.url))
const matches = (url) => SATELLITE_POS_ASSET_PATTERN.test(url)

afterEach(() => {
	delete window.posnext_asset_versions
})

describe("satellite POS assets are cached for offline use", () => {
	it("the strategy URL carries the version the page booted with", () => {
		window.posnext_asset_versions = { posnext_promotions: "0a1b2c3d4e5f" }
		const url = satellitePosAssetUrl(
			"posnext_promotions",
			"offer-strategies.js",
		)
		expect(url).toBe(
			"/assets/posnext_promotions/pos/offer-strategies.js?v=0a1b2c3d4e5f",
		)
		expect(matches(url)).toBe(true)
		expect(matches(`https://pos.example.com${url}`)).toBe(true)
	})

	it("matches any satellite's versioned POS script", () => {
		expect(
			matches("/assets/magento_integration/pos/receipt.mjs?v=abc123"),
		).toBe(true)
		expect(matches("/assets/some_app/pos/sub/dir/data.json?v=ff00")).toBe(true)
	})

	it("an unversioned URL is not cached (it could be a stale release)", () => {
		const url = satellitePosAssetUrl(
			"posnext_promotions",
			"offer-strategies.js",
		)
		expect(url).toBe("/assets/posnext_promotions/pos/offer-strategies.js")
		expect(matches(url)).toBe(false)
	})

	it("leaves pos_next's own bundle, other assets, the API and look-alike query strings alone", () => {
		expect(matches("/assets/pos_next/pos/assets/index-abc.js?v=1")).toBe(false)
		expect(matches("/assets/posnext_promotions/js/pricing_rule.js?v=1")).toBe(
			false,
		)
		expect(
			matches("/api/method/posnext_promotions.api.offers.get_offers"),
		).toBe(false)
		expect(matches("/files/pos/photo.js?v=1")).toBe(false)
		// Anchored (m-4): a path in the query string of another request does not match.
		expect(matches("/api/method/x?u=/assets/a/pos/b.js?v=1")).toBe(false)
		expect(
			matches("https://pos.example.com/api/method/x?u=/assets/a/pos/b.js?v=1"),
		).toBe(false)
	})

	it("is served cache-first: one URL per version", () => {
		expect(satellitePosAssetCaching.handler).toBe("CacheFirst")
		expect(satellitePosAssetCaching.urlPattern).toBe(
			SATELLITE_POS_ASSET_PATTERN,
		)
	})

	it("is one of the service worker's runtime caching rules (vite.config.js)", () => {
		const config = readFileSync(
			resolve(here, "../../../vite.config.js"),
			"utf8",
		)
		expect(config).toMatch(
			/import \{ satellitePosAssetCaching \} from "\.\/src\/utils\/offline\/satelliteAssets\.js"/,
		)
		const runtime = config.slice(config.indexOf("runtimeCaching: ["))
		expect(runtime.slice(0, runtime.indexOf("cleanupOutdatedCaches"))).toMatch(
			/^\s*satellitePosAssetCaching,$/m,
		)
	})
})
