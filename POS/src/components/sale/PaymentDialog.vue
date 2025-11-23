<template>
	<Dialog v-model="show" :options="{ title: 'Complete Payment', size: '2xl' }">
		<template #body-content>
			<div class="space-y-4">
				<!-- INFORMATION SECTION (TOP) -->

				<!-- Payment Summary Card -->
				<div class="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
					<div class="flex justify-between items-start mb-3">
						<div>
							<div class="text-xs font-medium text-gray-600 mb-1">Total Amount</div>
							<div class="text-3xl font-bold text-gray-900">
								{{ formatCurrency(grandTotal) }}
							</div>
						</div>
						<div class="text-right">
							<div v-if="remainingAmount > 0" class="mb-2">
								<div class="text-xs font-medium text-orange-600 mb-1">Remaining</div>
								<div class="text-xl font-bold text-orange-600">
									{{ formatCurrency(remainingAmount) }}
								</div>
							</div>
							<div v-if="changeAmount > 0">
								<div class="text-xs font-medium text-green-600 mb-1">Change</div>
								<div class="text-xl font-bold text-green-600">
									{{ formatCurrency(changeAmount) }}
								</div>
							</div>
							<div v-if="totalPaid >= grandTotal && changeAmount === 0" class="flex items-center text-green-600">
								<svg class="w-5 h-5 mr-1" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
								</svg>
								<span class="text-xs font-semibold">Paid in Full</span>
							</div>
						</div>
					</div>

					<!-- Progress Bar -->
					<div class="w-full bg-white rounded-full h-2.5 overflow-hidden shadow-inner">
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

				<!-- Customer Credit Display -->
				<div
					v-if="allowCreditSale"
					:class="[
						'rounded-lg p-3 border-2',
						totalAvailableCredit > 0
							? 'bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200'
							: totalAvailableCredit < 0
							? 'bg-gradient-to-br from-red-50 to-rose-50 border-red-300'
							: 'bg-gradient-to-br from-gray-50 to-slate-50 border-gray-200'
					]"
				>
					<div class="flex items-center justify-between">
						<div class="flex items-center space-x-2">
							<div
								:class="[
									'w-8 h-8 rounded-full flex items-center justify-center',
									totalAvailableCredit > 0
										? 'bg-emerald-200'
										: totalAvailableCredit < 0
										? 'bg-red-200'
										: 'bg-gray-200'
								]"
							>
								<svg
									:class="[
										'w-5 h-5',
										totalAvailableCredit > 0
											? 'text-emerald-700'
											: totalAvailableCredit < 0
											? 'text-red-700'
											: 'text-gray-700'
									]"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										v-if="totalAvailableCredit >= 0"
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
									/>
									<path
										v-else
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
									/>
								</svg>
							</div>
							<div>
								<div class="text-xs font-semibold text-gray-800">
									{{ totalAvailableCredit >= 0 ? 'Customer Credit Available' : 'Customer Outstanding Balance' }}
								</div>
								<div v-if="totalAvailableCredit > 0" class="text-xs text-emerald-700">
									Credit can be applied to invoice
								</div>
								<div v-else-if="totalAvailableCredit < 0" class="text-xs text-red-700">
									Amount owed by customer
								</div>
								<div v-else class="text-xs text-gray-600">
									No outstanding balance
								</div>
							</div>
						</div>
						<div class="text-right">
							<div
								:class="[
									'text-xs font-medium',
									totalAvailableCredit > 0
										? 'text-emerald-700'
										: totalAvailableCredit < 0
										? 'text-red-700'
										: 'text-gray-700'
								]"
							>
								{{ totalAvailableCredit >= 0 ? 'Available' : 'Outstanding' }}
							</div>
							<div
								:class="[
									'text-2xl font-bold',
									totalAvailableCredit > 0
										? 'text-emerald-700'
										: totalAvailableCredit < 0
										? 'text-red-700'
										: 'text-gray-700'
								]"
							>
								{{ formatCurrency(Math.abs(totalAvailableCredit)) }}
							</div>
						</div>
					</div>
				</div>

				<!-- Additional Discount Section (Compact) -->
				<div v-if="settingsStore.allowAdditionalDiscount" class="bg-gradient-to-r from-orange-50 to-red-50 border border-orange-300 rounded-lg p-2">
					<div class="flex items-center justify-between mb-1.5">
						<div class="flex items-center space-x-1.5">
							<div class="w-5 h-5 rounded-full bg-orange-200 flex items-center justify-center">
								<svg class="w-3 h-3 text-orange-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
								</svg>
							</div>
							<span class="text-[11px] font-bold text-orange-900">Additional Discount</span>
							<span v-if="localAdditionalDiscount > 0" class="text-[10px] font-bold text-red-600 bg-red-100 px-1.5 py-0.5 rounded">
								-{{ formatCurrency(additionalDiscountType === 'percentage' ? (subtotal * localAdditionalDiscount / 100) : localAdditionalDiscount) }}
							</span>
						</div>
						<button
							v-if="localAdditionalDiscount > 0"
							@click="clearAdditionalDiscount"
							class="text-[10px] text-orange-700 hover:text-orange-900 font-semibold px-1.5 py-0.5 bg-orange-100 hover:bg-orange-200 rounded transition-colors"
						>
							Clear
						</button>
					</div>
					<div class="grid grid-cols-[100px_1fr] gap-1.5">
						<!-- Discount Type Selector (Compact) -->
						<select
							v-model="additionalDiscountType"
							@change="handleAdditionalDiscountTypeChange"
							class="w-full px-1.5 py-1.5 text-[11px] font-medium border border-orange-300 rounded focus:outline-none focus:ring-1 focus:ring-orange-500 focus:border-transparent bg-white"
						>
							<option value="percentage">% Percent</option>
							<option value="amount">{{ currency }} Amount</option>
						</select>
						<!-- Discount Value Input (Compact) -->
						<div class="relative">
							<span v-if="additionalDiscountType === 'amount'" class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-600 text-[11px] font-medium">{{ currency }}</span>
							<input
								type="number"
								v-model.number="localAdditionalDiscount"
								@input="handleAdditionalDiscountChange"
								placeholder="0.00"
								min="0"
								:max="additionalDiscountType === 'percentage' ? 100 : subtotal"
								step="0.01"
								:class="[
									'w-full py-1.5 text-[11px] font-semibold border border-orange-300 rounded focus:outline-none focus:ring-1 focus:ring-orange-500 focus:border-transparent bg-white placeholder-gray-400',
									additionalDiscountType === 'amount' ? 'pl-9 pr-2' : 'px-2 pr-6'
								]"
							/>
							<span v-if="additionalDiscountType === 'percentage'" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 text-[11px] font-medium">%</span>
						</div>
					</div>
				</div>

				<!-- Payment Methods Grid -->
				<div>
					<h3 class="text-sm font-semibold text-gray-700 mb-3">Payment Methods</h3>
					<div class="text-xs text-gray-500 mb-2">
						Select payment method to add
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
								step="5"
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
									step="5"
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
			<div class="flex justify-between items-center w-full space-x-2">
				<!-- Left: Clear All Button -->
				<Button
					v-if="paymentEntries.length > 0"
					variant="subtle"
					@click="clearAll"
					theme="red"
				>
					Clear All
				</Button>
				<div v-else></div>

				<!-- Right: Main Action Buttons -->
				<div class="flex items-center space-x-2">
					<Button variant="subtle" @click="show = false">
						Cancel
					</Button>

					<!-- Apply Credit Button (if available) -->
					<Button
						v-if="allowCreditSale && totalAvailableCredit > 0 && remainingAmount > 0"
						variant="solid"
						@click="applyCustomerCredit"
					>
						<template #prefix>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
							</svg>
						</template>
						Apply Credit
					</Button>

					<!-- Pay on Account Button (if credit sales enabled) -->
					<button
						v-if="allowCreditSale"
						@click="addCreditAccountPayment"
						:disabled="paymentEntries.length > 0"
						:class="[
							'inline-flex items-center justify-center gap-2 transition-colors focus:outline-none shrink-0 h-7 text-base px-2 rounded',
							paymentEntries.length > 0
								? 'bg-orange-400 text-ink-white cursor-not-allowed'
								: 'bg-orange-600 text-ink-white focus-visible:ring focus-visible:ring-orange-400 hover:bg-orange-700 active:bg-orange-800'
						]"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
						</svg>
						<span class="truncate">Pay on Account</span>
					</button>

					<!-- Complete/Partial Payment Button -->
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
import { usePOSSettingsStore } from "@/stores/posSettings"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { getPaymentIcon } from "@/utils/payment"
import { offlineWorker } from "@/utils/offline/workerClient"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import { useToast } from "@/composables/useToast"

