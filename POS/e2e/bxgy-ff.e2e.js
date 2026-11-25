// Buy X Get Y × F&F × "Allow Free Gift with F&F" (allow_free_gift_with_ff), in the browser, with
// server checks on every sale. Run only this group:  cd POS && e2e/run.sh bxgy-ff
// (a) same-item BXGY UIT-PR-BXGY (buy 2 get 1), qty 1 -> 2 -> 4 -> 1, checkbox OFF / ON
// (b) Item Level Discount rule (UIT-PR-B20 set to promotion_type Item Level Discount), OFF / ON
// (c) Price "buy one" rule UIT-PR-BUY1 (created here, deleted after): must behave like (a). Rule shape as
//     specified (Price, 100%, apply_discount_on_price Max, min_or_max_discount_qty_limit 1, on UIT-A) plus
//     min_qty 2 so that qty 1 is below the offer, as BXGY is.
//     Marked test.fail() until the promotions port is deployed ("pending port, Price buy-one = BXGY").
import { expect, test } from "@playwright/test";
import {
	AUTH, addItem, breakdown, clearCart, errorsSince, expectSaleOk, expectSettingsClean, ffReset, ffSet,
	freeRows, lastTotalChanged, nowStamp, openPos, record, row, selectCustomer, sell, server, setQty, shot, withRule,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });

const PRICING = /apply_friends_and_family_discount|\.apply_offers/;
let since;

/** Run body with the checkbox at `allow`, then always reset_ff (restores it). */
async function withCheckbox(page, allow, body) {
	ffSet({ allow_free_gift_with_ff: allow });
	try {
		await openPos(page);
		await clearCart(page);
		await selectCustomer(page, "UIT-Verified");
		return await body();
	} finally {
		ffReset();
	}
}

const paidRows = (inv, code) => inv.items.filter((i) => i.item_code === code && !i.is_free_item);
const freeOf = (inv) => inv.items.filter((i) => i.is_free_item);

test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

