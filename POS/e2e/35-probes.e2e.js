// Plan §4: the 12 scripted request probes, from a logged-in uit-cashier (or uit-manager) tab.
// Payloads are built from the POS's own captured update_invoice request.
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, api, clearCart, closeDialogs, errorsSince, expectSettingsClean, inv, nowStamp,
	openPos, record, restoreDoc, selectCustomer, server, setDoc, withPos,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

const SUBMIT = "pos_next.api.invoices.submit_invoice";
const UPDATE = "pos_next.api.invoices.update_invoice";
const msgOf = (r) => {
	const m = r.body?._server_messages;
	let t = "";
	try {
		t = JSON.parse(m || "[]").map((x) => JSON.parse(x).message).join(" | ");
	} catch {}
	return (t || r.body?.exception || "").replace(/<br>/g, " ").slice(0, 400);
};

/** Ring a cart, open payment to capture the update_invoice payload, close payment, clear. */
async function capture(page, customer, items) {
	await openPos(page);
	await clearCart(page);
	await selectCustomer(page, customer);
	for (const [code, qty] of items) await addItem(page, code, qty);
	const req = page.waitForRequest((r) => r.url().includes(UPDATE) && r.method() === "POST");
	await page.getByRole("button", { name: "Proceed to payment" }).click();
	const body = (await req).postDataJSON();
	await page.waitForTimeout(1500);
	await closeDialogs(page);
	await clearCart(page);
	const doc = typeof body.data === "string" ? JSON.parse(body.data) : body.data;
	delete doc.name;
	return doc;
}
const cashPay = (doc, amount) => ({ ...doc, payments: [{ mode_of_payment: "Cash", amount, default: 1 }] });

test("P-01 update_pos_settings: cashier cannot raise otp_max_sends_per_hour, manager can", async ({ page, browser }) => {
	await openPos(page);
	const r1 = await api(page, "pos_next.pos_next.doctype.pos_settings.pos_settings.update_pos_settings", { pos_profile: "UIT-FF Profile", settings: { otp_max_sends_per_hour: 100000 } });
	const v1 = server("get", { doctype: "POS Settings", name: POS_SETTINGS, fields: ["otp_max_sends_per_hour"] });
	const ctx = await browser.newContext({ storageState: AUTH.manager });
	const m = await ctx.newPage();
	await m.goto("/app");
	await m.waitForFunction(() => window.frappe?.csrf_token, null, { timeout: 60_000 });
	const r2 = await api(m, "pos_next.pos_next.doctype.pos_settings.pos_settings.update_pos_settings", { pos_profile: "UIT-FF Profile", settings: { otp_max_sends_per_hour: 100000 } });
	const v2 = server("get", { doctype: "POS Settings", name: POS_SETTINGS, fields: ["otp_max_sends_per_hour"] });
	await api(m, "pos_next.pos_next.doctype.pos_settings.pos_settings.update_pos_settings", { pos_profile: "UIT-FF Profile", settings: { otp_max_sends_per_hour: 5 } });
	await ctx.close();
	restoreDoc("pos_settings", POS_SETTINGS, ["otp_max_sends_per_hour"]);
	record("P-01", { cashier: [r1.status, v1], manager: [r2.status, v2] });
	expect(v1.otp_max_sends_per_hour).toBe(5);
	expect(v2.otp_max_sends_per_hour).toBe(100000);
});

test("P-02 unpaid update_invoice on UIT-NOFF with F&F markers is re-priced to list", async ({ page, browser }) => {
	const doc = await capture(page, "UIT-Verified", [["UIT-A", 1]]);
	const ctx = await browser.newContext({ storageState: AUTH.manager });
	const m = await ctx.newPage();
	await m.goto("/app");
	await m.waitForFunction(() => window.frappe?.csrf_token, null, { timeout: 60_000 });
	const d = { ...doc, pos_profile: "UIT-NOFF Profile", payments: [] };
	d.items = d.items.map((i) => ({ ...i, rate: 70, discount_percentage: 30, discount_amount: 30, posnext_discount_source: "friends_and_family", posnext_fnf_percentage: 30, posnext_fnf_discount_amount: 30 }));
	const r = await api(m, UPDATE, { data: d });
	await ctx.close();
	const name = r.body.message?.name;
	const saved = name ? inv(name) : null;
	record("P-02", { status: r.status, name, row: saved?.items[0], msg: msgOf(r) });
	expect(r.status).toBe(200);
	expect(Number(saved.items[0].rate)).toBe(100);
	expect(saved.items[0].posnext_discount_source || "").toBe("");
});

