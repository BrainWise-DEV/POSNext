// Run 3: re-test of the run-2 defects that are supposed to be fixed (G1, G3/G5, G4).
// Each test makes a real sale in the browser and checks the saved invoice on the server.
import { expect, test } from "@playwright/test";
import {
	AUTH, addItem, applyCoupon, breakdown, cartTotals, clearCart, coupons, errorsSince, expectSaleOk,
	expectSettingsClean, freeRows, inv, nowStamp, openPayment, openPos, record, row, selectCustomer, sell,
	setQty, shot, withCoupon, withFf, withRule, closeDialogs,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });

let since;
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
});
test.afterEach(() => expectSettingsClean());

const errs = () => errorsSince(since);

test("D-R2-08 G1 mixed-SKU GWP sells for a plain customer", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-GWP1");
	await addItem(page, "UIT-GWP2");
	await expect(freeRows(page)).toHaveCount(1);
	await shot(page, "D-R2-08-gwp-cart");
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	const free = s.invoice.items.filter((i) => i.is_free_item);
	expect(free.length).toBe(1);
	expect(free[0].pricing_rules).toContain("UIT-PR-GWP");
	expect(Number(free[0].rate)).toBe(0);
	record("D-R2-08", { invoice: s.name, total: s.total, free, errors: errs() });
});

test("D-R2-08b G1 mixed-SKU GWP with F&F and the gift checkbox on", async ({ page }) => {
	await withFf({ allow_free_gift_with_ff: 1 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-GWP1");
		await addItem(page, "UIT-GWP2");
		await expect(freeRows(page)).toHaveCount(1);
		const s = await sell(page);
		expectSaleOk(s.invoice, s.total);
		const paid = s.invoice.items.filter((i) => !i.is_free_item);
		const free = s.invoice.items.filter((i) => i.is_free_item);
		expect(free.length).toBe(1);
		expect(free[0].pricing_rules).toContain("UIT-PR-GWP");
		expect(paid.every((i) => i.posnext_discount_source === "friends_and_family")).toBeTruthy();
		record("D-R2-08b", { invoice: s.name, total: s.total, rows: s.invoice.items, usage: s.invoice.usage, errors: errs() });
	});
});

test("D-R2-15 G3 Add on top: UIT-L10 stacks on UIT-C under UIT-PR-C40", async ({ page }) => {
	await withCoupon("UIT-L10", { promotion_conflict: "Add on top" }, async () => {
		const before = coupons()["UIT-L10"];
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-C");
		await expect(breakdown(page, "UIT-C")).toContainText("30.00");
		const msg = await applyCoupon(page, "UIT-L10");
		await shot(page, "D-R2-15-addontop-cart");
		const lineText = await row(page, "UIT-C").innerText();
		const s = await sell(page);
		expectSaleOk(s.invoice, s.total);
		const c = s.invoice.items.find((i) => i.item_code === "UIT-C");
		record("D-R2-15", { invoice: s.name, total: s.total, row: c, lineText, msg, used: [before, coupons()["UIT-L10"]], errors: errs() });
		expect.soft(c.pricing_rules, "promoted line keeps its rule tag (D-10b1)").toContain("UIT-PR-C40");
		expect(c.posnext_coupon_code).toBe("UIT-L10");
		expect(Number(c.posnext_coupon_share)).toBeGreaterThan(0);
		// promotion 20 + coupon 10% of the promoted 30 = 3 -> rate 27
		expect(Number(c.rate)).toBeCloseTo(27, 2);
		expect(coupons()["UIT-L10"]).toBe(before + 1);
	});
});

test("G4/D-R2-11 the coupon is dropped on a walk-in -> named customer change", async ({ page }) => {
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L10");
	await expect(breakdown(page, "UIT-A")).toContainText("90.00");
	await selectCustomer(page, "UIT-Unverified");
	await expect(row(page, "UIT-A")).not.toContainText("UIT-L10");
	await expect(row(page, "UIT-A")).not.toContainText("90.00");
	await expect(page.getByRole("button", { name: /Remove coupon/ })).toHaveCount(0);
	const before = coupons()["UIT-L10"];
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.si.coupon_code || "").toBe("");
	expect(s.invoice.items[0].posnext_coupon_code || "").toBe("");
	expect(Number(s.invoice.items[0].rate)).toBe(100);
	expect(coupons()["UIT-L10"]).toBe(before);
	record("D-R2-11a", { invoice: s.name, errors: errs() });
});

