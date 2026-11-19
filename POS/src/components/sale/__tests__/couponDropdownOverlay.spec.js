/**
 * Coupon/promotion filter dropdowns must teleport above the management overlay.
 * frappe-ui FormControl select portals at z-100; this dialog is z-300.
 * @vitest-environment node
 */
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

function source(rel) {
	return readFileSync(path.resolve(__dirname, rel), "utf8")
}

describe("promotion overlay dropdown stacking", () => {
	it("uses SelectInput for coupon status and type filters", () => {
		const coupon = source("../CouponManagement.vue")

		expect(coupon).toMatch(/<SelectInput[\s\S]{0,80}v-model="filterStatus"/)
		expect(coupon).toMatch(/<SelectInput[\s\S]{0,80}v-model="filterType"/)
		expect(coupon).not.toMatch(
			/v-model="filterStatus"[\s\S]{0,80}type="select"/,
		)
		expect(coupon).not.toMatch(/v-model="filterType"[\s\S]{0,80}type="select"/)
	})

	it("uses SelectInput for the promotions status filter", () => {
		const promo = source("../PromotionManagement.vue")

		expect(promo).toMatch(/<SelectInput[\s\S]{0,80}v-model="filterStatus"/)
		expect(promo).not.toMatch(/v-model="filterStatus"[\s\S]{0,80}type="select"/)
	})

	it("raises portaled frappe-ui select menus above POS overlays", () => {
		const css = source("../../../index.css")

		expect(css).toMatch(/--z-dropdown:\s*10000/)
		expect(css).toContain("[data-reka-popper-content-wrapper]")
		expect(css).toContain("z-index: var(--z-dropdown) !important")
	})
})
