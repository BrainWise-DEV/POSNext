<template>
	<Dialog
		v-model="show"
		:options="{ title: __('POS Shift History'), size: '7xl' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-6">
				<!-- Quick Summary Cards — totals come from the server (#11 fix) -->
				<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
					<div class="bg-blue-50 border border-blue-100 rounded-xl p-4 flex flex-col justify-between shadow-sm">
						<span class="text-xs font-semibold text-blue-600 uppercase tracking-wider">{{ __('Total Sales') }}</span>
						<span class="text-2xl font-bold text-blue-900 mt-1">{{ formatCurrency(serverTotals.total_sales) }}</span>
					</div>
					<div class="bg-indigo-50 border border-indigo-100 rounded-xl p-4 flex flex-col justify-between shadow-sm">
						<span class="text-xs font-semibold text-indigo-600 uppercase tracking-wider">{{ __('Total Shifts') }}</span>
						<span class="text-2xl font-bold text-indigo-900 mt-1">{{ serverTotals.total_shifts }}</span>
					</div>
					<div :class="['rounded-xl p-4 flex flex-col justify-between shadow-sm border', serverTotals.total_cash_diff >= 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-rose-50 border-rose-100']">
						<span :class="['text-xs font-semibold uppercase tracking-wider', serverTotals.total_cash_diff >= 0 ? 'text-emerald-600' : 'text-rose-600']">{{ __('Net Cash Diff') }}</span>
						<span :class="['text-2xl font-bold mt-1', serverTotals.total_cash_diff >= 0 ? 'text-emerald-900' : 'text-rose-900']">{{ formatCurrency(serverTotals.total_cash_diff) }}</span>
					</div>
				</div>

				<!-- Filters Section -->
				<div class="flex flex-col sm:flex-row items-end gap-3 bg-gray-50/50 p-4 rounded-xl border border-gray-100">
					<div class="w-full sm:w-44">
						<label class="block text-[10px] font-bold text-gray-400 uppercase mb-1 ml-1">{{ __('From Date') }}</label>
						<Input
							type="date"
							v-model="filters.from_date"
							class="shadow-sm"
							@change="loadShifts"
						/>
					</div>
					<div class="w-full sm:w-44">
						<label class="block text-[10px] font-bold text-gray-400 uppercase mb-1 ml-1">{{ __('To Date') }}</label>
						<Input
							type="date"
							v-model="filters.to_date"
							class="shadow-sm"
							@change="loadShifts"
						/>
					</div>
					<div class="flex-1"></div>
					<div class="flex items-center gap-2">
						<Button
							variant="subtle"
							theme="gray"
							class="shadow-sm font-bold"
							@click="setQuickFilter('7days')"
						>
							{{ __('7D') }}
						</Button>
						<Button
							variant="subtle"
							theme="gray"
							class="shadow-sm font-bold"
							@click="setQuickFilter('1month')"
						>
							{{ __('1M') }}
						</Button>
						<Button
							variant="solid"
							theme="blue"
							class="shadow-md"
							@click="loadShifts"
							:loading="shiftsResource.loading"
						>
							<template #icon>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
								</svg>
							</template>
							{{ __('Refresh') }}
						</Button>
						<Button
							variant="subtle"
							theme="gray"
							class="shadow-sm border border-gray-100"
							@click="exportToCSV"
							:disabled="shifts.length === 0"
						>
							<template #icon>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
								</svg>
							</template>
						</Button>
					</div>
				</div>

				<!-- Shifts Table -->
				<div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
					<div v-if="shiftsResource.loading" class="flex flex-col items-center justify-center py-20">
						<div class="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
						<p class="mt-4 text-sm font-semibold text-gray-500 tracking-wide uppercase">{{ __('Loading your history...') }}</p>
					</div>

					<div v-else-if="shifts.length === 0" class="flex flex-col items-center justify-center py-20 opacity-50">
						<svg class="h-16 w-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
						</svg>
						<p class="mt-4 text-sm font-semibold text-gray-500 uppercase tracking-widest">{{ __('No shifts found for this range') }}</p>
					</div>

					<div v-else class="overflow-x-auto max-h-[50vh]">
						<table class="w-full text-left text-sm whitespace-nowrap border-collapse">
							<thead class="bg-gray-50 border-b border-gray-100 top-0 sticky z-10">
								<tr>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest">{{ __('Shift Date') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest">{{ __('POS Profile') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest">{{ __('Cashier') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-center">{{ __('Times (Open - Close)') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">{{ __('Opening') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">{{ __('Closing') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">{{ __('Sales') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">{{ __('Cash Diff') }}</th>
									<th class="px-5 py-3 text-[10px] font-bold text-gray-500 uppercase tracking-widest text-right">{{ __('Actions') }}</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-gray-50 bg-white">
								<tr 
									v-for="shift in shifts" 
									:key="shift.opening_shift_name" 
									class="hover:bg-blue-50/50 transition-all duration-200 group relative"
								>
									<td class="px-5 py-4 font-semibold text-gray-900 group-hover:text-blue-700">
										{{ formatDate(shift.date) }}
									</td>
									<td class="px-5 py-4">
										<span class="px-2 py-1 bg-gray-100 text-gray-700 text-[11px] font-semibold rounded-md uppercase tracking-wide">
											{{ shift.pos_profile }}
										</span>
									</td>
									<td class="px-5 py-4 text-gray-500 tabular-nums">
										{{ shift.cashier }}
									</td>
									<td class="px-5 py-4 text-center">
										<div class="flex items-center justify-center gap-2">
											<span class="text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">{{ formatTime(shift.open_time) }}</span>
											<svg class="w-3 h-3 text-gray-300" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
											<span v-if="shift.close_time" class="text-[11px] font-semibold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{{ formatTime(shift.close_time) }}</span>
											<span v-else class="text-[11px] font-semibold text-green-600 bg-green-50 px-1.5 py-0.5 rounded italic uppercase tracking-tighter">{{ __('Running') }}</span>
										</div>
									</td>
									<td class="px-5 py-4 text-right tabular-nums font-medium text-gray-600">{{ formatCurrency(shift.opening_amount) }}</td>
									<td class="px-5 py-4 text-right tabular-nums font-medium text-gray-600">{{ formatCurrency(shift.closing_amount) }}</td>
									<td class="px-5 py-4 text-right tabular-nums font-bold text-gray-900">{{ formatCurrency(shift.sales_total) }}</td>
									<td class="px-5 py-4 text-right">
										<span :class="['inline-flex items-center gap-1 font-bold tabular-nums', getCashDiffColor(shift.difference)]">
											<svg v-if="shift.difference > 0" class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M14.707 12.707a1 1 0 01-1.414 0L10 9.414l-3.293 3.293a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clip-rule="evenodd"/></svg>
											<svg v-else-if="shift.difference < 0" class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
											{{ formatCurrency(shift.difference) }}
										</span>
									</td>
									<!-- FIX #17: actions column — user can open either Opening or Closing shift -->
									<td class="px-3 py-4 text-right">
										<div class="flex items-center justify-end gap-1">
											<button
												@click.stop="openShiftDoc(shift, 'opening')"
												class="text-[10px] font-semibold px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
												:title="__('View Opening Shift')"
											>
												{{ __('Open') }}
											</button>
											<button
												v-if="shift.closing_shift_name"
												@click.stop="openShiftDoc(shift, 'closing')"
												class="text-[10px] font-semibold px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
												:title="__('View Closing Shift')"
											>
												{{ __('Close') }}
											</button>
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<!-- Pagination bar (shown when there is more than one page) -->
				<div
					v-if="totalPages > 1"
					class="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50/60 rounded-b-xl"
				>
					<span class="text-[11px] font-medium text-gray-500 select-none">
						{{ __('Showing') }}
						{{ (currentPage - 1) * PAGE_SIZE + 1 }}&ndash;{{ Math.min(currentPage * PAGE_SIZE, serverTotals.total_shifts) }}
						{{ __('of') }} {{ serverTotals.total_shifts }} {{ __('shifts') }}
					</span>

					<div class="flex items-center gap-1">
						<button
							@click="goToPage(currentPage - 1)"
							:disabled="currentPage === 1 || shiftsResource.loading"
							class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-white hover:border-blue-300 hover:text-blue-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
						>
							<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
						</button>

						<template v-for="page in visiblePages" :key="page">
							<span
								v-if="typeof page === 'string'"
								class="w-8 h-8 flex items-center justify-center text-gray-400 text-xs select-none"
							>&hellip;</span>
							<button
								v-else
								@click="goToPage(page)"
								:disabled="shiftsResource.loading"
								:class="[
									'w-8 h-8 flex items-center justify-center rounded-lg border text-xs font-semibold transition-colors',
									page === currentPage
										? 'bg-blue-600 border-blue-600 text-white shadow-sm'
										: 'border-gray-200 text-gray-600 hover:bg-white hover:border-blue-300 hover:text-blue-600 disabled:opacity-50',
								]"
							>{{ page }}</button>
						</template>

						<button
							@click="goToPage(currentPage + 1)"
							:disabled="currentPage === totalPages || shiftsResource.loading"
							class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-white hover:border-blue-300 hover:text-blue-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
						>
							<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/></svg>
						</button>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="show = false" class="font-bold uppercase tracking-widest text-xs px-6">
				{{ __('Close History') }}
			</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { DEFAULT_CURRENCY, DEFAULT_LOCALE, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { ref, watch, reactive, onMounted, computed } from "vue"

const { showError } = useToast()

const props = defineProps({
	modelValue: Boolean,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits(["update:modelValue"])

const show = ref(props.modelValue)
const shifts = ref([])

// Pagination
const PAGE_SIZE   = 5
const currentPage = ref(1)

const totalPages = computed(() => {
	const total = serverTotals.value.total_shifts
	return total > 0 ? Math.ceil(total / PAGE_SIZE) : 1
})

// Visible page numbers for the paginator (always shows at most 5 buttons)
const visiblePages = computed(() => {
	const total = totalPages.value
	const cur   = currentPage.value
	if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)

	const pages = new Set([1, total])
	for (let i = Math.max(1, cur - 1); i <= Math.min(total, cur + 1); i++) pages.add(i)
	if (cur - 2 > 2)     pages.add('..l')
	if (cur + 2 < total) pages.add('..r')
	return [...pages].sort((a, b) =>
		typeof a === 'number' && typeof b === 'number' ? a - b
		: typeof a === 'number' ? -1 : 1
	)
})

// FIX #11: server-side aggregate totals (avoid client-side computation over
// a LIMIT-truncated page). Initialised to zeros; updated on each successful load.
const serverTotals = ref({
	total_sales: 0,
	total_cash_diff: 0,
	total_shifts: 0,
})

// Initialize date filters once on mount; profile + shift loading is deferred
// to the show-watcher so it only fires when the dialog is actually opened.
const filters = reactive({
	from_date: "",
	to_date: "",
})

onMounted(() => {
	const today = new Date()
	const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)

	filters.from_date = startOfMonth.toISOString().split('T')[0]
	filters.to_date = today.toISOString().split('T')[0]
})


/**
 * Safely encode a single CSV field per RFC 4180 + OWASP formula-injection rules.
 *
 * Rules applied in order:
 *  1. Coerce to string; null/undefined → empty string.
 *  2. OWASP formula-injection guard: if the value starts with one of the
 *     dangerous leading characters (=, +, -, @, TAB, CR) that spreadsheet
 *     apps treat as formula starters, prepend a single TAB character.
 *     This breaks the formula trigger while keeping the cell readable.
 *  3. RFC 4180 quoting: always wrap the field in double-quotes and escape
 *     any embedded double-quote by doubling it ("").
 *
 * @param {*} value - Raw cell value.
 * @returns {string} - RFC 4180 quoted cell string.
 */
function csvEscape(value) {
	const FORMULA_PREFIX = /^[=+\-@\t\r]/
	let str = (value == null || value === undefined) ? '' : String(value)

	// Strip bare \r or \r\n inside values; keep \n (will be inside quotes, safe in RFC 4180)
	str = str.replace(/\r\n?/g, '\n')

	// OWASP: neutralise formula-injection trigger characters at start of cell
	if (FORMULA_PREFIX.test(str)) {
		str = '\t' + str
	}

	// RFC 4180: always quote, escape internal double-quotes by doubling
	return '"' + str.replace(/"/g, '""') + '"'
}

/**
 * Download shift history as a properly encoded CSV file.
 *
 * Uses Blob + URL.createObjectURL (best practice):
 *  - No 2 MB data-URI size cap.
 *  - Binary-safe: UTF-8 BOM ensures Excel opens with correct encoding
 *    without requiring a manual import wizard.
 *  - CRLF line endings (\r\n) per RFC 4180 — required by Excel on Windows.
 *  - Memory is released immediately via revokeObjectURL after the click.
 */
function exportToCSV() {
	if (!shifts.value.length) return

	const headers = [
		__('Date'),
		__('POS Profile'),
		__('Cashier'),
		__('Open Time'),
		__('Close Time'),
		__('Opening Amount'),
		__('Closing Amount'),
		__('Total Sales'),
		__('Cash Difference'),
	]

	// Build rows — format display values for readability in the spreadsheet
	const rows = shifts.value.map(s => [
		s.date || '',
		s.pos_profile || '',
		s.cashier || '',
		s.open_time  ? formatTime(s.open_time)  : '',
		s.close_time ? formatTime(s.close_time) : '',
		s.opening_amount ?? 0,
		s.closing_amount ?? 0,
		s.sales_total    ?? 0,
		s.difference     ?? 0,
	])

	// RFC 4180: CRLF between records; header row first
	const CRLF = '\r\n'
	const csvLines = [
		headers.map(csvEscape).join(','),
		...rows.map(row => row.map(csvEscape).join(',')),
	].join(CRLF)

	// UTF-8 BOM (EF BB BF) — tells Excel this is UTF-8, preventing mojibake
	const BOM = '\uFEFF'
	const blob = new Blob([BOM + csvLines], { type: 'text/csv;charset=utf-8;' })

	// Create a temporary object URL, trigger download, then revoke immediately
	const url = URL.createObjectURL(blob)
	const link = document.createElement('a')
	link.href = url
	link.download = `POS_Shift_History_${filters.from_date}_to_${filters.to_date}.csv`
	link.style.display = 'none'
	document.body.appendChild(link)
	link.click()
	document.body.removeChild(link)
	// Release the object URL from memory — must happen after the click
	URL.revokeObjectURL(url)
}

// FIX #17: replaced the old viewShift() that always opened the closing shift
// (if it existed) with openShiftDoc() that lets the user pick explicitly.
function openShiftDoc(shift, type) {
	if (type === 'closing' && shift.closing_shift_name) {
		window.open(`/app/pos-closing-shift/${shift.closing_shift_name}`, '_blank')
	} else {
		window.open(`/app/pos-opening-shift/${shift.opening_shift_name}`, '_blank')
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function formatDate(dateString) {
	if (!dateString) return ""
	return new Date(dateString).toLocaleDateString(DEFAULT_LOCALE, {
		year: "numeric",
		month: "short",
		day: "2-digit"
	})
}

function formatTime(dateTimeString) {
	if (!dateTimeString) return "-"
	return new Date(dateTimeString).toLocaleTimeString(DEFAULT_LOCALE, {
		hour: "2-digit",
		minute: "2-digit",
		hour12: true
	})
}

function getCashDiffColor(diff) {
	if (!diff && diff !== 0) return 'text-gray-900'
	if (diff > 0) return 'text-green-600'
	if (diff < 0) return 'text-red-600'
	return 'text-gray-900'
}

function setQuickFilter(type) {
	const today = new Date()
	filters.to_date = today.toISOString().split('T')[0]
	
	const from = new Date()
	if (type === '7days') {
		from.setDate(today.getDate() - 7)
	} else if (type === '1month') {
		from.setMonth(today.getMonth() - 1)
	}
	filters.from_date = from.toISOString().split('T')[0]
	
	loadShifts()
}

const shiftsResource = createResource({
	url: "pos_next.api.shifts.get_shift_history",
	makeParams() {
		return {
			filters: JSON.stringify(filters),
			limit:  PAGE_SIZE,
			offset: (currentPage.value - 1) * PAGE_SIZE,
		}
	},
	auto: false,
	onSuccess(response) {
		if (response && typeof response === 'object' && !Array.isArray(response) && response.rows) {
			shifts.value = response.rows || []
			serverTotals.value = {
				total_sales:     response.totals?.total_sales     ?? 0,
				total_cash_diff: response.totals?.total_cash_diff ?? 0,
				total_shifts:    response.totals?.total_shifts    ?? shifts.value.length,
			}
		} else {
			shifts.value = response || []
			serverTotals.value = {
				total_sales:     shifts.value.reduce((s, r) => s + (r.sales_total || 0), 0),
				total_cash_diff: shifts.value.reduce((s, r) => s + (r.difference  || 0), 0),
				total_shifts:    shifts.value.length,
			}
		}
	},
	onError(error) {
		console.error("Error loading shifts:", error)
		showError(__("Failed to load shift history"))
	},
})

// Navigate to a specific page (1-indexed)
function goToPage(page) {
	const p = Number(page)
	if (!Number.isInteger(p) || p < 1 || p > totalPages.value) return
	currentPage.value = p
	shiftsResource.reload()
}

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			shiftsResource.reload()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// loadShifts always returns to page 1 (filter changed)
function loadShifts() {
	currentPage.value = 1
	shiftsResource.reload()
}

</script>
