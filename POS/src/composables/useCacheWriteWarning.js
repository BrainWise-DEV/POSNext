import { onScopeDispose } from "vue";
import { CACHE_WRITE_FAILED_EVENT } from "@/utils/offline/workerClient";

/**
 * Warn the cashier, at most every `intervalMs`, when an offline cache write was lost
 * because the worker is down (D-R4-02 review I-1). The listener lives as long as the
 * component that calls this (review R1-m3).
 *
 * @param {(message: string) => void} showWarning
 * @param {{ intervalMs?: number }} [options]
 */
export function useCacheWriteWarning(showWarning, { intervalMs = 10 * 60 * 1000 } = {}) {
	if (typeof window === "undefined") return;
	let warnedAt = 0;
	const onFailed = () => {
		if (warnedAt && Date.now() - warnedAt < intervalMs) return;
		warnedAt = Date.now();
		showWarning(__("Offline data could not be saved on this device. Reload the POS while online to save it."));
	};
	window.addEventListener(CACHE_WRITE_FAILED_EVENT, onFailed);
	onScopeDispose(() => window.removeEventListener(CACHE_WRITE_FAILED_EVENT, onFailed));
}
