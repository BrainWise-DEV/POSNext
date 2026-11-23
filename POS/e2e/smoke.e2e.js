// Plan section 6 smoke (12 paths), rewritten for run 3 so it passes against pos-dev, with server checks.
// docs/superpowers/plans/2026-11-18-ui-test-plan-ff-coupons-offers.md
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
	AUTH, ARTIFACTS, MAILPIT, addItem, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince,
	expectSaleOk, expectSettingsClean, ffReset, ffSet, freeRows, inv, nowStamp, openPayment, openPos, payExact,
	pollServer, record, restoreDoc, row, selectCustomer, sell, server, setDoc, setQty, shot, successDialog,
	waitIdle, payOffline,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });

let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

async function fresh(page) {
	await openPos(page);
	await clearCart(page);
}

// ---- 1. U-01 OTP -----------------------------------------------------------------------
test("U-01 OTP: Frappe Email verify of UIT-OTP1", async ({ page, request }) => {
	const email = "uit-otp1@uit-ff.example";
	// re-runnable: put UIT-OTP1 back to unverified with its seeded address
	server("py", {
		code: `frappe.db.set_value("Customer", "UIT-OTP1", {"email_id": "${email}", "custom_email_verified": 0, "custom_verified_email": None}, update_modified=False)\nresult=1`,
	});
	const mails = async () => {
		const res = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${email}"` } });
		return (await res.json()).messages || [];
	};
	const before = new Set((await mails()).map((m) => m.ID));
	await fresh(page);
	await selectCustomer(page, "UIT-OTP1");
	await page.getByRole("button", { name: "Edit customer details" }).click();
	await page.getByTestId("send-code").click();
	await expect(page.getByTestId("otp-input")).toBeVisible();
	await expect(page.getByTestId("countdown")).toContainText("Code expires in");
	let code = "";
	await expect
		.poll(
			async () => {
				const m = (await mails()).find((x) => !before.has(x.ID));
				if (!m) return "";
				const msg = await (await request.get(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
				code = (msg.Text || msg.HTML || "").match(/\b\d{6}\b/)?.[0] || "";
				return code;
			},
			{ timeout: 60_000 },
		)
		.toMatch(/^\d{6}$/);
	await page.getByTestId("otp-input").fill(code);
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("verified-badge")).toContainText("Email verified");
	const c = server("get", { doctype: "Customer", name: "UIT-OTP1", fields: ["custom_email_verified", "custom_verified_email", "custom_email_verified_via"] });
	const comments = server("py", { code: `result=[c.content[:200] for c in frappe.get_all("Comment",filters={"reference_name":"UIT-OTP1","creation":[">=","${since}"]},fields=["content"])]` });
	const logs = server("py", { code: `result=frappe.get_all("Friends and Family Log",filters={"customer":"UIT-OTP1","creation":[">=","${since}"]},fields=["log_type","message","details"])` });
	record("U-01", { customer: c, comments, logs, mails: (await mails()).length - before.size, errors: errorsSince(since) });
	expect(c.custom_email_verified).toBe(1);
	expect(c.custom_verified_email).toBe(email);
	expect(c.custom_email_verified_via).toBe("frappe_email");
	expect(comments.join(" ")).not.toContain(code);
	expect(logs.some((l) => l.log_type === "Eligibility Applied")).toBeTruthy();
	await closeDialogs(page);
});

// ---- 2. U-06 badge + reload ------------------------------------------------------------
test("U-06 F&F badge and line survive a reload", async ({ page }) => {
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	const check = async () => {
		await expect(page.getByTestId("fnf-customer-badge")).toHaveText("F&F 30%");
		await expect(page.getByTestId("fnf-cart-messages")).toContainText(/Friends & Family 30% applied to 1 item\(s\) — saving E£ 30\.00/);
		await expect(breakdown(page, "UIT-A")).toContainText("100.00");
		await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	};
	await check();
	await page.reload();
	await openPos(page);
	await check();
	await shot(page, "U-06-after-reload");
	const elig = await page.evaluate(async () => {
		const r = await fetch("/api/method/posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility", {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.csrf_token },
			body: JSON.stringify({ customer: "UIT-Verified", pos_profile: "UIT-FF Profile" }),
		});
		return (await r.json()).message;
	});
	record("U-06", { elig });
	expect(elig.eligible).toBe(true);
	expect(elig.reason).toBe("email_verified");
	await clearCart(page);
});

