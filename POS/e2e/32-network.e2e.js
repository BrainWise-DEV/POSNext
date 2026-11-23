// Plan §3.5: offline, network failure, lost response and the queue (U-28 – U-32), F5/F6 idempotency.
// Offline = context.setOffline(true) plus aborting /api/method/* at the context, so neither the page
// nor its workers reach the server; each test polls the server until its sale exists.
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, api, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince,
	expectSaleOk, expectSettingsClean, ffReset, ffSet, freeRows, inv, nowStamp, openPayment, openPos,
	payExact, pollServer, record, restoreDoc, row, selectCustomer, sell, server, setDoc, setQty, shot,
	successDialog, waitIdle, payOffline,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
	await expect(page.getByRole("button", { name: "Cache ready" })).toBeVisible({ timeout: 120_000 });
});
test.afterEach(() => expectSettingsClean());

const blockApi = (route) => route.abort("internetdisconnected");
async function goOffline(page, context) {
	await context.route("**/api/method/**", blockApi);
	await context.setOffline(true);
	await expect(page.getByRole("button", { name: /Offline mode/ })).toBeVisible({ timeout: 30_000 });
}
async function goOnline(page, context) {
	await context.unroute("**/api/method/**", blockApi);
	await context.setOffline(false);
}
async function payOfflineT(page) {
	const r = await payOffline(page);
	if (r.error) await clearCart(page); // the sale is queued even when the checkout shows an error
	lastOfflineError = r.error;
	return r.total;
}
let lastOfflineError = null;
const latestFor = (customer) => server("latest", { customer, since, n: 5 }).filter((x) => x.docstatus === 1);

test("U-28 offline sale with a BXGY free row syncs; queue goes to 0", async ({ page, context }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await expect(freeRows(page)).toHaveCount(1);
	await goOffline(page, context);
	const total = await payOfflineT(page);
	await page.waitForTimeout(5000);
	const during = latestFor("UIT-Unverified").length;
	await goOnline(page, context);
	const name = await pollServer(() => latestFor("UIT-Unverified")[0]?.name, { timeout: 120_000, message: "U-28 sync" });
	const d = inv(name);
	record("U-28", { offlineError: lastOfflineError, invoice: name, total, during, rows: d.items.map((i) => [i.item_code, i.qty, i.rate, i.is_free_item, i.pricing_rules]), ois: d.offline_sync, errors: errorsSince(since) });
	expect(during, "nothing reaches the server while offline").toBe(0);
	expectSaleOk(d, total);
	expect(d.items.filter((i) => i.is_free_item)).toHaveLength(1);
	expect(d.offline_sync[0]?.status).toBe("Synced");
});

test("U-29 (b) priced online at 70, paid offline -> saved at 70, USG 30", async ({ page, context }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await goOffline(page, context);
	const total = await payOfflineT(page);
	await goOnline(page, context);
	const name = await pollServer(() => latestFor("UIT-Verified")[0]?.name, { timeout: 120_000, message: "U-29b sync" });
	const d = inv(name);
	record("U-29b", { offlineError: lastOfflineError, invoice: name, total, rows: d.items, usage: d.usage, errors: errorsSince(since) });
	expectSaleOk(d, total);
	expect(Number(d.items[0].rate)).toBe(70);
	expect(d.usage[0].amount).toBe(30);
});

