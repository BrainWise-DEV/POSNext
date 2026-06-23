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
	};
}
