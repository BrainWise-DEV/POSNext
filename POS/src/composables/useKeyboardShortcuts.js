import { onUnmounted, watch } from "vue";

/**
 * Window-level shortcuts. F-keys never type text, so they fire from inputs too;
 * any other key is skipped while an input or textarea has focus.
 *
 * @param {() => boolean} isBlocked - True while a dialog, lock screen or overlay is showing
 * @param {Record<string, () => void>} handlers - Keyed by KeyboardEvent.key, e.g. { F9: pay }
 */
export function useGlobalShortcuts(isBlocked, handlers) {
	const onKeydown = (event) => {
		const handler = handlers[event.key];
		if (!handler || isBlocked()) return;
		const tag = document.activeElement?.tagName;
		if ((tag === "INPUT" || tag === "TEXTAREA") && !/^F\d{1,2}$/.test(event.key)) return;
		event.preventDefault();
		handler();
	};
	window.addEventListener("keydown", onKeydown);
	onUnmounted(() => window.removeEventListener("keydown", onKeydown));
}

/**
 * Enter confirms the picker's default option while it is open. Runs in the capture
 * phase so a focused button (e.g. the dialog's close X) is not clicked instead.
 * Inputs handle their own Enter. Esc is already handled by the dialog.
 *
 * @param {import('vue').Ref<boolean>} isOpen
 * @param {(event: KeyboardEvent) => void} onEnter
 */
export function usePickerEnter(isOpen, onEnter) {
	const onKeydown = (event) => {
		if (event.key !== "Enter" || event.isComposing || ["INPUT", "TEXTAREA"].includes(event.target?.tagName)) return;
		event.preventDefault();
		event.stopPropagation();
		onEnter(event);
	};
	const stop = watch(
		isOpen,
		(open) => window[open ? "addEventListener" : "removeEventListener"]("keydown", onKeydown, true),
		{ immediate: true },
	);
	onUnmounted(() => {
		stop();
		window.removeEventListener("keydown", onKeydown, true);
	});
}