test("P-03/P-04 under S2: rate 85 refused (15% > 10%); rate 0 refused", async ({ page }) => {
	await withPos({ allow_user_to_edit_rate: 1, max_discount_allowed: 10 }, async () => {
		const doc = await capture(page, "UIT-Unverified", [["UIT-A", 1]]);
		const d85 = cashPay({ ...doc, items: doc.items.map((i) => ({ ...i, rate: 85, discount_percentage: 15, discount_amount: 15 })) }, 97.75);
		const r85 = await api(page, SUBMIT, { invoice: d85, data: {} });
		const d0 = cashPay({ ...doc, items: doc.items.map((i) => ({ ...i, rate: 0, discount_percentage: 100, discount_amount: 100 })) }, 0);
		const r0 = await api(page, SUBMIT, { invoice: d0, data: {} });
		record("P-03/04", { r85: [r85.status, msgOf(r85)], r0: [r0.status, msgOf(r0)] });
		expect(r85.status).toBe(417);
		expect(msgOf(r85)).toMatch(/reduced from 100(\.0)? to 85(\.0)? \(15(\.0)?%\), above the maximum allowed discount of 10(\.0)?%/);
		expect(r0.status).toBe(417);
		expect(msgOf(r0)).toMatch(/cannot be sold at zero price/);
	});
});

test("P-05 under S4: a manual header over 10% is refused", async ({ page }) => {
	await withPos({ allow_user_to_edit_additional_discount: 1, max_discount_allowed: 10 }, async () => {
		const doc = await capture(page, "UIT-Unverified", [["UIT-A", 2]]);
		const d = cashPay({ ...doc, discount_amount: 30, apply_discount_on: "Grand Total" }, 200);
		const r = await api(page, SUBMIT, { invoice: d, data: {} });
		record("P-05", { status: r.status, msg: msgOf(r) });
		expect(r.status).toBe(417);
		expect(msgOf(r)).toMatch(/above the maximum allowed invoice discount of 10(\.0)?%/);
	});
});

test("P-06/P-07 unbacked free rows are refused", async ({ page }) => {
	const trig = await capture(page, "UIT-Unverified", [["UIT-TRIG", 1]]);
	const gift = trig.items.find((i) => i.is_free_item);
	setDoc("Pricing Rule", "UIT-PR-FREE", { disable: 1 });
	let r6;
	try {
		r6 = await api(page, SUBMIT, { invoice: cashPay(trig, 115), data: {} });
	} finally {
		restoreDoc("rules", "UIT-PR-FREE", ["disable"]);
	}
	const a = await capture(page, "UIT-Unverified", [["UIT-A", 1]]);
	const extra = { ...a.items[0], item_code: "UIT-B", item_name: "UIT-B", is_free_item: 1, rate: 0, price_list_rate: 0, discount_percentage: 0, discount_amount: 0, pricing_rules: "" };
	delete extra.name;
	const r7 = await api(page, SUBMIT, { invoice: cashPay({ ...a, items: [...a.items, extra] }, 115), data: {} });
	const errs = errorsSince(since);
	record("P-06/07", { hadGift: !!gift, r6: [r6.status, msgOf(r6)], r7: [r7.status, msgOf(r7)], errors: errs });
	expect(r6.status).toBe(417);
	expect(msgOf(r6)).toMatch(/free item UIT-GIFT is not backed by an offer/);
	expect(r7.status).toBe(417);
	expect(msgOf(r7)).toMatch(/free item UIT-B is not backed by an offer/);
});

test("P-08 forged price_list_rate is overwritten with the server price", async ({ page }) => {
	const doc = await capture(page, "UIT-Unverified", [["UIT-A", 1]]);
	const d = cashPay({ ...doc, items: doc.items.map((i) => ({ ...i, price_list_rate: 1000, discount_percentage: 99, rate: 10, discount_amount: 990 })) }, 12);
	const r = await api(page, SUBMIT, { invoice: d, data: {} });
	const name = r.body.message?.name;
	const saved = name ? inv(name) : null;
	record("P-08", { status: r.status, msg: msgOf(r), name, row: saved?.items[0] });
	if (r.status === 200) expect(Number(saved.items[0].price_list_rate)).toBe(100);
	else expect(r.status).toBe(417);
});

