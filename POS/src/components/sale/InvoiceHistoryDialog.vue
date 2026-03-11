<template>
	<Dialog
		v-model="show"
		:options="{ title: __('Invoice History'), size: '5xl' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Filters -->
				<div class="flex items-center gap-2">
					<div class="flex-1">
						<Input
							v-model="searchTerm"
							type="text"
							:placeholder="__('Search by invoice number or customer...')"
							@input="onSearchInput"
						>
							<template #prefix>
								<!-- Search icon -->
								<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
								</svg>
							</template>
						</Input>
					</div>
					<Button
						variant="subtle"
						@click="loadInvoices"
						:loading="invoicesResource.loading && !isLoadingMore"
						:title="__('Refresh')"
					>
						<!-- RotateCcw icon -->
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
						</svg>
					</Button>
				</div>

				<!-- Error State -->
				<div
					v-if="invoicesResource.error && !invoicesResource.loading"
					class="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
				>
					<!-- AlertCircle icon -->
					<svg class="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
					</svg>
					<span>{{ __('Failed to load invoices. Please try again.') }}</span>
					<Button variant="subtle" size="sm" @click="loadInvoices" class="ml-auto">
						{{ __('Retry') }}
					</Button>
				</div>

				<!-- Skeleton Loaders (initial load only) -->
				<div v-else-if="invoicesResource.loading && !isLoadingMore" class="flex flex-col gap-2">
					<div
						v-for="n in 5"
						:key="n"
						class="rounded-lg border border-gray-100 bg-white p-3 animate-pulse"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="flex-1 space-y-2">
								<div class="flex items-center gap-2">
									<div class="h-4 w-28 rounded bg-gray-200"></div>
									<div class="h-4 w-14 rounded-full bg-gray-100"></div>
								</div>
								<div class="h-3 w-36 rounded bg-gray-100"></div>
								<div class="h-3 w-24 rounded bg-gray-100"></div>
							</div>
							<div class="flex flex-col items-end gap-2">
								<div class="h-5 w-20 rounded bg-gray-200"></div>
								<div class="flex gap-1">
									<div class="h-7 w-7 rounded bg-gray-100"></div>
									<div class="h-7 w-7 rounded bg-gray-100"></div>
									<div class="h-7 w-7 rounded bg-gray-100"></div>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Empty State -->
				<div v-else-if="isEmpty" class="flex flex-col items-center justify-center py-12 text-center">
					<!-- FileSearch icon -->
					<svg class="mx-auto h-14 w-14 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
						<circle cx="11" cy="11" r="0" stroke-width="0"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-3-3"/>
					</svg>
					<p class="mt-3 text-sm font-semibold text-gray-500">{{ __('No invoices found') }}</p>
					<p class="mt-1 text-xs text-gray-400">
						{{ __('Try adjusting your search or refresh the list.') }}
					</p>
					<Button variant="subtle" class="mt-4" @click="loadInvoices">
						{{ __('Refresh') }}
					</Button>
				</div>

				<!-- Invoices List -->
				<div v-else class="flex flex-col gap-2 max-h-96 overflow-y-auto pe-2">
					<div
						v-for="(invoice, index) in invoices"
						:key="invoice.name + invoice.posting_date"
						class="bg-white border border-gray-200 rounded-lg p-3 hover:shadow-md transition-all"
					>
						<div class="flex items-start justify-between gap-3">
							<!-- Invoice Info (Start Side) -->
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2 mb-1 flex-wrap">
									<h4 class="text-sm font-semibold text-gray-900">
										{{ invoice.name }}
									</h4>
									<!-- Return badge -->
									<span
										v-if="invoice.is_return"
										class="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-800"
									>
										{{ __('Return') }}
									</span>
									<!-- Status badge -->
									<span
										v-else
										:class="[
											'text-xs px-2 py-0.5 rounded-full font-medium',
											getInvoiceStatusColor(invoice)
										]"
									>
										{{ __(invoice.status) }}
									</span>
								</div>
								<p class="text-xs text-gray-600 text-start">{{ invoice.customer_name }}</p>
								<p class="text-xs text-gray-500 text-start">{{ formatDateTime(invoice.posting_date, invoice.posting_time) }}</p>
							</div>

							<!-- Amount & Actions (End Side) -->
							<div class="flex-shrink-0 flex flex-col items-end">
								<p class="text-sm font-bold text-gray-900 text-end">
									{{ formatCurrency(invoice.grand_total) }}
								</p>
								<div class="flex items-center gap-1 mt-2">
									<Button
										variant="ghost"
										theme="blue"
										size="sm"
										@click="viewInvoice(invoice)"
										:title="__('View Details')"
									>
										<!-- Eye icon -->
										<svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
										</svg>
									</Button>
									<Button
										variant="ghost"
										theme="green"
										size="sm"
										@click="printInvoice(invoice)"
										:title="__('Print')"
									>
										<!-- Printer icon -->
										<svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
										</svg>
									</Button>
									<Button
										v-if="canCreateReturn(invoice)"
										variant="ghost"
										theme="orange"
										size="sm"
										@click="openReturnModal(invoice)"
										:title="__('Create Return')"
									>
										<!-- RotateCcw icon -->
										<svg class="w-4 h-4 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
										</svg>
									</Button>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Load More -->
				<div v-if="hasMore && !isEmpty && !invoicesResource.error" class="text-center">
					<Button
						variant="subtle"
						@click="loadMore"
						:loading="isLoadingMore"
					>
						{{ __('Load More') }}
					</Button>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="show = false">
				{{ __('Close') }}
			</Button>
		</template>
	</Dialog>

	<!-- Return Invoice Dialog -->
	<ReturnInvoiceDialog
		v-model="showReturnDialog"
		:pos-profile="posProfile"
		:pos-opening-shift="posOpeningShift"
		:currency="currency"
		:preselected-invoice="selectedInvoiceForReturn"
		@return-created="handleReturnCreated"
	/>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { DEFAULT_CURRENCY, DEFAULT_LOCALE, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { getInvoiceStatusColor } from "@/utils/invoice"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import ReturnInvoiceDialog from "./ReturnInvoiceDialog.vue"

const { showError } = useToast()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	posOpeningShift: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

const emit = defineEmits(["update:modelValue", "create-return", "view-invoice", "print-invoice", "return-created"])

// ─── State ────────────────────────────────────────────────────────────────────
const show = ref(props.modelValue)
const invoices = ref([])
const searchTerm = ref("")
const offset = ref(0)
const LIMIT = 20
const hasMore = ref(true)
const isLoadingMore = ref(false)

// Return dialog state
const showReturnDialog = ref(false)
const selectedInvoiceForReturn = ref(null)

// ─── Computed ─────────────────────────────────────────────────────────────────
const isEmpty = computed(
	() => !invoicesResource.loading && !invoicesResource.error && invoices.value.length === 0
)

// ─── Debounce utility (no lodash needed) ─────────────────────────────────────
let _debounceTimer = null
function debounce(fn, delay) {
	return (...args) => {
		clearTimeout(_debounceTimer)
		_debounceTimer = setTimeout(() => fn(...args), delay)
	}
}

// ─── Resource ─────────────────────────────────────────────────────────────────
const invoicesResource = createResource({
	url: "pos_next.api.invoices.get_invoices",
	makeParams() {
		return {
			pos_profile: props.posProfile,
			search: searchTerm.value || null,
			limit: LIMIT,
			offset: offset.value,
		}
	},
	auto: false,
	onSuccess(data) {
		if (data && Array.isArray(data)) {
			const newInvoices = data.map((inv) => ({ ...inv }))

			if (isLoadingMore.value) {
				// Append, deduplicating by name
				const existingNames = new Set(invoices.value.map((i) => i.name))
				const unique = newInvoices.filter((i) => !existingNames.has(i.name))
				invoices.value = [...invoices.value, ...unique]
			} else {
				invoices.value = newInvoices
			}

			hasMore.value = data.length === LIMIT
		}
		isLoadingMore.value = false
	},
	onError(error) {
		console.error("Error loading invoices:", error)
		isLoadingMore.value = false
	},
})

// ─── Actions ─────────────────────────────────────────────────────────────────
function loadInvoices() {
	if (!props.posProfile) return
	offset.value = 0
	isLoadingMore.value = false
	invoicesResource.reload()
}

function loadMore() {
	if (!props.posProfile || !hasMore.value) return
	offset.value += LIMIT
	isLoadingMore.value = true
	invoicesResource.reload()
}

const _debouncedSearch = debounce(() => {
	loadInvoices()
}, 300)

function onSearchInput() {
	_debouncedSearch()
}

function viewInvoice(invoice) {
	emit("view-invoice", invoice)
}

function printInvoice(invoice) {
	emit("print-invoice", invoice)
}

function canCreateReturn(invoice) {
	return invoice.docstatus === 1 && !invoice.is_return && invoice.status !== "Credit Note Issued"
}

function openReturnModal(invoice) {
	selectedInvoiceForReturn.value = invoice
	showReturnDialog.value = true
}

function handleReturnCreated(returnInvoice) {
	loadInvoices()
	emit("return-created", returnInvoice)
}

function formatDateTime(date, time) {
	const dateStr = new Date(date).toLocaleDateString(DEFAULT_LOCALE, {
		month: "short",
		day: "numeric",
		year: "numeric",
	})
	if (time) {
		return `${dateStr} ${time}`
	}
	return dateStr
}

// ─── Watchers ─────────────────────────────────────────────────────────────────
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val && props.posProfile) {
			loadInvoices()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
	// Dialog cleanup: reset state when dialog closes
	if (!val) {
		searchTerm.value = ""
		offset.value = 0
		invoices.value = []
		hasMore.value = true
	}
})

// Clear selected invoice when return dialog closes
watch(showReturnDialog, (val) => {
	if (!val) {
		selectedInvoiceForReturn.value = null
	}
})
</script>
