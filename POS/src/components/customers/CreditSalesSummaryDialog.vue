<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[290]"
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
								<h2 class="text-xl font-bold text-gray-900">{{ __('Credit Sales') }}</h2>
								<p class="text-sm text-gray-600 mt-0.5">{{ __('Customers who owe money') }}</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<button
								type="button"
								@click="loadSummary"
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

					<!-- Body -->
					<div class="flex-1 overflow-y-auto">

						<!-- Skeleton -->
						<div v-if="loading" class="p-6 space-y-4">
							<div class="bg-gray-100 rounded-xl h-24 animate-pulse"/>
							<div class="space-y-3 mt-6">
								<div v-for="i in 6" :key="i" class="bg-gray-100 rounded-xl h-16 animate-pulse"/>
							</div>
						</div>

						<!-- Content -->
						<div v-else-if="summary" class="p-6 space-y-6">

							<!-- Total card -->
							<div class="bg-orange-50 border-2 border-orange-300 rounded-xl p-5 text-center">
								<div class="text-xs font-medium text-orange-600 mb-1">{{ __('Total Owed') }}</div>
								<div class="text-3xl font-bold text-orange-700">{{ formatCurrency(summary.totals.net_balance) }}</div>
								<div class="text-xs text-orange-500 mt-1">
									{{ __('{0} customer(s) owe money', [summary.totals.customer_count]) }}
								</div>
							</div>

							<!-- Search -->
							<div v-if="summary.customers.length > 0" class="relative">
								<svg class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
								</svg>
								<input
									v-model="searchTerm"
									type="text"
									:placeholder="__('Search customers...')"
									class="w-full ps-9 pe-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400"
								/>
							</div>

							<!-- Empty state -->
							<div v-if="summary.customers.length === 0" class="text-center py-12">
								<div class="text-5xl mb-3">✓</div>
								<p class="text-lg font-semibold text-green-700">{{ __('No customers owe money') }}</p>
								<p class="text-sm text-gray-500 mt-1">{{ __('Everyone is settled up.') }}</p>
							</div>

							<!-- No search results -->
							<div v-else-if="filteredCustomers.length === 0" class="text-center py-8 text-gray-400 text-sm">
								{{ __('No customers match your search.') }}
							</div>

							<!-- Customer list -->
							<div v-else class="space-y-3">
								<button
									v-for="row in filteredCustomers"
									:key="row.customer"
									type="button"
									@click="$emit('select-customer', row.customer)"
									class="w-full bg-white border border-gray-200 rounded-xl p-4 text-start hover:border-orange-300 hover:bg-orange-50 transition-colors flex items-center justify-between gap-4 group"
								>
									<div class="flex-1 min-w-0">
										<div class="text-sm font-bold text-gray-900 truncate">{{ row.customer_name }}</div>
										<div class="text-xs text-gray-500 mt-0.5">
											{{ __('{0} invoice(s)', [row.due_count]) }}
										</div>
									</div>
									<div class="text-end flex-shrink-0">
										<div class="text-base font-bold text-orange-600">{{ formatCurrency(row.net_balance) }}</div>
									</div>
									<svg class="w-4 h-4 text-gray-300 flex-shrink-0 group-hover:text-orange-400 rtl-flip" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
									</svg>
								</button>
							</div>
						</div>

						<!-- Error state -->
						<div v-else class="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
							<svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
							</svg>
							<p>{{ __('Failed to load credit sales. Try refreshing.') }}</p>
							<button type="button" @click="loadSummary" class="text-orange-600 text-sm font-semibold hover:underline">
								{{ __('Retry') }}
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import {
	DEFAULT_CURRENCY,
	formatCurrency as formatCurrencyUtil,
} from "@/utils/currency"
import { normalizeSearchText } from "@/utils/searchText"
import { __ } from "@/utils/translation"
import { call } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	company: {
		type: String,
		default: "",
	},
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits(["update:modelValue", "select-customer"])

const { showError } = useToast()

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const loading = ref(false)
const summary = ref(null)
const searchTerm = ref("")

const filteredCustomers = computed(() => {
	if (!summary.value) return []
	const term = normalizeSearchText(searchTerm.value).trim()
	if (!term) return summary.value.customers
	return summary.value.customers.filter((c) =>
		normalizeSearchText(c.customer_name || c.customer).includes(term),
	)
})

watch(
	() => props.modelValue,
	(val) => {
		if (val) {
			summary.value = null
			searchTerm.value = ""
			loadSummary()
		}
	},
)

async function loadSummary() {
	loading.value = true
	try {
		const result = await call(
			"pos_next.api.customer_dues.get_credit_customers_summary",
			{
				pos_profile: props.posProfile || undefined,
				company: props.company || undefined,
			},
		)
		summary.value = result
	} catch (error) {
		showError(error.message || __("Failed to load credit sales"))
		summary.value = null
	} finally {
		loading.value = false
	}
}

function handleClose() {
	show.value = false
}

function formatCurrency(amount) {
	const cur = summary.value?.currency || props.currency
	return formatCurrencyUtil(Number.parseFloat(amount || 0), cur)
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
[dir="rtl"] .rtl-flip {
	transform: scaleX(-1);
}
</style>
