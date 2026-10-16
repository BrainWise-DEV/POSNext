import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("frappe-ui", () => ({ createResource: () => ({ fetch: vi.fn(), submit: vi.fn() }) }));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }));
vi.mock("@/utils/offline/uuid", () => ({ generateUUID: () => "key-1" }));
vi.mock("@/utils/offline/db", () => ({ db: {} }));
vi.mock("@/utils/itemAddons", () => ({ getAddonCarrierItem: () => "ADDON-TINTING" }));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import { useInvoice } from "@/composables/useInvoice";

const BASE = {
	item_code: "BASE",
	item_name: "Base",
	uom: "Nos",
	quantity: 2,
	rate: 100000,
	price_list_rate: 100000,
	warehouse: "W1",
	conversion_factor: 1,
};

describe("tinting", () => {
	let invoice;
	beforeEach(() => {
		setActivePinia(createPinia());
		invoice = useInvoice();
		invoice.invoiceItems.value = [{ ...BASE }];
		invoice.recalculateItem(invoice.invoiceItems.value[0]);
	});

	it("goes on the base row only and leaves the price alone", () => {
		invoice.setItemTinting("BASE", "Nos", { job: " J-77 ", hpp_tinta: "15000" });
		const rows = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
		expect(rows).toHaveLength(1);
		expect(rows[0]).toMatchObject({
			item_code: "BASE",
			rate: 100000,
			custom_hpp_tinta: 15000,
			custom_tinting_job: "J-77",
		});
		expect(rows[0].custom_addon_key).toBeUndefined();
	});

	it("is cleared by null, an empty job or an HPP of 0", () => {
		for (const value of [null, { job: "", hpp_tinta: 5 }, { job: "J1", hpp_tinta: 0 }]) {
			invoice.setItemTinting("BASE", "Nos", { job: "J1", hpp_tinta: 5 });
			invoice.setItemTinting("BASE", "Nos", value);
			expect(invoice.invoiceItems.value[0].tinting).toBeNull();
			const [row] = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
			expect(row.custom_tinting_job).toBeUndefined();
		}
	});

	it("follows the first warehouse chunk of an SPG order line", () => {
		const line = invoice.invoiceItems.value[0];
		line.pos_order_chunks = [
			{ warehouse: "W1", qty: 1 },
			{ warehouse: "W2", qty: 1 },
		];
		invoice.setItemTinting("BASE", "Nos", { job: "J1", hpp_tinta: 8000 });
		const rows = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
		expect(rows.map((r) => [r.warehouse, r.custom_tinting_job, r.custom_hpp_tinta])).toEqual([
			["W1", "J1", 8000],
			["W2", undefined, undefined],
		]);
	});

	it("ignores an unknown line", () => {
		invoice.setItemTinting("OTHER", "Nos", { job: "J1", hpp_tinta: 5 });
		expect(invoice.invoiceItems.value[0].tinting).toBeUndefined();
	});
});

describe("open price", () => {
	it("submits the typed rate, not the list price", () => {
		setActivePinia(createPinia());
		const invoice = useInvoice();
		const line = { ...BASE, rate: 125000, is_rate_manually_edited: 1, original_rate: 100000 };
		invoice.invoiceItems.value = [line];
		invoice.recalculateItem(line);
		const [row] = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
		expect(row).toMatchObject({
			rate: 125000,
			price_list_rate: 100000,
			is_rate_manually_edited: 1,
		});
	});
});
