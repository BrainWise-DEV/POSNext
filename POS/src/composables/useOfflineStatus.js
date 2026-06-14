import { onMounted, onUnmounted, ref } from "vue"
import { offlineState } from "@/utils/offline/offlineState"

export function useOfflineStatus() {
	const isOffline = ref(offlineState.isOffline)
	let unsubscribe = null

	onMounted(() => {
		unsubscribe = offlineState.subscribe((state) => {
			isOffline.value = state.isOffline
		})
	})

	onUnmounted(() => {
		if (unsubscribe) {
			unsubscribe()
			unsubscribe = null
		}
	})

	return { isOffline }
}
