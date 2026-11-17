import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), data: null }),
	call: vi.fn(),
}));
vi.mock("@/utils/offline", () => ({ isOffline: () => true, getCachedItem: vi.fn() }));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}));

const { useInvoice } = await import("../useInvoice");
const { stripFriendsAndFamilyForOrder } = await import("@/utils/friendsAndFamily");

const FNF_KEYS = [
	"posnext_discount_source",
	"posnext_fnf_program",
	"posnext_fnf_percentage",
	"posnext_fnf_discount_amount",
	"posnext_fnf_replaced_discount",
];

function line(overrides = {}) {
	return {
		item_code: "A",
		item_name: "A",
		quantity: 1,
		rate: 70,
		price_list_rate: 100,
		uom: "Nos",
		discount_percentage: 0,
		discount_amount: 0,
		pricing_rules: [],
		...overrides,
	};
}

const fnfLine = (overrides = {}) =>
	line({
		discount_source: "friends_and_family",
		discount_percentage: 30,
		discount_amount: 30,
		fnf_discount_amount: 30,
		...overrides,
	});

describe("formatItemsForSubmission F&F markers", () => {
	beforeEach(() => setActivePinia(createPinia()));

	it("formats F&F markers only on F&F lines", () => {
		const { formatItemsForSubmission } = useInvoice();
		const rows = formatItemsForSubmission([
			fnfLine({ posnext_fnf_program: "Staff", posnext_fnf_percentage: 30 }),
			fnfLine({ item_code: "B" }),
			line({ item_code: "C", discount_source: "pricing_rule", pricing_rules: ["PR-1"] }),
			line({
				item_code: "D",
				is_free_item: 1,
				pricing_rules: ["GIFT-1"],
				discount_source: "free_item",
			}),
			line({ item_code: "E" }),
		]);

		expect(rows[0]).toMatchObject({
			posnext_discount_source: "friends_and_family",
			posnext_fnf_program: "Staff",
			posnext_fnf_percentage: 30,
		});
		// The cart holds no program / % for this line: only the source is sent.
		expect(rows[1].posnext_discount_source).toBe("friends_and_family");
		expect(rows[1]).not.toHaveProperty("posnext_fnf_program");
		expect(rows[1]).not.toHaveProperty("posnext_fnf_percentage");
		// The server derives amounts; the client never sends them as authority.
		for (const row of rows) {
			expect(row).not.toHaveProperty("posnext_fnf_discount_amount");
			expect(row).not.toHaveProperty("posnext_fnf_replaced_discount");
		}
		for (const row of rows.slice(2)) {
			for (const key of FNF_KEYS) expect(row).not.toHaveProperty(key);
		}
		// Gift rows keep their rule names.
		expect(rows[3].pricing_rules).toBe("GIFT-1");
	});

	it("gives a synthesized free row no F&F markers", () => {
		const { formatItemsForSubmission } = useInvoice();
		const rows = formatItemsForSubmission([fnfLine({ free_qty: 1, pricing_rules: ["BOGO"] })]);
		expect(rows).toHaveLength(2);
		expect(rows[1].is_free_item).toBe(1);
		for (const key of FNF_KEYS) expect(rows[1]).not.toHaveProperty(key);
	});

	it("sends no F&F markers on a Sales Order (strip runs first)", () => {
		const { formatItemsForSubmission } = useInvoice();
		const { items } = stripFriendsAndFamilyForOrder([
			fnfLine({ posnext_fnf_program: "Staff", posnext_fnf_percentage: 30 }),
		]);
		const [row] = formatItemsForSubmission(items);
		for (const key of FNF_KEYS) expect(row).not.toHaveProperty(key);
		expect(row.discount_percentage).toBe(0);
	});
});
