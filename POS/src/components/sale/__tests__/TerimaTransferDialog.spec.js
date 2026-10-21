// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => call(...args) }));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock("frappe-ui", () => ({
	Dialog: { template: "<div><slot name='body-content' /></div>" },
	Button: {
		props: ["disabled", "loading"],
		template: "<button :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>",
		emits: ["click"],
	},
}));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import TerimaTransferDialog from "@/components/sale/TerimaTransferDialog.vue";

const BILLS = [
	{ doctype: "Sales Invoice", name: "SINV-PT-00401", company: "PT", tanggal: "2026-10-15", total: 3600000, sisa: 3600000 },
	{ doctype: "Sales Order", name: "SO-PT-00068", company: "PT", tanggal: "2026-10-16", total: 15000000, dp: 0, sisa: 15000000 },
];

beforeEach(() => {
	call.mockReset();
	call.mockImplementation(async (method) => {
		if (method.endsWith("get_kasir_setup"))
			return {
				modes: ["Transfer BCA", "Transfer Mandiri"],
				rekening_mode: {
					"Transfer BCA": { name: "BCA", bank: "BCA", nomor: "1234567890", company: "PT X" },
					"Transfer Mandiri": { name: "MDR", bank: "Mandiri", nomor: "2222", company: "PT X" },
				},
				today: "2026-10-19",
			};
		if (method.endsWith("get_open_bills")) return { bills: BILLS, customer_name: "Toko Sinar" };
		if (method.endsWith("receive_transfer")) return { transfer: "TRF-1", payment_entries: ["PE-1", "PE-2", "PE-3"], uang_muka: 400000 };
	});
});

async function open() {
	const wrapper = mount(TerimaTransferDialog, {
		props: { modelValue: false, posProfile: "Kasir", initialCustomer: { name: "CUST-1", customer_name: "Toko Sinar" } },
		global: { mocks: { __: globalThis.__ } },
	});
	await wrapper.setProps({ modelValue: true });
	await flushPromises();
	return wrapper;
}

const save = (wrapper) => wrapper.findAll("button").find((b) => b.text() === "Simpan pembayaran");

async function pickBoth(wrapper) {
	const boxes = wrapper.findAll("input[type=checkbox]");
	await boxes[0].setValue(true);
	await boxes[1].setValue(true);
	const amounts = wrapper.findAll("input[type=number]").filter((i) => i.attributes("max"));
	await amounts[1].setValue(6000000);
	await flushPromises();
}

describe("TerimaTransferDialog", () => {
	it("loads the cart customer's bills and fills the sender", async () => {
		const wrapper = await open();
		expect(call).toHaveBeenCalledWith("nextend.treasury.transfer.get_open_bills", { customer: "CUST-1", pos_profile: "Kasir" });
		expect(wrapper.text()).toContain("SINV-PT-00401");
		expect(wrapper.text()).toContain("SO-PT-00068");
		const sender = wrapper.findAll("input[type=text]")[0];
		expect(sender.element.value).toBe("Toko Sinar");
	});

	it("follows the picked bills until the cashier types the amount", async () => {
		const wrapper = await open();
		await pickBoth(wrapper);
		const nominal = wrapper.findAll("input[type=number]").find((i) => !i.attributes("max"));
		expect(Number(nominal.element.value)).toBe(9600000);
		expect(wrapper.text()).toContain("Pas");
	});

	it("keeps an overpayment as advance and sends one allocation per bill", async () => {
		const wrapper = await open();
		await pickBoth(wrapper);
		const nominal = wrapper.findAll("input[type=number]").find((i) => !i.attributes("max"));
		await nominal.setValue(10000000);
		await nominal.trigger("input");
		expect(wrapper.text()).toContain("uang muka customer");

		await save(wrapper).trigger("click");
		await flushPromises();
		const [, args] = call.mock.calls.find(([m]) => m.endsWith("receive_transfer"));
		expect(args.nominal).toBe(10000000);
		expect(args.allocations).toEqual([
			{ doctype: "Sales Invoice", name: "SINV-PT-00401", amount: 3600000 },
			{ doctype: "Sales Order", name: "SO-PT-00068", amount: 6000000 },
		]);
		expect(wrapper.text()).toContain("Cetak SINV-PT-00401");
	});

	it("shows the account of the chosen payment mode", async () => {
		const wrapper = await open();
		expect(wrapper.text()).toContain("BCA 1234567890");
		await wrapper.find("select").setValue("Transfer Mandiri");
		expect(wrapper.text()).toContain("Mandiri 2222");
		expect(wrapper.text()).not.toContain("BCA 1234567890");
	});

	it("refuses a transfer smaller than the bills", async () => {
		const wrapper = await open();
		await pickBoth(wrapper);
		const nominal = wrapper.findAll("input[type=number]").find((i) => !i.attributes("max"));
		await nominal.setValue(9000000);
		await nominal.trigger("input");
		expect(wrapper.text()).toContain("Kurang");
		expect(save(wrapper).attributes("disabled")).toBeDefined();
	});
});
