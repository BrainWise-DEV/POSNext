<template>
	<Dialog
		v-model="show"
		:options="{ title: __('POS Shift History'), size: '7xl' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-6">
				<!-- Quick Summary Cards -->
				<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
					<div class="bg-blue-50 border border-blue-100 rounded-xl p-4 flex flex-col justify-between shadow-sm">
						<span class="text-xs font-semibold text-blue-600 uppercase tracking-wider">{{ __('Total Sales') }}</span>
						<span class="text-2xl font-bold text-blue-900 mt-1">{{ formatCurrency(totalGrandTotal) }}</span>
					</div>
					<div class="bg-indigo-50 border border-indigo-100 rounded-xl p-4 flex flex-col justify-between shadow-sm">
						<span class="text-xs font-semibold text-indigo-600 uppercase tracking-wider">{{ __('Total Shifts') }}</span>
						<span class="text-2xl font-bold text-indigo-900 mt-1">{{ shifts.length }}</span>
					</div>
					<div :class="['rounded-xl p-4 flex flex-col justify-between shadow-sm border', totalCashDiff >= 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-rose-50 border-rose-100']">
						<span :class="['text-xs font-semibold uppercase tracking-wider', totalCashDiff >= 0 ? 'text-emerald-600' : 'text-rose-600']">{{ __('Net Cash Diff') }}</span>
						<span :class="['text-2xl font-bold mt-1', totalCashDiff >= 0 ? 'text-emerald-900' : 'text-rose-900']">{{ formatCurrency(totalCashDiff) }}</span>
					</div>
				</div>

				<!-- Filters Section -->
				<div class="flex flex-col sm:flex-row items-end gap-3 bg-gray-50/50 p-4 rounded-xl border border-gray-100">
					<div class="w-full sm:w-56">
						<label class="block text-[10px] font-bold text-gray-400 uppercase mb-1 ml-1">{{ __('POS Profile') }}</label>
						<select
							v-model="filters.pos_profile"
							@change="loadShifts"
							class="w-full h-10 px-3 bg-white border border-gray-200 rounded-lg text-sm font-medium focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all cursor-pointer shadow-sm"
						>
							<option value="">{{ __('All Profiles') }}</option>
							<option v-for="profile in posProfiles" :key="profile.name" :value="profile.name">
								{{ profile.name }}
							</option>
						</select>
					</div>
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
								</tr>
							</thead>
							<tbody class="divide-y divide-gray-50 bg-white">
								<tr 
									v-for="shift in shifts" 
									:key="shift.opening_shift_name" 
									@click="viewShift(shift)"
									class="hover:bg-blue-50/50 cursor-pointer transition-all duration-200 group relative"
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
								</tr>
							</tbody>
						</table>
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
	posProfile: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits(["update:modelValue"])

const show = ref(props.modelValue)
const shifts = ref([])
const posProfiles = ref([])

const filters = reactive({
	pos_profile: props.posProfile,
	from_date: "",
	to_date: "",
})

// Computed totals
const totalGrandTotal = computed(() => {
	return shifts.value.reduce((sum, s) => sum + Number.parseFloat(s.sales_total || 0), 0)
})

const totalCashDiff = computed(() => {
	return shifts.value.reduce((sum, s) => sum + Number.parseFloat(s.difference || 0), 0)
})

// Initialize filters and load profiles
onMounted(() => {
	const today = new Date()
	const startOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)
	
	filters.from_date = startOfMonth.toISOString().split('T')[0]
	filters.to_date = today.toISOString().split('T')[0]

	loadProfiles()
	if (show.value) {
		loadShifts()
	}
})

async function loadProfiles() {
	try {
		const res = await fetch("/api/method/frappe.client.get_list", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				doctype: "POS Profile",
				filters: { disabled: 0 },
				fields: ["name"]
			})
		})
		const data = await res.json()
		posProfiles.value = data.message || []
	} catch (e) {
		console.error("Failed to load profiles", e)
	}
}

function exportToCSV() {
	if (shifts.value.length === 0) return

	const headers = [
		__('Date'), 
		__('POS Profile'), 
		__('Cashier'), 
		__('Open Time'), 
		__('Close Time'), 
		__('Opening Amount'), 
		__('Closing Amount'), 
		__('Total Sales'), 
		__('Cash Difference')
	]

	const rows = shifts.value.map(s => [
		s.date,
		s.pos_profile,
		s.cashier,
		s.open_time,
		s.close_time || '-',
		s.opening_amount,
		s.closing_amount,
		s.sales_total,
		s.difference
	])

	let csvContent = "data:text/csv;charset=utf-8," 
		+ headers.join(",") + "\n"
		+ rows.map(e => e.join(",")).join("\n");

	const encodedUri = encodeURI(csvContent);
	const link = document.createElement("a");
	link.setAttribute("href", encodedUri);
	link.setAttribute("download", `POS_Shift_History_${filters.from_date}_to_${filters.to_date}.csv`);
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
}

function viewShift(shift) {
	const doctype = shift.closing_shift_name ? 'pos-closing-shift' : 'pos-opening-shift'
	const name = shift.closing_shift_name || shift.opening_shift_name
	window.open(`/app/${doctype}/${name}`, '_blank')
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
			filters: JSON.stringify(filters)
		}
	},
	auto: false,
	onSuccess(data) {
		shifts.value = data || []
	},
	onError(error) {
		console.error("Error loading shifts:", error)
		showError(__("Failed to load shift history"))
	},
})

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val && props.posProfile) {
			filters.pos_profile = props.posProfile
			shiftsResource.reload()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

function loadShifts() {
	if (props.posProfile) {
		shiftsResource.reload()
	}
}

</script>
