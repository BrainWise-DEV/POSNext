import { useBootstrapStore } from "@/stores/bootstrap";
import { usePOSShiftStore } from "@/stores/posShift";
import { computed } from "vue";

const DENIED = __("Your role is not allowed to reprint a printed order.");

function allowedRoles(posProfile) {
	return (posProfile?.posa_role_allowed_for_reprint ?? [])
		.map((row) => row.role)
		.filter(Boolean);
}

function userLacksReprintRole(userRoles, posProfile) {
	const allowed = allowedRoles(posProfile);
	if (!allowed.length) return false;
	return !(userRoles ?? []).some((role) => allowed.includes(role));
}

function isPrinted(invoice) {
	return Boolean(invoice?.data?.was_printed) || Number(invoice?.posa_is_printed) === 1;
}

export function useReprintPermission() {
	const userRoles = computed(() => useBootstrapStore().data?.user_roles ?? []);
	const posProfile = computed(() => usePOSShiftStore().currentProfile);

	const historyPrintBlocked = computed(() =>
		userLacksReprintRole(userRoles.value, posProfile.value)
	);

	const printButtonBase =
		"inline-flex items-center justify-center p-1.5 rounded-lg border transition-colors";

	function printButtonClass(blocked) {
		if (blocked) {
			return `${printButtonBase} text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed`;
		}
		return `${printButtonBase} text-green-600 bg-green-50 border-green-100 hover:bg-green-100`;
	}

	/** Invoice log / history — every row is a reprint. */
	function isHistoryPrintDisabled() {
		return historyPrintBlocked.value;
	}

	/** Offline queue — block only when already printed once. */
	function isPrintDisabled(invoice) {
		if (!userLacksReprintRole(userRoles.value, posProfile.value)) return false;
		return isPrinted(invoice);
	}

	function historyPrintTitle() {
		return isHistoryPrintDisabled() ? DENIED : __("Print");
	}

	function printTitle(invoice) {
		return isPrintDisabled(invoice) ? DENIED : __("Print");
	}

	return {
		historyPrintBlocked,
		isHistoryPrintDisabled,
		isPrintDisabled,
		historyPrintTitle,
		printTitle,
		printButtonClass,
		userLacksReprintRole: () => userLacksReprintRole(userRoles.value, posProfile.value),
	};
}
