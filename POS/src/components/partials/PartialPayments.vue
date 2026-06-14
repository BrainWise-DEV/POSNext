<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4 md:p-6">
				<div class="w-full max-w-6xl max-h-[90vh] bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col">
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-5 border-b bg-gradient-to-r from-orange-50 to-amber-50">
						<div class="flex items-center gap-3">
							<div class="p-2 bg-orange-100 rounded-lg">
								<svg class="w-6 h-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">{{ __('Partial Payments') }}</h2>
								<p class="text-sm text-gray-600 flex items-center mt-0.5">
									{{ __('Manage invoices with pending payments') }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<!-- Summary Badge -->
							<div v-if="summary.count > 0" class="px-4 py-2 bg-orange-100 rounded-lg border border-orange-200">
								<div class="text-xs text-orange-600 font-medium">
									{{ summary.count === 1 
									? __('{0} invoice - {1} outstanding', [summary.count, formatCurrency(summary.total_outstanding)])
									: __('{0} invoices - {1} outstanding', [summary.count, formatCurrency(summary.total_outstanding)]) }}
								</div>
							</div>
							<Button
								@click="loadInvoices"
								:loading="loading"
								variant="ghost"
								size="sm"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
									</svg>
								</template>
								{{ __('Refresh') }}
							</Button>
							<button
								@click="handleClose"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors"
							>
								<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Main Content -->
					<div class="flex-1 overflow-y-auto bg-gray-50">
						<!-- Loading State -->
						<div v-if="loading" class="flex flex-col items-center justify-center py-16">
							<div class="animate-spin rounded-full h-12 w-12 border-b-3 border-orange-500 mb-4"></div>
							<p class="text-sm font-medium text-gray-600">{{ __('Loading invoices...') }}</p>
						</div>

						<!-- Empty State -->
						<div v-else-if="invoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
							<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
							</svg>
							<p class="text-gray-600 font-medium">{{ __('No Partial Payments') }}</p>
							<p class="text-gray-500 text-sm mt-1">{{ __('All invoices are either fully paid or unpaid') }}</p>
						</div>

						<!-- Invoices List -->
						<div v-else class="p-6 flex flex-col gap-4">
							<div
								v-for="invoice in invoices"
								:key="invoice.name"
								class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
							>
								<!-- Invoice Header -->
								<div class="p-4 border-b bg-gray-50">
									<div class="flex items-start justify-between">
										<div>
											<div class="flex items-center gap-2">
												<h3 class="text-lg font-bold text-gray-900">{{ invoice.name }}</h3>
												<span
													:class="[
														'px-2 py-0.5 text-xs font-semibold rounded-full',
														getInvoiceStatusColor(invoice)
													]"
												>
													{{ __(invoice.status) }}
												</span>
											</div>
											<div class="flex items-center gap-4 mt-1 text-sm text-gray-600">
												<div class="flex items-center">
													<svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
													</svg>
													{{ invoice.customer_name || invoice.customer }}
												</div>
												<div class="flex items-center">
													<svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
													</svg>
													{{ formatDate(invoice.posting_date) }} {{ formatTime(invoice.posting_time) }}
												</div>
											</div>
										</div>
										<button
											@click="selectInvoice(invoice)"
											class="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors text-sm font-semibold"
										>
											{{ __('Add Payment') }}
										</button>
									</div>
								</div>

								<!-- Payment Summary -->
								<div class="p-4">
									<div class="grid grid-cols-3 gap-4 mb-4">
										<div class="text-center p-3 bg-blue-50 rounded-lg border border-blue-100">
											<div class="text-xs text-gray-600 mb-1">{{ __('Total Amount') }}</div>
											<div class="text-lg font-bold text-gray-900">{{ formatCurrency(invoice.grand_total) }}</div>
										</div>
										<div class="text-center p-3 bg-green-50 rounded-lg border border-green-100">
											<div class="text-xs text-gray-600 mb-1">{{ __('Paid') }}</div>
											<div class="text-lg font-bold text-green-600">{{ formatCurrency(invoice.paid_amount) }}</div>
										</div>
										<div class="text-center p-3 bg-orange-50 rounded-lg border border-orange-100">
											<div class="text-xs text-gray-600 mb-1">{{ __('Outstanding') }}</div>
											<div class="text-lg font-bold text-orange-600">{{ formatCurrency(invoice.outstanding_amount) }}</div>
										</div>
									</div>

									<!-- Payment Progress Bar -->
									<div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden mb-3">
										<div
											class="h-full bg-gradient-to-r from-green-500 to-green-600 transition-all duration-300"
											:style="{ width: `${(invoice.paid_amount / invoice.grand_total) * 100}%` }"
										></div>
									</div>

									<!-- Payment Methods -->
									<div v-if="invoice.payments && invoice.payments.length > 0" class="mt-3">
										<div class="text-xs font-medium text-gray-600 mb-2">{{ __('Payment History') }}</div>
										<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
											<div
												v-for="(payment, idx) in invoice.payments"
												:key="idx"
												:class="[
													'flex flex-col p-2 rounded-lg border text-sm',
													payment.source === 'Payment Entry'
														? 'bg-blue-50 border-blue-200'
														: 'bg-gray-50 border-gray-200'
												]"
											>
												<div class="flex items-center justify-between mb-1">
													<span class="text-gray-700 font-medium">{{ payment.mode_of_payment }}</span>
													<span class="font-semibold text-gray-900">{{ formatCurrency(payment.amount) }}</span>
												</div>
												<div class="flex items-center justify-between">
													<span
														v-if="payment.posting_date"
														class="text-[9px] text-gray-500"
													>
														{{ formatDate(payment.posting_date) }}
													</span>
													<span
														v-if="payment.source"
														:class="[
															'text-[9px] font-semibold',
															payment.source === 'Payment Entry'
																? 'text-blue-600'
																: 'text-gray-500'
														]"
													>
														{{ getPaymentSourceLabel(payment.source) }}
													</span>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>

	<!-- Payment Dialog -->
	<PaymentDialog
		v-model="showPaymentDialog"
		:grand-total="selectedInvoice?.outstanding_amount || 0"
		:pos-profile="posProfile"
		:currency="currency"
		:is-offline="false"
		:allow-partial-payment="posSettingsStore.allowPartialPayment"
		@payment-completed="handlePaymentCompleted"
	/>
