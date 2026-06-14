<template>
	<div class="filters-simple">
		<!-- Main Search Bar with Inline Filters -->
		<div class="search-section">
			<div class="search-bar">
				<svg class="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
				</svg>
				<input
					v-model="store.searchTerm"
					type="text"
					class="search-input"
					:placeholder="__('Search invoices...')"
				/>
				<button
					v-if="store.searchTerm"
					@click="store.searchTerm = ''"
					class="clear-search"
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
					</svg>
				</button>
			</div>

			<!-- Quick Filter Chips -->
			<div class="quick-filters">
				<!-- Date Chips -->
				<button
					v-for="preset in quickDates"
					:key="preset.value"
					@click="preset.action()"
					:class="['filter-chip', { active: isDatePresetActive(preset.value) }]"
				>
					<svg class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
					</svg>
					{{ preset.label }}
				</button>

				<!-- Status Chips -->
				<button
					v-for="status in statusOptions"
					:key="status.value"
					@click="toggleStatus(status.value)"
					:class="['filter-chip', { active: store.status === status.value }]"
				>
					<svg v-if="status.value === 'Paid'" class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
					</svg>
					<svg v-else-if="status.value === 'Unpaid'" class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
					</svg>
					<svg v-else-if="status.value === 'Partly Paid'" class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
					</svg>
					<svg v-else-if="status.value === 'Overdue'" class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
					</svg>
					{{ status.label }}
				</button>

				<!-- More Filters Button -->
				<button
					@click="showAdvanced = !showAdvanced"
					:class="['filter-chip', 'more-btn', { active: showAdvanced || hasAdvancedFilters }]"
				>
					<svg class="chip-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/>
					</svg>
					{{ __('More') }}
					<span v-if="hasAdvancedFilters" class="count-badge">{{ advancedFiltersCount }}</span>
				</button>
			</div>
		</div>

		<!-- Active Filters Summary -->
		<Transition name="fade">
			<div v-if="store.hasActiveFilters" class="active-summary">
				<div class="summary-content">
					<TranslatedHTML 
						class="summary-text"
						:inner="__('&lt;strong&gt;{0}&lt;/strong&gt; of &lt;strong&gt;{1}&lt;/strong&gt; invoice(s)', 
							[(filterStats?.filtered || 0), (filterStats?.total || 0)]) "
					/>
					<div class="active-pills">
						<button
							v-for="filter in store.filterSummary"
							:key="filter.type"
							@click="store.clearFilter(filter.type)"
							class="active-pill"
						>
							{{ filter.label }}
							<svg class="w-3 h-3 ms-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
							</svg>
						</button>
					</div>
				</div>
				<button @click="store.clearAllFilters()" class="clear-all">
					{{ __('Clear all') }}
				</button>
			</div>
		</Transition>

		<!-- Advanced Filters Panel (Collapsible) -->
		<Transition name="expand">
			<div v-if="showAdvanced" class="advanced-panel">
				<!-- Customer & Product in Row -->
				<div class="filter-row">
					<div class="filter-field">
						<label class="field-label">
							<svg class="label-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
							</svg>
							{{ __('Customer') }}
						</label>
						<AutocompleteSelect
							v-model="store.customer"
							:options="props.uniqueCustomers"
							:placeholder="__('Search customers...')"
							icon="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
						/>
					</div>

					<div class="filter-field">
						<label class="field-label">
							<svg class="label-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
							</svg>
							{{ __('Product') }}
						</label>
						<AutocompleteSelect
							v-model="store.product"
							:options="props.uniqueProducts"
							:placeholder="__('Search products...')"
							icon="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
						/>
					</div>
				</div>

				<!-- Custom Date Range -->
				<div class="filter-row">
					<div class="filter-field">
						<label class="field-label">
							<svg class="label-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
							</svg>
							{{ __('From Date') }}
						</label>
						<input
							v-model="store.dateFrom"
							type="date"
							class="field-input"
						/>
					</div>

					<div class="filter-field">
						<label class="field-label">
							<svg class="label-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
							</svg>
							{{ __('To Date') }}
						</label>
						<input
							v-model="store.dateTo"
							type="date"
							class="field-input"
						/>
					</div>
				</div>

				<!-- Save Filter (if has filters) -->
				<div v-if="store.hasActiveFilters" class="save-row">
					<input
						v-model="saveFilterName"
						type="text"
						class="save-input"
						:placeholder="__('Save these filters as...')"
						@keyup.enter="saveFilters"
					/>
					<button @click="saveFilters" :disabled="!saveFilterName" class="save-btn">
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
						</svg>
						{{ __('Save') }}
					</button>
				</div>

				<!-- Saved Filters -->
				<div v-if="store.savedFilters.length > 0" class="saved-filters">
					<div class="saved-header">{{ __('Saved Filters') }}</div>
					<div class="saved-list">
						<button
							v-for="preset in store.savedFilters"
							:key="preset.name"
							@click="loadSavedFilter(preset.name)"
							class="saved-item"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/>
							</svg>
							{{ preset.name }}
							<span
								@click.stop="deleteSavedFilter(preset.name)"
								class="delete-saved"
							>
								<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</span>
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</div>
</template>

