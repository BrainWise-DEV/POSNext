// Plan §3.2–3.4: F&F pricing, caps, coupons, offers, edit dialogs, SO strip
// (U-10, U-11, U-12, U-14, U-16, U-17, U-19, U-19b, U-20, U-21, U-22, U-23, U-24, U-26, U-27).
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince,
	expectSaleOk, expectSettingsClean, freeRows, nowStamp, openPayment, openPos, record, row, selectCustomer,
	sell, setQty, shot, waitIdle, withCoupon, withFf, withPos,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
});
test.afterEach(() => expectSettingsClean());

const sum = (a, f) => a.reduce((x, r) => x + Number(r[f] || 0), 0);
const logsOf = (inv) => inv.logs.map((l) => `${l.log_type}/${l.reason}/capped=${l.capped}/${l.cap_hit}`);

async function reopen(page) {
	await page.reload();
	await openPos(page);
	await clearCart(page);
}

test("U-10 (a) per-order cap 50, UIT-A x3", async ({ page }) => {
	await withFf({ max_discount_per_order: 50 }, async () => {
		await reopen(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-A");
		await setQty(page, "UIT-A", 3);
		const msgs = await page.getByTestId("fnf-cart-messages").innerText();
		const line = await row(page, "UIT-A").innerText();
		const s = await sell(page);
		const fnf = sum(s.invoice.items, "posnext_fnf_discount_amount");
		record("U-10a", { invoice: s.name, msgs, line, fnf, usage: s.invoice.usage, logs: logsOf(s.invoice), errors: errorsSince(since) });
		expectSaleOk(s.invoice, s.total);
		expect(fnf).toBeLessThanOrEqual(50);
		expect(fnf).toBeGreaterThanOrEqual(50 - 0.03);
		expect(msgs + line).toMatch(/reduced by the discount limit|capped/);
		expect(msgs).toMatch(/50\.00/);
		expect(sum(s.invoice.usage, "amount")).toBeCloseTo(fnf, 2);
		expect.soft(s.invoice.logs.some((l) => l.log_type === "Cap Hit" || l.capped), "Cap Hit audit (D-R2-02)").toBeTruthy();
	});
});

test("U-10 (b) per-order cap 50, UIT-ODD x7", async ({ page }) => {
	await withFf({ max_discount_per_order: 50 }, async () => {
		await reopen(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-ODD");
		await setQty(page, "UIT-ODD", 7);
		const s = await sell(page);
		const fnf = sum(s.invoice.items, "posnext_fnf_discount_amount");
		record("U-10b", { invoice: s.name, fnf, logs: logsOf(s.invoice), errors: errorsSince(since) });
		expectSaleOk(s.invoice, s.total);
		expect(fnf).toBeLessThanOrEqual(50);
		expect(fnf).toBeGreaterThanOrEqual(50 - 0.07);
	});
});

test("U-10 (c) default cap, UIT-ODD x3: line discount 30.00, USG = line", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-ODD");
	await setQty(page, "UIT-ODD", 3);
	const s = await sell(page);
	record("U-10c", { invoice: s.name, rows: s.invoice.items, usage: s.invoice.usage });
	expectSaleOk(s.invoice, s.total);
	expect(sum(s.invoice.items, "posnext_fnf_discount_amount")).toBeCloseTo(30, 2);
	expect(sum(s.invoice.usage, "amount")).toBeCloseTo(30, 2);
});

test("U-11 kill switch while a cart is open: (a) Hold then resume re-prices to list, (b) Checkout re-prices", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await withFf({ enabled: 0 }, async () => {
		// (a) Hold straight away (held carts are kept in the browser), then resume it
		await page.getByRole("button", { name: "Hold", exact: true }).click();
		await expect(page.getByText("Your cart is empty")).toBeVisible();
		await page.getByRole("button", { name: /Draft Invoices/ }).click();
		const drafts = page.getByRole("dialog").filter({ hasText: "Draft" });
		const listed = await drafts.innerText();
		await drafts.getByText("UIT-Verified").first().click();
		await waitIdle(page, 2500);
		await closeDialogs(page);
		const resumed = (await row(page, "UIT-A").innerText()).replace(/\s+/g, " ");
		// (b) Checkout on that cart: no F&F reaches payment
		const { changed, total } = await openPayment(page).catch(() => ({ changed: "error" }));
		await closeDialogs(page);
		await clearCart(page);
		record("U-11", { listed: listed.slice(0, 300), resumed, changed, total });
		expect(resumed).not.toContain("70.00");
		expect(total).toBeCloseTo(115, 2);
	});
});

