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

function respond(preview, brands = ["NIPPON", "PROPAN", ""]) {
	call.mockImplementation(async (method) => {
		if (method.endsWith("list_uploads"))
			return [
				{ name: "PMT-0001", brand: "PROPAN", status: "Ada Pending", rows: 2, pending: 1, can_cancel: false },
				{ name: "PMT-0002", status: "Diajukan", rows: 1, pending: 0, can_cancel: true },
			];
		if (method.endsWith("get_template_brands")) return brands;
		if (method.endsWith("preview_upload")) return preview;
		if (method.endsWith("submit_upload")) return "PMT-0003";
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

function brandSelect(wrapper) {
	return wrapper.findAll("select")[1];
}

async function chooseFile(wrapper, { periode = true, brand = "PROPAN" } = {}) {
	if (brand !== null) await brandSelect(wrapper).setValue(brand);
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

function batalkan(wrapper) {
	return wrapper.findAll("button").filter((b) => b.text() === "Batalkan");
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
		expect(wrapper.text()).toContain("PROPAN ·");
		expect(wrapper.text()).toContain("(Tanpa Brand) ·");
	});

	it("lists the warehouse brands and needs one before the template downloads", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.get_template_brands", { warehouse: "WH B" });
		const options = brandSelect(wrapper).findAll("option").map((o) => o.text());
		expect(options).toEqual(["Pilih brand", "NIPPON", "PROPAN", "(Tanpa Brand)"]);
		expect(wrapper.find("a").exists()).toBe(false);

		await brandSelect(wrapper).setValue("NIPPON");
		expect(wrapper.find("a").attributes("href")).toContain("download_template?warehouse=WH%20B&brand=NIPPON");
		await brandSelect(wrapper).setValue("");
		expect(wrapper.find("a").attributes("href")).toMatch(/&brand=$/);
	});

	it("picks the only brand by itself", async () => {
		respond(PREVIEW_OK, ["AVIAN"]);
		const wrapper = await open();
		expect(wrapper.find("a").attributes("href")).toContain("&brand=AVIAN");
	});

	it("says when the warehouse has no tinta", async () => {
		respond(PREVIEW_OK, []);
		const wrapper = await open();
		expect(wrapper.text()).toContain("Belum ada tinta add on");
	});

	it("asks for the period before reading a file", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		await chooseFile(wrapper, { periode: false });
		expect(globalThis.fetch).not.toHaveBeenCalled();
		expect(wrapper.text()).toContain("Pilih brand dan isi periode");
	});

	it("asks for the brand before reading a file", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		await chooseFile(wrapper, { brand: null });
		expect(globalThis.fetch).not.toHaveBeenCalled();
		expect(wrapper.text()).toContain("Pilih brand dan isi periode");
	});

	it("previews the file and submits it", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		await chooseFile(wrapper);

		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.preview_upload", {
			warehouse: "WH B",
			brand: "PROPAN",
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

	it("offers Batalkan only on uploads the server allows to withdraw", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		expect(batalkan(wrapper)).toHaveLength(1);

		globalThis.confirm = vi.fn(() => false);
		await batalkan(wrapper)[0].trigger("click");
		expect(call).not.toHaveBeenCalledWith("nextend.pemakaian_tinta.cancel_upload", expect.anything());

		globalThis.confirm = vi.fn(() => true);
		call.mockClear();
		await batalkan(wrapper)[0].trigger("click");
		await flushPromises();
		expect(call.mock.calls.map(([m]) => m)).toEqual([
			"nextend.pemakaian_tinta.cancel_upload",
			"nextend.pemakaian_tinta.list_uploads",
			"nextend.pemakaian_tinta.get_template_brands",
		]);
		expect(call).toHaveBeenCalledWith("nextend.pemakaian_tinta.cancel_upload", { name: "PMT-0002" });
	});

	it("shows why a withdraw failed", async () => {
		respond(PREVIEW_OK);
		const wrapper = await open();
		call.mockImplementation(async () => {
			throw new Error("Hanya upload berstatus Diajukan yang bisa dibatalkan dari POS.");
		});
		globalThis.confirm = vi.fn(() => true);
		await batalkan(wrapper)[0].trigger("click");
		await flushPromises();
		expect(wrapper.text()).toContain("Hanya upload berstatus Diajukan");
	});
});
