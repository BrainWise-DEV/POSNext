/** Grid/list view mode persisted per user. @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useItemsViewMode } from "../useItemsViewMode"

describe("useItemsViewMode", () => {
	beforeEach(() => {
		localStorage.clear()
		vi.restoreAllMocks()
	})

	it("defaults to grid with no manual choice", () => {
		const { viewMode, userManuallySetView } = useItemsViewMode("a@x.com")
		expect(viewMode.value).toBe("grid")
		expect(userManuallySetView.value).toBe(false)
	})

	it("restores the user's choice as a manual one, per user", () => {
		useItemsViewMode("a@x.com").setViewMode("list")
		const again = useItemsViewMode("a@x.com")
		expect(again.viewMode.value).toBe("list")
		expect(again.userManuallySetView.value).toBe(true)
		expect(useItemsViewMode("b@x.com").viewMode.value).toBe("grid")
	})

	it("ignores unknown stored values", () => {
		localStorage.setItem("pos_next_items_view_mode:a@x.com", "tiles")
		expect(useItemsViewMode("a@x.com").viewMode.value).toBe("grid")
	})

	it("keeps working when storage throws", () => {
		vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
			throw new Error("blocked")
		})
		vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
			throw new Error("blocked")
		})
		const { viewMode, setViewMode } = useItemsViewMode("a@x.com")
		setViewMode("list")
		expect(viewMode.value).toBe("list")
	})
})
