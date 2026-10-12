import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("frappe-ui", () => ({ createResource: () => ({ fetch: vi.fn(), submit: vi.fn() }) }));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: vi.fn() }));
vi.mock("@/utils/offline/uuid", () => ({ generateUUID: () => "key-1" }));
vi.mock("@/utils/offline/db", () => ({ db: {} }));
vi.mock("@/utils/itemAddons", () => ({ getAddonCarrierItem: () => "ADDON-TINTING" }));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import { useInvoice } from "@/composables/useInvoice";

describe("add on rows", () => {
	let invoice;
	beforeEach(() => {
		setActivePinia(createPinia());
		invoice = useInvoice();
		invoice.invoiceItems.value = [
			{
				item_code: "BASE",
				item_name: "Base",
				uom: "Nos",
				quantity: 1,
				rate: 100000,
				price_list_rate: 100000,
				warehouse: "W1",
				conversion_factor: 1,
			},
		];
	});

	it("drops zero priced add ons and submits group and tinta rows", () => {
		invoice.setItemAddons("BASE", "Nos", [
			{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: 25000 },
			{ item_code: "AVN-BLK", addon_group: "Tinta Avian", item_name: "Avian Black", amount: 5000 },
			{ item_code: "LOOSE", addon_group: null, item_name: "Loose", amount: 0 },
		]);
		const base = invoice.invoiceItems.value[0];
		expect(base.addons).toHaveLength(2);
		expect(base.addon_key).toBe("key-1");

		const rows = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
		expect(rows.map((r) => [r.item_code, r.custom_addon_item, r.custom_addon_group])).toEqual([
			["BASE", undefined, undefined],
			["ADDON-TINTING", null, "Tinta Propan"],
			["ADDON-TINTING", "AVN-BLK", "Tinta Avian"],
		]);
		expect(rows.slice(1).map((r) => [r.rate, r.price_list_rate, r.qty])).toEqual([
			[25000, 25000, 1],
			[5000, 5000, 1],
		]);
		expect(rows[0].custom_addon_key).toBe("key-1");
		expect(rows.slice(1).every((r) => r.custom_addon_parent_key === "key-1")).toBe(true);
	});

	it("leaves no add on when every price is empty", () => {
		invoice.setItemAddons("BASE", "Nos", [
			{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: "" },
		]);
		const rows = invoice.formatItemsForSubmission(invoice.invoiceItems.value);
		expect(rows.map((r) => r.item_code)).toEqual(["BASE"]);
	});
});
