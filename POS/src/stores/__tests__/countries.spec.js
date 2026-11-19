import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

const COUNTRY_INFO = {
	Egypt: { code: "eg", isd: "+20" },
	Australia: { code: "au", isd: "+61" },
	Canada: { code: "ca", isd: "+1" },
	"Cayman Islands": { code: "ky", isd: "+ 345" },
	"Heard Island and McDonald Islands": { code: "hm", isd: "+0" },
	"United States Minor Outlying Islands": { code: "um", isd: null },
}

vi.mock("frappe-ui", () => ({
	createResource: (opts) => ({
		fetch: async () => opts.onSuccess({ country_info: COUNTRY_INFO }),
	}),
}))
vi.mock("@/utils/logger", () => ({
	logger: { create: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }) },
}))

import { useCountriesStore } from "../countries"

describe("countries store ISD handling", () => {
	let store
	beforeEach(async () => {
		setActivePinia(createPinia())
		store = useCountriesStore()
		await store.loadCountries()
	})

	it("drops dummy and missing ISDs from the list", () => {
		const isds = store.countries.map((c) => c.isd)
		expect(isds).not.toContain("+0")
		expect(store.countries.find((c) => c.code === "HM")).toBeUndefined()
		expect(store.countries.find((c) => c.code === "UM")).toBeUndefined()
		expect(store.findCountryByISD("+0")).toBeUndefined()
	})

	it("keeps a real ISD that has a stray space", () => {
		expect(store.findCountryByISD("+345")?.name).toBe("Cayman Islands")
	})

	it("treats +0000000000 as having no ISD", () => {
		expect(store.parsePhoneNumber("+0000000000")).toEqual({ isd: "", number: "0000000000" })
	})

	it("ignores a bogus ISD before a dash", () => {
		expect(store.parsePhoneNumber("+0-1234567")).toEqual({ isd: "", number: "1234567" })
	})

	it("still parses real numbers with and without the dash", () => {
		expect(store.parsePhoneNumber("+20-1012345678")).toEqual({ isd: "+20", number: "1012345678" })
		expect(store.parsePhoneNumber("+201012345678")).toEqual({ isd: "+20", number: "1012345678" })
		expect(store.parsePhoneNumber("+61-412345678").isd).toBe("+61")
	})
})