</template>

<script setup>
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { getInvoiceStatusColor } from "@/utils/invoice"
import PaymentDialog from "@/components/sale/PaymentDialog.vue"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { useToast } from "@/composables/useToast"
import { useFormatters } from "@/composables/useFormatters"
import { Button, call } from "frappe-ui"
import { onMounted, ref, watch } from "vue"

const posSettingsStore = usePOSSettingsStore()
const { showSuccess, showError } = useToast()
const { formatDate, formatTime } = useFormatters()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits(["update:modelValue"])

const show = ref(props.modelValue)
const loading = ref(false)
const invoices = ref([])
const summary = ref({
	count: 0,
	total_outstanding: 0,
	total_paid: 0,
})
const selectedInvoice = ref(null)
const showPaymentDialog = ref(false)

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			loadInvoices()
			loadSummary()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Methods
function handleClose() {
	show.value = false
}

async function loadInvoices() {
	if (!props.posProfile) return

	loading.value = true

	try {
		const result = await call("pos_next.api.partial_payments.get_partial_paid_invoices", {
			pos_profile: props.posProfile,
			limit: 50,
		})

		invoices.value = result || []
	} catch (error) {
		console.error("Error loading partial payments:", error)
		showError(error.message || __("Failed to load partial payments"))
	} finally {
		loading.value = false
	}
}

async function loadSummary() {
	if (!props.posProfile) return

	try {
		const result = await call("pos_next.api.partial_payments.get_partial_payment_summary", {
			pos_profile: props.posProfile,
		})

		summary.value = result || { count: 0, total_outstanding: 0, total_paid: 0 }
	} catch (error) {
		console.error("Error loading summary:", error)
	}
}

function selectInvoice(invoice) {
	console.log('[PartialPayments] Select invoice:', {
		invoice: invoice.name,
		allowPartialPayment: posSettingsStore.allowPartialPayment,
		posSettings: posSettingsStore.settings
	})
	selectedInvoice.value = invoice
	showPaymentDialog.value = true
}

async function handlePaymentCompleted(paymentData) {
	console.log('[PartialPayments] Payment completed:', {
		selectedInvoice: selectedInvoice.value?.name,
		paymentData: paymentData
	})

	if (!selectedInvoice.value) {
		console.warn('[PartialPayments] No invoice selected')
		return
	}

	try {
		console.log('[PartialPayments] Calling API to add payment...')
		const result = await call("pos_next.api.partial_payments.add_payment_to_partial_invoice", {
			invoice_name: selectedInvoice.value.name,
			payments: paymentData.payments,
		})

		console.log('[PartialPayments] API response:', result)

		showSuccess(__("Payment added successfully"))

		// Reload invoices and summary
		console.log('[PartialPayments] Reloading invoices and summary...')
		await loadInvoices()
		await loadSummary()

		selectedInvoice.value = null
	} catch (error) {
		console.error("[PartialPayments] Error adding payment:", error)
		showError(error.message || __("Failed to add payment"))
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function getPaymentSourceLabel(source) {
	// Convert source to user-friendly label
	switch (source) {
		case 'POS':
			return 'POS'
		case 'POS Payment Entry':
			return 'POS'
		case 'Payment Entry':
			return 'Back Office'
		default:
			return source
	}
}


// Lifecycle
onMounted(() => {
	if (show.value) {
		loadInvoices()
		loadSummary()
	}
})
</script>

<style scoped>
/* Fade transition for overlay */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
