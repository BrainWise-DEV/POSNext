// Plan §3.1–3.2: OTP panel, customer dialog, eligibility (U-02, U-03, U-04, U-05b, U-07, U-08, U-34c).
// OTP rows spend sends (5/h per customer + profile): each test resets its customer first.
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, addItem, api, breakdown, clearCart, closeDialogs, errorsSince, expectSettingsClean,
	mailCode, mailIds, nowStamp, openPos, record, resetCustomer, restoreDoc, row, selectCustomer, server,
	setDoc, shot, waitIdle,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(async ({ page }) => {
	since = nowStamp();
	await openPos(page);
	await clearCart(page);
});
test.afterEach(() => expectSettingsClean());

async function openEdit(page, customer) {
	await selectCustomer(page, customer);
	await page.getByRole("button", { name: "Edit customer details" }).click();
	await expect(page.getByTestId("customer-dialog-body")).toBeVisible();
}

/** Send a code; when the POS's cached customer email differs from the server (a reset made by the spec),
 * the panel offers "Save email & send code" instead of Verify. */
async function sendCode(page) {
	const send = page.getByTestId("send-code");
	if (await send.isEnabled().catch(() => false)) return send.click();
	return page.getByTestId("save-and-send").click();
}

test("U-02 (a) wrong code, (b) resend after cooldown, (c) expired code", async ({ page, request }) => {
	test.setTimeout(420_000);
	const email = "uit-otp2@uit-ff.example";
	resetCustomer("UIT-OTP2", email);
	const out = {};
	// (a)
	await openEdit(page, "UIT-OTP2");
	let before = await mailIds(request, email);
	await sendCode(page);
	const c1 = await mailCode(request, email, before);
	await page.getByTestId("otp-input").fill(c1 === "000000" ? "111111" : "000000");
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("error-msg")).toContainText("Wrong code (or email changed).");
	await expect(page.getByTestId("otp-input")).toBeVisible();
	out.a = await page.getByTestId("error-msg").innerText();
	// (b) wait out the cooldown (60 s), resend, first code fails, second verifies
	await expect(page.getByTestId("resend")).toBeEnabled({ timeout: 90_000 });
	before = await mailIds(request, email);
	await page.getByTestId("resend").click();
	const c2 = await mailCode(request, email, before);
	await page.getByTestId("otp-input").fill(c1);
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("error-msg")).toContainText("Wrong code");
	await page.getByTestId("otp-input").fill(c2);
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("verified-badge")).toContainText("Email verified");
	out.b = server("get", { doctype: "Customer", name: "UIT-OTP2", fields: ["custom_email_verified", "custom_verified_email"] });
	await closeDialogs(page);
	// (c) TTL 60, wait 70 s
	resetCustomer("UIT-OTP2", "uit-otp2b@uit-ff.example");
	setDoc("POS Settings", POS_SETTINGS, { otp_ttl_seconds: 60 });
	try {
		await page.reload();
		await openPos(page);
		await openEdit(page, "UIT-OTP2");
		before = await mailIds(request, "uit-otp2b@uit-ff.example");
		await sendCode(page);
		const c3 = await mailCode(request, "uit-otp2b@uit-ff.example", before);
		await page.waitForTimeout(70_000);
		// the panel may already have switched to its expired view (input hidden)
		if (await page.getByTestId("otp-input").isVisible().catch(() => false)) {
			await page.getByTestId("otp-input").fill(c3);
			await page.getByTestId("verify").click().catch(() => {});
		}
		await expect(page.getByTestId("expired-msg")).toContainText("Code expired. Request a new one.");
		out.c = server("get", { doctype: "Customer", name: "UIT-OTP2", fields: ["custom_email_verified"] });
		await closeDialogs(page);
	} finally {
		restoreDoc("pos_settings", POS_SETTINGS, ["otp_ttl_seconds"]);
	}
	record("U-02", { ...out, errors: errorsSince(since) });
	expect(out.b.custom_email_verified).toBe(1);
	expect(out.c.custom_email_verified).toBe(0);
});

