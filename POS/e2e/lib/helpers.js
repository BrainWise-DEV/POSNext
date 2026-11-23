// Shared helpers for the UIT run-3 specs: POS UI steps + the Python server verifier.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
export const E2E = path.resolve(here, "..");
export const AUTH = {
	cashier: path.join(E2E, ".auth", "cashier.json"),
	cashier2: path.join(E2E, ".auth", "cashier2.json"),
	manager: path.join(E2E, ".auth", "manager.json"),
};
export const ARTIFACTS = path.resolve(process.env.UIT_ARTIFACTS || path.join(E2E, "artifacts"));
export const SNAPSHOT = path.join(ARTIFACTS, "settings-snapshot-pre.json");
export const PROFILE = "UIT-FF Profile";
export const MAILPIT = (process.env.UIT_MAILPIT_URL || "http://localhost:8025").replace(/\/$/, "");
const SITES = process.env.UIT_SITES_DIR || "/home/ubuntu/frappe-bench/sites";
const PY = path.join(SITES, "..", "env", "bin", "python");

fs.mkdirSync(ARTIFACTS, { recursive: true });

// ---- server side ------------------------------------------------------------------------

/** Run a server.py command as Administrator (Python route) and return its JSON result. */
export function server(cmd, args = {}) {
	const out = execFileSync(PY, [path.join(here, "server.py"), cmd, JSON.stringify(args)], {
		cwd: SITES,
		encoding: "utf8",
		maxBuffer: 64 * 1024 * 1024,
		env: { ...process.env, UIT_PASSWORD: "", UIT_PASSWORD2: "", UIT_MANAGER_PASSWORD: "" },
	});
	const at = out.lastIndexOf("@@JSON@@");
	return JSON.parse(out.slice(at + 8));
}
export const inv = (name) => server("invoice", { name });
export const nowStamp = () => server("py", { code: "result=str(frappe.utils.now())" });
export const coupons = () => server("coupons");
export const ffSet = (values) => server("ff_set", { values });
export const ffReset = () => server("ff_reset");
export const setDoc = (doctype, name, values) => server("set_value", { doctype, name, values });
export const restoreDoc = (section, docname, fields) =>
	server("restore", { path: SNAPSHOT, section, docname, fields });
export const settingsDiff = () => server("diff", { path: SNAPSHOT });
export const errorsSince = (since) => server("errors_brief", { since });

/** Append a result line (JSON) for the results file; one file per spec run. */
export function record(id, data) {
	fs.appendFileSync(
		path.join(ARTIFACTS, "evidence.jsonl"),
		JSON.stringify({ id, at: new Date().toISOString(), ...data }) + "\n",
	);
}

/** Common server assertions for a submitted sale. */
export function expectSaleOk(data, dialogTotal) {
	expect(data.si.docstatus, `${data.si.name} submitted`).toBe(1);
	expect(data.paid_equals_due, `${data.si.name} collected ${data.collected} = due ${data.due}`).toBeTruthy();
	if (dialogTotal !== undefined) expect(Number(data.due)).toBeCloseTo(dialogTotal, 2);
}

// ---- UI ---------------------------------------------------------------------------------

/** A money amount as it appears in the UI. */
export const amount = (n) =>
	new RegExp(`(?<![\\d.,])${Number(n).toLocaleString("en-US", { minimumFractionDigits: 2 }).replace(/[.,]/g, "\\$&")}(?![\\d])`);

export const searchBox = (page) => page.getByRole("textbox", { name: /Search items/i }).first();

/** Load /pos and get past the shift dialog (resume or open a shift on the profile). */
export async function openPos(page, profile = PROFILE) {
	await page.goto("/pos");
	const search = searchBox(page);
	const shiftDialog = page.getByRole("dialog").filter({ hasText: /Open POS Shift|Resume|shift/i });
	await expect(search.or(shiftDialog).first()).toBeVisible({ timeout: 90_000 });
	for (let i = 0; i < 12 && !(await search.isVisible().catch(() => false)); i++) {
		const dlg = page.getByRole("dialog").first();
		if (await dlg.isVisible().catch(() => false)) {
			const prof = dlg.getByRole("heading", { name: profile, exact: true });
			if (await prof.isVisible().catch(() => false)) await prof.click();
			const step = dlg.getByRole("button", { name: /^(Resume Shift|Resume|Open Shift|Next|Continue)$/ });
			if (await step.first().isEnabled().catch(() => false)) await step.first().click();
		}
		await page.waitForTimeout(1000);
	}
	await expect(search).toBeVisible({ timeout: 60_000 });
	await waitIdle(page);
}

