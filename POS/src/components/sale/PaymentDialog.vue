<template>
	<Dialog v-model="show" :options="{ title: 'Complete Payment', size: '2xl' }">
		<template #body-content>
			<div class="space-y-6">
				<!-- Payment Summary Card -->
				<div class="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-100">
					<div class="flex justify-between items-start mb-4">
						<div>
							<div class="text-sm font-medium text-gray-600 mb-1">Total Amount</div>
							<div class="text-4xl font-bold text-gray-900">
								{{ formatCurrency(grandTotal) }}
							</div>
						</div>
						<div class="text-right">
							<div v-if="remainingAmount > 0" class="mb-2">
								<div class="text-xs font-medium text-orange-600 mb-1">Remaining</div>
								<div class="text-2xl font-bold text-orange-600">
									{{ formatCurrency(remainingAmount) }}
								</div>
							</div>
							<div v-if="changeAmount > 0">
								<div class="text-xs font-medium text-green-600 mb-1">Change</div>
								<div class="text-2xl font-bold text-green-600">
									{{ formatCurrency(changeAmount) }}
								</div>
							</div>
							<div v-if="totalPaid >= grandTotal && changeAmount === 0" class="flex items-center text-green-600">
								<svg class="w-6 h-6 mr-1" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
								</svg>
								<span class="text-sm font-semibold">Paid in Full</span>
							</div>
						</div>
					</div>

					<!-- Progress Bar -->
					<div class="w-full bg-white rounded-full h-3 overflow-hidden shadow-inner">
						<div
							:class="[
								'h-full transition-all duration-300',
								totalPaid >= grandTotal ? 'bg-green-500' : 'bg-blue-500'
							]"
							:style="{ width: `${grandTotal > 0 ? Math.min((totalPaid / grandTotal) * 100, 100) : 0}%` }"
						></div>
					</div>
					<div class="text-xs text-gray-600 mt-1">
						{{ formatCurrency(totalPaid) }} paid of {{ formatCurrency(grandTotal) }}
					</div>
				</div>

				<!-- Payment Methods Grid -->
				<div>
					<div class="flex items-center justify-between mb-3">
						<h3 class="text-sm font-semibold text-gray-700">Payment Methods</h3>
						<div v-if="remainingAmount > 0" class="text-xs text-gray-500">
							Click to add payment
						</div>
					</div>
					<div class="grid grid-cols-2 md:grid-cols-3 gap-3">
						<button
							v-for="method in paymentMethods"
							:key="method.mode_of_payment"
							@click="quickAddPayment(method)"
							:disabled="remainingAmount === 0"
							:class="[
								'group relative p-4 rounded-xl border-2 transition-all text-left',
								'hover:shadow-lg transform hover:-translate-y-0.5',
								remainingAmount === 0 ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
								'border-gray-200 hover:border-blue-400 bg-white hover:bg-blue-50'
							]"
						>
							<div class="flex items-start justify-between">
								<div class="flex-1">
									<div class="flex items-center mb-1">
										<span class="text-2xl mr-2">{{ getPaymentIcon(method.type) }}</span>
										<div>
											<div class="font-semibold text-sm text-gray-900">
												{{ method.mode_of_payment }}
											</div>
											<div class="text-xs text-gray-500">{{ method.type || "Cash" }}</div>
										</div>
									</div>
								</div>
								<div class="opacity-0 group-hover:opacity-100 transition-opacity">
									<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
									</svg>
								</div>
							</div>
							<div v-if="getMethodTotal(method.mode_of_payment) > 0"
								class="mt-2 pt-2 border-t border-gray-200">
								<div class="text-xs text-gray-500">Added</div>
								<div class="font-bold text-blue-600">
									{{ formatCurrency(getMethodTotal(method.mode_of_payment)) }}
								</div>
							</div>
						</button>
					</div>
				</div>

				<!-- Quick Amount Buttons -->
				<div v-if="remainingAmount > 0 && lastSelectedMethod" class="bg-gray-50 rounded-lg p-4 border border-gray-200">
					<div class="text-xs font-medium text-gray-600 mb-2">
						Quick amounts for {{ lastSelectedMethod.mode_of_payment }}
					</div>
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
						<button
							v-for="amount in quickAmounts"
							:key="amount"
							@click="addCustomPayment(lastSelectedMethod, amount)"
							class="px-4 py-3 text-sm font-semibold rounded-lg bg-white border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-700 hover:text-blue-600 transition-all"
						>
							{{ formatCurrency(amount) }}
						</button>
					</div>
					<div class="mt-2">
						<div class="text-xs font-medium text-gray-600 mb-1">Custom amount</div>
						<div class="flex space-x-2">
							<Input
								v-model="customAmount"
								type="number"
								step="0.01"
								min="0"
								placeholder="0.00"
								class="flex-1"
								@keyup.enter="addCustomPayment(lastSelectedMethod, customAmount)"
							/>
							<Button
								variant="solid"
								theme="blue"
								@click="addCustomPayment(lastSelectedMethod, customAmount)"
								:disabled="!customAmount || customAmount <= 0"
							>
								Add
							</Button>
						</div>
					</div>
				</div>

				<!-- Active Payment Entries -->
				<div v-if="paymentEntries.length > 0">
					<h3 class="text-sm font-semibold text-gray-700 mb-3">Payment Breakdown</h3>
					<div class="space-y-2 max-h-64 overflow-y-auto">
						<div
							v-for="(entry, index) in paymentEntries"
							:key="index"
							class="group flex items-center justify-between p-3 bg-white rounded-lg border-2 border-gray-200 hover:border-red-300 transition-all"
						>
							<div class="flex items-center space-x-3">
								<span class="text-xl">{{ getPaymentIcon(entry.type) }}</span>
								<div>
									<div class="font-medium text-sm text-gray-900">{{ entry.mode_of_payment }}</div>
									<div class="text-xs text-gray-500">{{ entry.type }}</div>
								</div>
							</div>
							<div class="flex items-center space-x-4">
								<input
									v-model.number="entry.amount"
									type="number"
									step="0.01"
									min="0"
									class="w-28 px-3 py-1 text-right font-bold text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
									@input="updatePaymentEntry(index, $event.target.value)"
								/>
								<button
									@click="removePaymentEntry(index)"
									class="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-all"
								>
									<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
									</svg>
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex justify-between items-center w-full">
				<Button variant="subtle" @click="clearAll" v-if="paymentEntries.length > 0" theme="red">
					Clear All
				</Button>
				<div class="flex space-x-2 ml-auto">
					<Button variant="subtle" @click="show = false">Cancel</Button>
					<Button
						variant="solid"
						theme="blue"
						@click="completePayment"
						:disabled="!canComplete"
					>
						<template #prefix>
							<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
								<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
							</svg>
						</template>
						{{ paymentButtonText }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { offlineWorker } from "@/utils/offline/workerClient"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	grandTotal: {
		type: Number,
		default: 0,
	},
	posProfile: String,
	currency: {
		type: String,
		default: "USD",
	},
	isOffline: {
		type: Boolean,
		default: false,
	},
	allowPartialPayment: {
		type: Boolean,
		default: false,
	},
})

