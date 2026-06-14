import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { DEFAULT_LOCALE } from "@/utils/currency"

/**
 * Invoice Filters Store
 *
 * Manages invoice filtering state and logic for Invoice Management
 * Supports filtering by date range, customer, payment status, and products
 */
export const useInvoiceFiltersStore = defineStore("invoiceFilters", () => {
	// Filter state
	const dateFrom = ref("")
	const dateTo = ref("")
	const customer = ref("")
	const status = ref("")
	const product = ref("")
	const searchTerm = ref("")

	// UI state
	const showFilters = ref(false)
	const savedFilters = ref([])
	const currentFilterName = ref("")

	// Computed: Active filters count
	const activeFiltersCount = computed(() => {
		let count = 0
		if (dateFrom.value || dateTo.value) count++
		if (customer.value) count++
		if (status.value) count++
		if (product.value) count++
		return count
	})

	// Computed: Has any filters active
	const hasActiveFilters = computed(() => activeFiltersCount.value > 0)

	// Computed: Filter summary for display
	const filterSummary = computed(() => {
		const summary = []

		if (dateFrom.value || dateTo.value) {
			summary.push({
				type: "date",
				label: formatDateRangeLabel(),
				value: { from: dateFrom.value, to: dateTo.value },
			})
		}

		if (customer.value) {
			summary.push({
				type: "customer",
				label: customer.value,
				value: customer.value,
			})
		}

		if (status.value) {
			summary.push({
				type: "status",
				label: status.value,
				value: status.value,
			})
		}

		if (product.value) {
			summary.push({
				type: "product",
				label: product.value,
				value: product.value,
			})
		}

		return summary
	})

	// Actions: Quick date filters
	function setToday() {
		const today = new Date()
		dateFrom.value = formatDateForInput(today)
		dateTo.value = formatDateForInput(today)
	}

	function setYesterday() {
		const yesterday = new Date()
		yesterday.setDate(yesterday.getDate() - 1)
		dateFrom.value = formatDateForInput(yesterday)
		dateTo.value = formatDateForInput(yesterday)
	}

	function setThisWeek() {
		const today = new Date()
		const weekStart = new Date(today)
		weekStart.setDate(today.getDate() - today.getDay())
		dateFrom.value = formatDateForInput(weekStart)
		dateTo.value = formatDateForInput(today)
	}

	function setThisMonth() {
		const today = new Date()
		const monthStart = new Date(today.getFullYear(), today.getMonth(), 1)
		dateFrom.value = formatDateForInput(monthStart)
		dateTo.value = formatDateForInput(today)
	}

	function setLast7Days() {
		const today = new Date()
		const weekAgo = new Date(today)
		weekAgo.setDate(today.getDate() - 7)
		dateFrom.value = formatDateForInput(weekAgo)
		dateTo.value = formatDateForInput(today)
	}

	function setLast30Days() {
		const today = new Date()
		const monthAgo = new Date(today)
		monthAgo.setDate(today.getDate() - 30)
		dateFrom.value = formatDateForInput(monthAgo)
		dateTo.value = formatDateForInput(today)
	}

	function setDateRange(from, to) {
		dateFrom.value = from
		dateTo.value = to
	}

	// Actions: Clear filters
	function clearDateFilter() {
		dateFrom.value = ""
		dateTo.value = ""
	}

	function clearCustomerFilter() {
		customer.value = ""
	}

	function clearStatusFilter() {
		status.value = ""
	}

	function clearProductFilter() {
		product.value = ""
	}

	function clearSearchTerm() {
		searchTerm.value = ""
	}

	function clearAllFilters() {
		dateFrom.value = ""
		dateTo.value = ""
		customer.value = ""
		status.value = ""
		product.value = ""
		searchTerm.value = ""
	}

	function clearFilter(type) {
		switch (type) {
			case "date":
				clearDateFilter()
				break
			case "customer":
				clearCustomerFilter()
				break
			case "status":
				clearStatusFilter()
				break
			case "product":
				clearProductFilter()
				break
		}
	}

	// Actions: Save and load filter presets
	function saveCurrentFilters(name) {
		const filterPreset = {
			name,
			dateFrom: dateFrom.value,
			dateTo: dateTo.value,
			customer: customer.value,
			status: status.value,
			product: product.value,
			createdAt: new Date().toISOString(),
		}

		const existingIndex = savedFilters.value.findIndex((f) => f.name === name)
		if (existingIndex >= 0) {
			savedFilters.value[existingIndex] = filterPreset
		} else {
			savedFilters.value.push(filterPreset)
		}

		currentFilterName.value = name

		// Persist to localStorage
		localStorage.setItem(
			"pos_invoice_filters",
			JSON.stringify(savedFilters.value),
		)
	}

	function loadFilterPreset(name) {
		const preset = savedFilters.value.find((f) => f.name === name)
		if (preset) {
			dateFrom.value = preset.dateFrom
			dateTo.value = preset.dateTo
			customer.value = preset.customer
			status.value = preset.status
			product.value = preset.product
			currentFilterName.value = name
		}
	}

	function deleteFilterPreset(name) {
		savedFilters.value = savedFilters.value.filter((f) => f.name !== name)
		if (currentFilterName.value === name) {
			currentFilterName.value = ""
		}
		localStorage.setItem(
			"pos_invoice_filters",
			JSON.stringify(savedFilters.value),
		)
	}

	function loadSavedFiltersFromStorage() {
		try {
			const saved = localStorage.getItem("pos_invoice_filters")
			if (saved) {
				savedFilters.value = JSON.parse(saved)
			}
		} catch (error) {
			console.error("Failed to load saved filters:", error)
		}
	}

	// Helper functions
	function formatDateForInput(date) {
		const year = date.getFullYear()
		const month = String(date.getMonth() + 1).padStart(2, "0")
		const day = String(date.getDate()).padStart(2, "0")
		return `${year}-${month}-${day}`
	}

	function formatDateRangeLabel() {
		if (dateFrom.value && dateTo.value) {
			if (dateFrom.value === dateTo.value) {
				return formatDateDisplay(dateFrom.value)
			}
			return `${formatDateDisplay(dateFrom.value)} - ${formatDateDisplay(dateTo.value)}`
		}
		if (dateFrom.value) {
			return __('From {0}', [formatDateDisplay(dateFrom.value)])
		}
		if (dateTo.value) {
			return __('Until {0}', [formatDateDisplay(dateTo.value)])
		}
		return ""
	}

	function formatDateDisplay(dateString) {
		if (!dateString) return ""
		const date = new Date(dateString)
		return date.toLocaleDateString(DEFAULT_LOCALE, {
			month: "short",
			day: "numeric",
			year: "numeric",
		})
	}

	// Toggle filters visibility
	function toggleFilters() {
		showFilters.value = !showFilters.value
	}

	return {
		// State
		dateFrom,
		dateTo,
		customer,
		status,
		product,
		searchTerm,
		showFilters,
		savedFilters,
		currentFilterName,

		// Computed
		activeFiltersCount,
		hasActiveFilters,
		filterSummary,

		// Actions - Quick dates
		setToday,
		setYesterday,
		setThisWeek,
		setThisMonth,
		setLast7Days,
		setLast30Days,
		setDateRange,

		// Actions - Clear
		clearDateFilter,
		clearCustomerFilter,
		clearStatusFilter,
		clearProductFilter,
		clearSearchTerm,
		clearAllFilters,
		clearFilter,

		// Actions - Presets
		saveCurrentFilters,
		loadFilterPreset,
		deleteFilterPreset,
		loadSavedFiltersFromStorage,

		// Actions - UI
		toggleFilters,

		// Helpers
		formatDateRangeLabel,
		formatDateDisplay,
	}
})
