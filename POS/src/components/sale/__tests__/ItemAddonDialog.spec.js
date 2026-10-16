// @vitest-environment jsdom
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("frappe-ui", () => ({
	Dialog: { template: "<div><slot name='body-content' /><slot name='actions' /></div>" },
	Button: { template: "<button @click=\"$emit('click')\"><slot /></button>", emits: ["click"] },
	Input: { template: "<input />" },
}));
vi.mock("@/utils/currency", () => ({ formatCurrency: (n) => String(n) }));
vi.mock("@/utils/itemAddons", async (importOriginal) => ({
	...(await importOriginal()),
	getAvailableAddons: (_item, jenis) => ((globalThis.__addonJenis = jenis), {
		items: [
			{ item_code: "PRP-YEL", item_name: "Propan Yellow", addon_group: "Tinta Propan" },
			{ item_code: "PRP-RED", item_name: "Propan Red", addon_group: "Tinta Propan" },
			{ item_code: "LOOSE", item_name: "Loose", addon_group: null },
			// In a group that is not offered gelondongan - listed on its own.
			{ item_code: "AVN-BLK", item_name: "Avian Black", addon_group: "Tinta Avian" },
		],
		groups: ["Tinta Propan"],
	}),
}));
globalThis.__ = (s) => s;

import ItemAddonDialog from "@/components/sale/ItemAddonDialog.vue";

const ITEM = { item_code: "BASE", item_name: "Base", warehouse: "W1" };

async function open(addons = []) {
	const wrapper = mount(ItemAddonDialog, {
		props: { modelValue: false, item: { ...ITEM, addons } },
		global: { mocks: { __: (s) => s } },
	});
	await wrapper.setProps({ modelValue: true });
	return wrapper;
}

// Price inputs in render order: group header, its members, then the loose tinta.
function inputs(wrapper) {
	const [header, yellow, red, loose, avian] = wrapper.findAll("input[type=number]");
	return { header, yellow, red, loose, avian };
}

async function save(wrapper) {
	await wrapper.findAll("button").at(-1).trigger("click");
	return wrapper.emitted("save").at(-1)[0];
}

describe("ItemAddonDialog", () => {
	it("offers the Add On Jual kind - tinta goes through the tinting dialog", async () => {
		await open();
		expect(globalThis.__addonJenis).toBe("Add On Jual");
	});

	it("nests members under their offered group and lists the rest flat", async () => {
		const wrapper = await open();
		expect(wrapper.findAll("input[type=number]")).toHaveLength(5);
		expect(wrapper.text()).toContain("Tinta Propan");
		expect(wrapper.text()).toContain("Gelondongan");
	});

	it("saves a gelondongan price as the group, without a tinta", async () => {
		const wrapper = await open();
		await inputs(wrapper).header.setValue("25000");
		expect(await save(wrapper)).toEqual([
			{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: 25000 },
		]);
	});

	it("locks members while the group has a price", async () => {
		const wrapper = await open();
		await inputs(wrapper).header.setValue("25000");
		const { yellow, red, loose } = inputs(wrapper);
		expect(yellow.element.disabled).toBe(true);
		expect(red.element.disabled).toBe(true);
		expect(loose.element.disabled).toBe(false);
	});

	it("locks the group at 0 once a member has a price, and sends only members", async () => {
		const wrapper = await open();
		await inputs(wrapper).yellow.setValue("5000");
		const { header } = inputs(wrapper);
		expect(header.element.disabled).toBe(true);
		expect(header.element.value).toBe("0");
		expect(await save(wrapper)).toEqual([
			{ item_code: "PRP-YEL", addon_group: "Tinta Propan", item_name: "Propan Yellow", amount: 5000 },
		]);
	});

	it("drops empty and zero prices", async () => {
		const wrapper = await open();
		const { red, loose, avian } = inputs(wrapper);
		await red.setValue("0");
		await loose.setValue("");
		await avian.setValue("3000");
		expect(await save(wrapper)).toEqual([
			{ item_code: "AVN-BLK", addon_group: "Tinta Avian", item_name: "Avian Black", amount: 3000 },
		]);
	});

	it("reopens with the prices already on the line", async () => {
		const wrapper = await open([
			{ item_code: null, addon_group: "Tinta Propan", item_name: "Tinta Propan", amount: 25000 },
			{ item_code: "LOOSE", addon_group: null, item_name: "Loose", amount: 1000 },
		]);
		const { header, yellow, loose } = inputs(wrapper);
		expect(header.element.value).toBe("25000");
		expect(yellow.element.disabled).toBe(true);
		expect(loose.element.value).toBe("1000");
		expect((await save(wrapper)).map((a) => a.amount)).toEqual([25000, 1000]);
	});
});
