/**
 * A server message made of lines joined with <br> reads as sentences, not run
 * together (UI test D-R3-09: "...1.0 sent).The offers changed.").
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest"

globalThis.__ = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
const { parseError } = await import("../errorHandler")

const REFUSAL =
	"Row 2: free item UIT-GIFT is not backed by an offer (free qty 0 expected, 1.0 sent).<br>The offers changed. Refresh and re-apply offers."

describe("parseError line breaks", () => {
	it("keeps a space where the server broke the line", () => {
		const { message } = parseError({ messages: [REFUSAL] })
		expect(message).toBe(
			"Row 2: free item UIT-GIFT is not backed by an offer (free qty 0 expected, 1.0 sent). The offers changed. Refresh and re-apply offers."
		)
	})

	it("reads _server_messages the same way", () => {
		const { message } = parseError({
			_server_messages: JSON.stringify([JSON.stringify({ message: REFUSAL })]),
		})
		expect(message).toContain("sent). The offers changed.")
	})
})