test("U-12 (a) F&F beats a 20% rule, (b) a 40% rule beats F&F", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-B");
	await addItem(page, "UIT-C");
	await expect(breakdown(page, "UIT-B")).toContainText("140.00");
	await expect(breakdown(page, "UIT-C")).toContainText("30.00");
	const bNote = await row(page, "UIT-B").innerText();
	const cNote = await row(page, "UIT-C").innerText();
	const s = await sell(page);
	const b = s.invoice.items.find((i) => i.item_code === "UIT-B");
	const c = s.invoice.items.find((i) => i.item_code === "UIT-C");
	record("U-12", { invoice: s.name, bNote, cNote, b, c, logs: logsOf(s.invoice), changed: s.changed });
	expectSaleOk(s.invoice, s.total);
	expect(b.posnext_discount_source).toBe("friends_and_family");
	expect(Number(b.rate)).toBe(140);
	expect(c.posnext_discount_source || "").not.toBe("friends_and_family");
	expect(Number(c.rate)).toBe(30);
	expect.soft(b.posnext_fnf_replaced_discount || "", "signed replaced-discount envelope (D-10a)").toContain("sig");
	expect.soft(c.pricing_rules || "", "promotion line keeps its rule tag (D-10b1)").toContain("UIT-PR-C40");
	expect.soft(s.invoice.logs.some((l) => l.log_type === "Comparison Lost"), "Comparison Lost log (D-10b2, deferred)").toBeTruthy();
});

test("U-14 coupon dialog: F&F hint, unknown code, remove", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await page.getByRole("button", { name: "Apply coupon code" }).click();
	const hint = await page.getByTestId("coupon-fnf-hint").innerText();
	const dlg = page.getByRole("dialog").last();
	await dlg.getByPlaceholder(/ENTER-CODE-HERE/i).fill("NOPE-123");
	await dlg.getByRole("button", { name: "Apply", exact: true }).click();
	await expect(dlg.getByText("Sorry, this coupon code does not exist")).toBeVisible();
	const focus = await page.evaluate(() => document.activeElement?.tagName + "/" + (document.activeElement?.getAttribute("aria-label") || ""));
	await closeDialogs(page);
	await selectCustomer(page, "UIT-Unverified");
	await applyCoupon(page, "UIT-L10");
	await expect(breakdown(page, "UIT-A")).toContainText("90.00");
	await page.getByRole("button", { name: /Remove coupon/ }).first().click();
	await expect(page.getByText(/Discount has been removed/).first()).toBeVisible();
	await expect(row(page, "UIT-A")).not.toContainText("90.00");
	record("U-14", { hint, focusAfterError: focus });
	expect(hint).toContain("Friends & Family customer (30%). Only the better discount applies — coupon or Friends & Family, never both.");
	await clearCart(page);
});

test("U-16 (a) scoped coupon UIT-SI20, (b) Better-of-the-two UIT-BET", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-A2");
	await applyCoupon(page, "UIT-SI20");
	await expect(breakdown(page, "UIT-A")).toContainText("80.00");
	await expect(row(page, "UIT-A2")).not.toContainText("80.00");
	const s1 = await sell(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-B");
	await addItem(page, "UIT-C");
	const toast = applyCoupon(page, "UIT-BET");
	const toastText = await page.getByText(/saves more/i).first().innerText({ timeout: 8000 }).catch(() => "");
	await toast;
	await expect(breakdown(page, "UIT-B")).toContainText("140.00");
	await expect(breakdown(page, "UIT-C")).toContainText("30.00");
	const bLabel = await row(page, "UIT-B").innerText();
	const s2 = await sell(page);
	const b = s2.invoice.items.find((i) => i.item_code === "UIT-B");
	const c = s2.invoice.items.find((i) => i.item_code === "UIT-C");
	record("U-16", { a: s1.name, aRows: s1.invoice.items.map((i) => [i.item_code, i.rate, i.posnext_coupon_code]), b: s2.name, bRow: b, cRow: c, toastText, bLabel });
	expectSaleOk(s1.invoice, s1.total);
	expectSaleOk(s2.invoice, s2.total);
	expect(s1.invoice.items.find((i) => i.item_code === "UIT-A").posnext_coupon_code).toBe("UIT-SI20");
	expect(s1.invoice.items.find((i) => i.item_code === "UIT-A2").posnext_coupon_code || "").toBe("");
	expect(b.posnext_coupon_code).toBe("UIT-BET");
	expect(c.posnext_coupon_code || "").toBe("");
	expect.soft(c.pricing_rules || "", "UIT-C keeps UIT-PR-C40 tag (D-10b1)").toContain("UIT-PR-C40");
});

