import { parseError } from "./errorHandler";
import { silentPrintDoc } from "./printInvoice";

const EOD_PRINT_FORMAT = "POS Next EOD Report";

export async function printEODReport(closingShiftName) {
	await silentPrintDoc("POS Closing Shift", closingShiftName, EOD_PRINT_FORMAT);
}

/**
 * What the cashier is told when the EOD report does not print: the reason the server
 * or the printer gave, so a broken print format is not mistaken for a printer (D-R4-04).
 */
export function eodPrintFailureMessage(error) {
	const reason = error?.messages?.length || error?._server_messages || error?.message ? parseError(error).message : "";
	return reason
		? __("EOD report did not print: {0}", [reason])
		: __("EOD report did not print. Use the Reprint button to retry.");
}
