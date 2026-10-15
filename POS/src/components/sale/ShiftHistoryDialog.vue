<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div v-if="show" class="fixed inset-0 bg-black bg-opacity-50 z-[300]">
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4" @click.self="show = false">
				<div class="w-full max-w-[95vw] max-h-[95vh] bg-white rounded-lg shadow-2xl flex flex-col overflow-hidden">
					<!-- Header -->
					<div
						class="flex items-center justify-between px-6 py-5 border-b rounded-t-lg bg-gradient-to-r from-blue-50 to-indigo-50"
					>
						<div class="flex items-center gap-3">
							<div class="p-2 bg-blue-100 rounded-lg">
								<FeatherIcon name="clock" class="w-6 h-6 text-blue-600" />
							</div>
							<div class="text-start">
								<h2 class="text-xl font-bold text-gray-900">{{ __("Shift History") }}</h2>
								<p class="text-sm text-gray-600 mt-0.5">{{ __("Your opened and closed shifts") }}</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button
								variant="ghost"
								size="sm"
								icon-left="download"
								:disabled="shifts.length === 0"
								@click="exportToCSV"
							>
								{{ __("Export") }}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								icon-left="refresh-cw"
								:loading="shiftsResource.loading"
								@click="loadShifts"
							>
								{{ __("Refresh") }}
							</Button>
							<button
								type="button"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors"
								:aria-label="__('Close')"
								@click="show = false"
							>
								<FeatherIcon name="x" class="w-5 h-5 text-gray-600" />
							</button>
						</div>
					</div>

					<!-- Body -->
					<div class="flex-1 min-h-0 overflow-y-auto p-6 flex flex-col gap-5">
						<!-- Filters: drive both the totals and the table -->
						<div class="flex flex-wrap items-end gap-4 p-4 bg-gray-50 border border-gray-200 rounded-lg">
							<div class="w-full sm:w-48">
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">{{ __("From Date") }}</label>
								<Input v-model="filters.from_date" type="date" :max="filters.to_date" @change="onDateChange" />
							</div>
							<div class="w-full sm:w-48">
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">{{ __("To Date") }}</label>
								<Input v-model="filters.to_date" type="date" :min="filters.from_date" @change="onDateChange" />
							</div>
							<div class="inline-flex rounded-lg border border-gray-200 bg-white p-0.5" role="group">
								<button
									v-for="range in QUICK_RANGES"
									:key="range.key"
									type="button"
									class="h-7 px-3 rounded-md text-sm font-medium transition-colors"
									:class="
										activeRange === range.key
											? 'bg-blue-600 text-white shadow-sm'
											: 'text-gray-600 hover:bg-gray-100'
									"
									:aria-pressed="activeRange === range.key"
									@click="setQuickFilter(range.key)"
								>
									{{ range.label() }}
								</button>
							</div>
						</div>

						<!-- Summary: totals come from the server -->
						<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
							<div class="text-center p-4 bg-blue-50 rounded-lg border border-blue-100">
								<div class="text-xs text-gray-600 mb-1">{{ __("Total Sales") }}</div>
								<div class="text-xl font-bold text-gray-900 tabular-nums">
									{{ formatCurrency(serverTotals.total_sales) }}
								</div>
							</div>
							<div class="text-center p-4 bg-gray-50 rounded-lg border border-gray-200">
								<div class="text-xs text-gray-600 mb-1">{{ __("Total Shifts") }}</div>
								<div class="text-xl font-bold text-gray-900 tabular-nums">{{ serverTotals.total_shifts }}</div>
							</div>
							<div
								class="text-center p-4 rounded-lg border"
								:class="serverTotals.total_cash_diff < 0 ? 'bg-red-50 border-red-100' : 'bg-green-50 border-green-100'"
							>
								<div class="text-xs text-gray-600 mb-1">{{ __("Net Cash Difference") }}</div>
								<div
									class="text-xl font-bold tabular-nums"
									:class="serverTotals.total_cash_diff < 0 ? 'text-red-700' : 'text-green-700'"
								>
									{{ formatCurrency(serverTotals.total_cash_diff) }}
								</div>
							</div>
						</div>

						<!-- Shifts table -->
						<div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
							<div v-if="shiftsResource.loading" class="text-center py-16">
								<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
								<p class="mt-3 text-xs text-gray-500">{{ __("Loading shifts...") }}</p>
							</div>

							<div v-else-if="shifts.length === 0" class="text-center py-16">
								<div class="w-14 h-14 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
									<FeatherIcon name="clock" class="w-7 h-7 text-gray-400" />
								</div>
								<p class="text-gray-600 font-medium">{{ __("No shifts in this period") }}</p>
								<p class="text-gray-500 text-sm mt-1">{{ __("Try a wider date range") }}</p>
							</div>

							<div v-else class="overflow-auto max-h-[55vh]">
								<table class="w-full text-start text-sm border-collapse min-w-[860px]">
									<thead class="bg-gray-50 border-b border-gray-200 sticky top-0 z-10">
										<tr class="text-xs font-medium text-gray-500 uppercase whitespace-nowrap">
											<th class="px-5 py-3 text-start">{{ __("Shift") }}</th>
											<th class="px-5 py-3 text-start">{{ __("Status") }}</th>
											<th class="px-5 py-3 text-start">{{ __("Cashier") }}</th>
											<th class="px-5 py-3 text-end">{{ __("Opening") }}</th>
											<th class="px-5 py-3 text-end">{{ __("Closing") }}</th>
											<th class="px-5 py-3 text-end">{{ __("Sales") }}</th>
											<th class="px-5 py-3 text-end">{{ __("Cash Difference") }}</th>
											<th class="px-5 py-3 text-end">{{ __("Actions") }}</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-gray-100">
										<tr
											v-for="shift in shifts"
											:key="shift.opening_shift_name"
											class="hover:bg-blue-50/50 transition-colors"
										>
											<td class="px-5 py-4 text-start">
												<p class="font-semibold text-gray-900 whitespace-nowrap">{{ formatDate(shift.date) }}</p>
												<p class="mt-0.5 text-xs text-gray-500 tabular-nums whitespace-nowrap">
													<bdi v-if="shift.close_time" dir="ltr">
														{{ formatTime(shift.open_time) }} – {{ formatTime(shift.close_time) }}
													</bdi>
													<template v-else>{{ __("Since {0}", { 0: `\u2066${formatTime(shift.open_time)}\u2069` }) }}</template>
												</p>
											</td>
											<td class="px-5 py-4 text-start">
												<span
													class="inline-flex px-2 py-0.5 text-xs font-semibold rounded-full whitespace-nowrap"
													:class="shift.close_time ? 'bg-gray-100 text-gray-700' : 'bg-green-100 text-green-700'"
												>
													{{ shift.close_time ? __("Closed") : __("Running") }}
												</span>
											</td>
											<td class="px-5 py-4 text-start">
												<p class="text-gray-900 break-all">{{ shift.cashier }}</p>
												<p v-if="!posProfile" class="text-xs text-gray-500 break-words">{{ shift.pos_profile }}</p>
											</td>
											<td class="px-5 py-4 text-end whitespace-nowrap tabular-nums text-gray-600">
												{{ formatCurrency(shift.opening_amount) }}
											</td>
											<td class="px-5 py-4 text-end whitespace-nowrap tabular-nums text-gray-600">
												{{ shift.close_time ? formatCurrency(shift.closing_amount) : "—" }}
											</td>
											<td class="px-5 py-4 text-end whitespace-nowrap tabular-nums font-bold text-gray-900">
												{{ formatCurrency(shift.sales_total) }}
											</td>
											<td class="px-5 py-4 text-end whitespace-nowrap tabular-nums font-bold" :class="getCashDiffColor(shift.difference)">
												{{ formatCurrency(shift.difference) }}
											</td>
											<td class="px-5 py-4 text-end">
												<div class="flex items-center justify-end gap-2">
													<button
														type="button"
														class="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm hover:bg-gray-50 transition-colors"
														:title="__('View Opening Shift')"
														@click.stop="openShiftDoc(shift, 'opening')"
													>
														<FeatherIcon name="external-link" class="w-3.5 h-3.5" />
														{{ __("Opening") }}
													</button>
													<button
														v-if="shift.closing_shift_name"
														type="button"
														class="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm hover:bg-gray-50 transition-colors"
														:title="__('View Closing Shift')"
														@click.stop="openShiftDoc(shift, 'closing')"
													>
														<FeatherIcon name="external-link" class="w-3.5 h-3.5" />
														{{ __("Closing") }}
													</button>
												</div>
											</td>
										</tr>
									</tbody>
								</table>
							</div>

							<!-- Pagination -->
							<div
								v-if="totalPages > 1"
								class="flex items-center justify-between gap-3 px-5 py-3 border-t border-gray-200 bg-gray-50"
							>
								<span class="text-xs text-gray-600 select-none">
									{{
										__("Showing {0}–{1} of {2} shifts", {
											0: (currentPage - 1) * PAGE_SIZE + 1,
											1: Math.min(currentPage * PAGE_SIZE, serverTotals.total_shifts),
											2: serverTotals.total_shifts,
										})
									}}
								</span>
								<div class="flex items-center gap-1">
									<button
										type="button"
										class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
										:disabled="currentPage === 1 || shiftsResource.loading"
										:aria-label="__('Previous')"
										@click="goToPage(currentPage - 1)"
									>
										<FeatherIcon name="chevron-left" class="w-4 h-4 rtl:rotate-180" />
									</button>
									<template v-for="page in visiblePages" :key="page">
										<span
											v-if="typeof page === 'string'"
											class="w-8 h-8 flex items-center justify-center text-gray-400 text-xs select-none"
										>&hellip;</span>
										<button
											v-else
											type="button"
											:disabled="shiftsResource.loading"
											:class="[
												'w-8 h-8 flex items-center justify-center rounded-lg border text-xs font-semibold transition-colors',
												page === currentPage
													? 'bg-blue-600 border-blue-600 text-white shadow-sm'
													: 'bg-white border-gray-200 text-gray-600 hover:border-blue-300 hover:text-blue-600 disabled:opacity-50',
											]"
											@click="goToPage(page)"
										>
											{{ page }}
										</button>
									</template>
									<button
										type="button"
										class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
										:disabled="currentPage === totalPages || shiftsResource.loading"
										:aria-label="__('Next')"
										@click="goToPage(currentPage + 1)"
									>
										<FeatherIcon name="chevron-right" class="w-4 h-4 rtl:rotate-180" />
									</button>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { DEFAULT_CURRENCY, DEFAULT_LOCALE, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Button, FeatherIcon, Input, createResource } from "frappe-ui"
import { ref, watch, reactive, onMounted, computed } from "vue"

const { showError } = useToast()

const props = defineProps({
	modelValue: Boolean,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	posProfile: String,
})

const emit = defineEmits(["update:modelValue"])

const show = ref(props.modelValue)
const shifts = ref([])

// Pagination
const PAGE_SIZE   = 10
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
	return [...pages].sort((a, b) => {
		if (typeof a === 'number' && typeof b === 'number') return a - b
		if (typeof a === 'number') return -1
		if (typeof b === 'number') return 1
		return a === b ? 0 : a === '..l' ? -1 : 1
	})
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

// Quick ranges; a manual date edit clears the highlighted one
const QUICK_RANGES = [
	{ key: "7days", label: () => __("Last 7 days") },
	{ key: "1month", label: () => __("Last 30 days") },
]
const activeRange = ref(null)

function onDateChange() {
	activeRange.value = null
	loadShifts()
}

function setQuickFilter(type) {
	activeRange.value = type
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
			pos_profile: props.posProfile,
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

<style scoped>
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
