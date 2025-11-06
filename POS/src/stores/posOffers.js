import { defineStore } from "pinia"
import { computed, ref } from "vue"

const defaultSnapshot = () => ({
	subtotal: 0,
	itemCount: 0,
	itemCodes: [],
	itemGroups: [],
	brands: [],
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

		cartSnapshot.value = {
			subtotal,
			itemCount,
			itemCodes,
			itemGroups,
			brands,
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

		// Check minimum quantity (e.g., "Buy 2 Get 1 Free" requires at least 2 items)
		if (offer?.min_qty && itemCount < offer.min_qty) {
			return {
				eligible: false,
				reason: `At least ${offer.min_qty} items required`,
			}
		}

		// Check minimum amount
		if (offer?.min_amt && subtotal < offer.min_amt) {
			return {
				eligible: false,
				reason: `Minimum cart value of ${offer.min_amt} required`,
			}
		}

		// Check maximum amount
		if (offer?.max_amt && subtotal > offer.max_amt) {
			return {
				eligible: false,
				reason: `Maximum cart value exceeded (${offer.max_amt})`,
			}
		}

		// Check item eligibility based on apply_on
		if (offer?.apply_on === "Item Code") {
			// Check if cart contains any of the eligible items
			const eligibleItems = offer.eligible_items || []
			if (eligibleItems.length > 0) {
				const hasEligibleItem = eligibleItems.some((item) =>
					cartItemCodes.includes(item),
				)
				if (!hasEligibleItem) {
					return {
						eligible: false,
						reason: "Cart does not contain eligible items for this offer",
					}
				}
			}
		} else if (offer?.apply_on === "Item Group") {
			// Check if cart contains items from any of the eligible groups
			const eligibleGroups = offer.eligible_item_groups || []
			if (eligibleGroups.length > 0) {
				const hasEligibleGroup = eligibleGroups.some((group) =>
					cartItemGroups.includes(group),
				)
				if (!hasEligibleGroup) {
					return {
						eligible: false,
						reason: "Cart does not contain items from eligible groups",
					}
				}
			}
		} else if (offer?.apply_on === "Brand") {
			// Check if cart contains items from any of the eligible brands
			const eligibleBrands = offer.eligible_brands || []
			if (eligibleBrands.length > 0) {
				const hasEligibleBrand = eligibleBrands.some((brand) =>
					cartBrands.includes(brand),
				)
				if (!hasEligibleBrand) {
					return {
						eligible: false,
						reason: "Cart does not contain items from eligible brands",
					}
				}
			}
		}
		// If apply_on is 'Transaction', it applies to entire cart (no item-specific check needed)

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
	}
})
