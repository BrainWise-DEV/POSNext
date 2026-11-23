// Re-checks behind two P1 findings: D-R3-10 (allow_return = 0 does not stop a POS return) and
// D-R3-08 (a coupon over its limit at Checkout shows no message). Runs as uit-cashier2 (open shift).
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince, expectSettingsClean,
	inv, nowStamp, openPayment, openPos, payExact, record, restoreDoc, selectCustomer, sell, server, setDoc, shot,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier2 });
let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

test("D-R3-10 with allow_return = 0 a POS return still goes through", async ({ page }) => {
	const flag = server("get", { doctype: "POS Settings", name: POS_SETTINGS, fields: ["allow_return"] });
	expect(flag.allow_return).toBe(0);
	await openPos(page);
	await clearCart(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A2");
	const s = await sell(page);
	await page.getByRole("button", { name: "Return Invoice" }).click();
	const dlg = page.getByRole("dialog").filter({ hasText: /Return/ }).last();
	await dlg.getByRole("textbox").first().fill(s.name);
	await page.waitForTimeout(1500);
	await dlg.getByText(s.name).first().click();
	await expect(dlg.getByText("Select Items to Return")).toBeVisible({ timeout: 30_000 });
	await dlg.getByRole("button", { name: "Select All" }).click();
	const done = page.waitForResponse((r) => r.url().includes("submit_invoice") && r.request().method() === "POST", { timeout: 60_000 }).catch(() => null);
	await dlg.getByRole("button", { name: "Create Return" }).click();
	const res = await done;
	let body = {};
	try {
		body = res ? await res.json() : {};
	} catch {}
	await page.waitForTimeout(1500);
	const screen = await page.locator("body").innerText();
	await shot(page, "D-R3-10-return-with-flag-0");
	await closeDialogs(page);
	const ret = body.message?.name ? inv(body.message.name) : null;
	record("D-R3-10", { allow_return: flag.allow_return, original: s.name, status: res?.status(), ret: ret?.si.name, retStatus: ret?.si.status, paidBack: ret ? -ret.payments.reduce((a, p) => a + p.amount, 0) : null, screen: (screen.match(/[^\n]*(not allowed|disabled|Return invoice .* created)[^\n]*/i) || [""])[0], errors: errorsSince(since) });
	expect(ret, "the return was created although allow_return = 0").toBeNull();
});

test("D-R3-08 recheck: coupon over its limit at Checkout — capture every new text line", async ({ page, browser }) => {
	const used = coupons()["UIT-MAX1"];
	setDoc("POS Coupon", "UIT-MAX1", { maximum_use: used + 1 });
	try {
		await openPos(page);
		await clearCart(page);
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-A");
		await applyCoupon(page, "UIT-MAX1");
		await expect(breakdown(page, "UIT-A")).toContainText("90.00");
		// another cashier uses the last allowed use
		const ctxA = await browser.newContext({ storageState: AUTH.cashier });
		const a = await ctxA.newPage();
		await openPos(a);
		await clearCart(a);
		await selectCustomer(a, "UIT-Unverified");
		await addItem(a, "UIT-A");
		await applyCoupon(a, "UIT-MAX1");
		const sa = await sell(a);
		await ctxA.close();
		const before = new Set((await page.locator("body").innerText()).split("\n").map((x) => x.trim()));
		await page.getByRole("button", { name: "Proceed to payment" }).click();
		const seen = new Set();
		for (let i = 0; i < 40; i++) {
			await page.waitForTimeout(250);
			for (const line of (await page.locator("body").innerText()).split("\n").map((x) => x.trim())) {
				if (line && !before.has(line)) seen.add(line);
			}
		}
		await shot(page, "D-R3-08-recheck");
		const newLines = [...seen];
		const msg = newLines.filter((l) => /coupon|maximum|limit|not applicable|usage/i.test(l));
		record("D-R3-08", { a: sa.name, used: [used, coupons()["UIT-MAX1"]], newLines: newLines.slice(0, 40), msg, errors: errorsSince(since) });
		await closeDialogs(page);
		await clearCart(page);
		expect(msg.length, `a coupon message is shown (new lines: ${JSON.stringify(newLines).slice(0, 300)})`).toBeGreaterThan(0);
	} finally {
		restoreDoc("coupons", "UIT-MAX1", ["maximum_use"]);
	}
});
