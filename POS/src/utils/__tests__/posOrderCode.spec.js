import { describe, it, expect } from "vitest";

import { orderFromQrPayload, parsePosOrderCode } from "@/utils/posOrderCode";

// Payload as built by nextend.pos_order.build_qr_payload (trailing empty columns dropped).
const QR =
	'{"c":"HEMAT","d":500,"i":[["BASE",0,2,"Nos",9000,10000,2000,10,1,0,"","k1"],' +
	'["ADDON-TINTING",0,1,"Nos",5000,5000,0,0,1,0,"TINTA-A","","k1"],["GRATIS",1,1,"Nos",0,0,0,0,1,1],' +
	'["CAT",0,1,"Nos",1000,1000,0,0,1,0,"","","","warna biru"],' +
	'["ADDON-TINTING",0,1,"Nos",25000,25000,0,0,1,0,"","","k1","","Tinta Propan"]],' +
	'"o":"SPO-260927-0001","sh":"POSA-OS-26-0000004","sp":"SPG A","v":1,"w":["DKB - PT","DKB - CV"]}';

describe("parsePosOrderCode", () => {
	it("recognises a typed order number", () => {
		expect(parsePosOrderCode(" spo-260927-0001 ")).toEqual({
			name: "SPO-260927-0001",
			payload: null,
		});
	});

	it("recognises the order QR", () => {
		const code = parsePosOrderCode(QR);
		expect(code.name).toBe("SPO-260927-0001");
		expect(code.payload.i).toHaveLength(5);
	});

	it("leaves ordinary barcodes and foreign JSON alone", () => {
		expect(parsePosOrderCode("8991234567890")).toBeNull();
		expect(parsePosOrderCode('{"o":"SPO-260927-0001"}')).toBeNull();
		expect(parsePosOrderCode("{not json")).toBeNull();
	});
});

describe("orderFromQrPayload", () => {
	it("expands rows with warehouse index and default columns", () => {
		const order = orderFromQrPayload(parsePosOrderCode(QR).payload);

		expect(order).toMatchObject({
			name: "SPO-260927-0001",
			pos_opening_shift: "POSA-OS-26-0000004",
			sales_person: "SPG A",
			discount_amount: 500,
			coupon_code: "HEMAT",
		});
		expect(order.items[0]).toMatchObject({
			item_code: "BASE",
			warehouse: "DKB - PT",
			qty: 2,
			rate: 9000,
			price_list_rate: 10000,
			discount_amount: 2000,
			discount_percentage: 10,
			addon_key: "k1",
			addon_parent_key: null,
		});
		expect(order.items[1]).toMatchObject({ addon_item: "TINTA-A", addon_parent_key: "k1" });
		expect(order.items[2]).toMatchObject({
			warehouse: "DKB - CV",
			is_free_item: 1,
			rate: 0,
			keterangan: "",
		});
		expect(order.items[3]).toMatchObject({
			item_code: "CAT",
			keterangan: "warna biru",
			addon_group: null,
		});
		// Gelondongan: no tinta, the group sits in the last column.
		expect(order.items[4]).toMatchObject({
			addon_item: null,
			addon_parent_key: "k1",
			addon_group: "Tinta Propan",
		});
	});

	it("carries the delivery the SPG chose, none when the goods are taken along", () => {
		const payload = parsePosOrderCode(QR).payload;
		expect(orderFromQrPayload(payload)).toMatchObject({ dikirim: 0, alamat_kirim: "" });
		expect(orderFromQrPayload({ ...payload, k: "Jl. Kenanga 14", kc: "sore" })).toMatchObject({
			dikirim: 1,
			alamat_kirim: "Jl. Kenanga 14",
			catatan_kirim: "sore",
		});
	});
});