test("U-17 100% coupon = free row, CPN.used +1", async ({ page }) => {
	const before = coupons()["UIT-L100"];
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L100");
	const s = await sell(page);
	record("U-17", { invoice: s.name, row: s.invoice.items[0], used: [before, coupons()["UIT-L100"]] });
	expectSaleOk(s.invoice, 0);
	expect(s.invoice.items[0].is_free_item).toBe(1);
	expect(s.invoice.items[0].posnext_coupon_code).toBe("UIT-L100");
	expect(coupons()["UIT-L100"]).toBe(before + 1);
});

test("U-18 (a) F&F beats UIT-L10: coupon not applied, USG written", async ({ page }) => {
	const before = coupons()["UIT-L10"];
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	const text = await applyCoupon(page, "UIT-L10", { close: false });
	const cmp = await page.getByTestId("coupon-comparison-message").innerText().catch(() => text);
	await closeDialogs(page);
	const s = await sell(page);
	record("U-18a", { invoice: s.name, cmp, usage: s.invoice.usage });
	expect(cmp).toMatch(/Friends & Family discount \(30%\) is better than coupon UIT-L10 \(10%\)/);
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.si.coupon_code || "").toBe("");
	expect(coupons()["UIT-L10"]).toBe(before);
	expect(s.invoice.usage.length).toBe(1);
});

test("U-19 coupon on one line, F&F on another; Remove keeps F&F", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-EXCL");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L20");
	await expect(breakdown(page, "UIT-EXCL")).toContainText("64.00");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	const s = await sell(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-EXCL");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L20");
	await page.getByRole("button", { name: /Remove coupon/ }).first().click();
	await waitIdle(page);
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await expect(row(page, "UIT-EXCL")).not.toContainText("64.00");
	record("U-19", { invoice: s.name, rows: s.invoice.items.map((i) => [i.item_code, i.rate, i.posnext_coupon_code, i.posnext_discount_source]), usage: s.invoice.usage });
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.si.coupon_code).toBe("UIT-L20");
	expect(s.invoice.items.find((i) => i.item_code === "UIT-EXCL").posnext_coupon_code).toBe("UIT-L20");
	expect(s.invoice.items.find((i) => i.item_code === "UIT-A").posnext_discount_source).toBe("friends_and_family");
	expect(sum(s.invoice.usage, "amount")).toBeCloseTo(30, 2);
	await clearCart(page);
});

test("U-19b (b) Add on top within the S2 max discount, (c) the same coupon twice and after a reload", async ({ page }) => {
	await withCoupon("UIT-L20", { promotion_conflict: "Add on top" }, async () => {
		await withPos({ allow_user_to_edit_rate: 1, max_discount_allowed: 45 }, async () => {
			await reopen(page);
			// (b) UIT-C: rule 40% + coupon 20% on top = 52% > 45% max
			await selectCustomer(page, "UIT-Unverified");
			await addItem(page, "UIT-C");
			const msgB = await applyCoupon(page, "UIT-L20", { close: false });
			const bodyB = await page.locator("body").innerText();
			await closeDialogs(page);
			const lineB = await row(page, "UIT-C").innerText();
			// (c) the same coupon again
			const again = await applyCoupon(page, "UIT-L20", { close: false });
			await closeDialogs(page);
			const lineC1 = await row(page, "UIT-C").innerText();
			await page.reload();
			await openPos(page);
			const lineC2 = await row(page, "UIT-C").innerText();
			const again2 = await applyCoupon(page, "UIT-L20", { close: false });
			await closeDialogs(page);
			const lineC3 = await row(page, "UIT-C").innerText();
			const before = coupons()["UIT-L20"];
			const s = await sell(page);
			const c = s.invoice.items[0];
			record("U-19b-bc", { invoice: s.name, c, msgB: msgB.slice(0, 400), capNote: (bodyB.match(/[^\n]*(maximum|max|limit)[^\n]*/i) || [""])[0], lineB, again: again.slice(0, 300), again2: again2.slice(0, 300), lineC1, lineC2, lineC3, used: [before, coupons()["UIT-L20"]], errors: errorsSince(since) });
			expectSaleOk(s.invoice, s.total);
			expect(Number(c.discount_percentage)).toBeLessThanOrEqual(45.0001);
			expect(lineC1).toBe(lineB);
			expect(lineC3.replace(/\s+/g, " ")).toBe(lineC2.replace(/\s+/g, " "));
			expect(coupons()["UIT-L20"]).toBe(before + 1);
		});
	});
});

