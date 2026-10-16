import { describe, expect, it } from "vitest";

import { formatAmountInput, parseAmountInput } from "@/utils/amountInput";

describe("formatAmountInput", () => {
	it("groups thousands as the POS shows money", () => {
		expect(formatAmountInput("15000")).toBe("15,000");
		expect(formatAmountInput("1234567")).toBe("1,234,567");
		expect(formatAmountInput("999")).toBe("999");
	});

	it("re-formats text that is already grouped or has stray characters", () => {
		expect(formatAmountInput("15,0000")).toBe("150,000");
		expect(formatAmountInput("Rp 2.500")).toBe("2.50");
		expect(formatAmountInput("abc")).toBe("");
		expect(formatAmountInput("")).toBe("");
		expect(formatAmountInput(null)).toBe("");
	});

	it("keeps a decimal part being typed, at most two digits", () => {
		expect(formatAmountInput("1500.")).toBe("1,500.");
		expect(formatAmountInput("1500.567")).toBe("1,500.56");
		expect(formatAmountInput("007")).toBe("7");
	});
});

describe("parseAmountInput", () => {
	it("reads formatted text back", () => {
		expect(parseAmountInput("15,000")).toBe(15000);
		expect(parseAmountInput("1,500.5")).toBe(1500.5);
		expect(parseAmountInput("")).toBe(0);
		expect(parseAmountInput("x")).toBe(0);
		expect(parseAmountInput(undefined)).toBe(0);
	});
});