test("P-09 forged F&F at 60%: unpaid re-stamped to 30%, paid refused", async ({ page }) => {
	const doc = await capture(page, "UIT-Verified", [["UIT-A", 1]]);
	const forged = { ...doc, items: doc.items.map((i) => ({ ...i, rate: 40, discount_percentage: 60, discount_amount: 60, posnext_discount_source: "friends_and_family", posnext_fnf_percentage: 60, posnext_fnf_discount_amount: 60 })) };
	const ra = await api(page, UPDATE, { data: { ...forged, payments: [] } });
	const sa = ra.body.message?.name ? inv(ra.body.message.name) : null;
	const rb = await api(page, SUBMIT, { invoice: cashPay(forged, 46), data: {} });
	record("P-09", { a: [ra.status, sa?.items[0].rate, sa?.items[0].posnext_fnf_percentage], b: [rb.status, msgOf(rb)] });
	expect(Number(sa.items[0].rate)).toBe(70);
	expect(rb.status).toBe(417);
	expect(msgOf(rb)).toMatch(/more than the .*30\.00 this customer is entitled to/);
});

test("P-10 forged replaced-discount envelope is ignored and not stored", async ({ page }) => {
	const doc = await capture(page, "UIT-Verified", [["UIT-A", 1]]);
	const env = JSON.stringify({ v: 2, source: "promotion", discount_percentage: 90, sig: "deadbeef" });
	const forged = { ...doc, items: doc.items.map((i) => ({ ...i, posnext_fnf_replaced_discount: env })) };
	const ru = await api(page, UPDATE, { data: { ...forged, payments: [] } });
	const su = ru.body.message?.name ? inv(ru.body.message.name) : null;
	const rp = await api(page, SUBMIT, { invoice: cashPay(forged, 80), data: {} });
	const sp = rp.body.message?.name ? inv(rp.body.message.name) : null;
	record("P-10", { unpaid: [ru.status, su?.items[0].rate, su?.items[0].posnext_fnf_replaced_discount], paid: [rp.status, sp?.items[0].rate, sp?.items[0].posnext_fnf_replaced_discount, msgOf(rp)] });
	expect(Number(su.items[0].rate)).toBe(70);
	expect(rp.status).toBeLessThan(500);
	if (sp) {
		expect(Number(sp.items[0].rate)).toBe(70);
		expect.soft(sp.items[0].posnext_fnf_replaced_discount || "", "forged envelope not stored on a paid submit (D-R2-13)").not.toContain("deadbeef");
	}
});

test("P-11 profile permission checks", async ({ page }) => {
	const doc = await capture(page, "UIT-Unverified", [["UIT-A", 1]]);
	const blank = await api(page, UPDATE, { data: { ...doc, pos_profile: "" } });
	const other = await api(page, UPDATE, { data: { ...doc, pos_profile: "Main POS Profile" } });
	const noff = { name: server("py", { code: `result=(frappe.get_all("Sales Invoice",filters={"docstatus":0,"pos_profile":"UIT-NOFF Profile"},pluck="name",limit=1) or [None])[0]` }) };
	const cross = await api(page, UPDATE, { data: { ...doc, name: noff?.name } });
	record("P-11", { blank: [blank.status, msgOf(blank)], other: [other.status, msgOf(other)], cross: [noff?.name, cross.status, msgOf(cross)] });
	expect(blank.status).toBe(403);
	expect(msgOf(blank)).toContain("POS Profile is required");
	expect(other.status).toBe(403);
	if (noff.name) {
		expect(cross.status).toBe(403);
		expect(msgOf(cross)).toContain("This document cannot be changed from this POS Profile.");
	}
});

test("P-12 a cashier cannot set custom_email_verified", async ({ page }) => {
	await openPos(page);
	const r1 = await api(page, "pos_next.api.customers.update_customer", { name: "UIT-Unverified", custom_email_verified: 1 });
	const r2 = await api(page, "frappe.client.set_value", { doctype: "Customer", name: "UIT-Unverified", fieldname: "custom_email_verified", value: 1 });
	const v = server("get", { doctype: "Customer", name: "UIT-Unverified", fields: ["custom_email_verified", "custom_verified_email"] });
	server("py", { code: `frappe.db.set_value("Customer","UIT-Unverified",{"custom_email_verified":0,"custom_verified_email":None},update_modified=False)\nresult=1` });
	record("P-12", { r1: r1.status, r2: r2.status, v });
	expect(v.custom_email_verified).toBe(0);
});
