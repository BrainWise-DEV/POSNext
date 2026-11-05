import { describe, expect, it } from "vitest"
import {
	matchSegments,
	normalizeSearchText,
	tokenizeQuery,
} from "../searchText"

describe("normalizeSearchText", () => {
	it("returns an empty string for nullish or empty input", () => {
		expect(normalizeSearchText(null)).toBe("")
		expect(normalizeSearchText(undefined)).toBe("")
		expect(normalizeSearchText("")).toBe("")
	})

	it("lowercases Latin text", () => {
		expect(normalizeSearchText("John DOE")).toBe("john doe")
	})

	it("strips Arabic diacritics", () => {
		expect(normalizeSearchText("مُحَمَّد")).toBe("محمد")
	})

	it("unifies alef variants and other letter forms", () => {
		expect(normalizeSearchText("أحمد")).toBe("احمد")
		expect(normalizeSearchText("إيمان")).toBe("ايمان")
		expect(normalizeSearchText("آمال")).toBe("امال")
		expect(normalizeSearchText("فاطمة")).toBe("فاطمه")
		expect(normalizeSearchText("مصطفى")).toBe("مصطفي")
		expect(normalizeSearchText("مؤمن")).toBe("مومن")
		expect(normalizeSearchText("هانئ")).toBe("هاني")
	})

	it("converts Arabic-Indic and Persian digits to Latin digits", () => {
		expect(normalizeSearchText("٠١٢٣٤٥٦٧٨٩")).toBe("0123456789")
		expect(normalizeSearchText("۰۱۲۳۴۵۶۷۸۹")).toBe("0123456789")
		expect(normalizeSearchText("٠١٠ 123")).toBe("010 123")
	})
})

describe("tokenizeQuery", () => {
	it("splits on whitespace and normalizes each token", () => {
		expect(tokenizeQuery("  أحمد   علي ")).toEqual(["احمد", "علي"])
	})

	it("returns no tokens for a blank query", () => {
		expect(tokenizeQuery("   ")).toEqual([])
		expect(tokenizeQuery(null)).toEqual([])
	})
})

describe("matchSegments", () => {
	const joined = (segments) => segments.map((s) => s.text).join("")
	const hits = (segments) => segments.filter((s) => s.hit).map((s) => s.text)

	it("returns no segments for empty text", () => {
		expect(matchSegments("", ["a"])).toEqual([])
	})

	it("returns one unhighlighted segment when there are no tokens", () => {
		expect(matchSegments("Ahmed", [])).toEqual([{ text: "Ahmed", hit: false }])
	})

	it("highlights a Latin match case-insensitively", () => {
		const segments = matchSegments("John Doe", tokenizeQuery("doe"))
		expect(segments).toEqual([
			{ text: "John ", hit: false },
			{ text: "Doe", hit: true },
		])
	})

	it("matches across alef variants in both directions", () => {
		expect(hits(matchSegments("احمد علي", tokenizeQuery("أحمد")))).toEqual([
			"احمد",
		])
		expect(hits(matchSegments("أحمد علي", tokenizeQuery("احمد")))).toEqual([
			"أحمد",
		])
	})

	it("keeps diacritics inside the highlighted original text", () => {
		const text = "مُحَمَّد سعيد"
		const segments = matchSegments(text, tokenizeQuery("محمد"))
		expect(joined(segments)).toBe(text)
		expect(hits(segments)).toEqual(["مُحَمَّد"])
	})

	it("matches Arabic-Indic digits typed against Latin digits and back", () => {
		expect(hits(matchSegments("01012345678", tokenizeQuery("٠١٢٣")))).toEqual([
			"0123",
		])
		expect(hits(matchSegments("٠١٠١٢٣٤٥", tokenizeQuery("1012")))).toEqual([
			"١٠١٢",
		])
	})

	it("highlights every occurrence and every token", () => {
		const segments = matchSegments("Ali Ali Hassan", tokenizeQuery("ali has"))
		expect(hits(segments)).toEqual(["Ali", "Ali", "Has"])
		expect(joined(segments)).toBe("Ali Ali Hassan")
	})
})
