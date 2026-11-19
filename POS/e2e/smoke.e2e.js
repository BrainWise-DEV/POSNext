// Playwright smoke harness for the F&F / coupons / offers UI test plan, section 6:
// docs/superpowers/plans/2026-11-18-ui-test-plan-ff-coupons-offers.md
//
// Data comes only from `bench --site <site> execute pos_next.ui_test_seed.seed`.
// Selectors: the existing data-testid attributes, roles and visible text.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { AUTH_DIR } from "./global-setup.js";

const dir = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = path.join(dir, "artifacts");
const CASHIER = path.join(AUTH_DIR, "cashier.json");
const CASHIER2 = path.join(AUTH_DIR, "cashier2.json");

const PROFILE = "UIT-FF Profile";
const MAILPIT = (process.env.UIT_MAILPIT_URL || "http://localhost:8025").replace(/\/$/, "");
const ADMIN_TOKEN =
	process.env.UIT_ADMIN_API_KEY && process.env.UIT_ADMIN_API_SECRET
		? `token ${process.env.UIT_ADMIN_API_KEY}:${process.env.UIT_ADMIN_API_SECRET}`
		: null;

test.use({ storageState: CASHIER });

// ---- helpers -------------------------------------------------------------------------

/** A money amount as it appears in the UI, with or without decimals and a currency symbol. */
const amount = (n) => new RegExp(`(?<![\\d.])${String(n).replace(".", "\\.")}(\\.00)?(?![\\d])`);

/** Load /pos and get past the shift dialog (resume or open a shift on UIT-FF Profile). */
async function openPos(page) {
	await page.goto("/pos");
	const search = page.getByRole("textbox", { name: "Search items" });
	const shiftDialog = page.getByRole("dialog").filter({ hasText: "Open POS Shift" });
	await expect(search.or(shiftDialog)).toBeVisible({ timeout: 60_000 });
	if (await shiftDialog.isVisible()) {
		await shiftDialog.getByText(PROFILE, { exact: true }).first().click();
		const step = shiftDialog.getByRole("button", { name: /^(Resume Shift|Open Shift|Next)$/ });
		for (let i = 0; i < 4 && !(await search.isVisible()); i++) {
			if (await step.isVisible().catch(() => false)) await step.click();
			await page.waitForTimeout(700);
		}
	}
	await expect(search).toBeVisible({ timeout: 30_000 });
}

/** Pick a customer in the cart header (the profile starts with UIT-Walk-in). */
async function selectCustomer(page, name) {
	const change = page.getByTitle("Change customer");
	if (await change.isVisible().catch(() => false)) await change.click();
	const box = page.getByRole("textbox", { name: "Search customer in cart" });
	await expect(box).toBeEnabled({ timeout: 30_000 });
	await box.fill(name);
	await page
		.getByRole("button", { name: new RegExp(name) })
		.filter({ hasNotText: "Create New Customer" })
		.first()
		.click();
	await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
}

async function addItem(page, code, times = 1) {
	await page.getByRole("textbox", { name: "Search items" }).fill(code);
	const card = page.getByRole("button", { name: code, exact: true });
	for (let i = 0; i < times; i++) await card.click();
}

/** The paid cart row of an item. UIT-A must not match UIT-A2. */
const row = (page, code) =>
	page.locator("[data-line-key]").filter({ hasText: new RegExp(`${code}(?![\\w-])`) });

const freeRows = (page) => page.getByText("Free gift", { exact: true });

async function setQty(page, code, qty) {
	const box = row(page, code).getByRole("textbox", { name: "Quantity" });
	await box.fill(String(qty));
	await box.press("Enter");
}

async function applyCoupon(page, code) {
	await page.getByRole("button", { name: "Apply coupon code" }).click();
	const dialog = page.getByRole("dialog").filter({ hasText: "Coupon Code" });
	await dialog.getByPlaceholder("ENTER-CODE-HERE").fill(code);
	await dialog.getByRole("button", { name: "Apply", exact: true }).click();
	return dialog;
}

async function closeCouponDialog(page) {
	const close = page.getByRole("dialog").getByRole("button", { name: "Close", exact: true });
	if (await close.isVisible().catch(() => false)) await close.click();
}