/** Wait until no pricing/offer request is in flight for a moment. */
export async function waitIdle(page, ms = 1200) {
	await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
	await page.waitForTimeout(ms);
}

export async function dump(page, name) {
	await page.screenshot({ path: path.join(ARTIFACTS, `${name}.png`), fullPage: true });
	fs.writeFileSync(path.join(ARTIFACTS, `${name}.aria.txt`), await page.locator("body").ariaSnapshot());
}

export async function shot(page, name) {
	await page.screenshot({ path: path.join(ARTIFACTS, `${name}.png`) });
}

/** Pick a customer in the cart header. */
export async function selectCustomer(page, name) {
	const box = page.getByRole("textbox", { name: "Search customer in cart" });
	if (!(await box.isVisible().catch(() => false))) {
		const remove = page.getByRole("button", { name: "Remove customer" });
		if (await remove.isVisible().catch(() => false)) await remove.click();
		else await page.locator("button", { has: page.locator("p") }).filter({ hasText: /^UIT-|Walk/ }).first().click();
	}
	await expect(box).toBeEnabled({ timeout: 30_000 });
	await box.fill(name);
	await page
		.getByRole("button", { name: new RegExp(`(^|\\s)${name.replace(/[-]/g, "\\-")}(\\s|$)`) })
		.filter({ hasNotText: "Create New Customer" })
		.first()
		.click();
	await expect(page.getByRole("button", { name: "Remove customer" })).toBeVisible();
	await waitIdle(page);
}

export async function addItem(page, code, times = 1) {
	await searchBox(page).fill(code);
	const card = page.getByRole("button", { name: code, exact: true }).first();
	for (let i = 0; i < times; i++) {
		await card.click();
		await page.waitForTimeout(300);
	}
	await searchBox(page).fill("");
	await waitIdle(page);
}

/** The paid cart row of an item (UIT-A must not match UIT-A2). */
export const row = (page, code) =>
	page.locator("[data-line-key]").filter({ has: page.getByRole("heading", { name: code, exact: true }) });
export const breakdown = (page, code) => row(page, code).getByTestId("line-price-breakdown");
export const freeRows = (page) => page.getByText("Free gift", { exact: true });

export async function setQty(page, code, qty) {
	const box = row(page, code).getByRole("textbox", { name: "Quantity" });
	await box.fill(String(qty));
	await box.press("Enter");
	await waitIdle(page, 1500);
}

export async function applyCoupon(page, code, { close = true } = {}) {
	// with a coupon applied the cart button is named "Coupon"
	await page.getByRole("button", { name: "Apply coupon code" }).or(page.getByRole("button", { name: "Coupon", exact: true })).first().click();
	const dialog = page.getByRole("dialog").filter({ hasText: /Coupon/ }).last();
	const input = dialog.getByPlaceholder(/ENTER-CODE-HERE/i);
	if (!(await input.isVisible({ timeout: 3000 }).catch(() => false))) {
		// a coupon is already applied: the dialog offers only Remove (no second code)
		const t = `NO_INPUT\n${await dialog.innerText().catch(() => "")}`;
		if (close) await closeDialogs(page);
		return t;
	}
	await input.fill(code);
	await dialog.getByRole("button", { name: "Apply", exact: true }).click();
	await page.waitForTimeout(700);
	// the dialog text, or (if it closed) the page text with the toast
	const quick = await page.locator("body").innerText().catch(() => "");
	await waitIdle(page, 1000);
	const text = ((await dialog.isVisible().catch(() => false)) ? await dialog.innerText().catch(() => "") : "") + "\n" + quick;
	if (close) await closeDialogs(page);
	return text;
}

export async function closeDialogs(page) {
	for (let i = 0; i < 3; i++) {
		const d = page.getByRole("dialog").last();
		if (!(await d.isVisible().catch(() => false))) return;
		const btn = d.getByRole("button", { name: /^(Close|Cancel|Done)$/ }).first();
		if (await btn.isVisible().catch(() => false)) await btn.click();
		else await page.keyboard.press("Escape");
		await page.waitForTimeout(400);
	}
}

