// F&F × promotions × coupons edge cases (run 3), each a real sale with server checks.
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince,
	expectSaleOk, expectSettingsClean, ffReset, ffSet, freeRows, inv, nowStamp, openPayment, openPos, record,
	restoreDoc, row, selectCustomer, sell, server, setDoc, setQty, shot, waitIdle, withCoupon, withFf, withPos,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
});
test.afterEach(() => expectSettingsClean());

const rowsOf = (inv) => inv.items.map((i) => [i.item_code, i.qty, i.rate, i.is_free_item, i.posnext_discount_source, i.posnext_coupon_code, i.posnext_coupon_share, i.pricing_rules]);
const item = (inv, code, free = 0) => inv.items.find((i) => i.item_code === code && i.is_free_item === free);
const usage = (inv) => inv.usage.reduce((a, u) => a + u.amount, 0);

test("E-P100 a 100% price rule beats F&F: free row, no USG", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-P100");
	await addItem(page, "UIT-A");
	const s = await sell(page);
	record("E-P100", { invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice) });
	expectSaleOk(s.invoice, s.total);
	expect(item(s.invoice, "UIT-P100", 1)).toBeTruthy();
	expect(usage(s.invoice)).toBeCloseTo(30, 2);
});

test("E-06 coupon + offer + F&F + free rows on one cart, customer Verified -> Unverified -> Walk-in -> Verified, then F5", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	for (const c of ["UIT-A", "UIT-C", "UIT-EXCL", "UIT-P100", "UIT-TRIG"]) await addItem(page, c);
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await applyCoupon(page, "UIT-L20");
	const snap = async () => (await page.locator("[data-line-key]").allInnerTexts()).map((t) => t.replace(/\s+/g, " ")).join(" || ") + ` || free=${await freeRows(page).count()}`;
	const first = await snap();
	await selectCustomer(page, "UIT-Unverified");
	const plain = await snap();
	const couponAfterChange = await page.getByRole("button", { name: /Remove coupon/ }).count();
	await selectCustomer(page, "UIT-Walk-in");
	await selectCustomer(page, "UIT-Verified");
	const back = await snap();
	await page.reload();
	await openPos(page);
	const afterF5 = await snap();
	const s = await sell(page);
	record("E-06", { first, plain, couponAfterChange, back, afterF5, invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice), changed: s.changed, errors: errorsSince(since) });
	expectSaleOk(s.invoice, s.total);
	expect(couponAfterChange, "coupon dropped on customer change (D-16)").toBe(0);
	expect(back).toBe(afterF5);
	expect(item(s.invoice, "UIT-A").posnext_discount_source).toBe("friends_and_family");
	expect(Number(item(s.invoice, "UIT-C").rate)).toBe(30);
	expect(item(s.invoice, "UIT-P100", 1)).toBeTruthy();
	expect(item(s.invoice, "UIT-BXGY", 1)).toBeTruthy();
	expect(s.changed).toBeNull();
});

test("E-08 per-order cap 90 split across lines (UIT-A + UIT-B + UIT-ODD)", async ({ page }) => {
	await withFf({ max_discount_per_order: 90 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		for (const c of ["UIT-A", "UIT-B", "UIT-ODD"]) await addItem(page, c);
		const msgs = await page.getByTestId("fnf-cart-messages").innerText();
		const s = await sell(page);
		const f = s.invoice.items.reduce((a, i) => a + i.posnext_fnf_discount_amount, 0);
		record("E-08", { invoice: s.name, rows: rowsOf(s.invoice), fnf: f, usage: usage(s.invoice), msgs, logs: s.invoice.logs.map((l) => l.log_type) });
		expectSaleOk(s.invoice, s.total);
		expect(f).toBeLessThanOrEqual(90);
		expect(f).toBeGreaterThanOrEqual(89.97);
		expect(usage(s.invoice)).toBeCloseTo(f, 2);
	});
});

test("E-09 per-order cap 50 with a competing 20% rule (UIT-A + UIT-B)", async ({ page }) => {
	await withFf({ max_discount_per_order: 50 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-A");
		await addItem(page, "UIT-B");
		const s = await sell(page);
		record("E-09", { invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice), logs: s.invoice.logs.map((l) => `${l.log_type}/${l.reason}`), changed: s.changed });
		expectSaleOk(s.invoice, s.total);
		expect(usage(s.invoice)).toBeLessThanOrEqual(50);
		expect.soft(s.invoice.logs.some((l) => l.log_type === "Cap Hit"), "Cap Hit log when F&F is dropped by the cap (D-R2-02)").toBeTruthy();
	});
});

test("E-09b monthly cap split across lines (cap = used + 50, UIT-A + UIT-B)", async ({ page }) => {
	const used = server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });
	await withFf({ max_discount_per_customer_month: used + 50 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Cap");
		await addItem(page, "UIT-A");
		await addItem(page, "UIT-B");
		const msgs = await page.getByTestId("fnf-cart-messages").innerText();
		const s = await sell(page);
		record("E-09b", { invoice: s.name, used, rows: rowsOf(s.invoice), usage: usage(s.invoice), msgs, changed: s.changed });
		expectSaleOk(s.invoice, s.total);
		expect(usage(s.invoice)).toBeLessThanOrEqual(50.001);
		expect(usage(s.invoice)).toBeGreaterThan(29.99);
	});
});

