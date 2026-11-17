/**
 * Task 8k (Ruling 77): no line discount beyond the line's value, no item at zero
 * price, and coupon checks say which document they are for.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

const { call, showError } = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s);
	return { call: vi.fn(async () => ({ valid: true })), showError: vi.fn() };
});
vi.mock("frappe-ui", () => ({
	call,
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: vi.fn(),
		showError,
		showWarning: vi.fn(),
		showInfo: vi.fn(),
	}),
}));
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}));
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}));

const { usePOSCartStore } = await import("../posCart");

const item = (code, price = 100) => ({
	item_code: code,
	item_name: code,
	rate: price,
	price_list_rate: price,
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
});

describe("cart discount limits", () => {
	let cart;
	beforeEach(() => {
		setActivePinia(createPinia());
		call.mockClear();
		showError.mockClear();
		cart = usePOSCartStore();
		cart.posProfile = "POS-1";
		cart.customer = "CUST-1";
	});

	it("refuses an item without a price", () => {
		cart.addItem(item("NO-PRICE", 0));
		expect(cart.invoiceItems).toHaveLength(0);
		expect(showError).toHaveBeenCalledWith(
			expect.stringContaining("cannot be sold at zero price")
		);
	});

	it("adds an item with a price", () => {
		cart.addItem(item("A"));
		expect(cart.invoiceItems).toHaveLength(1);
		expect(showError).not.toHaveBeenCalled();
	});

	it("clamps stacked percentages at the line's value", () => {
		cart.addItem(item("A"));
		const line = cart.invoiceItems[0];
		line.discount_percentage = 120;
		cart.recalculateItem(line);
		expect(line.discount_percentage).toBe(100);
		expect(line.discount_amount).toBe(100);
	});

	it("clamps a fixed amount at the line's value", () => {
		cart.addItem(item("A"));
		const line = cart.invoiceItems[0];
		line.discount_percentage = 0;
		line.discount_amount = 250;
		cart.recalculateItem(line);
		expect(line.discount_amount).toBe(100);
	});

	it("re-checks a coupon for the document it is on", async () => {
		cart.addItem(item("A"));
		cart.setTargetDoctype("Sales Order");
		cart.appliedCoupon = { name: "C10", code: "C10" };
		cart.customer = "CUST-2";
		await nextTick();
		const [, params] = call.mock.calls.find(([, p]) => p?.coupon_code === "C10");
		expect(params.target_doctype).toBe("Sales Order");
	});
});