/** Text of the cart totals area as a map, e.g. {"Grand Total": 218.5, "Rounded Total": 218}. */
export async function cartTotals(page) {
	const t = await page.locator("body").innerText();
	const out = {};
	for (const k of ["Subtotal", "Tax", "Grand Total", "Rounded Total", "Rounding Adjustment", "Friends & Family discount", "Additional Discount", "Coupon discount"]) {
		const m = t.match(new RegExp(`${k}\\s*\\n?\\s*([−-]?)E£\\s*([\\d,]+\\.\\d+)`));
		if (m) out[k] = Number(m[2].replace(/,/g, "")) * (m[1] ? -1 : 1);
	}
	return out;
}

/** Press Checkout and return the payment dialog and the total to collect (from the Exact cash button). */
export async function openPayment(page) {
	await page.getByRole("button", { name: "Proceed to payment" }).click();
	const dialog = page.getByRole("dialog").filter({ hasText: "Complete Payment" });
	const changedDlg = page.getByRole("dialog").filter({ hasText: "Invoice Total Changed" });
	await expect(dialog.or(changedDlg).first()).toBeVisible();
	let changed = null;
	for (let i = 0; i < 4 && (await changedDlg.isVisible().catch(() => false)); i++) {
		const t = (await changedDlg.innerText()).replace(/\s+/g, " ");
		changed = changed ? `${changed} || ${t}` : t;
		lastTotalChanged.push(t);
		await changedDlg.getByRole("button", { name: "Continue to Payment" }).click();
		await expect(dialog.or(changedDlg).first()).toBeVisible();
		await page.waitForTimeout(1500);
	}
	if (await changedDlg.isVisible().catch(() => false)) {
		throw new Error(`Checkout loops on "Invoice Total Changed" (payment never opens): ${changed}`);
	}
	await expect(dialog).toBeVisible();
	await page.waitForTimeout(1000);
	const exact = dialog.getByRole("button", { name: /^Exact cash/ });
	let total = null;
	if (await exact.isVisible().catch(() => false)) {
		const label = await exact.innerText();
		total = Number((label.match(/([\d,]+\.\d+)/) || ["", "0"])[1].replace(/,/g, ""));
	} else {
		const txt = await dialog.innerText();
		const m = txt.match(/(?:Rounded Total|Grand Total)\s*E£\s*([\d,]+\.\d+)/);
		total = m ? Number(m[1].replace(/,/g, "")) : 0;
	}
	return { dialog, total, changed };
}

/** "Invoice Total Changed" prompts seen by openPayment (a test can inspect and clear it). */
export const lastTotalChanged = [];

/** Pay the whole amount in cash; returns {name, status, request, body} of the submit_invoice call. */
export async function payExact(page, dialog) {
	const done = page.waitForResponse(
		(r) => r.url().includes("pos_next.api.invoices.submit_invoice") && r.request().method() === "POST",
		{ timeout: 60_000 },
	);
	const exact = dialog.getByRole("button", { name: /^Exact cash/ });
	if (await exact.isVisible().catch(() => false)) await exact.click();
	else await dialog.getByRole("button", { name: /^\s*Complete Payment\s*$/ }).last().click();
	const res = await done;
	let body = {};
	try {
		body = await res.json();
	} catch {}
	const message = body.message || {};
	return { name: message.name, status: res.status(), request: res.request().postData() || "", body };
}

export const successDialog = (page) => page.getByRole("dialog").filter({ hasText: /Invoice Created Successfully|created successfully/ });

/** Full sale: Checkout, Exact cash, success dialog closed; returns {name, total, invoice}. */
export async function sell(page) {
	const { dialog, total, changed } = await openPayment(page);
	const paid = await payExact(page, dialog);
	expect(paid.status, `submit_invoice HTTP ${paid.status}: ${JSON.stringify(paid.body).slice(0, 400)}`).toBe(200);
	await expect(successDialog(page)).toBeVisible();
	await closeDialogs(page);
	const invoice = inv(paid.name);
	return { name: paid.name, total, invoice, request: paid.request, changed };
}

