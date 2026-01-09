import { useInvoice } from "@/composables/useInvoice"
import { usePOSOffersStore } from "@/stores/posOffers"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { parseError } from "@/utils/errorHandler"
import {
	checkStockAvailability,
	formatStockError,
} from "@/utils/stockValidator"
import { offlineState } from "@/utils/offline/offlineState"
import { useToast } from "@/composables/useToast"
import { defineStore } from "pinia"
import { computed, nextTick, ref, toRaw, watch } from "vue"

/**
 * Creates an async task queue that ensures only one operation runs at a time.
 * Subsequent calls while processing will be queued and the latest one executed.
 */
function createAsyncQueue() {
	let isProcessing = false
	let pendingTask = null
	let currentAbortController = null

	return {
		/**
		 * Enqueue a task. If already processing, replaces any pending task.
		 * @param {Function} taskFn - Async function to execute
		 * @returns {Promise} Resolves when task completes or is superseded
		 */
		async enqueue(taskFn) {
			// If currently processing, queue this as the next task (replacing any pending)
			if (isProcessing) {
				pendingTask = taskFn
				return
			}

			isProcessing = true
			currentAbortController = new AbortController()

			try {
				await taskFn(currentAbortController.signal)
			} finally {
				isProcessing = false
				currentAbortController = null

				// Process pending task if any
				if (pendingTask) {
					const next = pendingTask
					pendingTask = null
					await this.enqueue(next)
				}
			}
		},

		/**
		 * Cancel current operation and clear pending tasks
		 */
		cancel() {
			if (currentAbortController) {
				currentAbortController.abort()
			}
			pendingTask = null
		},

		/**
		 * Check if queue is currently processing
		 */
		get isProcessing() {
			return isProcessing
		},

		/**
		 * Check if there's a pending task
		 */
		get hasPending() {
			return pendingTask !== null
		}
	}
}