// ---- 3. U-09 F&F submit + INV-1 --------------------------------------------------------
test("U-09 F&F sale submits at the cart total", async ({ page }) => {
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	const s = await sell(page);
	record("U-09", { invoice: s.name, total: s.total, rows: s.invoice.items, usage: s.invoice.usage, logs: s.invoice.logs, errors: errorsSince(since) });
	expectSaleOk(s.invoice, s.total);
	const r = s.invoice.items[0];
	expect(Number(r.rate)).toBe(70);
	expect(r.posnext_discount_source).toBe("friends_and_family");
	expect(Number(r.posnext_fnf_discount_amount)).toBe(30);
	expect(s.invoice.usage).toHaveLength(1);
	expect(s.invoice.usage[0].amount).toBe(30);
	expect(s.invoice.logs.some((l) => l.log_type === "Discount Applied")).toBeTruthy();
});

// ---- 4. U-15 (a) line coupon, hold, resume, pay ----------------------------------------
test("U-15a line coupon on a held draft, then paid", async ({ page }) => {
	const before = coupons()["UIT-L10"];
	await fresh(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-B");
	const msg = await applyCoupon(page, "UIT-L10", { close: false });
	expect(msg).toContain("UIT-L10 applied successfully");
	await closeDialogs(page);
	await expect(breakdown(page, "UIT-A")).toContainText("90.00");
	await expect(row(page, "UIT-B")).not.toContainText("UIT-L10");
	await page.getByRole("button", { name: "Hold", exact: true }).click();
	await expect(page.getByText("Your cart is empty")).toBeVisible();
	expect(coupons()["UIT-L10"]).toBe(before);
	await page.getByRole("button", { name: /Draft Invoices/ }).click();
	const drafts = page.getByRole("dialog").filter({ hasText: "Draft" });
	await drafts.getByText("UIT-Unverified").first().click();
	await waitIdle(page);
	await closeDialogs(page);
	await expect(row(page, "UIT-A")).toBeVisible();
	await expect(breakdown(page, "UIT-A")).toContainText("90.00");
	const s = await sell(page);
	record("U-15a", { invoice: s.name, total: s.total, rows: s.invoice.items, used: [before, coupons()["UIT-L10"]], errors: errorsSince(since) });
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.si.coupon_code).toBe("UIT-L10");
	expect(s.invoice.items.find((i) => i.item_code === "UIT-A").posnext_coupon_code).toBe("UIT-L10");
	expect(s.invoice.items.find((i) => i.item_code === "UIT-B").posnext_coupon_code || "").toBe("");
	expect(coupons()["UIT-L10"]).toBe(before + 1);
});

// ---- 5. U-18 (b) CVF-03 + reload --------------------------------------------------------
test("U-18b a 50% line coupon wins over F&F and survives a reload", async ({ page }) => {
	const before = coupons()["UIT-L50"];
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L50");
	const check = async () => {
		await expect(breakdown(page, "UIT-A")).toContainText("50.00");
		await expect(page.getByTestId("fnf-customer-badge")).toHaveAttribute("title", /Coupon UIT-L50 applied instead of Friends & Family/);
		await expect(page.getByTestId("fnf-cart-messages")).toContainText("discounts are never combined");
	};
	await check();
	await page.reload();
	await openPos(page);
	await check();
	const s = await sell(page);
	record("U-18b", { invoice: s.name, rows: s.invoice.items, usage: s.invoice.usage, errors: errorsSince(since) });
	expectSaleOk(s.invoice, s.total);
	expect(s.invoice.items[0].posnext_coupon_code).toBe("UIT-L50");
	expect(s.invoice.items[0].posnext_discount_source || "").not.toBe("friends_and_family");
	expect(s.invoice.usage).toHaveLength(0);
	expect(coupons()["UIT-L50"]).toBe(before + 1);
});

