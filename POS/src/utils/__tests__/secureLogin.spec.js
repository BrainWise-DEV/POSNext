import { describe, expect, it } from "vitest"
import { canLogin } from "@/utils/secureLogin"

describe("canLogin", () => {
	it("allows a secure context (HTTPS or localhost)", () => {
		expect(canLogin({ isSecureContext: true })).toBe(true)
	})

	it("blocks plain http outside dev mode", () => {
		expect(canLogin({ isSecureContext: false })).toBe(false)
	})

	it("allows plain http in frontend or backend dev mode", () => {
		expect(canLogin({ isSecureContext: false, frontendDev: true })).toBe(true)
		expect(canLogin({ isSecureContext: false, backendDev: 1 })).toBe(true)
	})
})
