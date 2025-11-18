<template>
	<Dialog
		v-model="show"
		:options="{ title: 'Invoice Details', size: '3xl' }"
	>
		<template #body-content>
			<div v-if="loading" class="text-center py-12">
				<div class="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto"></div>
				<p class="mt-3 text-sm text-gray-500">Loading invoice details...</p>
			</div>

			<div v-else-if="invoiceData" class="space-y-6">
				<!-- Invoice Header -->
				<div class="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-lg p-5 border border-indigo-100">
					<div class="flex items-start justify-between">
						<div class="flex-1">
							<div class="flex items-center space-x-3 mb-2">
								<h3 class="text-xl font-bold text-gray-900">{{ invoiceData.name }}</h3>
								<span
									v-if="invoiceData.is_return"
									class="px-3 py-1 text-xs font-semibold rounded-full bg-red-100 text-red-800"
								>
									Return Invoice
								</span>
								<span
									v-else
									:class="[
										'px-3 py-1 text-xs font-semibold rounded-full',
										getStatusClass(invoiceData.status)
									]"
								>
									{{ invoiceData.status }}
								</span>
							</div>
							<div class="grid grid-cols-2 gap-3 text-sm">
								<div>
									<span class="text-gray-600">Customer:</span>
									<span class="ml-2 font-semibold text-gray-900">{{ invoiceData.customer_name || invoiceData.customer }}</span>
								</div>
								<div>
									<span class="text-gray-600">Date:</span>
									<span class="ml-2 font-medium text-gray-900">{{ formatDate(invoiceData.posting_date) }} {{ formatTime(invoiceData.posting_time) }}</span>
								</div>
								<div v-if="invoiceData.return_against">
									<span class="text-gray-600">Return Against:</span>
									<span class="ml-2 font-medium text-gray-900">{{ invoiceData.return_against }}</span>
								</div>
							</div>
						</div>
						<div class="text-right ml-4">
							<div class="text-xs text-gray-500 mb-1">Grand Total</div>
							<div class="text-2xl font-bold text-indigo-600">
								{{ formatCurrency(invoiceData.grand_total) }}
							</div>
						</div>
					</div>
				</div>

				<!-- Items Section -->
				<div>
					<h4 class="text-sm font-semibold text-gray-700 mb-3 flex items-center">
						<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
						</svg>
						Items
					</h4>
					<div class="border border-gray-200 rounded-lg overflow-hidden">
						<table class="min-w-full divide-y divide-gray-200">
							<thead class="bg-gray-50">
								<tr>
									<th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Item</th>
									<th class="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Qty</th>
									<th class="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Rate</th>
									<th class="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Discount</th>
									<th class="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Amount</th>
								</tr>
							</thead>
							<tbody class="bg-white divide-y divide-gray-200">
								<tr v-for="(item, idx) in invoiceData.items" :key="idx" class="hover:bg-gray-50">
									<td class="px-4 py-3">
										<div class="text-sm font-medium text-gray-900">{{ item.item_name }}</div>
										<div class="text-xs text-gray-500">{{ item.item_code }}</div>
									</td>
									<td class="px-4 py-3 text-right text-sm text-gray-900">{{ item.qty }}</td>
									<td class="px-4 py-3 text-right text-sm text-gray-900">{{ formatCurrency(item.rate) }}</td>
									<td class="px-4 py-3 text-right text-sm text-gray-600">
										{{ item.discount_percentage ? `${item.discount_percentage}%` : '-' }}
									</td>
									<td class="px-4 py-3 text-right text-sm font-semibold text-gray-900">{{ formatCurrency(item.amount) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<!-- Totals Section -->
				<div class="grid grid-cols-2 gap-6">
					<!-- Payment Info -->
					<div v-if="invoiceData.payments && invoiceData.payments.length > 0">
						<h4 class="text-sm font-semibold text-gray-700 mb-3 flex items-center">
							<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/>
							</svg>
							Payments
						</h4>
						<div class="space-y-2">
							<div
								v-for="(payment, idx) in invoiceData.payments"
								:key="idx"
								class="flex justify-between items-center p-3 bg-green-50 border border-green-200 rounded-lg"
							>
								<div>
									<div class="text-sm font-medium text-gray-900">{{ payment.mode_of_payment }}</div>
									<div v-if="payment.account" class="text-xs text-gray-500">{{ payment.account }}</div>
								</div>
								<div class="text-sm font-semibold text-green-700">{{ formatCurrency(payment.amount) }}</div>
							</div>
						</div>
					</div>

					<!-- Summary -->
					<div>
						<h4 class="text-sm font-semibold text-gray-700 mb-3">Summary</h4>
						<div class="space-y-2 bg-gray-50 p-4 rounded-lg border border-gray-200">
							<div class="flex justify-between text-sm">
								<span class="text-gray-600">Net Total:</span>
								<span class="font-medium text-gray-900">{{ formatCurrency(invoiceData.net_total || invoiceData.total) }}</span>
							</div>
							<div v-if="invoiceData.total_taxes_and_charges" class="flex justify-between text-sm">
								<span class="text-gray-600">Taxes:</span>
								<span class="font-medium text-gray-900">{{ formatCurrency(invoiceData.total_taxes_and_charges) }}</span>
							</div>
							<div v-if="invoiceData.discount_amount" class="flex justify-between text-sm">
								<span class="text-gray-600">Discount:</span>
								<span class="font-medium text-red-600">-{{ formatCurrency(invoiceData.discount_amount) }}</span>
							</div>
							<div class="pt-2 border-t border-gray-300 flex justify-between">
								<span class="font-semibold text-gray-900">Grand Total:</span>
								<span class="font-bold text-lg text-indigo-600">{{ formatCurrency(invoiceData.grand_total) }}</span>
							</div>
							<div v-if="invoiceData.paid_amount" class="flex justify-between text-sm">
								<span class="text-gray-600">Paid Amount:</span>
								<span class="font-semibold text-green-600">{{ formatCurrency(invoiceData.paid_amount) }}</span>
							</div>
							<div v-if="invoiceData.outstanding_amount" class="flex justify-between text-sm">
								<span class="text-gray-600">Outstanding:</span>
								<span class="font-semibold text-orange-600">{{ formatCurrency(invoiceData.outstanding_amount) }}</span>
							</div>
						</div>
					</div>
				</div>

				<!-- Additional Info -->
				<div v-if="invoiceData.remarks" class="bg-gray-50 p-4 rounded-lg border border-gray-200">
					<h4 class="text-sm font-semibold text-gray-700 mb-2">Remarks</h4>
					<p class="text-sm text-gray-600">{{ invoiceData.remarks }}</p>
				</div>
			</div>

			<div v-else class="text-center py-12">
				<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
				</svg>
				<p class="mt-2 text-sm text-gray-500">Failed to load invoice details</p>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-between items-center w-full">
				<Button variant="subtle" @click="show = false">
					Close
				</Button>
				<Button @click="handlePrint">
					<template #prefix>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
						</svg>
					</template>
					Print
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { useFormatters } from "@/composables/useFormatters"
import { logger } from "@/utils/logger"
import { Button, Dialog, call } from "frappe-ui"
import { ref, watch, nextTick } from "vue"

const log = logger.create('InvoiceDetailDialog')
const { formatCurrency, formatDate, formatTime } = useFormatters()

const props = defineProps({
	modelValue: Boolean,
	invoiceName: String,
	posProfile: String,
})

const emit = defineEmits(["update:modelValue", "print-invoice"])

const show = ref(props.modelValue)
const loading = ref(false)
const invoiceData = ref(null)

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val && props.invoiceName) {
			loadInvoiceDetails()
		}
	},
)

