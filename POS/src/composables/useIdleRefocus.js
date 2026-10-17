import { getCurrentInstance, onBeforeUnmount, watch } from "vue"

/**
 * Idle auto-refocus for the POS sale screen.
 *
 * After a configurable period of inactivity, focus is returned to the item
 * search input so the next scan/keystroke lands in the right place. This is
 * the native, configurable replacement for the hardcoded idle-refocus that
 * previously lived in the external `easy_entry` app's `pos_guard.js`.
 *
 * Guards (ported from pos_guard.js `userIsBusy`): never steal focus from
 * another text field (customer search, quantity edit, etc.) and never fight an
 * open dialog.
 *
 * @param {Object} opts
 * @param {import("vue").Ref<Boolean>} opts.enabled - whether refocus is active
 * @param {import("vue").Ref<Number>} opts.intervalSeconds - idle seconds before refocus
 * @param {import("vue").Ref<Boolean>|Function} [opts.isDialogOpen] - dialog-open signal
 * @param {Function} opts.onRefocus - called to refocus the item search input
 */
export function useIdleRefocus({
	enabled,
	intervalSeconds,
	isDialogOpen,
	onRefocus,
}) {
	const ACTIVITY_EVENTS = [
		"keydown",
		"mousedown",
		"touchstart",
		"pointerdown",
		"input",
	]

	let idleTimer = null
	let wired = false

	function dialogIsOpen() {
		const signal =
			typeof isDialogOpen === "function" ? isDialogOpen() : isDialogOpen?.value
		if (signal) return true
		// frappe-ui renders these only while a dialog is open
		return !!document.querySelector('[data-dialog], [role="dialog"], .modal.show')
	}

	/**
	 * Don't reclaim focus while the user is mid-task in another field, or while
	 * a dialog is open. Returns true when we should hold off.
	 */
	function userIsBusy() {
		const ae = document.activeElement
		if (
			ae &&
			(ae.tagName === "INPUT" ||
				ae.tagName === "TEXTAREA" ||
				ae.tagName === "SELECT" ||
				ae.isContentEditable)
		) {
			return true
		}
		return dialogIsOpen()
	}

	function clearTimer() {
		if (idleTimer) {
			clearTimeout(idleTimer)
			idleTimer = null
		}
	}

	function scheduleRefocus() {
		clearTimer()
		const ms = Math.max(1, Number(intervalSeconds.value) || 3) * 1000
		idleTimer = setTimeout(() => {
			if (userIsBusy()) {
				// Check again later instead of grabbing focus mid-task
				scheduleRefocus()
				return
			}
			onRefocus?.()
		}, ms)
	}

	function handleActivity() {
		if (enabled.value) scheduleRefocus()
	}

	function start() {
		if (wired) return
		wired = true
		for (const evt of ACTIVITY_EVENTS) {
			document.addEventListener(evt, handleActivity, true)
		}
		scheduleRefocus()
	}

	function stop() {
		clearTimer()
		if (!wired) return
		wired = false
		for (const evt of ACTIVITY_EVENTS) {
			document.removeEventListener(evt, handleActivity, true)
		}
	}

	// Start/stop with the enable toggle (immediate covers initial state)
	watch(enabled, (on) => (on ? start() : stop()), { immediate: true })
	// Reschedule when the interval changes
	watch(intervalSeconds, () => {
		if (enabled.value) scheduleRefocus()
	})

	// Auto-cleanup when used inside a component
	if (getCurrentInstance()) onBeforeUnmount(stop)

	return { start, stop }
}
