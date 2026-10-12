// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => call(...args) }));
vi.mock("frappe-ui", () => ({
	Dialog: { template: "<div><slot name='body-content' /></div>" },
	Button: {
		props: ["disabled", "loading"],
		template: "<button :disabled=\"disabled\" @click=\"$emit('click')\"><slot /></button>",
		emits: ["click"],
	},
}));
globalThis.__ = (s, args = []) => String(s).replace(/\{(\d+)\}/g, (_, i) => args[i]);

import PemakaianTintaDialog from "@/components/sale/PemakaianTintaDialog.vue";

const PREVIEW_OK = {
	errors: [],
	rows: [
		{ row_no: 2, item_code: "PRP-YEL", item_name: "Yellow", qty: 3, stock_uom: "Liter", status: "ok", messages: [] },
		{ row_no: 3, item_code: "PRP-RED", item_name: "Red", qty: 9, stock_uom: "Liter", status: "warning",
			messages: ["Stok saat ini 2 Liter, kurang dari pemakaian - akan Pending."] },
	],
	summary: { ok: 1, warning: 1, error: 0 },
	can_submit: true,
};
const PREVIEW_BAD = {
	errors: ["Periode beririsan dengan upload lain di gudang ini: PMT-0001"],
	rows: [{ row_no: 2, item_code: "XX", qty: false, status: "error", messages: ["Item XX tidak ditemukan."] }],
	summary: { ok: 0, warning: 0, error: 1 },
	can_submit: false,
};

function respond(preview) {
	call.mockImplementation(async (method) => {
		if (method.endsWith("list_uploads")) return [{ name: "PMT-0001", status: "Ada Pending", rows: 2, pending: 1 }];
		if (method.endsWith("preview_upload")) return preview;
		if (method.endsWith("submit_upload")) return "PMT-0002";
	});
}

async function open() {
	const wrapper = mount(PemakaianTintaDialog, {
		props: { modelValue: false, warehouses: ["WH A", "WH B"], defaultWarehouse: "WH B" },
		global: { mocks: { __: globalThis.__ } },
	});
	await wrapper.setProps({ modelValue: true });
	await flushPromises();
	return wrapper;
}

async function chooseFile(wrapper, { periode = true } = {}) {
	const dates = wrapper.findAll("input[type=date]");
	if (periode) {
		await dates[0].setValue("2026-09-01");
		await dates[1].setValue("2026-09-30");
	}
	const input = wrapper.find("input[type=file]");
	Object.defineProperty(input.element, "files", {
		value: [new File(["x"], "pakai.xlsx")],
		configurable: true,
	});
	await input.trigger("change");
	await flushPromises();
}

function ajukan(wrapper) {
	return wrapper.findAll("button").find((b) => b.text() === "Ajukan");
}

describe("PemakaianTintaDialog", () => {
	beforeEach(() => {
		call.mockReset();
		globalThis.fetch = vi.fn(async () => ({
			ok: true,
			json: async () => ({ message: { file_url: "/private/files/pakai.xlsx" } }),
		}));
	});

	it("opens on the shift warehouse with its upload history and template link", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		expect(wrapper.find("select").element.value).toBe("WH B");
		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.list_uploads", { warehouse: "WH B" });
		expect(wrapper.text()).toContain("PMT-0001");
		expect(wrapper.text()).toContain("1 pending");
		expect(wrapper.find("a").attributes("href")).toContain("download_template?warehouse=WH%20B");
	});

	it("asks for the period before reading a file", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		await chooseFile(wrapper, { periode: false });
		expect(globalThis.fetch).not.toHaveBeenCalled();
		expect(wrapper.text()).toContain("Isi periode dulu");
	});

	it("previews the file and submits it", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		await chooseFile(wrapper);

		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.preview_upload", {
			warehouse: "WH B",
			periode_dari: "2026-09-01",
			periode_sampai: "2026-09-30",
			file_url: "/private/files/pakai.xlsx",
		});
		expect(wrapper.text()).toContain("akan Pending");
		expect(ajukan(wrapper).element.disabled).toBe(false);

		await ajukan(wrapper).trigger("click");
		await flushPromises();
		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.submit_upload", expect.objectContaining({
			file_url: "/private/files/pakai.xlsx",
		}));
		expect(ajukan(wrapper)).toBeUndefined(); // preview cleared
	});

	it("blocks submitting while the preview has errors", async () => {
		respond(PREVIEW_BAD);
		const wrapper = await open();
		await chooseFile(wrapper);
		expect(wrapper.text()).toContain("Periode beririsan");
		expect(wrapper.text()).toContain("tidak ditemukan");
		expect(ajukan(wrapper).element.disabled).toBe(true);
	});

	it("shows a failed upload instead of a preview", async () => {
		respond(PREVIEW_OK);
		globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({ exception: "Too big" }) }));
		const wrapper = await open();
		await chooseFile(wrapper);
		expect(wrapper.text()).toContain("Too big");
		expect(ajukan(wrapper)).toBeUndefined();
	});
});