test("G4/U-18c the coupon is dropped on an F&F -> plain customer change", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L50");
	await expect(breakdown(page, "UIT-A")).toContainText("50.00");
	await selectCustomer(page, "UIT-Unverified");
	await expect(row(page, "UIT-A")).not.toContainText("UIT-L50");
	await expect(row(page, "UIT-A")).not.toContainText("50.00");
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.si.coupon_code || "").toBe("");
	expect(Number(s.invoice.items[0].rate)).toBe(100);
	expect(s.invoice.items[0].posnext_discount_source || "").toBe("");
	record("U-18c", { invoice: s.name, errors: errs() });
});

test("G4/D-R2-06 a 100% coupon line shows Free at 0.00", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L100");
	const line = await row(page, "UIT-A").innerText();
	expect(line).toMatch(/Free/);
	const { dialog, total } = await openPayment(page);
	const dlg = await dialog.innerText();
	await shot(page, "D-R2-06-payment");
	expect(total).toBe(0);
	expect(dlg).toMatch(/UIT-A[^\n]*\n?[^\n]*0\.00/);
	expect(dlg).not.toMatch(/UIT-A\s*E£ 100\.00 × 1\s*E£ 100\.00/);
	await closeDialogs(page);
	const s = await sell(page);
	expectSaleOk(s.invoice, 0);
	expect(s.invoice.items[0].is_free_item).toBe(1);
	record("D-R2-06", { invoice: s.name, line, dlg: dlg.slice(0, 400), errors: errs() });
});

test("G4/D-R2-06b a 100% price-rule line (UIT-P100) shows Free at 0.00", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-P100");
	const line = await page.locator("body").innerText();
	const { dialog, total } = await openPayment(page);
	const dlg = await dialog.innerText();
	expect(total).toBe(0);
	expect(dlg).not.toMatch(/UIT-P100\s*E£ 25\.00 × 1\s*E£ 25\.00/);
	await closeDialogs(page);
	const s = await sell(page);
	expectSaleOk(s.invoice, 0);
	record("D-R2-06b", { invoice: s.name, dlg: dlg.slice(0, 400), cartHasFree: /Free/.test(line), errors: errs() });
});

test("G4/D-R2-07 the Tax row shows the server tax after a header (order) coupon", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A", 2);
	await addItem(page, "UIT-EXCL");
	await applyCoupon(page, "UIT-O100");
	const totals = await cartTotals(page);
	const { dialog, total } = await openPayment(page);
	const dlg = await dialog.innerText();
	await closeDialogs(page);
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	expect(totals.Tax).toBeCloseTo(Number(s.invoice.si.total_taxes_and_charges), 2);
	expect(Number(s.invoice.si.discount_amount)).toBeCloseTo(100, 2);
	expect(total).toBeCloseTo(Number(s.invoice.due), 2);
	record("D-R2-07", { invoice: s.name, totals, dlg: dlg.slice(0, 500), si: s.invoice.si, errors: errs() });
});

test("G4/D-R2-04 no F&F balance deduction is shown when an order promotion wins", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-EXCL");
	await setQty(page, "UIT-EXCL", 13);
	await addItem(page, "UIT-A");
	await expect(page.getByText(/Invoice promotion applied instead of Friends & Family/).first()).toBeVisible();
	const msgs = await page.getByTestId("fnf-cart-messages").innerText().catch(() => "");
	await shot(page, "D-R2-04-cart");
	const m = msgs.match(/([\d,]+\.\d+) left, E£ ([\d,]+\.\d+) after/);
	if (m) expect(m[1]).toBe(m[2]);
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.usage.length).toBe(0);
	expect(Number(s.invoice.si.discount_amount)).toBeGreaterThan(0);
	record("D-R2-04", { invoice: s.name, msgs, logs: s.invoice.logs, errors: errs() });
});