test("U-29 (c) monthly cap spent by another cashier while offline -> saved at 70, logged cap_exceeded", async ({ page, context, browser }) => {
	const used = server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });
	ffSet({ max_discount_per_customer_month: used + 30 });
	try {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Cap");
		await addItem(page, "UIT-A");
		await expect(breakdown(page, "UIT-A")).toContainText("70.00");
		await goOffline(page, context);
		const ctxB = await browser.newContext({ storageState: AUTH.cashier2 });
		const b = await ctxB.newPage();
		await openPos(b);
		await clearCart(b);
		await selectCustomer(b, "UIT-Cap");
		await addItem(b, "UIT-A");
		const sb = await sell(b);
		await ctxB.close();
		const total = await payOfflineT(page);
		await goOnline(page, context);
		const name = await pollServer(() => latestFor("UIT-Cap").find((x) => x.name !== sb.name)?.name, { timeout: 120_000, message: "U-29c sync" });
		const d = inv(name);
		const after = server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });
		record("U-29c", { offlineError: lastOfflineError, b: sb.name, invoice: name, used, after, rows: d.items, logs: d.logs, errors: errorsSince(since) });
		expectSaleOk(d, total);
		expect(Number(d.items[0].rate)).toBe(70);
		expect(d.logs.some((l) => l.log_type === "Offline Disagreement" && l.reason === "cap_exceeded")).toBeTruthy();
		expect(after).toBeCloseTo(used + 60, 2);
	} finally {
		ffReset();
	}
});

test("U-29 (d) gift priced online, rule disabled before the sync -> saved, Unbacked free item logged", async ({ page, context }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-TRIG");
	await expect(freeRows(page)).toHaveCount(1);
	await goOffline(page, context);
	const total = await payOfflineT(page);
	setDoc("Pricing Rule", "UIT-PR-FREE", { disable: 1 });
	try {
		await goOnline(page, context);
		const name = await pollServer(() => latestFor("UIT-Unverified")[0]?.name, { timeout: 120_000, message: "U-29d sync" });
		const d = inv(name);
		const errs = errorsSince(since);
		record("U-29d", { offlineError: lastOfflineError, invoice: name, rows: d.items.map((i) => [i.item_code, i.is_free_item, i.pricing_rules]), errors: errs });
		expectSaleOk(d, total);
		expect(errs.some((e) => /Unbacked free item|not backed/i.test(e.head + e.method))).toBeTruthy();
	} finally {
		restoreDoc("rules", "UIT-PR-FREE", ["disable"]);
	}
});

for (const policy of ["Allow and log", "Reject"]) {
	test(`U-30 offline coupon overshoot, policy ${policy}`, async ({ page, context, browser }) => {
		const used = coupons()["UIT-MAX1"];
		setDoc("POS Coupon", "UIT-MAX1", { maximum_use: used + 1 });
		setDoc("POS Settings", POS_SETTINGS, { offline_coupon_overshoot: policy });
		try {
			await page.reload();
			await openPos(page);
			await selectCustomer(page, "UIT-Unverified");
			await addItem(page, "UIT-A");
			await applyCoupon(page, "UIT-MAX1");
			await expect(breakdown(page, "UIT-A")).toContainText("90.00");
			await goOffline(page, context);
			const ctxB = await browser.newContext({ storageState: AUTH.cashier2 });
			const b = await ctxB.newPage();
			await openPos(b);
			await clearCart(b);
			await selectCustomer(b, "UIT-Unverified");
			await addItem(b, "UIT-A");
			await applyCoupon(b, "UIT-MAX1");
			const sb = await sell(b);
			await ctxB.close();
			const total = await payOfflineT(page);
			await goOnline(page, context);
			await page.waitForTimeout(15_000);
			await page.getByRole("button", { name: /Online mode/ }).click().catch(() => {});
			let name = null;
			if (policy === "Allow and log") {
				name = await pollServer(() => latestFor("UIT-Unverified").find((x) => x.name !== sb.name)?.name, { timeout: 120_000, message: "U-30 sync" });
			} else {
				await page.waitForTimeout(20_000);
				name = latestFor("UIT-Unverified").find((x) => x.name !== sb.name)?.name || null;
			}
			const queue = await page.locator("body").innerText();
			await shot(page, `U-30-${policy.replace(/ /g, "")}`);
			const errs = errorsSince(since);
			record(`U-30-${policy}`, { offlineError: lastOfflineError, b: sb.name, invoice: name, used: [used, coupons()["UIT-MAX1"]], failedVisible: /failed/i.test(queue), errors: errs });
			if (policy === "Allow and log") {
				expect(name).toBeTruthy();
				expectSaleOk(inv(name), total);
				expect(coupons()["UIT-MAX1"]).toBe(used + 2);
				expect(errs.some((e) => /POS Coupon check/.test(e.head + e.method))).toBeTruthy();
			} else {
				expect(name).toBeNull();
				expect(coupons()["UIT-MAX1"]).toBe(used + 1);
			}
		} finally {
			restoreDoc("coupons", "UIT-MAX1", ["maximum_use"]);
			restoreDoc("pos_settings", POS_SETTINGS, ["offline_coupon_overshoot"]);
			// a rejected sale stays in this context's queue; the context dies with the test
		}
	});
}

