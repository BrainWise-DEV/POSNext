import { beforeEach, describe, expect, it, vi } from "vitest";

// Minimal in-memory IndexedDB: just what draftManager uses (keyPath "id" with
// autoIncrement, and a unique "draft_id" index).
function installFakeIndexedDB() {
	const rows = new Map();
	let nextId = 1;
	const respond = (compute) => {
		const request = {};
		queueMicrotask(() => {
			try {
				request.result = compute();
				request.onsuccess?.({ target: request });
			} catch (error) {
				request.error = error;
				request.onerror?.({ target: request });
			}
		});
		return request;
	};
	const store = {
		add: (draft) =>
			respond(() => {
				const stored = { ...draft, id: nextId++ };
				rows.set(stored.id, stored);
				return stored.id;
			}),
		put: (draft) =>
			respond(() => {
				rows.set(draft.id, { ...draft });
				return draft.id;
			}),
		delete: (id) => respond(() => rows.delete(id)),
		index: () => ({
			get: (draftId) => respond(() => [...rows.values()].find((r) => r.draft_id === draftId)),
		}),
	};
	const database = {
		objectStoreNames: { contains: () => true },
		transaction: () => ({ objectStore: () => store }),
	};
	globalThis.indexedDB = {
		open: () => {
			const request = {};
			queueMicrotask(() => {
				request.result = database;
				request.onsuccess?.({ target: request });
			});
			return request;
		},
	};
	return rows;
}

describe("draftManager update/delete (no async Promise executors)", () => {
	let rows;
	let manager;

	beforeEach(async () => {
		vi.resetModules();
		rows = installFakeIndexedDB();
		manager = await import("../draftManager");
	});

	it("updates an existing draft and keeps its other fields", async () => {
		const saved = await manager.saveDraft({ customer: "C1", items: [{ item_code: "A" }] });
		const updated = await manager.updateDraft(saved.draft_id, { customer: "C2" });

		expect(updated.customer).toBe("C2");
		expect(updated.items).toEqual([{ item_code: "A" }]);
		expect(updated.draft_id).toBe(saved.draft_id);
		expect([...rows.values()].find((r) => r.draft_id === saved.draft_id).customer).toBe("C2");
	});

	it("rejects when updating a draft that does not exist", async () => {
		await expect(manager.updateDraft("missing", { customer: "C" })).rejects.toThrow("Draft not found");
	});

	it("deletes an existing draft", async () => {
		const saved = await manager.saveDraft({ customer: "C1" });
		await expect(manager.deleteDraft(saved.draft_id)).resolves.toBe(true);
		expect(rows.size).toBe(0);
	});

	it("rejects when deleting a draft that does not exist", async () => {
		await expect(manager.deleteDraft("missing")).rejects.toThrow("Draft not found");
	});

	it("rejects (not hangs) when the data cannot be serialised", async () => {
		const saved = await manager.saveDraft({ customer: "C1" });
		const circular = {};
		circular.self = circular;
		await expect(manager.updateDraft(saved.draft_id, circular)).rejects.toThrow();
	});
});
