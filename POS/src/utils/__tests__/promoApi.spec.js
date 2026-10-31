import { afterEach, describe, expect, it, vi } from "vitest";
import { isMagentoAppInstalled, isPromotionsAppInstalled, promoApi } from "../promoApi";

describe("promoApi install detection", () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("is off when no flag source exists", () => {
		vi.stubGlobal("window", {});
		expect(isPromotionsAppInstalled()).toBe(false);
		expect(promoApi.applyOffers()).toBe("pos_next.api.invoices.apply_offers");
	});

	it("reads the /pos page flags (window.posnext_app_flags)", () => {
		vi.stubGlobal("window", { posnext_app_flags: { posnext_promotions: 1 } });
		expect(isPromotionsAppInstalled()).toBe(true);
		expect(isMagentoAppInstalled()).toBe(false);
		expect(promoApi.applyOffers()).toBe("posnext_promotions.api.offers.apply_offers");
	});

	it("still reads Desk boot flags (frappe.boot)", () => {
		vi.stubGlobal("window", {
			frappe: { boot: { posnext_promotions: 1, magento_integration: 1 } },
		});
		expect(isPromotionsAppInstalled()).toBe(true);
		expect(isMagentoAppInstalled()).toBe(true);
	});
});
