<template>
	<div class="flex flex-col h-screen bg-gray-100 dark:bg-gray-900">
		<!-- Header -->
		<header class="bg-white dark:bg-gray-800 shadow-sm z-10 p-4 flex justify-between items-center">
			<div>
				<h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ __("Kitchen Display System") }}</h1>
				<p class="text-sm text-gray-500 dark:text-gray-400">{{ __("Active Orders") }}: {{ orders.length }}</p>
			</div>
			<div class="flex gap-2">
				<Button @click="loadOrders" icon="refresh-cw">
					{{ __("Refresh") }}
				</Button>
				<Button @click="$router.push('/')" variant="subtle">
					{{ __("Back to POS") }}
				</Button>
			</div>
		</header>

		<!-- Orders Grid -->
		<main class="flex-1 overflow-x-auto overflow-y-hidden p-6">
			<div v-if="loading" class="flex justify-center items-center h-full">
				<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 dark:border-white"></div>
			</div>

			<div v-else-if="orders.length === 0" class="flex flex-col justify-center items-center h-full text-gray-500">
				<svg class="w-16 h-16 mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"></path></svg>
				<h2 class="text-xl font-medium">{{ __("No Active Orders") }}</h2>
				<p>{{ __("Kitchen is clear.") }}</p>
			</div>

			<div v-else class="flex gap-4 h-full overflow-x-auto snap-x">
				<KDSOrderCard
					v-for="order in sortedOrders"
					:key="order.name"
					:order="order"
					@status-updated="loadOrders"
					class="snap-start"
				/>
			</div>
		</main>
	</div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from "vue"
import { Button } from "frappe-ui"
import KDSOrderCard from "@/components/invoices/KDSOrderCard.vue"
import { call } from "@/utils/apiWrapper"
import { useToast } from "@/composables/useToast"

const { showError } = useToast()
const orders = ref([])
const loading = ref(true)
let pollInterval = null

const sortedOrders = computed(() => {
	// Sort by creation time (oldest first)
	return [...orders.value].sort((a, b) => new Date(a.creation) - new Date(b.creation))
})

async function loadOrders() {
	try {
		const res = await call("pos_next.api.restaurant.get_kds_orders")

		if (res) {
			orders.value = res
		}
	} catch (error) {
		console.error("Failed to load KDS orders:", error)
		showError(__("Failed to load orders from server."))
	} finally {
		loading.value = false
	}
}

onMounted(() => {
	loadOrders()
	// Poll for new orders every 10 seconds
	pollInterval = setInterval(loadOrders, 10000)
})

onUnmounted(() => {
	if (pollInterval) {
		clearInterval(pollInterval)
	}
})
</script>

<style scoped>
/* Custom scrollbar for horizontal scrolling */
::-webkit-scrollbar {
	height: 12px;
}
::-webkit-scrollbar-track {
	background: rgba(0,0,0,0.05);
	border-radius: 6px;
}
::-webkit-scrollbar-thumb {
	background: rgba(0,0,0,0.2);
	border-radius: 6px;
}
::-webkit-scrollbar-thumb:hover {
	background: rgba(0,0,0,0.3);
}
.dark ::-webkit-scrollbar-track {
	background: rgba(255,255,255,0.05);
}
.dark ::-webkit-scrollbar-thumb {
	background: rgba(255,255,255,0.2);
}
.dark ::-webkit-scrollbar-thumb:hover {
	background: rgba(255,255,255,0.3);
}
</style>
