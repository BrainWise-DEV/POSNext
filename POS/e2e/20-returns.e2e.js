// Run 3: G2 returns (U-27b, run-2 D-R2-16, E-20..E-23) through the POS Return Invoice dialog.
// Needs POS Settings allow_return = 1 (set and restored here) and, for (c), a second payment mode
// (UIT-Card, created here and removed after).
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, applyCoupon, clearCart, closeDialogs, errorsSince, expectSaleOk,
	expectSettingsClean, inv, nowStamp, openPayment, openPos, payExact, record, restoreDoc, selectCustomer,
	sell, server, setDoc, setQty, shot, successDialog, waitIdle,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });

let since;
test.beforeAll(() => {
	setDoc("POS Settings", POS_SETTINGS, { allow_return: 1 });
});
test.afterAll(() => {
	restoreDoc("pos_settings", POS_SETTINGS, ["allow_return"]);
	expectSettingsClean();
});
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
});

/** Open Return Invoice, find the invoice, select items (all, or {code: qty}), create; returns the return name. */
async function returnFromPos(page, original, select = "all", payments = null) {
	await page.getByRole("button", { name: "Return Invoice" }).click();
	const dlg = page.getByRole("dialog").filter({ hasText: /Return/ }).last();
	await expect(dlg).toBeVisible();
	const search = dlg.getByRole("textbox").first();
	await search.fill(original);
	await page.waitForTimeout(1500);
	await dlg.getByText(original).first().click();
	await expect(dlg.getByText("Select Items to Return")).toBeVisible({ timeout: 30_000 });
	if (select === "all") {
		await dlg.getByRole("button", { name: "Select All" }).click();
	} else {
		for (const [code, qty] of Object.entries(select)) {
			const card = dlg.locator("div.cursor-pointer").filter({ hasText: code }).filter({ has: page.locator("input[type=checkbox]") }).first();
			await card.locator("input[type=checkbox]").first().check();
			await card.locator("input[type=number]").first().fill(String(qty));
			await card.locator("input[type=number]").first().blur();
		}
	}
	await page.waitForTimeout(800);
	if (payments) await payments(dlg);
	const text = await dlg.innerText();
	const done = page.waitForResponse((r) => r.url().includes("pos_next.api.invoices.submit_invoice") && r.request().method() === "POST", { timeout: 60_000 }).catch(() => null);
	await dlg.getByRole("button", { name: "Create Return" }).click();
	const res = await done;
	let body = {};
	try {
		body = res ? await res.json() : {};
	} catch {}
	await page.waitForTimeout(1500);
	const after = await page.locator("body").innerText();
	await closeDialogs(page);
	return { name: body.message?.name, status: res?.status(), dialogText: text, after, body };
}

function refundCheck(ret, orig) {
	const paidBack = -ret.payments.reduce((a, p) => a + p.amount, 0);
	return { paidBack, retDue: -(ret.si.rounded_total || ret.si.grand_total), retOutstanding: ret.si.outstanding_amount, origPaid: orig.collected };
}

test("U-27b(a) / E-20 full return of an F&F rounded sale refunds exactly what was paid", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	const s = await sell(page);
	expectSaleOk(s.invoice, 80);
	const r = await returnFromPos(page, s.name);
	expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
	const ret = inv(r.name);
	const rc = refundCheck(ret, s.invoice);
	expect(ret.si.docstatus).toBe(1);
	expect(rc.paidBack).toBeCloseTo(80, 2);
	expect(Number(ret.si.outstanding_amount)).toBeCloseTo(0, 2);
	expect(ret.usage.some((u) => u.is_return && u.amount < 0)).toBeTruthy();
	record("U-27b-a", { original: s.name, ret: r.name, rc, payments: ret.payments, usage: ret.usage, errors: errorsSince(since) });
});

test("U-27b(b) / E-22 full return of a BXGY free-row sale: free row at 0, refund = paid", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	const r = await returnFromPos(page, s.name);
	expect(r.status, JSON.stringify(r.body).slice(0, 300)).toBe(200);
	const ret = inv(r.name);
	const rc = refundCheck(ret, s.invoice);
	expect(rc.paidBack).toBeCloseTo(s.invoice.collected, 2);
	expect(Number(ret.si.outstanding_amount)).toBeCloseTo(0, 2);
	const free = ret.items.filter((i) => i.is_free_item);
	expect(free.every((i) => Number(i.rate) === 0)).toBeTruthy();
	record("U-27b-b", { original: s.name, ret: r.name, rc, items: ret.items.map((i) => [i.item_code, i.qty, i.rate, i.is_free_item]), dialog: r.dialogText.slice(0, 600), errors: errorsSince(since) });
});

