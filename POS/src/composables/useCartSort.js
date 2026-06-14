import { ref, reactive, computed, watch } from "vue"

// ── Module-level constants (created once, shared across all instances) ───
const CART_SORT_OPTIONS = Object.freeze([
	{
		field: 'order',
		label: __('Addition Order'),
		icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'
	},
	{
		field: 'name',
		label: __('Name'),
		icon: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z'
	},
	{
		field: 'price',
		label: __('Price'),
		icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
	},
	{
		field: 'quantity',
		label: __('Quantity'),
		icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4'
	},
	{
		field: 'total',
		label: __('Total'),
		icon: 'M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z'
	},
])

const CART_SORT_ICONS = Object.freeze({
	ascending: 'M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12',
	descending: 'M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4',
	inactive: 'M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4'
})

// O(1) label lookup instead of .find() per call
const SORT_LABEL_MAP = Object.freeze(
	Object.fromEntries(CART_SORT_OPTIONS.map(o => [o.field, o.label]))
)

/**
 * Composable for cart item sorting.
 *
 * Owns all sort-related state, addition-order tracking, and the
 * sorted-items computed.  Extracted from InvoiceCart.vue.
 *
 * @param {() => Array} itemsGetter - Getter (or ref) that returns the raw cart
 *        items array.  Typically `() => props.items`.
 */
export function useCartSort(itemsGetter) {
	// Normalise getter once — avoid typeof check on every access
	const getItems = typeof itemsGetter === 'function'
		? itemsGetter
		: () => itemsGetter.value

	// ── State ────────────────────────────────────────────────────────────
	const cartSortBy = ref(null)
	const cartSortOrder = ref('asc')
	const showCartSortDropdown = ref(false)

	// ── Addition-order tracking ─────────────────────────────────────────
	const lastTouched = reactive(new Map())
	let touchSeq = 0
	const itemKey = (item) => `${item.item_code}\0${item.uom || ''}`

	// Cached previous snapshot avoids re-parsing the prev string every tick
	let prevSnapshot = new Map()

	watch(
		() => {
			// Build signature string — Vue compares by identity (cheap shallow watch)
			const items = getItems() || []
			return items.map(i => `${i.item_code}\0${i.uom || ''}:${i.quantity}`).join('|')
		},
		(cur) => {
			const newSnapshot = new Map()
			for (const entry of cur.split('|')) {
				if (!entry) continue
				const sep = entry.lastIndexOf(':')
				const key = entry.slice(0, sep)
				const qty = entry.slice(sep + 1)
				newSnapshot.set(key, qty)
				if (prevSnapshot.get(key) !== qty) {
					lastTouched.set(key, ++touchSeq)
				}
			}
			// Clean up removed items
			for (const key of prevSnapshot.keys()) {
				if (!newSnapshot.has(key)) lastTouched.delete(key)
			}
			prevSnapshot = newSnapshot
		},
		{ immediate: true }
	)

	// ── Computed ─────────────────────────────────────────────────────────
	const sortedItems = computed(() => {
		const items = getItems()

		const field = cartSortBy.value
		if (!field) return items

		const dir = cartSortOrder.value === 'asc' ? 1 : -1

		if (field === 'order') {
			return [...items].sort((a, b) => {
				const ta = lastTouched.get(itemKey(a)) || 0
				const tb = lastTouched.get(itemKey(b)) || 0
				return ta !== tb ? dir * (tb - ta) : 0
			})
		}

		// Capture comparator once — avoids reading the ref inside O(n log n) iterations
		let cmp
		switch (field) {
			case 'name':
				cmp = (a, b) => (a.item_name || '').localeCompare(b.item_name || '')
				break
			case 'price':
				cmp = (a, b) => (a.rate || 0) - (b.rate || 0)
				break
			case 'quantity':
				cmp = (a, b) => (a.quantity || 0) - (b.quantity || 0)
				break
			case 'total':
				cmp = (a, b) => {
					const aT = a.amount || (a.rate || 0) * (a.quantity || 0)
					const bT = b.amount || (b.rate || 0) * (b.quantity || 0)
					return aT - bT
				}
				break
			default:
				return items
		}
		return [...items].sort((a, b) => dir * cmp(a, b))
	})

	// ── Functions ────────────────────────────────────────────────────────
	function toggleCartSortDropdown() {
		showCartSortDropdown.value = !showCartSortDropdown.value
	}

	function handleCartSortToggle(field) {
		if (!field) {
			cartSortBy.value = null
			cartSortOrder.value = 'asc'
			showCartSortDropdown.value = false
			return
		}
		if (cartSortBy.value === field) {
			cartSortOrder.value = cartSortOrder.value === 'asc' ? 'desc' : 'asc'
		} else {
			cartSortBy.value = field
			cartSortOrder.value = 'asc'
		}
	}

	function getCartSortLabel() {
		return SORT_LABEL_MAP[cartSortBy.value] || cartSortBy.value
	}

	function getCartSortIconState(field) {
		if (cartSortBy.value !== field) return 'inactive'
		return cartSortOrder.value === 'asc' ? 'ascending' : 'descending'
	}

	return {
		// State
		cartSortBy,
		cartSortOrder,
		showCartSortDropdown,

		// Computed
		sortedItems,

		// Constants
		CART_SORT_OPTIONS,
		CART_SORT_ICONS,

		// Functions
		toggleCartSortDropdown,
		handleCartSortToggle,
		getCartSortLabel,
		getCartSortIconState,
	}
}
