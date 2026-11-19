import { afterAll, describe, expect, it } from "vitest"
import {
	DEFAULT_LOCALE,
	formatCurrency,
	formatCurrencyNumber,
	formatDate,
	formatDateTime,
	formatTime,
	getCurrencySymbol,
	setLocale,
} from "../currency"
import { useFormatters } from "../../composables/useFormatters"

const NO_ARABIC_DIGITS = /^[^\u0660-\u0669\u06F0-\u06F9]*$/

describe("locale formatting", () => {
	afterAll(() => setLocale("en"))

	it("follows the user's language and keeps en-US as the fallback", () => {
		setLocale(null)
		expect(DEFAULT_LOCALE).toBe("en-US")
		setLocale("ar")
		expect(DEFAULT_LOCALE).toBe("ar-EG-u-nu-latn")
		setLocale("pt-br")
		expect(DEFAULT_LOCALE).toBe("pt-BR-u-nu-latn")
	})

	it("formats Arabic dates with month names and Latin digits", () => {
		setLocale("ar")
		expect(formatDate("2026-11-05")).toBe("5 نوفمبر 2026")
		expect(formatTime("2026-11-05 21:15:00")).toBe("9:15 م")
		expect(formatTime("09:05:33.123")).toBe("9:05 ص")
		expect(formatDateTime("2026-11-05 21:15:00")).toBe("5 نوفمبر 2026، 9:15 م")
		expect(formatDateTime("2026-11-05 21:15:00")).toMatch(NO_ARABIC_DIGITS)
	})

	it("formats English dates unambiguously", () => {
		setLocale("en")
		expect(formatDate("2026-11-05")).toBe("Nov 5, 2026")
		expect(formatTime("21:15")).toBe("9:15 PM")
		expect(formatDateTime(new Date(2026, 10, 5, 21, 15))).toBe("Nov 5, 2026, 9:15 PM")
		expect(formatDate("")).toBe("")
		expect(formatDate("not a date")).toBe("")
	})

	it("shows ج.م after the amount in Arabic and E£ before it otherwise", () => {
		setLocale("ar")
		expect(getCurrencySymbol("EGP")).toBe("ج.م")
		expect(formatCurrency(1234.5, "EGP")).toBe("1,234.50 ج.م")
		expect(formatCurrency(-5, "EGP")).toBe("\u2066-5.00\u2069 ج.م")
		expect(formatCurrencyNumber(1234.5)).toBe("1,234.50")
		expect(formatCurrency(1234.5, "EGP")).toMatch(NO_ARABIC_DIGITS)
		setLocale("en")
		expect(getCurrencySymbol("EGP")).toBe("E£")
		expect(formatCurrency(1234.5, "EGP")).toBe("E£ 1,234.50")
		expect(formatCurrency(-5, "EGP")).toBe("-E£ 5.00")
	})

	it("routes useFormatters dates through the same helpers", () => {
		setLocale("ar")
		const f = useFormatters()
		expect(f.formatDate("2026-11-05")).toBe("5 نوفمبر 2026")
		expect(f.formatTime("15:31:22.975239")).toBe("3:31 م")
		expect(f.formatDateTime("2026-11-05 21:15:00")).toBe("5 نوفمبر 2026، 9:15 م")
	})
})
