<template>
	<header class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
		<div class="flex items-center justify-between">
			<!-- Left: Logo and session info -->
			<div class="flex items-center gap-4">
				<div class="flex items-center gap-2">
					<FeatherIcon name="shopping-bag" class="w-6 h-6 text-blue-600 dark:text-blue-400" />
					<span class="text-lg font-semibold text-gray-900 dark:text-white">{{ __("Your Order") }}</span>
				</div>

				<!-- Session info -->
				<div v-if="displayStore.sessionInfo" class="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
					<span class="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">
						{{ displayStore.sessionInfo.pos_profile }}
					</span>
					<span v-if="displayStore.cartData.customer_name" class="flex items-center gap-1">
						<FeatherIcon name="user" class="w-4 h-4" />
						{{ displayStore.cartData.customer_name }}
					</span>
				</div>
			</div>

			<!-- Right: Connection status and actions -->
			<div class="flex items-center gap-4">
				<!-- Connection status -->
				<div class="flex items-center gap-2">
					<span
						:class="[
							'w-2 h-2 rounded-full',
							connectionStatusClass
						]"
					/>
					<span class="text-sm text-gray-600 dark:text-gray-400">{{ connectionStatusText }}</span>
				</div>

				<!-- Last update time -->
				<div v-if="displayStore.lastUpdateTime" class="text-xs text-gray-500">
					{{ __("Updated") }}: {{ formatTime(displayStore.lastUpdateTime) }}
				</div>

				<!-- Refresh button -->
				<button
					class="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
					:title="__('Refresh')"
					@click="displayStore.refreshCart()"
				>
					<FeatherIcon name="refresh-cw" class="w-5 h-5" />
				</button>

				<!-- Settings/Logout -->
				<div class="relative">
					<button
						class="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
						@click="showMenu = !showMenu"
					>
						<FeatherIcon name="more-vertical" class="w-5 h-5" />
					</button>

					<!-- Dropdown menu -->
					<transition
						enter-active-class="transition-all duration-150"
						leave-active-class="transition-all duration-150"
						enter-from-class="opacity-0 scale-95"
						leave-to-class="opacity-0 scale-95"
					>
						<div
							v-if="showMenu"
							class="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl z-50"
						>
							<!-- Actions section -->
							<div class="py-1">
								<button
									class="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
									@click="handleLogout"
								>
									<FeatherIcon name="log-out" class="w-4 h-4" />
									{{ __("Disconnect") }}
								</button>
							</div>
						</div>
					</transition>
				</div>
			</div>
		</div>
	</header>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { computed, ref, onMounted, onUnmounted } from "vue"
import { useCustomerDisplayStore } from "@/stores/customerDisplay"

const displayStore = useCustomerDisplayStore()

const showMenu = ref(false)

// Connection status styling
const connectionStatusClass = computed(() => {
	switch (displayStore.connectionStatus) {
		case "connected":
			return "bg-green-500"
		case "polling":
			return "bg-yellow-500 animate-pulse"
		case "error":
			return "bg-red-500"
		case "connecting":
			return "bg-blue-500 animate-pulse"
		default:
			return "bg-gray-500"
	}
})

const connectionStatusText = computed(() => {
	switch (displayStore.connectionStatus) {
		case "connected":
			return __("Connected")
		case "polling":
			return __("Polling")
		case "error":
			return __("Connection Error")
		case "connecting":
			return __("Connecting...")
		default:
			return __("Disconnected")
	}
})

// Format time
function formatTime(date) {
	if (!date) return ""
	return new Date(date).toLocaleTimeString("fr-FR", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	})
}

// Handle logout
function handleLogout() {
	showMenu.value = false
	displayStore.logout()
}

// Close menu on click outside
function handleClickOutside(event) {
	if (showMenu.value && !event.target.closest(".relative")) {
		showMenu.value = false
	}
}

onMounted(() => {
	document.addEventListener("click", handleClickOutside)
})

onUnmounted(() => {
	document.removeEventListener("click", handleClickOutside)
})
</script>
