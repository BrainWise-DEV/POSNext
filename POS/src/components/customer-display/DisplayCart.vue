<template>
	<div class="flex flex-col h-full bg-white dark:bg-gray-900">
		<!-- Empty cart state -->
		<div v-if="!displayStore.hasItems" class="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500">
			<FeatherIcon name="shopping-cart" class="w-32 h-32 mb-6 opacity-30" />
			<p class="text-2xl text-gray-600 dark:text-gray-400">{{ __("Your cart is empty") }}</p>
			<p class="text-lg mt-2 text-gray-400 dark:text-gray-600">{{ __("Your items will appear here") }}</p>
		</div>

		<!-- Cart with items -->
		<div v-else class="flex-1 flex flex-col overflow-hidden">
			<!-- Items list -->
			<div class="flex-1 overflow-y-auto p-6">
				<transition-group
					name="cart-item"
					tag="div"
					class="space-y-4"
				>
					<div
						v-for="(item, index) in displayStore.cartData.items"
						:key="item.item_code + '-' + index"
						class="cart-item bg-gray-100 dark:bg-gray-800 rounded-xl p-4 flex items-center gap-4 shadow-lg"
					>
						<!-- Item image -->
						<div class="w-20 h-20 flex-shrink-0 bg-gray-200 dark:bg-gray-700 rounded-lg overflow-hidden">
							<img
								v-if="item.image"
								:src="item.image"
								:alt="item.item_name"
								class="w-full h-full object-cover"
							/>
							<div v-else class="w-full h-full flex items-center justify-center">
								<FeatherIcon name="package" class="w-8 h-8 text-gray-400 dark:text-gray-500" />
							</div>
						</div>

						<!-- Item details -->
						<div class="flex-1 min-w-0">
							<h3 class="text-lg font-medium text-gray-900 dark:text-white truncate">
								{{ item.item_name }}
							</h3>
							<p class="text-sm text-gray-500 dark:text-gray-400">
								{{ item.item_code }}
							</p>
							<!-- Show discount if applied -->
							<p v-if="item.discount_percentage" class="text-sm text-green-600 dark:text-green-400">
								-{{ item.discount_percentage }}%
							</p>
						</div>

						<!-- Quantity -->
						<div class="text-center px-4">
							<span class="text-3xl font-bold text-gray-900 dark:text-white">{{ item.qty }}</span>
							<p class="text-xs text-gray-500 dark:text-gray-400 uppercase">{{ item.uom || __("Unit") }}</p>
						</div>

						<!-- Price -->
						<div class="text-right min-w-[120px]">
							<p class="text-xl font-semibold text-gray-900 dark:text-white">
								{{ formatCurrency(item.amount) }}
							</p>
							<p class="text-sm text-gray-500 dark:text-gray-400">
								{{ formatCurrency(item.rate) }} / {{ item.uom || __("Unit") }}
							</p>
						</div>
					</div>
				</transition-group>
			</div>

			<!-- Totals section -->
			<div class="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 p-6">
				<div class="max-w-2xl mx-auto space-y-3">
					<!-- Subtotal -->
					<div class="flex justify-between text-lg text-gray-600 dark:text-gray-400">
						<span>{{ __("Subtotal") }}</span>
						<span>{{ formatCurrency(displayStore.cartData.subtotal) }}</span>
					</div>

					<!-- Tax -->
					<div v-if="displayStore.cartData.total_tax" class="flex justify-between text-lg text-gray-600 dark:text-gray-400">
						<span>{{ __("Tax") }}</span>
						<span>{{ formatCurrency(displayStore.cartData.total_tax) }}</span>
					</div>

					<!-- Discount -->
					<div v-if="displayStore.cartData.discount_amount" class="flex justify-between text-lg text-green-600 dark:text-green-400">
						<span>{{ __("Discount") }}</span>
						<span>-{{ formatCurrency(displayStore.cartData.discount_amount) }}</span>
					</div>

					<!-- Grand Total -->
					<div class="flex justify-between text-4xl font-bold text-gray-900 dark:text-white pt-4 border-t border-gray-200 dark:border-gray-700">
						<span>{{ __("Total") }}</span>
						<span class="text-blue-600 dark:text-blue-400">{{ formatCurrency(displayStore.cartData.grand_total) }}</span>
					</div>
				</div>

				<!-- Item count -->
				<div class="text-center mt-4 text-gray-500">
					{{ displayStore.itemCount }} {{ displayStore.itemCount === 1 ? __("item in your cart") : __("items in your cart") }}
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { useCustomerDisplayStore } from "@/stores/customerDisplay"

const displayStore = useCustomerDisplayStore()

// Format currency
function formatCurrency(amount) {
	const currency = displayStore.cartData.currency || "EUR"
	return new Intl.NumberFormat("fr-FR", {
		style: "currency",
		currency: currency,
	}).format(amount || 0)
}
</script>

<style scoped>
/* Cart item transitions */
.cart-item-enter-active,
.cart-item-leave-active {
	transition: all 0.3s ease;
}

.cart-item-enter-from {
	opacity: 0;
	transform: translateX(-30px);
}

.cart-item-leave-to {
	opacity: 0;
	transform: translateX(30px);
}

.cart-item-move {
	transition: transform 0.3s ease;
}

/* Smooth scrollbar for webkit browsers */
::-webkit-scrollbar {
	width: 8px;
}

::-webkit-scrollbar-track {
	background: #1f2937;
}

::-webkit-scrollbar-thumb {
	background: #4b5563;
	border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
	background: #6b7280;
}
</style>
