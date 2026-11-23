/**
 * G5: an "Add on top" coupon over an F&F line. The cart keeps the server-signed
 * snapshot of the discount F&F displaced and sends it back with that line, so the
 * server can stack the coupon on it and work out the coupon's own share.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s)
})
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}))
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }))
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}))

const { usePOSCartStore } = await import("../posCart")
const { stampFnfLine, stripFnfLine } = await import("@/utils/friendsAndFamily")

const SNAP = "posnext_fnf_replaced_discount"
const SIGNED = '{"v":2,"sig":"abc"}'
const item = (code) => ({
	item_code: code,
	item_name: code,
	rate: 100,
	price_list_rate: 100,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
})
const coupon = { coupon_code: "ADD", discount_type: "Percentage", discount_percentage: 10, max_amount: 50 }
// Promo 25 (the one F&F displaced) + 10% of 75 = 32.5 on the line, coupon money 7.5.
const stackedUpdate = {
	line_key: 1,
	item_code: "B",
	discount_percentage: 0,
	discount_amount: 32.5,
	rate: 67.5,
	amount: 67.5,
	coupon_code: "ADD",
	coupon_only_discount: 7.5,
	existing_discount: 25,
	stacked: true,
}

describe("stacked coupon over an F&F line: the signed snapshot", () => {
	let cart
	beforeEach(() => {
		setActivePinia(createPinia())
		cart = usePOSCartStore()
		cart.posProfile = "POS-1"
		cart.customer = "CUST-1"
		cart.addItem(item("A"))
		cart.addItem(item("B"))
		stampFnfLine(cart.invoiceItems[1], {
			discount_percentage: 30,
			discount_amount: 30,
			rate: 70,
			applies: true,
			[SNAP]: SIGNED,
		})
		cart.recalculateItem(cart.invoiceItems[1])
	})

	const applyStacked = () =>
		cart.applyDiscountToCart({ name: "ADD", code: "ADD", line_level: true, coupon, line_updates: [stackedUpdate] })

	it("the F&F stamp keeps the server's snapshot and a strip drops it", () => {
		const line = cart.invoiceItems[1]
		expect(line[SNAP]).toBe(SIGNED)
		stripFnfLine(line)
		expect(line[SNAP]).toBeNull()
	})

	it("coupon and offer payloads send it with the F&F line, and with the coupon line over it", () => {
		for (const build of [() => cart.buildCouponItemsPayload(), () => cart.buildOfferEvaluationPayload({}).items]) {
			const [a, b] = build()
			expect(a).not.toHaveProperty(SNAP)
			expect(b[SNAP]).toBe(SIGNED)
			expect(b.discount_source).toBe("friends_and_family")
		}
		applyStacked()
		const [a, b] = cart.buildCouponItemsPayload()
		expect(a).not.toHaveProperty(SNAP)
		expect(b[SNAP]).toBe(SIGNED)
		expect(b.discount_source).toBe("friends_and_family") // the line as it is without the coupon
	})

	it("the submitted stacked line carries the snapshot; an F&F or plain coupon line does not", () => {
		let rows = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rows[1]).not.toHaveProperty(SNAP) // an F&F row: the server keeps its own
		applyStacked()
		rows = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rows[1].posnext_coupon_code).toBe("ADD")
		expect(rows[1][SNAP]).toBe(SIGNED)
		// Not stacked (the coupon replaced F&F outright): nothing to stack on, nothing sent.
		cart.applyDiscountToCart({
			name: "ADD",
			code: "ADD",
			line_level: true,
			coupon,
			line_updates: [{ ...stackedUpdate, stacked: false, existing_discount: 0, discount_amount: 40 }],
		})
		rows = cart.formatItemsForSubmission(cart.invoiceItems)
		expect(rows[1].posnext_coupon_code).toBe("ADD")
		expect(rows[1]).not.toHaveProperty(SNAP)
	})

	it("dropping the F&F kept under the coupon drops its snapshot", () => {
		applyStacked()
		cart.applyDiscountToCart({
			name: "C50",
			code: "C50",
			amount: 50,
			suppress_friends_and_family: true,
			coupon: { coupon_code: "C50", discount_type: "Amount", discount_amount: 50 },
		})
		expect(cart.invoiceItems[1][SNAP]).toBeNull()
	})
})
