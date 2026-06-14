import { computed, readonly, ref, watch } from "vue"

/**
 * Global Dialog State Manager
 *
 * Automatically tracks all open dialogs/modals across the application to prevent UI conflicts.
 * Main use case: Hiding/disabling the draggable divider when any dialog is open.
 *
 * Benefits:
 * - No manual array maintenance - dialogs auto-register when opened
 * - Zero-config for new dialogs - just use `useDialog()`
 * - Global state shared across all components
 * - Automatic cleanup on component unmount
 *
 * @example
 * // In POSSale.vue (or any component with dialogs):
 * const { isOpen: showPaymentDialog } = useDialog('payment')
 * const { isOpen: showCustomerDialog } = useDialog('customer')
 * // Use showPaymentDialog.value = true/false as normal
 *
 * @example
 * // In components that need to react to ANY dialog being open:
 * const { isAnyDialogOpen } = useDialogState()
 * // Use in template: :class="{ 'hidden': isAnyDialogOpen }"
 */

// Global state - shared across all components
const activeDialogs = ref(new Set())
const dialogCounter = ref(0)

/**
 * Composable for managing dialog state globally
 *
 * @example
 * // In any component with a dialog:
 * const { isOpen: showPaymentDialog, isAnyDialogOpen } = useDialog('payment')
 *
 * // In divider component:
 * const { isAnyDialogOpen } = useDialogState()
 */
export function useDialog(dialogId) {
	if (!dialogId) {
		throw new Error("useDialog requires a unique dialogId")
	}

	const isOpen = ref(false)

	// Watch for changes and update global state
	const setOpen = (value) => {
		if (value && !isOpen.value) {
			activeDialogs.value.add(dialogId)
			dialogCounter.value++
		} else if (!value && isOpen.value) {
			activeDialogs.value.delete(dialogId)
			dialogCounter.value--
		}
		isOpen.value = value
	}

	// Computed to track any dialog being open
	const isAnyDialogOpen = computed(() => dialogCounter.value > 0)

	// Cleanup on unmount (automatically handled by Vue)
	const cleanup = () => {
		if (isOpen.value) {
			activeDialogs.value.delete(dialogId)
			dialogCounter.value--
		}
	}

	return {
		isOpen: computed({
			get: () => isOpen.value,
			set: setOpen,
		}),
		isAnyDialogOpen: readonly(isAnyDialogOpen),
		cleanup,
		// Helper methods
		open: () => setOpen(true),
		close: () => setOpen(false),
		toggle: () => setOpen(!isOpen.value),
	}
}

/**
 * Simplified composable for components that only need to check if any dialog is open
 * (e.g., the draggable divider)
 */
export function useDialogState() {
	const isAnyDialogOpen = computed(() => dialogCounter.value > 0)
	const activeCount = computed(() => activeDialogs.value.size)

	return {
		isAnyDialogOpen: readonly(isAnyDialogOpen),
		activeCount: readonly(activeCount),
		activeDialogIds: readonly(computed(() => Array.from(activeDialogs.value))),
	}
}

/**
 * Alternative: Simple ref-based approach for existing code
 * Wraps an existing ref and registers it with the global state
 *
 * @example
 * const showPaymentDialog = registerDialog(ref(false), 'payment')
 */
export function registerDialog(dialogRef, dialogId) {
	if (!dialogId) {
		throw new Error("registerDialog requires a unique dialogId")
	}

	// Watch the ref and update global state
	const stopWatch = watch(
		dialogRef,
		(newValue, oldValue) => {
			if (newValue && !oldValue) {
				activeDialogs.value.add(dialogId)
				dialogCounter.value++
			} else if (!newValue && oldValue) {
				activeDialogs.value.delete(dialogId)
				dialogCounter.value--
			}
		},
		{ immediate: false },
	)

	// Return the original ref with cleanup
	dialogRef.cleanup = () => {
		stopWatch()
		if (dialogRef.value) {
			activeDialogs.value.delete(dialogId)
			dialogCounter.value--
		}
	}

	return dialogRef
}
