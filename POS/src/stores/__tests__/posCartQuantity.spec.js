/**
 * Cashier-typed quantities and taps on same-item gift lines.
 * @vitest-environment jsdom
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { syncCartFreeItems, totalSkuQty } from "@/utils/gwpSameItemFreeRows";

vi.hoisted(() => {
	globalThis.__ = (s) => s;
});
vi.mock("frappe-ui", () => ({
	call: vi.fn(),
	createResource: () => ({ submit: vi.fn(), reload: vi.fn(), fetch: vi.fn() }),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
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
