import { useInvoiceFiltersStore } from "@/stores/invoiceFilters"
import { computed } from "vue"

/**
 * Invoice Filters Composable
 *
 * Provides filtering logic for invoice lists
 * Works with the invoice filters store for state management
 *
 * @param {Array} invoices - Array of invoice objects to filter
 * @returns {Object} Filtered invoices and helper functions
 */
export function useInvoiceFilters(invoices) {
	const filtersStore = useInvoiceFiltersStore()

	/**
	 * Apply all active filters to the invoice list
	 */
	const filteredInvoices = computed(() => {
		if (!Array.isArray(invoices.value)) return []

		let result = [...invoices.value]

		// Apply search term filter
		if (filtersStore.searchTerm) {
			const search = filtersStore.searchTerm.toLowerCase()
			result = result.filter(
				(inv) =>
					inv.name?.toLowerCase().includes(search) ||
					inv.customer_name?.toLowerCase().includes(search) ||
					inv.customer?.toLowerCase().includes(search),
			)
		}

		// Apply date range filter
		if (filtersStore.dateFrom) {
			const fromDate = new Date(filtersStore.dateFrom)
			fromDate.setHours(0, 0, 0, 0)
			result = result.filter((inv) => {
				const invDate = new Date(inv.posting_date)
				invDate.setHours(0, 0, 0, 0)
				return invDate >= fromDate
			})
		}

		if (filtersStore.dateTo) {
			const toDate = new Date(filtersStore.dateTo)
			toDate.setHours(23, 59, 59, 999)
			result = result.filter((inv) => {
				const invDate = new Date(inv.posting_date)
				return invDate <= toDate
			})
		}

		// Apply customer filter
		if (filtersStore.customer) {
			result = result.filter(
				(inv) =>
					inv.customer === filtersStore.customer ||
					inv.customer_name === filtersStore.customer,
			)
		}

		// Apply status filter
		if (filtersStore.status) {
			result = result.filter((inv) => inv.status === filtersStore.status)
		}

		// Apply product filter
		if (filtersStore.product) {
			const productSearch = filtersStore.product.toLowerCase()
			result = result.filter((inv) => {
				if (!inv.items || !Array.isArray(inv.items)) return false
				return inv.items.some(
					(item) =>
						item.item_name?.toLowerCase().includes(productSearch) ||
						item.item_code?.toLowerCase().includes(productSearch),
				)
			})
		}

		return result
	})

	/**
	 * Get unique customers from invoices for dropdown
	 */
	const uniqueCustomers = computed(() => {
		if (!Array.isArray(invoices.value)) return []

		const customersMap = new Map()

		invoices.value.forEach((inv) => {
			if (inv.customer) {
				const customerName = inv.customer_name || inv.customer
				customersMap.set(inv.customer, customerName)
			}
		})

		return Array.from(customersMap.entries())
			.map(([value, label]) => ({ value, label }))
			.sort((a, b) => a.label.localeCompare(b.label))
	})

	/**
	 * Get unique payment statuses from invoices
	 */
	const uniqueStatuses = computed(() => {
		if (!Array.isArray(invoices.value)) return []

		const statuses = new Set()
		invoices.value.forEach((inv) => {
			if (inv.status) {
				statuses.add(inv.status)
			}
		})

		return Array.from(statuses).sort()
	})

	/**
	 * Get unique products from invoices for dropdown
	 */
	const uniqueProducts = computed(() => {
		if (!Array.isArray(invoices.value)) return []

		const productsMap = new Map()

		invoices.value.forEach((inv) => {
			if (inv.items && Array.isArray(inv.items)) {
				inv.items.forEach((item) => {
					if (item.item_code) {
						const productName = item.item_name || item.item_code
						// Use item_code as value for exact matching
						productsMap.set(item.item_code, {
							value: item.item_code,
							label: productName,
							subtitle: item.item_code !== productName ? item.item_code : null,
						})
					}
				})
			}
		})

		return Array.from(productsMap.values()).sort((a, b) =>
			a.label.localeCompare(b.label),
		)
	})

	/**
	 * Get customer name from value
	 */
	function getCustomerName(customerValue) {
		const customer = uniqueCustomers.value.find(
			(c) => c.value === customerValue,
		)
		return customer ? customer.label : customerValue
	}

	/**
	 * Check if invoice matches all active filters
	 * Useful for individual invoice checking
	 */
	function matchesFilters(invoice) {
		// Search term
		if (filtersStore.searchTerm) {
			const search = filtersStore.searchTerm.toLowerCase()
			const matchesSearch =
				invoice.name?.toLowerCase().includes(search) ||
				invoice.customer_name?.toLowerCase().includes(search) ||
				invoice.customer?.toLowerCase().includes(search)
			if (!matchesSearch) return false
		}

		// Date range
		if (filtersStore.dateFrom) {
			const fromDate = new Date(filtersStore.dateFrom)
			fromDate.setHours(0, 0, 0, 0)
			const invDate = new Date(invoice.posting_date)
			invDate.setHours(0, 0, 0, 0)
			if (invDate < fromDate) return false
		}

		if (filtersStore.dateTo) {
			const toDate = new Date(filtersStore.dateTo)
			toDate.setHours(23, 59, 59, 999)
			const invDate = new Date(invoice.posting_date)
			if (invDate > toDate) return false
		}

		// Customer
		if (filtersStore.customer) {
			if (
				invoice.customer !== filtersStore.customer &&
				invoice.customer_name !== filtersStore.customer
			) {
				return false
			}
		}

		// Status
		if (filtersStore.status) {
			if (invoice.status !== filtersStore.status) return false
		}

		// Product
		if (filtersStore.product) {
			if (!invoice.items || !Array.isArray(invoice.items)) return false
			const productSearch = filtersStore.product.toLowerCase()
			const hasProduct = invoice.items.some(
				(item) =>
					item.item_name?.toLowerCase().includes(productSearch) ||
					item.item_code?.toLowerCase().includes(productSearch),
			)
			if (!hasProduct) return false
		}

		return true
	}

	/**
	 * Get filter statistics
	 */
	const filterStats = computed(() => {
		return {
			total: invoices.value?.length || 0,
			filtered: filteredInvoices.value.length,
			percentage: invoices.value?.length
				? Math.round(
						(filteredInvoices.value.length / invoices.value.length) * 100,
					)
				: 0,
		}
	})

	return {
		// Filtered data
		filteredInvoices,
		uniqueCustomers,
		uniqueProducts,
		uniqueStatuses,
		filterStats,

		// Helper functions
		getCustomerName,
		matchesFilters,

		// Store access (for convenience)
		store: filtersStore,
	}
}

/**
 * Quick date filter presets
 * Exported for use in filter UI components
 */
export const DATE_PRESETS = [
	{ label: __("Today"), value: "today", action: "setToday" },
	{ label: __("Yesterday"), value: "yesterday", action: "setYesterday" },
	{ label: __("This Week"), value: "week", action: "setThisWeek" },
	{ label: __("This Month"), value: "month", action: "setThisMonth" },
	{ label: __("Last 7 Days"), value: "last7", action: "setLast7Days" },
	{ label: __("Last 30 Days"), value: "last30", action: "setLast30Days" },
]

/**
 * Payment status options
 */
export const PAYMENT_STATUS_OPTIONS = [
	{ label: __("All Status"), value: "" },
	{ label: __("Paid"), value: "Paid" },
	{ label: __("Unpaid"), value: "Unpaid" },
	{ label: __("Partly Paid"), value: "Partly Paid" },
	{ label: __("Overdue"), value: "Overdue" },
]
