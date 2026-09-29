import { beforeEach, describe, expect, it, vi } from "vitest";

const callMock = vi.fn();
const offlineMock = vi.fn(() => false);
const cachedMock = vi.fn(async () => [{ name: "SP-CACHED" }]);

vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => callMock(...args) }));
vi.mock("@/utils/offline/offlineState", () => ({ isOffline: () => offlineMock() }));
vi.mock("@/utils/offline/cache", () => ({
	getCachedSalesPersons: (...args) => cachedMock(...args),
}));

import {
	clearSalesPersonsSessionCache,
	loadSalesPersonsForProfile,
} from "@/utils/salesPersonsList";

describe("loadSalesPersonsForProfile", () => {
	beforeEach(() => {
		clearSalesPersonsSessionCache();
		callMock.mockReset();
		offlineMock.mockReset();
		offlineMock.mockReturnValue(false);
		cachedMock.mockClear();
	});

	it("fetches from the server once per profile and reuses the list", async () => {
		callMock.mockResolvedValue([{ name: "SP-1" }]);

		const first = await loadSalesPersonsForProfile("POS-A");
		const second = await loadSalesPersonsForProfile("POS-A");

		expect(first).toEqual([{ name: "SP-1" }]);
		expect(second).toBe(first);
		expect(callMock).toHaveBeenCalledTimes(1);
		expect(callMock).toHaveBeenCalledWith("pos_next.api.pos_profile.get_sales_persons", {
			pos_profile: "POS-A",
		});
	});

	it("dedupes concurrent loads", async () => {
		callMock.mockResolvedValue([{ name: "SP-1" }]);
		await Promise.all([loadSalesPersonsForProfile("POS-A"), loadSalesPersonsForProfile("POS-A")]);
		expect(callMock).toHaveBeenCalledTimes(1);
	});

	it("keeps a separate list per profile", async () => {
		callMock.mockResolvedValueOnce([{ name: "SP-A" }]).mockResolvedValueOnce([{ name: "SP-B" }]);
		expect(await loadSalesPersonsForProfile("POS-A")).toEqual([{ name: "SP-A" }]);
		expect(await loadSalesPersonsForProfile("POS-B")).toEqual([{ name: "SP-B" }]);
	});

	it("uses the IndexedDB copy offline without calling the server", async () => {
		offlineMock.mockReturnValue(true);
		expect(await loadSalesPersonsForProfile("POS-A")).toEqual([{ name: "SP-CACHED" }]);
		expect(callMock).not.toHaveBeenCalled();
		expect(cachedMock).toHaveBeenCalledWith("POS-A");
	});

	it("falls back to the IndexedDB copy on server error and retries next time", async () => {
		const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
		callMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce([{ name: "SP-1" }]);

		expect(await loadSalesPersonsForProfile("POS-A")).toEqual([{ name: "SP-CACHED" }]);
		expect(await loadSalesPersonsForProfile("POS-A")).toEqual([{ name: "SP-1" }]);
		expect(callMock).toHaveBeenCalledTimes(2);
		errorSpy.mockRestore();
	});

	it("returns an empty list without a profile", async () => {
		expect(await loadSalesPersonsForProfile("")).toEqual([]);
		expect(callMock).not.toHaveBeenCalled();
	});
});
