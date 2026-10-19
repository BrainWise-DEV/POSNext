/**
 * Mobile checkout must expose the same partial-payment completion path as desktop.
 * @vitest-environment node
 */
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

function source(rel) {
	return readFileSync(path.resolve(__dirname, rel), "utf8")
}

describe("mobile partial payment action", () => {
	it("renders the mobile completion action when partial payment is allowed", () => {
		const dialog = source("../PaymentDialog.vue")
		expect(dialog).toMatch(
			/totalPaid > 0[\s\S]{0,180}allowPartialPayment/
		)
	})

	it("uses the shared payment button label on mobile", () => {
		const dialog = source("../PaymentDialog.vue")
		expect(dialog).toContain('isSubmitting ? __("Processing...") : paymentButtonText')
		expect(dialog).toContain('return __("Partial Payment")')
	})
})
