import { useDialog, useDialogState } from "@/composables/useDialogState"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

const LEFT_PANEL_MIN = 320
const RIGHT_PANEL_MIN = 360

export const usePOSUIStore = defineStore("posUI", () => {
	// Loading state
	const isLoading = ref(true)

	// Dialog states using the dialog composable
	const { isOpen: showPaymentDialog } = useDialog("payment")
	const { isOpen: showCustomerDialog } = useDialog("customer")
	const { isOpen: showSuccessDialog } = useDialog("success")
	const { isOpen: showOpenShiftDialog } = useDialog("openShift")
	const { isOpen: showCloseShiftDialog } = useDialog("closeShift")
	const { isOpen: showDraftDialog } = useDialog("draft")
	const { isOpen: showReturnDialog } = useDialog("return")
	const { isOpen: showCouponDialog } = useDialog("coupon")
	const { isOpen: showOffersDialog } = useDialog("offers")
	const { isOpen: showBatchSerialDialog } = useDialog("batchSerial")
	const { isOpen: showHistoryDialog } = useDialog("history")
	const { isOpen: showOfflineInvoicesDialog } = useDialog("offlineInvoices")
	const { isOpen: showCreateCustomerDialog } = useDialog("createCustomer")
	const { isOpen: showClearCartDialog } = useDialog("clearCart")
	const { isOpen: showLogoutDialog } = useDialog("logout")
	const { isOpen: showItemSelectionDialog } = useDialog("itemSelection")
	const { isOpen: showErrorDialog } = useDialog("invoiceError")

	// Global dialog state
	const { isAnyDialogOpen } = useDialogState()

	// Error dialog state
	const errorDialogTitle = ref("")
	const errorDialogMessage = ref("")
	const errorDetails = ref("")
	const errorType = ref("error") // 'error', 'warning', 'validation'
	const errorRetryAction = ref(null)
	const errorRetryActionData = ref(null)

	// Success dialog state
	const lastInvoiceName = ref("")
	const lastInvoiceTotal = ref(0)
	const lastPaidAmount = ref(0)
	/** Full receipt payload for invoices not yet on the server (offline queue) */
	const lastOfflinePrintDoc = ref(null)

	// Customer dialog state
	const initialCustomerName = ref("")

	// Mobile responsiveness
	const mobileActiveTab = ref("items") // 'items' or 'cart'
	const windowWidth = ref(
		typeof window !== "undefined" ? window.innerWidth : 1024,
	)

	// Layout state
	const leftPanelWidth = ref(800)
	const isResizing = ref(false)

	// Computed
	const isDesktop = computed(() => windowWidth.value >= 1024)

	// Actions
	function setLoading(loading) {
		isLoading.value = loading
	}

	function setWindowWidth(width) {
		windowWidth.value = width
	}

	function setMobileTab(tab) {
		mobileActiveTab.value = tab
	}

	function showError(
		title,
		message,
		details = "",
		retryAction = null,
		retryData = null,
	) {
		errorDialogTitle.value = title
		errorDialogMessage.value = message
		errorDetails.value = details
		errorRetryAction.value = retryAction
		errorRetryActionData.value = retryData
		showErrorDialog.value = true
	}

	function clearError() {
		errorDialogTitle.value = ""
		errorDialogMessage.value = ""
		errorDetails.value = ""
		errorRetryAction.value = null
		errorRetryActionData.value = null
		showErrorDialog.value = false
	}

	function showSuccess(invoiceName, total, paidAmount = null) {
		lastInvoiceName.value = invoiceName
		lastInvoiceTotal.value = total
		lastPaidAmount.value = paidAmount !== null ? paidAmount : total
		showSuccessDialog.value = true
	}

	function setLastOfflinePrintDoc(doc) {
		lastOfflinePrintDoc.value = doc
	}

	function clearLastOfflinePrintDoc() {
		lastOfflinePrintDoc.value = null
	}

	function setInitialCustomerName(name) {
		initialCustomerName.value = name
	}

	// Layout actions
	function clampLeftPanelWidth(width, containerWidth) {
		const safeContainerWidth =
			Number.isFinite(containerWidth) && containerWidth > 0
				? containerWidth
				: LEFT_PANEL_MIN + RIGHT_PANEL_MIN
		const maxWidth = Math.max(
			LEFT_PANEL_MIN,
			safeContainerWidth - RIGHT_PANEL_MIN,
		)
		const clampedWidth = Math.min(Math.max(width, LEFT_PANEL_MIN), maxWidth)
		return Number.isFinite(clampedWidth) ? clampedWidth : LEFT_PANEL_MIN
	}

	function setLeftPanelWidth(width, containerWidth = null) {
		if (containerWidth !== null) {
			const clamped = clampLeftPanelWidth(width, containerWidth)
			leftPanelWidth.value = clamped
		} else {
			leftPanelWidth.value = width
		}
	}

	function setResizing(resizing) {
		isResizing.value = resizing
	}

	function updateLayoutBounds(containerWidth) {
		if (containerWidth) {
			leftPanelWidth.value = clampLeftPanelWidth(
				leftPanelWidth.value,
				containerWidth,
			)
		}
	}

	function resetAllDialogs() {
		// Close all dialogs on logout to prevent stale state
		showPaymentDialog.value = false
		showCustomerDialog.value = false
		showSuccessDialog.value = false
		showOpenShiftDialog.value = false
		showCloseShiftDialog.value = false
		showDraftDialog.value = false
		showReturnDialog.value = false
		showCouponDialog.value = false
		showOffersDialog.value = false
		showBatchSerialDialog.value = false
		showHistoryDialog.value = false
		showOfflineInvoicesDialog.value = false
		showCreateCustomerDialog.value = false
		showClearCartDialog.value = false
		showLogoutDialog.value = false
		showItemSelectionDialog.value = false
		showErrorDialog.value = false
		clearError()
		lastOfflinePrintDoc.value = null
	}

	return {
		// State
		isLoading,
		showPaymentDialog,
		showCustomerDialog,
		showSuccessDialog,
		showOpenShiftDialog,
		showCloseShiftDialog,
		showDraftDialog,
		showReturnDialog,
		showCouponDialog,
		showOffersDialog,
		showBatchSerialDialog,
		showHistoryDialog,
		showOfflineInvoicesDialog,
		showCreateCustomerDialog,
		showClearCartDialog,
		showLogoutDialog,
		showItemSelectionDialog,
		showErrorDialog,
		isAnyDialogOpen,
		errorDialogTitle,
		errorDialogMessage,
		errorDetails,
		errorType,
		errorRetryAction,
		errorRetryActionData,
		lastInvoiceName,
		lastInvoiceTotal,
		lastPaidAmount,
		lastOfflinePrintDoc,
		initialCustomerName,
		mobileActiveTab,
		windowWidth,
		leftPanelWidth,
		isResizing,

		// Computed
		isDesktop,

		// Actions
		setLoading,
		setWindowWidth,
		setMobileTab,
		showError,
		clearError,
		showSuccess,
		setLastOfflinePrintDoc,
		clearLastOfflinePrintDoc,
		setInitialCustomerName,
		setLeftPanelWidth,
		setResizing,
		updateLayoutBounds,
		clampLeftPanelWidth,
		resetAllDialogs,
	}
})
