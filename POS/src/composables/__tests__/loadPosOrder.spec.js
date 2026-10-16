import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("frappe-ui", () => ({ createResource: () => ({ fetch: vi.fn(), submit: vi.fn() }) }));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }));
vi.mock("@/utils/offline/uuid", () => ({ generateUUID: () => "uuid" }));
vi.mock("@/utils/offline/db", () => ({ db: {} }));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import { useInvoice } from "@/composables/useInvoice";

// SPG order: base row with promo discount, tinted open price row split over two
// warehouses, promo free item.
const ORDER = {
	name: "SPO-261007-0001",
	sales_person: "SPG Ani",
	discount_amount: 5000,
	coupon_code: "HEMAT",
	items: [
		{ item_code: "A", qty: 2, uom: "Nos", warehouse: "W1", price_list_rate: 100, rate: 90,
			discount_percentage: 10, discount_amount: 10, pricing_rules: "PRLE-1" },
		{ item_code: "B", qty: 1, uom: "Nos", warehouse: "W1", price_list_rate: 50, rate: 70,
			is_rate_manually_edited: 1, hpp_tinta: 12, tinting_job: "J-9" },
		{ item_code: "B", qty: 1, uom: "Nos", warehouse: "W2", price_list_rate: 50, rate: 70,
			is_rate_manually_edited: 1 },
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
		// The SPG's open price and tinting come back on the merged line.
		expect(rows[1]).toMatchObject({
			quantity: 2,
			rate: 70,
			price_list_rate: 50,
			is_rate_manually_edited: 1,
			original_rate: 50,
			tinting: { job: "J-9", hpp_tinta: 12 },
		});
		expect(rows[0].tinting).toBeUndefined();
		const submitted = invoice.formatItemsForSubmission(rows);
		expect(submitted.filter((r) => r.item_code === "B").map((r) => [r.warehouse, r.rate, r.custom_tinting_job])).toEqual([
			["W1", 70, "J-9"],
			["W2", 70, undefined],
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
		expect(rows[1]).toMatchObject({ rate: 70, tinting: { job: "J-9", hpp_tinta: 12 } });
		expect(invoice.posOrder.value).toBe(null);
		expect(invoice.couponCode.value).toBe(null);
		expect(invoice.additionalDiscount.value).toBe(5000);
		expect(invoice.posOrderSalesPerson.value).toBe(null);
	});

	it("the SPG's delivery choice follows the order to the cashier and back to the SPG", () => {
		invoice.loadPosOrder(ORDER);
		expect(invoice.posOrderDelivery.value).toBe(null);

		const delivered = { ...ORDER, dikirim: 1, alamat_kirim: "Jl. Kenanga 14", catatan_kirim: "sore" };
		invoice.loadPosOrder(delivered);
		expect(invoice.posOrderDelivery.value).toEqual({ alamat: "Jl. Kenanga 14", catatan: "sore" });
		invoice.loadPosOrder(delivered, { editable: true });
		expect(invoice.posOrderDelivery.value).toEqual({ alamat: "Jl. Kenanga 14", catatan: "sore" });

		invoice.resetInvoice();
		expect(invoice.posOrderDelivery.value).toBe(null);
	});
});