/** Press Checkout and return the payment dialog with its Grand Total as a number. */
async function openPayment(page) {
	await page.getByRole("button", { name: "Proceed to payment" }).click();
	const dialog = page.getByRole("dialog").filter({ hasText: "Complete Payment" });
	await expect(dialog).toBeVisible();
	const text = await dialog
		.getByText("Grand Total", { exact: true })
		.first()
		.locator("xpath=following-sibling::span[1]")
		.textContent();
	return { dialog, total: Number(text.replace(/[^\d.]/g, "")) };
}

/** Pay the whole amount in cash and return the submit_invoice request body and invoice. */
async function payExact(page, dialog) {
	const done = page.waitForResponse(
		(r) => r.url().includes("pos_next.api.invoices.submit_invoice") && r.request().method() === "POST",
	);
	await dialog.getByRole("button", { name: /^Exact cash/ }).click();
	const res = await done;
	const body = await res.json();
	return { request: res.request().postData() || "", invoice: body.message || {}, status: res.status() };
}

/** INV-1: the dialog total equals the submitted grand total (or rounded total). */
function expectParity(total, invoice) {
	const server = Number(invoice.rounded_total || invoice.grand_total);
	expect(server).toBeCloseTo(total, 2);
}

const successDialog = (page) => page.getByRole("dialog").filter({ hasText: "Invoice Created Successfully" });

async function adminSetRuleDisabled(request, rule, disabled) {
	const res = await request.put(`/api/resource/Pricing Rule/${encodeURIComponent(rule)}`, {
		headers: { Authorization: ADMIN_TOKEN },
		data: { disable: disabled ? 1 : 0 },
	});
	expect(res.ok(), `PUT Pricing Rule ${rule}`).toBeTruthy();
}

// ---- 1. U-01 OTP -----------------------------------------------------------------------

test("U-01 OTP: Frappe Email verify of UIT-OTP1", async ({ page, request }) => {
	const email = "uit-otp1@uit-ff.example";
	const mails = async () => {
		const res = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${email}"` } });
		expect(res.ok(), "Mailpit search").toBeTruthy();
		return (await res.json()).messages || [];
	};
	const before = new Set((await mails()).map((m) => m.ID));

	await openPos(page);
	await selectCustomer(page, "UIT-OTP1");
	await page.getByTitle("Edit customer details").click();

	await page.getByTestId("send-code").click();
	await expect(page.getByTestId("otp-input")).toBeVisible();
	await expect(page.getByTestId("countdown")).toContainText("Code expires in");

	let code = "";
	await expect
		.poll(
			async () => {
				const fresh = (await mails()).find((m) => !before.has(m.ID));
				if (!fresh) return "";
				const msg = await (await request.get(`${MAILPIT}/api/v1/message/${fresh.ID}`)).json();
				code = (msg.Text || msg.HTML || "").match(/\b\d{6}\b/)?.[0] || "";
				return code;
			},
			{ timeout: 60_000, message: "6-digit code in Mailpit" },
		)
		.toMatch(/^\d{6}$/);

	await page.getByTestId("otp-input").fill(code);
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("verified-badge")).toContainText("Email verified");
});

// ---- 2. U-06 badge + reload ------------------------------------------------------------

test("U-06 F&F badge and line survive a reload", async ({ page }) => {
	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");

	const check = async () => {
		await expect(page.getByTestId("fnf-customer-badge")).toHaveText("F&F 30%");
		await expect(page.getByTestId("fnf-cart-messages")).toContainText(
			/Friends & Family 30% applied to 1 item\(s\) — saving 30(\.00)?/,
		);
		const breakdown = row(page, "UIT-A").getByTestId("line-price-breakdown");
		await expect(breakdown).toContainText(amount(100));
		await expect(breakdown).toContainText(amount(70));
	};
	await check();
	await page.reload();
	await expect(page.getByRole("textbox", { name: "Search items" })).toBeVisible({ timeout: 60_000 });
	await check();
});

// ---- 3. U-09 F&F submit + INV-1 --------------------------------------------------------

