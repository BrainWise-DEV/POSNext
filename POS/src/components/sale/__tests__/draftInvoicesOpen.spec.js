/**
 * The held invoice already open in the cart can't be loaded again.
 * @vitest-environment jsdom
 */
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
	globalThis.__ = (s) => s;
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot name='actions' /></div>" },
	FeatherIcon: { template: "<i />" },
}));
vi.mock("@/utils/draftManager", () => ({
	clearAllDrafts: vi.fn(),
	deleteDraft: vi.fn(),
	getAllDrafts: vi.fn(async () => [
		{ draft_id: "D-OPEN", customer: "Ahmed", created_at: "2026-10-25T10:00:00", items: [] },
		{ draft_id: "D-OTHER", customer: "Mona", created_at: "2026-10-25T11:00:00", items: [] },
	]),
}));
vi.mock("@/utils/printInvoice", () => ({ printInvoiceCustom: vi.fn() }));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("@/stores/posShift", () => ({ usePOSShiftStore: () => ({}) }));
vi.mock("@/stores/posCart", () => ({ usePOSCartStore: () => ({ currentDraftId: "D-OPEN" }) }));
vi.mock("@/stores/posDrafts", () => ({ usePOSDraftsStore: () => ({ returnDraftSerials: vi.fn() }) }));

const { default: DraftInvoicesDialog } = await import("../DraftInvoicesDialog.vue");

describe("DraftInvoicesDialog", () => {
	it("marks the open held invoice and does not load it twice", async () => {
		const wrapper = mount(DraftInvoicesDialog, {
			props: { modelValue: true },
			global: { mocks: { __: globalThis.__ } },
		});
		await flushPromises();

		const cards = wrapper.findAll("[aria-disabled]");
		expect(cards).toHaveLength(2);
		expect(cards[0].text()).toContain("Open in the cart now");
		expect(cards[0].text()).toContain("Ahmed");

		await cards[0].trigger("click");
		expect(wrapper.emitted("load-draft")).toBeUndefined();

		await cards[1].trigger("click");
		expect(wrapper.emitted("load-draft")[0][0].draft_id).toBe("D-OTHER");
	});
});