for (const allow of [0, 1]) {
	test(`(a) BXGY x F&F, checkbox ${allow ? "ON" : "OFF"}: qty 1 -> 2 -> 4 -> 1, F&F back at 1 with no stale tag`, async ({ page }) => {
		const bodies = [];
		page.on("request", (r) => {
			if (r.method() === "POST" && PRICING.test(r.url())) bodies.push(r.postData() || "");
		});
		await withCheckbox(page, allow, async () => {
			const steps = {};
			await addItem(page, "UIT-BXGY");
			await expect(breakdown(page, "UIT-BXGY")).toContainText("42.00");
			steps.q1 = await row(page, "UIT-BXGY").innerText();

			await setQty(page, "UIT-BXGY", 2);
			await expect(freeRows(page)).toHaveCount(1);
			steps.q2 = await row(page, "UIT-BXGY").innerText();
			if (allow) {
				await expect(breakdown(page, "UIT-BXGY")).toContainText("84.00");
				await expect(row(page, "UIT-BXGY").getByTestId("fnf-line-note")).toHaveCount(0);
			} else {
				await expect(row(page, "UIT-BXGY")).toContainText("Promotion item — not eligible for Friends & Family");
				await expect(row(page, "UIT-BXGY")).toContainText("120.00");
			}

			await setQty(page, "UIT-BXGY", 4);
			await expect(freeRows(page)).not.toHaveCount(0);
			steps.q4 = await page.locator("body").innerText().then((t) => t.slice(t.indexOf("Cart Items"), t.indexOf("Total Quantity")));
			steps.q4free = await freeRows(page).count();

			bodies.length = 0;
			await setQty(page, "UIT-BXGY", 1);
			await expect(freeRows(page)).toHaveCount(0);
			await expect(row(page, "UIT-BXGY").getByTestId("fnf-line-note")).toHaveCount(0);
			await expect(breakdown(page, "UIT-BXGY")).toContainText("42.00");
			expect(bodies.length, "a pricing request after qty back to 1").toBeGreaterThan(0);
			expect(bodies.at(-1)).not.toContain("UIT-PR-BXGY");

			const s = await sell(page);
			record(`BXGY-a-${allow}`, { invoice: s.name, total: s.total, steps, rows: s.invoice.items, usage: s.invoice.usage, errors: errorsSince(since) });
			expectSaleOk(s.invoice, s.total);
			expect(s.invoice.items.length).toBe(1);
			const r = s.invoice.items[0];
			expect(Number(r.rate)).toBeCloseTo(42, 2);
			expect(r.posnext_discount_source).toBe("friends_and_family");
			expect(r.pricing_rules || "").not.toContain("UIT-PR-BXGY");
			expect(s.invoice.usage.reduce((a, u) => a + u.amount, 0)).toBeCloseTo(18, 2);
		});
	});

	test(`(a2) BXGY x2 sold with F&F, checkbox ${allow ? "ON" : "OFF"}: paid line, free row, USG`, async ({ page }) => {
		await withCheckbox(page, allow, async () => {
			await addItem(page, "UIT-BXGY");
			await setQty(page, "UIT-BXGY", 2);
			await expect(freeRows(page)).toHaveCount(1);
			const s = await sell(page);
			record(`BXGY-a2-${allow}`, { invoice: s.name, total: s.total, rows: s.invoice.items, usage: s.invoice.usage, logs: s.invoice.logs, errors: errorsSince(since) });
			expectSaleOk(s.invoice, s.total);
			const paid = paidRows(s.invoice, "UIT-BXGY");
			const free = freeOf(s.invoice);
			expect(free.length).toBe(1);
			expect(free[0].pricing_rules).toContain("UIT-PR-BXGY");
			expect(Number(free[0].rate)).toBe(0);
			const usage = s.invoice.usage.reduce((a, u) => a + u.amount, 0);
			if (allow) {
				expect(paid.every((p) => p.posnext_discount_source === "friends_and_family")).toBeTruthy();
				expect(Number(paid[0].rate)).toBeCloseTo(42, 2);
				expect(usage).toBeCloseTo(36, 2); // paid qty only
			} else {
				expect(paid.every((p) => !p.posnext_discount_source)).toBeTruthy();
				expect(Number(paid[0].rate)).toBeCloseTo(60, 2);
				expect(usage).toBe(0);
			}
		});
	});
}

for (const allow of [0, 1]) {
	test(`(b) Item Level Discount rule x F&F, checkbox ${allow ? "ON" : "OFF"}: always blocks F&F on the line`, async ({ page }) => {
		await withRule("UIT-PR-B20", { promotion_type: "Item Level Discount" }, async () => {
			await withCheckbox(page, allow, async () => {
				await addItem(page, "UIT-B");
				await addItem(page, "UIT-A");
				await expect(row(page, "UIT-B")).toContainText("160.00");
				await expect(row(page, "UIT-B")).toContainText("Promotion item — not eligible for Friends & Family");
				await expect(breakdown(page, "UIT-A")).toContainText("70.00");
				lastTotalChanged.length = 0;
				let s;
				try {
					s = await sell(page);
				} catch (e) {
					await shot(page, `BXGY-b-${allow}-blocked`);
					const drafts = server("latest", { customer: "UIT-Verified", since, n: 5 });
					record(`BXGY-b-${allow}`, { blocked: String(e.message).slice(0, 300), prompts: [...lastTotalChanged], drafts, errors: errorsSince(since) });
					throw e;
				}
				record(`BXGY-b-${allow}`, { invoice: s.name, total: s.total, changed: s.changed, rows: s.invoice.items, usage: s.invoice.usage, errors: errorsSince(since) });
				expectSaleOk(s.invoice, s.total);
				expect.soft(s.changed, "no re-price at Checkout (cart and server agree)").toBeNull();
				const b = paidRows(s.invoice, "UIT-B")[0];
				expect(Number(b.rate)).toBeCloseTo(160, 2);
				expect(b.posnext_discount_source || "").not.toBe("friends_and_family");
				expect(paidRows(s.invoice, "UIT-A")[0].posnext_discount_source).toBe("friends_and_family");
				expect(s.invoice.usage.reduce((a, u) => a + u.amount, 0)).toBeCloseTo(30, 2);
			});
		});
	});
}