test("E-21 full return of a coupon sale whose rounding went up (287.50 -> 288)", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-B");
	await applyCoupon(page, "UIT-L10");
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	const r = await returnFromPos(page, s.name);
	const ret = inv(r.name);
	const rc = refundCheck(ret, s.invoice);
	expect(rc.paidBack).toBeCloseTo(s.invoice.collected, 2);
	expect(Number(ret.si.outstanding_amount)).toBeCloseTo(0, 2);
	record("E-21", { original: s.name, ret: r.name, rc, errors: errorsSince(since) });
});

test("E-23 / U-27b 3 x UIT-ODD returned one by one: refunds add up to exactly what was paid", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-ODD");
	await setQty(page, "UIT-ODD", 3);
	const s = await sell(page);
	expectSaleOk(s.invoice, s.total);
	const rets = [];
	for (let i = 0; i < 3; i++) {
		const r = await returnFromPos(page, s.name, { "UIT-ODD": 1 });
		expect(r.status, `return ${i + 1}: ${JSON.stringify(r.body).slice(0, 300)}`).toBe(200);
		const ret = inv(r.name);
		rets.push({ name: r.name, ...refundCheck(ret, s.invoice) });
	}
	const total = rets.reduce((a, r) => a + r.paidBack, 0);
	expect(total).toBeCloseTo(s.invoice.collected, 2);
	for (const r of rets) expect(Number(r.retOutstanding)).toBeCloseTo(0, 2);
	// a fourth return is refused (nothing left)
	await page.getByRole("button", { name: "Return Invoice" }).click();
	const dlg = page.getByRole("dialog").filter({ hasText: /Return/ }).last();
	await dlg.getByRole("textbox").first().fill(s.name);
	await page.waitForTimeout(1500);
	await page.waitForTimeout(2500);
	const fourth = await dlg.innerText();
	// fully returned: the invoice is no longer offered (or says so when opened)
	expect(fourth).toMatch(/No invoices found|already been returned|No items available for return/);
	await closeDialogs(page);
	record("E-23", { original: s.name, paid: s.invoice.collected, rets, total, errors: errorsSince(since) });
});

test("U-27b(c) a sale paid across two modes, returned in three parts: never more than paid, by the chosen modes", async ({ page }) => {
	server("py", {
		code: `
if not frappe.db.exists("Mode of Payment", "UIT-Card"):
    d = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "UIT-Card", "type": "Bank",
        "accounts": [{"company": "BrainWise (Demo)", "default_account": "Bank Account - BrD"}]})
    d.insert(ignore_permissions=True)
p = frappe.get_doc("POS Profile", "UIT-FF Profile")
if not any(r.mode_of_payment == "UIT-Card" for r in p.payments):
    p.append("payments", {"mode_of_payment": "UIT-Card", "default": 0})
    p.save(ignore_permissions=True)
result = [r.mode_of_payment for r in p.payments]`,
	});
	try {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-A");
		await setQty(page, "UIT-A", 3);
		const { dialog, total } = await openPayment(page);
		// 100 by UIT-Card, the rest by Cash
		await dialog.getByRole("button", { name: "UIT-Card" }).click();
		await dialog.getByRole("button", { name: "C", exact: true }).click().catch(() => {});
		for (const k of ["1", "0", "0"]) await dialog.getByRole("button", { name: k, exact: true }).click();
		await dialog.getByRole("button", { name: "Add", exact: true }).click();
		await dialog.getByRole("button", { name: "Cash", exact: true }).click();
		await page.waitForTimeout(500);
		// the first quick amount is the remainder
		await dialog.getByRole("button", { name: /^E£ [\d,]+\.\d\d$/ }).first().click();
		await page.waitForTimeout(500);
		const paid = await payExact(page, dialog);
		expect(paid.status).toBe(200);
		await expect(successDialog(page)).toBeVisible();
		await closeDialogs(page);
		const orig = inv(paid.name);
		expectSaleOk(orig, total);
		const rets = [];
		for (let i = 0; i < 3; i++) {
			const r = await returnFromPos(page, paid.name, { "UIT-A": 1 });
			const ret = r.name ? inv(r.name) : null;
			rets.push({ name: r.name, status: r.status, payments: ret?.payments, outstanding: ret?.si.outstanding_amount, dialog: r.dialogText.slice(-700) });
			expect(r.status, `return ${i + 1}: ${JSON.stringify(r.body).slice(0, 300)}`).toBe(200);
		}
		const refunded = rets.reduce((a, r) => a - (r.payments || []).reduce((x, p) => x + p.amount, 0), 0);
		expect(refunded).toBeLessThanOrEqual(orig.collected + 0.005);
		expect(refunded).toBeCloseTo(orig.collected, 2);
		record("U-27b-c", { original: paid.name, payments: orig.payments, rets, refunded, errors: errorsSince(since) });
	} finally {
		server("py", {
			code: `
p = frappe.get_doc("POS Profile", "UIT-FF Profile")
p.set("payments", [r for r in p.payments if r.mode_of_payment != "UIT-Card"])
p.save(ignore_permissions=True)
result = [r.mode_of_payment for r in p.payments]`,
		});
	}
});
