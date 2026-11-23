// Settings matrix (run 3): each setting that changes POS behaviour, changed ONE at a time, driven in the
// browser, server checked, restored at once (finally) and diffed against the snapshot after each row.
// Evidence lines carry {setting, value, expected, observed} for the matrix table.
import { expect, test } from "@playwright/test";
import {
	AUTH, POS_SETTINGS, PROFILE, addItem, api, applyCoupon, breakdown, clearCart, closeDialogs, coupons,
	errorsSince, expectSaleOk, expectSettingsClean, ffReset, freeRows, nowStamp, openPayment, openPos, payExact,
	record, restoreDoc, row, SNAPSHOT, selectCustomer, sell, server, setDoc, setQty, shot, successDialog, waitIdle,
} from "./lib/helpers.js";

test.use({ storageState: AUTH.cashier });
let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

const SNAP = { ff: ["ff", "Friends and Family Settings"], pos: ["pos_settings", POS_SETTINGS], profile: ["profiles", PROFILE] };

/** change: [kind, name, values]; kind = ff | pos | profile | coupon | rule | fftable */
function apply(change) {
	const [kind, name, values] = change;
	if (kind === "ff") return server("ff_set", { values });
	if (kind === "fftable") return server("ff_table", { field: name, rows: values, values: change[3] || null });
	const dt = { pos: "POS Settings", profile: "POS Profile", coupon: "POS Coupon", rule: "Pricing Rule" }[kind];
	return setDoc(dt, name, values);
}
async function fresh(page) {
	await openPos(page);
	await clearCart(page);
}
async function ring(page, customer, items, coupon) {
	await selectCustomer(page, customer);
	for (const [code, qty] of items) {
		await addItem(page, code);
		if (qty > 1) await setQty(page, code, qty);
	}
	if (coupon) return applyCoupon(page, coupon);
	return "";
}
const rowsOf = (inv) => inv.items.map((i) => `${i.item_code} q${i.qty} @${i.rate}${i.is_free_item ? " FREE" : ""}${i.posnext_discount_source ? ` ${i.posnext_discount_source}` : ""}${i.posnext_coupon_code ? ` cpn ${i.posnext_coupon_code}` : ""}${i.pricing_rules ? ` [${i.pricing_rules}]` : ""}`).join("; ");
const rate = (inv, code) => Number(inv.items.find((i) => i.item_code === code && !i.is_free_item)?.rate);
const src = (inv, code) => inv.items.find((i) => i.item_code === code && !i.is_free_item)?.posnext_discount_source || "";