<script setup>
import AutocompleteSelect from "@/components/common/AutocompleteSelect.vue"
import { useInvoiceFiltersStore } from "@/stores/invoiceFilters"
import { computed, ref } from "vue"
import TranslatedHTML from "../common/TranslatedHTML.vue"

const props = defineProps({
	uniqueCustomers: {
		type: Array,
		default: () => [],
	},
	uniqueProducts: {
		type: Array,
		default: () => [],
	},
	filterStats: {
		type: Object,
		default: null,
	},
})

const store = useInvoiceFiltersStore()
const showAdvanced = ref(false)
const saveFilterName = ref("")

// Quick date presets (simplified)
const quickDates = [
	{ label: __("Today"), value: "today", action: () => store.setToday() },
	{
		label: __("Yesterday"),
		value: "yesterday",
		action: () => store.setYesterday(),
	},
	{ label: __("This Week"), value: "week", action: () => store.setThisWeek() },
	{ label: __("This Month"), value: "month", action: () => store.setThisMonth() },
]

// Status options (only show meaningful ones)
const statusOptions = [
	{ label: __("Paid"), value: "Paid" },
	{ label: __("Unpaid"), value: "Unpaid" },
	{ label: __("Partial"), value: "Partly Paid" },
	{ label: __("Overdue"), value: "Overdue" },
]

// Advanced filters (customer, product, custom date)
const hasAdvancedFilters = computed(() => {
	return !!(store.customer || store.product || (store.dateFrom && store.dateTo))
})

const advancedFiltersCount = computed(() => {
	let count = 0
	if (store.customer) count++
	if (store.product) count++
	if (store.dateFrom && store.dateTo) count++
	return count
})

function toggleStatus(status) {
	if (store.status === status) {
		store.status = ""
	} else {
		store.status = status
	}
}

function isDatePresetActive(preset) {
	const today = new Date()
	today.setHours(0, 0, 0, 0)

	let fromDate, toDate

	switch (preset) {
		case "today":
			fromDate = toDate = formatDateForInput(today)
			break
		case "yesterday":
			const yesterday = new Date(today)
			yesterday.setDate(yesterday.getDate() - 1)
			fromDate = toDate = formatDateForInput(yesterday)
			break
		case "week":
			const weekStart = new Date(today)
			weekStart.setDate(today.getDate() - today.getDay())
			fromDate = formatDateForInput(weekStart)
			toDate = formatDateForInput(today)
			break
		case "month":
			const monthStart = new Date(today.getFullYear(), today.getMonth(), 1)
			fromDate = formatDateForInput(monthStart)
			toDate = formatDateForInput(today)
			break
		default:
			return false
	}

	return store.dateFrom === fromDate && store.dateTo === toDate
}

