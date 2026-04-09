<template>
	<div class="customer-display min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-white">
		<!-- Not authenticated: Show auth modal -->
		<DisplayAuth v-if="!displayStore.isAuthenticated" />

		<!-- Authenticated but no active session -->
		<div
			v-else-if="!displayStore.posOpeningEntry"
			class="flex flex-col items-center justify-center min-h-screen p-8"
		>
			<div class="text-center space-y-6">
				<div class="text-6xl mb-4">
					<FeatherIcon name="monitor" class="w-24 h-24 mx-auto text-gray-400 dark:text-gray-500" />
				</div>
				<h1 class="text-3xl font-bold text-gray-900 dark:text-white">{{ __("Welcome") }}</h1>

				<!-- Profile selector -->
				<div class="max-w-md mx-auto space-y-4">
					<label class="block text-left text-gray-600 dark:text-gray-400">{{ __("Select POS Profile") }}</label>
					<select
						v-model="selectedProfile"
						class="w-full px-4 py-3 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						@change="handleProfileSelect"
					>
						<option value="" disabled>{{ __("Choose a POS profile...") }}</option>
						<option v-for="profile in displayStore.posProfiles" :key="profile.name" :value="profile.name">
							{{ profile.name }} ({{ profile.company }})
						</option>
					</select>

					<div v-if="displayStore.connectionError" class="mt-4 p-4 bg-red-100 dark:bg-red-900/50 rounded-lg">
						<p class="text-red-700 dark:text-red-300">{{ displayStore.connectionError }}</p>
					</div>

					<button
						class="mt-4 px-6 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-white rounded-lg transition-colors"
						@click="displayStore.logout()"
					>
						{{ __("Change API Key") }}
					</button>
				</div>
			</div>
		</div>

		<!-- Main display view -->
		<div v-else class="flex flex-col h-screen overflow-hidden">
			<!-- Header -->
			<DisplayHeader />

			<!-- Main content -->
			<div class="flex-1 flex overflow-hidden">
				<!-- Thank you overlay -->
				<transition
					enter-active-class="transition-opacity duration-300"
					leave-active-class="transition-opacity duration-300"
					enter-from-class="opacity-0"
					leave-to-class="opacity-0"
				>
					<div
						v-if="displayStore.showThankYou"
						class="fixed inset-0 z-50 flex items-center justify-center bg-green-600 text-white"
					>
						<div class="text-center space-y-8">
							<div class="text-8xl animate-bounce">
								<FeatherIcon name="check-circle" class="w-32 h-32 mx-auto" />
							</div>
							<h1 class="text-6xl font-bold">{{ __("Thank You!") }}</h1>
							<p class="text-3xl">{{ __("See you soon!") }}</p>
							<p v-if="displayStore.lastSaleAmount" class="text-4xl font-semibold mt-4">
								{{ formatCurrency(displayStore.lastSaleAmount) }}
							</p>
						</div>
					</div>
				</transition>

				<!-- Cart display -->
				<DisplayCart class="flex-1" />

				<!-- Customer creation sidebar -->
				<transition
					enter-active-class="transition-all duration-300"
					leave-active-class="transition-all duration-300"
					enter-from-class="opacity-0 translate-x-full"
					leave-to-class="opacity-0 translate-x-full"
				>
					<div v-if="showCreateCustomer" class="w-96 border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 z-40">
						<CreateCustomerModal
							:show-address="displayStore.displaySettings.showAddressFields"
							@close="showCreateCustomer = false"
							@created="handleCustomerCreated"
						/>
					</div>
				</transition>
			</div>

			<!-- Floating "Create Account" button (bottom right) -->
			<div v-if="displayStore.displaySettings.enableAccountCreation" class="fixed bottom-8 right-8 z-30">
				<button
					class="flex items-center gap-3 px-6 py-4 text-lg font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-full shadow-2xl transition-all hover:scale-105 active:scale-95"
					@click="showCreateCustomer = true"
				>
					<FeatherIcon name="user-plus" class="w-6 h-6" />
					<span>{{ __("Create Account") }}</span>
				</button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { onMounted, onUnmounted, reactive, ref } from "vue"
import { useCustomerDisplayStore } from "@/stores/customerDisplay"
import DisplayAuth from "@/components/customer-display/DisplayAuth.vue"
import DisplayHeader from "@/components/customer-display/DisplayHeader.vue"
import DisplayCart from "@/components/customer-display/DisplayCart.vue"
import CreateCustomerModal from "@/components/customer-display/CreateCustomerModal.vue"

const displayStore = useCustomerDisplayStore()

const selectedProfile = ref("")
const showCreateCustomer = ref(false)

// Format currency
function formatCurrency(amount) {
	const rawCurrency = displayStore.cartData?.currency

	const currency =
		typeof rawCurrency === "string"
			? rawCurrency
			: rawCurrency?.name ||
			  rawCurrency?.currency ||
			  rawCurrency?.code ||
			  null

	const numericAmount = Number(amount || 0)

	if (!currency) {
		return numericAmount.toFixed(2)
	}

	try {
		return new Intl.NumberFormat(undefined, {
			style: "currency",
			currency,
		}).format(numericAmount)
	} catch {
		return `${currency} ${numericAmount.toFixed(2)}`
	}
}

// Handle profile selection
async function handleProfileSelect() {
	if (selectedProfile.value) {
		await displayStore.selectPosProfile(selectedProfile.value)
	}
}

// Handle customer created
function handleCustomerCreated(customer) {
	showCreateCustomer.value = false
	// Immediately update cart with new customer (don't wait for realtime event)
	if (customer) {
		displayStore.cartData.customer = customer.name
		displayStore.cartData.customer_name = customer.customer_name
	}
}

// Try to restore session on mount
onMounted(async () => {
	await displayStore.tryRestoreSession()

	// Sync selected profile
	if (displayStore.posProfile) {
		selectedProfile.value = displayStore.posProfile
	}
})

// Cleanup on unmount
onUnmounted(() => {
	displayStore.stopCartSync()
})
</script>

<style scoped>
.customer-display {
	font-family: "Inter", system-ui, -apple-system, sans-serif;
}

/* Smooth animations for cart items */
.customer-display :deep(.cart-item) {
	transition: all 0.3s ease;
}
</style>