test("E-AOT B20 + UIT-L10 Add on top: 200 -> 160 -> 144, share 16", async ({ page }) => {
	await withCoupon("UIT-L10", { promotion_conflict: "Add on top" }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Unverified");
		await addItem(page, "UIT-B");
		await applyCoupon(page, "UIT-L10");
		const line = await row(page, "UIT-B").innerText();
		const s = await sell(page);
		const b = item(s.invoice, "UIT-B");
		record("E-AOT-B20", { invoice: s.name, row: b, line: line.replace(/\s+/g, " ") });
		expectSaleOk(s.invoice, s.total);
		expect(Number(b.rate)).toBeCloseTo(144, 2);
		expect(Number(b.posnext_coupon_share)).toBeCloseTo(16, 2);
	});
});

test("E-AOT-FF Add on top on an F&F customer: F&F line vs promoted line", async ({ page }) => {
	await withCoupon("UIT-L10", { promotion_conflict: "Add on top" }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-C");
		await addItem(page, "UIT-A");
		const msg = await applyCoupon(page, "UIT-L10");
		const lines = (await page.locator("[data-line-key]").allInnerTexts()).map((t) => t.replace(/\s+/g, " "));
		const s = await sell(page);
		record("E-AOT-FF", { invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice), lines, msg: (msg.match(/[^\n]*(better|applied|never)[^\n]*/g) || []).slice(0, 4), changed: s.changed });
		expectSaleOk(s.invoice, s.total);
		expect(s.changed).toBeNull();
		// no line carries F&F and a coupon at once
		expect(s.invoice.items.every((i) => !(i.posnext_discount_source === "friends_and_family" && i.posnext_coupon_code))).toBeTruthy();
	});
});

test("E-HOLD hold and resume an F&F + BXGY free-row cart", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	const before = (await page.locator("[data-line-key]").allInnerTexts()).join("|").replace(/\s+/g, " ");
	await page.getByRole("button", { name: "Hold", exact: true }).click();
	await expect(page.getByText("Your cart is empty")).toBeVisible();
	await page.getByRole("button", { name: /Draft Invoices/ }).click();
	await page.getByRole("dialog").filter({ hasText: "Draft" }).getByText("UIT-Verified").first().click();
	await waitIdle(page, 2000);
	await closeDialogs(page);
	const after = (await page.locator("[data-line-key]").allInnerTexts()).join("|").replace(/\s+/g, " ");
	const free = await freeRows(page).count();
	const s = await sell(page);
	record("E-HOLD", { before, after, free, invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice), changed: s.changed });
	expectSaleOk(s.invoice, s.total);
	expect(free).toBe(1);
	expect(after).toBe(before);
	expect(usage(s.invoice)).toBeCloseTo(30, 2);
});

test("E-UOM a second UOM (Box = 6) on UIT-A: F&F on the box price", async ({ page }) => {
	server("py", {
		code: `
if not frappe.db.exists("UOM", "UIT-Box"):
    frappe.get_doc({"doctype": "UOM", "uom_name": "UIT-Box"}).insert(ignore_permissions=True)
it = frappe.get_doc("Item", "UIT-A")
if not any(u.uom == "UIT-Box" for u in it.uoms):
    it.append("uoms", {"uom": "UIT-Box", "conversion_factor": 6})
    it.save(ignore_permissions=True)
result = [(u.uom, u.conversion_factor) for u in it.uoms]`,
	});
	try {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		// with two UOMs, adding the item opens "Select Unit of Measure"
		await page.getByRole("textbox", { name: /Search items/ }).fill("UIT-A");
		await page.getByRole("button", { name: "UIT-A", exact: true }).first().click();
		let switched = false;
		if (await page.getByText("Select Unit of Measure").isVisible({ timeout: 8000 }).catch(() => false)) {
			await page.getByText("UIT-Box", { exact: true }).click();
			await page.getByText("Confirm", { exact: true }).click();
			switched = true;
		}
		await page.getByRole("textbox", { name: /Search items/ }).fill("");
		await waitIdle(page, 2000);
		const line = (await row(page, "UIT-A").innerText().catch(() => "")).replace(/\s+/g, " ");
		const s = await sell(page);
		const a = s.invoice.items[0];
		record("E-UOM", { switched, line, invoice: s.name, row: a, usage: usage(s.invoice), changed: s.changed });
		expectSaleOk(s.invoice, s.total);
		expect(switched, "UOM selectable in the edit dialog").toBe(true);
		expect(a.uom).toBe("UIT-Box");
		expect(Number(a.rate)).toBeCloseTo(420, 2);
		expect(usage(s.invoice)).toBeCloseTo(180, 2);
	} finally {
		server("py", {
			code: `
it = frappe.get_doc("Item", "UIT-A")
it.set("uoms", [u for u in it.uoms if u.uom != "UIT-Box"])
it.save(ignore_permissions=True)
result = [(u.uom, u.conversion_factor) for u in it.uoms]`,
		});
	}
});

