import { openLocalAgentCashDrawer } from "@/utils/localAgent";
import { getSavedPrinterName, openCashDrawer as openQzCashDrawer } from "@/utils/qzTray";

export function cashDrawerStorageKey(posProfile) {
	const profile = String(posProfile || "default").trim() || "default";
	return `posnext_cash_drawer_terminal:${profile}`;
}

export function loadCashDrawerTerminalSettings(posProfile) {
	try {
		const raw = localStorage.getItem(cashDrawerStorageKey(posProfile));
		if (!raw) {
			return {
				mode: "disabled",
				terminal_id: "",
				printer_name: "",
				command_profile: "escpos_drawer_1",
			};
		}
		const saved = JSON.parse(raw);
		return {
			mode: ["disabled", "qz", "local_agent"].includes(saved?.mode) ? saved.mode : "disabled",
			terminal_id: String(saved?.terminal_id || "").trim(),
			printer_name: String(saved?.printer_name || "").trim(),
			command_profile: ["escpos_drawer_1", "escpos_drawer_2", "star"].includes(saved?.command_profile)
				? saved.command_profile
				: "escpos_drawer_1",
		};
	} catch {
		return {
			mode: "disabled",
			terminal_id: "",
			printer_name: "",
			command_profile: "escpos_drawer_1",
		};
	}
}

export function getCashDrawerMethodLabel(mode) {
	if (mode === "qz") return "QZ Tray";
	if (mode === "local_agent") return "POSNext Local Agent";
	return "";
}

/**
 * Resolve the printer used by the cash drawer. A terminal-specific printer
 * overrides the saved QZ receipt printer. Local Agent always requires an
 * explicit allowlisted printer configured for that terminal.
 */
export function resolveCashDrawerPrinter(mode, printerName = "") {
	const configured = String(printerName || "").trim();
	if (configured) return configured;
	if (mode === "qz") return String(getSavedPrinterName() || "").trim();
	return "";
}

/** Execute one semantic cash drawer open action. */
export async function openCashDrawerHardware({ mode, printerName, commandProfile, terminalId = "" }) {
	if (mode === "qz") {
		return openQzCashDrawer(printerName, commandProfile);
	}

	if (mode === "local_agent") {
		return openLocalAgentCashDrawer(printerName, commandProfile, terminalId);
	}

	throw new Error("Cash drawer mode is disabled.");
}
