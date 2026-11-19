/**
 * A capped percentage coupon must reach the cart as its capped amount.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import CouponDialog from "../CouponDialog.vue";

vi.hoisted(() => {
	globalThis.__ = (s) => s;
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot /></div>" },
	Input: { template: "<input />" },
	call: vi.fn(async () => ({
		valid: true,
		coupon: {
			coupon_code: "WELCOME10",
			discount_type: "Percentage",
			discount_percentage: 10,
			min_amount: 500,
			max_amount: 300,
			apply_on: "Grand Total",
		},
	})),
	createResource: () => ({ reload: vi.fn() }),
}));
vi.mock("@/utils/promoApi", () => ({
	isPromotionsAppInstalled: () => false,
	promoApi: { getActiveCoupons: () => "x", validateCoupon: () => "x" },
}));
vi.mock("@/stores/posCart", () => ({ usePOSCartStore: () => ({}) }));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("@/composables/useInvoice", () => ({
	useInvoice: () => ({
		calculateDiscountAmount: (d, base) =>
			d.percentage > 0 ? (base * d.percentage) / 100 : d.amount > 0 ? d.amount : 0,
	}),
}));

describe("CouponDialog max discount cap", () => {
	it("emits the capped amount with percentage 0 so the cart keeps the cap", async () => {
		const wrapper = mount(CouponDialog, {
			props: { modelValue: true, subtotal: 9952, grandTotal: 9952, customer: "Walk-In Customer", company: "Nexus" },
			global: { mocks: { __: globalThis.__ } },
		});
		wrapper.vm.$.setupState.couponCode = "WELCOME10";
		await wrapper.vm.$.setupState.applyCoupon();

		const [discount] = wrapper.emitted("discount-applied")[0];
		expect(discount.amount).toBe(300);
		expect(discount.percentage).toBe(0);
	});
});