test("U-31 (a) a blocked pricing request is non-blocking; the next change re-prices", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	let blocked = 0;
	await page.route(/apply_friends_and_family_discount|\.apply_offers/, (r) => {
		if (blocked++ === 0) return r.abort();
		return r.continue();
	});
	await setQty(page, "UIT-A", 3);
	const errDialogs = await page.getByRole("dialog").count();
	const msg3 = await page.getByTestId("fnf-cart-messages").innerText().catch(() => "");
	await setQty(page, "UIT-A", 4);
	await expect(breakdown(page, "UIT-A")).toContainText("280.00");
	const msg4 = await page.getByTestId("fnf-cart-messages").innerText();
	record("U-31a", { errDialogs, msg3, msg4 });
	expect(errDialogs).toBe(0);
	expect(msg4).toContain("saving E£ 120.00");
	await clearCart(page);
});

/** Make the next submit_invoice reach the server but lose its response. Returns the server's answer. */
async function dropNextSubmit(page) {
	const seen = {};
	let done = false;
	await page.route("**/api/method/pos_next.api.invoices.submit_invoice", async (route) => {
		if (done) return route.continue();
		done = true;
		// Node cannot resolve *.localhost: fetch via 127.0.0.1 with the site's Host header and the page's cookies
		const req = route.request();
		const headers = { ...(await req.allHeaders()), host: new URL(req.url()).host };
		const res = await route.fetch({ url: req.url().replace(/\/\/[^/:]+/, "//127.0.0.1"), headers });
		try {
			seen.body = await res.json();
		} catch {}
		seen.request = route.request().postData();
		await route.abort("connectionreset");
	});
	return seen;
}


/** Keep the outcome unknown: no recovery lookup answers (draft re-save, docstatus read, key check). */
async function blockRecovery(page) {
	const pat = /frappe\.client\.get_value|check_offline_invoice_synced|pos_next\.api\.invoices\.update_invoice/;
	const handler = (route) => route.abort("connectionreset");
	await page.route(pat, handler);
	return () => page.unroute(pat, handler);
}

test("U-31 (b) lost response, same cart: Complete again returns the same invoice (one sale)", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A2");
	const seen = await dropNextSubmit(page);
	const { dialog, total } = await openPayment(page);
	await dialog.getByRole("button", { name: /^Exact cash/ }).click();
	// the POS may recover by itself (Ruling 149): wait for its success dialog or a settled error
	await successDialog(page).waitFor({ timeout: 30_000 }).catch(() => {});
	const first = seen.body?.message?.name;
	const screen1 = await page.locator("body").innerText();
	await shot(page, "U-31b-after-drop");
	let second = null;
	if (await successDialog(page).isVisible().catch(() => false)) {
		second = (await successDialog(page).innerText()).match(/ACC-SINV-\d+-\d+/)?.[0];
	} else {
		await closeDialogs(page);
		const p2 = await openPayment(page);
		const r2 = await payExact(page, p2.dialog);
		second = r2.name;
		await expect(successDialog(page)).toBeVisible();
	}
	await closeDialogs(page);
	const all = latestFor("UIT-Unverified");
	record("U-31b", { first, second, all: all.map((x) => x.name), key: /idempotency_key/.test(seen.request || ""), screen1: screen1.slice(-600), errors: errorsSince(since) });
	expect(first).toBeTruthy();
	expect(second).toBe(first);
	expect(all).toHaveLength(1);
	expectSaleOk(inv(first), total);
});