watch(show, async (val) => {
	emit("update:modelValue", val)
	if (!val) {
		// Clear data when closing
		invoiceData.value = null
	} else {
		// Ensure dialog appears above other dialogs
		await nextTick()
		const dialogs = document.querySelectorAll('.modal-container, .modal-backdrop')
		dialogs.forEach(dialog => {
			const title = dialog.querySelector('[class*="title"]')
			if (title && title.textContent?.includes('Invoice Details')) {
				dialog.style.zIndex = '400'
			}
		})
	}
})

async function loadInvoiceDetails() {
	if (!props.invoiceName) return

	loading.value = true
	try {
		const result = await call("pos_next.api.invoices.get_invoice", {
			invoice_name: props.invoiceName,
		})

		invoiceData.value = result
	} catch (error) {
		log.error("Error loading invoice details:", error)
		invoiceData.value = null
	} finally {
		loading.value = false
	}
}

function getStatusClass(status) {
	switch (status) {
		case "Paid":
			return "bg-green-100 text-green-800"
		case "Unpaid":
			return "bg-yellow-100 text-yellow-800"
		case "Partly Paid":
		case "Overdue":
			return "bg-orange-100 text-orange-800"
		case "Return":
			return "bg-red-100 text-red-800"
		case "Draft":
			return "bg-gray-100 text-gray-800"
		case "Cancelled":
			return "bg-red-100 text-red-800"
		default:
			return "bg-gray-100 text-gray-800"
	}
}

function handlePrint() {
	if (!invoiceData.value) return
	emit("print-invoice", invoiceData.value)
}
</script>

