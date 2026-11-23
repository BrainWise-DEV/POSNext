// Plan §3.6–3.7: Jinja receipts (U-33 b, c), Arabic (U-34 a, b), narrow layout (U-36), accessibility (U-37).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
	AUTH, ARTIFACTS, addItem, applyCoupon, clearCart, closeDialogs, errorsSince, expectSettingsClean, nowStamp,
	openPayment, openPos, record, selectCustomer, sell, setQty, shot,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

async function jinja(page, name) {
	const url = `/printview?doctype=Sales%20Invoice&name=${encodeURIComponent(name)}&format=POS%20Next%20Receipt&no_letterhead=1`;
	const p = await page.context().newPage();
	const res = await p.goto(url);
	const html = await p.content();
	const text = await p.locator("body").innerText();
	await p.close();
	fs.writeFileSync(path.join(ARTIFACTS, `U-33b-${name}.html`), html);
	return { status: res.status(), text };
}

test("U-33 (b)(c) Jinja POS Next Receipt: F&F + coupon + free rows, zero total, rounding line", async ({ page }) => {
	await openPos(page);
	await clearCart(page);
	// U-19 shape + a free row (U-23 b)
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-EXCL");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-TRIG");
	await applyCoupon(page, "UIT-L20");
	const s1 = await sell(page);
	// U-17 shape
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L100");
	const s2 = await sell(page);
	const r1 = await jinja(page, s1.name);
	const r2 = await jinja(page, s2.name);
	record("U-33bc", { a: s1.name, aSi: s1.invoice.si, b: s2.name, r1: [r1.status, r1.text.slice(0, 1500)], r2: [r2.status, r2.text.slice(0, 800)] });
	expect(r1.status).toBe(200);
	expect(r1.text).toMatch(/Coupon: UIT-L20|UIT-L20/);
	expect(r2.text).toMatch(/\(FREE\)/);
	if (Number(s1.invoice.si.rounding_adjustment)) {
		expect.soft(r1.text, "a rounding line when rounding applies (D-R2-12)").toMatch(/Round/i);
	}
	expect.soft(r1.text, "currency symbol (D-8)").not.toContain("£ or");
});

test("U-34 (a)(b) Arabic: comparison message and verification panel in Arabic", async ({ page }) => {
	await openPos(page);
	await clearCart(page);
	// build the cart in English (selectors are English names), then switch the UI language
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-B");
	const res = {};
	try {
		await page.getByRole("button", { name: /English/ }).first().click();
		await page.getByRole("menuitem", { name: /العربية|Arabic/ }).first().click();
		await expect(page.locator("html")).toHaveAttribute("dir", "rtl", { timeout: 30_000 });
		await page.waitForTimeout(3000);
		res.cmp = await page.locator("[data-line-key]").first().innerText().catch(() => "");
		res.msgs = await page.getByTestId("fnf-cart-messages").innerText().catch(() => "");
		await shot(page, "U-34b-ar");
		await page.getByRole("button", { name: "تعديل بيانات العميل" }).first().click();
		await page.waitForTimeout(1500);
		res.panel = await page.getByTestId("customer-dialog-body").innerText().catch(() => "");
		await shot(page, "U-34a-ar-dialog");
		await closeDialogs(page);
	} finally {
		const lang = page.getByRole("button", { name: /العربية|Arabic/ }).first();
		if (await lang.isVisible().catch(() => false)) {
			await lang.click();
			await page.getByRole("menuitem", { name: /English/ }).first().click();
			await expect(page.locator("html")).not.toHaveAttribute("dir", "rtl", { timeout: 30_000 });
		}
		await clearCart(page);
	}
	record("U-34ab", { cmp: res.cmp?.replace(/\s+/g, " "), msgs: res.msgs, panel: res.panel?.slice(0, 500) });
	expect(res.cmp + res.msgs).toMatch(/الأصدقاء والعائلة/);
	expect(res.panel).not.toMatch(/\b(Verify email|Wrong code|Send code)\b/);
});

