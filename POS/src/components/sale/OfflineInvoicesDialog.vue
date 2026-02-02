<template>
	<Dialog v-model="show" :options="{ title: __('Offline Invoices'), size: 'xl' }">
		<template #body-content>
			<div class="flex flex-col gap-3 sm:flex flex-col gap-4">
				<!-- Header Info -->
				<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 sm:p-4 bg-orange-50 rounded-lg border border-orange-200">
					<div class="flex items-center gap-2 sm:gap-3">
						<svg class="w-5 h-5 sm:w-6 sm:h-6 text-orange-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
						</svg>
						<div class="min-w-0">
							<h3 class="font-semibold text-gray-900 text-sm sm:text-base">{{ __('{0} Pending Invoice(s)', [invoices.length]) }}</h3>
							<p class="text-xs sm:text-sm text-gray-600 truncate">{{ __("These invoices will be submitted when you're back online") }}</p>
						</div>
					</div>
					<Button
						v-if="!isOffline && invoices.length > 0"
						@click="syncAll"
						:loading="isSyncing"
						variant="solid"
						class="flex-shrink-0 whitespace-nowrap w-full sm:w-auto text-sm"
					>
						<template #prefix>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
							</svg>
						</template>
						{{ __('Sync All') }}
					</Button>
				</div>

				<!-- Loading State -->
				<div v-if="loading" class="flex items-center justify-center py-12">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
				</div>

				<!-- Empty State -->
				<div v-else-if="invoices.length === 0" class="text-center py-12">
					<svg class="w-16 h-16 mx-auto text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
					</svg>
					<p class="mt-4 text-gray-500">{{ __('No pending offline invoices') }}</p>
				</div>

				<!-- Invoices List -->
				<div v-else class="flex flex-col gap-2 sm:flex flex-col gap-3 max-h-[60vh] sm:max-h-96 overflow-y-auto">
					<div
						v-for="invoice in invoices"
						:key="invoice.id"
						class="border border-gray-200 rounded-lg p-3 sm:p-4 hover:bg-gray-50 transition-colors"
					>
						<div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
							<div class="flex-1 min-w-0">
								<div class="flex flex-wrap items-center gap-2">
									<h4 class="font-semibold text-gray-900 text-sm sm:text-base truncate">
										{{ invoice.data.customer || __('Walk-in Customer') }}
									</h4>
									<span
										v-if="invoice.retry_count > 0"
										class="text-[10px] sm:text-xs px-2 py-0.5 sm:py-1 bg-red-100 text-red-700 rounded-full flex-shrink-0"
									>
										{{ __('{0} failed', [invoice.retry_count]) }}
									</span>
								</div>
								<div class="mt-2 flex flex-col gap-1 text-xs sm:text-sm text-gray-600">
									<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
										<span>{{ __('{0} items', [invoice.data.items?.length || 0]) }}</span>
										<span class="font-semibold text-gray-900">
											{{ formatCurrency(invoice.data.grand_total || 0) }}
										</span>
										<span class="text-[10px] sm:text-xs text-gray-500">
											{{ formatDate(invoice.timestamp) }}
										</span>
									</div>
									<div v-if="invoice.data.payments?.length > 0" class="flex flex-wrap items-center gap-2">
										<span class="text-[10px] sm:text-xs text-gray-500">{{ __('Payments:') }}</span>
										<span
											v-for="(payment, idx) in invoice.data.payments"
											:key="idx"
											class="text-[10px] sm:text-xs px-2 py-0.5 bg-gray-100 rounded"
										>
											{{ payment.mode_of_payment }}: {{ formatCurrency(payment.amount) }}
										</span>
									</div>
								</div>
							</div>
							<div class="flex items-center justify-end sm:justify-start gap-1 sm:gap-2">
								<button
									@click="editInvoice(invoice)"
									class="p-1.5 sm:p-2 hover:bg-blue-50 rounded-lg transition-colors touch-manipulation"
									:title="__('Edit Invoice')"
								>
									<svg class="w-4 h-4 sm:w-5 sm:h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
									</svg>
								</button>
								<button
									@click="viewDetails(invoice)"
									class="p-1.5 sm:p-2 hover:bg-gray-100 rounded-lg transition-colors touch-manipulation"
									:title="__('View Details')"
								>
									<svg class="w-4 h-4 sm:w-5 sm:h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
									</svg>
								</button>
								<button
									@click="deleteInvoice(invoice)"
									class="p-1.5 sm:p-2 hover:bg-red-50 rounded-lg transition-colors touch-manipulation"
									:title="__('Delete')"
								>
									<svg class="w-4 h-4 sm:w-5 sm:h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
									</svg>
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</template>
	</Dialog>

	<!-- Details Dialog -->
	<Dialog v-model="showDetails" :options="{ title: __('Invoice Details'), size: 'lg' }">
		<template #body-content>
			<div v-if="selectedInvoice" class="flex flex-col gap-3 sm:flex flex-col gap-4">
				<div class="bg-gray-50 p-3 sm:p-4 rounded-lg">
					<h4 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">{{ __('Customer') }}</h4>
					<p class="text-sm sm:text-base">{{ selectedInvoice.data.customer || __('Walk-in Customer') }}</p>
				</div>

				<div class="bg-gray-50 p-3 sm:p-4 rounded-lg">
					<h4 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">{{ __('Items') }}</h4>
					<div class="flex flex-col gap-2">
						<div
							v-for="(item, idx) in selectedInvoice.data.items"
							:key="idx"
							class="flex justify-between text-xs sm:text-sm gap-2"
						>
							<span class="truncate">{{ item.item_name || item.item_code }} × {{ item.quantity || item.qty }}</span>
							<span class="font-semibold flex-shrink-0">{{ formatCurrency(item.amount || 0) }}</span>
						</div>
					</div>
				</div>

				<div class="bg-gray-50 p-3 sm:p-4 rounded-lg">
					<div class="flex justify-between mb-1 text-xs sm:text-sm">
						<span class="text-gray-600">{{ __('Subtotal') }}</span>
						<span>{{ formatCurrency(selectedInvoice.data.total || 0) }}</span>
					</div>
					<div v-if="selectedInvoice.data.total_tax" class="flex justify-between mb-1 text-xs sm:text-sm">
						<span class="text-gray-600">{{ __('Tax') }}</span>
						<span>{{ formatCurrency(selectedInvoice.data.total_tax) }}</span>
					</div>
					<div v-if="selectedInvoice.data.total_discount" class="flex justify-between mb-1 text-xs sm:text-sm">
						<span class="text-gray-600">{{ __('Discount') }}</span>
						<span class="text-red-600">-{{ formatCurrency(selectedInvoice.data.total_discount) }}</span>
					</div>
					<div class="flex justify-between font-semibold text-base sm:text-lg pt-2 border-t">
						<span>{{ __('Grand Total') }}</span>
						<span>{{ formatCurrency(selectedInvoice.data.grand_total || 0) }}</span>
					</div>
				</div>

				<div v-if="selectedInvoice.data.payments?.length > 0" class="bg-gray-50 p-3 sm:p-4 rounded-lg">
					<h4 class="font-semibold text-gray-900 mb-2 text-sm sm:text-base">{{ __('Payments') }}</h4>
					<div class="flex flex-col gap-1">
						<div
							v-for="(payment, idx) in selectedInvoice.data.payments"
							:key="idx"
							class="flex justify-between text-xs sm:text-sm"
						>
							<span>{{ payment.mode_of_payment }}</span>
							<span class="font-semibold">{{ formatCurrency(payment.amount) }}</span>
						</div>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="showDetails = false" class="w-full sm:w-auto">{{ __('Close') }}</Button>
		</template>
	</Dialog>

	<!-- Delete Confirmation Dialog -->
	<Dialog v-model="showDeleteConfirm" :options="{ title: __('Delete Offline Invoice'), size: 'md' }">
		<template #body-content>
			<div v-if="invoiceToDelete" class="flex flex-col gap-3 sm:flex flex-col gap-4">
				<div class="flex items-start gap-2 sm:gap-3">
					<svg class="w-5 h-5 sm:w-6 sm:h-6 text-red-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
					</svg>
					<div class="min-w-0 flex-1">
						<p class="text-gray-900 font-medium mb-2 text-sm sm:text-base">{{ __('Are you sure you want to delete this offline invoice?') }}</p>
						<div class="bg-gray-50 rounded-lg p-2.5 sm:p-3 flex flex-col gap-1 text-xs sm:text-sm">
							<div class="flex justify-between gap-2">
								<span class="text-gray-600">{{ __('Customer:') }}</span>
								<span class="font-semibold truncate">{{ invoiceToDelete.data.customer || __('Walk-in Customer') }}</span>
							</div>
							<div class="flex justify-between gap-2">
								<span class="text-gray-600">{{ __('Amount:') }}</span>
								<span class="font-semibold">{{ formatCurrency(invoiceToDelete.data.grand_total) }}</span>
							</div>
							<div class="flex justify-between gap-2">
								<span class="text-gray-600">{{ __('Items:') }}</span>
								<span class="font-semibold">{{ invoiceToDelete.data.items?.length || 0 }}</span>
							</div>
						</div>
						<p class="text-red-600 text-xs sm:text-sm mt-3">{{ __('This action cannot be undone.') }}</p>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="showDeleteConfirm = false" class="w-full sm:w-auto">{{ __('Cancel') }}</Button>
			<Button variant="solid" theme="red" @click="confirmDelete" class="w-full sm:w-auto">{{ __('Delete Invoice') }}</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Button, Dialog } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	isOffline: {
		type: Boolean,
		default: false,
	},
	pendingInvoices: {
		type: Array,
		default: () => [],
	},
	isSyncing: {
		type: Boolean,
		default: false,
	},
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits([
	"update:modelValue",
	"sync-all",
	"delete-invoice",
	"edit-invoice",
	"refresh",
])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const loading = ref(false)
const invoices = ref([])
const selectedInvoice = ref(null)
const showDetails = ref(false)
const showDeleteConfirm = ref(false)
const invoiceToDelete = ref(null)

