import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const dir = path.dirname(fileURLToPath(import.meta.url));
export const AUTH_DIR = path.join(dir, ".auth");

/**
 * Log in through /api/method/login from inside a real browser page and save the session as a
 * storageState file. A browser is used (not Playwright's Node request context) because Node cannot
 * resolve `*.localhost` hosts, while Chromium maps them to loopback. This works over plain http:
 * the session cookie is not Secure. No trace or video is recorded here, so the password (passed as
 * an evaluate argument, never in source) cannot land in a trace or report.
 */
async function login(browser, baseURL, usr, pwd, file) {
	const context = await browser.newContext({ baseURL });
	const page = await context.newPage();
	await page.goto("/api/method/ping");
	const status = await page.evaluate(
		async ([u, p]) => {
			const body = new URLSearchParams({ usr: u, pwd: p });
			const r = await fetch("/api/method/login", { method: "POST", body });
			return r.status;
		},
		[usr, pwd],
	);
	if (status !== 200) throw new Error(`Login failed for ${usr}: HTTP ${status}`);
	await context.storageState({ path: file });
	await context.close();
}

export default async function globalSetup() {
	const baseURL = process.env.UIT_BASE_URL;
	const users = [
		["cashier", process.env.UIT_USER, process.env.UIT_PASSWORD],
		["cashier2", process.env.UIT_USER2, process.env.UIT_PASSWORD2],
		["manager", process.env.UIT_MANAGER, process.env.UIT_MANAGER_PASSWORD],
	];
	if (!baseURL || !users[0][1] || !users[0][2]) {
		throw new Error("Set UIT_BASE_URL, UIT_USER and UIT_PASSWORD (read them from uit-passwords.tsv in the shell).");
	}
	fs.mkdirSync(AUTH_DIR, { recursive: true });
	const browser = await chromium.launch();
	try {
		for (const [key, usr, pwd] of users) {
			if (usr && pwd) await login(browser, baseURL, usr, pwd, path.join(AUTH_DIR, `${key}.json`));
		}
	} finally {
		await browser.close();
	}
}
