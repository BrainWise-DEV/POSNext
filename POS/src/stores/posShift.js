import { useShift } from "@/composables/useShift"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

export const usePOSShiftStore = defineStore("posShift", () => {
	// Use the existing shift composable
	const { currentProfile, currentShift, hasOpenShift, checkOpeningShift } =
		useShift()

	// Additional shift state
	const currentTime = ref("")
	const shiftDuration = ref("")

	// Computed
	const profileName = computed(() => currentProfile.value?.name)
	const profileCurrency = computed(
		() => currentProfile.value?.currency || "USD",
	)
	const profileWarehouse = computed(() => currentProfile.value?.warehouse)
	const profileCompany = computed(() => currentProfile.value?.company)
	const profileCustomer = computed(() => currentProfile.value?.customer)
	const autoPrintEnabled = computed(
		() => currentProfile.value?.print_receipt_on_order_complete,
	)
	const writeOffAccount = computed(() => currentProfile.value?.write_off_account)
	const writeOffCostCenter = computed(() => currentProfile.value?.write_off_cost_center)
	const writeOffLimit = computed(() => currentProfile.value?.write_off_limit || 0)

	// Actions
	function updateShiftDuration() {
		if (!hasOpenShift.value || !currentShift.value?.period_start_date) {
			shiftDuration.value = ""
			return
		}

		const startTime = new Date(currentShift.value.period_start_date)
		const now = new Date()
		const diff = now - startTime

		const hours = Math.floor(diff / (1000 * 60 * 60))
		const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
		const seconds = Math.floor((diff % (1000 * 60)) / 1000)

		shiftDuration.value = `${hours} ${__('Hr')} ${minutes} ${__('Min')} ${seconds} ${__('Sec')}`
	}

	function updateCurrentTime() {
		const now = new Date()
		currentTime.value = now.toLocaleTimeString("en-US", { hour12: false })
	}

	function startTimers() {
		// Update both immediately
		updateCurrentTime()
		updateShiftDuration()

		// Then update every second
		const intervalId = setInterval(() => {
			updateCurrentTime()
			updateShiftDuration()
		}, 1000)

		return intervalId
	}

	async function checkShift() {
		await checkOpeningShift.fetch()
		return hasOpenShift.value
	}

	return {
		// State
		currentProfile,
		currentShift,
		hasOpenShift,
		currentTime,
		shiftDuration,

		// Computed
		profileName,
		profileCurrency,
		profileWarehouse,
		profileCompany,
		profileCustomer,
		autoPrintEnabled,
		writeOffAccount,
		writeOffCostCenter,
		writeOffLimit,

		// Actions
		updateShiftDuration,
		updateCurrentTime,
		startTimers,
		checkShift,
		checkOpeningShift,
	}
})