test("E-RET-MIX return of a coupon + F&F invoice (U-19 shape), then a partial F&F return", async ({ page }) => {
	await withPos({ allow_return: 1 }, async () => {
		await page.reload();
		await openPos(page);
		await selectCustomer(page, "UIT-Verified");
		await addItem(page, "UIT-EXCL");
		await addItem(page, "UIT-A");
		await setQty(page, "UIT-A", 2);
		await applyCoupon(page, "UIT-L20");
		const s = await sell(page);
		expectSaleOk(s.invoice, s.total);
		const doReturn = async (sel) => {
			await page.getByRole("button", { name: "Return Invoice" }).click();
			const dlg = page.getByRole("dialog").filter({ hasText: /Return/ }).last();
			await dlg.getByRole("textbox").first().fill(s.name);
			await page.waitForTimeout(1500);
			await dlg.getByText(s.name).first().click();
			await expect(dlg.getByText("Select Items to Return")).toBeVisible({ timeout: 30_000 });
			for (const [code, qty] of Object.entries(sel)) {
				const card = dlg.locator("div.cursor-pointer").filter({ hasText: code }).filter({ has: page.locator("input[type=checkbox]") }).first();
				await card.locator("input[type=checkbox]").first().check();
				await card.locator("input[type=number]").first().fill(String(qty));
				await card.locator("input[type=number]").first().blur();
			}
			await page.waitForTimeout(800);
			const done = page.waitForResponse((r) => r.url().includes("submit_invoice") && r.request().method() === "POST", { timeout: 60_000 });
			await dlg.getByRole("button", { name: "Create Return" }).click();
			const body = await (await done).json();
			await page.waitForTimeout(1200);
			await closeDialogs(page);
			return inv(body.message.name);
		};
		const r1 = await doReturn({ "UIT-A": 1 });
		const r2 = await doReturn({ "UIT-A": 1, "UIT-EXCL": 1 });
		const paidBack = [r1, r2].map((r) => -r.payments.reduce((a, p) => a + p.amount, 0));
		record("E-RET-MIX", { original: s.name, paid: s.invoice.collected, r1: [r1.si.name, rowsOf(r1), r1.usage], r2: [r2.si.name, rowsOf(r2), r2.usage], paidBack, couponUsed: coupons()["UIT-L20"] });
		expect(paidBack[0] + paidBack[1]).toBeCloseTo(s.invoice.collected, 2);
		expect(r1.usage.reduce((a, u) => a + u.amount, 0)).toBeCloseTo(-30, 2);
		expect(r2.si.outstanding_amount).toBeCloseTo(0, 2);
	});
});

test("E-DESK Desk submit of a held POS F&F draft", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	// Held carts live in the browser; the server draft is the one Checkout saves (the 8o check)
	await openPayment(page);
	await closeDialogs(page);
	const draft = server("py", { code: `result=frappe.get_all("Sales Invoice",filters={"customer":"UIT-Verified","docstatus":0,"creation":[">=","${since}"]},pluck="name",order_by="creation desc",limit=1)` })[0];
	const out = server("py", {
		code: `
d = frappe.get_doc("Sales Invoice", "${draft}")
d.set("payments", [])
d.append("payments", {"mode_of_payment": "Cash", "account": "Cash - BrD", "amount": d.rounded_total or d.grand_total})
d.paid_amount = d.rounded_total or d.grand_total
d.submit()
result = d.name`,
	});
	const d = inv(out);
	record("E-DESK", { draft, invoice: out, rows: rowsOf(d), usage: usage(d), logs: d.logs.map((l) => l.log_type), status: d.si.status });
	expect(d.si.docstatus).toBe(1);
	expect(Number(d.items[0].rate)).toBe(70);
	expect(usage(d)).toBeCloseTo(30, 2);
	// the held draft is still listed in the POS? (it is submitted now)
	await clearCart(page);
});

test("E-ZERO an F&F cart that a 100% coupon makes zero", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L100");
	const s = await sell(page);
	record("E-ZERO", { invoice: s.name, rows: rowsOf(s.invoice), usage: usage(s.invoice), due: s.invoice.due });
	expectSaleOk(s.invoice, 0);
	expect(usage(s.invoice)).toBe(0);
});

test("E-ODD-ROUND F&F on UIT-ODD x7 with rounding (no cap)", async ({ page }) => {
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-ODD");
	await setQty(page, "UIT-ODD", 7);
	const s = await sell(page);
	record("E-ODD", { invoice: s.name, si: s.invoice.si, rows: rowsOf(s.invoice), usage: usage(s.invoice) });
	expectSaleOk(s.invoice, s.total);
	expect(usage(s.invoice)).toBeCloseTo(s.invoice.items[0].posnext_fnf_discount_amount, 2);
});
