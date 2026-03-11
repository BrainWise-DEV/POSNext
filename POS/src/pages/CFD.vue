<template>
	<div class="flex flex-col lg:flex-row h-screen bg-gray-50 text-gray-900 overflow-hidden font-sans">
		<!-- Left Side: Order Items -->
		<div class="flex-1 flex flex-col bg-white shadow-xl z-10 lg:w-2/3 max-w-4xl border-r">
			<div class="p-6 bg-gradient-to-r from-blue-600 to-indigo-700 text-white flex justify-between items-center shadow-md">
				<h1 class="text-3xl font-extrabold tracking-tight">{{ __("Your Order") }}</h1>
				<div class="text-lg font-medium opacity-90">{{ itemCount }} {{ __("Items") }}</div>
			</div>

			<div class="flex-1 overflow-y-auto p-6">
				<div v-if="items.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
					<svg class="w-32 h-32 mb-6 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
					<p class="text-2xl font-medium">{{ __("Welcome! Please place your order at the counter.") }}</p>
				</div>
				<ul v-else class="space-y-4">
					<li v-for="item in items" :key="item.item_code" class="flex justify-between items-center p-5 bg-gray-50 rounded-2xl border border-gray-100 shadow-sm transition-transform hover:scale-[1.01]">
						<div class="flex items-center gap-4">
							<div class="w-12 h-12 bg-blue-100 text-blue-700 rounded-xl flex items-center justify-center font-bold text-xl">
								{{ item.qty || item.quantity }}<span class="text-sm ml-0.5 opacity-70">x</span>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-800">{{ item.item_name }}</h2>
								<div v-if="item.posa_special_instructions" class="text-sm font-medium text-purple-600 mt-1">
									{{ item.posa_special_instructions }}
								</div>
								<div v-if="item.discount_amount > 0" class="text-sm font-bold text-green-600 mt-1">
									{{ __("Discount Applied") }}
								</div>
							</div>
						</div>
						<div class="text-2xl font-bold text-gray-900">
							{{ formatCFDCurrency(item.rate * (item.qty || item.quantity)) }}
						</div>
					</li>
				</ul>
			</div>
		</div>

		<!-- Right Side: Order Summary & Branding -->
		<div class="lg:w-1/3 flex flex-col bg-gray-900 text-white relative overflow-hidden">
			<!-- Abstract decorative background -->
			<div class="absolute top-0 right-0 -mr-20 -mt-20 w-96 h-96 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
			<div class="absolute bottom-0 left-0 -ml-20 -mb-20 w-80 h-80 rounded-full bg-purple-500 opacity-20 blur-3xl"></div>

			<div class="p-8 flex-1 flex flex-col justify-center relative z-10">

				<div class="bg-white/10 backdrop-blur-md rounded-3xl p-8 shadow-2xl border border-white/20">
					<h3 class="text-2xl font-bold text-blue-200 mb-6 uppercase tracking-wider">{{ __("Order Total") }}</h3>

					<div class="space-y-4 mb-8">
						<div class="flex justify-between items-center text-xl text-gray-300">
							<span>{{ __("Subtotal") }}</span>
							<span>{{ formatCFDCurrency(subtotal) }}</span>
						</div>

						<div v-if="totalTax > 0" class="flex justify-between items-center text-xl text-gray-300">
							<span>{{ __("Tax") }}</span>
							<span>{{ formatCFDCurrency(totalTax) }}</span>
						</div>

						<div v-if="totalDiscount > 0" class="flex justify-between items-center text-xl text-green-400 font-bold">
							<span>{{ __("Discount") }}</span>
							<span>- {{ formatCFDCurrency(totalDiscount) }}</span>
						</div>
					</div>

					<div class="pt-6 border-t border-white/20 flex justify-between items-end">
						<span class="text-2xl font-bold text-gray-100">{{ __("Total to Pay") }}</span>
						<span class="text-6xl font-black text-white tracking-tighter">{{ formatCFDCurrency(grandTotal) }}</span>
					</div>
				</div>

			</div>

			<!-- Footer -->
			<div class="p-6 text-center relative z-10 bg-black/30 backdrop-blur-sm">
				<p class="text-xl font-medium text-gray-300 mb-2">{{ __("Thank you for your visit!") }}</p>
				<p class="text-sm text-gray-500">Powered by Midiya</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { initSocket } from "@/socket"

const items = ref([])
const grandTotal = ref(0)
const totalTax = ref(0)
const totalDiscount = ref(0)
const currency = ref('AZN') // Default fallback

const itemCount = computed(() => {
	return items.value.reduce((acc, item) => acc + Number(item.qty || item.quantity || 1), 0)
})

const subtotal = computed(() => {
	return grandTotal.value - totalTax.value + totalDiscount.value
})

function formatCFDCurrency(amount) {
	return new Intl.NumberFormat('az-Latn-AZ', {
		style: 'currency',
		currency: currency.value || 'AZN',
		minimumFractionDigits: 2
	}).format(amount)
}

let channel = null
let socket = null

onMounted(() => {
	// Initialize BroadcastChannel to listen to cart updates locally (same browser)
	channel = new BroadcastChannel('pos_cfd_sync')

	const updateFromPayload = (payload) => {
		items.value = payload.items || []
		grandTotal.value = payload.grandTotal || 0
		totalTax.value = payload.totalTax || 0
		totalDiscount.value = payload.totalDiscount || 0
		currency.value = payload.currency || 'AZN'
	}

	channel.onmessage = (event) => {
		if (event.data && event.data.type === 'CART_UPDATE') {
			updateFromPayload(event.data.payload)
		}
	}

	// Fallback to socket.io for cross-browser/cross-device updates
	socket = initSocket()
	if (socket) {
		if (socket.disconnected) {
			socket.connect()
		}
		socket.on("cfd_update", (payload) => {
			if (typeof payload === 'string') {
				try {
					payload = JSON.parse(payload)
				} catch(e){}
			}
			updateFromPayload(payload)
		})
	}
})

onBeforeUnmount(() => {
	if (channel) {
		channel.close()
	}
	if (socket) {
		socket.off("cfd_update")
	}
})
</script>

<style>
body {
	margin: 0;
	overflow: hidden;
}
</style>
