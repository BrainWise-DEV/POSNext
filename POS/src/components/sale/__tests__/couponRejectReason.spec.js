/**
 * A rejected coupon shows the server's reason inline, once, with no toast (D-12).
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CouponDialog from "../CouponDialog.vue";

const h = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s);
	return { validate: {}, showError: vi.fn(), showWarning: vi.fn(), showSuccess: vi.fn() };
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot /></div>" },
	Input: { template: "<input />" },
	call: vi.fn(async () => h.validate),
	createResource: () => ({ reload: vi.fn() }),
}));
vi.mock("@/utils/promoApi", () => ({
	isPromotionsAppInstalled: () => false,
	promoApi: { getActiveCoupons: () => "x", validateCoupon: () => "validate" },
}));
vi.mock("@/stores/posCart", () => ({
	usePOSCartStore: () => ({
		targetDoctype: "Sales Invoice",
		fnfEligibility: { eligible: false },
		invoiceItems: [],
		buildCouponItemsPayload: () => [],
		buildOfferEvaluationPayload: () => ({ items: [] }),
	}),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: h.showSuccess, showError: h.showError, showWarning: h.showWarning }),
}));
vi.mock("@/composables/useInvoice", () => ({ useInvoice: () => ({}) }));

async function apply() {
	const wrapper = mount(CouponDialog, {
		props: { modelValue: true, subtotal: 100, grandTotal: 100, customer: "C", company: "Nexus" },
		global: { mocks: { __: globalThis.__ } },
	});
	wrapper.vm.$.setupState.couponCode = "BAD";
	await wrapper.vm.$.setupState.applyCoupon();
	return wrapper;
}

describe("CouponDialog rejected coupon", () => {
	beforeEach(() => {
		h.showError.mockReset();
		h.showWarning.mockReset();
	});

	it("shows the server's reason inline and raises no toast", async () => {
		h.validate = { valid: false, message: "Coupon has expired", message_en: "Coupon has expired" };
		const wrapper = await apply();
		expect(h.showError).not.toHaveBeenCalled();
		expect(h.showWarning).not.toHaveBeenCalled();
		expect(wrapper.text()).toContain("Coupon has expired");
		expect(wrapper.text()).not.toContain("Failed to apply coupon");
	});
});
