// Plan §3.8: two-tab races (U-38 b, c) and the same address verified twice (U-39).
import { expect, test } from "@playwright/test";
import {
	AUTH, addItem, applyCoupon, breakdown, clearCart, closeDialogs, coupons, errorsSince, expectSaleOk,
	expectSettingsClean, ffReset, ffSet, inv, mailCode, mailIds, nowStamp, openPayment, openPos, payExact, record,
	resetCustomer, restoreDoc, selectCustomer, server, setDoc, setQty, shot,
} from "./lib/helpers.js";

let since;
test.beforeEach(() => {
	since = nowStamp();
});
test.afterEach(() => expectSettingsClean());

const capUsed = () => server("py", { code: `result=frappe.db.get_value("Friends and Family Usage Total",{"customer":"UIT-Cap","period_key":frappe.utils.nowdate()[:7]},"base_amount") or 0` });

async function twoTabs(browser, fn) {
	const ctxA = await browser.newContext({ storageState: AUTH.cashier });
	const ctxB = await browser.newContext({ storageState: AUTH.cashier2 });
	try {
		return await fn(await ctxA.newPage(), await ctxB.newPage());
	} finally {
		await ctxA.close();
		await ctxB.close();
	}
}

test("U-38 (b) Block submit: B is refused when Payment opens, before any payment", async ({ browser }) => {
	const used = capUsed();
	ffSet({ max_discount_per_customer_month: used + 40, on_cap_breach_at_submit: "Block submit" });
	try {
		await twoTabs(browser, async (a, b) => {
			const prep = async (p) => {
				await openPos(p);
				await clearCart(p);
				await selectCustomer(p, "UIT-Cap");
				await addItem(p, "UIT-A");
				await setQty(p, "UIT-A", 2);
				await expect(breakdown(p, "UIT-A")).toContainText("160.00");
			};
			await prep(a);
			await prep(b);
			const pa = await openPayment(a);
			const ra = await payExact(a, pa.dialog);
			await closeDialogs(a);
			await b.getByRole("button", { name: "Proceed to payment" }).click();
			await b.waitForTimeout(4000);
			const bText = await b.locator("body").innerText();
			await shot(b, "U-38b-B");
			const payOpen = await b.getByRole("dialog").filter({ hasText: "Complete Payment" }).isVisible().catch(() => false);
			const after = capUsed();
			const draftsB = server("py", { code: `result=frappe.get_all("Sales Invoice",filters={"customer":"UIT-Cap","docstatus":0,"owner":"uit-cashier2@uit-pos.example","creation":[">=","${since}"]},fields=["name","paid_amount"])` });
			record("U-38b", { a: ra.name, bMsg: (bText.match(/[^\n]*(cap exceeded|exceeds|Invoice Total Changed)[^\n]*/gi) || []).slice(0, 4), payOpen, used, after, draftsB, errors: errorsSince(since) });
			expect(ra.status).toBe(200);
			expect(bText).toMatch(/Friends & Family cap exceeded|exceeds the customer's remaining monthly allowance|Invoice Total Changed/);
			expect(after).toBeCloseTo(used + 40, 2);
			expect(draftsB.every((d) => !d.paid_amount)).toBeTruthy();
		});
	} finally {
		ffReset();
	}
});

test("U-38 (c) UIT-MAX1 used in both tabs: B is refused", async ({ browser }) => {
	const used = coupons()["UIT-MAX1"];
	setDoc("POS Coupon", "UIT-MAX1", { maximum_use: used + 1 });
	try {
		await twoTabs(browser, async (a, b) => {
			const prep = async (p) => {
				await openPos(p);
				await clearCart(p);
				await selectCustomer(p, "UIT-Unverified");
				await addItem(p, "UIT-A");
				await applyCoupon(p, "UIT-MAX1");
				await expect(breakdown(p, "UIT-A")).toContainText("90.00");
			};
			await prep(a);
			await prep(b);
			const pa = await openPayment(a);
			const ra = await payExact(a, pa.dialog);
			await closeDialogs(a);
			// B presses Checkout; catch the refusal text while it is on screen (toasts fade)
			await b.getByRole("button", { name: "Proceed to payment" }).click();
			let bText = "";
			for (let i = 0; i < 40 && !/usage limit|Coupon Not Applicable|Complete Payment/.test(bText); i++) {
				await b.waitForTimeout(250);
				bText = await b.locator("body").innerText();
			}
			let rb = null;
			const pay = b.getByRole("dialog").filter({ hasText: "Complete Payment" });
			if (await pay.isVisible().catch(() => false)) {
				rb = await payExact(b, pay).catch((e) => ({ err: e.message }));
				await b.waitForTimeout(500);
				bText += "\n" + (await b.locator("body").innerText());
			}
			await shot(b, "U-38c-B");
			record("U-38c", { a: ra.name, b: rb?.name || null, bStatus: rb?.status, bMsg: (bText.match(/[^\n]*(Coupon Not Applicable|usage limit)[^\n]*/g) || []).slice(0, 3), used: [used, coupons()["UIT-MAX1"]], errors: errorsSince(since) });
			expect(ra.status).toBe(200);
			expect(bText).toMatch(/Coupon UIT-MAX1 has reached its usage limit|Coupon Not Applicable|usage limit/);
			expect(coupons()["UIT-MAX1"]).toBe(used + 1);
		});
	} finally {
		restoreDoc("coupons", "UIT-MAX1", ["maximum_use"]);
	}
});

test("U-39 the same address verified twice at once: exactly one wins", async ({ browser, request }) => {
	const email = "uit-race@uit-ff.example";
	resetCustomer("UIT-OTP1", email);
	resetCustomer("UIT-Shared", email);
	await twoTabs(browser, async (a, b) => {
		const before = await mailIds(request, email);
		const prep = async (p, cust) => {
			await openPos(p);
			await clearCart(p);
			await selectCustomer(p, cust);
			await p.getByRole("button", { name: "Edit customer details" }).click();
			await p.getByTestId("send-code").click();
			await expect(p.getByTestId("otp-input")).toBeVisible();
		};
		await prep(a, "UIT-OTP1");
		const c1 = await mailCode(request, email, before);
		const mid = await mailIds(request, email);
		await prep(b, "UIT-Shared");
		const c2 = await mailCode(request, email, mid);
		await a.getByTestId("otp-input").fill(c1);
		await b.getByTestId("otp-input").fill(c2);
		await Promise.all([a.getByTestId("verify").click(), b.getByTestId("verify").click()]);
		await a.waitForTimeout(4000);
		const ta = await a.getByTestId("email-verification-panel").innerText();
		const tb = await b.getByTestId("email-verification-panel").innerText();
		const won = server("py", { code: `result=frappe.get_all("Customer",filters={"custom_verified_email":"${email}"},pluck="name")` });
		record("U-39", { ta, tb, won });
		expect(won).toHaveLength(1);
		expect([ta, tb].filter((t) => /Email verified/.test(t))).toHaveLength(1);
		expect(`${ta} ${tb}`).toMatch(/already verified for another customer|Another request is in progress/);
	});
});
