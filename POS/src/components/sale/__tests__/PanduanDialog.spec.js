// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => call(...args) }));
vi.mock("frappe-ui", () => ({
	Dialog: { template: "<div><slot name='body-content' /></div>" },
}));
globalThis.__ = (s) => String(s);

import PanduanDialog from "@/components/sale/PanduanDialog.vue";

const CATEGORIES = [
	{ label: "Fitur", entries: [{ name: "add-on-item", title: "Add On Item", published: 1 }] },
];

function mountDialog(props = {}) {
	return mount(PanduanDialog, {
		props: { modelValue: true, categories: [], ...props },
		global: { mocks: { __: globalThis.__ } },
	});
}

describe("PanduanDialog", () => {
	beforeEach(() => {
		call.mockReset();
	});

	it("lists the docs and opens one read-only", async () => {
		call.mockResolvedValue({ name: "add-on-item", title: "Add On Item", html: "<p>Isi panduan</p>" });
		const wrapper = mountDialog({ categories: CATEGORIES });
		expect(wrapper.text()).toContain("Fitur");

		await wrapper.find("button").trigger("click");
		await flushPromises();

		expect(call).toHaveBeenCalledWith("nextend.panduan.read_doc", { name: "add-on-item" });
		expect(wrapper.find(".panduan-article").html()).toContain("Isi panduan");
		expect(wrapper.find("input, textarea, [contenteditable]").exists()).toBe(false);
	});

	it("shows an empty state when the user may read no doc", () => {
		expect(mountDialog().text()).toContain("Belum ada panduan.");
	});

	it("shows loading instead of the empty state", () => {
		const text = mountDialog({ loading: true }).text();
		expect(text).toContain("Memuat...");
		expect(text).not.toContain("Belum ada panduan.");
	});

	it("shows the load error instead of the empty state", () => {
		const text = mountDialog({ loadError: "Panduan tidak bisa dimuat." }).text();
		expect(text).toContain("Panduan tidak bisa dimuat.");
		expect(text).not.toContain("Belum ada panduan.");
	});

	it("shows an error when a doc cannot be opened", async () => {
		const wrapper = mountDialog({ categories: CATEGORIES });
		call.mockImplementation(async () => {
			throw new Error("Dokumentasi add-on-item tidak ditemukan.");
		});

		await wrapper.find("button").trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("tidak ditemukan");
		expect(wrapper.find(".panduan-article").exists()).toBe(false);
	});
});
