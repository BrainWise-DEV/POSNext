/**
 * @vitest-environment jsdom
 */
import { mount, flushPromises } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const callMock = vi.fn()
const offlineMock = vi.fn(() => false)

vi.mock("frappe-ui", () => ({ call: (...args) => callMock(...args) }))
vi.mock("@/utils/offline/offlineState", () => ({ isOffline: () => offlineMock() }))

import EmailVerificationPanel from "../EmailVerificationPanel.vue"

const t = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
globalThis.__ = t

const baseProps = {
	customer: "CUST-1",
	email: "jane@example.com",
	savedEmail: "jane@example.com",
	posProfile: "POS-A",
}

function factory(props = {}) {
	return mount(EmailVerificationPanel, {
		props: { ...baseProps, ...props },
		global: { mocks: { __: t } },
		attachTo: document.body,
	})
}

const sent = { ok: true, code: "sent", expires_in: 900, resend_in: 60 }
const find = (w, id) => w.find(`[data-testid="${id}"]`)

async function toCodeSent(w, response = sent) {
	callMock.mockResolvedValueOnce(response)
	await find(w, "send-code").trigger("click")
	await flushPromises()
}

describe("EmailVerificationPanel", () => {
	beforeEach(() => {
		vi.useFakeTimers()
		callMock.mockReset()
		offlineMock.mockReturnValue(false)
	})
	afterEach(() => {
		vi.useRealTimers()
	})

	it("starts idle with a Verify button", () => {
		const w = factory()
		expect(find(w, "send-code").exists()).toBe(true)
		expect(find(w, "send-code").attributes("disabled")).toBeUndefined()
		expect(find(w, "not-verified-label").exists()).toBe(true)
		w.unmount()
	})

	it("idle -> sending -> code_sent, calls the API with customer/email only", async () => {
		const w = factory()
		let resolve
		callMock.mockReturnValueOnce(new Promise((r) => (resolve = r)))
		await find(w, "send-code").trigger("click")
		expect(find(w, "sending").exists()).toBe(true)
		resolve(sent)
		await flushPromises()
		expect(find(w, "otp-input").exists()).toBe(true)
		expect(find(w, "enter-code-hint").text()).toContain("jane@example.com")
		expect(callMock).toHaveBeenCalledWith(
			"pos_next.api.email_verification.send_email_otp",
			{ customer: "CUST-1", email: "jane@example.com", pos_profile: "POS-A" },
		)
		// never sends a phone number
		expect(JSON.stringify(callMock.mock.calls[0][1])).not.toContain("phone")
		w.unmount()
	})

	it("emits lock-change while a code is pending and unlocks via Change email", async () => {
		const w = factory()
		await toCodeSent(w)
		expect(w.emitted("lock-change").at(-1)).toEqual([true])
		await find(w, "change-email").trigger("click")
		expect(w.emitted("lock-change").at(-1)).toEqual([false])
		expect(find(w, "send-code").exists()).toBe(true)
		w.unmount()
	})

	it("accepts only digits, max 6, and enables Verify at 6 digits", async () => {
		const w = factory()
		await toCodeSent(w)
		const input = find(w, "otp-input")
		expect(input.attributes("inputmode")).toBe("numeric")
		expect(input.attributes("maxlength")).toBe("6")
		await input.setValue("12ab34")
		expect(input.element.value).toBe("1234")
		expect(find(w, "verify").attributes("disabled")).toBeDefined()
		await input.setValue("1234567")
		expect(input.element.value).toBe("123456")
		expect(find(w, "verify").attributes("disabled")).toBeUndefined()
		w.unmount()
	})

	it("counts down from 15:00 and moves to expired at 0", async () => {
		const w = factory()
		await toCodeSent(w)
		expect(find(w, "countdown").text()).toContain("15:00")
		await vi.advanceTimersByTimeAsync(61_000)
		expect(find(w, "countdown").text()).toContain("13:59")
		await vi.advanceTimersByTimeAsync(839_000)
		await flushPromises()
		expect(find(w, "expired-msg").exists()).toBe(true)
		expect(find(w, "send-code").text()).toContain("Send new code")
		expect(find(w, "otp-input").exists()).toBe(false)
		w.unmount()
	})

	it("disables Resend for 60s then enables it", async () => {
		const w = factory()
		await toCodeSent(w)
		expect(find(w, "resend").attributes("disabled")).toBeDefined()
		expect(find(w, "resend").text()).toContain("60s")
		await vi.advanceTimersByTimeAsync(30_000)
		expect(find(w, "resend").text()).toContain("30s")
		await vi.advanceTimersByTimeAsync(30_000)
		expect(find(w, "resend").attributes("disabled")).toBeUndefined()
		expect(find(w, "resend").text()).toContain("Resend code")
		w.unmount()
	})

	it("verifies successfully -> badge + verified event, unlocked", async () => {
		const w = factory()
		await toCodeSent(w)
		await find(w, "otp-input").setValue("482913")
		callMock.mockResolvedValueOnce({ ok: true, code: "verified", verified_email: "jane@example.com" })
		await find(w, "verify").trigger("click")
		await flushPromises()
		expect(callMock).toHaveBeenLastCalledWith(
			"pos_next.api.email_verification.verify_email_otp",
			{ customer: "CUST-1", otp: "482913", email: "jane@example.com", pos_profile: "POS-A" },
		)
		expect(find(w, "verified-badge").exists()).toBe(true)
		expect(w.emitted("verified")[0][0]).toEqual({
			customer: "CUST-1",
			verified_email: "jane@example.com",
		})
		expect(w.emitted("lock-change").at(-1)).toEqual([false])
		w.unmount()
	})

	it("a not-ok response (e.g. status:false mapped) is never shown as verified", async () => {
		const w = factory()
		await toCodeSent(w)
		await find(w, "otp-input").setValue("111111")
		callMock.mockResolvedValueOnce({ ok: false, code: "invalid_otp", message: "Wrong code (or email changed)." })
		await find(w, "verify").trigger("click")
		await flushPromises()
		expect(find(w, "verified-badge").exists()).toBe(false)
		expect(w.emitted("verified")).toBeUndefined()
		expect(find(w, "error-msg").text()).toContain("Wrong code")
		// stays on the code step with the input retained
		expect(find(w, "otp-input").element.value).toBe("111111")
		w.unmount()
	})

	it("expired code from server moves to expired", async () => {
		const w = factory()
		await toCodeSent(w)
		await find(w, "otp-input").setValue("111111")
		callMock.mockResolvedValueOnce({ ok: false, code: "expired", message: "Code expired. Request a new one." })
		await find(w, "verify").trigger("click")
		await flushPromises()
		expect(find(w, "expired-msg").exists()).toBe(true)
		w.unmount()
	})

	it("send error stays idle and shows the mapped message", async () => {
		const w = factory()
		callMock.mockResolvedValueOnce({ ok: false, code: "not_synced", message: "Customer is not registered in Magento yet." })
		await find(w, "send-code").trigger("click")
		await flushPromises()
		expect(find(w, "error-msg").text()).toContain("not registered in Magento")
		expect(find(w, "send-code").exists()).toBe(true)
		w.unmount()
	})

	it("API exceptions show an error and keep the previous step", async () => {
		const w = factory()
		callMock.mockRejectedValueOnce(new Error("boom"))
		await find(w, "send-code").trigger("click")
		await flushPromises()
		expect(find(w, "error-msg").text()).toContain("boom")
		w.unmount()
	})

	it("is disabled offline", async () => {
		offlineMock.mockReturnValue(true)
		const w = factory()
		expect(find(w, "send-code").attributes("disabled")).toBeDefined()
		expect(find(w, "offline-msg").exists()).toBe(true)
		await find(w, "send-code").trigger("click")
		expect(callMock).not.toHaveBeenCalled()
		w.unmount()
	})

	it("disabled for blank, fabricated or unsaved emails", async () => {
		for (const email of ["", "pos.7701234567@pos.miraaya", "nope"]) {
			const w = factory({ email, savedEmail: email })
			expect(find(w, "send-code").attributes("disabled")).toBeDefined()
			w.unmount()
		}
		const w = factory({ email: "new@example.com", savedEmail: "jane@example.com" })
		expect(find(w, "send-code").attributes("disabled")).toBeDefined()
		expect(find(w, "unsaved-msg").exists()).toBe(true)
		w.unmount()
	})

	it("shows the verified badge for a verified customer and resets it when the email is edited", async () => {
		const w = factory({ verified: true, verifiedEmail: "jane@example.com" })
		expect(find(w, "verified-badge").exists()).toBe(true)
		await w.setProps({ email: "other@example.com" })
		expect(find(w, "verified-badge").exists()).toBe(false)
		expect(find(w, "send-code").exists()).toBe(true)
		await w.setProps({ email: "JANE@example.com" })
		expect(find(w, "verified-badge").exists()).toBe(true)
		w.unmount()
	})

	it("new customer without Magento id: shows sync hint but keeps Verify enabled", () => {
		const w = factory({ magentoSynced: false })
		expect(find(w, "sync-pending-hint").exists()).toBe(true)
		expect(find(w, "send-code").attributes("disabled")).toBeUndefined()
		w.unmount()
	})

	it("synced customer: no sync hint", () => {
		const w = factory()
		expect(find(w, "sync-pending-hint").exists()).toBe(false)
		w.unmount()
	})

	it("sync_pending from the server shows the server message, not 'not registered'", async () => {
		const msg = "Customer is saved but not synced with Magento yet. Please try again in a moment."
		const w = factory({ magentoSynced: false })
		await toCodeSent(w, { ok: false, code: "sync_pending", message: msg })
		expect(w.text()).toContain(msg)
		expect(w.text()).not.toContain("not registered")
		w.unmount()
	})
})