// Load invoices when dialog opens
watch(show, async (newVal) => {
	if (newVal) {
		await loadInvoices()
	}
})

// Watch for prop changes (e.g., after delete or sync)
watch(() => props.pendingInvoices, (newInvoices) => {
	invoices.value = newInvoices
})

async function loadInvoices() {
	loading.value = true
	try {
		// Get invoices from parent component
		invoices.value = props.pendingInvoices
	} catch (error) {
		console.error("Error loading offline invoices:", error)
	} finally {
		loading.value = false
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(amount, props.currency)
}

function formatDate(timestamp) {
	const date = new Date(timestamp)
	const now = new Date()
	const diffInSeconds = Math.floor((now - date) / 1000)

	if (diffInSeconds < 60) return __("Just now")
	if (diffInSeconds < 3600)
		return __('{0} minutes ago', [Math.floor(diffInSeconds / 60)])
	if (diffInSeconds < 86400)
		return __('{0} hours ago', [Math.floor(diffInSeconds / 3600)])

	return date.toLocaleDateString() + " " + date.toLocaleTimeString()
}

function viewDetails(invoice) {
	selectedInvoice.value = invoice
	showDetails.value = true
}

function editInvoice(invoice) {
	emit("edit-invoice", invoice)
	show.value = false
}

function syncAll() {
	emit("sync-all")
}

function deleteInvoice(invoice) {
	invoiceToDelete.value = invoice
	showDeleteConfirm.value = true
}

async function confirmDelete() {
	if (invoiceToDelete.value) {
		// Close dialog immediately for better UX
		showDeleteConfirm.value = false
		const invoiceId = invoiceToDelete.value.id
		invoiceToDelete.value = null

		// Emit the delete event and let parent handle the refresh
		// The watcher on pendingInvoices will update the list automatically
		emit("delete-invoice", invoiceId)
	}
}
</script>
