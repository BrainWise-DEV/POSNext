#!/usr/bin/env node
/**
 * Sign the most-recent .exe for a customer and emit a `latest.json` ready to
 * upload alongside it (S3, R2, GitHub Releases, etc).
 *
 *   yarn desktop:publish <slug>
 *
 * Looks for:
 *   desktop/dist/<slug>/<productName>_<version>_x64-setup.exe
 *   desktop/keys/<slug>.key       (private signing key from `tauri signer generate`)
 *
 * Writes:
 *   desktop/dist/<slug>/latest.json
 *   desktop/dist/<slug>/<setup>.sig (alongside the .exe)
 *
 * The actual upload to the customer's update channel is intentionally NOT
 * performed here — that's a per-customer decision (S3 push, scp, drop into a
 * Frappe File field, etc). Hand the two files off and you're done.
 */

import { spawnSync } from "node:child_process"
import {
	existsSync,
	readFileSync,
	readdirSync,
	statSync,
	writeFileSync,
} from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const desktopRoot = resolve(__dirname, "..")
const customersDir = join(desktopRoot, "customers")
const distRoot = join(desktopRoot, "dist")
const keysDir = join(desktopRoot, "keys")

function die(msg) {
	console.error(`✗ ${msg}`)
	process.exit(1)
}

const slug = process.argv[2]
if (!slug) die("Usage: publish-update.mjs <slug>")

const cfgPath = join(customersDir, `${slug}.json`)
if (!existsSync(cfgPath)) die(`No customer config at ${cfgPath}`)
const cfg = JSON.parse(readFileSync(cfgPath, "utf8"))

if (!cfg.updater?.active) {
	die(`Updater is not active for ${slug}. Set updater.active=true in customers/${slug}.json first.`)
}
const keyPath = join(keysDir, `${slug}.key`)
if (!existsSync(keyPath)) die(`No private signing key at ${keyPath}`)

const customerDist = join(distRoot, slug)
if (!existsSync(customerDist)) die(`No dist directory at ${customerDist}`)

const setup = readdirSync(customerDist).find(
	(f) => f.endsWith("-setup.exe") || f.endsWith(".msi") || f.endsWith(".nsis.zip"),
)
if (!setup) die(`No installer found under ${customerDist}`)
const setupPath = join(customerDist, setup)

console.log(`▶ Signing ${setupPath}`)
const sign = spawnSync(
	"yarn",
	["--cwd", desktopRoot, "tauri", "signer", "sign", "-k", keyPath, "-f", setupPath],
	{ stdio: "inherit", shell: process.platform === "win32" },
)
if (sign.status !== 0) die("tauri signer sign failed")

const sigPath = `${setupPath}.sig`
if (!existsSync(sigPath)) die(`Expected signature at ${sigPath}`)
const signature = readFileSync(sigPath, "utf8").trim()

const latest = {
	version: cfg.version,
	notes: cfg.releaseNotes || `Release ${cfg.version}`,
	pub_date: new Date().toISOString(),
	platforms: {
		"windows-x86_64": {
			signature,
			url:
				cfg.updater?.installerUrl ||
				`${cfg.updater.endpoint.replace(/\/latest\.json$/, "")}/${setup}`,
		},
	},
}
const latestPath = join(customerDist, "latest.json")
writeFileSync(latestPath, JSON.stringify(latest, null, 2))
console.log(`✓ Wrote ${latestPath}`)
console.log(`  Upload ${setupPath} and ${latestPath} to ${cfg.updater.endpoint}`)