test("U-03 (a) email change clears verification and F&F, (b) code for an old address fails", async ({ page, request }) => {
	// UIT-OTP1 verified first (as U-01 leaves it)
	server("py", { code: `frappe.db.set_value("Customer","UIT-OTP1",{"email_id":"uit-otp1@uit-ff.example","custom_email_verified":1,"custom_verified_email":"uit-otp1@uit-ff.example","custom_email_verified_via":"frappe_email"},update_modified=False)\nresult=1` });
	await page.reload();
	await openPos(page);
	await selectCustomer(page, "UIT-OTP1");
	await addItem(page, "UIT-A");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await page.getByRole("button", { name: "Edit customer details" }).click();
	const email = page.getByRole("textbox", { name: /email/i }).first();
	await email.fill("uit-otp1b@uit-ff.example");
	await page.getByTestId("customer-submit").click();
	await waitIdle(page, 2500);
	await closeDialogs(page);
	const a = server("get", { doctype: "Customer", name: "UIT-OTP1", fields: ["email_id", "custom_email_verified", "custom_verified_email"] });
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0, { timeout: 30_000 });
	const lineRightAfterSave = await row(page, "UIT-A").innerText();
	// "the cart loses F&F on refresh": the next re-price drops it
	await (await import("./lib/helpers.js")).setQty(page, "UIT-A", 2);
	await expect(row(page, "UIT-A")).not.toContainText("140.00");
	const logs = server("py", { code: `result=[l.log_type for l in frappe.get_all("Friends and Family Log",filters={"customer":"UIT-OTP1","creation":[">=","${since}"]},fields=["log_type"])]` });
	// (b) send to otp1b, change to otp1c, save, enter the old code
	await page.getByRole("button", { name: "Edit customer details" }).click();
	let before = await mailIds(request, "uit-otp1b@uit-ff.example");
	await page.getByTestId("send-code").click();
	const code = await mailCode(request, "uit-otp1b@uit-ff.example", before);
	const emailBox = page.getByRole("textbox", { name: /email/i }).first();
	let changeEmailUsed = false;
	if (await emailBox.isDisabled().catch(() => false)) {
		// the email is locked while a code is pending: "Change email" unlocks it
		await page.getByTestId("change-email").click();
		changeEmailUsed = true;
	}
	await emailBox.fill("uit-otp1c@uit-ff.example");
	const unsaved = await page.getByTestId("unsaved-msg").innerText().catch(() => "");
	await page.getByTestId("customer-submit").click();
	await waitIdle(page, 2000);
	let msg = "";
	if (await page.getByTestId("otp-input").isVisible().catch(() => false)) {
		await page.getByTestId("otp-input").fill(code);
		await page.getByTestId("verify").click();
		msg = await page.getByTestId("error-msg").innerText().catch(() => "");
	}
	const b = server("get", { doctype: "Customer", name: "UIT-OTP1", fields: ["email_id", "custom_email_verified"] });
	await closeDialogs(page);
	record("U-03", { changeEmailUsed, lineRightAfterSave: lineRightAfterSave.replace(/\s+/g, " "), a, logs, unsaved, msg, b, errors: errorsSince(since) });
	expect(a.custom_email_verified).toBe(0);
	expect(logs).toContain("Eligibility Removed");
	expect(b.custom_email_verified).toBe(0);
	await clearCart(page);
});

test("U-04 (a) double-click Send gives one send, (b) offline disables Send", async ({ page, context, request }) => {
	const email = "uit-otp3@uit-ff.example";
	resetCustomer("UIT-OTP3", email);
	await page.reload();
	await openPos(page);
	await openEdit(page, "UIT-OTP3");
	const before = await mailIds(request, email);
	await page.getByTestId("send-code").dblclick();
	await mailCode(request, email, before);
	await page.waitForTimeout(4000);
	const sent = (await mailIds(request, email)).filter((i) => !before.includes(i)).length;
	await closeDialogs(page);
	await context.setOffline(true);
	await page.waitForTimeout(3000);
	await page.getByRole("button", { name: "Edit customer details" }).click();
	await expect(page.getByTestId("offline-msg")).toContainText("Verification requires an internet connection.");
	const disabled = await page.getByTestId("send-code").isDisabled().catch(() => "absent");
	await context.setOffline(false);
	await closeDialogs(page);
	record("U-04", { sent, disabled, errors: errorsSince(since) });
	expect(sent).toBe(1);
	expect(disabled === true || disabled === "absent").toBeTruthy();
});

