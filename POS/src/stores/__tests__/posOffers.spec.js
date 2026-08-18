import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn() }));
vi.mock("@/utils/offline", () => ({ isOffline: () => false }));
vi.mock("@/utils/offline/workerClient", () => ({ offlineWorker: {} }));
vi.mock("@/utils/offline/db", () => ({
	getOneTimeRedemptions: vi.fn(), setOneTimeRedemptions: vi.fn(), addOneTimeRedemptions: vi.fn(),
}));
vi.mock("@/stores/posShift", () => ({ usePOSShiftStore: () => ({}) }));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import { usePOSOffersStore } from "@/stores/posOffers";

// Invoice ACC-SINV-2026-00165 / 00167: SKU009 x1 @150 (50% off), 9505 x2 @90.
// gross = 330, net = 255.
const SNAPSHOT = {
	subtotal: 330, netSubtotal: 255, itemCount: 3,
	itemCodes: ["SKU009", "9505"], itemGroups: ["Demo Item Group"], brands: [],
	itemQuantities: { SKU009: 1, "9505": 2 },
	itemGroupQuantities: { "Demo Item Group": 3 },
	brandQuantities: {},
	itemAmounts: { SKU009: 150, "9505": 180 },
	itemGroupAmounts: { "Demo Item Group": 330 },
	brandAmounts: {},
};

describe("offer amount gate mirrors the server basis", () => {
	let store;
	beforeEach(() => {
		setActivePinia(createPinia());
		store = usePOSOffersStore();
		store.updateCartSnapshot(SNAPSHOT);
	});

	it("PRLE-0013: Transaction max_amt=260 gates on net 255, not gross 330", () => {
		const offer = { name: "PRLE-0013", apply_on: "Transaction", max_amt: 260 };
		expect(store.getEligibleItemAmount(offer)).toBe(255);
		expect(store.checkOfferEligibility(offer).eligible).toBe(true);
	});

	it("Transaction rule is still rejected when the net total really exceeds max_amt", () => {
		const offer = { name: "X", apply_on: "Transaction", max_amt: 200 };
		expect(store.checkOfferEligibility(offer).eligible).toBe(false);
	});

	it("Item Code rule gates on that item's gross line amount, not the cart", () => {
		// SKU009 alone is 150 gross; cart is 330.
		const offer = { name: "Y", apply_on: "Item Code", eligible_items: ["SKU009"], min_amt: 200 };
		expect(store.getEligibleItemAmount(offer)).toBe(150);
		expect(store.checkOfferEligibility(offer).eligible).toBe(false);
		expect(store.getUnlockAmount(offer)).toBe(50);

		const ok = { ...offer, min_amt: 120 };
		expect(store.checkOfferEligibility(ok).eligible).toBe(true);
	});

	it("Item Group rule sums only the matching lines", () => {
		const offer = {
			name: "Z", apply_on: "Item Group",
			eligible_item_groups: ["Demo Item Group"], min_amt: 300,
		};
		expect(store.getEligibleItemAmount(offer)).toBe(330);
		expect(store.checkOfferEligibility(offer).eligible).toBe(true);
	});

	it("offers with no scope metadata fall back to the gross subtotal", () => {
		expect(store.getEligibleItemAmount({ name: "W" })).toBe(330);
	});
});
