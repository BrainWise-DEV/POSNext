/**
 * Sales Persons Composable
 * Handles sales person selection for payment dialog
 */

import { ref, computed } from "vue"
import { createResource } from "frappe-ui"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { logger } from "@/utils/logger"

const log = logger.create("useSalesPersons")

export function useSalesPersons(posProfile) {
	const settingsStore = usePOSSettingsStore()

	// State
	const salesPersons = ref([])
	const selectedSalesPersons = ref([])
	const salesPersonSearch = ref("")
	const loadingSalesPersons = ref(false)
	const salesPersonDropdownOpen = ref(false)

	// Resource
	const salesPersonsResource = createResource({
		url: "pos_next.api.pos_profile.get_sales_persons",
		makeParams() {
			return {
				pos_profile: posProfile.value,
			}
		},
		auto: false,
		onSuccess(data) {
			log.debug("Sales persons loaded:", data)
			salesPersons.value = data?.message || data || []
			loadingSalesPersons.value = false
		},
		onError(error) {
			log.error("Error loading sales persons:", error)
			salesPersons.value = []
			loadingSalesPersons.value = false
		},
	})

	// Computed: Available sales persons (exclude already selected, filter by search)
	const availableSalesPersons = computed(() => {
		const selectedIds = selectedSalesPersons.value.map((p) => p.sales_person)
		const searchLower = (salesPersonSearch.value || "").toLowerCase()

		return salesPersons.value
			.filter((person) => {
				// Exclude already selected
				if (selectedIds.includes(person.name)) {
					return false
				}
				// Filter by search term if provided
				if (searchLower) {
					const name = (person.sales_person_name || person.name || "").toLowerCase()
					return name.includes(searchLower)
				}
				return true
			})
			.slice(0, 10) // Limit to 10 results for performance
	})

	// Computed: Total allocation percentage
	const totalSalesAllocation = computed(() => {
		return selectedSalesPersons.value.reduce((sum, p) => sum + (p.allocated_percentage || 0), 0)
	})

	// Computed: Validation - sales person is required when enabled
	const isSalesPersonValid = computed(() => {
		// If sales persons feature is disabled, always valid
		if (!settingsStore.enableSalesPersons) {
			return true
		}
		// At least one sales person must be selected
		return selectedSalesPersons.value.length > 0
	})

	/**
	 * Load sales persons from server
	 */
	function loadSalesPersons() {
		if (!posProfile.value) return

		if (settingsStore.enableSalesPersons && salesPersons.value.length === 0) {
			loadingSalesPersons.value = true
			salesPersonsResource.fetch()
		}
	}

	/**
	 * Add a sales person to the selection
	 * @param {Object} person - Sales person to add
	 */
	function addSalesPerson(person) {
		// For Single mode, replace the existing selection with 100%
		if (settingsStore.isSingleSalesPerson) {
			selectedSalesPersons.value = [
				{
					sales_person: person.name,
					sales_person_name: person.sales_person_name || person.name,
					allocated_percentage: 100,
					commission_rate: person.commission_rate,
				},
			]
			// Close dropdown after single selection
			salesPersonSearch.value = ""
			salesPersonDropdownOpen.value = false
		} else {
			// For Multiple mode, add to the list and redistribute evenly
			selectedSalesPersons.value.push({
				sales_person: person.name,
				sales_person_name: person.sales_person_name || person.name,
				allocated_percentage: 0, // Will be recalculated
				commission_rate: person.commission_rate,
			})
			// Redistribute commission evenly among all selected
			redistributeCommission()
			// Keep dropdown open for multiple selection, just clear search
			salesPersonSearch.value = ""
		}
	}

	/**
	 * Remove a sales person from the selection
	 * @param {string} personName - Name of person to remove
	 */
	function removeSalesPerson(personName) {
		const index = selectedSalesPersons.value.findIndex((p) => p.sales_person === personName)
		if (index > -1) {
			selectedSalesPersons.value.splice(index, 1)
			// Redistribute commission among remaining
			if (selectedSalesPersons.value.length > 0) {
				redistributeCommission()
			}
		}
	}

	/**
	 * Clear all selected sales persons
	 */
	function clearSalesPersons() {
		selectedSalesPersons.value = []
		salesPersonSearch.value = ""
	}

	/**
	 * Redistribute commission evenly among all selected sales persons
	 */
	function redistributeCommission() {
		const count = selectedSalesPersons.value.length
		if (count === 0) return

		const evenShare = 100 / count
		selectedSalesPersons.value.forEach((person) => {
			person.allocated_percentage = evenShare
		})
	}

	/**
	 * Handle blur event for dropdown (with delay for click events)
	 */
	function handleSalesPersonBlur() {
		setTimeout(() => {
			salesPersonDropdownOpen.value = false
		}, 150)
	}

	/**
	 * Reset sales persons state
	 */
	function resetSalesPersons() {
		selectedSalesPersons.value = []
		salesPersonSearch.value = ""
		salesPersonDropdownOpen.value = false
	}

	return {
		// State
		salesPersons,
		selectedSalesPersons,
		salesPersonSearch,
		loadingSalesPersons,
		salesPersonDropdownOpen,

		// Computed
		availableSalesPersons,
		totalSalesAllocation,
		isSalesPersonValid,

		// Actions
		loadSalesPersons,
		addSalesPerson,
		removeSalesPerson,
		clearSalesPersons,
		handleSalesPersonBlur,
		resetSalesPersons,
	}
}