test("U-09 F&F sale submits at the cart total", async ({ page }) => {
	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(row(page, "UIT-A").getByTestId("line-price-breakdown")).toContainText(amount(70));

	const { dialog, total } = await openPayment(page);
	await expect(dialog).toContainText(amount(70));
	const paid = await payExact(page, dialog);
	expect(paid.status).toBe(200);
	expectParity(total, paid.invoice);
	await expect(successDialog(page)).toBeVisible();
});

// ---- 4. U-15 (a) line coupon, hold, resume, pay ----------------------------------------

test("U-15a line coupon on a held draft, then paid", async ({ page }) => {
	await openPos(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-B");

	await applyCoupon(page, "UIT-L10");
	await expect(page.getByText("UIT-L10 applied successfully").first()).toBeVisible();
	await closeCouponDialog(page);
	await expect(row(page, "UIT-A").getByTestId("line-price-breakdown")).toContainText(amount(90));
	await expect(row(page, "UIT-B")).not.toContainText("UIT-L10");

	// Hold, then resume from Draft Invoices.
	await page.getByRole("button", { name: "Hold", exact: true }).click();
	await expect(page.getByText("Your cart is empty")).toBeVisible();
	await page.getByRole("button", { name: /Draft Invoices/ }).click();
	const drafts = page.getByRole("dialog").filter({ hasText: "Draft Invoices" });
	await drafts.getByText("UIT-Unverified").first().click();
	await expect(row(page, "UIT-A")).toBeVisible();
	await expect(page.getByRole("button", { name: "Remove coupon UIT-L10" })).toBeVisible();

	const { dialog, total } = await openPayment(page);
	const paid = await payExact(page, dialog);
	expectParity(total, paid.invoice);
	expect(paid.request).toContain("UIT-L10");
	await expect(successDialog(page)).toBeVisible();
});

// ---- 5. U-18 (b) CVF-03: line coupon beats F&F, survives reload -------------------------

test("U-18b a 50% line coupon wins over F&F and survives a reload", async ({ page }) => {
	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await applyCoupon(page, "UIT-L50");
	await closeCouponDialog(page);

	const check = async () => {
		await expect(row(page, "UIT-A").getByTestId("line-price-breakdown")).toContainText(amount(50));
		await expect(page.getByTestId("fnf-customer-badge")).toHaveAttribute(
			"title",
			/Coupon UIT-L50 applied instead of Friends & Family/,
		);
		await expect(page.getByTestId("fnf-cart-messages")).toContainText("discounts are never combined");
	};
	await check();
	await page.reload();
	await expect(page.getByRole("textbox", { name: "Search items" })).toBeVisible({ timeout: 60_000 });
	await check();
});

// ---- 6. U-21b BXGY qty 1 -> 2 -> 1 brings F&F back --------------------------------------

test("U-21b BXGY 1 -> 2 -> 1 brings F&F back before payment opens", async ({ page }) => {
	const pricing = [];
	page.on("request", (r) => {
		if (
			r.method() === "POST" &&
			/apply_friends_and_family_discount|\.apply_offers/.test(r.url())
		) {
			pricing.push(r.postData() || "");
		}
	});

	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-BXGY");
	const line = row(page, "UIT-BXGY");
	await expect(line.getByTestId("line-price-breakdown")).toContainText(amount(42));

	await setQty(page, "UIT-BXGY", 2);
	await expect(line.getByTestId("fnf-line-note")).toContainText(
		"Promotion item — not eligible for Friends & Family",
	);
	await expect(line).toContainText(amount(120));
	await expect(freeRows(page)).toHaveCount(1);

	pricing.length = 0;
	await setQty(page, "UIT-BXGY", 1);
	await expect(freeRows(page)).toHaveCount(0);
	await expect(line.getByTestId("fnf-line-note")).toHaveCount(0);
	await expect(line.getByTestId("line-price-breakdown")).toContainText(amount(42));
	expect(pricing.length, "a pricing request after qty back to 1").toBeGreaterThan(0);
	expect(pricing.at(-1)).not.toContain("UIT-PR-BXGY");

	// Payment opens at 42 with no "price changed" prompt.
	const { dialog, total } = await openPayment(page);
	await expect(page.getByText("Invoice Total Changed")).toHaveCount(0);
	await expect(dialog).toContainText(amount(42));
	const paid = await payExact(page, dialog);
	expectParity(total, paid.invoice);
	expect(paid.request).not.toContain("UIT-PR-BXGY");
	await expect(successDialog(page)).toBeVisible();
});

// ---- 7. U-23 (a) BXGY free row, survives reload -----------------------------------------

test("U-23a BXGY x2 for a plain customer gives a free row that survives a reload", async ({ page }) => {
	await openPos(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);

	const check = async () => {
		await expect(row(page, "UIT-BXGY")).toContainText(amount(60));
		await expect(freeRows(page)).toHaveCount(1);
		await expect(row(page, "UIT-BXGY")).toHaveCount(1);
	};
	await check();
	await page.reload();
	await expect(page.getByRole("textbox", { name: "Search items" })).toBeVisible({ timeout: 60_000 });
	await check();
});

// ---- 8. U-25 stale offer ----------------------------------------------------------------

test("U-25 a stale free-item offer is refused, then sells after a refresh", async ({ page, request }) => {
	test.skip(!ADMIN_TOKEN, "Needs UIT_ADMIN_API_KEY and UIT_ADMIN_API_SECRET to disable UIT-PR-FREE.");

	await openPos(page);
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-TRIG");
	await expect(freeRows(page)).toHaveCount(1);

	await adminSetRuleDisabled(request, "UIT-PR-FREE", true);
	try {
		const { dialog } = await openPayment(page);
		await payExact(page, dialog);
		const error = page.getByRole("dialog").filter({ hasText: /not backed by an offer/ });
		await expect(error).toBeVisible();
		await expect(error).toContainText(/offers changed/i);
		await error.getByRole("button", { name: "Close", exact: true }).click();

		// Refresh: reload the page, which re-applies the offers.
		await page.reload();
		await expect(page.getByRole("textbox", { name: "Search items" })).toBeVisible({ timeout: 60_000 });
		await expect(freeRows(page)).toHaveCount(0);
		const retry = await openPayment(page);
		await payExact(page, retry.dialog);
		await expect(successDialog(page)).toBeVisible();
	} finally {
		await adminSetRuleDisabled(request, "UIT-PR-FREE", false);
	}
});

// ---- 9. U-29 (a) offline sale without F&F ------------------------------------------------

test("U-29a a sale made offline has no F&F badge and syncs without an error", async ({ page, context }) => {
	await openPos(page);
	await expect(page.getByRole("button", { name: "Cache ready" })).toBeVisible({ timeout: 120_000 });

	await context.setOffline(true);
	await expect(page.getByRole("button", { name: "Offline mode active" })).toBeVisible();
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await expect(row(page, "UIT-A")).toBeVisible();
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);

	const { dialog } = await openPayment(page);
	await dialog.getByRole("button", { name: /^Exact cash/ }).click();
	await expect(successDialog(page)).toBeVisible();
	await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();

	// Back online: the queue syncs and the cashier sees no error dialog.
	const synced = page.waitForResponse(
		(r) => r.url().includes("pos_next.api.invoices.submit_invoice") && r.request().method() === "POST",
		{ timeout: 120_000 },
	);
	await context.setOffline(false);
	await expect(page.getByRole("button", { name: "Online mode active" })).toBeVisible();
	await page.getByRole("button", { name: "Online mode active" }).click();
	expect((await synced).status()).toBe(200);
	await expect(page.getByRole("dialog").filter({ hasText: "Error" })).toHaveCount(0);
});

