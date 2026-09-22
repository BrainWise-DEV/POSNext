/**
 * Offline expense queue helpers — behaviour checks for save/count/delete/limits.
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/utils/apiWrapper", () => ({
	call: vi.fn(),
}));

vi.mock("@/utils/logger", () => ({
	logger: {
		create: () => ({
			info: vi.fn(),
			debug: vi.fn(),
			error: vi.fn(),
			warn: vi.fn(),
			success: vi.fn(),
		}),
	},
}));

vi.mock("@/utils/offline/offlineState", () => ({
	offlineState: {
		isOffline: false,
		setServerOnline: vi.fn(),
	},
}));

const expenseRows = new Map();
let nextId = 1;

vi.mock("@/utils/offline/db", () => {
	const expense_queue = {
		async add(row) {
			const id = nextId++;
			expenseRows.set(id, { ...row, id });
			return id;
		},
		async get(id) {
			return expenseRows.get(id) || null;
		},
		async delete(id) {
			expenseRows.delete(id);
		},
		async update(id, patch) {
			const row = expenseRows.get(id);
			if (row) expenseRows.set(id, { ...row, ...patch });
		},
		filter(predicate) {
			const rows = [...expenseRows.values()].filter(predicate);
			return {
				async toArray() {
					return rows;
				},
				async count() {
					return rows.length;
				},
				async delete() {
					for (const row of rows) expenseRows.delete(row.id);
				},
			};
		},
		where() {
			return {
				equals() {
					return {
						async first() {
							return null;
						},
					};
				},
			};
		},
	};

	return {
		db: { expense_queue, invoice_queue: expense_queue, settings: { get: async () => null } },
		getSetting: async () => null,
		setSetting: async () => true,
	};
});

import {
	deleteOfflineExpense,
	expenseDialogCacheKey,
	getOfflineExpenseRemainingAllowance,
	getPendingExpenseCount,
	getPendingExpenseLocalTotal,
	saveOfflineExpense,
	validateExpenseQueueAttachment,
} from "@/utils/offline/sync";

describe("offline expense queue helpers", () => {
	beforeEach(() => {
		expenseRows.clear();
		nextId = 1;
	});

	it("saveOfflineExpense assigns pos_expense_* offline_id and stores blobs", async () => {
		const blob = new Blob(["hello"], { type: "text/plain" });
		const result = await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 10,
				mode_of_payment: "Cash",
				remarks: "Taxi",
			},
			[{ name: "r.txt", type: "text/plain", size: 5, blob }],
			{ maximum_expense_amount: 100, shift_expense_total: 0, max_file_size: 1024 },
		);

		expect(result.success).toBe(true);
		expect(result.offline_id).toMatch(/^pos_expense_/);
		const row = expenseRows.get(result.id);
		expect(row.synced).toBe(false);
		expect(row.attachments).toHaveLength(1);
		expect(row.attachments[0].blob).toBe(blob);
	});

	it("getPendingExpenseCount ignores synced rows", async () => {
		await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 5,
				mode_of_payment: "Cash",
				remarks: "A",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 0 },
		);
		const id2 = await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 5,
				mode_of_payment: "Cash",
				remarks: "B",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 5 },
		);
		expenseRows.set(id2.id, { ...expenseRows.get(id2.id), synced: true });

		expect(await getPendingExpenseCount()).toBe(1);
	});

	it("deleteOfflineExpense removes only unsynced id", async () => {
		const saved = await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 5,
				mode_of_payment: "Cash",
				remarks: "Del",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 0 },
		);
		await deleteOfflineExpense(saved.id);
		expect(expenseRows.has(saved.id)).toBe(false);
	});

	it("rejects invalid file type", () => {
		expect(
			validateExpenseQueueAttachment({ name: "x.exe", size: 10 }, 1024),
		).toMatch(/not allowed/i);
	});

	it("rejects queue save when max missing", async () => {
		await expect(
			saveOfflineExpense(
				{
					pos_opening_shift: "SHIFT-1",
					pos_profile: "PROFILE-1",
					expense_account: "Travel - TC",
					amount: 5,
					mode_of_payment: "Cash",
					remarks: "No max",
				},
				[],
				{ maximum_expense_amount: 0, shift_expense_total: 0 },
			),
		).rejects.toThrow(/not configured/i);
	});

	it("rejects queue save when amount exceeds remaining incl. pending", async () => {
		await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 80,
				mode_of_payment: "Cash",
				remarks: "First",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 0 },
		);

		await expect(
			saveOfflineExpense(
				{
					pos_opening_shift: "SHIFT-1",
					pos_profile: "PROFILE-1",
					expense_account: "Travel - TC",
					amount: 30,
					mode_of_payment: "Cash",
					remarks: "Over",
				},
				[],
				{ maximum_expense_amount: 100, shift_expense_total: 0 },
			),
		).rejects.toThrow(/exceeds/i);
	});

	it("getOfflineExpenseRemainingAllowance subtracts pending", () => {
		expect(
			getOfflineExpenseRemainingAllowance({
				maximumExpenseAmount: 100,
				shiftExpenseTotal: 20,
				pendingLocalTotal: 30,
			}),
		).toBe(50);
	});

	it("expense dialog cache key is scoped to profile and shift", () => {
		expect(expenseDialogCacheKey("PROFILE-1", "SHIFT-A")).toBe(
			"expense_dialog_cache:PROFILE-1:SHIFT-A",
		);
		expect(expenseDialogCacheKey("PROFILE-1", "SHIFT-A")).not.toBe(
			expenseDialogCacheKey("PROFILE-1", "SHIFT-B"),
		);
	});

	it("deleteOfflineExpense refuses rows with server_journal_entry", async () => {
		const saved = await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 5,
				mode_of_payment: "Cash",
				remarks: "Posted",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 0 },
		);
		expenseRows.set(saved.id, {
			...expenseRows.get(saved.id),
			server_journal_entry: "ACC-JV-1",
		});

		await expect(deleteOfflineExpense(saved.id)).rejects.toThrow(/already created/i);
		expect(expenseRows.has(saved.id)).toBe(true);
	});

	it("pending local total still counts JE rows until cache_counted", async () => {
		const saved = await saveOfflineExpense(
			{
				pos_opening_shift: "SHIFT-1",
				pos_profile: "PROFILE-1",
				expense_account: "Travel - TC",
				amount: 40,
				mode_of_payment: "Cash",
				remarks: "Partial",
			},
			[],
			{ maximum_expense_amount: 100, shift_expense_total: 0 },
		);
		expenseRows.set(saved.id, {
			...expenseRows.get(saved.id),
			server_journal_entry: "ACC-JV-2",
			cache_counted: false,
		});

		expect(await getPendingExpenseLocalTotal("SHIFT-1")).toBe(40);

		expenseRows.set(saved.id, {
			...expenseRows.get(saved.id),
			cache_counted: true,
		});
		expect(await getPendingExpenseLocalTotal("SHIFT-1")).toBe(0);
	});
});
