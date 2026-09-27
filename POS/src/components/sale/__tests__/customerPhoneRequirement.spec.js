/**
 * Customer phone requirement must be governed by POS Settings while preserving
 * the existing phone + country-code validation when a number is entered.
 * @vitest-environment node
 */
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

function source(rel) {
	return readFileSync(path.resolve(__dirname, rel), "utf8")
}

describe("customer phone requirement", () => {
	it("defines a default-on POS Settings field", () => {
		const settings = source("../../../../../pos_next/pos_next/doctype/pos_settings/pos_settings.json")
		expect(settings).toContain('"fieldname": "require_customer_phone"')
		expect(settings).toMatch(/"require_customer_phone"[\s\S]{0,140}"default": "1"|"default": "1"[\s\S]{0,140}"require_customer_phone"/)
	})

	it("includes the phone policy in shared bootstrap settings", () => {
		const constants = source("../../../../../pos_next/api/constants.py")
		expect(constants).toContain('"require_customer_phone"')
		expect(constants).toContain('"require_customer_phone": 1')
	})

	it("exposes the setting through the POS settings store", () => {
		const store = source("../../../stores/posSettings.js")
		expect(store).toContain("require_customer_phone: 1")
		expect(store).toContain("const requireCustomerPhone = computed")
		expect(store).toContain("requireCustomerPhone,")
	})

	it("allows blank phone only when the setting is disabled", () => {
		const dialog = source("../CreateCustomerDialog.vue")
		expect(dialog).toContain('v-if="requireCustomerPhone"')
		expect(dialog).toContain(':required="requireCustomerPhone"')
		expect(dialog).toContain("return !requireCustomerPhone.value")
		expect(dialog).toContain("phoneNumber.value && !selectedCountryCode.value")
		expect(dialog).toContain("requireCustomerPhone.value && !phoneNumber.value")
	})
})