test.describe("(c) Price buy-one rule UIT-PR-BUY1 behaves like BXGY", () => {
	test.beforeAll(() => {
		server("py", {
			code: `
if not frappe.db.exists("Pricing Rule", "UIT-PR-BUY1"):
    src = frappe.get_doc("Pricing Rule", "UIT-PR-B20")
    d = frappe.get_doc({"doctype": "Pricing Rule", "title": "UIT-PR-BUY1", "apply_on": "Item Code",
        "items": [{"item_code": "UIT-A"}], "price_or_product_discount": "Price", "rate_or_discount": "Discount Percentage",
        "discount_percentage": 100, "apply_discount_on_price": "Max", "min_or_max_discount_qty_limit": 1, "min_qty": 2,
        "selling": 1, "company": src.company, "for_price_list": src.for_price_list, "currency": src.currency,
        "pos_only": src.pos_only, "valid_from": src.valid_from})
    d.insert(ignore_permissions=True)
    frappe.rename_doc("Pricing Rule", d.name, "UIT-PR-BUY1", force=True)
result = frappe.db.exists("Pricing Rule", "UIT-PR-BUY1")`,
		});
	});
	test.afterAll(() => {
		server("py", {
			code: `
for n in frappe.get_all("Pricing Rule", filters={"title": "UIT-PR-BUY1"}, pluck="name"):
    used = frappe.db.exists("Sales Invoice Item", {"pricing_rules": ["like", f"%{n}%"]})
    if used:
        frappe.db.set_value("Pricing Rule", n, "disable", 1)
    else:
        frappe.delete_doc("Pricing Rule", n, force=True, ignore_permissions=True)
result = frappe.get_all("Pricing Rule", filters={"title": "UIT-PR-BUY1"}, fields=["name", "disable"])`,
		});
	});

	for (const allow of [0, 1]) {
		test(`(c) UIT-PR-BUY1 x F&F, checkbox ${allow ? "ON" : "OFF"}: qty 1, 2, 3 like BXGY`, async ({ page }) => {
			test.fail(true, "pending port, Price buy-one = BXGY");
			test.info().annotations.push({ type: "pending", description: "pending port, Price buy-one = BXGY" });
			test.info().annotations.push({ type: "rule shape", description: "UIT-PR-BUY1 adds min_qty 2 to the specified fields, so qty 1 is below the offer as with BXGY; drop it if the port defines buy-one without a minimum" });
			await withCheckbox(page, allow, async () => {
				const steps = {};
				await addItem(page, "UIT-A");
				await expect(breakdown(page, "UIT-A")).toContainText("70.00"); // qty 1: F&F, below the rule
				steps.q1 = (await row(page, "UIT-A").innerText()).replace(/\s+/g, " ");
				record(`BXGY-c-${allow}-q1`, { q1: steps.q1 });
				await setQty(page, "UIT-A", 2);
				steps.q2 = await page.locator("body").innerText().then((t) => t.slice(t.indexOf("Cart Items"), t.indexOf("Total Quantity")));
				if (allow) {
					await expect(row(page, "UIT-A").getByTestId("fnf-line-note")).toHaveCount(0);
					await expect(page.getByText(/Friends & Family/).first()).toBeVisible();
				} else {
					await expect(row(page, "UIT-A")).toContainText("Promotion item — not eligible for Friends & Family");
				}
				await setQty(page, "UIT-A", 3);
				steps.q3 = await page.locator("body").innerText().then((t) => t.slice(t.indexOf("Cart Items"), t.indexOf("Total Quantity")));
				record(`BXGY-c-${allow}-steps`, { steps });
				const s = await sell(page);
				record(`BXGY-c-${allow}`, { invoice: s.name, total: s.total, steps, changed: s.changed, rows: s.invoice.items.map((i) => [i.item_code, i.qty, i.rate, i.is_free_item, i.pricing_rules, i.posnext_discount_source]), usage: s.invoice.usage, errors: errorsSince(since) });
				expectSaleOk(s.invoice, s.total);
				const rows = s.invoice.items.filter((i) => i.item_code === "UIT-A");
				// like BXGY: one unit free (rate 0), the paid units get F&F only with the checkbox on
				expect(rows.some((r) => Number(r.rate) === 0)).toBeTruthy();
				const paid = rows.filter((r) => Number(r.rate) > 0);
				if (allow) expect(paid.every((r) => r.posnext_discount_source === "friends_and_family")).toBeTruthy();
				else expect(paid.every((r) => r.posnext_discount_source !== "friends_and_family")).toBeTruthy();
			});
		});
	}
});