test("U-05b customer dialog as a cashier: lists, country picker, Escape, save mobile", async ({ page }) => {
	server("py", { code: `frappe.db.set_value("Customer","UIT-OTP2","mobile_no","",update_modified=False)\nresult=1` });
	await openEdit(page, "UIT-OTP2");
	const body = page.getByTestId("customer-dialog-body");
	await page.getByTestId("country-code-button").click();
	const picker = page.getByTestId("country-picker");
	await expect(picker).toBeVisible();
	const countries = await picker.getByRole("option").count().catch(() => 0) || (await picker.locator("li,button").count());
	await page.keyboard.press("Escape");
	await expect(picker).toBeHidden();
	await expect(body).toBeVisible();
	const groupOk = await body.innerText();
	const mobile = page.getByRole("textbox", { name: /mobile|phone/i }).first();
	await mobile.fill("1000000002");
	await page.getByTestId("customer-submit").click();
	const toast = await page.getByText(/updated/i).first().innerText({ timeout: 20_000 }).catch(() => "");
	await closeDialogs(page);
	const saved = server("get", { doctype: "Customer", name: "UIT-OTP2", fields: ["mobile_no"] });
	// Walk-in dummy country
	await selectCustomer(page, "UIT-Walk-in");
	await page.getByRole("button", { name: "Edit customer details" }).click();
	await shot(page, "U-05b-walkin");
	const walkinFlag = await page.getByTestId("country-code-button").innerText().catch(() => "");
	await closeDialogs(page);
	record("U-05b", { countries, toast, saved, walkinFlag, hasGroup: /Individual|Commercial/.test(groupOk), errors: errorsSince(since) });
	expect(countries).toBeGreaterThan(200);
	expect(saved.mobile_no).toContain("1000000002");
});

test("U-07 not eligible, then switch to F&F and back", async ({ page }) => {
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A");
	await expect(page.getByTestId("fnf-cart-messages")).toContainText("No Friends & Family: verify the email of customer UIT-Unverified (OTP) first");
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
	await selectCustomer(page, "UIT-Verified");
	await expect(breakdown(page, "UIT-A")).toContainText("70.00");
	await expect(page.getByTestId("fnf-customer-badge")).toBeVisible();
	await selectCustomer(page, "UIT-Unverified");
	await expect(page.getByTestId("fnf-customer-badge")).toHaveCount(0);
	await expect(row(page, "UIT-A")).not.toContainText("70.00");
	const e = await api(page, "posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility", { customer: "UIT-Unverified", pos_profile: "UIT-FF Profile" });
	record("U-07", { elig: e.body.message });
	expect(e.body.message.reason).toBe("email_not_verified");
	expect(e.body.message.ff_member).toBe(true);
	await clearCart(page);
});

test("U-08 profile without F&F (UIT-NOFF): eligibility says profile_not_allowed", async ({ page }) => {
	const e = await api(page, "posnext_promotions.api.friends_and_family.check_friends_and_family_eligibility", { customer: "UIT-Verified", pos_profile: "UIT-NOFF Profile" });
	record("U-08", { elig: e.body.message, status: e.status });
	expect(e.body.message?.eligible).toBe(false);
	expect(e.body.message?.reason).toBe("profile_not_allowed");
});

test("U-34c Arabic-Indic digits are accepted as an OTP", async ({ page, request }) => {
	const email = "uit-otp3@uit-ff.example";
	resetCustomer("UIT-OTP3", email);
	await page.reload();
	await openPos(page);
	await openEdit(page, "UIT-OTP3");
	await expect(page.getByTestId("resend").or(page.getByTestId("send-code")).first()).toBeVisible();
	const before = await mailIds(request, email);
	const send = page.getByTestId("send-code");
	if (await send.isVisible().catch(() => false)) await send.click();
	else await page.getByTestId("resend").click({ timeout: 90_000 });
	const code = await mailCode(request, email, before);
	const arabic = code.replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[Number(d)]);
	await page.getByTestId("otp-input").pressSequentially(arabic);
	const shown = await page.getByTestId("otp-input").inputValue();
	await page.getByTestId("verify").click();
	await expect(page.getByTestId("verified-badge")).toContainText("Email verified");
	await closeDialogs(page);
	record("U-34c", { shown, errors: errorsSince(since) });
	expect(shown).toBe(code);
});
