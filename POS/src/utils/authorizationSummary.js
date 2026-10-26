import { formatCurrency } from "@/utils/currency";

function t(text) {
	const translate = globalThis.__;
	return typeof translate === "function" ? translate(text) : text;
}

export function buildAuthorizationSummary(state = {}, { formatAmount = formatCurrency } = {}) {
	const context = state.context || {};
	const rows = [];


	const action = state.actionLabel || state.action;
	if (action) {
		rows.push({ key: "action", label: t("Action"), value: String(action) });
	}

	const amount = Number.parseFloat(context.amount);
	if (Number.isFinite(amount) && amount !== 0) {
		rows.push({
			key: "amount",
			label: context.amountLabel ? t(context.amountLabel) : t("Refund Amount"),
			value: formatAmount(amount, context.currency),
		});
	}

	if (context.journal_entry) {
		rows.push({ key: "journal_entry", label: t("Journal Entry"), value: String(context.journal_entry) });
	}

	if (context.return_against) {
		rows.push({
			key: "return_against",
			label: t("Against Invoice"),
			value: String(context.return_against),
		});
	}

	return rows;
}
