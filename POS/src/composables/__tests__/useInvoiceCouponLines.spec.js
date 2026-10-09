import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), data: null }),
	call: vi.fn(),
}));
vi.mock("@/utils/offline", () => ({ isOffline: () => true, getCachedItem: vi.fn() }));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}));

const { useInvoice } = await import("../useInvoice");

function cart() {
	const invoice = useInvoice();
	invoice.invoiceItems.value = [
		{ item_code: "A", quantity: 1, price_list_rate: 100, rate: 100, discount_percentage: 0 },
		{ item_code: "X", quantity: 1, price_list_rate: 100, rate: 100, discount_percentage: 0 },
		{ item_code: "G", quantity: 1, price_list_rate: 100, rate: 100, discount_percentage: 10 },
	];
	invoice.invoiceItems.value.forEach(invoice.recalculateItem);
	invoice.rebuildIncrementalCache();
	return invoice;
}

const lineCoupon = {
	code: "SAVE20",
	application_mode: "line",
	line_updates: [
		{ line_key: 0, item_code: "A", discount_percentage: 20, discount_amount: 0 },
		{ line_key: 2, item_code: "G", discount_percentage: 0, discount_amount: 20 },
	],
};

describe("useInvoice line-level coupons", () => {
	beforeEach(() => setActivePinia(createPinia()));

	it("discounts only the eligible lines and keeps the header discount", () => {
		const invoice = cart();
		invoice.additionalDiscount.value = 5;
		invoice.applyDiscount(lineCoupon);

		const [a, x, g] = invoice.invoiceItems.value;
		expect(a).toMatchObject({ coupon_code: "SAVE20", discount_amount: 20, amount: 80 });
		expect(x).toMatchObject({ discount_amount: 0, amount: 100 });
		expect(x.coupon_code).toBeUndefined();
		expect(g).toMatchObject({ coupon_code: "SAVE20", discount_amount: 20, amount: 80 });
		expect(invoice.additionalDiscount.value).toBe(5);
		expect(invoice.couponCode.value).toBe("SAVE20");
	});

	it("keeps a coupon amount absolute when qty changes", () => {
		const invoice = cart();
		invoice.applyDiscount(lineCoupon);
		const g = invoice.invoiceItems.value[2];
		g.quantity = 3;
		invoice.recalculateItem(g);
		expect(g).toMatchObject({ discount_amount: 20, discount_percentage: 0, amount: 280 });
	});

	it("restores the pre-coupon discount on removal and leaves the header discount", () => {
		const invoice = cart();
		invoice.additionalDiscount.value = 5;
		invoice.applyDiscount(lineCoupon);
		invoice.removeDiscount();

		const [a, , g] = invoice.invoiceItems.value;
		expect(a).toMatchObject({ coupon_code: null, discount_amount: 0, amount: 100 });
		expect(g).toMatchObject({ coupon_code: null, discount_percentage: 10, amount: 90 });
		expect(invoice.additionalDiscount.value).toBe(5);
		expect(invoice.couponCode.value).toBeNull();
	});

	it("still clears the Additional Discount for the header-level fallback", () => {
		const invoice = cart();
		invoice.applyDiscount({ code: "OLD10", amount: 10 });
		expect(invoice.additionalDiscount.value).toBe(10);
		invoice.removeDiscount();
		expect(invoice.additionalDiscount.value).toBe(0);
	});
});