function formatDateForInput(date) {
	const year = date.getFullYear()
	const month = String(date.getMonth() + 1).padStart(2, "0")
	const day = String(date.getDate()).padStart(2, "0")
	return `${year}-${month}-${day}`
}

function saveFilters() {
	if (saveFilterName.value && store.hasActiveFilters) {
		store.saveCurrentFilters(saveFilterName.value)
		saveFilterName.value = ""
		showAdvanced.value = false
	}
}

function loadSavedFilter(name) {
	store.loadFilterPreset(name)
	showAdvanced.value = false
}

function deleteSavedFilter(name) {
	if (confirm(__('Delete "{0}"?', [name]))) {
		store.deleteFilterPreset(name)
	}
}
</script>

<style scoped>
.filters-simple {
	width: 100%;
}

/* Search Section */
.search-section {
	display: flex;
	flex-direction: column;
	gap: 0.75rem;
}

.search-bar {
	position: relative;
	display: flex;
	align-items: center;
}

.search-icon {
	position: absolute;
	inset-inline-start: 1rem;
	width: 1.25rem;
	height: 1.25rem;
	color: #9ca3af;
	pointer-events: none;
}

.search-input {
	width: 100%;
	padding-block: 0.875rem;
	padding-inline: 3rem;
	border: 2px solid #e5e7eb;
	border-radius: 12px;
	font-size: 0.9375rem;
	color: #111827;
	background: white;
	transition: all 0.2s;
}

.search-input:focus {
	outline: none;
	border-color: #6366f1;
	box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.clear-search {
	position: absolute;
	inset-inline-end: 0.75rem;
	padding: 0.375rem;
	background: transparent;
	border: none;
	color: #9ca3af;
	border-radius: 6px;
	cursor: pointer;
	transition: all 0.15s;
}

.clear-search:hover {
	background: #f3f4f6;
	color: #374151;
}

/* Quick Filters */
.quick-filters {
	display: flex;
	flex-wrap: wrap;
	gap: 0.5rem;
}

.filter-chip {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	padding: 0.5rem 0.875rem;
	background: white;
	border: 1.5px solid #e5e7eb;
	border-radius: 20px;
	font-size: 0.8125rem;
	font-weight: 500;
	color: #374151;
	cursor: pointer;
	transition: all 0.15s;
	white-space: nowrap;
}

.filter-chip:hover {
	border-color: #6366f1;
	background: #f5f3ff;
	color: #6366f1;
}

.filter-chip.active {
	background: #6366f1;
	border-color: #6366f1;
	color: white;
}

.filter-chip.more-btn {
	position: relative;
}

.chip-icon {
	width: 0.875rem;
	height: 0.875rem;
}

.count-badge {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	min-width: 1.125rem;
	height: 1.125rem;
	padding: 0 0.25rem;
	background: rgba(255, 255, 255, 0.3);
	border-radius: 9999px;
	font-size: 0.6875rem;
	font-weight: 700;
}

/* Active Summary */
.active-summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 0.75rem 1rem;
	background: #f0fdf4;
	border: 1px solid #bbf7d0;
	border-radius: 10px;
	margin-top: 0.75rem;
	gap: 1rem;
}

.summary-content {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	flex: 1;
	flex-wrap: wrap;
}

.summary-text {
	font-size: 0.8125rem;
	color: #166534;
}

.summary-text strong {
	font-weight: 600;
}

.active-pills {
	display: flex;
	flex-wrap: wrap;
	gap: 0.375rem;
}

.active-pill {
	display: inline-flex;
	align-items: center;
	padding: 0.25rem 0.625rem;
	background: white;
	border: 1px solid #86efac;
	border-radius: 12px;
	font-size: 0.75rem;
	color: #15803d;
	cursor: pointer;
	transition: all 0.15s;
}

.active-pill:hover {
	background: #dcfce7;
	border-color: #4ade80;
}

.clear-all {
	padding: 0.5rem 0.875rem;
	background: white;
	border: 1px solid #fca5a5;
	border-radius: 8px;
	font-size: 0.8125rem;
	font-weight: 500;
	color: #dc2626;
	cursor: pointer;
	transition: all 0.15s;
	white-space: nowrap;
}

