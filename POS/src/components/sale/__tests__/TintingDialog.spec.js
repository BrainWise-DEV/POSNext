// @vitest-environment jsdom
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("frappe-ui", () => ({
	Dialog: { template: "<div><slot name='body-content' /><slot name='actions' /></div>" },
	Button: { template: "<button @click=\"$emit('click')\"><slot /></button>", emits: ["click"] },
}));
vi.mock("@/utils/currency", () => ({ formatCurrency: (n) => String(n) }));
vi.mock("@/utils/itemAddons", async (importOriginal) => ({
	...(await importOriginal()),
	getAvailableAddons: (_item, jenis) => ((globalThis.__tintaJenis = jenis), {
		items: [
			{ item_code: "PRP-YEL", item_name: "Propan Yellow", addon_group: "Tinta Propan" },
			{ item_code: "PRP-RED", item_name: "Propan Red", addon_group: "Tinta Propan" },
			{ item_code: "LOOSE", item_name: "Loose", addon_group: null },
		],
		groups: ["Tinta Propan"],
	}),
	isOpenPriceItem: (code) => code === "BASE",
}));
globalThis.__ = (s) => s;

import TintingDialog from "@/components/sale/TintingDialog.vue";

const ITEM = { item_code: "BASE", item_name: "Base", warehouse: "W1", rate: 60000 };

async function open(tinting = null, item = {}) {
	const wrapper = mount(TintingDialog, {
		props: { modelValue: false, item: { ...ITEM, ...item, tinting } },
		global: { mocks: { __: (s) => s } },
	});
	await wrapper.setProps({ modelValue: true });
	return wrapper;
}

// Amount inputs in render order: group header, its members, then the loose tinta.
function amounts(wrapper) {
	const [header, yellow, red, loose] = wrapper.findAll(
		"input[inputmode=decimal]:not([data-test=tinting-rate])"
	);
	return { header, yellow, red, loose };
}

async function save(wrapper, arg = 0) {
	await wrapper.findAll("button").find((b) => b.text() === "Save").trigger("click");
	return wrapper.emitted("save")?.at(-1)?.[arg];
}

async function fill(wrapper) {
	await wrapper.find("[data-test=tinting-job]").setValue("J-1");
	await amounts(wrapper).header.setValue("5000");
}

describe("TintingDialog", () => {
	it("lists the Tinta Produksi kind with the old add on layout", async () => {
		const wrapper = await open();
		expect(globalThis.__tintaJenis).toBe("Tinta Produksi");
		expect(amounts(wrapper).loose.exists()).toBe(true);
		expect(wrapper.text()).toContain("Gelondongan");
		expect(wrapper.find("input[placeholder]").exists()).toBe(false);
	});

	it("formats the HPP while typing and saves the total with the job", async () => {
		const wrapper = await open();
		await wrapper.find("[data-test=tinting-job]").setValue(" J-77 ");
		const { header } = amounts(wrapper);
		await header.setValue("15000");
		expect(header.element.value).toBe("15,000");
		expect(wrapper.find("[data-test=tinting-total]").text()).toBe("15000");
		expect(await save(wrapper)).toEqual({
			job: "J-77",
			hpp_tinta: 15000,
			tinta: [{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: 15000 }],
		});
	});

	it("sums per tinta HPP and locks the group header", async () => {
		const wrapper = await open();
		await wrapper.find("[data-test=tinting-job]").setValue("J-1");
		const { header, yellow, loose } = amounts(wrapper);
		await yellow.setValue("2500");
		await loose.setValue("1,000");
		expect(header.element.disabled).toBe(true);
		const saved = await save(wrapper);
		expect(saved.hpp_tinta).toBe(3500);
		expect(saved.tinta.map((t) => t.item_code)).toEqual(["PRP-YEL", "LOOSE"]);
	});

	it("needs a job and some HPP", async () => {
		const wrapper = await open();
		await amounts(wrapper).header.setValue("5000");
		expect(await save(wrapper)).toBeUndefined();
		expect(wrapper.find("[data-test=tinting-error]").exists()).toBe(true);

		await wrapper.find("[data-test=tinting-job]").setValue("J-1");
		await amounts(wrapper).header.setValue("0");
		expect(await save(wrapper)).toBeUndefined();
	});

	it("reopens with what was filled, or the bare total of a reloaded line", async () => {
		let wrapper = await open({
			job: "J-1",
			hpp_tinta: 2500,
			tinta: [{ item_code: "PRP-YEL", addon_group: "Tinta Propan", item_name: "Y", amount: 2500 }],
		});
		expect(wrapper.find("[data-test=tinting-job]").element.value).toBe("J-1");
		expect(amounts(wrapper).yellow.element.value).toBe("2,500");

		wrapper = await open({ job: "J-2", hpp_tinta: 12000 });
		expect(amounts(wrapper).header.element.value).toBe("12,000");
	});

	it("removes the tinta", async () => {
		const wrapper = await open({ job: "J-1", hpp_tinta: 100, tinta: [] });
		await wrapper.findAll("button").find((b) => b.text() === "Hapus Tinta").trigger("click");
		expect(wrapper.emitted("save").at(-1)[0]).toBeNull();
	});

	it("shows the selling price and saves a changed open price", async () => {
		const wrapper = await open();
		const rate = wrapper.find("[data-test=tinting-rate]");
		expect(rate.element.value).toBe("60,000");
		expect(rate.element.readOnly).toBe(false);
		await fill(wrapper);
		expect(await save(wrapper, 1)).toBeNull();

		await rate.setValue("75000");
		expect(rate.element.value).toBe("75,000");
		expect(await save(wrapper, 1)).toBe(75000);
	});

	it("rejects an open price of 0", async () => {
		const wrapper = await open();
		await fill(wrapper);
		await wrapper.find("[data-test=tinting-rate]").setValue("0");
		expect(await save(wrapper)).toBeUndefined();
		expect(wrapper.find("[data-test=tinting-error]").text()).toContain("Harga jual");
	});

	it("keeps the price read-only for a non open price item or a promotion", async () => {
		for (const item of [{ item_code: "OTHER" }, { pricing_rules: "PR-1" }, { pricing_rules: ["PR-1"] }]) {
			const wrapper = await open(null, item);
			const rate = wrapper.find("[data-test=tinting-rate]");
			expect(rate.element.readOnly).toBe(true);
			await rate.setValue("1");
			await fill(wrapper);
			expect(await save(wrapper, 1)).toBeNull();
		}
	});
});