const ROWS = [
	// ---- F&F Settings
	{ id: "S-FF-08", setting: "F&F discount_percentage", value: "15 (from 30)", change: ["ff", null, { discount_percentage: 15 }], expected: "UIT-A 85 (F&F 15%); UIT-B keeps its 20% rule (160)",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1], ["UIT-B", 1]]); const badge = await page.getByTestId("fnf-customer-badge").innerText(); const s = await sell(page); return { s, badge, ok: rate(s.invoice, "UIT-A") === 85 && rate(s.invoice, "UIT-B") === 160 && /15%/.test(badge) }; } },
	{ id: "S-FF-07", setting: "F&F start_date", value: "tomorrow", change: ["ff", null, { start_date: "__TOMORROW__" }], expected: "program inactive: UIT-A at 100, no badge",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const badge = await page.getByTestId("fnf-customer-badge").count(); const s = await sell(page); return { s, badge, ok: rate(s.invoice, "UIT-A") === 100 && badge === 0 }; } },
	{ id: "S-FF-07b", setting: "F&F end_date", value: "yesterday", change: ["ff", null, { end_date: "__YESTERDAY__" }], expected: "program inactive: UIT-A at 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 100 }; } },
	{ id: "S-FF-07c", setting: "F&F end_date", value: "today (inclusive)", change: ["ff", null, { end_date: "__TODAY__" }], expected: "active: UIT-A 70",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 }; } },
	{ id: "S-FF-06", setting: "F&F approved_domains", value: "[other-uit.example] only", change: ["fftable", "approved_domains", [{ email_domain: "other-uit.example", enabled: 1 }]], expected: "UIT-Verified (uit-ff.example) not eligible: 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const msgs = await page.getByTestId("fnf-cart-messages").innerText().catch(() => ""); const s = await sell(page); return { s, msgs, ok: rate(s.invoice, "UIT-A") === 100 }; } },
	{ id: "S-FF-09", setting: "F&F discount_scope Item Code + applicable_items", value: "[UIT-A]", change: ["fftable", "applicable_items", [{ item_code: "UIT-A" }], { discount_scope: "Item Code" }], expected: "UIT-A 70, UIT-A2 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1], ["UIT-A2", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 && rate(s.invoice, "UIT-A2") === 100 }; } },
	{ id: "S-FF-10", setting: "F&F discount_scope Item Group + applicable_item_groups", value: "[UIT-Group]", change: ["fftable", "applicable_item_groups", [{ item_group: "UIT-Group" }], { discount_scope: "Item Group" }], expected: "UIT-A 70 (in scope)",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 }; } },
	{ id: "S-FF-11", setting: "F&F discount_scope Brand + applicable_brands", value: "[UIT-Brand]", change: ["fftable", "applicable_brands", [{ brand: "UIT-Brand" }], { discount_scope: "Brand" }], expected: "UIT-A 70",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 }; } },
	{ id: "S-FF-12", setting: "F&F excluded_item_groups", value: "[UIT-Group]", change: ["fftable", "excluded_item_groups", [{ item_group: "UIT-Group" }]], expected: "no UIT item gets F&F: UIT-A 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 100 }; } },
	{ id: "S-FF-13", setting: "F&F excluded_brands", value: "[UIT-Brand]", change: ["fftable", "excluded_brands", [{ brand: "UIT-Brand" }]], expected: "UIT-A 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 100 }; } },
	{ id: "S-FF-14", setting: "F&F excluded_items", value: "[] (from [UIT-EXCL])", change: ["fftable", "excluded_items", []], expected: "UIT-EXCL gets F&F: 56",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-EXCL", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-EXCL") === 56 }; } },
	{ id: "S-FF-05", setting: "F&F eligibility_basis (hidden)", value: "Customer Flag", change: ["ff", null, { eligibility_basis: "Customer Flag" }], expected: "no effect (eligibility is email-domain only): UIT-A 70",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 }; } },
	{ id: "S-FF-16", setting: "F&F unclassified_promotion_policy", value: "Block F&F on line", change: ["ff", null, { unclassified_promotion_policy: "Block F&F on line" }], expected: "no effect on classified rules: UIT-B F&F 140 (20% rule is classified 'price')",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 140 }; } },
	{ id: "S-FF-17", setting: "F&F replaced_discount_snapshot_hours", value: "1 (from seeded)", change: ["ff", null, { replaced_discount_snapshot_hours: 1 }], expected: "no visible POS effect; UIT-B F&F 140",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-B", 1]]); const s = await sell(page); return { s, env: s.invoice.items[0].posnext_fnf_replaced_discount, ok: rate(s.invoice, "UIT-B") === 140 }; } },
	{ id: "S-FF-02", setting: "F&F max_discount_per_order", value: "90 (exactly at cap: UIT-A + UIT-B = 30 + 60)", change: ["ff", null, { max_discount_per_order: 90 }], expected: "30 + 60 = 90, no capped message",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1], ["UIT-B", 1]]); const msgs = await page.getByTestId("fnf-cart-messages").innerText(); const s = await sell(page); const f = s.invoice.items.reduce((a, i) => a + i.posnext_fnf_discount_amount, 0); return { s, msgs, f, ok: Math.abs(f - 90) < 0.01 && !/reduced by the discount limit/.test(msgs) }; } },
	// ---- POS Settings
	{ id: "S-POS-05", setting: "POS Settings tax_inclusive", value: "1", change: ["pos", POS_SETTINGS, { tax_inclusive: 1 }], expected: "prices include tax; UIT-A F&F 70 + UIT-B F&F 140 = 210 collected",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1], ["UIT-B", 1]]); const s = await sell(page); return { s, ok: Math.abs(s.invoice.due - 210) < 0.01 }; } },
	{ id: "S-POS-06", setting: "POS Settings enable_customer_email_verification", value: "0", change: ["pos", POS_SETTINGS, { enable_customer_email_verification: 0 }], expected: "F&F still needs a verified email; the panel stays for members",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1]]); await page.getByRole("button", { name: "Edit customer details" }).click(); await expect(page.getByTestId("customer-dialog-body")).toBeVisible(); await page.waitForTimeout(2000); const panel = await page.getByTestId("email-verification-panel").count(); const dialogText = (await page.getByTestId("customer-dialog-body").innerText()).slice(0, 300); await closeDialogs(page); const s = await sell(page); return { s, panel, dialogText, ok: rate(s.invoice, "UIT-A") === 100 && panel > 0 }; } },
	{ id: "S-POS-07", setting: "POS Settings default_coupon_promotion_conflict", value: "Add on top (from Skip the line)", change: ["pos", POS_SETTINGS, { default_coupon_promotion_conflict: "Add on top" }], expected: "only the default for coupons created in the POS; UIT-L10 (blank) on UIT-C keeps 'Skip the line': 30",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-C", 1]], "UIT-L10"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-C") === 30 }; } },
	{ id: "S-POS-08", setting: "POS Settings allow_user_to_edit_item_discount", value: "0", change: ["pos", POS_SETTINGS, { allow_user_to_edit_item_discount: 0 }], expected: "engine discounts still sell (F&F 70, rule 160)",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1], ["UIT-C", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 70 && rate(s.invoice, "UIT-C") === 30 }; } },
	{ id: "S-POS-09", setting: "POS Settings allow_credit_sale", value: "1", change: ["pos", POS_SETTINGS, { allow_credit_sale: 1 }], expected: "Pay on Account offered; F&F credit sale saved unpaid at 80",
		run: async (page) => {
			await ring(page, "UIT-Verified", [["UIT-A", 1]]);
			const { dialog } = await openPayment(page);
			const btn = dialog.getByRole("button", { name: /Pay on Account|on account|credit/i }).first();
			const offered = await btn.isVisible().catch(() => false);
			let s = null;
			if (offered) {
				const done = page.waitForResponse((r) => r.url().includes("submit_invoice") && r.request().method() === "POST", { timeout: 30_000 }).catch(() => null);
				await btn.click(); // first click arms the confirmation (creditConfirming)
				await page.waitForTimeout(800);
				await dialog.getByRole("button", { name: /Pay on Account|on account|credit|Confirm/i }).first().click().catch(() => {});
				const res = await done;
				const name = res ? (await res.json()).message?.name : null;
				await closeDialogs(page);
				s = name ? { name, invoice: server("invoice", { name }) } : null;
			} else await closeDialogs(page);
			return { s, offered, sale: !!s, ok: offered && s && rate(s.invoice, "UIT-A") === 70 && s.invoice.si.outstanding_amount > 0, noSaleCheck: true };
		} },
	{ id: "S-POS-14", setting: "POS Settings allow_return", value: "0 (seeded)", change: ["pos", POS_SETTINGS, { allow_return: 0 }], expected: "Return Invoice not available / refused",
		run: async (page) => { const btn = page.getByRole("button", { name: "Return Invoice" }); const vis = await btn.isVisible().catch(() => false); let txt = ""; if (vis) { await btn.click(); await page.waitForTimeout(1500); txt = (await page.locator("body").innerText()).match(/[^\n]*(not allowed|disabled|permission)[^\n]*/i)?.[0] || ""; await closeDialogs(page); } return { vis, txt, ok: !vis || !!txt, noSaleCheck: true }; } },
	{ id: "S-POS-16", setting: "POS Settings create_only_sales_order", value: "1", change: ["pos", POS_SETTINGS, { create_only_sales_order: 1, allow_sales_order: 1 }], expected: "cart is a Sales Order; F&F stripped (invoices only)",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const t = await row(page, "UIT-A").innerText(); const body = await page.locator("body").innerText(); return { line: t, ok: !/70\.00/.test(t), order: /Order/.test(body), noSaleCheck: true }; } },
	// ---- POS Profile
	{ id: "S-PROF-01", setting: "POS Profile disable_rounded_total", value: "1", change: ["profile", PROFILE, { disable_rounded_total: 1 }], expected: "no rounding: collect grand 80.50",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const s = await sell(page); return { s, ok: Math.abs(s.invoice.collected - 80.5) < 0.01 }; } },
	{ id: "S-PROF-02", setting: "POS Profile allow_friends_family", value: "0", change: ["profile", PROFILE, { allow_friends_family: 0 }], expected: "profile_not_allowed: no badge, UIT-A 100",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-A", 1]]); const badge = await page.getByTestId("fnf-customer-badge").count(); const s = await sell(page); return { s, badge, ok: rate(s.invoice, "UIT-A") === 100 && badge === 0 }; } },
	{ id: "S-PROF-03", setting: "POS Profile ignore_pricing_rule", value: "1", change: ["profile", PROFILE, { ignore_pricing_rule: 1 }], expected: "pricing rules ignored: UIT-C 50, no BXGY free row; F&F decides alone (UIT-C 35)",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-C", 1], ["UIT-BXGY", 2]]); const free = await freeRows(page).count(); const s = await sell(page); return { s, free, ok: free === 0 && s.invoice.items.every((i) => !i.is_free_item) }; } },
	{ id: "S-PROF-04", setting: "POS Profile apply_discount_on", value: "Net Total (from Grand Total)", change: ["profile", PROFILE, { apply_discount_on: "Net Total" }], expected: "order coupon UIT-O100 on the net total: tax on 180 (27.00), collected 207",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 2], ["UIT-EXCL", 1]], "UIT-O100"); const s = await sell(page); return { s, tax: s.invoice.si.total_taxes_and_charges, ok: Math.abs(s.invoice.si.total_taxes_and_charges - 27) < 0.01 }; } },
	// ---- POS Coupon
	{ id: "S-CPN-02", setting: "POS Coupon apply_scope", value: "Item Group UIT-Group (UIT-SI20)", change: ["coupon", "UIT-SI20", { apply_scope: "Item Group", applicable_item_group: "UIT-Group" }], expected: "UIT-A and UIT-A2 both 80",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1], ["UIT-A2", 1]], "UIT-SI20"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 80 && rate(s.invoice, "UIT-A2") === 80 }; } },
	{ id: "S-CPN-05", setting: "POS Coupon exclude_already_discounted_items", value: "0 (UIT-L10)", change: ["coupon", "UIT-L10", { exclude_already_discounted_items: 0 }], expected: "no effect (matrix rules mandatory): UIT-B keeps 20% (160)",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1], ["UIT-B", 1]], "UIT-L10"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 160 && rate(s.invoice, "UIT-A") === 90 }; } },
	{ id: "S-CPN-07", setting: "POS Coupon max_amount", value: "5 (UIT-L50, no promotion on the line)", change: ["coupon", "UIT-L50", { max_amount: 5 }], expected: "UIT-A 95",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1]], "UIT-L50"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 95 }; } },
	{ id: "S-CPN-08", setting: "POS Coupon min_amount", value: "1000 (UIT-L20, cart 300)", change: ["coupon", "UIT-L20", { min_amount: 1000 }], expected: "refused 'Minimum eligible amount … 1,000.00'",
		run: async (page) => { const t = await ring(page, "UIT-Unverified", [["UIT-A", 1], ["UIT-B", 1]], "UIT-L20"); const m = t.match(/[^\n]*Minimum[^\n]*/)?.[0] || ""; await clearCart(page); return { msg: m, ok: /1,000\.00/.test(m), noSaleCheck: true }; } },
	{ id: "S-CPN-09", setting: "POS Coupon valid_upto", value: "yesterday (UIT-L20)", change: ["coupon", "UIT-L20", { valid_upto: "__YESTERDAY__" }], expected: "refused: expired",
		run: async (page) => { const t = await ring(page, "UIT-Unverified", [["UIT-A", 1]], "UIT-L20"); const m = t.match(/[^\n]*expired[^\n]*/i)?.[0] || ""; await clearCart(page); return { msg: m, ok: !!m, noSaleCheck: true }; } },
	{ id: "S-CPN-10", setting: "POS Coupon disabled", value: "1 (UIT-L20)", change: ["coupon", "UIT-L20", { disabled: 1 }], expected: "refused: disabled",
		run: async (page) => { const t = await ring(page, "UIT-Unverified", [["UIT-A", 1]], "UIT-L20"); const m = t.match(/[^\n]*disabled[^\n]*/i)?.[0] || ""; await clearCart(page); return { msg: m, ok: !!m, noSaleCheck: true }; } },
	{ id: "S-CPN-11", setting: "POS Coupon maximum_use_per_customer", value: "1 (UIT-L20)", change: ["coupon", "UIT-L20", { maximum_use_per_customer: 1 }], expected: "first sale with it OK, the second for the same customer refused",
		run: async (page) => { await ring(page, "UIT-Walk-in", [["UIT-A", 1]], "UIT-L20"); const s = await sell(page); const t = await ring(page, "UIT-Walk-in", [["UIT-A", 1]], "UIT-L20"); const applied = /80\.00/.test(await row(page, "UIT-A").innerText()); await clearCart(page); return { s, second: (t.match(/[^\n]*(limit|already|maximum)[^\n]*/i) || [""])[0], applied, ok: rate(s.invoice, "UIT-A") === 80 && !applied }; } },
	{ id: "S-CPN-12", setting: "POS Coupon one_use", value: "1 (UIT-L20)", change: ["coupon", "UIT-L20", { one_use: 1 }], expected: "after one sale with it, it is refused",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1]], "UIT-L20"); const s = await sell(page); const t = await ring(page, "UIT-Verified", [["UIT-EXCL", 1]], "UIT-L20"); const applied = /64\.00/.test(await row(page, "UIT-EXCL").innerText()); await clearCart(page); return { s, second: (t.match(/[^\n]*(used|limit)[^\n]*/i) || [""])[0], applied, ok: !applied }; } },
	{ id: "S-CPN-13", setting: "POS Coupon discount_type", value: "Amount 10 (UIT-L10)", change: ["coupon", "UIT-L10", { discount_type: "Amount", discount_amount: 10 }], expected: "UIT-A 90 (10 off)",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 1]], "UIT-L10"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 90 }; } },
	{ id: "S-CPN-14", setting: "POS Coupon apply_on", value: "Net Total (UIT-O40)", change: ["coupon", "UIT-O40", { apply_on: "Net Total" }], expected: "per-line order coupon on the net: UIT-A x2 at 80",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-A", 2]], "UIT-O40"); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-A") === 80 }; } },
	// ---- Pricing Rule
	{ id: "S-RULE-02", setting: "Pricing Rule for_price_list", value: "Standard Selling (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { for_price_list: "Standard Selling" }], expected: "rule not offered: UIT-B 200",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 200 }; } },
	{ id: "S-RULE-03", setting: "Pricing Rule valid_from", value: "tomorrow (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { valid_from: "__TOMORROW__" }], expected: "UIT-B 200",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 200 }; } },
	{ id: "S-RULE-04", setting: "Pricing Rule pos_only", value: "0 (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { pos_only: 0 }], expected: "still applies in the POS: 160",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 160 }; } },
	{ id: "S-RULE-08", setting: "Pricing Rule pos_active_to_time (end boundary on valid_upto)", value: "valid_upto today, to_time 1 h ago (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { valid_upto: "__TODAY__", pos_active_to_time: "__HOURS_AGO_1__" }], expected: "the promotion ended an hour ago: UIT-B 200",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 200 }; } },
	{ id: "S-RULE-08b", setting: "Pricing Rule pos_active_from_time (start boundary on valid_from)", value: "valid_from today, from_time in 1 h (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { valid_from: "__TODAY__", pos_active_from_time: "__HOURS_AHEAD_1__" }], expected: "the promotion starts in an hour: UIT-B 200",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 200 }; } },
	{ id: "S-RULE-08c", setting: "Pricing Rule pos_active_from_time (start boundary on valid_from)", value: "valid_from today, from_time 1 h ago (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { valid_from: "__TODAY__", pos_active_from_time: "__HOURS_AGO_1__" }], expected: "started: UIT-B 160",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-B", 1]]); const s = await sell(page); return { s, ok: rate(s.invoice, "UIT-B") === 160 }; } },
	{ id: "S-RULE-10", setting: "Pricing Rule promotion_type", value: "Auto Discount (UIT-PR-B20)", change: ["rule", "UIT-PR-B20", { promotion_type: "Auto Discount" }], expected: "F&F customer: F&F 30% beats 20% (140) — or the rule blocks; recorded",
		run: async (page) => { await ring(page, "UIT-Verified", [["UIT-B", 1]]); const line = await row(page, "UIT-B").innerText(); const s = await sell(page); return { s, line, ok: [140, 160].includes(rate(s.invoice, "UIT-B")) && !s.changed }; } },
	{ id: "S-RULE-12", setting: "Pricing Rule gwp_paid_qty_basis", value: "Min Price (UIT-PR-GWP, from Max Price)", change: ["rule", "UIT-PR-GWP", { gwp_paid_qty_basis: "Min Price" }], expected: "the GWP free row follows the basis; the sale completes",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-GWP1", 1], ["UIT-GWP2", 1]]); const free = await freeRows(page).count(); const s = await sell(page); return { s, free, ok: s.invoice.items.some((i) => i.is_free_item) }; } },
	{ id: "S-RULE-13", setting: "Pricing Rule max_accumulated_discount_percentage", value: "45 (UIT-PR-C40) + UIT-L10 Add on top", change: ["rule", "UIT-PR-C40", { max_accumulated_discount_percentage: 45 }], pre: ["coupon", "UIT-L10", { promotion_conflict: "Add on top" }], expected: "stack 40% + 10% of the rest = 46% capped to 45%: rate 27.50",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-C", 1]], "UIT-L10"); const s = await sell(page); return { s, ok: Math.abs(rate(s.invoice, "UIT-C") - 27.5) < 0.01 }; } },
	{ id: "S-RULE-14", setting: "Pricing Rule priority", value: "CART5 = 5, CART-GIFT = 1", change: ["rule", "UIT-PR-CART5", { has_priority: 1, priority: "5" }], pre: ["rule", "UIT-PR-CART-GIFT", { has_priority: 1, priority: "1" }], expected: "a price and a product transaction rule both apply (header 5% + gift)",
		run: async (page) => { await ring(page, "UIT-Unverified", [["UIT-EXCL", 13]]); const s = await sell(page); return { s, ok: s.invoice.si.discount_amount > 0 && s.invoice.items.some((i) => i.is_free_item) }; } },
];

function resolveDates(values) {
	const d = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
	const t = (h) => {
		const x = new Date(Date.now() + h * 3600000);
		return `${String(x.getHours()).padStart(2, "0")}:${String(x.getMinutes()).padStart(2, "0")}:00`;
	};
	const map = { __TOMORROW__: d(1), __YESTERDAY__: d(-1), __TODAY__: d(0), __HOURS_AGO_3__: t(-3), __HOURS_AGO_1__: t(-1), __HOURS_AHEAD_1__: t(1) };
	return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, map[v] ?? v]));
}

