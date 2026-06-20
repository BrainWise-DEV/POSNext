import { onBeforeUnmount, unref, watch } from "vue"

/**
 * Consistent keyboard confirm for dialogs.
 *
 * Wires a window-level `keydown` listener while a dialog is open and invokes the
 * dialog's primary action on **Ctrl/Cmd+S** (universal) and optionally **Enter**.
 *
 * Why a module-level stack: dialogs can stack (CustomerDialog → CreateCustomerDialog,
 * PartialPayments → PaymentDialog). Only the top-most open instance should react to a
 * keypress, otherwise a parent dialog would submit at the same time as its child.
 * This is intentionally independent of `useDialogState` (which has no ordering).
 *
 * @example
 * useDialogSubmit({
 *   isOpen: show,
 *   onSubmit: handleCreate,
 *   canSubmit: () => !!customerData.customer_name && hasPermission,
 *   enter: true,   // default
 *   ctrlS: true,   // default
 * })
 */

// Module-level ordered stack of open dialog instance ids (last = top-most).
const openDialogStack = []
let nextInstanceId = 0

// Registry of instance id → its keydown config, so the single shared listener can
// dispatch to whichever instance is currently on top of the stack.
const instances = new Map()

let listenerAttached = false

function handleKeydown(event) {
	if (openDialogStack.length === 0) return

	const topId = openDialogStack[openDialogStack.length - 1]
	const instance = instances.get(topId)
	if (!instance) return

	const { onSubmit, canSubmit, enter, ctrlS } = instance

	const isCtrlS =
		(event.ctrlKey || event.metaKey) && (event.key === "s" || event.key === "S")
	const isEnter = event.key === "Enter"

	const allowed = () => !canSubmit || canSubmit()

	if (isCtrlS) {
		// Always suppress the browser "Save page" dialog, regardless of guard.
		event.preventDefault()
		if (ctrlS && allowed()) {
			onSubmit()
		}
		return
	}

	if (isEnter) {
		if (!enter) return
		// Leave textarea newlines and any local @keydown.enter handler alone.
		const target = event.target
		if (target && target.tagName === "TEXTAREA") return
		if (event.defaultPrevented) return
		if (allowed()) {
			onSubmit()
		}
	}
}

function attachListener() {
	if (listenerAttached) return
	window.addEventListener("keydown", handleKeydown, true)
	listenerAttached = true
}

function detachListener() {
	if (!listenerAttached) return
	window.removeEventListener("keydown", handleKeydown, true)
	listenerAttached = false
}

export function useDialogSubmit(options) {
	const {
		isOpen,
		onSubmit,
		canSubmit = null,
		enter = true,
		ctrlS = true,
	} = options

	const id = nextInstanceId++

	const pushToStack = () => {
		instances.set(id, { onSubmit, canSubmit, enter, ctrlS })
		// Remove any stale entry, then push to top.
		const existing = openDialogStack.indexOf(id)
		if (existing !== -1) openDialogStack.splice(existing, 1)
		openDialogStack.push(id)
		attachListener()
	}

	const removeFromStack = () => {
		const existing = openDialogStack.indexOf(id)
		if (existing !== -1) openDialogStack.splice(existing, 1)
		instances.delete(id)
		if (openDialogStack.length === 0) detachListener()
	}

	const stop = watch(
		() => unref(isOpen),
		(open) => {
			if (open) {
				pushToStack()
			} else {
				removeFromStack()
			}
		},
		{ immediate: true },
	)

	onBeforeUnmount(() => {
		stop()
		removeFromStack()
	})
}