const emit = defineEmits(["update:modelValue", "payment-completed"])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const paymentMethods = ref([])
const lastSelectedMethod = ref(null)
const customAmount = ref("")
const paymentEntries = ref([])

const paymentMethodsResource = createResource({
	url: "pos_next.api.pos_profile.get_payment_methods",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		paymentMethods.value = data?.message || data || []
		// Set first method as last selected for quick amounts
		if (paymentMethods.value.length > 0) {
			const defaultMethod = paymentMethods.value.find((m) => m.default)
			lastSelectedMethod.value = defaultMethod || paymentMethods.value[0]
		}
	},
})

// Load payment methods - from cache if offline, from server if online
async function loadPaymentMethods() {
	// Guard: Don't load if posProfile is not set
	if (!props.posProfile) {
		console.warn(
			"PaymentDialog: Cannot load payment methods - posProfile is not set",
		)
		return
	}

	if (props.isOffline) {
		// Load from cache when offline using worker
		const cached = await offlineWorker.getCachedPaymentMethods(props.posProfile)
		if (cached && cached.length > 0) {
			paymentMethods.value = cached
			if (paymentMethods.value.length > 0) {
				const defaultMethod = paymentMethods.value.find((m) => m.default)
				lastSelectedMethod.value = defaultMethod || paymentMethods.value[0]
			}
		}
	} else {
		// Load from server when online
		// Use fetch() instead of reload() for proper initialization
		try {
			await paymentMethodsResource.fetch()
		} catch (error) {
			console.error("Error loading payment methods:", error)
		}
	}
}

const totalPaid = computed(() => {
	return paymentEntries.value.reduce(
		(sum, entry) => sum + (entry.amount || 0),
		0,
	)
})

const remainingAmount = computed(() => {
	const remaining = props.grandTotal - totalPaid.value
	return remaining > 0 ? remaining : 0
})

const changeAmount = computed(() => {
	const change = totalPaid.value - props.grandTotal
	return change > 0 ? change : 0
})

const canComplete = computed(() => {
	// If partial payment is allowed, can complete with any amount > 0
	if (props.allowPartialPayment) {
		return totalPaid.value > 0 && paymentEntries.value.length > 0
	}
	// Otherwise require full payment
	return totalPaid.value >= props.grandTotal && paymentEntries.value.length > 0
})