// ---- 10. U-33 (a) receipt HTML artifact ---------------------------------------------------

test("U-33a POS receipt names the F&F discount and marks the free row", async ({ page, context }) => {
	// Force the built-in receipt template (the one the plan's U-33a describes): the /printview
	// popup is refused, so the app falls back to printInvoiceCustom().
	await context.addInitScript(() => {
		const open = window.open.bind(window);
		window.open = (url, ...rest) =>
			typeof url === "string" && url.startsWith("/printview") ? null : open(url, ...rest);
	});

	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-A");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await expect(freeRows(page)).toHaveCount(1);

	const { dialog } = await openPayment(page);
	const paid = await payExact(page, dialog);
	const invoiceName = paid.invoice.name;
	expect(invoiceName).toBeTruthy();

	const popup = context.waitForEvent("page");
	await page.getByRole("button", { name: "Print Invoice" }).click();
	const receipt = await popup;
	await receipt.waitForLoadState("domcontentloaded");
	const html = await receipt.content();

	fs.mkdirSync(ARTIFACTS, { recursive: true });
	fs.writeFileSync(path.join(ARTIFACTS, `U-33a-${invoiceName}.html`), html);

	expect(html).toContain("Friends & Family discount");
	expect(html).toContain("(FREE)");
});

// ---- 11. U-35 RTL screenshots --------------------------------------------------------------