// ---- 6. U-21b BXGY 1 -> 2 -> 1 ----------------------------------------------------------
test("U-21b BXGY 1 -> 2 -> 1 brings F&F back before payment opens", async ({ page }) => {
	const pricing = [];
	page.on("request", (r) => {
		if (r.method() === "POST" && /apply_friends_and_family_discount|\.apply_offers/.test(r.url())) pricing.push(r.postData() || "");
	});
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-BXGY");
	await expect(breakdown(page, "UIT-BXGY")).toContainText("42.00");
	await setQty(page, "UIT-BXGY", 2);
	await expect(row(page, "UIT-BXGY").getByTestId("fnf-line-note")).toContainText("Promotion item — not eligible for Friends & Family");
	await expect(row(page, "UIT-BXGY")).toContainText("120.00");
	await expect(freeRows(page)).toHaveCount(1);
	pricing.length = 0;
	await setQty(page, "UIT-BXGY", 1);
	await expect(freeRows(page)).toHaveCount(0);
	await expect(row(page, "UIT-BXGY").getByTestId("fnf-line-note")).toHaveCount(0);
	await expect(breakdown(page, "UIT-BXGY")).toContainText("42.00");
	expect(pricing.length).toBeGreaterThan(0);
	expect(pricing.at(-1)).not.toContain("UIT-PR-BXGY");
	const { dialog, total } = await openPayment(page);
	await expect(page.getByText("Invoice Total Changed")).toHaveCount(0);
	const paid = await payExact(page, dialog);
	expect(paid.request).not.toContain("UIT-PR-BXGY");
	await expect(successDialog(page)).toBeVisible();
	await closeDialogs(page);
	const d = inv(paid.name);
	record("U-21b", { invoice: paid.name, total, rows: d.items, usage: d.usage, errors: errorsSince(since) });
	expectSaleOk(d, total);
	expect(d.items).toHaveLength(1);
	expect(Number(d.items[0].rate)).toBe(42);
	expect(d.items[0].posnext_discount_source).toBe("friends_and_family");
	expect(d.items[0].pricing_rules || "").toBe("");
	expect(d.usage[0].amount).toBe(18);
});

