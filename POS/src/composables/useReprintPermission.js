import { useBootstrapStore } from "@/stores/bootstrap";
import { usePOSShiftStore } from "@/stores/posShift";
import { isInvoicePrinted } from "@/utils/invoice";
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

export function useReprintPermission() {
	const userRoles = computed(() => useBootstrapStore().data?.user_roles ?? []);
	const posProfile = computed(() => usePOSShiftStore().currentProfile);

	const printButtonBase =
		"inline-flex items-center justify-center p-1.5 rounded-lg border transition-colors";

	function printButtonClass(blocked) {
		if (blocked) {
			return `${printButtonBase} text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed`;
		}
		return `${printButtonBase} text-green-600 bg-green-50 border-green-100 hover:bg-green-100`;
	}

	function isPrintDisabled(invoice) {
		if (!userLacksReprintRole(userRoles.value, posProfile.value)) return false;
		return isInvoicePrinted(invoice);
	}

	function printTitle(invoice) {
		return isPrintDisabled(invoice) ? DENIED : __("Print");
	}

	return {
		isPrintDisabled,
		printTitle,
		printButtonClass,
	};
}
