/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import { useSearchInput } from "@/composables/useSearchInput";

vi.hoisted(() => {
	globalThis.__ = (s, args) => s.replace(/{(\d+)}/g, (_, n) => args?.[n] ?? _);
});

const chipsy = { item_code: "CHIPSY", item_name: "شيبسي" };
const lays = { item_code: "LAYS", item_name: "ليز" };

function setup({ results = [chipsy], barcodeItem = null } = {}) {
	const itemStore = reactive({
		searchTerm: "",
		filteredItems: [],
		setSearchTerm: vi.fn((t) => {
			itemStore.searchTerm = t;
			itemStore.filteredItems = t ? results : [];
		}),
		clearSearch: vi.fn(() => {
			itemStore.searchTerm = "";
			itemStore.filteredItems = [];
		}),
		searchByBarcode: vi.fn(async () => barcodeItem),
	});
	const onItemFound = vi.fn(() => true);
	const showWarning = vi.fn();
	const search = useSearchInput({ itemStore, onItemFound, showWarning, isAnyDialogOpen: { value: false } });
	const input = document.createElement("input");
	document.body.appendChild(input);
	search.searchInputRef.value = input;
	const type = (text) => {
		input.value = text;
		search.handleSearchInput({ target: input });
	};
	const press = (key) => search.handleKeyDown(new KeyboardEvent("keydown", { key }));
	return { itemStore, onItemFound, showWarning, search, input, type, press };
}

describe("useSearchInput Enter on a name search", () => {
	it("adds the single visible result when the barcode lookup misses", async () => {
		const { onItemFound, showWarning, type, press } = setup();
		type("شيبسي");
		press("Enter");
		await vi.waitFor(() => expect(onItemFound).toHaveBeenCalledWith(chipsy, false));
		expect(showWarning).not.toHaveBeenCalled();
	});

	it("keeps the query and asks the cashier to pick when several results show", async () => {
		const { onItemFound, showWarning, type, press, input, itemStore } = setup({ results: [chipsy, lays] });
		type("chips");
		press("Enter");
		await vi.waitFor(() => expect(showWarning).toHaveBeenCalled());
		expect(showWarning.mock.calls[0][0]).toContain("chips");
		expect(onItemFound).not.toHaveBeenCalled();
		expect(input.value).toBe("chips");
		expect(itemStore.searchTerm).toBe("chips");
	});

	it("still adds a barcode hit", async () => {
		const { onItemFound, type, press } = setup({ results: [], barcodeItem: lays });
		type("6221");
		press("Enter");
		await vi.waitFor(() => expect(onItemFound).toHaveBeenCalledWith(lays, false));
	});

	it("tells the cashier what to do when nothing matches", async () => {
		const { showWarning, type, press } = setup({ results: [] });
		type("zzz");
		press("Enter");
		await vi.waitFor(() => expect(showWarning).toHaveBeenCalled());
		expect(showWarning.mock.calls[0][0]).toBe("No item matches «zzz». Search by name or scan the barcode again.");
	});
});

describe("useSearchInput keyboard navigation", () => {
	it("moves the highlight with the arrows and adds it on Enter", () => {
		const { search, onItemFound, type, press } = setup({ results: [chipsy, lays] });
		type("chips");
		press("ArrowDown");
		press("ArrowDown");
		expect(search.highlightedCode.value).toBe("LAYS");
		press("ArrowUp");
		expect(search.highlightedCode.value).toBe("CHIPSY");
		press("Enter");
		expect(onItemFound).toHaveBeenCalledWith(chipsy, false);
		expect(search.highlightedCode.value).toBe(null);
	});

	it("clears on Esc and selects the text on click instead of clearing", () => {
		const { search, itemStore, input, type, press } = setup();
		type("شيبسي");
		const select = vi.spyOn(input, "select");
		search.handleSearchClick();
		expect(select).toHaveBeenCalled();
		expect(itemStore.searchTerm).toBe("شيبسي");
		press("Escape");
		expect(itemStore.searchTerm).toBe("");
		expect(input.value).toBe("");
	});
});
