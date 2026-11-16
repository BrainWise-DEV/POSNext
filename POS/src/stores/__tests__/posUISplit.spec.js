/** Item/cart split kept as a ratio and clamped on resize. */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

globalThis.__ = (s) => s

const { RIGHT_PANEL_MAX, usePOSUIStore } = await import("../posUI")

describe("posUI split ratio", () => {
	let ui
	beforeEach(() => {
		setActivePinia(createPinia())
		ui = usePOSUIStore()
	})

	it("caps the cart at RIGHT_PANEL_MAX on wide screens", () => {
		ui.updateLayoutBounds(1856)
		expect(1856 - ui.leftPanelWidth).toBe(RIGHT_PANEL_MAX)
	})

	it("keeps the cart at least 360px on narrow desktops", () => {
		ui.updateLayoutBounds(960)
		expect(960 - ui.leftPanelWidth).toBeGreaterThanOrEqual(360)
		expect(ui.leftPanelWidth).toBeGreaterThanOrEqual(320)
	})

	it("follows the container after a resize instead of keeping old pixels", () => {
		ui.updateLayoutBounds(1302)
		ui.setLeftPanelWidth(800, 1302)
		ui.updateLayoutBounds(1856)
		ui.updateLayoutBounds(1302)
		expect(ui.leftPanelWidth).toBe(800)
		ui.updateLayoutBounds(1000)
		expect(ui.leftPanelWidth).toBeCloseTo((800 / 1302) * 1000, 5)
	})

	it("clamps a drag outside the bounds", () => {
		ui.setLeftPanelWidth(100, 1302)
		expect(1302 - ui.leftPanelWidth).toBe(RIGHT_PANEL_MAX)
		ui.setLeftPanelWidth(5000, 1302)
		expect(1302 - ui.leftPanelWidth).toBe(360)
	})
})
