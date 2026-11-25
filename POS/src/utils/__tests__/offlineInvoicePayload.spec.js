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

	it("an order's carried key names its doctype; an invoice's does not (Ruling 146 (c))", () => {
		const base = { cart: cart(), shift, customer: "Cust", paymentData: {}, idempotencyKey: "key-12345678" };
		const order = buildOfflineInvoiceData({ ...base, idempotencyDoctype: "Sales Order" });
		expect(order.idempotency_doctype).toBe("Sales Order");
		const invoice = buildOfflineInvoiceData({ ...base, idempotencyDoctype: "Sales Invoice" });
		expect(invoice).not.toHaveProperty("idempotency_doctype");
	});
});

describe("buildOfflineInvoiceData for a Sales Order cart (H2 round 1, I-2)", () => {
	const fnfLine = {
		item_code: "A",
		rate: 100,
		price_list_rate: 100,
		discount_percentage: 30,
		discount_amount: 30,
		discount_source: "friends_and_family",
	};

	it("queues a Sales Order with its delivery date", () => {
		const data = buildOfflineInvoiceData({
			cart: cart({ targetDoctype: "Sales Order", deliveryDate: "2026-11-30" }),
			shift,
			customer: "Cust",
			paymentData: {},
		});
		expect(data.doctype).toBe("Sales Order");
		expect(data.delivery_date).toBe("2026-11-30");
	});

	it("carries no F&F on an order", () => {
		const data = buildOfflineInvoiceData({
			cart: cart({
				targetDoctype: "Sales Order",
				invoiceItems: [fnfLine],
				formatItemsForSubmission: (items) => items.map((i) => ({ ...i })),
			}),
			shift,
			customer: "Cust",
			paymentData: {},
		});
		expect(data.items[0]).toMatchObject({ discount_percentage: 0, discount_amount: 0 });
	});

	it("an invoice cart queues a Sales Invoice with no delivery date", () => {
		const data = buildOfflineInvoiceData({
			cart: cart({ targetDoctype: "Sales Invoice", deliveryDate: "2026-11-30" }),
			shift,
			customer: "Cust",
			paymentData: {},
		});
		expect(data.doctype).toBe("Sales Invoice");
		expect(data.delivery_date).toBeUndefined();
	});
});
