import { describe, expect, it, vi } from "vitest";
import { buildOfflineInvoiceData } from "../offlineInvoicePayload";

function cart(overrides = {}) {
	return {
		posProfile: "P",
		posOpeningShift: "S",
		invoiceItems: [{ item_code: "A" }],
		formatItemsForSubmission: vi.fn((items) => items.map((i) => ({ ...i, posnext_coupon_code: "LINE10" }))),
		payments: [{ mode_of_payment: "Cash", amount: 90 }],
		salesTeam: [],
		grandTotal: 90,
		totalTax: 0,
		totalDiscount: 10,
		additionalDiscount: 0,
		couponCode: null,
		...overrides,
	};
}

const shift = { profileCompany: "C", profileCustomer: "Walk-in" };

describe("buildOfflineInvoiceData", () => {
	it("carries the order-level coupon and its header discount, as the online submit does", () => {
		const data = buildOfflineInvoiceData({
			cart: cart({ couponCode: "ORDER40", additionalDiscount: 40 }),
			shift,
			customer: "Cust",
			paymentData: {},
		});
		expect(data.coupon_code).toBe("ORDER40");
		expect(data.discount_amount).toBe(40);
	});

	it("carries the line coupon's code next to the tagged lines", () => {
		const data = buildOfflineInvoiceData({
			cart: cart({ couponCode: "LINE10" }),
			shift,
			customer: "Cust",
			paymentData: {},
		});
		expect(data.coupon_code).toBe("LINE10");
		expect(data.discount_amount).toBe(0);
		expect(data.items[0].posnext_coupon_code).toBe("LINE10");
	});

	it("sends no coupon and a zero header discount without one", () => {
		const data = buildOfflineInvoiceData({ cart: cart(), shift, customer: null, paymentData: {} });
		expect(data.coupon_code).toBeNull();
		expect(data.discount_amount).toBe(0);
		expect(data.customer).toBe("Walk-in");
	});

	it("carries the cart's idempotency key when one is given (Ruling 139)", () => {
		const keyed = buildOfflineInvoiceData({
			cart: cart(),
			shift,
			customer: "Cust",
			paymentData: {},
			idempotencyKey: "key-12345678",
		});
		expect(keyed.idempotency_key).toBe("key-12345678");
		const plain = buildOfflineInvoiceData({ cart: cart(), shift, customer: "Cust", paymentData: {} });
		expect(plain).not.toHaveProperty("idempotency_key");
	});
});