test("U-19b fixed-amount and capped coupons Add on top: the limit counts only the coupon share", async ({ page }) => {
	await withCoupon("UIT-O40", { promotion_conflict: "Add on top" }, async () => {
		await withCoupon("UIT-L50", { promotion_conflict: "Add on top", max_amount: 5 }, async () => {
			await reopen(page);
			// fixed 40 on top of UIT-C x2 (2 x 30 after the 40% rule)
			await selectCustomer(page, "UIT-Unverified");
			await addItem(page, "UIT-C");
			await setQty(page, "UIT-C", 2);
			await applyCoupon(page, "UIT-O40");
			const lineFixed = await row(page, "UIT-C").innerText();
			const s1 = await sell(page);
			// 50% capped at 5 on top of UIT-C (30 after rule)
			await selectCustomer(page, "UIT-Unverified");
			await addItem(page, "UIT-C");
			await applyCoupon(page, "UIT-L50");
			const lineCap = await row(page, "UIT-C").innerText();
			const s2 = await sell(page);
			const r1 = s1.invoice.items[0];
			const r2 = s2.invoice.items[0];
			record("U-19b-limits", { fixed: s1.name, r1, lineFixed, capped: s2.name, r2, lineCap, errors: errorsSince(since) });
			expectSaleOk(s1.invoice, s1.total);
			expectSaleOk(s2.invoice, s2.total);
			expect(Number(r1.posnext_coupon_share) * r1.qty, "coupon share is per unit").toBeCloseTo(40, 2);
			expect(Number(r1.amount)).toBeCloseTo(60 - 40, 2);
			expect(Number(r2.posnext_coupon_share)).toBeCloseTo(5, 2);
			expect(Number(r2.rate)).toBeCloseTo(25, 2);
		});
	});
});

test("U-20 (a) O40 refused vs F&F 60, (b) O100 wins the whole order", async ({ page }) => {
	const before = coupons()["UIT-O100"];
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await setQty(page, "UIT-A", 2);
	const a = await applyCoupon(page, "UIT-O40", { close: false });
	const cmpA = await page.getByTestId("coupon-comparison-message").innerText().catch(() => a);
	await closeDialogs(page);
	await expect(breakdown(page, "UIT-A")).toContainText("140.00");
	await addItem(page, "UIT-EXCL");
	await applyCoupon(page, "UIT-O100");
	await expect(page.getByTestId("fnf-customer-badge")).toHaveAttribute("title", /Coupon UIT-O100 applied instead of Friends & Family/);
	const s = await sell(page);
	record("U-20", { cmpA, invoice: s.name, si: s.invoice.si, usage: s.invoice.usage, logs: logsOf(s.invoice) });
	expect(cmpA).toMatch(/better than coupon UIT-O40/);
	expectSaleOk(s.invoice, s.total);
	expect(Number(s.invoice.si.discount_amount)).toBeCloseTo(100, 2);
	expect(s.invoice.items.every((i) => i.posnext_discount_source !== "friends_and_family")).toBeTruthy();
	expect(s.invoice.usage).toHaveLength(0);
	expect(coupons()["UIT-O100"]).toBe(before + 1);
});

test("U-21 (a) BXGY x2 + UIT-A with F&F, checkbox off", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await addItem(page, "UIT-A");
	await expect(row(page, "UIT-BXGY")).toContainText("Promotion item — not eligible for Friends & Family");
	await expect(freeRows(page)).toHaveCount(1);
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	const s = await sell(page);
	record("U-21a", { invoice: s.name, rows: s.invoice.items.map((i) => [i.item_code, i.qty, i.rate, i.is_free_item, i.pricing_rules, i.posnext_discount_source]), usage: s.invoice.usage });
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.items.filter((i) => i.is_free_item && i.pricing_rules.includes("UIT-PR-BXGY"))).toHaveLength(1);
	expect(sum(s.invoice.usage, "amount")).toBeCloseTo(30, 2);
});

