#!/usr/bin/env node
/**
 * Local-dev orchestrator: spawn `vite --mode desktop` against the chosen
 * customer's Frappe Cloud site, then `tauri dev` pointed at localhost:8080.
 *
 *   yarn desktop:dev <slug>
 */

import { spawn } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const desktopRoot = resolve(__dirname, "..")
const repoRoot = resolve(desktopRoot, "..")
const tauriDir = join(desktopRoot, "src-tauri")
const customersDir = join(desktopRoot, "customers")

const slug = process.argv[2]
if (!slug) {
	console.error("Usage: dev-customer.mjs <slug>")
	process.exit(1)
}
const cfgPath = join(customersDir, `${slug}.json`)
if (!existsSync(cfgPath)) {
	console.error(`No customer config at ${cfgPath}`)
	process.exit(1)
}
const cfg = JSON.parse(readFileSync(cfgPath, "utf8"))
if (!cfg.siteUrl) {
	console.error(`customers/${slug}.json missing siteUrl`)
	process.exit(1)
}

const env = {
	...process.env,
	VITE_POS_TARGET: "desktop",
	VITE_FRAPPE_BASE_URL: cfg.siteUrl,
}

console.log(`▶ Starting Vite (mode=desktop, base=${cfg.siteUrl})`)
const vite = spawn("yarn", ["--cwd", join(repoRoot, "POS"), "dev:desktop"], {
	stdio: "inherit",
	env,
	shell: process.platform === "win32",
})

console.log(`▶ Starting Tauri dev`)
const tauri = spawn("yarn", ["--cwd", desktopRoot, "tauri", "dev"], {
	stdio: "inherit",
	env,
	shell: process.platform === "win32",
})

const cleanup = () => {
	vite.kill()
	tauri.kill()
}
process.on("SIGINT", cleanup)
process.on("SIGTERM", cleanup)

tauri.on("exit", (code) => {
	vite.kill()
	process.exit(code ?? 0)
})
