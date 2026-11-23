/**
 * Every name POSSale's checkout uses is defined (UI test D-R3-02).
 *
 * The offline branch of handlePaymentCompleted once read `preparedItems` after its
 * definition was removed: every offline checkout threw "preparedItems is not defined".
 * Mounting POSSale is impractical, so its <script setup> is parsed and every identifier
 * read in handlePaymentCompleted must resolve to a binding, an import or a global.
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { parse as parseBabel } from "@babel/parser"
import traverseModule from "@babel/traverse"
import { parse as parseSfc } from "@vue/compiler-sfc"
import { describe, expect, it } from "vitest"

const traverse = traverseModule.default || traverseModule

const GLOBALS = new Set([
	"__",
	"window",
	"document",
	"navigator",
	"console",
	"Math",
	"Date",
	"JSON",
	"Number",
	"String",
	"Boolean",
	"Object",
	"Array",
	"Map",
	"Set",
	"Promise",
	"Error",
	"TypeError",
	"setTimeout",
	"clearTimeout",
	"undefined",
	"Infinity",
	"NaN",
	"globalThis",
	"sessionStorage",
	"localStorage",
	"frappe",
	"structuredClone",
	"parseFloat",
	"parseInt",
	"isNaN",
	"encodeURIComponent",
])

function unresolvedNamesIn(functionName) {
	const source = readFileSync(resolve(__dirname, "../POSSale.vue"), "utf8")
	const { descriptor } = parseSfc(source)
	const ast = parseBabel(descriptor.scriptSetup.content, { sourceType: "module" })
	const unresolved = new Set()
	let found = false
	traverse(ast, {
		FunctionDeclaration(path) {
			if (path.node.id?.name !== functionName) return
			found = true
			path.traverse({
				ReferencedIdentifier(ref) {
					const name = ref.node.name
					if (!ref.scope.hasBinding(name) && !GLOBALS.has(name)) unresolved.add(name)
				},
			})
		},
	})
	expect(found).toBe(true)
	return [...unresolved]
}

describe("POSSale handlePaymentCompleted", () => {
	it("reads no undefined name (the offline receipt and stock deduction included)", () => {
		expect(unresolvedNamesIn("handlePaymentCompleted")).toEqual([])
	})
})
