/**
 * PN-130 — Friends & Family POS helpers (payload shapes from posnext_promotions).
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";
import {
	buildFnfCartMessages,
	fnfEmailBlockMessage,
	FNF_REASON,
	isFnfAllowedForProfile,
	discountTotalsBySource,
	FNF_DISCOUNT_SOURCE,
	fnfLineNote,
	fnfLockedDiscountAmount,
	indexFnfLines,
	isFnfLine,
	LINE_SOURCE,
	lineBreakdown,
	lineDiscountSource,
	mergeServerLine,
	normalizeEligibility,
	normalizeFnfResult,
	pickLocalizedMessage,
	resolveHeaderDiscount,
	stampFnfLine,
	stripFnfLine,
} from "@/utils/friendsAndFamily";

const fmt = (v) => `EGP ${Number(v).toFixed(2)}`;

// Trimmed from a real apply_offers response on brainwise.dev (GP-LAP-01 @ 899, 30%).
const appliedBlock = {
	eligible: true,
	discount_percentage: 30,
	applied_count: 1,
	message: "You have received the Miraaya Friends & Family offer!",
	reason: "customer_flag",
	items: [
		{
			item_code: "GP-LAP-01",
			idx: 0,
			applies: true,
			discount_percentage: 30,
			discount_amount: 269.7,
			rate: 629.3,
			reason: "applied",
			competing_source: null,
			competing_amount: 0,
			best_discount: {
				winner: "friends_and_family",
				outcome: "fnf_only",
				suppressed: [],
				message: "Friends & Family discount (30%) applied.",
				message_en: "Friends & Family discount (30%) applied.",
				message_ar: "تم تطبيق خصم الأصدقاء والعائلة (30%).",
			},
			fnf_uncapped_amount: 269.7,
			capped: false,
		},
	],
	caps: {
		active: false,
		monthly_remaining: null,
		fnf_applied_total: 269.7,
		capped: false,
		cap_hit: null,
		message: "",
		message_en: "",
		message_ar: "",
	},
	cap_hit: null,
};

const bestDiscount = {
	winner: "friends_and_family",
	suppressed: [],
	message: "Friends & Family discount (30%) applied.",
	message_en: "Friends & Family discount (30%) applied.",
	message_ar: "تم تطبيق خصم الأصدقاء والعائلة (30%).",
};

function cartLine(overrides = {}) {
	return {
		item_code: "GP-LAP-01",
		quantity: 1,
		rate: 899,
		price_list_rate: 899,
		discount_percentage: 0,
		discount_amount: 0,
		discount_source: "",
		pricing_rules: [],
		...overrides,
	};
}

describe("pickLocalizedMessage", () => {
	const payload = { message: "srv", message_en: "en", message_ar: "ar" };
	it("uses message_ar for Arabic and message_en for English", () => {
		expect(pickLocalizedMessage(payload, "ar")).toBe("ar");
		expect(pickLocalizedMessage(payload, "en")).toBe("en");
	});
	it("falls back to the server-translated message for other locales / missing keys", () => {
		expect(pickLocalizedMessage(payload, "pt-br")).toBe("srv");
		expect(pickLocalizedMessage({ message: "only" }, "ar")).toBe("only");
		expect(pickLocalizedMessage(null, "en")).toBe("");
	});
});

describe("normalizeEligibility", () => {
	it("keeps the ff_activated customer message and % for an eligible customer", () => {
		const e = normalizeEligibility({
			message: {
				customer: "F&F Smoke Eligible",
				eligible: true,
				reason: "customer_flag",
				discount_percentage: 30,
				program: { discount_percentage: 30 },
				customer_message: { event: "ff_activated", ar: "عرض ميرايا", en: "Miraaya F&F offer", message: "عرض ميرايا" },
			},
		});
		expect(e).toMatchObject({ eligible: true, discountPercentage: 30 });
		expect(e).not.toHaveProperty("userMessage");
		expect(pickLocalizedMessage(e.customerMessage, "en")).toBe("Miraaya F&F offer");
		expect(pickLocalizedMessage(e.customerMessage, "ar")).toBe("عرض ميرايا");
	});
	it("has no customer message when none is configured", () => {
		const e = normalizeEligibility({ eligible: true, discount_percentage: 30, customer_message: null });
		expect(e.customerMessage).toBeNull();
		expect(pickLocalizedMessage(e.customerMessage, "en")).toBe("");
	});
	it("zeroes the % for an ineligible customer", () => {
		const e = normalizeEligibility({ eligible: false, reason: "not_eligible", discount_percentage: 0 }, "X");
		expect(e).toMatchObject({ eligible: false, discountPercentage: 0, customerMessage: null, customer: "X" });
	});
});

describe("normalizeFnfResult / indexFnfLines", () => {
	it("returns null when apply_offers sent no F&F block (ineligible customer)", () => {
		expect(normalizeFnfResult(undefined)).toBeNull();
		expect(indexFnfLines(null).size).toBe(0);
	});
	it("indexes line results by cart idx", () => {
		const r = normalizeFnfResult(appliedBlock, bestDiscount);
		expect(r.appliedCount).toBe(1);
		expect(r.bestDiscount).toBe(bestDiscount);
		expect(indexFnfLines(r).get(0).applies).toBe(true);
	});
});

describe("stampFnfLine / stripFnfLine", () => {
	it("stamps the server amount and pins it to the quantity", () => {
		const item = cartLine();
		stampFnfLine(item, appliedBlock.items[0]);
		expect(isFnfLine(item)).toBe(true);
		expect(item).toMatchObject({
			discount_source: FNF_DISCOUNT_SOURCE,
			discount_percentage: 30,
			discount_amount: 269.7,
			fnf_discount_amount: 269.7,
			fnf_qty: 1,
			is_already_discounted: 1,
		});
	});

	it("clears a stale F&F discount (switch to an ineligible customer)", () => {
		const item = cartLine({ discount_percentage: 30, discount_amount: 269.7, discount_source: FNF_DISCOUNT_SOURCE });
		expect(stripFnfLine(item)).toBe(true);
		expect(item).toMatchObject({ discount_percentage: 0, discount_amount: 0, discount_source: "" });
	});

	it("leaves a non-F&F discount alone", () => {
		const item = cartLine({ discount_percentage: 10, discount_amount: 89.9, discount_source: "manual_discount" });
		expect(stripFnfLine(item)).toBe(false);
		expect(item.discount_percentage).toBe(10);
	});
});

describe("fnfLockedDiscountAmount (capped lines)", () => {
	it("uses the server amount instead of the unrounded %", () => {
		// Per-order cap 100 on an 899 line → 11.1234…% on the server.
		const item = cartLine();
		stampFnfLine(item, { ...appliedBlock.items[0], discount_percentage: 11.123470522803114, discount_amount: 100, capped: true });
		expect(fnfLockedDiscountAmount(item, 899)).toBe(100);
	});
	it("falls back to normal maths once the quantity changed", () => {
		const item = cartLine();
		stampFnfLine(item, appliedBlock.items[0]);
		item.quantity = 2;
		expect(fnfLockedDiscountAmount(item, 1798)).toBeNull();
	});
	it("ignores non-F&F lines", () => {
		expect(fnfLockedDiscountAmount(cartLine({ discount_amount: 5 }), 899)).toBeNull();
	});
});

describe("lineDiscountSource / lineBreakdown", () => {
	it("labels F&F, promotion, coupon, manual and none", () => {
		expect(lineDiscountSource(cartLine({ discount_source: FNF_DISCOUNT_SOURCE, discount_amount: 1 }))).toBe(LINE_SOURCE.FRIENDS_AND_FAMILY);
		expect(lineDiscountSource(cartLine({ discount_percentage: 10, pricing_rules: ["PRLE-0001"] }))).toBe(LINE_SOURCE.PROMOTION);
		expect(lineDiscountSource(cartLine({ discount_percentage: 10, discount_source: "auto_discount" }))).toBe(LINE_SOURCE.PROMOTION);
		expect(lineDiscountSource(cartLine({ discount_percentage: 15, discount_source: "coupon" }))).toBe(LINE_SOURCE.COUPON);
		expect(lineDiscountSource(cartLine({ discount_percentage: 5 }))).toBe(LINE_SOURCE.MANUAL);
		expect(lineDiscountSource(cartLine())).toBe(LINE_SOURCE.NONE);
		expect(lineDiscountSource(cartLine({ is_free_item: 1 }))).toBe(LINE_SOURCE.FREE);
	});

	it("shows original − discount = final", () => {
		const item = cartLine({ quantity: 2, discount_amount: 539.4, discount_source: FNF_DISCOUNT_SOURCE });
		expect(lineBreakdown(item)).toEqual({ source: "friends_and_family", original: 1798, discount: 539.4, final: 1258.6 });
	});

	it("totals discounts per source and skips free rows", () => {
		const totals = discountTotalsBySource([
			cartLine({ discount_amount: 269.7, discount_source: FNF_DISCOUNT_SOURCE }),
			cartLine({ item_code: "P", discount_amount: 10, pricing_rules: "PRLE-1" }),
			cartLine({ item_code: "F", is_free_item: 1, discount_amount: 50 }),
		]);
		expect(totals.friends_and_family).toBe(269.7);
		expect(totals.promotion).toBe(10);
		expect(totals.free).toBe(0);
	});
});

describe("fnfLineNote", () => {
	it("explains excluded / out of scope / cap / promo better", () => {
		expect(fnfLineNote(cartLine({ fnf_reason: "excluded" })).text).toBe("Excluded from Friends & Family");
		expect(fnfLineNote(cartLine({ fnf_reason: "out_of_scope" })).text).toBe("Not covered by Friends & Family");
		expect(fnfLineNote(cartLine({ fnf_reason: "cap_reached" })).tone).toBe("warning");
		const decision = {
			message_en: "The promotion (40%) is better than the Friends & Family discount (30%) — the promotion applied instead of Friends & Family.",
			message_ar: "العرض الترويجي (40%) أفضل من خصم الأصدقاء والعائلة (30%)",
		};
		const line = cartLine({ fnf_reason: "other_discount_better", fnf_decision: decision });
		expect(fnfLineNote(line, { locale: "en" }).text).toBe(decision.message_en);
		expect(fnfLineNote(line, { locale: "ar" }).text).toBe(decision.message_ar);
	});
	it("flags a capped F&F line and is silent for a normal one", () => {
		expect(fnfLineNote(cartLine({ discount_source: FNF_DISCOUNT_SOURCE, fnf_capped: true })).tone).toBe("warning");
		expect(fnfLineNote(cartLine({ discount_source: FNF_DISCOUNT_SOURCE }))).toBeNull();
		expect(fnfLineNote(cartLine({ fnf_reason: "applied" }))).toBeNull();
	});
});

describe("buildFnfCartMessages", () => {
	const keys = (msgs) => msgs.map((m) => m.key);

	it("eligible + covered item → applied summary with the saving", () => {
		const msgs = buildFnfCartMessages({ result: normalizeFnfResult(appliedBlock, bestDiscount), formatAmount: fmt });
		expect(keys(msgs)).toEqual(["applied"]);
		expect(msgs[0].text).toBe("Friends & Family 30% applied to 1 item(s) — saving EGP 269.70");
	});

	it("ineligible customer (no block) → nothing", () => {
		expect(buildFnfCartMessages({ result: null, eligibility: { eligible: false } })).toEqual([]);
	});

	it("all items excluded → coverage warning", () => {
		const result = normalizeFnfResult({ ...appliedBlock, applied_count: 0, reason: "no_covered_items", items: [] });
		const msgs = buildFnfCartMessages({ result, formatAmount: fmt });
		expect(keys(msgs)).toEqual(["coverage"]);
		expect(msgs[0].tone).toBe("warning");
	});

	it("promotion wins → comparison message in the UI language", () => {
		const best = {
			winner: "promotion",
			suppressed: ["friends_and_family"],
			message_en: "The promotion (40%) is better than the Friends & Family discount (30%) — the promotion applied instead of Friends & Family.",
			message_ar: "العرض الترويجي (40%) أفضل من خصم الأصدقاء والعائلة (30%)",
		};
		const result = normalizeFnfResult({ ...appliedBlock, applied_count: 0, items: [] }, best);
		expect(buildFnfCartMessages({ result, locale: "ar" }).find((m) => m.key === "comparison").text).toBe(best.message_ar);
	});

	it("cap hit → cap message + monthly remaining", () => {
		const caps = {
			active: true,
			capped: true,
			cap_hit: "monthly",
			monthly_remaining: 100,
			monthly_remaining_after: 0,
			fnf_applied_total: 100,
			message_en: "Friends & Family discount reduced to 100.00 — monthly limit 500.00, 100.00 left this month before this order.",
			message_ar: "تم تخفيض خصم الأصدقاء والعائلة إلى 100.00",
		};
		const result = normalizeFnfResult({ ...appliedBlock, caps, cap_hit: "monthly" }, bestDiscount);
		const msgs = buildFnfCartMessages({ result, formatAmount: fmt, locale: "en" });
		expect(keys(msgs)).toEqual(["applied", "cap", "monthly"]);
		expect(msgs[1].text).toBe(caps.message_en);
		expect(msgs[2].text).toBe("Monthly Friends & Family balance: EGP 100.00 left, EGP 0.00 after this order");
	});

	it("coupon beat F&F → only the coupon explanation", () => {
		const msgs = buildFnfCartMessages({
			result: normalizeFnfResult(appliedBlock, bestDiscount),
			couponOverride: { code: "SAVE40", message_en: "Coupon SAVE40 (40%) is better than the Friends & Family discount (30%)." },
		});
		expect(keys(msgs)).toEqual(["coupon"]);
		expect(msgs[0].text).toContain("SAVE40");
	});

	it("empty cart → nothing", () => {
		expect(buildFnfCartMessages({ result: normalizeFnfResult(appliedBlock), hasItems: false })).toEqual([]);
	});
});

describe("mergeServerLine (apply_offers → cart)", () => {
	it("eligible: stamps F&F from the block", () => {
		const item = cartLine();
		const res = mergeServerLine(item, { ...cartLine(), discount_percentage: 30, discount_amount: 269.7, discount_source: FNF_DISCOUNT_SOURCE }, appliedBlock.items[0]);
		expect(res.stamped).toBe(true);
		expect(item.discount_amount).toBe(269.7);
		expect(isFnfLine(item)).toBe(true);
	});

	it("switch to ineligible: server echoes the old F&F line with no block → stripped", () => {
		const item = cartLine();
		stampFnfLine(item, appliedBlock.items[0]);
		// Exactly what apply_offers returned on brainwise.dev for F&F Smoke Ineligible.
		const echoed = { item_code: "GP-LAP-01", qty: 1, rate: 899, price_list_rate: 899, discount_percentage: 30, discount_amount: 269.7, discount_source: FNF_DISCOUNT_SOURCE, is_already_discounted: 1 };
		const res = mergeServerLine(item, echoed, undefined);
		expect(res.stripped).toBe(true);
		expect(item).toMatchObject({ discount_percentage: 0, discount_amount: 0, discount_source: "", is_already_discounted: 0 });
	});

	it("promotion wins the line: promo replaces the old F&F stamp", () => {
		const item = cartLine();
		stampFnfLine(item, appliedBlock.items[0]);
		const fnfLine = { idx: 0, applies: false, reason: "other_discount_better", best_discount: { message_en: "promo better" } };
		mergeServerLine(item, { discount_percentage: 40, discount_amount: 359.6, pricing_rules: "PRLE-0009", discount_source: "auto_discount" }, fnfLine);
		expect(item).toMatchObject({ discount_percentage: 40, discount_source: "auto_discount", pricing_rules: ["PRLE-0009"], fnf_reason: "other_discount_better" });
		expect(isFnfLine(item)).toBe(false);
	});

	it("excluded item keeps no discount and records the reason", () => {
		const item = cartLine({ item_code: "4124" });
		mergeServerLine(item, { item_code: "4124", discount_percentage: 0 }, { idx: 1, applies: false, reason: "excluded" });
		expect(item.discount_amount).toBe(0);
		expect(item.fnf_reason).toBe("excluded");
	});

	it("coupon replaced F&F: F&F stamp from the server is ignored", () => {
		const item = cartLine();
		stampFnfLine(item, appliedBlock.items[0]);
		const res = mergeServerLine(item, { discount_percentage: 30, discount_amount: 269.7, discount_source: FNF_DISCOUNT_SOURCE }, appliedBlock.items[0], { fnfSuppressed: true });
		expect(res.stripped).toBe(true);
		expect(item.discount_amount).toBe(0);
	});

	it("keeps a manual cashier discount when the server sends nothing", () => {
		const item = cartLine({ discount_percentage: 5, discount_amount: 44.95, discount_source: "manual_discount" });
		mergeServerLine(item, {}, undefined);
		expect(item.discount_percentage).toBe(5);
	});
});

describe("resolveHeaderDiscount (coupon vs apply_offers header)", () => {
	const coupon = { code: "FFDEMO40", percentage: 0, amount: 960, suppress_friends_and_family: true };

	it("keeps an applied coupon when the server reports no transaction-rule discount", () => {
		// Coupon beat F&F → F&F stamps stripped → cart re-evaluated → apply_offers
		// answers discount_amount 0. The coupon must survive (was the PN-130 bug).
		expect(resolveHeaderDiscount(0, coupon)).toEqual({ amount: 0, keepCoupon: true });
		expect(resolveHeaderDiscount(undefined, coupon)).toEqual({ amount: 0, keepCoupon: true });
		expect(resolveHeaderDiscount("0", coupon)).toEqual({ amount: 0, keepCoupon: true });
	});

	it("uses the server header discount when no coupon is applied", () => {
		expect(resolveHeaderDiscount(0, null)).toEqual({ amount: 0, keepCoupon: false });
		expect(resolveHeaderDiscount("125.5", null)).toEqual({ amount: 125.5, keepCoupon: false });
		expect(resolveHeaderDiscount(-5, null)).toEqual({ amount: 0, keepCoupon: false });
	});

	it("lets a real transaction-rule discount from the server through", () => {
		expect(resolveHeaderDiscount(50, coupon)).toEqual({ amount: 50, keepCoupon: false });
	});
});

describe("isFnfAllowedForProfile (POS Profile Allow F&F)", () => {
	it("defaults to allowed when the profile or field is missing", () => {
		expect(isFnfAllowedForProfile(null)).toBe(true);
		expect(isFnfAllowedForProfile(undefined)).toBe(true);
		expect(isFnfAllowedForProfile({})).toBe(true);
		expect(isFnfAllowedForProfile({ allow_friends_family: null })).toBe(true);
		expect(isFnfAllowedForProfile({ allow_friends_family: "" })).toBe(true);
	});
	it("allows when ticked", () => {
		expect(isFnfAllowedForProfile({ allow_friends_family: 1 })).toBe(true);
		expect(isFnfAllowedForProfile({ allow_friends_family: "1" })).toBe(true);
		expect(isFnfAllowedForProfile({ allow_friends_family: true })).toBe(true);
	});
	it("is off only for an explicit 0", () => {
		expect(isFnfAllowedForProfile({ allow_friends_family: 0 })).toBe(false);
		expect(isFnfAllowedForProfile({ allow_friends_family: "0" })).toBe(false);
		expect(isFnfAllowedForProfile({ allow_friends_family: false })).toBe(false);
	});
	it("normalizes the server's profile_not_allowed answer as not eligible", () => {
		const e = normalizeEligibility({ eligible: false, reason: FNF_REASON.PROFILE_NOT_ALLOWED, discount_percentage: 0 }, "X");
		expect(e).toMatchObject({ eligible: false, reason: "profile_not_allowed", discountPercentage: 0, program: null });
	});
});

describe("Approved Domains email block (F&F member with unapproved / unverified email)", () => {
	const blocked = (reason, message = "") =>
		normalizeEligibility({ eligible: false, reason, message, discount_percentage: 0 }, "C1");

	it("returns the server message for the email reasons only", () => {
		expect(fnfEmailBlockMessage(blocked("email_domain_not_approved", "srv domain"))).toBe("srv domain");
		expect(fnfEmailBlockMessage(blocked("email_not_verified", "srv verify"))).toBe("srv verify");
		expect(fnfEmailBlockMessage(blocked("not_eligible", "x"))).toBe("");
		expect(fnfEmailBlockMessage(null)).toBe("");
		expect(fnfEmailBlockMessage({ eligible: true, reason: "email_not_verified" })).toBe("");
	});
	it("falls back to a local text when the server sent no message", () => {
		expect(fnfEmailBlockMessage(blocked(FNF_REASON.EMAIL_NOT_VERIFIED))).toMatch(/verify/i);
		expect(fnfEmailBlockMessage(blocked(FNF_REASON.EMAIL_DOMAIN_NOT_APPROVED))).toMatch(/approved company domain/i);
	});
	it("shows a single warning in the cart messages", () => {
		const messages = buildFnfCartMessages({
			result: { eligible: false, appliedCount: 0, lines: [], caps: null },
			eligibility: blocked("email_domain_not_approved", "No F&F: approved domain needed"),
			hasItems: true,
		});
		expect(messages).toEqual([{ key: "email", tone: "warning", text: "No F&F: approved domain needed" }]);
	});
	it("shows nothing for an empty cart or a plain non-member", () => {
		expect(buildFnfCartMessages({ eligibility: blocked("email_not_verified", "m"), hasItems: false })).toEqual([]);
		expect(buildFnfCartMessages({ eligibility: blocked("not_eligible", "m"), hasItems: true })).toEqual([]);
	});
});