.clear-all:hover {
	background: #fee2e2;
	border-color: #f87171;
}

/* Advanced Panel */
.advanced-panel {
	margin-top: 1rem;
	padding: 1.25rem;
	background: #fafbfc;
	border: 1px solid #e5e7eb;
	border-radius: 12px;
	display: flex;
	flex-direction: column;
	gap: 1rem;
}

.filter-row {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
	gap: 1rem;
}

.filter-field {
	display: flex;
	flex-direction: column;
	gap: 0.5rem;
}

.field-label {
	display: flex;
	align-items: center;
	gap: 0.375rem;
	font-size: 0.8125rem;
	font-weight: 500;
	color: #374151;
}

.label-icon {
	width: 0.875rem;
	height: 0.875rem;
	color: #6b7280;
}

.field-input,
.field-select {
	padding: 0.625rem 0.75rem;
	border: 1px solid #d1d5db;
	border-radius: 8px;
	font-size: 0.875rem;
	color: #111827;
	background: white;
	transition: all 0.15s;
}

.field-input:focus,
.field-select:focus {
	outline: none;
	border-color: #6366f1;
	box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

/* Save Row */
.save-row {
	display: flex;
	gap: 0.75rem;
	padding-top: 0.75rem;
	border-top: 1px solid #e5e7eb;
}

.save-input {
	flex: 1;
	padding: 0.625rem 0.875rem;
	border: 1px solid #d1d5db;
	border-radius: 8px;
	font-size: 0.875rem;
	color: #111827;
	background: white;
}

.save-input:focus {
	outline: none;
	border-color: #6366f1;
	box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.save-btn {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	padding: 0.625rem 1rem;
	background: #6366f1;
	border: none;
	border-radius: 8px;
	font-size: 0.875rem;
	font-weight: 500;
	color: white;
	cursor: pointer;
	transition: all 0.15s;
}

.save-btn:hover:not(:disabled) {
	background: #4f46e5;
}

.save-btn:disabled {
	opacity: 0.5;
	cursor: not-allowed;
}

/* Saved Filters */
.saved-filters {
	padding-top: 0.75rem;
	border-top: 1px solid #e5e7eb;
}

.saved-header {
	font-size: 0.75rem;
	font-weight: 600;
	color: #6b7280;
	text-transform: uppercase;
	letter-spacing: 0.025em;
	margin-bottom: 0.5rem;
}

.saved-list {
	display: flex;
	flex-wrap: wrap;
	gap: 0.5rem;
}

.saved-item {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	padding: 0.5rem 0.75rem;
	background: white;
	border: 1px solid #d1d5db;
	border-radius: 8px;
	font-size: 0.8125rem;
	color: #374151;
	cursor: pointer;
	transition: all 0.15s;
	position: relative;
}

.saved-item:hover {
	border-color: #6366f1;
	background: #f5f3ff;
	color: #6366f1;
}

.delete-saved {
	padding: 0.125rem;
	background: transparent;
	border: none;
	color: inherit;
	opacity: 0.5;
	cursor: pointer;
	border-radius: 4px;
	transition: all 0.15s;
}

.delete-saved:hover {
	opacity: 1;
	background: rgba(220, 38, 38, 0.1);
	color: #dc2626;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
	transition: all 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
	transform: translateY(-4px);
}

.expand-enter-active,
.expand-leave-active {
	transition: all 0.3s ease;
	max-height: 600px;
	overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
	max-height: 0;
	opacity: 0;
}

/* Responsive */
@media (max-width: 640px) {
	.filter-row {
		grid-template-columns: 1fr;
	}

	.quick-filters {
		justify-content: flex-start;
	}

	.filter-chip {
		font-size: 0.75rem;
		padding: 0.4375rem 0.75rem;
	}

	.active-summary {
		flex-direction: column;
		align-items: stretch;
	}

	.summary-content {
		flex-direction: column;
		align-items: flex-start;
	}
}
</style>
