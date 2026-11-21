/**
 * G7: the service worker keeps satellite POS scripts (promotions' offline offer
 * strategies) for an offline reload, by pattern, not by one hard-coded file.
 */
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import {
	SATELLITE_POS_ASSET_PATTERN,
	satellitePosAssetCaching,
	satellitePosAssetUrl,
} from "@/utils/offline/satelliteAssets"

const here = dirname(fileURLToPath(import.meta.url))
const matches = (url) => SATELLITE_POS_ASSET_PATTERN.test(url)

describe("satellite POS assets are cached for offline use", () => {
	it("matches the offer strategies the cart loads, and any other satellite's POS script", () => {
		expect(
			satellitePosAssetUrl("posnext_promotions", "offer-strategies.js"),
		).toBe("/assets/posnext_promotions/pos/offer-strategies.js")
		expect(
			matches(
				satellitePosAssetUrl("posnext_promotions", "offer-strategies.js"),
			),
		).toBe(true)
		expect(
			matches(
				"https://pos.example.com/assets/posnext_promotions/pos/offer-strategies.js?v=3",
			),
		).toBe(true)
		expect(matches("/assets/magento_integration/pos/receipt.mjs")).toBe(true)
		expect(matches("/assets/some_app/pos/sub/dir/data.json")).toBe(true)
	})

	it("leaves pos_next's own bundle, other assets and the API alone", () => {
		expect(matches("/assets/pos_next/pos/assets/index-abc.js")).toBe(false)
		expect(matches("/assets/posnext_promotions/js/pricing_rule.js")).toBe(false)
		expect(matches("/assets/posnext_promotions/pos/")).toBe(false)
		expect(
			matches("/api/method/posnext_promotions.api.offers.get_offers"),
		).toBe(false)
		expect(matches("/files/pos/photo.js")).toBe(false)
	})

	it("is served stale-while-revalidate, so an update reaches the next load", () => {
		expect(satellitePosAssetCaching.handler).toBe("StaleWhileRevalidate")
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
