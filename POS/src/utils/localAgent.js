import { logger } from "@/utils/logger";

const log = logger.create("POSNextLocalAgent");
const DEFAULT_AGENT_URL = "http://127.0.0.1:17777";
const AGENT_URL_KEY = "posnext_local_agent_url";
const AGENT_TOKEN_KEY = "posnext_local_agent_token";

export function getLocalAgentUrl() {
	try {
		return String(localStorage.getItem(AGENT_URL_KEY) || DEFAULT_AGENT_URL).replace(/\/+$/, "");
	} catch {
		return DEFAULT_AGENT_URL;
	}
}

export function getLocalAgentToken() {
	try {
		return String(localStorage.getItem(AGENT_TOKEN_KEY) || "").trim();
	} catch {
		return "";
	}
}

export function saveLocalAgentToken(token) {
	try {
		localStorage.setItem(AGENT_TOKEN_KEY, String(token || "").trim());
	} catch (error) {
		log.warn("Unable to save Local Agent token:", error);
	}
}

function createNonce() {
	if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
	const bytes = new Uint8Array(16);
	globalThis.crypto?.getRandomValues?.(bytes);
	return `posnext-${Date.now()}-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
}

async function agentRequest(path, { method = "GET", body = null, timeoutMs = 5000 } = {}) {
	const token = getLocalAgentToken();
	if (!token) {
		throw new Error("POSNext Local Agent token is not configured on this terminal.");
	}

	const controller = new AbortController();
	const timer = window.setTimeout(() => controller.abort(), timeoutMs);
	try {
		const response = await fetch(`${getLocalAgentUrl()}${path}`, {
			method,
			headers: {
				"Content-Type": "application/json",
				"X-POSNext-Token": token,
				"X-POSNext-Nonce": createNonce(),
			},
			body: body == null ? undefined : JSON.stringify(body),
			signal: controller.signal,
			cache: "no-store",
		});

		const payload = await response.json().catch(() => ({}));
		if (!response.ok || payload?.success === false) {
			throw new Error(payload?.message || `POSNext Local Agent request failed (${response.status})`);
		}
		return payload;
	} catch (error) {
		if (error?.name === "AbortError") {
			throw new Error("POSNext Local Agent did not respond in time.");
		}
		if (error instanceof TypeError) {
			throw new Error(
				"Could not reach POSNext Local Agent on this computer. Check that the agent is running and the browser allows localhost access."
			);
		}
		throw error;
	} finally {
		window.clearTimeout(timer);
	}
}

export async function localAgentHealth() {
	return agentRequest("/health", { timeoutMs: 2500 });
}

export async function listLocalAgentPrinters() {
	const result = await agentRequest("/printers", { timeoutMs: 5000 });
	return Array.isArray(result?.printers) ? result.printers : [];
}

export async function testLocalAgentPrinter(printerName, terminalId = "") {
	const printer = String(printerName || "").trim();
	if (!printer) throw new Error("Local Agent printer is not configured.");
	return agentRequest("/test-print", {
		method: "POST",
		body: { printer_name: printer, terminal_id: String(terminalId || "").trim() },
		timeoutMs: 8000,
	});
}

export async function openLocalAgentCashDrawer(
	printerName,
	commandProfile = "escpos_drawer_1",
	terminalId = ""
) {
	const printer = String(printerName || "").trim();
	if (!printer) throw new Error("Local Agent cash drawer printer is not configured.");

	try {
		const result = await agentRequest("/drawer/open", {
			method: "POST",
			body: {
				printer_name: printer,
				command_profile: commandProfile,
				terminal_id: String(terminalId || "").trim(),
			},
			timeoutMs: 5000,
		});
		return { success: true, printerName: printer, ...result };
	} catch (error) {
		log.error("Local Agent drawer open failed:", error);
		throw error;
	}
}