for (const [w, h] of [[390, 844], [768, 1024]]) {
	test(`U-36 narrow layout ${w}x${h}: no horizontal scroll, touch targets`, async ({ page }) => {
		await page.setViewportSize({ width: w, height: h });
		await openPos(page);
		await clearCart(page);
		const measure = async (label) => {
			const r = await page.evaluate(() => {
				const small = [];
				for (const b of document.querySelectorAll("button, [role=button], input")) {
					const rc = b.getBoundingClientRect();
					if (!rc.width || !rc.height) continue;
					const st = getComputedStyle(b);
					if (st.visibility === "hidden" || st.display === "none") continue;
					if (rc.height < 40 || rc.width < 40) small.push(`${(b.getAttribute("aria-label") || b.innerText || b.placeholder || b.tagName).trim().slice(0, 24)}:${Math.round(rc.width)}x${Math.round(rc.height)}`);
				}
				return { scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth, small: small.slice(0, 40), nSmall: small.length };
			});
			return { label, ...r };
		};
		const out = [await measure("main")];
		await shot(page, `U-36-${w}-main`);
		await addItem(page, "UIT-A").catch(() => {});
		const checkout = page.getByRole("button", { name: "Proceed to payment" });
		if (!(await checkout.isVisible().catch(() => false))) {
			// narrow layout: the cart is behind a toggle
			const toggle = page.getByRole("button", { name: /cart|السلة/i }).first();
			if (await toggle.isVisible().catch(() => false)) await toggle.click();
		}
		out.push(await measure("cart"));
		await shot(page, `U-36-${w}-cart`);
		if (await checkout.isVisible().catch(() => false)) {
			const pay = await openPayment(page).catch(() => null);
			if (pay) {
				out.push(await measure("payment"));
				await shot(page, `U-36-${w}-payment`);
				await closeDialogs(page);
			}
		}
		await clearCart(page).catch(() => {});
		record(`U-36-${w}`, { out });
		for (const o of out) expect(o.scroll, `${o.label} horizontal scroll`).toBeLessThanOrEqual(0);
		expect.soft(out.map((o) => o.nSmall).reduce((a, b) => a + b, 0), "controls under 40 px (D-21)").toBe(0);
	});
}

test("U-37 accessibility: Coupon dialog focus, error live region, accessible names", async ({ page }) => {
	await openPos(page);
	await clearCart(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	const opener = page.getByRole("button", { name: "Apply coupon code" });
	await opener.focus();
	await page.keyboard.press("Enter");
	const dlg = page.getByRole("dialog").last();
	await expect(dlg).toBeVisible();
	const focusIn = await page.evaluate(() => {
		const a = document.activeElement;
		return { inDialog: !!a?.closest("[role=dialog]"), name: a?.getAttribute("aria-label") || a?.innerText || a?.placeholder || a?.tagName };
	});
	await page.keyboard.type("NOPE-123");
	await page.keyboard.press("Enter");
	await page.waitForTimeout(1500);
	const afterErr = await page.evaluate(() => {
		const a = document.activeElement;
		const live = Array.from(document.querySelectorAll("[aria-live],[role=alert],[role=status]")).map((e) => e.innerText).join(" | ");
		return { focus: a?.tagName, inDialog: !!a?.closest("[role=dialog]"), live };
	});
	await page.keyboard.press("Escape");
	await page.waitForTimeout(500);
	const back = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") || document.activeElement?.innerText);
	const unnamed = await page.evaluate(() =>
		Array.from(document.querySelectorAll("[data-testid]")).filter((e) => /BUTTON|INPUT/.test(e.tagName) && !(e.getAttribute("aria-label") || e.innerText?.trim() || e.labels?.length || e.placeholder)).map((e) => e.dataset.testid),
	);
	record("U-37", { focusIn, afterErr, back, unnamed });
	await clearCart(page);
	expect(focusIn.inDialog).toBe(true);
	expect.soft(afterErr.live, "error reaches a live region (D-22)").toMatch(/does not exist/);
	expect.soft(afterErr.inDialog, "focus stays in the dialog after an error (D-22)").toBe(true);
	expect(back).toMatch(/coupon/i);
	expect(unnamed).toEqual([]);
});
