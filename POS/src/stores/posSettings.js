import { createResource } from "frappe-ui"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

export const usePOSSettingsStore = defineStore("posSettings", () => {
	// State
	const settings = ref({
		pos_profile: "",
		enabled: 0,
		// General Settings
		max_discount_allowed: 0,
		use_percentage_discount: 0,
		allow_user_to_edit_additional_discount: 0,
		allow_credit_sale: 0,
		allow_return: 0,
		allow_write_off_change: 0,
		allow_partial_payment: 0,
		// Display Settings
		default_card_view: 0,
		display_item_code: 0,
		show_customer_balance: 0,
		hide_expected_amount: 0,
		display_discount_percentage: 0,
		display_discount_amount: 0,
		// Operations
		allow_sales_order: 0,
		allow_select_sales_order: 0,
		create_only_sales_order: 0,
		allow_return_without_invoice: 0,
		allow_free_batch_return: 0,
		allow_print_draft_invoices: 0,
		// Pricing & Display
		decimal_precision: "2",
		// Customer Settings
		allow_customer_purchase_order: 0,
		allow_duplicate_customer_names: 0,
		fetch_coupon: 0,
		// Printing
		allow_print_last_invoice: 0,
		silent_print: 0,
		// Delivery
		use_delivery_charges: 0,
		auto_set_delivery_charges: 0,
		// Advanced Settings
		use_limit_search: 0,
		search_limit: 1000,
		allow_submissions_in_background_job: 0,
		allow_delete_offline_invoice: 0,
		allow_change_posting_date: 0,
		// Miscellaneous
		input_qty: 0,
		allow_negative_stock: 0,
	})

	const isLoading = ref(false)
	const isLoaded = ref(false)

	// Computed - General Settings
	const isEnabled = computed(() => Boolean(settings.value.enabled))
	const maxDiscountAllowed = computed(
		() => Number.parseFloat(settings.value.max_discount_allowed) || 0,
	)
	const usePercentageDiscount = computed(() =>
		Boolean(settings.value.use_percentage_discount),
	)
	const allowAdditionalDiscount = computed(() =>
		Boolean(settings.value.allow_user_to_edit_additional_discount),
	)
	const allowCreditSale = computed(() =>
		Boolean(settings.value.allow_credit_sale),
	)
	const allowReturn = computed(() => Boolean(settings.value.allow_return))
	const allowWriteOffChange = computed(() =>
		Boolean(settings.value.allow_write_off_change),
	)
	const allowPartialPayment = computed(() =>
		Boolean(settings.value.allow_partial_payment),
	)

	// Computed - Display Settings
	const defaultCardView = computed(() =>
		Boolean(settings.value.default_card_view),
	)
	const displayItemCode = computed(() =>
		Boolean(settings.value.display_item_code),
	)
	const showCustomerBalance = computed(() =>
		Boolean(settings.value.show_customer_balance),
	)
	const hideExpectedAmount = computed(() =>
		Boolean(settings.value.hide_expected_amount),
	)
	const displayDiscountPercentage = computed(() =>
		Boolean(settings.value.display_discount_percentage),
	)
	const displayDiscountAmount = computed(() =>
		Boolean(settings.value.display_discount_amount),
	)

	// Computed - Operations
	const allowSalesOrder = computed(() =>
		Boolean(settings.value.allow_sales_order),
	)
	const allowSelectSalesOrder = computed(() =>
		Boolean(settings.value.allow_select_sales_order),
	)
	const createOnlySalesOrder = computed(() =>
		Boolean(settings.value.create_only_sales_order),
	)
	const allowReturnWithoutInvoice = computed(() =>
		Boolean(settings.value.allow_return_without_invoice),
	)
	const allowFreeBatchReturn = computed(() =>
		Boolean(settings.value.allow_free_batch_return),
	)
	const allowPrintDraftInvoices = computed(() =>
		Boolean(settings.value.allow_print_draft_invoices),
	)

	// Computed - Pricing & Display
	const decimalPrecision = computed(
		() => Number.parseInt(settings.value.decimal_precision) || 2,
	)

	// Computed - Customer Settings
	const allowCustomerPurchaseOrder = computed(() =>
		Boolean(settings.value.allow_customer_purchase_order),
	)
	const allowDuplicateCustomerNames = computed(() =>
		Boolean(settings.value.allow_duplicate_customer_names),
	)
	const fetchCoupon = computed(() => Boolean(settings.value.fetch_coupon))

	// Computed - Printing
	const allowPrintLastInvoice = computed(() =>
		Boolean(settings.value.allow_print_last_invoice),
	)
	const silentPrint = computed(() => Boolean(settings.value.silent_print))

	// Computed - Delivery
	const useDeliveryCharges = computed(() =>
		Boolean(settings.value.use_delivery_charges),
	)
	const autoSetDeliveryCharges = computed(() =>
		Boolean(settings.value.auto_set_delivery_charges),
	)

	// Computed - Advanced Settings
	const useLimitSearch = computed(() =>
		Boolean(settings.value.use_limit_search),
	)
	const searchLimit = computed(
		() => Number.parseInt(settings.value.search_limit) || 1000,
	)
	const allowSubmissionsInBackgroundJob = computed(() =>
		Boolean(settings.value.allow_submissions_in_background_job),
	)
	const allowDeleteOfflineInvoice = computed(() =>
		Boolean(settings.value.allow_delete_offline_invoice),
	)
	const allowChangePostingDate = computed(() =>
		Boolean(settings.value.allow_change_posting_date),
	)

	// Computed - Miscellaneous
	const inputQty = computed(() => Boolean(settings.value.input_qty))
	const allowNegativeStock = computed(() =>
		Boolean(settings.value.allow_negative_stock),
	)

	// Resource
	const settingsResource = createResource({
		url: "pos_next.pos_next.doctype.pos_settings.pos_settings.get_pos_settings",
		onSuccess(data) {
			console.log('[POSSettings Store] Loaded settings:', data)
			if (data) {
				Object.assign(settings.value, data)
				console.log('[POSSettings Store] Updated settings.value:', settings.value)
				console.log('[POSSettings Store] allowPartialPayment computed:', Boolean(settings.value.allow_partial_payment))
				isLoaded.value = true
			}
			isLoading.value = false
		},
		onError(error) {
			console.error("Failed to load POS Settings:", error)
			isLoading.value = false
		},
	})

	// Actions
	async function loadSettings(posProfile) {
		if (!posProfile) {
			console.warn("Cannot load POS Settings: POS Profile not provided")
			return false
		}

		isLoading.value = true
		settings.value.pos_profile = posProfile

		try {
			await settingsResource.submit({ pos_profile: posProfile })
			return true
		} catch (error) {
			console.error("Error loading POS Settings:", error)
			return false
		}
	}

	function resetSettings() {
		settings.value = {
			pos_profile: "",
			enabled: 0,
			max_discount_allowed: 0,
			use_percentage_discount: 0,
			allow_user_to_edit_additional_discount: 0,
			allow_credit_sale: 0,
			allow_return: 0,
			allow_write_off_change: 0,
			allow_partial_payment: 0,
			default_card_view: 0,
			display_item_code: 0,
			show_customer_balance: 0,
			hide_expected_amount: 0,
			display_discount_percentage: 0,
			display_discount_amount: 0,
			allow_sales_order: 0,
			allow_select_sales_order: 0,
			create_only_sales_order: 0,
			allow_return_without_invoice: 0,
			allow_free_batch_return: 0,
			allow_print_draft_invoices: 0,
			decimal_precision: "2",
			allow_customer_purchase_order: 0,
			allow_duplicate_customer_names: 0,
			fetch_coupon: 0,
			allow_print_last_invoice: 0,
			silent_print: 0,
			use_delivery_charges: 0,
			auto_set_delivery_charges: 0,
			use_limit_search: 0,
			search_limit: 1000,
			allow_submissions_in_background_job: 0,
			allow_delete_offline_invoice: 0,
			allow_change_posting_date: 0,
			input_qty: 0,
			allow_negative_stock: 0,
		}
		isLoaded.value = false
	}

	/**
	 * Validate discount amount against max discount setting
	 * @param {number} discountPercentage - The discount percentage to validate
	 * @returns {boolean} - True if discount is allowed, false otherwise
	 */
	function validateDiscount(discountPercentage) {
		if (!isEnabled.value || maxDiscountAllowed.value === 0) {
			return true // No restriction if settings disabled or max = 0
		}

		return discountPercentage <= maxDiscountAllowed.value
	}

	/**
	 * Check if negative stock is allowed
	 * @returns {boolean} - True if negative stock is allowed
	 */
	function isNegativeStockAllowed() {
		return isEnabled.value && Boolean(settings.value.allow_negative_stock)
	}

	/**
	 * Check if stock validation should be enforced
	 * @returns {boolean} - True if stock validation should prevent negative stock
	 */
	function shouldEnforceStockValidation() {
		return isEnabled.value && !Boolean(settings.value.allow_negative_stock)
	}

	return {
		// State
		settings,
		isLoading,
		isLoaded,

		// Computed - General Settings
		isEnabled,
		maxDiscountAllowed,
		usePercentageDiscount,
		allowAdditionalDiscount,
		allowCreditSale,
		allowReturn,
		allowWriteOffChange,
		allowPartialPayment,

		// Computed - Display Settings
		defaultCardView,
		displayItemCode,
		showCustomerBalance,
		hideExpectedAmount,
		displayDiscountPercentage,
		displayDiscountAmount,

		// Computed - Operations
		allowSalesOrder,
		allowSelectSalesOrder,
		createOnlySalesOrder,
		allowReturnWithoutInvoice,
		allowFreeBatchReturn,
		allowPrintDraftInvoices,

		// Computed - Pricing & Display
		decimalPrecision,

		// Computed - Customer Settings
		allowCustomerPurchaseOrder,
		allowDuplicateCustomerNames,
		fetchCoupon,

		// Computed - Printing
		allowPrintLastInvoice,
		silentPrint,

		// Computed - Delivery
		useDeliveryCharges,
		autoSetDeliveryCharges,

		// Computed - Advanced Settings
		useLimitSearch,
		searchLimit,
		allowSubmissionsInBackgroundJob,
		allowDeleteOfflineInvoice,
		allowChangePostingDate,

		// Computed - Miscellaneous
		inputQty,
		allowNegativeStock,

		// Actions
		loadSettings,
		resetSettings,
		validateDiscount,
		isNegativeStockAllowed,
		shouldEnforceStockValidation,
	}
})