test("G4/D-R2-17 a used one-time offer says why it was not applied", async ({ page }) => {
	await withRule("UIT-PR-C40", { one_time_per_customer: 1 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-OTP2");
		await addItem(page, "UIT-C");
		await expect(breakdown(page, "UIT-C")).toContainText("30.00");
		const first = await sell(page);
		expectSaleOk(first.invoice, first.total);
		expect(first.invoice.one_time.length).toBe(1);
		await selectCustomer(page, "UIT-OTP2");
		await addItem(page, "UIT-C");
		await expect(page.getByTestId("one-time-offer-used")).toBeVisible();
		const msg = await page.getByTestId("one-time-offer-used").innerText();
		expect(msg).toMatch(/not applied: this customer already used this one-time offer/);
		const second = await sell(page);
		expectSaleOk(second.invoice, second.total);
		expect(Number(second.invoice.items[0].rate)).toBe(50);
		record("D-R2-17", { first: first.name, second: second.name, msg, errors: errs() });
	});
});

test("G4/D-R2-03 F&F eligibility is re-checked when F&F is turned back on", async ({ page }) => {
	await withFf({ enabled: 0 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-A");
		await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
		await expect(row(page, "UIT-A")).not.toContainText("70.00");
	});
	// reset_ff turned F&F back on: the next cart change must bring it back, before Checkout
	await setQty(page, "UIT-A", 2);
	await expect(breakdown(page, "UIT-A")).toContainText("140.00", { timeout: 30_000 });
	await expect(page.getByTestId("fnf-customer-badge")).toBeVisible();
	const s = await sell(page);
	record("D-R2-03", { invoice: s.name, errors: errs() });
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.items[0].posnext_discount_source).toBe("friends_and_family");
});

test("G4/D-R2-03b the header Refresh re-checks F&F after it is turned back on", async ({ page }) => {
	await withFf({ enabled: 0 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-A");
		await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
	});
	await page.getByRole("button", { name: "Refresh items and customers" }).click();
	await expect(breakdown(page, "UIT-A")).toContainText("70.00", { timeout: 30_000 });
	await expect(page.getByTestId("fnf-customer-badge")).toBeVisible();
	record("D-R2-03b", { ok: true, errors: errs() });
	await clearCart(page);
});

test("G4/D-R2-14 the payment dialog explains an invoice discount on an F&F cart", async ({ page }) => {
	const { withPos, payExact, successDialog } = await import("./lib/helpers.js");
	await withPos({ allow_user_to_edit_additional_discount: 1, max_discount_allowed: 10 }, async () => {
		await page.reload();
		await openPos(page);
		await clearCart(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-A", 2);
		await expect(breakdown(page, "UIT-A")).toContainText("140.00");
		const { dialog } = await openPayment(page);
		const input = dialog.locator("input[type=number]").first();
		await input.fill("10");
		await input.dispatchEvent("input");
		await page.waitForTimeout(1500);
		const conflict = dialog.getByTestId("fnf-invoice-discount-conflict");
		const visible = await conflict.isVisible().catch(() => false);
		const text = visible ? await conflict.innerText() : "";
		await shot(page, "D-R2-14-payment");
		const paid = await payExact(page, dialog).catch((e) => ({ err: e.message }));
		await page.waitForTimeout(2000);
		const after = await page.locator("body").innerText();
		await closeDialogs(page);
		const inv0 = paid.name ? inv(paid.name) : null;
		record("D-R2-14", { visible, text, invoice: paid.name, si: inv0?.si, rows: inv0?.items.map((i) => [i.rate, i.posnext_discount_source]), prompt: (after.match(/[^\n]*Invoice Total Changed[^\n]*/) || [""])[0], errors: errs() });
		expect(visible, "the F&F / invoice discount conflict is explained in the dialog").toBe(true);
		expect(text).toMatch(/Friends & Family/);
		if (inv0) expectSaleOk(inv0);
		await clearCart(page);
	});
});
