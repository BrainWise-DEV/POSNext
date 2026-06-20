<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<div class="fixed inset-0 flex items-center justify-center p-4">
				<div class="w-full h-full max-w-[95vw] max-h-[95vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">

					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-orange-50 to-amber-50 flex-shrink-0">
						<div class="flex items-center gap-3">
							<div class="p-2 bg-orange-100 rounded-lg">
								<svg class="w-6 h-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">{{ __('Customer Account') }}</h2>
								<p class="text-sm text-gray-600 mt-0.5">
									{{ customerName || customer }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<button
								type="button"
								@click="loadStatement"
								:disabled="loading"
								class="p-2 text-gray-500 hover:bg-gray-100 active:bg-gray-200 rounded-lg transition-colors"
								:title="__('Refresh')"
							>
								<svg class="w-5 h-5" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
								</svg>
							</button>
							<button
								type="button"
								@click="handleClose"
								class="p-2 text-gray-500 hover:bg-gray-100 active:bg-gray-200 rounded-lg transition-colors"
								:title="__('Close')"
							>
								<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Offline banner -->
					<div v-if="isOffline()" class="px-6 py-2 bg-yellow-50 border-b border-yellow-200 flex items-center gap-2 text-sm text-yellow-800 flex-shrink-0">
						<svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
						</svg>
						{{ __('You are offline. Payments are disabled.') }}
					</div>

					<!-- Body -->
					<div class="flex-1 overflow-y-auto">

						<!-- Skeleton -->
						<div v-if="loading" class="p-6 space-y-4">
							<div class="grid grid-cols-3 gap-4">
								<div v-for="i in 3" :key="i" class="bg-gray-100 rounded-xl h-20 animate-pulse"/>
							</div>
							<div class="space-y-3 mt-6">
								<div v-for="i in 4" :key="i" class="bg-gray-100 rounded-xl h-16 animate-pulse"/>
							</div>
						</div>

						<!-- Content -->
						<div v-else-if="statement" class="p-6 space-y-6">

							<!-- Tab switcher -->
							<div class="flex p-1 bg-gray-200 rounded-lg">
								<button
									type="button"
									@click="activeTab = 'statement'"
									class="flex-1 px-4 py-2 text-sm font-semibold rounded-md transition-colors"
									:class="activeTab === 'statement' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'"
								>
									{{ __('Statement') }}
								</button>
								<button
									type="button"
									@click="activeTab = 'items'"
									class="flex-1 px-4 py-2 text-sm font-semibold rounded-md transition-colors"
									:class="activeTab === 'items' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'"
								>
									{{ __('Items on Credit') }}
								</button>
							</div>

							<!-- Statement panel -->
							<div v-if="activeTab === 'statement'" class="space-y-6">

							<!-- Summary strip -->
							<div class="grid grid-cols-3 gap-4">
								<!-- Total Due -->
								<div class="bg-orange-50 border border-orange-200 rounded-xl p-4 text-center">
									<div class="text-xs font-medium text-orange-600 mb-1">{{ __('Total Due') }}</div>
									<div class="text-lg font-bold text-orange-700">{{ formatCurrency(statement.summary.total_outstanding) }}</div>
									<div class="text-xs text-orange-500 mt-0.5">{{ __('{0} invoice(s)', [statement.summary.due_count]) }}</div>
								</div>
								<!-- Credit -->
								<div class="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
									<div class="text-xs font-medium text-green-600 mb-1">{{ __('Return Credit') }}</div>
									<div class="text-lg font-bold text-green-700">{{ formatCurrency(statement.summary.total_credit) }}</div>
									<div class="text-xs text-green-500 mt-0.5">{{ __('From returns') }}</div>
								</div>
								<!-- Net Balance (dominant) -->
								<div
									class="rounded-xl p-4 text-center border-2"
									:class="statement.summary.net_balance > 0
										? 'bg-orange-50 border-orange-300'
										: 'bg-green-50 border-green-300'"
								>
									<div class="text-xs font-medium mb-1" :class="statement.summary.net_balance > 0 ? 'text-orange-600' : 'text-green-600'">
										{{ __('Net Balance') }}
									</div>
									<div class="text-2xl font-bold" :class="statement.summary.net_balance > 0 ? 'text-orange-700' : 'text-green-700'">
										{{ formatCurrency(Math.abs(statement.summary.net_balance)) }}
									</div>
									<div class="text-xs mt-0.5" :class="statement.summary.net_balance > 0 ? 'text-orange-500' : 'text-green-500'">
										{{ statement.summary.net_balance > 0 ? __('Owes') : __('In credit') }}
									</div>
								</div>
							</div>

							<!-- Pay Due button -->
							<div class="flex justify-end" v-if="statement.summary.total_outstanding > 0">
								<button
									type="button"
									@click="openLumpSumPayment"
									:disabled="isOffline() || payingLump"
									class="px-6 py-2.5 bg-orange-500 text-white rounded-lg hover:bg-orange-600 active:bg-orange-700 transition-colors font-semibold text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
								>
									<LoadingIndicator v-if="payingLump" class="w-4 h-4"/>
									<svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
									</svg>
									{{ __('Pay Due ({0})', [formatCurrency(statement.summary.total_outstanding)]) }}
								</button>
							</div>

							<!-- Empty / all settled -->
							<div
								v-if="statement.summary.total_outstanding === 0 && statement.due_invoices.length === 0"
								class="text-center py-10"
							>
								<div class="text-5xl mb-3">✓</div>
								<p class="text-lg font-semibold text-green-700">{{ __('All Settled') }}</p>
								<p class="text-sm text-gray-500 mt-1">{{ __('This customer has no outstanding balance.') }}</p>
								<p v-if="statement.summary.total_credit > 0" class="text-sm text-green-600 mt-1 font-medium">
									{{ __('Credit available: {0}', [formatCurrency(statement.summary.total_credit)]) }}
								</p>
							</div>

							<!-- Filter chips -->
							<div v-if="allInvoices.length > 0" class="flex flex-wrap gap-2">
								<button
									v-for="chip in filterChips"
									:key="chip.value"
									type="button"
									@click="activeFilter = chip.value"
									class="px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors"
									:class="activeFilter === chip.value
										? 'bg-orange-500 text-white border-orange-500'
										: 'bg-white text-gray-600 border-gray-300 hover:border-orange-300 hover:text-orange-600'"
								>
									{{ chip.label }}
								</button>
							</div>

							<!-- Invoice list -->
							<div v-if="filteredInvoices.length > 0" class="space-y-3">
								<div
									v-for="invoice in filteredInvoices"
									:key="invoice.name"
									class="bg-white border rounded-xl overflow-hidden shadow-sm"
									:class="getInvoiceBorderClass(invoice)"
								>
									<!-- Invoice row -->
									<div
										class="p-4 cursor-pointer hover:bg-gray-50 transition-colors"
										@click="toggleInvoice(invoice.name)"
									>
										<div class="flex items-start justify-between gap-4">
											<div class="flex-1 min-w-0">
												<div class="flex items-center gap-2 flex-wrap">
													<span class="text-sm font-bold text-gray-900">{{ invoice.name }}</span>
													<span
														class="px-2 py-0.5 text-xs font-semibold rounded-full"
														:class="getStatusBadgeClass(invoice)"
													>{{ __(invoice.is_return ? 'Return' : invoice.status) }}</span>
												</div>
												<div class="flex items-center gap-3 mt-1 text-xs text-gray-500">
													<span>{{ formatDate(invoice.posting_date) }}</span>
													<span v-if="invoice.return_against">{{ __('vs {0}', [invoice.return_against]) }}</span>
												</div>
											</div>
											<div class="text-end flex-shrink-0">
												<div class="text-sm font-bold" :class="invoice.is_return ? 'text-red-600' : 'text-gray-900'">
													{{ invoice.is_return ? '-' : '' }}{{ formatCurrency(Math.abs(invoice.grand_total)) }}
												</div>
												<div v-if="!invoice.is_return" class="text-xs text-gray-500 mt-0.5">
													{{ __('Due: {0}', [formatCurrency(invoice.outstanding_amount)]) }}
												</div>
												<!-- Progress bar -->
												<div v-if="!invoice.is_return && invoice.grand_total > 0" class="w-24 h-1 bg-gray-200 rounded-full mt-1.5 ms-auto">
													<div
														class="h-full rounded-full transition-all"
														:class="invoice.outstanding_amount > 0 ? 'bg-orange-400' : 'bg-green-500'"
														:style="{ width: Math.round(Math.max(0, 1 - invoice.outstanding_amount / invoice.grand_total) * 100) + '%' }"
													/>
												</div>
											</div>
											<svg
												class="w-4 h-4 text-gray-400 flex-shrink-0 transition-transform mt-1"
												:class="expandedInvoices.has(invoice.name) ? 'rotate-180' : ''"
												fill="none" stroke="currentColor" viewBox="0 0 24 24"
											>
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
											</svg>
										</div>
									</div>

									<!-- Expanded detail -->
									<div v-if="expandedInvoices.has(invoice.name)" class="border-t bg-gray-50 px-4 py-3 space-y-3">

										<!-- Items table -->
										<div v-if="invoice.items && invoice.items.length">
											<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{{ __('Items') }}</div>
											<table class="w-full text-xs">
												<thead>
													<tr class="text-gray-500">
														<th class="text-start pb-1 font-medium">{{ __('Item') }}</th>
														<th class="text-end pb-1 font-medium">{{ __('Qty') }}</th>
														<th class="text-end pb-1 font-medium">{{ __('Rate') }}</th>
														<th class="text-end pb-1 font-medium">{{ __('Amount') }}</th>
													</tr>
												</thead>
												<tbody class="divide-y divide-gray-100">
													<tr v-for="item in invoice.items" :key="item.item_code" class="text-gray-700">
														<td class="py-1 pe-2 truncate max-w-[140px]" :title="item.item_name">{{ item.item_name }}</td>
														<td class="py-1 text-end">{{ item.qty }} {{ item.uom }}</td>
														<td class="py-1 text-end">{{ formatCurrency(item.rate) }}</td>
														<td class="py-1 text-end font-medium">{{ formatCurrency(item.amount) }}</td>
													</tr>
												</tbody>
											</table>
										</div>

										<!-- Payment history chips -->
										<div v-if="invoice.payments && invoice.payments.length">
											<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{{ __('Payment History') }}</div>
											<div class="flex flex-wrap gap-2">
												<div
													v-for="(payment, idx) in invoice.payments"
													:key="idx"
													class="flex items-center gap-1.5 px-2.5 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium"
												>
													<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
													</svg>
													{{ formatCurrency(payment.amount) }} · {{ payment.mode_of_payment || payment.payment_type }}
												</div>
											</div>
										</div>

										<!-- Row actions -->
										<div class="flex items-center gap-2 pt-1">
											<button
												v-if="!invoice.is_return && invoice.outstanding_amount > 0"
												type="button"
												@click.stop="openSingleInvoicePayment(invoice)"
												:disabled="isOffline()"
												class="px-3 py-1.5 text-xs font-semibold bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
											>
												<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
												</svg>
												{{ __('Pay') }}
											</button>
											<button
												type="button"
												@click.stop="$emit('print-invoice', invoice)"
												class="px-3 py-1.5 text-xs font-semibold bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-1"
											>
												<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
												</svg>
												{{ __('Print') }}
											</button>
										</div>
									</div>
								</div>
							</div>

							<!-- No results for filter -->
							<div v-else-if="allInvoices.length > 0" class="text-center py-8 text-gray-400 text-sm">
								{{ __('No invoices match the selected filter.') }}
							</div>
							</div>

							<!-- Items on Credit panel -->
							<div v-else-if="activeTab === 'items'" class="space-y-4">

								<!-- Headline -->
								<div class="bg-orange-50 border-2 border-orange-300 rounded-xl p-4 text-center">
									<div class="text-xs font-medium text-orange-600 mb-1">{{ __('Total owed: {0}', [formatCurrency(statement.summary.net_balance)]) }}</div>
									<div class="text-sm text-gray-600">
										{{ __('{0} took {1} item(s) on credit', [customerName || customer, creditItems.length]) }}
									</div>
								</div>

								<!-- Items table -->
								<div v-if="creditItems.length > 0" class="bg-white border border-gray-200 rounded-xl overflow-hidden">
									<table class="w-full text-sm">
										<thead>
											<tr class="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
												<th class="text-start px-4 py-2.5 font-medium">{{ __('Item') }}</th>
												<th class="text-end px-4 py-2.5 font-medium">{{ __('Qty') }}</th>
												<th class="text-end px-4 py-2.5 font-medium">{{ __('Amount') }}</th>
											</tr>
										</thead>
										<tbody class="divide-y divide-gray-100">
											<tr v-for="item in creditItems" :key="item.item_code" class="text-gray-700">
												<td class="px-4 py-2.5 truncate max-w-[200px]" :title="item.item_name">{{ item.item_name }}</td>
												<td class="px-4 py-2.5 text-end whitespace-nowrap">{{ item.total_qty }} {{ item.uom }}</td>
												<td class="px-4 py-2.5 text-end font-semibold whitespace-nowrap">{{ formatCurrency(item.total_amount) }}</td>
											</tr>
										</tbody>
									</table>
								</div>

								<!-- Empty state -->
								<div v-else class="text-center py-10 text-gray-400">
									<div class="text-4xl mb-2">📦</div>
									<p class="text-sm">{{ __('No items on credit.') }}</p>
								</div>
							</div>
						</div>

						<!-- Error state -->
						<div v-else class="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
							<svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
							</svg>
							<p>{{ __('Failed to load account statement. Try refreshing.') }}</p>
							<button type="button" @click="loadStatement" class="text-orange-600 text-sm font-semibold hover:underline">
								{{ __('Retry') }}
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>

	<!-- Lump-sum PaymentDialog -->
	<PaymentDialog
		v-model="showLumpSumPayment"
		:grand-total="statement?.summary.total_outstanding || 0"
		:subtotal="statement?.summary.total_outstanding || 0"
		:customer="customerName || customer"
		:pos-profile="posProfile"
		:currency="currency"
		:is-offline="false"
		:allow-partial-payment="true"
		@payment-completed="handleLumpSumCompleted"
	/>

	<!-- Single-invoice PaymentDialog -->
	<PaymentDialog
		v-model="showSinglePayment"
		:grand-total="selectedSingleInvoice?.outstanding_amount || 0"
		:subtotal="selectedSingleInvoice?.grand_total || 0"
		:items="selectedSingleInvoice?.items || []"
		:customer="customerName || customer"
		:pos-profile="posProfile"
		:currency="currency"
		:is-offline="false"
		:allow-partial-payment="true"
		@payment-completed="handleSinglePaymentCompleted"
	/>
</template>

<script setup>
import PaymentDialog from "@/components/sale/PaymentDialog.vue"
import { useDialogSubmit } from "@/composables/useDialogSubmit"
import { useToast } from "@/composables/useToast"
import { useShift } from "@/composables/useShift"
import {
	DEFAULT_CURRENCY,
	formatCurrency as formatCurrencyUtil,
} from "@/utils/currency"
import { isOffline } from "@/utils/offline/offlineState"
import { call, LoadingIndicator } from "frappe-ui"
import { computed, ref, watch } from "vue"
import { __ } from "@/utils/translation"

const props = defineProps({
	modelValue: Boolean,
	customer: {
		type: [String, Object],
		default: null,
	},
	posProfile: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	company: {
		type: String,
		default: "",
	},
})

const emit = defineEmits([
	"update:modelValue",
	"print-invoice",
	"payment-completed",
])

const { showSuccess, showError } = useToast()
const { currentShift } = useShift()

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const loading = ref(false)
const payingLump = ref(false)

// Enter or Ctrl/Cmd+S opens the lump-sum (pay all dues) payment.
useDialogSubmit({
	isOpen: show,
	onSubmit: () => openLumpSumPayment(),
	canSubmit: () => !isOffline() && !payingLump.value,
})
const statement = ref(null)
const expandedInvoices = ref(new Set())
const activeFilter = ref("all")
const activeTab = ref("statement")
const showLumpSumPayment = ref(false)
const showSinglePayment = ref(false)
const selectedSingleInvoice = ref(null)

const customerName = computed(() => {
	if (typeof props.customer === "object" && props.customer) {
		return props.customer.customer_name || props.customer.name
	}
	return props.customer
})

const customerId = computed(() => {
	if (typeof props.customer === "object" && props.customer) {
		return props.customer.name || props.customer.customer_name
	}
	return props.customer
})

const allInvoices = computed(() => {
	if (!statement.value) return []
	return [
		...(statement.value.due_invoices || []),
		...(statement.value.settled_invoices || []),
	]
})

const filterChips = computed(() => [
	{ value: "all", label: __("All ({0})", [allInvoices.value.length]) },
	{
		value: "unpaid",
		label: __("Unpaid ({0})", [
			allInvoices.value.filter((i) => i.status === "Unpaid" && !i.is_return)
				.length,
		]),
	},
	{
		value: "partly_paid",
		label: __("Partly Paid ({0})", [
			allInvoices.value.filter((i) => i.status === "Partly Paid").length,
		]),
	},
	{
		value: "overdue",
		label: __("Overdue ({0})", [
			allInvoices.value.filter((i) => i.status === "Overdue").length,
		]),
	},
	{
		value: "paid",
		label: __("Paid ({0})", [
			allInvoices.value.filter(
				(i) =>
					i.status === "Paid" || (i.outstanding_amount <= 0 && !i.is_return),
			).length,
		]),
	},
])

const filteredInvoices = computed(() => {
	const all = allInvoices.value
	switch (activeFilter.value) {
		case "unpaid":
			return all.filter((i) => i.status === "Unpaid" && !i.is_return)
		case "partly_paid":
			return all.filter((i) => i.status === "Partly Paid")
		case "overdue":
			return all.filter((i) => i.status === "Overdue")
		case "paid":
			return all.filter(
				(i) =>
					i.status === "Paid" || (i.outstanding_amount <= 0 && !i.is_return),
			)
		default:
			return all
	}
})

// Aggregate due-invoice line items, grouped by item, for the "Items on Credit" tab.
const creditItems = computed(() => {
	if (!statement.value) return []
	const byItem = new Map()
	for (const inv of statement.value.due_invoices || []) {
		for (const item of inv.items || []) {
			const key = item.item_code
			const existing = byItem.get(key)
			if (existing) {
				existing.total_qty += Number.parseFloat(item.qty || 0)
				existing.total_amount += Number.parseFloat(item.amount || 0)
			} else {
				byItem.set(key, {
					item_code: item.item_code,
					item_name: item.item_name,
					uom: item.uom,
					total_qty: Number.parseFloat(item.qty || 0),
					total_amount: Number.parseFloat(item.amount || 0),
				})
			}
		}
	}
	return [...byItem.values()].sort((a, b) => b.total_amount - a.total_amount)
})

watch(
	() => props.modelValue,
	(val) => {
		if (val) {
			statement.value = null
			expandedInvoices.value = new Set()
			activeFilter.value = "all"
			activeTab.value = "statement"
			loadStatement()
		}
	},
)

async function loadStatement() {
	if (!customerId.value) return
	loading.value = true
	try {
		const result = await call(
			"pos_next.api.customer_dues.get_customer_due_statement",
			{
				customer: customerId.value,
				pos_profile: props.posProfile || undefined,
				company: props.company || undefined,
			},
		)
		statement.value = result
	} catch (error) {
		showError(error.message || __("Failed to load account statement"))
		statement.value = null
	} finally {
		loading.value = false
	}
}

function toggleInvoice(name) {
	const next = new Set(expandedInvoices.value)
	if (next.has(name)) {
		next.delete(name)
	} else {
		next.add(name)
	}
	expandedInvoices.value = next
}

function openLumpSumPayment() {
	showLumpSumPayment.value = true
}

function openSingleInvoicePayment(invoice) {
	selectedSingleInvoice.value = invoice
	showSinglePayment.value = true
}

async function handleLumpSumCompleted(paymentData) {
	payingLump.value = true
	try {
		const result = await call("pos_next.api.customer_dues.pay_customer_due", {
			customer: customerId.value,
			payments: paymentData.payments,
			pos_profile: props.posProfile || undefined,
			pos_opening_shift: currentShift.value?.name || undefined,
			company: props.company || undefined,
		})
		const count = result.allocations?.length || 0
		const invCount = new Set(result.allocations?.map((a) => a.invoice)).size
		showSuccess(
			__("Paid {0} allocation(s) across {1} invoice(s)", [count, invCount]),
		)
		// Refresh statement
		statement.value = null
		await loadStatement()
		emit("payment-completed")
	} catch (error) {
		showError(error.message || __("Payment failed"))
	} finally {
		payingLump.value = false
	}
}

async function handleSinglePaymentCompleted(paymentData) {
	if (!selectedSingleInvoice.value) return
	try {
		await call("pos_next.api.partial_payments.add_payment_to_partial_invoice", {
			invoice_name: selectedSingleInvoice.value.name,
			payments: paymentData.payments,
			pos_opening_shift: currentShift.value?.name || undefined,
		})
		showSuccess(__("Payment added to {0}", [selectedSingleInvoice.value.name]))
		selectedSingleInvoice.value = null
		await loadStatement()
		emit("payment-completed")
	} catch (error) {
		showError(error.message || __("Payment failed"))
	}
}

function handleClose() {
	show.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function formatDate(dateStr) {
	if (!dateStr) return ""
	return new Date(dateStr).toLocaleDateString(undefined, {
		year: "numeric",
		month: "short",
		day: "numeric",
	})
}

function getInvoiceBorderClass(invoice) {
	if (invoice.is_return) return "border-red-200"
	if (invoice.status === "Overdue") return "border-red-300"
	if (invoice.status === "Partly Paid") return "border-orange-200"
	if (invoice.status === "Unpaid") return "border-orange-200"
	return "border-gray-200"
}

function getStatusBadgeClass(invoice) {
	if (invoice.is_return) return "bg-red-100 text-red-700"
	if (invoice.status === "Overdue") return "bg-red-100 text-red-700"
	if (invoice.status === "Partly Paid") return "bg-orange-100 text-orange-700"
	if (invoice.status === "Unpaid") return "bg-amber-100 text-amber-700"
	return "bg-green-100 text-green-700"
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
