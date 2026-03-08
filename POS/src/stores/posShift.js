import { useShift, shiftState } from "@/composables/useShift"
import { DEFAULT_CURRENCY, DEFAULT_LOCALE } from "@/utils/currency"
import { defineStore } from "pinia"
import { computed, ref } from "vue"

export const usePOSShiftStore = defineStore("posShift", () => {
	// Use the existing shift composable
	const { currentProfile, currentShift, hasOpenShift, checkOpeningShift } =
		useShift()

	// Additional shift state
	const currentTime = ref("")
	const shiftDuration = ref("")
	const shiftTimerPaused = ref(false)

	// Computed
	const profileName = computed(() => currentProfile.value?.name)
	const profileCurrency = computed(
		() => currentProfile.value?.currency || DEFAULT_CURRENCY,
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

		// Freeze the counter when closing dialog is open
		if (shiftTimerPaused.value) return

		// Elapsed = initial elapsed (server_now - shift_start, computed at fetch time)
		//         + time since we received the data (local clock only)
		// This avoids timezone mismatch between server and browser.
		const { _initialElapsedMs, _receivedAt } = shiftState.value
		const diff = _initialElapsedMs + (Date.now() - (_receivedAt || Date.now()))
		if (diff < 0) {
			shiftDuration.value = ""
			return
		}

		const days = Math.floor(diff / (1000 * 60 * 60 * 24))
		const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
		const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
		const seconds = Math.floor((diff % (1000 * 60)) / 1000)

		if (days > 0) {
			const dayLabel = days === 1 ? __('Day') : __('Days')
			const hourLabel = hours === 1 ? __('Hour') : __('Hours')
			const minLabel = minutes === 1 ? __('Minute') : __('Minutes')
			shiftDuration.value = `${days} ${dayLabel} ${hours} ${hourLabel} ${minutes} ${minLabel}`
		} else {
			const hourLabel = hours === 1 ? __('Hour') : __('Hours')
			const minLabel = minutes === 1 ? __('Minute') : __('Minutes')
			const secLabel = seconds === 1 ? __('Second') : __('Seconds')
			shiftDuration.value = `${hours} ${hourLabel} ${minutes} ${minLabel} ${seconds} ${secLabel}`
		}
	}

	function updateCurrentTime() {
		const now = new Date()
		currentTime.value = now.toLocaleTimeString(DEFAULT_LOCALE, { hour12: false })
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
		shiftTimerPaused,

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