// D-R3-01 diagnosis: a fresh Item Level rule (UIT-PR-IL15, 15% on UIT-A2, created here, removed after),
// one line only; F&F customer vs plain customer; the cart's update_invoice body is captured.
test.describe("(b-diag) Item Level Discount, one line, fresh rule", () => {
	test.beforeAll(() => {
		server("py", {
			code: `
if not frappe.db.exists("Pricing Rule", "UIT-PR-IL15"):
    src = frappe.get_doc("Pricing Rule", "UIT-PR-B20")
    d = frappe.get_doc({"doctype": "Pricing Rule", "title": "UIT-PR-IL15", "apply_on": "Item Code",
        "items": [{"item_code": "UIT-A2"}], "price_or_product_discount": "Price", "rate_or_discount": "Discount Percentage",
        "discount_percentage": 15, "promotion_type": "Item Level Discount",
        "selling": 1, "company": src.company, "for_price_list": src.for_price_list, "currency": src.currency,
        "pos_only": src.pos_only, "valid_from": src.valid_from})
    d.insert(ignore_permissions=True)
    frappe.rename_doc("Pricing Rule", d.name, "UIT-PR-IL15", force=True)
result = 1`,
		});
	});
	test.afterAll(() => {
		server("py", {
			code: `
for n in frappe.get_all("Pricing Rule", filters={"title": "UIT-PR-IL15"}, pluck="name"):
    if frappe.db.exists("Sales Invoice Item", {"pricing_rules": ["like", f"%{n}%"]}):
        frappe.db.set_value("Pricing Rule", n, "disable", 1)
    else:
        frappe.delete_doc("Pricing Rule", n, force=True, ignore_permissions=True)
result = 1`,
		});
	});
	for (const customer of ["UIT-Verified", "UIT-Unverified"]) {
		test(`(b-diag) ${customer}, UIT-A2 alone under a fresh Item Level 15% rule`, async ({ page }) => {
			const bodies = [];
			page.on("request", (r) => {
				if (r.method() === "POST" && /update_invoice/.test(r.url())) bodies.push(r.postData() || "");
			});
			await openPos(page);
			await clearCart(page);
			await selectCustomer(page, customer);
			await addItem(page, "UIT-A2");
			const line = (await row(page, "UIT-A2").innerText()).replace(/\s+/g, " ");
			lastTotalChanged.length = 0;
			let s = null;
			let err = null;
			try {
				s = await sell(page);
			} catch (e) {
				err = String(e.message).slice(0, 200);
				await shot(page, `BXGY-bdiag-${customer}`);
			}
			const sent = bodies.map((b) => {
				try {
					const d = JSON.parse(b).data;
					const doc = typeof d === "string" ? JSON.parse(d) : d;
					return (doc.items || []).map((i) => ({ item: i.item_code, rate: i.rate, pricing_rules: i.pricing_rules, src: i.posnext_discount_source }));
				} catch {
					return b.slice(0, 200);
				}
			});
			record(`BXGY-bdiag-${customer}`, { line, err, prompts: [...lastTotalChanged], sent, invoice: s?.name, rows: s?.invoice.items.map((i) => [i.item_code, i.rate, i.pricing_rules, i.posnext_discount_source]), errors: errorsSince(since) });
			expect(err).toBeNull();
			expect(s.changed).toBeNull();
		});
	}
});