test("U-31 (b2) lost response, then clear and ring a new sale online: 'The last sale was saved as …'", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A2");
	const seen = await dropNextSubmit(page);
	const { dialog } = await openPayment(page);
	const unblock = await blockRecovery(page);
	await dialog.getByRole("button", { name: /^Exact cash/ }).click();
	await page.waitForTimeout(8000);
	const first = seen.body?.message?.name;
	const afterDrop = (await page.locator("body").innerText()).slice(-400);
	await closeDialogs(page);
	await unblock();
	await clearCart(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-C");
	await page.getByRole("button", { name: "Proceed to payment" }).click();
	const notice = page.getByRole("dialog").filter({ hasText: "Last sale already saved" });
	await expect(notice).toBeVisible();
	const noticeText = await notice.innerText();
	await notice.getByRole("button", { name: "Done" }).click();
	await expect(row(page, "UIT-C")).toBeVisible();
	const s2 = await sell(page);
	const all = latestFor("UIT-Unverified");
	record("U-31b2", { afterDrop, first, noticeText, second: s2.name, all: all.map((x) => x.name), errors: errorsSince(since) });
	expect(noticeText).toContain(`The last sale was saved as ${first}`);
	expect(s2.name).not.toBe(first);
	expect(all).toHaveLength(2);
});

for (const choice of ["same", "new"]) {
	test(`U-31 (b3) lost response, no answer from the server, edited cart -> "${choice}"`, async ({ page }) => {
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-A2");
		const seen = await dropNextSubmit(page);
		const { dialog } = await openPayment(page);
		const unblock = await blockRecovery(page);
		await dialog.getByRole("button", { name: /^Exact cash/ }).click();
		await page.waitForTimeout(8000);
		const first = seen.body?.message?.name;
		await closeDialogs(page);
		// the lookup keeps getting no answer; update_invoice must work again for the edited cart's re-price
		await unblock();
		await page.route(/frappe\.client\.get_value|check_offline_invoice_synced/, (r) => r.abort());
		await setQty(page, "UIT-A2", 2);
		await page.getByRole("button", { name: "Proceed to payment" }).click();
		const ask = page.getByRole("dialog").filter({ hasText: "Is this the same sale?" });
		await expect(ask).toBeVisible();
		const askText = await ask.innerText();
		let second = null;
		if (choice === "same") {
			await ask.getByRole("button", { name: "Same sale — don't charge again" }).click();
			const pay = page.getByRole("dialog").filter({ hasText: "Complete Payment" });
			if (await pay.isVisible({ timeout: 8000 }).catch(() => false)) {
				const r = await payExact(page, pay);
				second = r.name;
			}
		} else {
			await ask.getByRole("button", { name: "New sale" }).click();
			const pay = page.getByRole("dialog").filter({ hasText: "Complete Payment" });
			await expect(pay).toBeVisible();
			const r = await payExact(page, pay);
			second = r.name;
		}
		await page.waitForTimeout(2000);
		const screen = await page.locator("body").innerText();
		await closeDialogs(page);
		const all = latestFor("UIT-Unverified");
		record(`U-31b3-${choice}`, { first, askText, second, all: all.map((x) => x.name), screen: screen.slice(-500), errors: errorsSince(since) });
		if (choice === "same") {
			expect(all).toHaveLength(1);
			if (second) expect(second).toBe(first);
		} else {
			expect(all).toHaveLength(2);
			expect(second).not.toBe(first);
		}
		await clearCart(page);
	});
}