const settingsStore = usePOSSettingsStore()
const { showWarning } = useToast()

const props = defineProps({
	modelValue: Boolean,
	grandTotal: {
		type: Number,
		default: 0,
	},
	subtotal: {
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
	allowCreditSale: {
		type: Boolean,
		default: false,
	},
	customer: {
		type: [String, Object],
		default: null,
	},
	company: {
		type: String,
		default: "",
	},
	additionalDiscount: {
		type: Number,
		default: 0,
	},
})

const emit = defineEmits(["update:modelValue", "payment-completed", "update-additional-discount"])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const paymentMethods = ref([])
const lastSelectedMethod = ref(null)
const customAmount = ref("")
const paymentEntries = ref([])
const customerCredit = ref([])
const customerBalance = ref({ total_outstanding: 0, total_credit: 0, net_balance: 0 })
const loadingCredit = ref(false)

// Additional discount state
const localAdditionalDiscount = ref(0)
// Initialize discount type from settings (default to percentage if enabled, otherwise amount)
const additionalDiscountType = ref(
	settingsStore.usePercentageDiscount ? 'percentage' : 'amount'
)

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

const customerCreditResource = createResource({
	url: "pos_next.api.credit_sales.get_available_credit",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		console.log('[PaymentDialog] Fetching credit for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		console.log('[PaymentDialog] Customer credit loaded:', data)
		customerCredit.value = data || []
		loadingCredit.value = false
		console.log('[PaymentDialog] Total available credit:', totalAvailableCredit.value)
	},
	onError(error) {
		console.error("[PaymentDialog] Error loading customer credit:", error)
		customerCredit.value = []
		loadingCredit.value = false
	},
})

const customerBalanceResource = createResource({
	url: "pos_next.api.credit_sales.get_customer_balance",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		console.log('[PaymentDialog] Fetching balance for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
		}
	},
	auto: false,
	onSuccess(data) {
		console.log('[PaymentDialog] Customer balance loaded:', data)
		customerBalance.value = data || { total_outstanding: 0, total_credit: 0, net_balance: 0 }
		console.log('[PaymentDialog] Net balance:', customerBalance.value.net_balance)
	},
	onError(error) {
		console.error("[PaymentDialog] Error loading customer balance:", error)
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }
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

const totalAvailableCredit = computed(() => {
	// Use net_balance: negative means customer has credit, positive means they owe
	// Return negative of net_balance so positive = credit available, negative = outstanding
	return -customerBalance.value.net_balance
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
		customerCredit.value = []
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }

		// Debug logging
		console.log('[PaymentDialog] Dialog opened with props:', {
			allowCreditSale: props.allowCreditSale,
			customer: props.customer,
			company: props.company,
			posProfile: props.posProfile
		})

		// Load payment methods
		if (props.posProfile) {
			loadPaymentMethods()
		}

		// Load customer credit and balance if enabled and customer is selected
		if (props.allowCreditSale && props.customer && props.company) {
			console.log('[PaymentDialog] Loading customer credit and balance...')
			loadingCredit.value = true
			customerCreditResource.fetch()
			customerBalanceResource.fetch()
		} else {
			console.log('[PaymentDialog] Not loading credit because:', {
				allowCreditSale: props.allowCreditSale,
				hasCustomer: !!props.customer,
				hasCompany: !!props.company
			})
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

// Apply existing customer credit to payment
function applyCustomerCredit() {
	console.log('[PaymentDialog] Apply customer credit:', {
		totalCredit: totalAvailableCredit.value,
		remainingAmount: remainingAmount.value,
		currentEntries: paymentEntries.value.length
	})

	if (remainingAmount.value === 0 || totalAvailableCredit.value === 0) return

	// Calculate how much credit to apply (min of remaining amount and available credit)
	const creditToApply = Math.min(remainingAmount.value, totalAvailableCredit.value)

	// Add credit as a payment entry
	paymentEntries.value.push({
		mode_of_payment: "Customer Credit",
		amount: Number.parseFloat(creditToApply.toFixed(2)),
		type: "Credit",
		is_customer_credit: true,
		credit_details: customerCredit.value.map(credit => ({
			...credit,
			credit_to_redeem: 0  // Will be calculated on backend
		}))
	})

	console.log('[PaymentDialog] Existing credit applied, new entries:', paymentEntries.value)
}

// Add "Pay on Account" - Credit Sale (invoice with outstanding amount)
function addCreditAccountPayment() {
	console.log('[PaymentDialog] Add credit account payment (Pay Later):', {
		grandTotal: props.grandTotal,
		currentPaid: totalPaid.value,
		remainingAmount: remainingAmount.value
	})

	// Close dialog and complete as credit sale (0 payment)
	// The backend will create an invoice with outstanding amount
	const paymentData = {
		payments: [],  // No payments - full amount on credit
		change_amount: 0,
		is_partial_payment: false,
		is_credit_sale: true,  // Mark as credit sale
		paid_amount: 0,
		outstanding_amount: props.grandTotal,
	}

	console.log('[PaymentDialog] Emitting credit sale payment-completed:', paymentData)
	emit("payment-completed", paymentData)
	show.value = false
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


// Additional discount handlers
function handleAdditionalDiscountChange() {
	let discountValue = localAdditionalDiscount.value
	let discountAmount = 0

	// If percentage mode, calculate amount
	if (additionalDiscountType.value === 'percentage') {
		// Validate against max_discount_allowed if configured
		if (settingsStore.maxDiscountAllowed > 0 && discountValue > settingsStore.maxDiscountAllowed) {
			localAdditionalDiscount.value = settingsStore.maxDiscountAllowed
			discountValue = settingsStore.maxDiscountAllowed
			// Show warning toast
			showWarning(`Maximum allowed discount is ${settingsStore.maxDiscountAllowed}%`)
		}

		// Ensure percentage is between 0-100
		if (discountValue > 100) {
			localAdditionalDiscount.value = 100
			discountValue = 100
		}

		// Convert percentage to amount
		discountAmount = (props.subtotal * discountValue) / 100
	} else {
		// Amount mode
		discountAmount = discountValue

		// For amount mode, check if it exceeds percentage limit when converted
		if (settingsStore.maxDiscountAllowed > 0 && props.subtotal > 0) {
			const percentageEquivalent = (discountAmount / props.subtotal) * 100
			if (percentageEquivalent > settingsStore.maxDiscountAllowed) {
				const maxAmount = (props.subtotal * settingsStore.maxDiscountAllowed) / 100
				localAdditionalDiscount.value = maxAmount
				discountAmount = maxAmount
				// Show warning toast
				showWarning(`Maximum allowed discount is ${settingsStore.maxDiscountAllowed}% (${props.currency} ${maxAmount.toFixed(2)})`)
			}
		}
	}

	// Ensure discount doesn't exceed subtotal
	if (discountAmount > props.subtotal) {
		if (additionalDiscountType.value === 'amount') {
			localAdditionalDiscount.value = props.subtotal
		}
		discountAmount = props.subtotal
	}

	// Ensure non-negative
	if (discountAmount < 0) {
		localAdditionalDiscount.value = 0
		discountAmount = 0
	}

	emit("update-additional-discount", discountAmount)
}

function handleAdditionalDiscountTypeChange() {
	// Don't reset - preserve last value when toggling type
	// Just recalculate to ensure it's within limits
	handleAdditionalDiscountChange()
}

function clearAdditionalDiscount() {
	localAdditionalDiscount.value = 0
	emit("update-additional-discount", 0)
}

// Watch for dialog open to sync additional discount from parent
watch(
	() => props.modelValue,
	(isOpen) => {
		if (isOpen) {
			// Only sync when dialog opens, not continuously
			localAdditionalDiscount.value = props.additionalDiscount || 0
		}
	},
)
</script>
