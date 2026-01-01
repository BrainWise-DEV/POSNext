import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { call } from "@/utils/apiWrapper"
import { isOffline } from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"

const defaultSnapshot = () => ({
	subtotal: 0,
	itemCount: 0,
	itemCodes: [],
	itemGroups: [],
	brands: [],
	// Quantity maps for accurate min_qty/max_qty validation
	itemQuantities: {},      // { item_code: qty }
	itemGroupQuantities: {}, // { item_group: qty }
	brandQuantities: {},     // { brand: qty }
})

function getDiscountSortValue(offer) {
	const percentage = Number.parseFloat(offer?.discount_percentage) || 0
	if (percentage) {
		return percentage
	}

	return Number.parseFloat(offer?.discount_amount) || 0
}

export const usePOSOffersStore = defineStore("posOffers", () => {
	const availableOffers = ref([])
	const cartSnapshot = ref(defaultSnapshot())
	const hasFetched = ref(false)

	function updateCartSnapshot(snapshot = {}) {
		const subtotal = Number.parseFloat(snapshot.subtotal) || 0
		const itemCount = Number.isFinite(snapshot.itemCount)
			? snapshot.itemCount
			: 0
		const itemCodes = Array.isArray(snapshot.itemCodes)
			? snapshot.itemCodes
			: []
		const itemGroups = Array.isArray(snapshot.itemGroups)
			? snapshot.itemGroups
			: []
		const brands = Array.isArray(snapshot.brands) ? snapshot.brands : []

		// Quantity maps for accurate offer validation
		const itemQuantities = snapshot.itemQuantities && typeof snapshot.itemQuantities === 'object'
			? snapshot.itemQuantities
			: {}
		const itemGroupQuantities = snapshot.itemGroupQuantities && typeof snapshot.itemGroupQuantities === 'object'
			? snapshot.itemGroupQuantities
			: {}
		const brandQuantities = snapshot.brandQuantities && typeof snapshot.brandQuantities === 'object'
			? snapshot.brandQuantities
			: {}

		cartSnapshot.value = {
			subtotal,
			itemCount,
			itemCodes,
			itemGroups,
			brands,
			itemQuantities,
			itemGroupQuantities,
			brandQuantities,
		}
	}

	function resetCartSnapshot() {
		cartSnapshot.value = defaultSnapshot()
	}

	function setAvailableOffers(offers = []) {
		if (!Array.isArray(offers)) {
			availableOffers.value = []
		} else {
			availableOffers.value = offers
		}
		hasFetched.value = true
	}

	function clearOffers() {
		availableOffers.value = []
		hasFetched.value = false
	}

	/**
	 * Calculates the total quantity of eligible items in cart for an offer
	 * @param {Object} offer - The offer to check
	 * @returns {number} Total quantity of eligible items
	 */
	function getEligibleItemQuantity(offer) {
		const itemQuantities = cartSnapshot.value.itemQuantities || {}
		const itemGroupQuantities = cartSnapshot.value.itemGroupQuantities || {}
		const brandQuantities = cartSnapshot.value.brandQuantities || {}

		if (offer?.apply_on === "Item Code") {
			const eligibleItems = offer.eligible_items || []
			if (eligibleItems.length > 0) {
				// Sum quantities of all eligible items in cart
				return eligibleItems.reduce((sum, itemCode) => {
					return sum + (itemQuantities[itemCode] || 0)
				}, 0)
			}
		} else if (offer?.apply_on === "Item Group") {
			const eligibleGroups = offer.eligible_item_groups || []
			if (eligibleGroups.length > 0) {
				// Sum quantities of all items in eligible groups
				return eligibleGroups.reduce((sum, group) => {
					return sum + (itemGroupQuantities[group] || 0)
				}, 0)
			}
		} else if (offer?.apply_on === "Brand") {
			const eligibleBrands = offer.eligible_brands || []
			if (eligibleBrands.length > 0) {
				// Sum quantities of all items from eligible brands
				return eligibleBrands.reduce((sum, brand) => {
					return sum + (brandQuantities[brand] || 0)
				}, 0)
			}
		}

		// For 'Transaction' offers or offers without specific item criteria,
		// use total cart quantity
		return cartSnapshot.value.itemCount || 0
	}

	/**
	 * Checks if an offer is eligible based on current cart state
	 * @param {Object} offer - The offer to check
	 * @returns {Object} {eligible: boolean, reason: string|null}
	 */
	function checkOfferEligibility(offer) {
		const subtotal = cartSnapshot.value.subtotal || 0
		const itemCount = cartSnapshot.value.itemCount || 0
		const cartItemCodes = cartSnapshot.value.itemCodes || []
		const cartItemGroups = cartSnapshot.value.itemGroups || []
		const cartBrands = cartSnapshot.value.brands || []

		// Check if cart is empty
		if (itemCount === 0) {
			return {
				eligible: false,
				reason: "Cart is empty",
			}
		}

		// Check item eligibility based on apply_on FIRST
		// This determines which items are eligible for the offer
		let eligibleItemQty = itemCount // Default to total cart qty for Transaction offers

		if (offer?.apply_on === "Item Code") {
			const eligibleItems = offer.eligible_items || []
			if (eligibleItems.length > 0) {
				const hasEligibleItem = eligibleItems.some((item) =>
					cartItemCodes.includes(item),
				)
				if (!hasEligibleItem) {
					return {
						eligible: false,
						reason: __("Cart does not contain eligible items for this offer"),
					}
				}
				// Calculate quantity of eligible items only
				eligibleItemQty = getEligibleItemQuantity(offer)
			}
		} else if (offer?.apply_on === "Item Group") {
			const eligibleGroups = offer.eligible_item_groups || []
			if (eligibleGroups.length > 0) {
				const hasEligibleGroup = eligibleGroups.some((group) =>
					cartItemGroups.includes(group),
				)
				if (!hasEligibleGroup) {
					return {
						eligible: false,
						reason: __("Cart does not contain items from eligible groups"),
					}
				}
				// Calculate quantity of items in eligible groups only
				eligibleItemQty = getEligibleItemQuantity(offer)
			}
		} else if (offer?.apply_on === "Brand") {
			const eligibleBrands = offer.eligible_brands || []
			if (eligibleBrands.length > 0) {
				const hasEligibleBrand = eligibleBrands.some((brand) =>
					cartBrands.includes(brand),
				)
				if (!hasEligibleBrand) {
					return {
						eligible: false,
						reason: __("Cart does not contain items from eligible brands"),
					}
				}
				// Calculate quantity of items from eligible brands only
				eligibleItemQty = getEligibleItemQuantity(offer)
			}
		}
		// If apply_on is 'Transaction', eligibleItemQty remains as total cart qty

		// Check minimum quantity against ELIGIBLE items quantity
		// (e.g., "Buy 2 of Item A Get 1 Free" requires 2 of Item A, not 2 total items)
		if (offer?.min_qty && eligibleItemQty < offer.min_qty) {
			return {
				eligible: false,
				reason: __('At least {0} eligible items required', [offer.min_qty]),
			}
		}

		// Check maximum quantity against ELIGIBLE items quantity
		if (offer?.max_qty && eligibleItemQty > offer.max_qty) {
			return {
				eligible: false,
				reason: __('Maximum {0} eligible items allowed for this offer', [offer.max_qty]),
			}
		}

		// Check minimum amount (still uses total subtotal)
		if (offer?.min_amt && subtotal < offer.min_amt) {
			return {
				eligible: false,
				reason: __('Minimum cart value of {0} required', [offer.min_amt]),
			}
		}

		// Check maximum amount (still uses total subtotal)
		if (offer?.max_amt && subtotal > offer.max_amt) {
			return {
				eligible: false,
				reason: __('Maximum cart value exceeded ({0})', [offer.max_amt]),
			}
		}

		return { eligible: true, reason: null }
	}

	const allEligibleOffers = computed(() => {
		return availableOffers.value.filter((offer) => {
			if (offer?.coupon_based) {
				return false
			}

			const eligibility = checkOfferEligibility(offer)
			return eligibility.eligible
		})
	})

	const allEligibleOffersSorted = computed(() => {
		return [...allEligibleOffers.value].sort((a, b) => {
			return getDiscountSortValue(b) - getDiscountSortValue(a)
		})
	})

	const autoEligibleOffers = computed(() => {
		return availableOffers.value.filter((offer) => {
			if (!offer?.auto || offer?.coupon_based) {
				return false
			}

			const eligibility = checkOfferEligibility(offer)
			return eligibility.eligible
		})
	})

	const autoEligibleCount = computed(() => autoEligibleOffers.value.length)

	function getUnlockAmount(offer) {
		const subtotal = cartSnapshot.value.subtotal || 0
		if (offer?.min_amt && subtotal < offer.min_amt) {
			return offer.min_amt - subtotal
		}
		return 0
	}

	// Track if we're currently fetching to prevent duplicate requests
	let fetchPromise = null

	/**
	 * Ensures offers are fetched before offer processing.
	 * This is critical for mobile view where InvoiceCart (which loads offers)
	 * may not be mounted when items are first added to the cart.
	 *
	 * @param {string} posProfile - POS Profile name to fetch offers for
	 * @returns {Promise<boolean>} True if offers are available (fetched or cached)
	 */
	async function ensureOffersFetched(posProfile) {
		// If already fetched, return immediately
		if (hasFetched.value) {
			return true
		}

		// If already fetching, wait for the existing request
		if (fetchPromise) {
			return fetchPromise
		}

		// No profile means we can't fetch
		if (!posProfile) {
			return false
		}

		// Start fetching
		fetchPromise = (async () => {
			try {
				if (isOffline()) {
					// Load offers from cache when offline
					const cachedOffers = await offlineWorker.getCachedOffers(posProfile)
					if (cachedOffers && cachedOffers.length > 0) {
						setAvailableOffers(cachedOffers)
						return true
					}
					// No cached offers available offline
					hasFetched.value = true // Mark as fetched to prevent retries
					return false
				}

				// Online: fetch from API
				const response = await call("pos_next.api.offers.get_offers", {
					pos_profile: posProfile,
				})

				const offers = response?.message || response || []
				setAvailableOffers(offers)

				// Cache offers for offline use
				if (offers.length > 0) {
					offlineWorker.cacheOffers(offers, posProfile).catch(() => {
						// Silently ignore cache errors
					})
				}

				return true
			} catch (error) {
				console.error("Error fetching offers:", error)
				hasFetched.value = true // Mark as fetched to prevent infinite retries
				return false
			} finally {
				fetchPromise = null
			}
		})()

		return fetchPromise
	}

	return {
		// State
		availableOffers,
		cartSnapshot,
		hasFetched,

		// Computed
		allEligibleOffers,
		allEligibleOffersSorted,
		autoEligibleOffers,
		autoEligibleCount,

		// Actions
		updateCartSnapshot,
		resetCartSnapshot,
		setAvailableOffers,
		clearOffers,
		checkOfferEligibility,
		getUnlockAmount,
		ensureOffersFetched,
	}
})