for (const allow of [0, 1]) {
	test(`U-22 free gifts with F&F, allow_free_gift_with_ff=${allow}`, async ({ page }) => {
		await withFf({ allow_free_gift_with_ff: allow }, async () => {
			await reopen(page);
			const out = {};
			// (i) free item
			await selectCustomer(page, "UIT-Verified");
			await addItem(page, "UIT-TRIG");
			await expect(breakdown(page, "UIT-TRIG")).toContainText("70.00");
			out.i = await freeRows(page).count();
			const si = await sell(page);
			out.iInv = si.name;
			out.iRows = si.invoice.items.map((i) => [i.item_code, i.is_free_item, i.pricing_rules]);
			expectSaleOk(si.invoice, si.total);
			// (ii) GWP
			await selectCustomer(page, "UIT-Verified");
			await addItem(page, "UIT-GWP1");
			await addItem(page, "UIT-GWP2");
			out.ii = await freeRows(page).count();
			const sii = await sell(page);
			out.iiInv = sii.name;
			out.iiRows = sii.invoice.items.map((i) => [i.item_code, i.is_free_item, i.pricing_rules, i.posnext_discount_source]);
			expectSaleOk(sii.invoice, sii.total);
			// (iii) cart total gift x8 then x7
			await selectCustomer(page, "UIT-Verified");
			await addItem(page, "UIT-A");
			await setQty(page, "UIT-A", 8);
			out.iii8 = await freeRows(page).count();
			await setQty(page, "UIT-A", 7);
			out.iii7 = await freeRows(page).count();
			await setQty(page, "UIT-A", 8);
			const siii = await sell(page);
			out.iiiInv = siii.name;
			out.iiiRows = siii.invoice.items.map((i) => [i.item_code, i.is_free_item, i.pricing_rules]);
			expectSaleOk(siii.invoice, siii.total);
			record(`U-22-${allow}`, { ...out, errors: errorsSince(since) });
			const freeSaved = (rows) => rows.filter((r) => r[1]).length;
			if (allow) {
				expect(out.i).toBe(1);
				expect(out.ii).toBe(1);
				expect(out.iii8).toBe(1);
				expect(out.iii7).toBe(0);
				expect(freeSaved(out.iRows)).toBe(1);
				expect(freeSaved(out.iiRows)).toBe(1);
				expect(freeSaved(out.iiiRows)).toBe(1);
			} else {
				expect(out.i + out.ii + out.iii8 + out.iii7).toBe(0);
				expect(freeSaved(out.iRows) + freeSaved(out.iiRows) + freeSaved(out.iiiRows)).toBe(0);
			}
		});
	});
}

test("U-23 (b) TRIG gift, (c) P100 free, (d) cart gift at 500 not 400", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-TRIG");
	await expect(freeRows(page)).toHaveCount(1);
	const sb = await sell(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-P100");
	const sc = await sell(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await setQty(page, "UIT-A", 5);
	const at5 = await freeRows(page).count();
	await setQty(page, "UIT-A", 4);
	const at4 = await freeRows(page).count();
	await setQty(page, "UIT-A", 5);
	const sd = await sell(page);
	record("U-23bcd", { b: sb.name, bRows: sb.invoice.items.map((i) => [i.item_code, i.is_free_item, i.rate, i.pricing_rules]), c: sc.name, cRow: sc.invoice.items[0], at5, at4, d: sd.name, dRows: sd.invoice.items.map((i) => [i.item_code, i.is_free_item, i.pricing_rules]) });
	for (const s of [sb, sc, sd]) expectSaleOk(s.invoice, s.total);
	expect(sb.invoice.items.find((i) => i.is_free_item).pricing_rules).toContain("UIT-PR-FREE");
	expect(sc.invoice.items[0].is_free_item).toBe(1);
	expect(sc.invoice.items[0].pricing_rules).toContain("UIT-PR-P100");
	expect(at5).toBe(1);
	expect(at4).toBe(0);
	expect(sd.invoice.items.find((i) => i.is_free_item).pricing_rules).toContain("UIT-PR-CART-GIFT");
});

test("U-24 (a) no-price item refused, (b) the free row cannot be edited", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await page.getByRole("textbox", { name: /Search items/ }).fill("UIT-NOPRICE");
	await page.getByRole("button", { name: "UIT-NOPRICE", exact: true }).click();
	const msg = await page.getByText(/has no price/).first().innerText({ timeout: 10_000 }).catch(() => "");
	const added = await row(page, "UIT-NOPRICE").count();
	await page.getByRole("textbox", { name: /Search items/ }).fill("");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await freeRows(page).first().click();
	await page.waitForTimeout(1000);
	const opened = await page.getByRole("dialog").count();
	const dlgText = opened ? await page.getByRole("dialog").last().innerText() : "";
	await closeDialogs(page);
	record("U-24", { msg, added, opened, dlgText: dlgText.slice(0, 200) });
	expect(msg).toContain("Item UIT-NOPRICE has no price and cannot be sold at zero price.");
	expect(added).toBe(0);
	expect(opened === 0 || /cannot be edited/.test(dlgText)).toBeTruthy();
	await clearCart(page);
});

