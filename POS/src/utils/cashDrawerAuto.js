import { call } from "@/utils/apiWrapper";
import {
	getCashDrawerMethodLabel,
	loadCashDrawerTerminalSettings,
	openCashDrawerHardware,
	resolveCashDrawerPrinter,
} from "@/utils/cashDrawerHardware";
import { logger } from "@/utils/logger";

const log = logger.create("CashDrawerAuto");

async function reportHardwareResult(logName, success, printerName = "", errorMessage = "") {
	try {
		await call("pos_next.api.cash_drawer.report_open_result", {
			log_name: logName,
			success: success ? 1 : 0,
			printer_name: String(printerName || "").trim(),
			error_message: success ? "" : String(errorMessage || "Cash drawer hardware failed."),
		});
	} catch (error) {
		log.warn("Unable to save automatic cash drawer hardware result:", error);
	}
}

/**
 * Attempt one automatic drawer opening for an ORIGINAL, already-submitted invoice.
 * The server is authoritative for Cash-type payment detection, sale/refund settings,
 * and AUTO:<invoice> idempotency. Callers must never invoke this from reprint paths.
 */
export async function tryAutomaticCashDrawerOpen({ invoiceName, posOpeningShift, posProfile }) {
	const name = String(invoiceName || "").trim();
	const shift = String(posOpeningShift || "").trim();
	if (!name || !shift) return { opened: false, reason: "missing_invoice_or_shift" };

	const terminal = loadCashDrawerTerminalSettings(posProfile);
	const method = getCashDrawerMethodLabel(terminal.mode);

	const response = await call("pos_next.api.cash_drawer.authorize_automatic_open", {
		invoice_name: name,
		pos_opening_shift: shift,
		terminal_id: terminal.terminal_id || "",
		method,
	});
	const authorization = response?.message || response;

	if (!authorization?.authorized) {
		return {
			opened: false,
			reason: authorization?.reason || "not_authorized",
			cashAmount: authorization?.cash_amount || 0,
		};
	}

	const printerName = resolveCashDrawerPrinter(terminal.mode, terminal.printer_name);
	if (
		terminal.mode === "disabled" ||
		!terminal.terminal_id ||
		!printerName ||
		!method
	) {
		const message = "Cash drawer is authorized, but this POS terminal hardware is not configured.";
		await reportHardwareResult(authorization.log_name, false, printerName, message);
		return {
			opened: false,
			reason: "terminal_not_configured",
			hardwareError: message,
			cashAmount: authorization.cash_amount || 0,
		};
	}

	try {
		const hardware = await openCashDrawerHardware({
			mode: terminal.mode,
			printerName,
			commandProfile: terminal.command_profile,
			terminalId: terminal.terminal_id,
		});
		await reportHardwareResult(
			authorization.log_name,
			true,
			hardware?.printerName || printerName
		);
		return {
			opened: true,
			reason: "opened",
			printerName: hardware?.printerName || printerName,
			cashAmount: authorization.cash_amount || 0,
		};
	} catch (error) {
		const message = error?.message || "Cash drawer hardware failed.";
		await reportHardwareResult(authorization.log_name, false, printerName, message);
		return {
			opened: false,
			reason: "hardware_failed",
			hardwareError: message,
			cashAmount: authorization.cash_amount || 0,
		};
	}
}