test("U-35 Arabic layout: badge, line note, Coupon dialog and payment dialog", async ({ page }) => {
	const shot = (name) => path.join(ARTIFACTS, `U-35-${name}.png`);
	const unclipped = async (locator) => {
		const [scroll, client] = await locator.evaluate((el) => [el.scrollWidth, el.clientWidth]);
		expect(scroll).toBeLessThanOrEqual(client + 1);
	};
	fs.mkdirSync(ARTIFACTS, { recursive: true });

	await openPos(page);
	await selectCustomer(page, "UIT-Verified");
	await addItem(page, "UIT-BXGY");
	await setQty(page, "UIT-BXGY", 2);
	await expect(page.getByTestId("fnf-line-note")).toBeVisible();

	try {
		await page.getByRole("button", { name: /English/ }).first().click();
		await page.getByRole("menuitem", { name: /العربية|Arabic/ }).click();
		await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

		const badge = page.getByTestId("fnf-customer-badge");
		await expect(badge).toBeVisible();
		await badge.screenshot({ path: shot("badge") });
		await unclipped(badge);

		const note = page.getByTestId("fnf-line-note").first();
		await note.screenshot({ path: shot("line-note") });
		await unclipped(note);

		// Arabic labels from pos_next/translations/ar.csv.
		await page.getByRole("button", { name: "تطبيق رمز الكوبون" }).click();
		const coupon = page.getByRole("dialog");
		await expect(coupon).toBeVisible();
		await coupon.screenshot({ path: shot("coupon-dialog") });
		await page.keyboard.press("Escape");
		await expect(coupon).toHaveCount(0);

		await page.getByRole("button", { name: "الدفع وإنهاء الطلب" }).click();
		const payment = page.getByRole("dialog");
		await expect(payment).toBeVisible();
		await payment.screenshot({ path: shot("payment-dialog") });
	} finally {
		// The language is stored on the user: put it back.
		await page.keyboard.press("Escape");
		await page.getByRole("button", { name: /العربية|Arabic/ }).first().click();
		await page.getByRole("menuitem", { name: /English/ }).click();
	}
});

// ---- 12. U-38 (a) two-context submit race ---------------------------------------------------

test("U-38a two cashiers submit the same capped F&F cart, both succeed", async ({ browser }) => {
	test.skip(
		!process.env.UIT_RACE || !process.env.UIT_USER2 || !fs.existsSync(CASHIER2),
		"Set UIT_RACE=1 and UIT_USER2/UIT_PASSWORD2, and set the UIT-Cap monthly cap to used + 40 first (see README).",
	);

	const ctxA = await browser.newContext({ storageState: CASHIER });
	const ctxB = await browser.newContext({ storageState: CASHIER2 });
	try {
		const a = await ctxA.newPage();
		const b = await ctxB.newPage();
		const prepare = async (page) => {
			await openPos(page);
			await selectCustomer(page, "UIT-Cap");
			await addItem(page, "UIT-A");
			await setQty(page, "UIT-A", 2);
			return openPayment(page);
		};
		const [payA, payB] = await Promise.all([prepare(a), prepare(b)]);
		await payExact(a, payA.dialog);
		await expect(successDialog(a)).toBeVisible();
		await payExact(b, payB.dialog);
		await expect(successDialog(b)).toBeVisible();
	} finally {
		await ctxA.close();
		await ctxB.close();
	}
});