test("U-26 edit dialogs: (a) S0 rate disabled, (b) S2 rate 85, (c) S2 rate 0, (d) S4 header capped", async ({ page }) => {
	const out = {};
	const openEdit = async () => {
		await row(page, "UIT-A").getByRole("heading", { name: "UIT-A", exact: true }).click();
		await expect(page.getByText("Edit Item Details")).toBeVisible();
	};
	const cancelEdit = async () => page.getByRole("button", { name: "Cancel", exact: true }).last().click().catch(() => {});
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await openEdit();
	const locked = page.getByRole("spinbutton", { name: "Rate editing is disabled" });
	out.a = { lockedVisible: await locked.isVisible().catch(() => false), disabled: await locked.isDisabled().catch(() => null) };
	await cancelEdit();
	await clearCart(page);
	await withPos({ allow_user_to_edit_rate: 1, max_discount_allowed: 10 }, async () => {
		await reopen(page);
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-A");
		await openEdit();
		const rate = page.getByRole("spinbutton").filter({ hasText: "" }).nth(1);
		const rateBox = page.locator("input").filter({ has: page.locator("xpath=self::*[@type='number']") });
		const r = page.getByRole("spinbutton", { name: /rate/i }).or(page.locator("xpath=//*[text()='Rate']/following::input[1]")).first();
		await r.fill("85");
		await page.getByRole("button", { name: "Update Item" }).click();
		await page.waitForTimeout(1200);
		out.b = ((await page.locator("body").innerText()).match(/[^\n]*exceeds maximum allowed discount[^\n]*/) || [""])[0];
		if (await page.getByText("Edit Item Details").isVisible().catch(() => false)) {
			await r.fill("0");
			await page.getByRole("button", { name: "Update Item" }).click();
			await page.waitForTimeout(1200);
			out.c = ((await page.locator("body").innerText()).match(/[^\n]*Rate must be greater than zero[^\n]*/) || [""])[0];
			await cancelEdit();
		}
		await clearCart(page);
		void rate;
		void rateBox;
	});
	await withPos({ allow_user_to_edit_additional_discount: 1, max_discount_allowed: 10 }, async () => {
		await reopen(page);
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-A");
		const { dialog } = await openPayment(page);
		const input = dialog.locator("input[type=number]").first();
		await input.fill("15");
		await input.dispatchEvent("input");
		await page.waitForTimeout(1000);
		out.d = { value: await input.inputValue(), toast: ((await page.locator("body").innerText()).match(/[^\n]*Maximum allowed discount[^\n]*/) || [""])[0] };
		await shot(page, "U-26d-payment");
		await closeDialogs(page);
		await clearCart(page);
	});
	record("U-26", out);
	expect(out.a.lockedVisible).toBe(true);
	expect(out.b).toMatch(/Rate reduction of 15\.00% exceeds maximum allowed discount of 10%/);
	expect(out.c).toContain("Rate must be greater than zero");
	expect(Number(out.d.value)).toBeLessThanOrEqual(10);
});

test("U-27 Sales Order strip and back", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-B");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await page.getByRole("button", { name: "Order", exact: true }).click();
	const toast = await page.getByText("Friends & Family discounts apply to invoices only").first().innerText({ timeout: 15_000 }).catch(() => "");
	await waitIdle(page);
	const soA = await row(page, "UIT-A").innerText();
	await page.getByRole("button", { name: "Invoice", exact: true }).click();
	await waitIdle(page, 2000);
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	record("U-27", { toast, soA });
	expect(toast).toContain("Friends & Family discounts apply to invoices only");
	expect(soA).not.toContain("70.00");
	await clearCart(page);
});
