import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { request } from "@playwright/test";

const dir = path.dirname(fileURLToPath(import.meta.url));
export const AUTH_DIR = path.join(dir, ".auth");

/** Log in through /api/method/login and save the session cookie as a storageState file. */
async function login(baseURL, usr, pwd, file) {
	const api = await request.newContext({ baseURL });
	const res = await api.post("/api/method/login", { form: { usr, pwd } });
	if (!res.ok()) {
		throw new Error(`Login failed for ${usr}: HTTP ${res.status()}`);
	}
	await api.storageState({ path: file });
	await api.dispose();
}

export default async function globalSetup() {
	const baseURL = process.env.UIT_BASE_URL;
	const user = process.env.UIT_USER;
	const password = process.env.UIT_PASSWORD;
	if (!baseURL || !user || !password) {
		throw new Error("Set UIT_BASE_URL, UIT_USER and UIT_PASSWORD (the seed prints the passwords once).");
	}
	fs.mkdirSync(AUTH_DIR, { recursive: true });
	await login(baseURL, user, password, path.join(AUTH_DIR, "cashier.json"));

	// Optional second cashier, only for the two-tab race (U-38).
	if (process.env.UIT_USER2 && process.env.UIT_PASSWORD2) {
		await login(baseURL, process.env.UIT_USER2, process.env.UIT_PASSWORD2, path.join(AUTH_DIR, "cashier2.json"));
	}
}