const paymentButtonText = computed(() => {
	console.log('[PaymentDialog] Button text calculation:', {
		totalPaid: totalPaid.value,
		grandTotal: props.grandTotal,
		allowPartialPayment: props.allowPartialPayment,
		canComplete: canComplete.value
	})

	if (totalPaid.value >= props.grandTotal) {
		return "Complete Payment"
	}
	if (props.allowPartialPayment && totalPaid.value > 0) {
		return "Partial Payment"
	}
	return "Complete Payment"
})

const quickAmounts = computed(() => {
	const remaining = remainingAmount.value
	if (remaining <= 0) {
		return [10, 20, 50, 100]
	}

	const amounts = []
	const exactAmount = Math.ceil(remaining)

	// For very small amounts (< 5), use small increments
	if (remaining < 5) {
		amounts.push(exactAmount, 5, 10, 20)
	}
	// For small amounts (5-20), use common bills/coins
	else if (remaining < 20) {
		amounts.push(exactAmount, 10, 20, 50)
	}
	// For medium amounts (20-100), use sensible denominations
	else if (remaining < 100) {
		amounts.push(exactAmount, Math.ceil(remaining / 10) * 10, 50, 100)
	}
	// For larger amounts, use bigger increments
	else {
		amounts.push(
			exactAmount,
			Math.ceil(remaining / 10) * 10,
			Math.ceil(remaining / 50) * 50,
			Math.ceil(remaining / 100) * 100,
		)
	}

	// Remove duplicates, filter positive, sort, and limit to 4
	return [...new Set(amounts)]
		.filter((amt) => amt > 0)
		.sort((a, b) => a - b)
		.slice(0, 4)
})

watch(show, (newVal) => {
	if (newVal) {
		// Reset state when dialog opens
		paymentEntries.value = []
		customAmount.value = ""
		lastSelectedMethod.value = null

		// Load payment methods
		if (props.posProfile) {
			loadPaymentMethods()
		}
	}
})

// One-click payment - adds remaining amount with selected method
function quickAddPayment(method) {
	console.log('[PaymentDialog] Quick add payment:', {
		method: method.mode_of_payment,
		remainingAmount: remainingAmount.value,
		currentEntries: paymentEntries.value.length
	})

	if (remainingAmount.value === 0) return

	lastSelectedMethod.value = method

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: Number.parseFloat(remainingAmount.value.toFixed(2)),
		type: method.type || "Cash",
	})

	console.log('[PaymentDialog] Payment added, new entries:', paymentEntries.value)
	customAmount.value = ""
}

// Add custom amount for a method
function addCustomPayment(method, amount) {
	console.log('[PaymentDialog] Add custom payment:', {
		method: method.mode_of_payment,
		amount: amount,
		currentEntries: paymentEntries.value.length
	})

	const amt = Number.parseFloat(amount)
	if (!amt || amt <= 0) return

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: amt,
		type: method.type || "Cash",
	})

	console.log('[PaymentDialog] Payment added, new entries:', paymentEntries.value)
	customAmount.value = ""
}

function removePaymentEntry(index) {
	paymentEntries.value.splice(index, 1)
}

function updatePaymentEntry(index, value) {
	const amt = Number.parseFloat(value)
	if (amt && amt > 0) {
		paymentEntries.value[index].amount = amt
	}
}

function clearAll() {
	paymentEntries.value = []
	customAmount.value = ""
}

function completePayment() {
	console.log('[PaymentDialog] Complete payment called:', {
		canComplete: canComplete.value,
		totalPaid: totalPaid.value,
		grandTotal: props.grandTotal,
		allowPartialPayment: props.allowPartialPayment,
		paymentEntries: paymentEntries.value
	})

	if (!canComplete.value) {
		console.warn('[PaymentDialog] Cannot complete - validation failed')
		return
	}

	const isPartial = totalPaid.value < props.grandTotal

	const paymentData = {
		payments: paymentEntries.value,
		change_amount: changeAmount.value,
		is_partial_payment: isPartial,
		paid_amount: totalPaid.value,
		outstanding_amount: isPartial ? remainingAmount.value : 0,
	}

	console.log('[PaymentDialog] Emitting payment-completed:', paymentData)

	emit("payment-completed", paymentData)

	show.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

// Get total amount for a specific payment method
function getMethodTotal(methodName) {
	return paymentEntries.value
		.filter((entry) => entry.mode_of_payment === methodName)
		.reduce((sum, entry) => sum + (entry.amount || 0), 0)
}

// Get icon based on payment type
function getPaymentIcon(type) {
	const iconMap = {
		Cash: "💵",
		Card: "💳",
		Bank: "🏦",
		Phone: "📱",
		Wallet: "👛",
		"Credit Card": "💳",
		"Debit Card": "💳",
		"Mobile Money": "📱",
		Check: "🧾",
		"Gift Card": "🎁",
	}
	return iconMap[type] || "💰"
}
</script>
