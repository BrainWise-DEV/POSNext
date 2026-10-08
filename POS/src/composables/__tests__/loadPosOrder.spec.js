import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("frappe-ui", () => ({ createResource: () => ({ fetch: vi.fn(), submit: vi.fn() }) }));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }));
vi.mock("@/utils/offline/uuid", () => ({ generateUUID: () => "uuid" }));
vi.mock("@/utils/offline/db", () => ({ db: {} }));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import { useInvoice } from "@/composables/useInvoice";

// SPG order: base row with promo discount + add on, manual-discount row, promo free item.
const ORDER = {
	name: "SPO-261007-0001",
	sales_person: "SPG Ani",
	discount_amount: 5000,
	coupon_code: "HEMAT",
	items: [
		{ item_code: "A", qty: 2, uom: "Nos", warehouse: "W1", price_list_rate: 100, rate: 90,
			discount_percentage: 10, discount_amount: 10, pricing_rules: "PRLE-1", addon_key: "k1" },
		{ item_code: "SAUCE", addon_item: "SAUCE", addon_parent_key: "k1", qty: 2, uom: "Nos",
			warehouse: "W1", rate: 5 },
		{ item_code: "B", qty: 1, uom: "Nos", warehouse: "W1", price_list_rate: 50, rate: 45,
			discount_percentage: 10, discount_amount: 5, addon_key: "k2" },
		{ item_code: "ADDON-TINTING", addon_group: "Tinta Propan", addon_parent_key: "k2", qty: 1,
			uom: "Nos", warehouse: "W1", rate: 25 },
		{ item_code: "FREE", qty: 1, uom: "Nos", warehouse: "W1", price_list_rate: 20, rate: 0,
			discount_percentage: 100, pricing_rules: "PRLE-2", is_free_item: 1 },
	],
};

describe("loadPosOrder", () => {
	let invoice;
	beforeEach(() => {
		setActivePinia(createPinia());
		invoice = useInvoice();
	});

	it("cashier: rows read-only with locked prices, cart tied to the order", () => {
		invoice.loadPosOrder(ORDER);
		const rows = invoice.invoiceItems.value;
		expect(rows.map((r) => r.item_code)).toEqual(["A", "B", "FREE"]);
		expect(rows.every((r) => r.pos_order_row && r.is_resolved_barcode)).toBe(true);
		expect(rows[0].discount_percentage).toBe(10);
		// Gelondongan comes back as the group, named after it.
		expect(rows[1].addons).toEqual([
			{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: 25 },
		]);
		expect(rows[0].addons).toEqual([
			{ item_code: "SAUCE", addon_group: null, item_name: "SAUCE", amount: 5 },
		]);
		expect(invoice.posOrder.value).toBe(ORDER.name);
		expect(invoice.couponCode.value).toBe("HEMAT");
		expect(invoice.posOrderSalesPerson.value).toBe("SPG Ani");
	});

	it("SPG edit: rows editable, promo results dropped, manual discount kept", () => {
		invoice.loadPosOrder(ORDER, { editable: true });
		const rows = invoice.invoiceItems.value;
		expect(rows.map((r) => r.item_code)).toEqual(["A", "B"]);
		expect(rows.some((r) => r.pos_order_row || r.is_resolved_barcode)).toBe(false);
		expect(rows[0]).toMatchObject({ discount_percentage: 0, pricing_rules: "", quantity: 2 });
		expect(rows[0].addons).toHaveLength(1);
		expect(rows[1].discount_percentage).toBe(10);
		expect(invoice.posOrder.value).toBe(null);
		expect(invoice.couponCode.value).toBe(null);
		expect(invoice.additionalDiscount.value).toBe(5000);
		expect(invoice.posOrderSalesPerson.value).toBe(null);
	});
});
