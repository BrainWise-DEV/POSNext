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

import TransferShiftDialog from "@/components/sale/TransferShiftDialog.vue";

const BCA = { name: "BCA", bank: "BCA", nomor: "0011" };
const row = (name, total, extra = {}) => ({
	name,
	nama_pengirim: `Pengirim ${name}`,
	customer_name: `Pengirim ${name}`,
	total,
	tanggal_transfer: "2026-10-21",
	rekening_tujuan: "BCA",
	rekening: BCA,
	status: "Belum dicek",
	bisa_diubah: true,
	gabungan: false,
	dokumen: [{ reference_name: `SINV-${name}`, company: "PT", amount: total }],
	...extra,
});

let rows;
beforeEach(() => {
	rows = [
		row("TRF-1", 600000),
		row("TRF-2", 900000),
		row("TRF-3", 250000, { rekening_tujuan: "MDR", rekening: { name: "MDR", bank: "Mandiri", nomor: "0022" } }),
		row("TRF-4", 100000, { status: "Diterima", bisa_diubah: false }),
	];
	call.mockReset();
	call.mockImplementation(async (method) => {
		if (method.endsWith("list_shift_transfers")) return { shift: "SHIFT-1", rows };
		if (method.endsWith("merge_transfers")) return { transfer: "TRF-1", total: 1500000, digabung: ["TRF-2"] };
		if (method.endsWith("split_transfer")) return { transfer: "TRF-5", dipisah: ["TRF-6"] };
	});
});

async function open() {
	const wrapper = mount(TransferShiftDialog, {
		props: { modelValue: false, posProfile: "Kasir" },
		global: { mocks: { __: globalThis.__ } },
	});
	await wrapper.setProps({ modelValue: true });
	await flushPromises();
	return wrapper;
}

const boxes = (wrapper) => wrapper.findAll("input[type=checkbox]");
const mergeButton = (wrapper) => wrapper.findAll("button").find((b) => b.text() === "Gabungkan jadi satu transfer");

describe("TransferShiftDialog", () => {
	it("lists the shift's transfers and locks the ones treasury already decided", async () => {
		const wrapper = await open();
		expect(call).toHaveBeenCalledWith("nextend.treasury.transfer.list_shift_transfers", { pos_profile: "Kasir" });
		expect(wrapper.text()).toContain("Pengirim TRF-1");
		expect(wrapper.text()).toContain("Mandiri 0022");
		expect(boxes(wrapper)[3].attributes("disabled")).toBeDefined();
	});

	it("merges two transfers to the same account with the sender from the proof", async () => {
		const wrapper = await open();
		await boxes(wrapper)[0].setValue(true);
		await boxes(wrapper)[1].setValue(true);
		expect(wrapper.text()).toContain("2 transfer dipilih");
		const sender = wrapper.findAll("input[type=text]")[0];
		expect(sender.element.value).toBe("Pengirim TRF-1");
		await sender.setValue("Budi Santoso");

		await mergeButton(wrapper).trigger("click");
		await flushPromises();
		const [, args] = call.mock.calls.find(([m]) => m.endsWith("merge_transfers"));
		expect(args.names).toEqual(["TRF-1", "TRF-2"]);
		expect(args.pengirim).toBe("Budi Santoso");
		expect(args.pos_profile).toBe("Kasir");
	});

	it("refuses to merge transfers to different accounts", async () => {
		const wrapper = await open();
		await boxes(wrapper)[0].setValue(true);
		await boxes(wrapper)[2].setValue(true);
		expect(wrapper.text()).toContain("Rekening tujuannya berbeda");
		expect(mergeButton(wrapper).attributes("disabled")).toBeDefined();
	});

	it("splits a merged transfer back", async () => {
		rows = [row("TRF-5", 1500000, { gabungan: true })];
		const wrapper = await open();
		await wrapper.findAll("button").find((b) => b.text() === "Pisahkan lagi").trigger("click");
		await flushPromises();
		expect(call).toHaveBeenCalledWith("nextend.treasury.transfer.split_transfer", { name: "TRF-5", pos_profile: "Kasir" });
	});
});