export const usePOSCartStore = defineStore("posCart", () => {
	// Use the existing invoice composable for core functionality
	const {
		invoiceItems,
		customer,
		subtotal,
		totalTax,
		totalDiscount,
		grandTotal,
		posProfile,
		posOpeningShift,
		payments,
		salesTeam,
		additionalDiscount,
		taxInclusive,
		isSubmitting,
		addItem: addItemToInvoice,
		removeItem,
		updateItemQuantity,
		submitInvoice: baseSubmitInvoice,
		clearCart: clearInvoiceCart,
		loadTaxRules,
		setTaxInclusive,
		setDefaultCustomer,
		applyDiscount,
		removeDiscount,
		applyOffersResource,
		getItemDetailsResource,
		recalculateItem,
		rebuildIncrementalCache,
		formatItemsForSubmission,
	} = useInvoice()

	const offersStore = usePOSOffersStore()
	const settingsStore = usePOSSettingsStore()

	// Additional cart state
	const pendingItem = ref(null)
	const pendingItemQty = ref(1)
	const appliedOffers = ref([])
	const appliedCoupon = ref(null)
	const selectionMode = ref("uom") // 'uom' or 'variant'
	const suppressOfferReapply = ref(false)
	const currentDraftId = ref(null)
	const targetDoctype = ref("Sales Invoice")

	// Offer processing state management
	const offerProcessingState = ref({
		isProcessing: false,      // True while any offer operation is running
		isAutoProcessing: false,  // True during automatic offer processing
		lastProcessedAt: 0,       // Timestamp of last successful processing
		lastCartHash: '',         // Hash of cart state when last processed
		error: null,              // Last error if any
		retryCount: 0,            // Number of consecutive failures
	})

	// Generation counter to track cart changes and invalidate stale operations
	let cartGeneration = 0

	// Async queue for sequential offer processing
	const offerQueue = createAsyncQueue()

	// Computed for backward compatibility and UI binding
	const isProcessingOffers = computed(() => offerProcessingState.value.isProcessing)

	/**
	 * Generates a comprehensive hash of the current cart state.
	 * Used to detect ANY change that might affect offer eligibility.
	 */
	function generateCartHash() {
		const items = invoiceItems.value
		const parts = [
			// Item details: code, quantity, uom, discount
			items.map(i => `${i.item_code}:${i.quantity}:${i.uom || ''}:${i.discount_percentage || 0}`).join('|'),
			// Total item count
			items.length.toString(),
			// Subtotal (rounded to avoid floating point issues)
			Math.round((subtotal.value || 0) * 100).toString(),
			// Customer
			customer.value?.name || customer.value || 'none',
			// Applied offers count
			appliedOffers.value.length.toString(),
		]
		return parts.join('::')
	}

	// Toast composable
	const { showSuccess, showError, showWarning } = useToast()

	// Computed
	const itemCount = computed(() => invoiceItems.value.length)
	const isEmpty = computed(() => invoiceItems.value.length === 0)
	const hasCustomer = computed(() => !!customer.value)

	// Actions
	function addItem(item, qty = 1, autoAdd = false, currentProfile = null) {
		// Check stock availability before adding to cart
		// Skip validation for batch/serial items - they have their own validation in the dialog
		// Check for stock items AND Product Bundles (bundles now have calculated stock)
		// Also check items with actual_qty defined (catches misconfigured items)

		// Determine if this item should be validated for stock
		// Include: stock items, bundles, OR items with actual_qty defined (catches misconfigured items)
		// CRITICAL: If is_stock_item is explicitly false/0, we must skip validation even if actual_qty exists
		const isNonStockItem = item.is_stock_item === 0 || item.is_stock_item === false
		const hasActualQty = item.actual_qty !== undefined || item.stock_qty !== undefined
		const shouldValidateStock = !isNonStockItem && (item.is_stock_item || item.is_bundle || hasActualQty)

		if (currentProfile && !autoAdd && settingsStore.shouldEnforceStockValidation() && shouldValidateStock && !item.has_serial_no && !item.has_batch_no) {
			const warehouse = item.warehouse || currentProfile.warehouse
			const actualQty =
				item.actual_qty !== undefined ? item.actual_qty : item.stock_qty || 0

			if (warehouse && actualQty !== undefined && actualQty !== null) {
				const stockCheck = checkStockAvailability({
					itemCode: item.item_code,
					qty: qty,
					warehouse: warehouse,
					actualQty: actualQty,
				})

				if (!stockCheck.available) {
					const itemType = item.is_bundle ? "Bundle" : "Item"
					const errorMsg = formatStockError(
						item.item_name,
						qty,
						stockCheck.actualQty,
						warehouse,
					)

					throw new Error(errorMsg.replace("Item", itemType))
				}
			}
		}

		// Add item to cart - no toast notification for performance
		addItemToInvoice(item, qty)
	}

	function clearCart() {
		// Cancel any pending offer processing
		debouncedProcessOffers.cancel()
		offerQueue.cancel()

		clearInvoiceCart()
		customer.value = null
		appliedOffers.value = []
		appliedCoupon.value = null
		currentDraftId.value = null
		targetDoctype.value = "Sales Invoice"

		// Reset offer processing state
		suppressOfferReapply.value = false
		offerProcessingState.value.lastCartHash = ''
		offerProcessingState.value.error = null
		offerProcessingState.value.retryCount = 0

		// Sync the empty snapshot
		syncOfferSnapshot()
	}

	function setTargetDoctype(doctype) {
		targetDoctype.value = doctype
	}

	const deliveryDate = ref("")

	function setDeliveryDate(date) {
		deliveryDate.value = date
	}

	async function submitInvoice() {
		if (invoiceItems.value.length === 0) {
			showWarning(__("Cart is empty"))
			return
		}
		if (!customer.value) {
			showWarning(__("Please select a customer"))
			return
		}

		return await baseSubmitInvoice(targetDoctype.value, deliveryDate.value)
	}

	async function createSalesOrder() {
		return await submitInvoice()
	}



	function setCustomer(selectedCustomer) {
		customer.value = selectedCustomer
	}

	function setPendingItem(item, qty = 1, mode = "uom") {
		pendingItem.value = item
		pendingItemQty.value = qty
		selectionMode.value = mode
	}

	function clearPendingItem() {
		pendingItem.value = null
		pendingItemQty.value = 1
		selectionMode.value = "uom"
	}

	// Discount & Offer Management
	function applyDiscountToCart(discount) {
		applyDiscount(discount)
		appliedCoupon.value = discount
		showSuccess(__('{0} applied successfully', [discount.name]))
	}

	function removeDiscountFromCart() {
		suppressOfferReapply.value = true
		appliedOffers.value = []
		removeDiscount()
		appliedCoupon.value = null
		showSuccess(__("Discount has been removed from cart"))
	}

	function buildOfferEvaluationPayload(currentProfile) {
		// Use toRaw() to ensure we get current, non-reactive values (prevents stale cached quantities)
		const rawItems = toRaw(invoiceItems.value)

		return {
			doctype: "Sales Invoice",
			pos_profile: posProfile.value,
			customer:
				customer.value?.name || customer.value || currentProfile?.customer,
			company: currentProfile?.company,
			selling_price_list: currentProfile?.selling_price_list,
			currency: currentProfile?.currency,
			discount_amount: additionalDiscount.value || 0,
			coupon_code: appliedCoupon.value?.name || "",
			items: rawItems.map((item) => ({
				item_code: item.item_code,
				item_name: item.item_name,
				qty: item.quantity,
				rate: item.rate,
				uom: item.uom,
				warehouse: item.warehouse,
				conversion_factor: item.conversion_factor || 1,
				price_list_rate: item.price_list_rate || item.rate,
				discount_percentage: item.discount_percentage || 0,
				discount_amount: item.discount_amount || 0,
			})),
		}
	}

	/**
	 * Check if pricing_rules has a value (handles string or array).
	 */
	function hasPricingRules(value) {
		if (!value) return false
		if (Array.isArray(value)) return value.length > 0
		return typeof value === 'string' && value.trim().length > 0
	}

	/**
	 * Sync discounts from server response to cart items.
	 * Server returns items in same order as sent (handles duplicate SKUs).
	 */
	function applyDiscountsFromServer(serverItems) {
		if (!Array.isArray(serverItems)) return false

		let hasDiscounts = false

		invoiceItems.value.forEach((item, index) => {
			const serverItem = serverItems[index] || {}
			const discountPct = Number.parseFloat(serverItem.discount_percentage) || 0
			const discountAmt = Number.parseFloat(serverItem.discount_amount) || 0

			// Only update if server applied a pricing rule or discount
			if (hasPricingRules(serverItem.pricing_rules) || discountPct > 0 || discountAmt > 0) {
				item.discount_percentage = discountPct
				item.discount_amount = discountAmt
				item.pricing_rules = serverItem.pricing_rules
				hasDiscounts = discountPct > 0 || discountAmt > 0
			}
			// Otherwise preserve existing manual discount

			recalculateItem(item)
		})

		rebuildIncrementalCache()
		return hasDiscounts
	}

	/**
	 * Parses the backend offer response and applies free item quantities to cart items
	 *
	 * @param {Array} freeItems - Array of free items from backend (e.g., [{item_code, qty, uom}])
	 * @returns {void}
	 *
	 * @example
	 * // Backend returns: [{ item_code: "SKU001", qty: 1, uom: "Nos" }]
	 * // Cart has: [{ item_code: "SKU001", quantity: 2, uom: "Nos" }]
	 * // Result: Cart item gets free_qty = 1 (shown as "2 items + 1 FREE")
	 */
	function processFreeItems(freeItems) {
		// Reset all free quantities
		invoiceItems.value.forEach(item => {
			item.free_qty = 0
		})

		// Early return if no free items
		if (!Array.isArray(freeItems) || freeItems.length === 0) {
			return
		}

		// Match free items to cart items and set free_qty
		for (const freeItem of freeItems) {
			const freeQty = Number.parseFloat(freeItem.qty) || 0
			if (freeQty <= 0) continue

			// Find matching cart item by item_code and uom
			const cartItem = invoiceItems.value.find(
				item => item.item_code === freeItem.item_code &&
				(item.uom || item.stock_uom) === (freeItem.uom || freeItem.stock_uom)
			)

			if (cartItem) {
				cartItem.free_qty = freeQty
			}
		}
	}

	/**
	 * Extracts and normalizes the offer response from backend
	 *
	 * @param {Object} response - Raw API response from backend
	 * @returns {Object} Normalized response with items, freeItems, and appliedRules
	 *
	 * IMPORTANT: No fallback for appliedRules - we trust the backend's response.
	 * If backend returns empty applied_pricing_rules, it means NO offers were applied.
	 * Previously we had a fallback that caused false "applied" status.
	 */
	function parseOfferResponse(response) {
		const payload = response?.message || response || {}

		return {
			items: Array.isArray(payload.items) ? payload.items : [],
			freeItems: Array.isArray(payload.free_items) ? payload.free_items : [],
			// CRITICAL: Only trust explicitly returned rules - NO FALLBACK
			// If backend doesn't return applied_pricing_rules, NO offers were applied
			appliedRules: Array.isArray(payload.applied_pricing_rules) ? payload.applied_pricing_rules : []
		}
	}

	function getAppliedOfferCodes() {
		return appliedOffers.value.map((entry) => entry.code)
	}

	function filterActiveOffers(appliedRuleNames = []) {
		if (!Array.isArray(appliedRuleNames) || appliedRuleNames.length === 0) {
			appliedOffers.value = []
			return
		}

		appliedOffers.value = appliedOffers.value.filter((entry) =>
			appliedRuleNames.includes(entry.code),
		)
	}

	async function applyOffer(offer, currentProfile, offersDialogRef = null) {
		if (!offer) {
			console.error("No offer provided")
			offersDialogRef?.resetApplyingState()
			return false
		}

		const offerCode = offer.name
		const existingCodes = getAppliedOfferCodes()
		const alreadyApplied = existingCodes.includes(offerCode)

		if (alreadyApplied) {
			return await removeOffer(offerCode, currentProfile, offersDialogRef)
		}

		if (!posProfile.value || invoiceItems.value.length === 0) {
			showWarning(__("Add items to the cart before applying an offer."))
			offersDialogRef?.resetApplyingState()
			return false
		}

		// Cancel any pending auto-processing since user is manually applying
		debouncedProcessOffers.cancel()
		offerQueue.cancel()

		let result = false

		await offerQueue.enqueue(async (signal) => {
			// Check if operation was cancelled
			if (signal?.aborted) return

			try {
				offerProcessingState.value.isProcessing = true
				offerProcessingState.value.error = null

				const invoiceData = buildOfferEvaluationPayload(currentProfile)
				const offerNames = [...new Set([...existingCodes, offerCode])]

				const response = await applyOffersResource.submit({
					invoice_data: invoiceData,
					selected_offers: offerNames,
				})

				// Check if cancelled during API call
				if (signal?.aborted) return

				const { items: responseItems, freeItems, appliedRules } =
					parseOfferResponse(response)

				suppressOfferReapply.value = true
				applyDiscountsFromServer(responseItems)
				processFreeItems(freeItems)
				filterActiveOffers(appliedRules)

				const offerApplied = appliedRules.includes(offerCode)

				if (!offerApplied) {
					// No new offer applied - restore previous state without new offer
					if (existingCodes.length) {
						try {
							const rollbackResponse = await applyOffersResource.submit({
								invoice_data: invoiceData,
								selected_offers: existingCodes,
							})
							const {
								items: rollbackItems,
								freeItems: rollbackFreeItems,
								appliedRules: rollbackRules,
							} = parseOfferResponse(rollbackResponse)

							applyDiscountsFromServer(rollbackItems)
							processFreeItems(rollbackFreeItems)
							filterActiveOffers(rollbackRules)
						} catch (rollbackError) {
							console.error("Error rolling back offers:", rollbackError)
						}
					}

					showWarning(__("Your cart doesn't meet the requirements for this offer."))
					offersDialogRef?.resetApplyingState()
					result = false
					return
				}

				const offerRuleCodes = appliedRules.includes(offerCode)
					? appliedRules.filter((ruleName) => ruleName === offerCode)
					: [offerCode]

				const updatedEntries = appliedOffers.value.filter(
					(entry) => entry.code !== offerCode,
				)
				updatedEntries.push({
					name: offer.title || offer.name,
					code: offerCode,
					offer, // Store full offer object for validation
					source: "manual",
					applied: true,
					rules: offerRuleCodes,
					// Store constraints for quick validation
					min_qty: offer.min_qty,
					max_qty: offer.max_qty,
					min_amt: offer.min_amt,
					max_amt: offer.max_amt,
				})
				appliedOffers.value = updatedEntries

				offerProcessingState.value.lastProcessedAt = Date.now()

				// Wait for Vue reactivity to propagate before showing toast
				await nextTick()

				showSuccess(__('{0} applied successfully', [(offer.title || offer.name)]))
				result = true
			} catch (error) {
				if (signal?.aborted) return
				console.error("Error applying offer:", error)
				offerProcessingState.value.error = error.message
				showError(__("Failed to apply offer. Please try again."))
				offersDialogRef?.resetApplyingState()
				result = false
			} finally {
				offerProcessingState.value.isProcessing = false
			}
		})

		return result
	}

	async function removeOffer(
		offer,
		currentProfile = null,
		offersDialogRef = null,
	) {
		const offerCode =
			typeof offer === "string" ? offer : offer?.name || offer?.code

		// Cancel any pending auto-processing
		debouncedProcessOffers.cancel()

		if (!offerCode) {
			// Remove all offers - immediate operation, no queue needed
			offerQueue.cancel()
			suppressOfferReapply.value = true
			appliedOffers.value = []
			processFreeItems([]) // Remove all free items
			removeDiscount()
			await nextTick()
			showSuccess(__("Offer has been removed from cart"))
			offersDialogRef?.resetApplyingState()
			return true
		}

		const remainingOffers = appliedOffers.value.filter(
			(entry) => entry.code !== offerCode,
		)
		const remainingCodes = remainingOffers.map((entry) => entry.code)

		if (remainingCodes.length === 0) {
			// All offers removed - immediate operation
			offerQueue.cancel()
			suppressOfferReapply.value = true
			appliedOffers.value = []
			processFreeItems([]) // Remove all free items
			removeDiscount()
			await nextTick()
			showSuccess(__("Offer has been removed from cart"))
			offersDialogRef?.resetApplyingState()
			return true
		}

		let result = false

		await offerQueue.enqueue(async (signal) => {
			if (signal?.aborted) return

			try {
				offerProcessingState.value.isProcessing = true
				offerProcessingState.value.error = null

				const invoiceData = buildOfferEvaluationPayload(currentProfile)

				const response = await applyOffersResource.submit({
					invoice_data: invoiceData,
					selected_offers: remainingCodes,
				})

				if (signal?.aborted) return

				const { items: responseItems, freeItems, appliedRules } =
					parseOfferResponse(response)

				suppressOfferReapply.value = true
				applyDiscountsFromServer(responseItems)
				processFreeItems(freeItems)
				filterActiveOffers(appliedRules)

				appliedOffers.value = appliedOffers.value.filter((entry) =>
					remainingCodes.includes(entry.code),
				)

				offerProcessingState.value.lastProcessedAt = Date.now()

				await nextTick()
				showSuccess(__("Offer has been removed from cart"))
				offersDialogRef?.resetApplyingState()
				result = true
			} catch (error) {
				if (signal?.aborted) return
				console.error("Error removing offer:", error)
				offerProcessingState.value.error = error.message
				showError(__("Failed to update cart after removing offer."))
				offersDialogRef?.resetApplyingState()
				result = false
			} finally {
				offerProcessingState.value.isProcessing = false
			}
		})

		return result
	}

	/**
	 * Validates applied offers and removes invalid ones when cart changes
	 * This function is called automatically when items are added/removed or quantities change
	 * @param {Object} currentProfile - Current POS profile
	 * @param {AbortSignal} signal - Optional abort signal for cancellation
	 */
	/**
	 * Validates applied offers and removes invalid ones when cart changes.
	 * This function is called from processOffersInternal - it does NOT manage
	 * suppressOfferReapply flag (that's handled by the caller).
	 * @param {Object} currentProfile - Current POS profile
	 * @param {AbortSignal} signal - Optional abort signal for cancellation
	 * @returns {boolean} True if any offers were removed
	 */
	async function reapplyOffer(currentProfile, signal = null) {
		// Clear offers if cart is empty
		if (invoiceItems.value.length === 0 && appliedOffers.value.length) {
			appliedOffers.value = []
			processFreeItems([]) // Remove all free items when cart is empty
			return true
		}

		// Only validate if there are applied offers
		if (appliedOffers.value.length === 0 || invoiceItems.value.length === 0) {
			return false
		}

		// Check if operation was cancelled
		if (signal?.aborted) return false

		try {
			// Build current cart snapshot for validation
			const cartSnapshot = buildCartSnapshot()

			// Check each applied offer against current cart state
			const invalidOffers = []
			for (const appliedOffer of appliedOffers.value) {
				const offer = appliedOffer.offer
				if (!offer) continue

				// Use offersStore to check eligibility
				offersStore.updateCartSnapshot(cartSnapshot)
				const { eligible, reason } = offersStore.checkOfferEligibility(offer)

				if (!eligible) {
					invalidOffers.push({
						...appliedOffer,
						reason
					})
				}
			}

			// Check for cancellation
			if (signal?.aborted) return false

			// If any offers are invalid, remove them and reapply remaining
			if (invalidOffers.length > 0) {
				const validOfferCodes = appliedOffers.value
					.filter(o => !invalidOffers.find(inv => inv.code === o.code))
					.map(o => o.code)

				if (validOfferCodes.length === 0) {
					// All offers invalid - clear everything
					appliedOffers.value = []
					processFreeItems([])

					// Reset all item rates to original (remove discounts)
					invoiceItems.value.forEach(item => {
						if (item.pricing_rules && item.pricing_rules.length > 0) {
							item.discount_percentage = 0
							item.discount_amount = 0
							item.pricing_rules = []
							recalculateItem(item)
						}
					})
					rebuildIncrementalCache()
				} else {
					// Reapply only valid offers
					const invoiceData = buildOfferEvaluationPayload(currentProfile)
					const response = await applyOffersResource.submit({
						invoice_data: invoiceData,
						selected_offers: validOfferCodes,
					})

					if (signal?.aborted) return false

					const { items: responseItems, freeItems, appliedRules } =
						parseOfferResponse(response)

					applyDiscountsFromServer(responseItems)
					processFreeItems(freeItems)
					filterActiveOffers(appliedRules)

					// Update appliedOffers to only include valid ones
					appliedOffers.value = appliedOffers.value.filter(entry =>
						appliedRules.includes(entry.code)
					)
				}

				// Wait for Vue to update before showing toast
				await nextTick()

				// Show warning about removed offers
				const offerNames = invalidOffers.map(o => o.name).join(', ')
				showWarning(__('Offer removed: {0}. Cart no longer meets requirements.', [offerNames]))
				return true
			}
			return false
		} catch (error) {
			if (signal?.aborted) return false
			console.error("Error validating offers:", error)
			offerProcessingState.value.error = error.message
			return false
		}
	}

	/**
	 * Automatically applies ALL eligible offers when cart changes.
	 * This function is called from processOffersInternal - it does NOT check
	 * suppressOfferReapply flag (that's handled by the caller).
	 * @param {Object} currentProfile - Current POS profile
	 * @param {AbortSignal} signal - Optional abort signal for cancellation
	 */
	async function autoApplyEligibleOffers(currentProfile, signal = null) {
		// Skip if cart is empty or no offers available
		if (invoiceItems.value.length === 0 || !offersStore.hasFetched) {
			return
		}

		// Check for cancellation
		if (signal?.aborted) return

		try {
			// Build current cart snapshot
			const cartSnapshot = buildCartSnapshot()
			offersStore.updateCartSnapshot(cartSnapshot)

			// Get ALL eligible offers (not just auto-offers)
			const allEligibleOffers = offersStore.allEligibleOffers

			if (allEligibleOffers.length === 0) {
				return
			}

			// Find offers that are not yet applied
			const appliedOfferCodes = new Set(appliedOffers.value.map(o => o.code))
			const newOffers = allEligibleOffers.filter(offer =>
				!appliedOfferCodes.has(offer.name)
			)

			if (newOffers.length === 0) {
				return
			}

			// Check for cancellation before API call
			if (signal?.aborted) return

			// Apply all new eligible offers in a single batch
			const existingCodes = appliedOffers.value.map(entry => entry.code)
			const newOfferCodes = newOffers.map(offer => offer.name)
			const allCodes = [...existingCodes, ...newOfferCodes]

			const invoiceData = buildOfferEvaluationPayload(currentProfile)

			const response = await applyOffersResource.submit({
				invoice_data: invoiceData,
				selected_offers: allCodes,
			})

			// Check for cancellation after API call
			if (signal?.aborted) return

			const { items: responseItems, freeItems, appliedRules } =
				parseOfferResponse(response)

			applyDiscountsFromServer(responseItems)
			processFreeItems(freeItems)
			filterActiveOffers(appliedRules)

			// Collect newly applied offers for notification
			const newlyAppliedOffers = []

			// Add newly applied offers to the list
			for (const offer of newOffers) {
				const offerCode = offer.name
				// Check if the offer was actually applied by ERPNext
				if (!appliedRules.includes(offerCode)) {
					continue
				}

				const offerRuleCodes = appliedRules.filter(ruleName => ruleName === offerCode)
				appliedOffers.value.push({
					name: offer.title || offer.name,
					code: offerCode,
					offer, // Store full offer object for validation
					source: "auto",
					applied: true,
					rules: offerRuleCodes,
					min_qty: offer.min_qty,
					max_qty: offer.max_qty,
					min_amt: offer.min_amt,
					max_amt: offer.max_amt,
				})

				newlyAppliedOffers.push(offer.title || offer.name)
			}

			offerProcessingState.value.lastProcessedAt = Date.now()

			// Wait for Vue reactivity to propagate before showing toast
			// This ensures the UI reflects the discount when the toast appears
			await nextTick()

			// Show consolidated toast for all newly applied offers
			if (newlyAppliedOffers.length > 0) {
				if (newlyAppliedOffers.length === 1) {
					showSuccess(__('Offer applied: {0}', [newlyAppliedOffers[0]]))
				} else {
					showSuccess(__('Offers applied: {0}', [newlyAppliedOffers.join(', ')]))
				}
			}
		} catch (error) {
			if (signal?.aborted) return
			console.error("Error auto-applying offers:", error)
			offerProcessingState.value.error = error.message
		}
	}

	/**
	 * Apply offers when offline using cached offer data.
	 * Calculates discounts client-side based on offer rules.
	 *
	 * In offline mode, we:
	 * 1. Check eligibility using posOffers.checkOfferEligibility
	 * 2. Apply discount percentage/amount directly to cart items
	 * 3. Handle free items (product discounts) by setting free_qty
	 * 4. Mark offers as applied (with source: "offline")
	 *
	 * Supports:
	 * - Discount Percentage (e.g., 10% off)
	 * - Discount Amount (e.g., $5 off)
	 * - Free Items (e.g., Buy 2 Get 1 Free)
	 */
	function applyOffersOffline() {
		// Skip if cart is empty or no offers available
		if (invoiceItems.value.length === 0 || !offersStore.hasFetched) {
			return
		}

		// Verify we're actually offline
		if (!offlineState.isOffline) {
			return // Use online mode instead
		}

		try {
			// Build current cart snapshot
			const cartSnapshot = buildCartSnapshot()
			offersStore.updateCartSnapshot(cartSnapshot)

			// Get eligible auto offers
			const eligibleOffers = offersStore.autoEligibleOffers

			if (eligibleOffers.length === 0) {
				return
			}

			// Find new offers to apply (both price and product discounts)
			const appliedOfferCodes = new Set(appliedOffers.value.map(o => o.code))
			const newOffers = eligibleOffers.filter(offer => !appliedOfferCodes.has(offer.name))

			if (newOffers.length === 0) {
				return
			}

			const newlyAppliedOffers = []

			for (const offer of newOffers) {
				// Determine offer type: "Item Price" (discount) or "Give Product" (free item)
				const isProductDiscount = offer.offer === 'Give Product'

				// Find eligible items based on offer.apply_on
				let eligibleItems = []

				if (offer.apply_on === 'Item Code') {
					const eligibleCodes = offer.eligible_items || []
					eligibleItems = invoiceItems.value.filter(item =>
						eligibleCodes.includes(item.item_code)
					)
				} else if (offer.apply_on === 'Item Group') {
					const eligibleGroups = offer.eligible_item_groups || []
					eligibleItems = invoiceItems.value.filter(item =>
						eligibleGroups.includes(item.item_group)
					)
				} else if (offer.apply_on === 'Brand') {
					const eligibleBrands = offer.eligible_brands || []
					eligibleItems = invoiceItems.value.filter(item =>
						eligibleBrands.includes(item.brand)
					)
				} else if (offer.apply_on === 'Transaction') {
					// Transaction-level discount applies to all items
					eligibleItems = invoiceItems.value
				}

				if (eligibleItems.length === 0) continue

				let offerApplied = false

				if (isProductDiscount) {
					// === PRODUCT DISCOUNT (FREE ITEMS) ===
					offerApplied = applyOfflineFreeItem(offer, eligibleItems)
				} else {
					// === PRICE DISCOUNT ===
					offerApplied = applyOfflinePriceDiscount(offer, eligibleItems)
				}

				if (offerApplied) {
					// Mark offer as applied
					appliedOffers.value.push({
						name: offer.title || offer.name,
						code: offer.name,
						offer,
						source: "offline",
						applied: true,
						rules: [offer.name],
						min_qty: offer.min_qty,
						max_qty: offer.max_qty,
						min_amt: offer.min_amt,
						max_amt: offer.max_amt,
					})

					newlyAppliedOffers.push(offer.title || offer.name)
				}
			}

			// Rebuild cache after bulk changes
			if (newlyAppliedOffers.length > 0) {
				rebuildIncrementalCache()
				showSuccess(__('Offline: {0} applied', [newlyAppliedOffers.join(', ')]))
			}
		} catch (error) {
			console.error("Error applying offers offline:", error)
		}
	}

	/**
	 * Apply price discount (percentage or amount) to eligible items offline
	 * @param {Object} offer - The offer to apply
	 * @param {Array} eligibleItems - Items eligible for the discount
	 * @returns {boolean} True if discount was applied
	 */
	function applyOfflinePriceDiscount(offer, eligibleItems) {
		const discountType = offer.discount_type || offer.rate_or_discount
		const discountPercentage = Number.parseFloat(offer.discount_percentage) || 0
		const discountAmount = Number.parseFloat(offer.discount_amount) || 0
		const rate = Number.parseFloat(offer.rate) || 0

		let applied = false

		for (const item of eligibleItems) {
			// Only apply if no existing pricing rule
			if (item.pricing_rules && item.pricing_rules.length > 0) continue

			if (discountType === 'Discount Percentage' && discountPercentage > 0) {
				item.discount_percentage = discountPercentage
				item.pricing_rules = [offer.name]
				recalculateItem(item)
				applied = true
			} else if (discountType === 'Discount Amount' && discountAmount > 0) {
				// Apply fixed discount amount
				item.discount_amount = discountAmount
				item.pricing_rules = [offer.name]
				recalculateItem(item)
				applied = true
			} else if (discountType === 'Rate' && rate > 0) {
				// Apply fixed rate (override price)
				item.rate = rate
				item.pricing_rules = [offer.name]
				recalculateItem(item)
				applied = true
			}
		}

		return applied
	}

	/**
	 * Apply free item (product discount) offer offline
	 * Handles: same_item (free item = purchased item) or specific free_item
	 *
	 * Recursive logic:
	 * - recurse_for: Give free item for every N quantity
	 * - apply_recursion_over: Qty for which recursion isn't applicable
	 * - Example: recurse_for=2, apply_recursion_over=0, free_qty=1
	 *   -> For 6 items: (6-0)/2 * 1 = 3 free items
	 *
	 * @param {Object} offer - The offer to apply
	 * @param {Array} eligibleItems - Items eligible for the free item
	 * @returns {boolean} True if free item was applied
	 */
	function applyOfflineFreeItem(offer, eligibleItems) {
		const freeQty = Number.parseFloat(offer.free_qty) || 0
		const sameItem = offer.same_item === 1
		const isRecursive = offer.is_recursive === 1
		const recurseFor = Number.parseFloat(offer.recurse_for) || 0
		const applyRecursionOver = Number.parseFloat(offer.apply_recursion_over) || 0
		const freeItemCode = offer.free_item

		if (freeQty <= 0) return false

		let applied = false

		if (sameItem) {
			// Free item is the same as the purchased item
			// E.g., "Buy 2 Get 1 Free" - the free item is the same item
			for (const item of eligibleItems) {
				let freeItemsToGive = freeQty

				if (isRecursive && recurseFor > 0) {
					// Recursive: for every recurseFor quantity, give freeQty free
					// Formula: floor((qty - apply_recursion_over) / recurse_for) * free_qty
					// E.g., Buy 2 Get 1 Free: recurse_for=2, free_qty=1
					//   For 6 items: floor((6-0)/2) * 1 = 3 free items
					const effectiveQty = Math.max(0, item.quantity - applyRecursionOver)
					const multiplier = Math.floor(effectiveQty / recurseFor)
					freeItemsToGive = multiplier * freeQty
				} else if (!isRecursive && offer.min_qty > 0) {
					// Non-recursive: just check if min_qty is met, give freeQty once
					// E.g., Buy 2 Get 1 Free (non-recursive): for 6 items, still give 1 free
					if (item.quantity >= offer.min_qty) {
						freeItemsToGive = freeQty
					} else {
						freeItemsToGive = 0
					}
				}

				if (freeItemsToGive > 0 && (!item.free_qty || item.free_qty === 0)) {
					item.free_qty = freeItemsToGive
					item.pricing_rules = item.pricing_rules || []
					if (!item.pricing_rules.includes(offer.name)) {
						item.pricing_rules.push(offer.name)
					}
					applied = true
				}
			}
		} else if (freeItemCode) {
			// Free item is a specific different item
			// Find if the free item is already in the cart
			const freeItemInCart = invoiceItems.value.find(
				item => item.item_code === freeItemCode
			)

			if (freeItemInCart) {
				// Calculate free qty (same recursive logic applies)
				let freeItemsToGive = freeQty

				if (isRecursive && recurseFor > 0) {
					// Calculate based on total eligible quantity
					const totalEligibleQty = eligibleItems.reduce(
						(sum, item) => sum + (item.quantity || 0), 0
					)
					const effectiveQty = Math.max(0, totalEligibleQty - applyRecursionOver)
					const multiplier = Math.floor(effectiveQty / recurseFor)
					freeItemsToGive = multiplier * freeQty
				}

				// Mark existing cart item as having free quantity
				if (freeItemsToGive > 0 && (!freeItemInCart.free_qty || freeItemInCart.free_qty === 0)) {
					freeItemInCart.free_qty = freeItemsToGive
					freeItemInCart.pricing_rules = freeItemInCart.pricing_rules || []
					if (!freeItemInCart.pricing_rules.includes(offer.name)) {
						freeItemInCart.pricing_rules.push(offer.name)
					}
					applied = true
				}
			}
			// Note: We don't add new items to cart offline - that would require
			// fetching item details. The free item will be added when back online.
		}

		return applied
	}

	/**
	 * Builds cart snapshot for offer validation
	 */
	function buildCartSnapshot() {
		const items = invoiceItems.value
		const totalQty = items.reduce((sum, item) => sum + (item.quantity || 0), 0)
		const itemCodes = items.map(item => item.item_code)
		const itemGroups = items.map(item => item.item_group).filter(Boolean)
		const brands = items.map(item => item.brand).filter(Boolean)

		// Build quantity maps for accurate offer validation
		// itemQuantities: { item_code: total_qty } - quantity per item code
		const itemQuantities = {}
		// itemGroupQuantities: { item_group: total_qty } - quantity per item group
		const itemGroupQuantities = {}
		// brandQuantities: { brand: total_qty } - quantity per brand
		const brandQuantities = {}

		for (const item of items) {
			const qty = item.quantity || 0

			// Aggregate by item code
			if (item.item_code) {
				itemQuantities[item.item_code] = (itemQuantities[item.item_code] || 0) + qty
			}

			// Aggregate by item group
			if (item.item_group) {
				itemGroupQuantities[item.item_group] = (itemGroupQuantities[item.item_group] || 0) + qty
			}

			// Aggregate by brand
			if (item.brand) {
				brandQuantities[item.brand] = (brandQuantities[item.brand] || 0) + qty
			}
		}

		return {
			subtotal: subtotal.value,
			itemCount: totalQty,
			itemCodes: [...new Set(itemCodes)],
			itemGroups: [...new Set(itemGroups)],
			brands: [...new Set(brands)],
			// New: quantity maps for accurate min_qty/max_qty validation
			itemQuantities,
			itemGroupQuantities,
			brandQuantities
		}
	}

	/**
	 * Find a cart item by item_code and optionally by UOM
	 * @param {string} itemCode - Item code to find
	 * @param {string|null} uom - Optional UOM to match
	 * @returns {Object|undefined} Cart item or undefined
	 */
	function findCartItem(itemCode, uom = null) {
		return invoiceItems.value.find((item) =>
			item.item_code === itemCode && (!uom || item.uom === uom)
		)
	}

	/**
	 * Find an existing cart item with target UOM (for merge detection)
	 * @param {string} itemCode - Item code
	 * @param {string} targetUom - Target UOM to find
	 * @param {Object} excludeItem - Item to exclude from search
	 * @returns {Object|undefined} Existing item or undefined
	 */
	function findItemWithUom(itemCode, targetUom, excludeItem = null) {
		return invoiceItems.value.find((item) =>
			item.item_code === itemCode &&
			item.uom === targetUom &&
			item !== excludeItem
		)
	}

	/**
	 * Remove an item from the cart
	 * @param {Object} cartItem - Item to remove
	 */
	function removeCartItem(cartItem) {
		const index = invoiceItems.value.indexOf(cartItem)
		if (index > -1) {
			invoiceItems.value.splice(index, 1)
		}
	}

	/**
	 * Merge source item into target item
	 * @param {Object} sourceItem - Item to merge from (will be removed)
	 * @param {Object} targetItem - Item to merge into
	 * @param {number} quantity - Quantity to add to target
	 * @returns {number} New total quantity
	 */
	function mergeItems(sourceItem, targetItem, quantity) {
		targetItem.quantity += quantity
		recalculateItem(targetItem)
		removeCartItem(sourceItem)
		rebuildIncrementalCache()
		return targetItem.quantity
	}

	/**
	 * Fetch and apply UOM details from server
	 * @param {Object} cartItem - Cart item to update
	 * @param {string} newUom - New UOM
	 * @param {number} qty - Quantity for pricing
	 */
	async function applyUomChange(cartItem, newUom, qty) {
		const itemDetails = await getItemDetailsResource.submit({
			item_code: cartItem.item_code,
			pos_profile: posProfile.value,
			customer: customer.value?.name || customer.value,
			qty,
			uom: newUom,
		})

		const uomData = cartItem.item_uoms?.find((u) => u.uom === newUom)

		cartItem.uom = newUom
		cartItem.conversion_factor = uomData?.conversion_factor || itemDetails.conversion_factor || 1
		cartItem.rate = itemDetails.price_list_rate || itemDetails.rate
		cartItem.price_list_rate = itemDetails.price_list_rate
	}

	/**
	 * Change item UOM - merges if target UOM already exists
	 * @param {string} itemCode - Item code
	 * @param {string} newUom - New UOM to change to
	 * @param {string|null} currentUom - Current UOM (required when same item has multiple UOMs)
	 */
	async function changeItemUOM(itemCode, newUom, currentUom = null) {
		try {
			const cartItem = findCartItem(itemCode, currentUom)
			if (!cartItem || cartItem.uom === newUom) return

			// Check for existing item to merge with
			const existingItem = findItemWithUom(itemCode, newUom, cartItem)
			if (existingItem) {
				const totalQty = mergeItems(cartItem, existingItem, cartItem.quantity)
				showSuccess(__('Merged into {0} (Total: {1})', [newUom, totalQty]))
				return
			}

			// Apply UOM change
			await applyUomChange(cartItem, newUom, cartItem.quantity)
			recalculateItem(cartItem)
			rebuildIncrementalCache()
			showSuccess(__('Unit changed to {0}', [newUom]))
		} catch (error) {
			console.error("Error changing UOM:", error)
			showError(__("Failed to update UOM. Please try again."))
		}
	}

	/**
	 * Update item details - handles UOM changes with merging
	 * @param {string} itemCode - Item code
	 * @param {Object} updates - Updated details
	 * @param {string|null} currentUom - Current UOM (required when same item has multiple UOMs)
	 */
	async function updateItemDetails(itemCode, updates, currentUom = null) {
		try {
			const cartItem = findCartItem(itemCode, currentUom)
			if (!cartItem) {
				throw new Error("Item not found in cart")
			}

			// Handle UOM change with potential merge
			if (updates.uom && updates.uom !== cartItem.uom) {
				const existingItem = findItemWithUom(itemCode, updates.uom, cartItem)
				if (existingItem) {
					const qtyToMerge = updates.quantity ?? cartItem.quantity
					const totalQty = mergeItems(cartItem, existingItem, qtyToMerge)
					showSuccess(__('Merged into {0} (Total: {1})', [updates.uom, totalQty]))
					return true
				}

				// Apply UOM change with new rate
				try {
					await applyUomChange(cartItem, updates.uom, updates.quantity ?? cartItem.quantity)
				} catch {
					// Fallback: just change UOM without rate update
					cartItem.uom = updates.uom
				}
			}

			// Apply other updates
			if (updates.quantity !== undefined) cartItem.quantity = updates.quantity
			if (updates.warehouse !== undefined) cartItem.warehouse = updates.warehouse
			if (updates.discount_percentage !== undefined) cartItem.discount_percentage = updates.discount_percentage
			if (updates.discount_amount !== undefined) cartItem.discount_amount = updates.discount_amount
			if (updates.price_list_rate !== undefined) cartItem.price_list_rate = updates.price_list_rate
			if (updates.serial_no !== undefined) cartItem.serial_no = updates.serial_no

			recalculateItem(cartItem)
			rebuildIncrementalCache()
			showSuccess(__('{0} updated', [cartItem.item_name]))
			return true
		} catch (error) {
			console.error("Error updating item:", error)
			showError(parseError(error) || __("Failed to update item."))
			return false
		}
	}

	// Performance: Cache previous item codes hash to avoid unnecessary recalculations
	let previousItemCodesHash = ""
	let cachedItemCodes = []
	let cachedItemGroups = []
	let cachedBrands = []
	let cachedItemQuantities = {}
	let cachedItemGroupQuantities = {}
	let cachedBrandQuantities = {}

	function syncOfferSnapshot() {
		// Only sync if values are initialized
		if (subtotal.value !== undefined && invoiceItems.value) {
			// Create hash for item codes and quantities to detect actual changes
			const currentHash = invoiceItems.value
				.map((item) => `${item.item_code}:${item.quantity}`)
				.join(",")

			// Only recalculate expensive operations if items actually changed
			if (currentHash !== previousItemCodesHash) {
				cachedItemCodes = invoiceItems.value.map((item) => item.item_code)
				cachedItemGroups = [
					...new Set(
						invoiceItems.value.map((item) => item.item_group).filter(Boolean),
					),
				]
				cachedBrands = [
					...new Set(
						invoiceItems.value.map((item) => item.brand).filter(Boolean),
					),
				]

				// Build quantity maps for accurate offer validation
				cachedItemQuantities = {}
				cachedItemGroupQuantities = {}
				cachedBrandQuantities = {}

				for (const item of invoiceItems.value) {
					const qty = item.quantity || 0

					if (item.item_code) {
						cachedItemQuantities[item.item_code] = (cachedItemQuantities[item.item_code] || 0) + qty
					}
					if (item.item_group) {
						cachedItemGroupQuantities[item.item_group] = (cachedItemGroupQuantities[item.item_group] || 0) + qty
					}
					if (item.brand) {
						cachedBrandQuantities[item.brand] = (cachedBrandQuantities[item.brand] || 0) + qty
					}
				}

				previousItemCodesHash = currentHash
			}

			// Calculate total quantity (sum of all item quantities, not line count)
			const totalQty = invoiceItems.value.reduce((sum, item) => {
				return sum + (item.quantity || 0)
			}, 0)

			offersStore.updateCartSnapshot({
				subtotal: subtotal.value,
				itemCount: totalQty, // Total quantity, not number of line items
				itemCodes: cachedItemCodes,
				itemGroups: cachedItemGroups,
				brands: cachedBrands,
				itemQuantities: cachedItemQuantities,
				itemGroupQuantities: cachedItemGroupQuantities,
				brandQuantities: cachedBrandQuantities,
			})
		}
	}

	/**
	 * Core offer processing function that validates and auto-applies offers.
	 * Runs through the queue to ensure sequential execution.
	 * Uses offline mode when network is unavailable.
	 * @param {AbortSignal} signal - Abort signal for cancellation
	 * @param {number} generation - Cart generation when this was triggered
	 * @param {boolean} force - If true, process even if cart hash matches
	 */
	async function processOffersInternal(signal = null, generation = 0, force = false) {
		// CRITICAL: Always reset suppression flag FIRST, before any early returns
		// This ensures the flag never gets stuck in a true state
		suppressOfferReapply.value = false

		// Check cancellation early
		if (signal?.aborted) return

		// Check if this operation is stale (cart changed since this was queued)
		if (generation > 0 && generation < cartGeneration) {
			return // Skip stale operation
		}

		// Only process offers if we have a POS profile
		// posProfile.value is the profile NAME (a string), not an object
		if (!posProfile.value) {
			return
		}

		// Ensure offers are fetched before processing
		// This is critical for mobile view where InvoiceCart may not be mounted yet
		// IMPORTANT: This must happen BEFORE hash check, because if offers weren't
		// fetched on previous runs, we need to re-process even if cart hash matches
		const wasFetched = offersStore.hasFetched
		// posProfile.value is the profile name string directly
		const profileName = posProfile.value
		await offersStore.ensureOffersFetched(profileName)

		// Check cancellation after fetch
		if (signal?.aborted) return

		// Generate current cart hash
		const currentHash = generateCartHash()

		// Skip if cart hasn't changed since last successful processing (unless forced)
		// Also force re-processing if offers were just fetched for the first time
		const justFetched = !wasFetched && offersStore.hasFetched
		if (!force && !justFetched && currentHash === offerProcessingState.value.lastCartHash) {
			return
		}

		// Update offer snapshot for eligibility checking
		syncOfferSnapshot()

		// === OFFLINE MODE ===
		// When offline, use cached offers and apply discounts client-side
		if (offlineState.isOffline) {
			applyOffersOffline()
			offerProcessingState.value.lastCartHash = generateCartHash()
			offerProcessingState.value.lastProcessedAt = Date.now()
			return
		}

		// === ONLINE MODE ===
		// Get current profile from posProfile
		const currentProfile = {
			customer: customer.value?.name || customer.value,
			company: posProfile.value.company,
			selling_price_list: posProfile.value.selling_price_list,
			currency: posProfile.value.currency,
		}

		// Validate and auto-remove invalid offers (if any are applied)
		if (appliedOffers.value.length > 0) {
			await reapplyOffer(currentProfile, signal)
		}

		// Check cancellation before auto-apply
		if (signal?.aborted) return

		// Check again if stale after reapply
		if (generation > 0 && generation < cartGeneration) {
			return
		}

		// Auto-apply eligible offers (always check for new eligible offers)
		await autoApplyEligibleOffers(currentProfile, signal)

		// Update last processed hash on success
		offerProcessingState.value.lastCartHash = generateCartHash()
		offerProcessingState.value.lastProcessedAt = Date.now()
		offerProcessingState.value.retryCount = 0
	}

	/**
	 * Triggers offer processing with proper state management.
	 * @param {boolean} force - If true, bypass hash check and force processing
	 */
	function triggerOfferProcessing(force = false) {
		// Increment generation to invalidate any in-flight operations
		const currentGen = ++cartGeneration

		// Enqueue the processing task - queue handles concurrency
		offerQueue.enqueue(async (signal) => {
			try {
				offerProcessingState.value.isProcessing = true
				offerProcessingState.value.isAutoProcessing = true
				offerProcessingState.value.error = null

				await processOffersInternal(signal, currentGen, force)
			} catch (error) {
				if (!signal?.aborted) {
					console.error("Error in offer processing:", error)
					offerProcessingState.value.error = error.message
					offerProcessingState.value.retryCount++

					// Auto-retry on failure (max 3 times)
					if (offerProcessingState.value.retryCount < 3) {
						setTimeout(() => {
							triggerOfferProcessing(true)
						}, 500 * offerProcessingState.value.retryCount)
					}
				}
			} finally {
				offerProcessingState.value.isProcessing = false
				offerProcessingState.value.isAutoProcessing = false
			}
		})
	}

	/**
	 * Force refresh offers - clears state and reprocesses from scratch.
	 * Call this when you suspect offers are out of sync.
	 */
	function forceRefreshOffers() {
		// Cancel any pending operations
		debouncedProcessOffers.cancel()
		offerQueue.cancel()

		// Clear the hash to force reprocessing
		offerProcessingState.value.lastCartHash = ''
		offerProcessingState.value.error = null
		offerProcessingState.value.retryCount = 0

		// Reset suppression
		suppressOfferReapply.value = false

		// Trigger immediate processing
		triggerOfferProcessing(true)
	}

	/**
	 * Calculate dynamic debounce delay based on cart size.
	 * Small carts (1-3 items): 100ms - fast response
	 * Medium carts (4-10 items): 200ms - balanced
	 * Large carts (11+ items): 300ms - reduce API load
	 */
	function getDynamicDebounceDelay() {
		const itemCount = invoiceItems.value.length
		if (itemCount <= 3) return 100
		if (itemCount <= 10) return 200
		return 300
	}

	/**
	 * Debounced offer processing with dynamic delay based on cart size.
	 * Prevents race conditions while staying responsive for small carts.
	 */
	let debounceTimeoutId = null
	function debouncedProcessOffers() {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId)
		}
		debounceTimeoutId = setTimeout(() => {
			debounceTimeoutId = null
			triggerOfferProcessing(false)
		}, getDynamicDebounceDelay())
	}

	// Add cancel and flush methods for compatibility
	debouncedProcessOffers.cancel = () => {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId)
			debounceTimeoutId = null
		}
	}

	debouncedProcessOffers.flush = () => {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId)
			debounceTimeoutId = null
			triggerOfferProcessing(false)
		}
	}

	// Watch for ANY cart changes that might affect offer eligibility
	// This includes: items, quantities, customer, subtotal, etc.
	watch(
		[
			// Watch item count (additions/removals)
			() => invoiceItems.value.length,
			// Watch item details (quantity, code, uom changes)
			() => invoiceItems.value.map(item =>
				`${item.item_code}:${item.quantity}:${item.uom || ''}:${item.discount_percentage || 0}`
			).join(','),
			// Watch subtotal changes
			subtotal,
			// Watch customer changes (some offers are customer-specific)
			() => customer.value?.name || customer.value,
		],
		(_newVals, oldVals) => {
			// Skip if this is initial render with empty cart
			if (!oldVals && invoiceItems.value.length === 0) {
				return
			}

			// Use debounced processing to prevent race conditions
			// This batches rapid cart changes and ensures only one offer
			// processing operation runs at a time
			debouncedProcessOffers()
		},
		{ immediate: true, flush: "post" },
	)

	// Additional watcher for applied offers changes (to handle removal edge cases)
	watch(
		() => appliedOffers.value.length,
		(newLen, oldLen) => {
			// If offers were removed externally, sync the snapshot
			if (newLen < oldLen) {
				syncOfferSnapshot()
			}
		}
	)

	return {
		// State
		invoiceItems,
		customer,
		subtotal,
		totalTax,
		totalDiscount,
		grandTotal,
		posProfile,
		posOpeningShift,
		payments,
		salesTeam,
		additionalDiscount,
		taxInclusive,
		pendingItem,
		pendingItemQty,
		appliedOffers,
		appliedCoupon,
		selectionMode,
		suppressOfferReapply,
		currentDraftId,
		offerProcessingState, // Offer processing state for UI feedback

		// Computed
		itemCount,
		isEmpty,
		hasCustomer,
		isProcessingOffers, // True when any offer operation is in progress
		isSubmitting, // True when invoice submission is in progress (mutex protected)

		// Actions
		addItem,
		removeItem,
		updateItemQuantity,
		clearCart,
		setCustomer,
		setDefaultCustomer,
		setPendingItem,
		clearPendingItem,
		loadTaxRules,
		setTaxInclusive,
		submitInvoice,
		applyDiscountToCart,
		removeDiscountFromCart,
		applyOffer,
		removeOffer,
		reapplyOffer,
		autoApplyEligibleOffers,
		changeItemUOM,
		updateItemDetails,
		getItemDetailsResource,
		recalculateItem,
		rebuildIncrementalCache,
		applyOffersResource,
		buildOfferEvaluationPayload,
		formatItemsForSubmission,

		// Sales Order feature
		targetDoctype,
		setTargetDoctype,
		createSalesOrder,
		deliveryDate,
		setDeliveryDate,

		// Utilities
		cancelPendingOfferProcessing: () => {
			debouncedProcessOffers.cancel()
			offerQueue.cancel()
		},
		forceRefreshOffers, // Force reprocess offers from scratch
	}
})
