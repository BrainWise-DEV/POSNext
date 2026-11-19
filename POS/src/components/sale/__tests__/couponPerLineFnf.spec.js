/**
 * An F&F customer's coupon follows the server's per-line decision: line coupons go to the
 * cart as line updates (F&F kept elsewhere); only an order coupon becomes a header discount.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CouponDialog from "../CouponDialog.vue";

const server = vi.hoisted(() => {
	globalThis.__ = (s, args) => (args ? `${s} ${args.join(" ")}` : s);
	return { coupon: {}, calc: {}, doctype: "Sales Invoice", methods: [] };
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot /></div>" },
	Input: { template: "<input />" },
	call: vi.fn(async (method) => {
		server.methods.push(method);
		return method === "calc" ? server.calc : { valid: true, coupon: server.coupon };
	}),
	createResource: () => ({ reload: vi.fn() }),
}));
vi.mock("@/utils/promoApi", () => ({
	isPromotionsAppInstalled: () => true,
	promoApi: {
		getActiveCoupons: () => "x",
		validateCoupon: () => "validate",
		calculateCouponDiscount: () => "calc",
		applyFriendsAndFamilyDiscount: () => "fnf",
	},
}));
vi.mock("@/stores/posCart", () => ({
	usePOSCartStore: () => ({
		targetDoctype: server.doctype,
		fnfEligibility: { eligible: true, discountPercentage: 30 },
		invoiceItems: [{ item_code: "A" }, { item_code: "B", discount_source: "friends_and_family" }],
		buildCouponItemsPayload: () => [],
		buildOfferEvaluationPayload: () => ({ items: [] }),
	}),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("@/composables/useInvoice", () => ({ useInvoice: () => ({}) }));

async function apply() {
	const wrapper = mount(CouponDialog, {
		props: { modelValue: true, subtotal: 200, grandTotal: 200, customer: "C", company: "Nexus" },
		global: { mocks: { __: globalThis.__ } },
	});
	wrapper.vm.$.setupState.couponCode = "C20";
	await wrapper.vm.$.setupState.applyCoupon();
	return wrapper.emitted("discount-applied")[0][0];
}

describe("CouponDialog coupon vs F&F per line", () => {
	beforeEach(() => {
		server.doctype = "Sales Invoice";
		server.methods = [];
		server.coupon = { coupon_code: "C20", discount_type: "Percentage", discount_percentage: 20 };
	});

	it("sends a per-line decision as line updates without suppressing F&F", async () => {
		server.calc = {
			valid: true,
			granularity: "line",
			discount: 20,
			suppress_friends_and_family: true,
			line_updates: [{ line_key: 0, item_code: "A", discount_percentage: 20 }],
		};
		const discount = await apply();
		expect(discount.line_level).toBe(true);
		expect(discount.line_updates).toHaveLength(1);
		expect(discount.amount).toBe(20);
		expect(discount.suppress_friends_and_family).toBeUndefined();
	});

	it("D-15: a line coupon that beat F&F carries the comparison for coupon-applied-fnf-message", async () => {
		const text = "Coupon C20 (50%) is better than Friends & Family (30%)"
		server.calc = {
			valid: true,
			granularity: "line",
			discount: 50,
			suppress_friends_and_family: true,
			line_updates: [{ line_key: 1, item_code: "B", discount_percentage: 50 }],
			best_discount: { suppressed: ["friends_and_family"] },
			message: text,
			message_en: text,
		};
		const discount = await apply();
		expect(discount.line_level).toBe(true);
		expect(discount.fnf_message).toMatchObject({ message_en: text });
		expect(discount.suppress_friends_and_family).toBeUndefined();
	});

	it("order_level_coupon_uses_header", async () => {
		server.coupon = { coupon_code: "C20", discount_type: "Amount", discount_amount: 60 };
		server.calc = {
			valid: true,
			granularity: "order",
			discount: 60,
			suppress_friends_and_family: true,
			line_updates: [{ line_key: 0, item_code: "A", discount_amount: 30 }],
		};
		const discount = await apply();
		expect(discount.line_level).toBeUndefined();
		expect(discount.amount).toBe(60);
		expect(discount.suppress_friends_and_family).toBe(true);
	});

	it("a coupon that loses to F&F (valid: false) applies no header discount", async () => {
		// Ruling 98: what calculate_coupon_discount returns when F&F wins (the R1 shape):
		// the dialog must stop here, so the cart never sends a header next to F&F lines.
		server.coupon = { coupon_code: "C20", discount_type: "Percentage", discount_percentage: 10 };
		server.calc = {
			valid: false,
			granularity: "order",
			discount: 0,
			coupon_value: 5,
			line_updates: [],
			best_discount: { suppressed: true },
			message: "Friends & Family discount (15.00) is better",
			message_en: "Friends & Family discount (15.00) is better",
		};
		const wrapper = mount(CouponDialog, {
			props: { modelValue: true, subtotal: 130, grandTotal: 130, customer: "C", company: "Nexus" },
			global: { mocks: { __: globalThis.__ } },
		});
		wrapper.vm.$.setupState.couponCode = "C20";
		await wrapper.vm.$.setupState.applyCoupon();
		expect(server.methods).toContain("calc");
		expect(wrapper.emitted("discount-applied")).toBeUndefined();
		expect(wrapper.vm.$.setupState.appliedDiscount).toBeFalsy();
	});

	it("a Sales Order is not compared with F&F: the coupon calculation is not used", async () => {
		server.doctype = "Sales Order";
		server.calc = { valid: false };
		server.coupon = { coupon_code: "C20", discount_type: "Percentage", discount_percentage: 20 };
		await apply().catch(() => {});
		expect(server.methods).not.toContain("calc");
	});
});
