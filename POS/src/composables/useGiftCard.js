/**
 * Gift Card Composable
 *
 * Handles gift card operations including:
 * - Loading available gift cards
 * - Applying gift cards to invoices
 * - Gift card balance management
 * - Gift card splitting logic
 */

import { createResource } from "frappe-ui"
import { ref, computed } from "vue"

export function useGiftCard() {
	const giftCards = ref([])
	const loading = ref(false)
	const error = ref(null)

	/**
	 * Resource to load available gift cards
	 */
	const giftCardsResource = createResource({
		url: "pos_next.api.offers.get_active_coupons",
		auto: false,
		onSuccess(data) {
			// Handle frappe response wrapper
			const cards = data?.message || data || []
			giftCards.value = cards
			error.value = null
		},
		onError(err) {
			console.error("Error loading gift cards:", err)
			error.value = err
			giftCards.value = []
		},
	})

	/**
	 * Resource to apply a gift card
	 */
	const applyGiftCardResource = createResource({
		url: "pos_next.api.gift_cards.apply_gift_card",
		auto: false,
	})

	/**
	 * Resource to get gift cards created from an invoice
	 */
	const giftCardsFromInvoiceResource = createResource({
		url: "pos_next.api.gift_cards.get_gift_cards_from_invoice",
		auto: false,
	})

	/**
	 * Load available gift cards for a customer and company
	 *
	 * @param {Object} params - Parameters
	 * @param {string} params.customer - Customer name (optional for anonymous cards)
	 * @param {string} params.company - Company name
	 * @returns {Promise<Array>} - List of available gift cards
	 */
	async function loadGiftCards({ customer, company }) {
		if (!company) {
			giftCards.value = []
			return []
		}

		loading.value = true
		try {
			await giftCardsResource.fetch({
				customer: customer || null,
				company,
			})
			return giftCards.value
		} catch (err) {
			console.error("Failed to load gift cards:", err)
			return []
		} finally {
			loading.value = false
		}
	}

	/**
	 * Apply a gift card to an invoice
	 *
	 * @param {Object} params - Parameters
	 * @param {string} params.couponCode - Gift card code
	 * @param {number} params.invoiceTotal - Invoice total amount
	 * @param {string} params.customer - Customer name (optional)
	 * @param {string} params.company - Company name
	 * @returns {Promise<Object>} - Application result with discount amount
	 */
	async function applyGiftCard({ couponCode, invoiceTotal, customer, company }) {
		try {
			const result = await applyGiftCardResource.fetch({
				coupon_code: couponCode,
				invoice_total: invoiceTotal,
				customer: customer || null,
				company,
			})

			const data = result?.message || result
			return data
		} catch (err) {
			console.error("Failed to apply gift card:", err)
			return {
				success: false,
				message: err.message || __("Failed to apply gift card"),
			}
		}
	}

	/**
	 * Get gift cards created from a specific invoice
	 * Called after invoice submission to check if gift cards were created
	 *
	 * @param {string} invoiceName - Name of the invoice
	 * @returns {Promise<Array>} - List of gift cards created from this invoice
	 */
	async function getGiftCardsFromInvoice(invoiceName) {
		if (!invoiceName) {
			console.log("[useGiftCard] No invoice name provided")
			return []
		}

		try {
			console.log("[useGiftCard] Fetching gift cards for invoice:", invoiceName)
			const result = await giftCardsFromInvoiceResource.fetch({
				invoice_name: invoiceName,
			})
			console.log("[useGiftCard] Raw API result:", result)

			const data = result?.message || result || []
			console.log("[useGiftCard] Parsed data:", data)
			return Array.isArray(data) ? data : []
		} catch (err) {
			console.error("Failed to get gift cards from invoice:", err)
			return []
		}
	}

	/**
	 * Calculate discount amount for a gift card
	 *
	 * @param {Object} giftCard - Gift card object
	 * @param {number} invoiceTotal - Invoice total amount
	 * @returns {Object} - Discount calculation result
	 */
	function calculateGiftCardDiscount(giftCard, invoiceTotal) {
		if (!giftCard) {
			return { discount: 0, willSplit: false, remainingBalance: 0 }
		}

		const balance = giftCard.balance || giftCard.gift_card_amount || giftCard.discount_amount || 0
		const discount = Math.min(balance, invoiceTotal)
		const willSplit = balance > invoiceTotal
		const remainingBalance = willSplit ? balance - invoiceTotal : 0

		return {
			discount,
			willSplit,
			remainingBalance,
			availableBalance: balance,
		}
	}

	/**
	 * Format gift card for display
	 *
	 * @param {Object} giftCard - Gift card object
	 * @returns {Object} - Formatted gift card info
	 */
	function formatGiftCard(giftCard) {
		return {
			code: giftCard.coupon_code,
			name: giftCard.coupon_name || giftCard.name,
			balance: giftCard.balance || giftCard.gift_card_amount || giftCard.discount_amount || 0,
			originalAmount: giftCard.original_amount || giftCard.balance,
			customer: giftCard.customer,
			customerName: giftCard.customer_name,
			validUpto: giftCard.valid_upto,
			isAnonymous: !giftCard.customer,
		}
	}

	/**
	 * Gift cards grouped by type (customer-specific vs anonymous)
	 */
	const groupedGiftCards = computed(() => {
		const customerCards = giftCards.value.filter((gc) => gc.customer)
		const anonymousCards = giftCards.value.filter((gc) => !gc.customer)

		return {
			customerCards,
			anonymousCards,
			hasCustomerCards: customerCards.length > 0,
			hasAnonymousCards: anonymousCards.length > 0,
		}
	})

	/**
	 * Total available balance across all gift cards
	 */
	const totalAvailableBalance = computed(() => {
		return giftCards.value.reduce((sum, gc) => {
			const balance = gc.balance || gc.gift_card_amount || gc.discount_amount || 0
			return sum + balance
		}, 0)
	})

	/**
	 * Check if there are any gift cards available
	 */
	const hasGiftCards = computed(() => giftCards.value.length > 0)

	return {
		// State
		giftCards,
		loading,
		error,

		// Computed
		groupedGiftCards,
		totalAvailableBalance,
		hasGiftCards,

		// Methods
		loadGiftCards,
		applyGiftCard,
		getGiftCardsFromInvoice,
		calculateGiftCardDiscount,
		formatGiftCard,

		// Resources (for advanced usage)
		giftCardsResource,
		applyGiftCardResource,
		giftCardsFromInvoiceResource,
	}
}
