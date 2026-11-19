/**
 * Unit picker lists each unit once; variant picker marks out-of-stock chips and pre-selects stock.
 * @vitest-environment jsdom
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import ItemSelectionDialog from "../ItemSelectionDialog.vue";
import { getDistinctUoms } from "@/utils/itemUoms";

vi.hoisted(() => {
	globalThis.__ = (s, args) => s.replace(/{(\d+)}/g, (_, n) => args?.[n] ?? _);
});

vi.mock("frappe-ui", () => ({
	Button: { template: "<button><slot /></button>" },
	Dialog: { template: "<div><slot name='body-content' /><slot name='actions' /></div>" },
	createResource: () => ({ reload: vi.fn() }),
}));
vi.mock("@/utils/offline/offlineState", () => ({ offlineState: { isOffline: false } }));
vi.mock("@/utils/offline/items", () => ({ getCachedVariants: vi.fn(), cacheItems: vi.fn() }));

const mountDialog = (props) =>
	mount(ItemSelectionDialog, { props: { modelValue: false, ...props }, global: { mocks: { __: globalThis.__ } } });

describe("unit picker", () => {
	const oreo = { item_code: "EG-1135", stock_uom: "Nos", rate: 13.95, item_uoms: [{ uom: "Nos", conversion_factor: 1 }] };

	it("counts the stock unit once", () => {
		expect(getDistinctUoms(oreo).map((u) => u.uom)).toEqual(["Nos"]);
		const box = { ...oreo, item_uoms: [...oreo.item_uoms, { uom: "Box", conversion_factor: 12 }] };
		expect(getDistinctUoms(box).map((u) => u.uom)).toEqual(["Nos", "Box"]);
	});

	it("lists each unit once in the dialog", () => {
		const state = mountDialog({ item: { ...oreo, item_uoms: [...oreo.item_uoms, { uom: "Box", conversion_factor: 12 }] } }).vm.$.setupState;
		state.loadOptions();
		expect(state.options.map((o) => o.label)).toEqual(["Nos", "Box"]);
	});
});

describe("variant picker", () => {
	const variant = (code, Color, Storage, actual_qty, rate) => ({ item_code: code, item_name: code, attributes: { Color, Storage }, actual_qty, rate, stock_uom: "Nos" });
	const variants = [
		variant("BLUE-256", "Blue", "256", 0, 77699),
		variant("BLUE-512", "Blue", "512", 3, 93899),
		variant("WHITE-256", "White", "256", 2, 77699),
	];

	async function openWithVariants() {
		const wrapper = mountDialog({ item: { item_code: "EG-1204" }, mode: "variant" });
		const state = wrapper.vm.$.setupState;
		state.options = state.mapVariantsToOptions(variants);
		await nextTick();
		return state;
	}

	it("pre-selects the first in-stock combination", async () => {
		const state = await openWithVariants();
		expect(state.selectedAttributes).toEqual({ Color: "Blue", Storage: "512" });
		expect(state.selectedOption.item_code).toBe("BLUE-512");
	});

	it("marks chips that cannot form an in-stock combination with the current pick", async () => {
		const state = await openWithVariants();
		expect(state.isChipInStock("Color", "Blue")).toBe(true);
		expect(state.isChipInStock("Color", "White")).toBe(false);
		expect(state.isChipInStock("Storage", "256")).toBe(false);
		expect(state.resolveChip("Storage", "256").item_code).toBe("BLUE-256");
	});

	it("re-picks the other attributes when a chip has no combination with them", async () => {
		const state = await openWithVariants();
		state.selectAttribute("Color", "White");
		expect(state.selectedAttributes).toEqual({ Color: "White", Storage: "256" });
	});

	it("maps common colour names to a swatch only for colour attributes", async () => {
		const state = await openWithVariants();
		expect(state.swatchColor("Color", "Blue")).toBeTruthy();
		expect(state.swatchColor("اللون", "ابيض")).toBe("#ffffff");
		expect(state.swatchColor("Storage", "Blue")).toBe(null);
		expect(state.swatchColor("Color", "Midnight Galaxy")).toBe(null);
	});
});