// ---- 7. U-23 (a) BXGY free row, reload ---------------------------------------------------
test("U-23a BXGY x2 for a plain customer gives a free row that survives a reload", async ({ page }) => {
	await fresh(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	const check = async () => {
		await expect(row(page, "UIT-BXGY")).toContainText("120.00");
		await expect(freeRows(page)).toHaveCount(1);
		await expect(row(page, "UIT-BXGY")).toHaveCount(1);
	};
	await check();
	await page.reload();
	await openPos(page);
	await check();
	const s = await sell(page);
	record("U-23a", { invoice: s.name, rows: s.invoice.items, errors: errorsSince(since) });
	expectSaleOk(s.invoice, s.total);
	const free = s.invoice.items.filter((i) => i.is_free_item);
	expect(free).toHaveLength(1);
	expect(free[0].pricing_rules).toContain("UIT-PR-BXGY");
	expect(Number(free[0].rate)).toBe(0);
});

// ---- 8. U-25 stale offer ------------------------------------------------------------------
test("U-25 a stale free-item offer is refused, then sells after a refresh", async ({ page }) => {
	await fresh(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-TRIG");
	await expect(freeRows(page)).toHaveCount(1);
	setDoc("Pricing Rule", "UIT-PR-FREE", { disable: 1 });
	try {
		await page.getByRole("button", { name: "Proceed to payment" }).click();
		await page.waitForTimeout(3000);
		let refusal = await page.locator("body").innerText();
		if (!/not backed by an offer/.test(refusal)) {
			const dlg = page.getByRole("dialog").filter({ hasText: "Complete Payment" });
			if (await dlg.isVisible().catch(() => false)) {
				await dlg.getByRole("button", { name: /^Exact cash/ }).click();
				await page.waitForTimeout(3000);
				refusal = await page.locator("body").innerText();
			}
		}
		await shot(page, "U-25-refusal");
		const m = refusal.match(/[^\n]*not backed by an offer[^\n]*/);
		const header = page.getByRole("button", { name: "Refresh items and customers" });
		await closeDialogs(page);
		// D-R2-09: the header Refresh should drop the stale gift
		await header.click();
		await waitIdle(page, 3000);
		const afterRefresh = await freeRows(page).count();
		if (afterRefresh) {
			await page.reload();
			await openPos(page);
		}
		await expect(freeRows(page)).toHaveCount(0);
		const s = await sell(page);
		record("U-25", { refusal: m?.[0], offersChanged: /offers changed/i.test(refusal), giftAfterHeaderRefresh: afterRefresh, invoice: s.name, rows: s.invoice.items, errors: errorsSince(since) });
		expect(m?.[0]).toMatch(/Row \d+: free item UIT-GIFT is not backed by an offer \(free qty 0 expected, 1(\.0)? sent\)/);
		expectSaleOk(s.invoice, s.total);
		expect(s.invoice.items.filter((i) => i.is_free_item)).toHaveLength(0);
		expect.soft(afterRefresh, "header Refresh drops the stale gift (D-R2-09)").toBe(0);
	} finally {
		restoreDoc("rules", "UIT-PR-FREE", ["disable"]);
	}
});

// ---- 9. U-29 (a) offline sale without F&F ------------------------------------------------
test("U-29a a sale made offline has no F&F badge and syncs without an error", async ({ page, context }) => {
	await fresh(page);
	await expect(page.getByRole("button", { name: "Cache ready" })).toBeVisible({ timeout: 120_000 });
	await context.setOffline(true);
	await expect(page.getByRole("button", { name: /Offline mode/ })).toBeVisible({ timeout: 30_000 });
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
	const off = await payOffline(page);
	if (off.error) await clearCart(page);
	await context.setOffline(false);
	const name = await pollServer(() => server("latest", { customer: "UIT-Verified", since, n: 1 })[0]?.name, { timeout: 120_000, message: "offline sale synced" });
	await page.waitForTimeout(3000);
	const errorDialogs = await page.getByRole("dialog").filter({ hasText: /Error|Failed/ }).count();
	const d = inv(name);
	record("U-29a", { offlineError: off.error, invoice: name, rows: d.items, logs: d.logs, ois: d.offline_sync, errorDialogs, errors: errorsSince(since) });
	expect(errorDialogs).toBe(0);
	expect.soft(off.error, "offline checkout shows no error (D-R3-02)").toBeNull();
	expect(d.si.docstatus).toBe(1);
	expect(Number(d.items[0].rate)).toBe(100);
	expect(d.logs.some((l) => l.log_type === "Offline Disagreement" && l.reason === "missing_fnf")).toBeTruthy();
	expect(d.offline_sync.length).toBe(1);
});

// ---- 10. U-33 (a) receipt HTML artifact ---------------------------------------------------
test("U-33a POS receipt names the F&F discount and marks the free row", async ({ page, context }) => {
	await context.addInitScript(() => {
		const open = window.open.bind(window);
		window.open = (url, ...rest) => (typeof url === "string" && url.includes("/printview") ? null : open(url, ...rest));
	});
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await expect(freeRows(page)).toHaveCount(1);
	const { dialog } = await openPayment(page);
	const paid = await payExact(page, dialog);
	await expect(successDialog(page)).toBeVisible();
	const popup = context.waitForEvent("page", { timeout: 20_000 }).catch(() => null);
	await successDialog(page).getByRole("button", { name: "Print Invoice" }).click();
	const receipt = await popup;
	let html = "";
	if (receipt) {
		await receipt.waitForLoadState("domcontentloaded");
		html = await receipt.content();
	} else {
		html = await page.evaluate(() => Array.from(document.querySelectorAll("iframe")).map((f) => f.contentDocument?.documentElement?.outerHTML || "").join("\n"));
	}
	fs.writeFileSync(path.join(ARTIFACTS, `U-33a-${paid.name}.html`), html);
	await closeDialogs(page);
	const hasFnf = /Friends (&amp;|&) Family discount/.test(html);
	record("U-33a", { invoice: paid.name, size: html.length, popup: !!receipt, hasFnf, hasFree: html.includes("(FREE)") });
	expect(hasFnf).toBe(true);
	expect(html).toContain("(FREE)");
});

// ---- 11. U-35 RTL screenshots --------------------------------------------------------------
test("U-35 Arabic layout: badge, line note, Coupon dialog and payment dialog", async ({ page }) => {
	const shotP = (n) => path.join(ARTIFACTS, `U-35-${n}.png`);
	const clipped = async (loc) => loc.evaluate((el) => el.scrollWidth > el.clientWidth + 1);
	await fresh(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await expect(page.getByTestId("fnf-line-note")).toBeVisible();
	const res = {};
	try {
		await page.getByRole("button", { name: /English/ }).first().click();
		await page.getByRole("menuitem", { name: /العربية|Arabic/ }).or(page.getByRole("button", { name: /العربية|Arabic/ })).first().click();
		await expect(page.locator("html")).toHaveAttribute("dir", "rtl", { timeout: 30_000 });
		await waitIdle(page, 2000);
		const badge = page.getByTestId("fnf-customer-badge");
		await badge.screenshot({ path: shotP("badge") });
		res.badgeClipped = await clipped(badge);
		const note = page.getByTestId("fnf-line-note").first();
		await note.screenshot({ path: shotP("line-note") });
		res.noteClipped = await clipped(note);
		res.noteText = await note.innerText();
		await page.getByRole("button", { name: "تطبيق رمز الكوبون" }).or(page.getByRole("button", { name: /coupon/i })).first().click();
		const coupon = page.getByRole("dialog").last();
		await expect(coupon).toBeVisible();
		await coupon.screenshot({ path: shotP("coupon-dialog") });
		await page.keyboard.press("Escape");
		await page.waitForTimeout(500);
		await closeDialogs(page);
		await page.getByRole("button", { name: /المتابعة للدفع|Proceed to payment/ }).first().click();
		const payment = page.getByRole("dialog").last();
		await expect(payment).toBeVisible();
		await payment.screenshot({ path: shotP("payment-dialog") });
		res.scroll = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
		await closeDialogs(page);
	} finally {
		await page.keyboard.press("Escape");
		const lang = page.getByRole("button", { name: /العربية|Arabic/ }).first();
		if (await lang.isVisible().catch(() => false)) {
			await lang.click();
			await page.getByRole("menuitem", { name: /English|الإنجليزية/ }).or(page.getByRole("button", { name: /^English|الإنجليزية/ })).first().click();
			await expect(page.locator("html")).not.toHaveAttribute("dir", "rtl", { timeout: 30_000 });
		}
		await clearCart(page);
	}
	record("U-35", res);
	expect(res.badgeClipped).toBe(false);
	expect(res.noteClipped).toBe(false);
	expect(res.scroll).toBeLessThanOrEqual(0);
});

// ---- 12. U-38 (a) two-context race ---------------------------------------------------------
test("U-38a two cashiers submit the same capped F&F cart, both succeed (Allow and log)", async ({ browser }) => {
	const used = server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });
	ffSet({ max_discount_per_customer_month: used + 40 });
	const ctxA = await browser.newContext({ storageState: AUTH.cashier });
	const ctxB = await browser.newContext({ storageState: AUTH.cashier2 });
	try {
		const a = await ctxA.newPage();
		const b = await ctxB.newPage();
		const prepare = async (p) => {
			await fresh(p);
			await selectCustomer(p, "UIT-Cap");
			await addItem(p, "UIT-A");
			await setQty(p, "UIT-A", 2);
			await expect(breakdown(p, "UIT-A")).toContainText("160.00");
			return openPayment(p);
		};
		const pa = await prepare(a);
		const pb = await prepare(b);
		const ra = await payExact(a, pa.dialog);
		const rb = await payExact(b, pb.dialog);
		const after = server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });
		const da = inv(ra.name);
		const db = inv(rb.name);
		record("U-38a", { a: ra.name, b: rb.name, used, after, logsB: db.logs, errors: errorsSince(since) });
		expect(ra.status).toBe(200);
		expect(rb.status).toBe(200);
		expectSaleOk(da);
		expectSaleOk(db);
		expect(after).toBeCloseTo(used + 80, 2);
	} finally {
		ffReset();
		await ctxA.close();
		await ctxB.close();
	}
});