for (const r of ROWS) {
	test(`${r.id} ${r.setting} = ${r.value}`, async ({ page }) => {
		const changes = [r.pre, r.change].filter(Boolean).map(([k, n, v, x]) => [k, n, Array.isArray(v) ? v : resolveDates(v), x]);
		try {
			for (const c of changes) apply(c);
			await fresh(page);
			const out = await r.run(page);
			const s = out.s;
			const observed = { ...out, s: undefined, invoice: s?.name, rows: s ? rowsOf(s.invoice) : undefined, due: s?.invoice.due, collected: s?.invoice.collected, changed: s?.changed };
			record(r.id, { matrix: true, setting: r.setting, value: r.value, expected: r.expected, observed, pass: !!out.ok, errors: errorsSince(since) });
			if (s && !out.noSaleCheck) expectSaleOk(s.invoice, s.total);
			expect(out.ok, `${r.id}: ${JSON.stringify(observed).slice(0, 600)}`).toBeTruthy();
		} finally {
			await clearCart(page).catch(() => {});
			for (const c of changes.reverse()) {
				const [kind, name, values] = c;
				if (kind === "ff" || kind === "fftable") {
					ffReset();
					server("restore", { path: SNAPSHOT, section: "ff", docname: "Friends and Family Settings" });
				} else restoreDoc({ pos: "pos_settings", profile: "profiles", coupon: "coupons", rule: "rules" }[kind], name, Object.keys(values));
			}
		}
	});
}
