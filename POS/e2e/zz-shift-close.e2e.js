// Runs last (file order): shift close warns about open drafts and lists them (G4, run-2 D-R2-18),
// then closes uit-cashier's shift and checks the closing totals on the server.
import { expect, test } from "@playwright/test";
import { AUTH, addItem, clearCart, closeDialogs, errorsSince, nowStamp, openPos, record, selectCustomer, server, shot, waitIdle } from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });

test("E-26 / D-R2-18 shift close warns about open drafts, lists them, and closes", async ({ page }) => {
	const since = nowStamp();
	await openPos(page);
	await clearCart(page);
	// make sure there is at least one open draft on this shift
	await selectCustomer(page, "UIT-Unverified");
	await addItem(page, "UIT-A2");
	await page.getByRole("button", { name: "Hold", exact: true }).click();
	await waitIdle(page);
	const drafts = server("py", {
		code: `
sh = frappe.get_all("POS Opening Shift", filters={"user": "uit-cashier@uit-pos.example", "status": "Open", "docstatus": 1}, pluck="name")
result = {"shift": sh, "drafts": frappe.get_all("Sales Invoice", filters={"docstatus": 0, "posa_pos_opening_shift": ["in", sh]}, pluck="name")}`,
	});
	await page.getByRole("button", { name: "Close Shift" }).click();
	const dlg = page.getByRole("dialog").last();
	await expect(dlg).toBeVisible();
	const warn = dlg.getByTestId("shift-open-drafts");
	await expect(warn).toBeVisible({ timeout: 30_000 });
	const warnText = await warn.innerText();
	await shot(page, "E-26-shift-close");
	const dlgText = await dlg.innerText();
	// count each payment mode at its own expected amount (the closing dialog lists one row per mode)
	const inputs = dlg.getByRole("spinbutton");
	const n = await inputs.count();
	for (let i = 0; i < n; i++) {
		const input = inputs.nth(i);
		const rowText = await input.locator("xpath=ancestor::*[contains(., 'Expected')][1]").innerText().catch(() => "");
		const m = rowText.match(/Expected[^\d-]*(-?[\d,]+\.\d\d)/);
		const v = await input.inputValue();
		if ((!v || v === "0") && m) await input.fill(m[1].replace(/,/g, ""));
	}
	const closeBtn = dlg.getByRole("button", { name: /Close Shift|Submit|Confirm/ }).last();
	await closeBtn.click();
	await page.waitForTimeout(5000);
	const confirm = page.getByRole("dialog").getByRole("button", { name: /Close Shift|Confirm|Yes/ }).last();
	if (await confirm.isVisible().catch(() => false)) await confirm.click();
	await page.waitForTimeout(5000);
	const after = await page.locator("body").innerText();
	await shot(page, "E-26-after-close");
	const closing = server("py", {
		code: `
cs = frappe.get_all("POS Closing Shift", filters={"pos_opening_shift": ["in", ${JSON.stringify(drafts.shift)}]}, fields=["name","docstatus","grand_total","net_total"])
pays = []
if cs:
    pays = frappe.get_all("POS Closing Shift Detail", filters={"parent": cs[0].name}, fields=["mode_of_payment","expected_amount","closing_amount","difference"])
result = {"closing": cs, "payments": pays}`,
	});
	record("E-26", { drafts, warnText, closing, after: after.slice(0, 400), errors: errorsSince(since) });
	expect(warnText).toMatch(/draft/i);
	for (const d of drafts.drafts.slice(0, 3)) expect.soft(warnText, "lists the drafts").toContain(d);
	expect(closing.closing.length).toBeGreaterThan(0);
});
