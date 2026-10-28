/**
 * Batch picker defaults to FEFO and the serial picker selects scanned serials on Enter.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import BatchSerialDialog from "../BatchSerialDialog.vue";

vi.hoisted(() => {
	globalThis.__ = (s, args) => s.replace(/{(\d+)}/g, (_, n) => args?.[n] ?? _);
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot name='actions' /></div>" },
	createResource: () => ({ reload: vi.fn() }),
}));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ loading: false, consumeSerials: vi.fn(), setWarehouse: vi.fn() }),
}));
vi.mock("@/stores/posCart", () => ({ usePOSCartStore: () => ({ invoiceItems: [] }) }));
vi.mock("@/utils/offline/items", () => ({
	getCachedBatchData: vi.fn(),
	getCachedSerialData: vi.fn(),
	persistItemBatchSerialData: vi.fn(),
}));
vi.mock("@/utils/offline", () => ({ isOffline: () => false }));

const mountDialog = (props) =>
	mount(BatchSerialDialog, { props: { modelValue: false, ...props }, global: { mocks: { __: globalThis.__ } } });

describe("BatchSerialDialog batch picker", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date(2026, 9, 25, 15, 0));
	});
	afterEach(() => vi.useRealTimers());

	it("pre-selects the earliest unexpired batch and lists it first", async () => {
		const wrapper = mountDialog({ item: { item_code: "YOG", has_batch_no: 1 } });
		const state = wrapper.vm.$.setupState;
		state.warehouseBatches = [
			{ batch_no: "OLD", qty: 3, expiry_date: "2026-10-01" },
			{ batch_no: "LATE", qty: 3, expiry_date: "2027-01-01" },
			{ batch_no: "NODATE", qty: 3 },
			{ batch_no: "SOON", qty: 3, expiry_date: "2026-11-05" },
		];
		await nextTick();
		expect(state.selectedBatch.batch_no).toBe("SOON");
		expect(state.availableBatches.map((b) => b.batch_no)).toEqual(["SOON", "LATE", "NODATE", "OLD"]);
	});

	it("passes the chosen batch's expiry with the batch number", async () => {
		const wrapper = mountDialog({ item: { item_code: "YOG", has_batch_no: 1 } });
		const state = wrapper.vm.$.setupState;
		state.warehouseBatches = [{ batch_no: "SOON", qty: 3, expiry_date: "2026-11-05" }];
		await nextTick();
		state.handleConfirm();
		expect(wrapper.emitted("batch-serial-selected")[0][0]).toEqual({ batch_no: "SOON", batch_expiry_date: "2026-11-05" });
	});

	it("labels expiry with an unambiguous date, a relative day count and a tone", () => {
		const state = mountDialog({ item: { item_code: "YOG", has_batch_no: 1 } }).vm.$.setupState;
		expect(state.expiryLabel("2026-11-05")).toBe("5 November 2026 · in 11 days");
		expect(state.expiryLabel("2026-10-25")).toBe("25 October 2026 · Expires today");
		expect(state.expiryLabel("2026-10-01")).toBe("1 October 2026 · Expired");
		expect(state.expiryTone("2026-11-05")).toContain("b45309");
		expect(state.expiryTone("2026-10-01")).toContain("red");
		expect(state.expiryTone("2027-06-01")).toContain("gray");
	});
});

describe("BatchSerialDialog serial picker", () => {
	const serials = [{ serial_no: "SN-0001" }, { serial_no: "SN-0002" }];

	it("selects an exact scanned serial on Enter and confirms once the quantity is met", () => {
		const wrapper = mountDialog({ item: { item_code: "PHONE", has_serial_no: 1 }, quantity: 1 });
		const state = wrapper.vm.$.setupState;
		state.availableSerials = serials;
		state.serialSearchQuery = "sn-0002";
		state.handleSerialEnter();
		expect(wrapper.emitted("batch-serial-selected")[0][0]).toEqual({ serial_no: "SN-0002", quantity: 1 });
	});

	it("waits for the required quantity and clears the search for the next scan", () => {
		const wrapper = mountDialog({ item: { item_code: "PHONE", has_serial_no: 1 }, quantity: 2 });
		const state = wrapper.vm.$.setupState;
		state.availableSerials = serials;
		state.serialSearchQuery = "SN-0001";
		state.handleSerialEnter();
		expect(state.serialSearchQuery).toBe("");
		expect(wrapper.emitted("batch-serial-selected")).toBeUndefined();
		state.serialSearchQuery = "SN-0002";
		state.handleSerialEnter();
		expect(wrapper.emitted("batch-serial-selected")[0][0].quantity).toBe(2);
	});

	it("hides Select All for a single-unit sale", async () => {
		const wrapper = mountDialog({ item: { item_code: "PHONE", has_serial_no: 1 }, quantity: 1 });
		wrapper.vm.$.setupState.availableSerials = serials;
		await nextTick();
		expect(wrapper.text()).not.toContain("Select All");
		await wrapper.setProps({ quantity: 2 });
		expect(wrapper.text()).toContain("Select All");
	});
});
