import { describe, expect, it, vi } from "vitest"

vi.mock("frappe-ui", () => ({
	createResource: (opts) => ({
		loading: false,
		fetch: async () =>
			opts.onSuccess({
				country_info: {
					Egypt: { code: "eg", isd: "+20" },
					"Heard Island and McDonald Islands": { code: "hm", isd: "+0" },
				},
			}),
	}),
}))
vi.mock("@/utils/logger", () => ({
	logger: { create: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }) },
}))

import { useCountryCodes } from "../useCountryCodes"

describe("useCountryCodes ISD handling", () => {
	it("has no +0 entry and parses +0000000000 without an ISD", async () => {
		const c = useCountryCodes()
		await c.loadCountries()
		expect(c.countries.value.map((x) => x.isd)).toEqual(["+20"])
		expect(c.parsePhoneNumber("+0000000000")).toEqual({ isd: "", number: "0000000000" })
		expect(c.parsePhoneNumber("+201012345678").isd).toBe("+20")
	})
})
