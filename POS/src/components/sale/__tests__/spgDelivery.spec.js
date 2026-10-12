// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

// A plain stand-in, not vi.fn: a spy reports the rejected lookup as unhandled.
const calls = [];
let lookup = async () => [];
vi.mock("@/utils/apiWrapper", () => ({
	call: (...args) => {
		calls.push(args);
		return lookup();
	},
}));
vi.mock("frappe-ui", () => ({
	Button: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ["disabled"] },
	Dialog: { template: '<div><slot name="body-content" /><slot name="actions" /></div>' },
}));
globalThis.__ = (s) => s;

import DeliveryAddressFields from "@/components/sale/DeliveryAddressFields.vue";
import SpgSaveOrderDialog from "@/components/sale/SpgSaveOrderDialog.vue";

const global = { mocks: { __: globalThis.__ } };
const ADDRESSES = [
	{ label: "Kiriman terakhir", alamat: "Jl. Kenanga 14" },
	{ label: "Andi-Kantor", alamat: "Jl. Melati 2" },
];

beforeEach(() => {
	calls.length = 0;
	lookup = async () => [];
});

describe("DeliveryAddressFields", () => {

	it("fills in the customer's first address and offers the others", async () => {
		lookup = async () => ADDRESSES;
		const wrapper = mount(DeliveryAddressFields, { props: { customer: "Andi" }, global });
		await flushPromises();

		expect(calls).toEqual([["nextend.pengiriman.get_delivery_addresses", { customer: "Andi" }]]);
		expect(wrapper.emitted("update:alamat")[0]).toEqual(["Jl. Kenanga 14"]);
		const chips = wrapper.findAll("button");
		expect(chips.map((chip) => chip.text())).toEqual(["Kiriman terakhir", "Andi-Kantor"]);
		await chips[1].trigger("click");
		expect(wrapper.emitted("update:alamat")[1]).toEqual(["Jl. Melati 2"]);
	});

	it("keeps an address already there, and asks nothing for a walk-in", async () => {
		lookup = async () => ADDRESSES;
		const typed = mount(DeliveryAddressFields, { props: { customer: "Andi", alamat: "Gudang proyek" }, global });
		await flushPromises();
		expect(typed.emitted("update:alamat")).toBeUndefined();

		calls.length = 0;
		mount(DeliveryAddressFields, { props: { customer: "" }, global });
		await flushPromises();
		expect(calls).toEqual([]);
	});

	it("is typed by hand when the lookup fails", async () => {
		lookup = async () => {
			throw new Error("offline");
		};
		const wrapper = mount(DeliveryAddressFields, { props: { customer: "Andi" }, global });
		await flushPromises();
		expect(calls).toHaveLength(1);
		expect(wrapper.findAll("button")).toHaveLength(0);
		await wrapper.find("textarea").setValue("Jl. Baru 1");
		expect(wrapper.emitted("update:alamat")[0]).toEqual(["Jl. Baru 1"]);
	});
});

describe("SpgSaveOrderDialog", () => {
	const saveButton = (wrapper) => wrapper.findAll("button").find((b) => b.text() === "Simpan Pesanan");

	async function open(props = {}) {
		const wrapper = mount(SpgSaveOrderDialog, { props: { modelValue: false, ...props }, global });
		await wrapper.setProps({ modelValue: true });
		return wrapper;
	}

	it("saves an order taken along without asking for an address", async () => {
		const wrapper = await open();
		await saveButton(wrapper).trigger("click");
		expect(wrapper.emitted("save")[0]).toEqual([{ dikirim: 0, alamat_kirim: "", catatan_kirim: "" }]);
	});

	it("a delivered order needs an address before it can be saved", async () => {
		const wrapper = await open({ customer: "Andi" });
		await wrapper.find("input[type=checkbox]").setValue(true);
		await flushPromises();
		expect(saveButton(wrapper).attributes("disabled")).toBeDefined();

		await wrapper.find("textarea").setValue(" Jl. Kenanga 14 ");
		await wrapper.find("input[type=text]").setValue("sore");
		expect(saveButton(wrapper).attributes("disabled")).toBeUndefined();
		await saveButton(wrapper).trigger("click");
		expect(wrapper.emitted("save")[0]).toEqual([
			{ dikirim: 1, alamat_kirim: "Jl. Kenanga 14", catatan_kirim: "sore" },
		]);
	});

	it("reopens with the delivery of the order being changed", async () => {
		const wrapper = await open({ initial: { alamat: "Jl. Melati 2", catatan: "pagi" } });
		expect(wrapper.find("input[type=checkbox]").element.checked).toBe(true);
		expect(wrapper.find("textarea").element.value).toBe("Jl. Melati 2");
		await saveButton(wrapper).trigger("click");
		expect(wrapper.emitted("save")[0]).toEqual([
			{ dikirim: 1, alamat_kirim: "Jl. Melati 2", catatan_kirim: "pagi" },
		]);
	});
});
