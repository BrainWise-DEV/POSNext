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
							@input="searchInvoices"
						>
							<template #prefix>
								<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
								</svg>
							</template>
						</Input>
					</div>
					<Button
						variant="subtle"
						@click="loadInvoices"
						:loading="invoicesResource.loading"
						:title="__('Refresh')"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
						</svg>
					</Button>
				</div>

				<!-- Invoices List -->
				<div v-if="invoicesResource.loading" class="text-center py-8">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
					<p class="mt-3 text-xs text-gray-500">{{ __('Loading invoices...') }}</p>
				</div>

				<div v-else-if="filteredInvoices.length === 0" class="text-center py-8">
					<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
					</svg>
					<p class="mt-2 text-sm text-gray-500">{{ __('No invoices found') }}</p>
				</div>

				<div v-else class="flex flex-col gap-2 max-h-96 overflow-y-auto pe-2">
					<div
						v-for="invoice in filteredInvoices"
						:key="invoice.name"
						class="bg-white border border-gray-200 rounded-lg p-3 hover:shadow-md transition-all"
					>
						<div class="flex items-start justify-between gap-3">
							<!-- Invoice Info (Start Side) -->
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2 mb-1 flex-wrap">
									<h4 class="text-sm font-semibold text-gray-900">
										{{ invoice.name }}
									</h4>
									<!-- Show Return badge (red) if it's a return invoice -->
									<span
										v-if="invoice.is_return"
										class="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-800"
									>
										{{ __('Return') }}
									</span>
									<!-- Otherwise show regular status badge -->
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
									<button
										@click="viewInvoice(invoice)"
										class="p-1.5 hover:bg-blue-50 rounded transition-colors"
										:title="__('View Details')"
									>
										<svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
										</svg>
									</button>
									<button
										@click="printInvoice(invoice)"
										class="p-1.5 hover:bg-green-50 rounded transition-colors"
										:title="__('Print')"
									>
										<svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
										</svg>
									</button>
									<button
										v-if="canCreateReturn(invoice)"
										@click="openReturnModal(invoice)"
										class="p-1.5 hover:bg-orange-50 rounded transition-colors"
										:title="__('Create Return')"
									>
										<svg class="w-4 h-4 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
										</svg>
									</button>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Load More -->
				<div v-if="hasMore && !invoicesResource.loading" class="text-center">
					<Button variant="subtle" @click="loadMore">
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

const show = ref(props.modelValue)
const invoices = ref([])
const searchTerm = ref("")
const page = ref(0)
const pageSize = 20
const hasMore = ref(true)

// Return dialog state
const showReturnDialog = ref(false)
const selectedInvoiceForReturn = ref(null)

// Track if we're loading more (appending) vs fresh load (replacing)
const isLoadingMore = ref(false)

// Create resource for loading invoices
const invoicesResource = createResource({
	url: "frappe.client.get_list",
	makeParams() {
		return {
			doctype: "Sales Invoice",
			filters: {
				is_pos: 1,
				...(props.posProfile && { pos_profile: props.posProfile }),
			},
			fields: [
				"name",
				"customer",
				"customer_name",
				"posting_date",
				"posting_time",
				"grand_total",
				"status",
				"docstatus",
				"is_return",
			],
			order_by: "modified desc",
			start: page.value * pageSize,
			page_length: pageSize,
		}
	},
	auto: false,
	onSuccess(data) {
		if (data && Array.isArray(data)) {
			const newInvoices = data.map((inv) => ({
				...inv,
				items_count: 0,
			}))

			if (isLoadingMore.value) {
				// Append to existing list
				invoices.value = [...invoices.value, ...newInvoices]
			} else {
				// Replace the list
				invoices.value = newInvoices
			}

			// Check if there are more results
			hasMore.value = data.length === pageSize
			isLoadingMore.value = false
		}
	},
	onError(error) {
		console.error("Error loading invoices:", error)
		showError(__("Failed to load invoices"))
		isLoadingMore.value = false
	},
})

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val && props.posProfile) {
			invoicesResource.reload()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Clear selected invoice when return dialog closes
watch(showReturnDialog, (val) => {
	if (!val) {
		selectedInvoiceForReturn.value = null
	}
})

const filteredInvoices = computed(() => {
	if (!searchTerm.value) return invoices.value

	const term = searchTerm.value.toLowerCase()
	return invoices.value.filter(
		(inv) =>
			inv.name.toLowerCase().includes(term) ||
			inv.customer_name?.toLowerCase().includes(term),
	)
})

function loadInvoices() {
	if (props.posProfile) {
		// Reset to first page for fresh load
		page.value = 0
		isLoadingMore.value = false
		invoicesResource.reload()
	}
}

function loadMore() {
	page.value++
	isLoadingMore.value = true
	invoicesResource.reload()
}

function searchInvoices() {
	// Debounced search - already filtered by computed property
}

function viewInvoice(invoice) {
	emit("view-invoice", invoice)
}

function printInvoice(invoice) {
	emit("print-invoice", invoice)
}

function canCreateReturn(invoice) {
	// Can create return if:
	// 1. Invoice is submitted (docstatus === 1)
	// 2. Not already a return invoice
	// 3. Status is not "Credit Note Issued" (already has a return)
	return invoice.docstatus === 1 && !invoice.is_return && invoice.status !== 'Credit Note Issued'
}

function openReturnModal(invoice) {
	selectedInvoiceForReturn.value = invoice
	showReturnDialog.value = true
}

function handleReturnCreated(returnInvoice) {
	// Refresh the invoice list to show updated statuses
	invoicesResource.reload()
	// Emit the event to parent
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
</script>