/** Empty the cart (Clear + confirm) and go back to walk-in. */
export async function clearCart(page) {
	await closeDialogs(page);
	const clear = page.getByRole("button", { name: "Clear", exact: true });
	if (await clear.isVisible().catch(() => false)) {
		await clear.click();
		const confirm = page.getByRole("dialog").getByRole("button", { name: /^(Clear|Yes|Confirm|Clear Cart)/ });
		if (await confirm.first().isVisible({ timeout: 2000 }).catch(() => false)) await confirm.first().click();
	}
	await waitIdle(page, 500);
}

/** Fail if any UIT setting differs from the pre-run snapshot (the restore guard). */
export function expectSettingsClean() {
	const d = settingsDiff();
	expect(d, `settings differ from the snapshot: ${JSON.stringify(d).slice(0, 800)}`).toEqual([]);
}

/** Change a doc, run body, always restore the touched fields from the snapshot. */
export async function withDoc(section, doctype, name, values, body) {
	setDoc(doctype, name, values);
	try {
		return await body();
	} finally {
		restoreDoc(section, name, Object.keys(values));
	}
}

/** Change F&F Settings scalars, run body, always reset_ff. */
export async function withFf(values, body) {
	ffSet(values);
	try {
		return await body();
	} finally {
		ffReset();
	}
}

export const POS_SETTINGS = "UIT-POS Settings FF Profile";
export const withPos = (values, body) => withDoc("pos_settings", "POS Settings", POS_SETTINGS, values, body);
export const withCoupon = (code, values, body) => withDoc("coupons", "POS Coupon", code, values, body);
export const withRule = (rule, values, body) => withDoc("rules", "Pricing Rule", rule, values, body);
export const withProfile = (values, body) => withDoc("profiles", "POS Profile", PROFILE, values, body);

/** Poll the server until fn() returns a truthy value. */
export async function pollServer(fn, { timeout = 90_000, every = 2000, message = "server state" } = {}) {
	const end = Date.now() + timeout;
	for (;;) {
		const v = fn();
		if (v) return v;
		if (Date.now() > end) throw new Error(`timed out waiting for ${message}`);
		await new Promise((r) => setTimeout(r, every));
	}
}

// ---- Mailpit / OTP ------------------------------------------------------------------------
export async function mailIds(request, email) {
	const res = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${email}"` } });
	return ((await res.json()).messages || []).map((m) => m.ID);
}
/** Wait for a new message to `email` not in `before`, return its 6-digit code. */
export async function mailCode(request, email, before, timeout = 60_000) {
	const end = Date.now() + timeout;
	while (Date.now() < end) {
		const res = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${email}"` } });
		const m = ((await res.json()).messages || []).find((x) => !before.includes(x.ID));
		if (m) {
			const msg = await (await request.get(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
			const code = (msg.Text || msg.HTML || "").match(/\b\d{6}\b/)?.[0];
			if (code) return code;
		}
		await new Promise((r) => setTimeout(r, 1500));
	}
	throw new Error(`no OTP mail for ${email}`);
}
export function resetCustomer(name, email) {
	return server("py", {
		code: `frappe.db.set_value("Customer", "${name}", {"email_id": "${email}", "custom_email_verified": 0, "custom_verified_email": None, "custom_email_verified_via": None}, update_modified=False)\nresult=1`,
	});
}
/** Call a whitelisted method from the page (cashier session, CSRF). */
export async function api(page, method, args) {
	return page.evaluate(
		async ([m, a]) => {
			const r = await fetch(`/api/method/${m}`, {
				method: "POST",
				headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.csrf_token || window.frappe?.csrf_token },
				body: JSON.stringify(a),
			});
			let body = {};
			try {
				body = await r.json();
			} catch {}
			return { status: r.status, body };
		},
		[method, args],
	);
}

/** Offline checkout: Exact cash, then the success dialog OR an error dialog (recorded, D-R3-02). */
export const offlineCheckoutErrors = [];
export async function payOffline(page) {
	const { dialog, total } = await openPayment(page);
	await dialog.getByRole("button", { name: /^Exact cash/ }).click();
	const ok = page.getByText(/saved offline|created successfully/i).first();
	const err = page.getByRole("dialog").filter({ hasText: /^Error|preparedItems/ });
	await expect(ok.or(err).first()).toBeVisible();
	let error = null;
	if (await err.isVisible().catch(() => false)) {
		error = (await err.innerText()).replace(/\s+/g, " ");
		offlineCheckoutErrors.push(error);
	}
	await closeDialogs(page);
	return { total, error };
}
