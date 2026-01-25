import { createResource } from "frappe-ui"
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { useBootstrapStore } from "./bootstrap"

export const usePOSSettingsStore = defineStore("posSettings", () => {
	// State
	const settings = ref({
		pos_profile: "",
		enabled: 0,
		// Wallet & Loyalty Settings
		enable_loyalty_program: 0,
		default_loyalty_program: "",
		wallet_account: "",
		auto_create_wallet: 1,
		loyalty_to_wallet: 1,
		// General Settings
		max_discount_allowed: 0,
		use_percentage_discount: 0,
		allow_user_to_edit_additional_discount: 0,
		allow_user_to_edit_item_discount: 1, // Allow item-level discounts
		disable_rounded_total: 1, // Disable rounding for accurate totals
		allow_credit_sale: 0,
		allow_return: 0,
		allow_write_off_change: 0,
		allow_partial_payment: 0,
		use_exact_amount: 0,
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
		// Sales Persons
		enable_sales_persons: "Disabled",
	})

	const isLoading = ref(false)
	const isLoaded = ref(false)

	// Computed - Wallet & Loyalty Settings
	const enableLoyaltyProgram = computed(() =>
		Boolean(settings.value.enable_loyalty_program),
	)
	const defaultLoyaltyProgram = computed(() =>
		settings.value.default_loyalty_program || "",
	)
	const walletAccount = computed(() =>
		settings.value.wallet_account || "",
	)
	const autoCreateWallet = computed(() =>
		Boolean(settings.value.auto_create_wallet),
	)
	const loyaltyToWallet = computed(() =>
		Boolean(settings.value.loyalty_to_wallet),
	)

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
	const allowItemDiscount = computed(() =>
		Boolean(settings.value.allow_user_to_edit_item_discount),
	)
	const disableRoundedTotal = computed(() =>
		Boolean(settings.value.disable_rounded_total),
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
	const useExactAmount = computed(() =>
		Boolean(settings.value.use_exact_amount),
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

	// Computed - Sales Persons
	const enableSalesPersons = computed(() =>
		settings.value.enable_sales_persons !== "Disabled"
	)
	const salesPersonsMode = computed(() =>
		settings.value.enable_sales_persons || "Disabled"
	)
	const isSingleSalesPerson = computed(() =>
		settings.value.enable_sales_persons === "Single"
	)
	const isMultipleSalesPersons = computed(() =>
		settings.value.enable_sales_persons === "Multiple"
	)

	// Resource
	const settingsResource = createResource({
		url: "pos_next.pos_next.doctype.pos_settings.pos_settings.get_pos_settings",
		onSuccess(data) {
			if (data) {
				Object.assign(settings.value, data)
				isLoaded.value = true
			}
			isLoading.value = false
		},
		onError(error) {
			isLoading.value = false
		},
	})

	// Actions
	async function loadSettings(posProfile) {
		if (!posProfile) {
			return false
		}

		isLoading.value = true
		settings.value.pos_profile = posProfile

		// OPTIMIZATION: Check if bootstrap has preloaded the settings
		try {
			const bootstrapStore = useBootstrapStore()
			const preloadedSettings = bootstrapStore.getPreloadedPOSSettings()
			if (preloadedSettings && Object.keys(preloadedSettings).length > 0) {
				Object.assign(settings.value, preloadedSettings)
				isLoaded.value = true
				isLoading.value = false
				return true
			}
		} catch {
			// Bootstrap store may not be available, fall through to API call
		}

		// Fallback to API call
		try {
			await settingsResource.submit({ pos_profile: posProfile })
			return true
		} catch {
			return false
		}
	}

	function resetSettings() {
		settings.value = {
			pos_profile: "",
			enabled: 0,
			// Wallet & Loyalty Settings
			enable_loyalty_program: 0,
			default_loyalty_program: "",
			wallet_account: "",
			auto_create_wallet: 1,
			loyalty_to_wallet: 1,
			// General Settings
			max_discount_allowed: 0,
			use_percentage_discount: 0,
			allow_user_to_edit_additional_discount: 0,
			allow_user_to_edit_item_discount: 1,
			disable_rounded_total: 1,
			allow_credit_sale: 0,
			allow_return: 0,
			allow_write_off_change: 0,
			allow_partial_payment: 0,
			use_exact_amount: 0,
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
			enable_sales_persons: "Disabled",
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

	/**
	 * Force reload settings from server
	 * This is called when settings are changed in the settings dialog
	 * to ensure all components have the latest settings immediately
	 */
	async function reloadSettings() {
		if (!settings.value.pos_profile) {
			return false
		}

		isLoading.value = true

		try {
			await settingsResource.reload()
			return true
		} catch {
			return false
		}
	}

	return {
		// State
		settings,
		isLoading,
		isLoaded,

		// Computed - Wallet & Loyalty Settings
		enableLoyaltyProgram,
		defaultLoyaltyProgram,
		walletAccount,
		autoCreateWallet,
		loyaltyToWallet,

		// Computed - General Settings
		isEnabled,
		maxDiscountAllowed,
		usePercentageDiscount,
		allowAdditionalDiscount,
		allowItemDiscount,
		disableRoundedTotal,
		allowCreditSale,
		allowReturn,
		allowWriteOffChange,
		allowPartialPayment,
		useExactAmount,

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

		// Computed - Sales Persons
		enableSalesPersons,
		salesPersonsMode,
		isSingleSalesPerson,
		isMultipleSalesPersons,

		// Actions
		loadSettings,
		reloadSettings,
		resetSettings,
		validateDiscount,
		isNegativeStockAllowed,
		shouldEnforceStockValidation,
	}
})
