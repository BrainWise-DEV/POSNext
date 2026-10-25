/**
 * Cashier-typed quantities and taps on same-item gift lines.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { syncCartFreeItems, totalSkuQty } from "@/utils/gwpSameItemFreeRows";

const toast = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s);
	return {};
});
vi.mock("frappe-ui", () => ({
	call: vi.fn(async () => ({ valid: true })),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => {
		Object.assign(toast, { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() });
		return toast;
	},
}));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }));
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false }),
}));

const { usePOSCartStore } = await import("../posCart");

const chipsy = { item_code: "CHIPSY", item_name: "Chipsy", rate: 15, price_list_rate: 15, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 };

// Server answer for "buy 2 get the 3rd free" (min_qty 2): one free unit once 2 are paid
const offerPass = (cart) => {
	const paid = cart.invoiceItems.find((i) => !i.is_free_item)?.quantity || 0;
	const free = paid >= 2 ? [{ item_code: "CHIPSY", qty: 1, uom: "Nos", min_qty: 2 }] : [];
	cart.invoiceItems = syncCartFreeItems(cart.invoiceItems, free, { recalculateItem: cart.recalculateItem });
};
const paidQty = (cart) => cart.invoiceItems.find((i) => !i.is_free_item)?.quantity;

describe("posCart same-item gift quantities", () => {
	let cart;
	beforeEach(() => {
		setActivePinia(createPinia());
		cart = usePOSCartStore();
	});

	it("typing 3 gives 3 units: 2 paid + 1 gift", () => {
		cart.addItem({ ...chipsy });
		cart.updateItemQuantity("CHIPSY", 3, "Nos");
		offerPass(cart);
		expect(paidQty(cart)).toBe(2);
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(3);
	});

	it("typing 1 on a 2 + 1 gift line settles at 1 paid, not 2", () => {
		cart.addItem({ ...chipsy });
		cart.updateItemQuantity("CHIPSY", 3, "Nos");
		offerPass(cart);
		cart.updateItemQuantity("CHIPSY", 1, "Nos");
		offerPass(cart);
		expect(paidQty(cart)).toBe(1);
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(1);
	});

	it("typing 4 on a 2 + 1 gift line gives 4 units: 3 paid + 1 gift", () => {
		cart.addItem({ ...chipsy });
		cart.updateItemQuantity("CHIPSY", 3, "Nos");
		offerPass(cart);
		cart.updateItemQuantity("CHIPSY", 4, "Nos");
		offerPass(cart);
		expect(paidQty(cart)).toBe(3);
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(4);
	});

	it("every tap adds a unit; the 3rd tap becomes the gift instead of a paid unit", () => {
		cart.addItem({ ...chipsy });
		offerPass(cart);
		cart.addItem({ ...chipsy });
		offerPass(cart);
		// 2 paid + 1 gift added on top
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(3);
		cart.addItem({ ...chipsy });
		offerPass(cart);
		// 3rd scanned unit is the gift: 2 paid + 1 gift
		expect(paidQty(cart)).toBe(2);
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(3);
		cart.addItem({ ...chipsy });
		offerPass(cart);
		expect(paidQty(cart)).toBe(3);
		expect(totalSkuQty(cart.invoiceItems, "CHIPSY")).toBe(4);
	});
});

describe("posCart whole-cart coupon", () => {
	let cart;
	beforeEach(() => {
		setActivePinia(createPinia());
		cart = usePOSCartStore();
		cart.addItem({ ...chipsy });
		cart.customer = "CUST-1";
		cart.applyDiscountToCart({ name: "WELCOME10", code: "WELCOME10", percentage: 0, amount: 5 });
	});

	it("says why when removing the customer drops the coupon", async () => {
		cart.customer = null;
		await vi.waitFor(() => expect(cart.appliedCoupon).toBeNull());
		expect(cart.additionalDiscount).toBe(0);
		expect(toast.showWarning).toHaveBeenCalledWith(expect.stringContaining("WELCOME10"));
	});

	it("drops the coupon when the last paid item is removed", async () => {
		cart.removeItem("CHIPSY", "Nos");
		await vi.waitFor(() => expect(cart.appliedCoupon).toBeNull());
		expect(cart.additionalDiscount).toBe(0);
	});

	it("keeps the coupon when the offers no longer give a header discount", () => {
		cart.removeOffer();
		expect(cart.additionalDiscount).toBe(5);
		expect(cart.appliedCoupon?.code).toBe("WELCOME10");
	});
});

describe("posCart line coupon on top of a promotion", () => {
	it("records only the coupon's share as the coupon amount", () => {
		setActivePinia(createPinia());
		const cart = usePOSCartStore();
		cart.addItem({ ...chipsy });
		cart.applyDiscountToCart({
			name: "WELCOME10",
			code: "WELCOME10",
			line_level: true,
			coupon: { discount_type: "Amount" },
			line_updates: [
				{ line_key: 0, item_code: "CHIPSY", discount_percentage: 0, discount_amount: 5, stacked: true, coupon_only_discount: 2 },
			],
		});
		expect(cart.appliedCoupon.amount).toBe(2);
	});
});