test("U-31 (c) a duplicate sync of one offline_id makes one invoice", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A2");
	let body = null;
	await page.route("**/api/method/pos_next.api.invoices.submit_invoice", async (route) => {
		body = route.request().postDataJSON();
		await route.continue();
	});
	const s = await sell(page);
	const offlineId = `pos_offline_uit3_${Date.now()}`;
	let src = body;
	if (typeof src.data === "string" && !src.invoice) src = JSON.parse(src.data);
	let inv0 = src.invoice || {};
	if (typeof inv0 === "string") inv0 = JSON.parse(inv0);
	inv0 = JSON.parse(JSON.stringify(inv0));
	delete inv0.name;
	const payload = { invoice: { ...inv0, offline_id: offlineId }, data: { offline_id: offlineId } };
	const [r1, r2] = await Promise.all([api(page, "pos_next.api.invoices.submit_invoice", payload), api(page, "pos_next.api.invoices.submit_invoice", payload)]);
	const n = server("py", { code: `result=frappe.get_all("Offline Invoice Sync",filters={"offline_id":"${offlineId}"},fields=["sales_invoice","status"])` });
	record("U-31c", { first: s.name, r1: [r1.status, r1.body.message?.name, (r1.body.exception || "").slice(0, 200)], r2: [r2.status, r2.body.message?.name, (r2.body.exception || "").slice(0, 200)], ois: n, errors: errorsSince(since) });
	expect(n.filter((x) => x.sales_invoice).length).toBe(1);
	const names = [r1.body.message?.name, r2.body.message?.name].filter(Boolean);
	expect(new Set(names).size).toBeLessThanOrEqual(1);
});

test("U-32 the offline queue survives a reload while offline, then syncs once", async ({ page, context }) => {
	await selectCustomer(page, "UIT-Walk-in");
	await addItem(page, "UIT-A2");
	await goOffline(page, context);
	await payOfflineT(page);
	let reloaded = true;
	try {
		await page.reload({ timeout: 30_000 });
		await expect(page.getByRole("textbox", { name: /Search items/ })).toBeVisible({ timeout: 60_000 });
	} catch {
		reloaded = false;
	}
	const pending = await page.locator("body").innerText().catch(() => "");
	await shot(page, "U-32-reloaded-offline");
	const during = latestFor("UIT-Walk-in").length;
	await goOnline(page, context);
	if (!reloaded) await openPos(page);
	const name = await pollServer(() => latestFor("UIT-Walk-in")[0]?.name, { timeout: 120_000, message: "U-32 sync" });
	await page.waitForTimeout(10_000);
	const all = latestFor("UIT-Walk-in");
	record("U-32", { offlineError: lastOfflineError, reloaded, during, invoice: name, count: all.length, pendingBadge: (pending.match(/[^\n]*(pending|offline)[^\n]*/i) || [""])[0], errors: errorsSince(since) });
	expect(reloaded, "the POS reloads while offline (service worker)").toBe(true);
	expect(during).toBe(0);
	expect(all).toHaveLength(1);
});

test("D-R3-02b offline: the cashier believes the error and pays the same cart again -> how many sales?", async ({ page, context }) => {
	await selectCustomer(page, "UIT-OTP3");
	await addItem(page, "UIT-A2");
	await goOffline(page, context);
	const first = await payOffline(page); // error dialog closed, cart NOT cleared
	const cartStill = await row(page, "UIT-A2").count();
	let second = null;
	if (cartStill) second = await payOffline(page);
	const cartAfter = await row(page, "UIT-A2").count();
	await goOnline(page, context);
	await pollServer(() => latestFor("UIT-OTP3")[0]?.name, { timeout: 120_000, message: "D-R3-02b sync" });
	await page.waitForTimeout(20_000);
	const all = latestFor("UIT-OTP3");
	record("D-R3-02b", { firstError: first.error, cartStill, secondError: second?.error, cartAfter, invoices: all.map((x) => x.name), errors: errorsSince(since) });
	expect(all, "one sale for one cart").toHaveLength(1);
	await clearCart(page);
});
