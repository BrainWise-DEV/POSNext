/** Unpaid-tab chip buckets partition the tab. */
import { describe, expect, it } from "vitest"
import { unpaidInvoiceBucket } from "../unpaidInvoiceBucket"

const invoices = [
	{ status: "Overdue", paid_amount: 0 },
	{ status: "Overdue", paid_amount: 40 },
	{ status: "Overdue and Discounted", paid_amount: 0 },
	{ status: "Partly Paid", paid_amount: 10 },
	{ status: "Partly Paid and Discounted", paid_amount: 5 },
	{ status: "Unpaid", paid_amount: 0 },
	{ status: "Unpaid", paid_amount: 3 },
	{ status: "Draft" },
]

describe("unpaidInvoiceBucket", () => {
	it("puts every invoice in exactly one bucket, so the counts sum to the tab", () => {
		const counts = Object.groupBy(invoices, unpaidInvoiceBucket)
		expect(counts.overdue).toHaveLength(3)
		expect(counts.partial).toHaveLength(3)
		expect(counts.unpaid).toHaveLength(2)
		expect(counts.overdue.length + counts.partial.length + counts.unpaid.length).toBe(
			invoices.length,
		)
	})

	it("ranks overdue above partly paid", () => {
		expect(unpaidInvoiceBucket({ status: "Overdue", paid_amount: 40 })).toBe("overdue")
	})
})
