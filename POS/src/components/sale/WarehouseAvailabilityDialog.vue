<template>
	<Dialog v-model="show" :options="{ size: '3xl' }">
		<template #body-title>
			<h3 class="text-lg font-semibold text-gray-900">{{ __('Stock Lookup') }}</h3>
		</template>
		<template #body-content>
			<!-- Initial Loading State - shown before any content is ready -->
			<div v-if="!isReady && loading" class="flex flex-col items-center justify-center py-12">
				<div class="text-center">
					<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
					<p class="mt-4 text-sm text-gray-500">{{ __('Loading stock information...') }}</p>
				</div>
				<button
					@click="closeDialog"
					class="mt-6 px-4 py-2 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
				>
					{{ __('Cancel') }}
				</button>
			</div>

			<template v-else>
			<!-- Subtitle -->
			<div class="mb-4 -mt-2 text-start">
				<p class="text-sm text-gray-500">
					{{ isSearchMode && !selectedItemCode ? __('Search for items across warehouses') : displayItemName }}
				</p>
			</div>

			<!-- Search Section (Search Mode) -->
			<div v-if="isSearchMode" class="py-4 px-4 border-b border-gray-200 bg-gray-50 rounded-lg relative mb-4">
				<div class="relative">
					<!-- Search Icon / Loading Spinner -->
					<div class="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none">
						<svg v-if="!searching" class="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
						<div v-else class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
					</div>
					<!-- Search Input -->
					<input
						ref="searchInputRef"
						v-model="searchQuery"
						type="text"
						:placeholder="__('Type to search items...')"
						class="stock-search-input w-full ps-10 pe-10 py-3 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
						@input="handleSearchInput"
						@keydown.enter.prevent="selectFirstResult"
						@keydown.down.prevent="navigateResults(1)"
						@keydown.up.prevent="navigateResults(-1)"
						@keydown.escape="handleEscape"
						@focus="showSearchResults = searchResults.length > 0 || searchQuery.length >= 1"
						autocomplete="off"
					/>
					<!-- Clear Button -->
					<button
						v-if="searchQuery"
						@click="clearSearch"
						class="absolute inset-y-0 end-0 pe-3 flex items-center"
						:aria-label="__('Clear search')"
					>
						<svg class="h-5 w-5 text-gray-400 hover:text-gray-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
					</button>
				</div>

				<!-- Search Hint -->
				<div v-if="!searchQuery && !selectedItemCode" class="mt-2 flex items-center justify-start gap-2 text-xs text-gray-500">
					<svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
					</svg>
					<span class="text-start">{{ __('Search by item name, code, or scan barcode') }}</span>
				</div>

				<!-- Search Results Dropdown -->
				<div
					v-if="showSearchResults && (searchResults.length > 0 || (searchQuery.length >= 1 && !searching))"
					class="absolute start-4 end-4 z-20 mt-1 bg-white border border-gray-200 rounded-lg shadow-2xl max-h-72 overflow-y-auto"
				>
					<!-- Results List -->
					<div v-if="searchResults.length > 0">
						<button
							v-for="(item, index) in searchResults"
							:key="item.item_code"
							ref="resultRefs"
							@click="selectItem(item)"
							@mouseenter="selectedResultIndex = index"
							:class="[
								'w-full text-start px-4 py-3 flex items-center gap-3 border-b border-gray-100 last:border-0 transition-colors',
								selectedResultIndex === index ? 'bg-blue-50' : 'hover:bg-gray-50'
							]"
						>
							<!-- Item Image -->
							<div class="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center overflow-hidden flex-shrink-0">
								<img
									v-if="item.image"
									:src="item.image"
									:alt="item.item_name"
									class="w-full h-full object-cover"
								/>
								<svg v-else class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
								</svg>
							</div>
							<div class="flex-1 min-w-0 text-start">
								<!-- Item Name with Highlighting -->
								<p class="text-sm font-medium text-gray-900 truncate" v-html="highlightMatch(item.item_name, searchQuery)"></p>
								<!-- Item Code with Highlighting -->
								<p class="text-xs text-gray-500 truncate" v-html="highlightMatch(item.item_code, searchQuery)"></p>
							</div>
							<div class="text-end flex-shrink-0 flex flex-col items-end gap-1">
								<!-- Stock Badge -->
								<span :class="[
									'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
									(item.actual_qty || 0) > 0 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
								]">
									{{ Math.floor(item.actual_qty || 0) }} {{ item.stock_uom || __('Nos') }}
								</span>
								<!-- Price if available -->
								<span v-if="item.rate" class="text-xs text-gray-500">
									{{ formatPrice(item.rate) }}
								</span>
							</div>
						</button>
					</div>

					<!-- No Results -->
					<div v-else-if="searchQuery.length >= 1 && !searching" class="px-4 py-6 text-center">
						<svg class="mx-auto h-10 w-10 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
						</svg>
						<p class="mt-2 text-sm text-gray-500">{{ __('No items found for "{0}"', [searchQuery]) }}</p>
						<p class="mt-1 text-xs text-gray-400">{{ __('Try a different search term') }}</p>
					</div>
				</div>
			</div>

			<!-- Selected Item Header (Search Mode with item selected) -->
			<div v-if="isSearchMode && selectedItemCode" class="py-2 px-3 bg-blue-50 border border-blue-200 rounded-lg mb-4">
				<div class="flex items-center gap-2">
					<!-- Item Image -->
					<div class="w-8 h-8 bg-white rounded flex items-center justify-center overflow-hidden border border-blue-200 flex-shrink-0">
						<img
							v-if="selectedItemImage"
							:src="selectedItemImage"
							:alt="displayItemName"
							class="w-full h-full object-cover"
						/>
						<svg v-else class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
						</svg>
					</div>
					<!-- Item Info -->
					<div class="flex-1 min-w-0 text-start">
						<p class="text-sm font-medium text-gray-900 truncate">{{ displayItemName }}</p>
						<p class="text-xs text-gray-500 truncate">{{ selectedItemCode }}</p>
					</div>
					<!-- Clear Button -->
					<button
						@click="clearSelectedItem"
						class="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-blue-100 rounded transition-colors flex-shrink-0"
						:title="__('Search Again')"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
					</button>
				</div>
			</div>

			<!-- Variant Selection Section -->
			<div v-if="showVariantSelection" class="mb-4 border border-gray-200 rounded-lg bg-gray-50">
				<div class="p-4">
					<div class="flex items-center justify-between mb-3">
						<h4 class="text-sm font-semibold text-gray-900">{{ __('Select Variants') }}</h4>
						<div class="flex gap-2">
							<button
								@click="selectAllVariants"
								class="text-xs px-2 py-1 text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded transition-colors"
							>
								{{ __('Select All') }}
							</button>
							<button
								@click="deselectAllVariants"
								class="text-xs px-2 py-1 text-gray-600 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
							>
								{{ __('Deselect All') }}
							</button>
						</div>
					</div>

					<!-- Loading Variants -->
					<div v-if="loadingVariants" class="flex items-center justify-center py-8">
						<div class="text-center">
							<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
							<p class="mt-2 text-xs text-gray-500">{{ __('Loading variants...') }}</p>
						</div>
					</div>

					<!-- Variants List -->
					<div v-else-if="variants.length > 0" class="space-y-2 max-h-64 overflow-y-auto">
						<button
							v-for="variant in variants"
							:key="variant.item_code"
							@click="toggleVariantSelection(variant)"
							:class="[
								'w-full text-start p-3 rounded-lg border transition-all',
								isVariantSelected(variant)
									? 'bg-blue-50 border-blue-300 shadow-sm'
									: 'bg-white border-gray-200 hover:border-blue-200 hover:bg-gray-50'
							]"
						>
							<div class="flex items-center gap-3">
								<!-- Checkbox -->
								<div class="flex-shrink-0">
									<div :class="[
										'w-5 h-5 rounded border-2 flex items-center justify-center transition-colors',
										isVariantSelected(variant)
											? 'bg-blue-600 border-blue-600'
											: 'bg-white border-gray-300'
									]">
										<svg v-if="isVariantSelected(variant)" class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/>
										</svg>
									</div>
								</div>
								
								<!-- Variant Image -->
								<div class="w-10 h-10 bg-gray-100 rounded flex items-center justify-center overflow-hidden flex-shrink-0">
									<img
										v-if="variant.image"
										:src="variant.image"
										:alt="variant.item_name"
										class="w-full h-full object-cover"
									/>
									<svg v-else class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
									</svg>
								</div>

								<!-- Variant Info -->
								<div class="flex-1 min-w-0">
									<p class="text-sm font-medium text-gray-900 truncate">{{ variant.item_name }}</p>
									<p class="text-xs text-gray-500 truncate">{{ variant.item_code }}</p>
									<!-- Attributes -->
									<div v-if="variant.attributes && Object.keys(variant.attributes).length > 0" class="mt-1 flex flex-wrap gap-1">
										<span
											v-for="(value, key) in variant.attributes"
											:key="key"
											class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-700"
										>
											{{ key }}: {{ value }}
										</span>
									</div>
								</div>
							</div>
						</button>
					</div>

					<!-- No Variants -->
					<div v-else class="text-center py-6">
						<p class="text-sm text-gray-500">{{ __('No variants found') }}</p>
					</div>

					<!-- Confirm Button -->
					<div v-if="variants.length > 0" class="mt-4 pt-4 border-t border-gray-200">
						<button
							@click="confirmVariantSelection"
							:disabled="selectedVariants.length === 0"
							:class="[
								'w-full px-4 py-2 rounded-lg font-medium transition-colors',
								selectedVariants.length > 0
									? 'bg-blue-600 text-white hover:bg-blue-700'
									: 'bg-gray-300 text-gray-500 cursor-not-allowed'
							]"
						>
							{{ __('Check Availability in All Wherehouses') }} ({{ selectedVariants.length }} {{ __('Selected') }})
						</button>
					</div>
				</div>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto">
				<!-- Loading State (only show if not in variant selection) -->
				<div v-if="loading && !showVariantSelection" class="flex items-center justify-center py-12">
					<div class="text-center">
						<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
						<p class="mt-4 text-sm text-gray-500">{{ __('Checking warehouse availability...') }}</p>
					</div>
				</div>

				<!-- Error State (only show if not in variant selection) -->
				<div v-else-if="error && !showVariantSelection" class="flex items-center justify-center py-12">
					<div class="text-center">
						<svg class="mx-auto h-12 w-12 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
						</svg>
						<p class="mt-4 text-sm text-gray-700">{{ error }}</p>
						<button
							@click="loadAvailability"
							class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
						>
							{{ __('Try Again') }}
						</button>
					</div>
				</div>

				<!-- Prompt to Search (Search Mode, No Item Selected) -->
				<div v-else-if="isSearchMode && !selectedItemCode && !showVariantSelection" class="flex items-center justify-center py-12">
					<div class="text-center">
						<svg class="mx-auto h-16 w-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
						<p class="mt-4 text-base font-medium text-gray-700">{{ __('Search for an item') }}</p>
						<p class="mt-2 text-sm text-gray-500">{{ __('Start typing to see suggestions') }}</p>
						<div class="mt-4 flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-gray-400">
							<span class="flex items-center gap-1">
								<kbd class="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 font-mono">↑↓</kbd>
								<span>{{ __('Navigate') }}</span>
							</span>
							<span class="flex items-center gap-1">
								<kbd class="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 font-mono">{{ __('Enter') }}</kbd>
								<span>{{ __('Select') }}</span>
							</span>
							<span class="flex items-center gap-1">
								<kbd class="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 font-mono">{{ __('Esc') }}</kbd>
								<span>{{ __('Clear') }}</span>
							</span>
						</div>
					</div>
				</div>

				<!-- Warehouses List (only show if not in variant selection) -->
				<div v-else-if="warehouses && warehouses.length > 0 && !showVariantSelection" class="flex flex-col gap-3">
					<!-- Group by warehouse if multiple variants selected -->
					<template v-if="selectedVariants.length > 1">
						<!-- Group warehouses by warehouse name -->
						<div
							v-for="(warehouseGroup, warehouseName) in groupedWarehouses"
							:key="warehouseName"
							class="bg-gray-50 rounded-lg p-4 border border-gray-200 hover:border-blue-300 transition-colors"
						>
							<div class="flex items-center justify-between gap-4 mb-3 pb-3 border-b border-gray-200">
								<div class="flex-1 min-w-0 text-start">
									<h3 class="font-medium text-gray-900 truncate">{{ warehouseGroup[0].warehouse_name }}</h3>
									<p class="text-sm text-gray-500 mt-0.5 truncate">{{ warehouseGroup[0].company }}</p>
								</div>
								<div class="text-end flex-shrink-0">
									<div class="text-xs text-gray-500">
										{{ warehouseGroup.length }} {{ warehouseGroup.length === 1 ? __('variant') : __('variants') }}
									</div>
								</div>
							</div>
							<!-- Variants in this warehouse -->
							<div class="space-y-2">
								<div
									v-for="warehouse in warehouseGroup"
									:key="`${warehouse.warehouse}-${warehouse.item_code}`"
									class="bg-white rounded p-3 border border-gray-100"
								>
									<div class="flex items-center justify-between gap-4">
										<div class="flex-1 min-w-0 text-start">
											<p class="text-sm font-medium text-gray-900 truncate">
												{{ getVariantName(warehouse.item_code) }}
											</p>
											<p class="text-xs text-gray-500 truncate">{{ warehouse.item_code }}</p>
										</div>
										<div class="text-end flex-shrink-0">
											<div :class="[
												'text-base font-bold',
												warehouse.available_qty > 0 ? 'text-green-600' : 'text-red-500'
											]">
												{{ Math.floor(warehouse.available_qty) }} {{ getVariantUom(warehouse.item_code) }}
											</div>
											<div class="text-xs text-gray-500 mt-0.5">
												<span v-if="warehouse.reserved_qty > 0" class="text-orange-600">
													{{ __( '{0} reserved', [Math.floor(warehouse.reserved_qty)]) }}
												</span>
												<span v-if="warehouse.rate" class="text-gray-500">{{ formatPrice(warehouse.rate) }}</span>
												<span v-else>{{ __('Available') }}</span>
											</div>
										</div>
									</div>
									<!-- Actual vs Available -->
									<div v-if="warehouse.actual_qty !== warehouse.available_qty" class="mt-2 pt-2 border-t border-gray-100">
										<div class="flex items-center justify-between text-xs text-gray-600">
											<span class="text-start">{{ __('Actual Stock') }}</span>
											<span class="font-medium text-end">{{ Math.floor(warehouse.actual_qty) }} {{ getVariantUom(warehouse.item_code) }}</span>
										</div>
									</div>
								</div>
							</div>
						</div>
					</template>
					<!-- Single variant or no variants - show simple list -->
					<template v-else>
						<div
							v-for="warehouse in warehouses"
							:key="warehouse.warehouse"
							class="bg-gray-50 rounded-lg p-4 border border-gray-200 hover:border-blue-300 transition-colors"
						>
							<div class="flex items-center justify-between gap-4">
								<div class="flex-1 min-w-0 text-start">
									<h3 class="font-medium text-gray-900 truncate">{{ warehouse.warehouse_name }}</h3>
									<p class="text-sm text-gray-500 mt-0.5 truncate">{{ warehouse.company }}</p>
									<!-- Show variant name if single variant selected -->
									<p v-if="warehouse.item_code && selectedVariants.length === 1" class="text-xs text-blue-600 mt-1">
										{{ getVariantName(warehouse.item_code) }}
									</p>
								</div>
								<div class="text-end flex-shrink-0">
									<div :class="[
										'text-lg font-bold',
										warehouse.available_qty > 0 ? 'text-green-600' : 'text-red-500'
									]">
										{{ Math.floor(warehouse.available_qty) }} {{ warehouse.item_code ? getVariantUom(warehouse.item_code) : displayUom }}
									</div>
									<!-- Converted quantity in barcode UOM if different -->
									<div v-if="selectedBarcodeUom && convertToBarcodeUom(warehouse.available_qty) !== null" class="text-sm text-blue-600 font-medium">
										≈ {{ Math.floor(convertToBarcodeUom(warehouse.available_qty) * 100) / 100 }} {{ selectedBarcodeUom }}
									</div>
									<div class="text-xs text-gray-500 mt-0.5">
										<span v-if="warehouse.reserved_qty > 0" class="text-orange-600">
											{{ __( '{0} reserved', [Math.floor(warehouse.reserved_qty)]) }}
										</span>
										<span v-else>{{ __('Available') }}</span>
									</div>
								</div>
							</div>
							<!-- Actual vs Available -->
							<div v-if="warehouse.actual_qty !== warehouse.available_qty" class="mt-2 pt-2 border-t border-gray-200">
								<div class="flex items-center justify-between text-xs text-gray-600">
									<span class="text-start">{{ __('Actual Stock') }}</span>
									<span class="font-medium text-end">{{ Math.floor(warehouse.actual_qty) }} {{ warehouse.item_code ? getVariantUom(warehouse.item_code) : displayUom }}</span>
								</div>
							</div>
						</div>
					</template>
				</div>

				<!-- No Stock State (only show if not in variant selection) -->
				<div v-else-if="(selectedItemCode || itemCode) && !showVariantSelection" class="flex items-center justify-center py-12">
					<div class="text-center">
						<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
						</svg>
						<p class="mt-4 text-sm text-gray-700 font-medium">{{ __('No stock available') }}</p>
						<p class="mt-1 text-sm text-gray-500">{{ __('This item is out of stock in all warehouses') }}</p>
					</div>
				</div>
			</div>
			</template>

			<!-- Footer -->
			<div v-if="isReady" class="pt-4 mt-4 border-t border-gray-200">
				<div class="flex flex-col sm:flex-row items-start sm:items-center gap-3">
					<div v-if="(selectedItemCode || itemCode) && warehouses.length > 0" class="text-sm text-gray-600 text-start">
						<div>
							<span class="font-medium">{{ __('Total Available') }}:</span>
							<span class="ms-2 text-gray-900 font-semibold text-lg">
								{{ totalAvailable }} {{ displayUom }}
							</span>
							<span v-if="warehouses.length > 0" class="ms-2 text-gray-500">
								{{ warehouses.length === 1
									? __('in 1 warehouse')
									: __('in {0} warehouses', [warehouses.length])
								}}
							</span>
						</div>
						<!-- Converted total in barcode UOM if different -->
						<div v-if="selectedBarcodeUom && convertToBarcodeUom(totalAvailable) !== null" class="text-blue-600 font-medium mt-1">
							≈ {{ Math.floor(convertToBarcodeUom(totalAvailable) * 100) / 100 }} {{ selectedBarcodeUom }}
						</div>
					</div>
					<button
						@click="closeDialog"
						class="w-full sm:w-auto sm:ms-auto px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
					>
						{{ __('Close') }}
					</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * WarehouseAvailabilityDialog.vue
 *
 * Stock Lookup Dialog - Shows item availability across warehouses
 *
 * Modes:
 * - 'item': Single item mode - shows availability for a specific item (default)
 * - 'search': Search mode - allows searching for any item with autocomplete
 *
 * RTL Support: Fully compatible with right-to-left languages
 * Translations: All user-facing strings use __() for i18n
 */
import { ref, computed, watch, nextTick } from 'vue'
import { call, Dialog } from 'frappe-ui'
import { __ } from '@/utils/translation'

const props = defineProps({
	modelValue: Boolean,
	// For single item mode (backward compatible)
	itemCode: String,
	itemName: String,
	uom: {
		type: String,
		default: 'Nos'
	},
	company: String,
	currency: {
		type: String,
		default: ''
	},
	// For search mode
	posProfile: String,
	// Mode: 'item' for single item (default), 'search' for general search
	mode: {
		type: String,
		default: 'item'
	}
})

const emit = defineEmits(['update:modelValue', 'close'])

// v-model binding for Dialog
const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val)
})

// Close dialog helper
function closeDialog() {
	emit('update:modelValue', false)
	emit('close')
}

// Determine if we're in search mode
const isSearchMode = computed(() => props.mode === 'search')

// Search state
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const selectedResultIndex = ref(-1)
const showSearchResults = ref(false)
const searchInputRef = ref(null)
const resultRefs = ref([])
let searchDebounce = null

// Selected item state (for search mode)
const selectedItemCode = ref('')
const selectedItemName = ref('')
const selectedItemImage = ref('')
const selectedUom = ref('Nos')
const selectedItemHasVariants = ref(false)
const selectedBarcodeUom = ref('') // Single barcode UOM if different from default
const selectedItemUoms = ref([]) // Conversion factors for UOMs

// Variant state
const variants = ref([])
const selectedVariants = ref([])
const loadingVariants = ref(false)
const showVariantSelection = ref(false)

// Warehouse availability state
const loading = ref(false)
const error = ref(null)
const warehouses = ref([])
const isReady = ref(false) // Gate to prevent showing content before data is ready

// Computed display values
const displayItemName = computed(() => {
	if (isSearchMode.value) {
		return selectedItemName.value || ''
	}
	return props.itemName || props.itemCode || ''
})

const displayUom = computed(() => {
	if (isSearchMode.value) {
		return selectedUom.value || 'Nos'
	}
	return props.uom || 'Nos'
})

const totalAvailable = computed(() => {
	if (!warehouses.value || warehouses.value.length === 0) return 0
	return Math.floor(warehouses.value.reduce((sum, w) => sum + (w.available_qty || 0), 0))
})

// Group warehouses by warehouse name when multiple variants selected
const groupedWarehouses = computed(() => {
	if (selectedVariants.value.length <= 1) return {}
	
	const grouped = {}
	for (const warehouse of warehouses.value) {
		const key = warehouse.warehouse || warehouse.warehouse_name
		if (!grouped[key]) {
			grouped[key] = []
		}
		grouped[key].push(warehouse)
	}
	return grouped
})

// Helper functions for variant info
function getVariantName(itemCode) {
	const variant = variants.value.find(v => v.item_code === itemCode)
	return variant ? variant.item_name : itemCode
}

function getVariantUom(itemCode) {
	const variant = variants.value.find(v => v.item_code === itemCode)
	return variant ? (variant.stock_uom || 'Nos') : displayUom.value
}

// Initialize and load based on mode
watch(() => props.modelValue, async (newVal) => {
	if (newVal) {
		// Set loading immediately to prevent flash of empty content
		loading.value = true
		isReady.value = false
		error.value = null

		if (isSearchMode.value) {
			// Search mode - clear state and focus search
			resetSearchState()
			isReady.value = true
			loading.value = false
			await nextTick()
			focusSearch()
		} else if (props.itemCode) {
			// Item mode - check if item has variants first
			// We need to fetch item details to check has_variants
			try {
				const itemResponse = await call('pos_next.api.items.get_items', {
					pos_profile: props.posProfile,
					search_term: props.itemCode,
					start: 0,
					limit: 1
				})
				const item = itemResponse?.[0]
				if (item && item.has_variants) {
					selectedItemCode.value = props.itemCode
					selectedItemName.value = props.itemName || props.itemCode
					selectedItemHasVariants.value = true
					isReady.value = true
					await loadVariants()
				} else {
					// No variants, directly load availability
					isReady.value = true
					await loadAvailability()
				}
			} catch (err) {
				console.error('Error checking item variants:', err)
				// Fallback to direct load
				isReady.value = true
				await loadAvailability()
			}
		} else {
			// No item code provided
			isReady.value = true
			loading.value = false
		}
	} else {
		// Reset when dialog closes
		resetSearchState()
		warehouses.value = []
		error.value = null
		isReady.value = false
	}
}, { immediate: true })

function resetSearchState() {
	searchQuery.value = ''
	searchResults.value = []
	selectedResultIndex.value = -1
	showSearchResults.value = false
	selectedItemCode.value = ''
	selectedItemName.value = ''
	selectedItemImage.value = ''
	selectedUom.value = 'Nos'
	selectedItemHasVariants.value = false
	selectedBarcodeUom.value = ''
	selectedItemUoms.value = []
	variants.value = []
	selectedVariants.value = []
	showVariantSelection.value = false
	warehouses.value = []
	error.value = null
	// Don't reset isReady here - it's managed by the watch
}

function focusSearch() {
	if (searchInputRef.value) {
		searchInputRef.value.focus()
	}
}

async function handleSearchInput() {
	selectedResultIndex.value = -1
	showSearchResults.value = true

	if (searchDebounce) {
		clearTimeout(searchDebounce)
	}

	// Start searching after just 1 character for faster autocomplete
	if (searchQuery.value.length < 1) {
		searchResults.value = []
		searching.value = false
		return
	}

	searching.value = true

	// Shorter debounce for snappier autocomplete (150ms)
	searchDebounce = setTimeout(async () => {
		await performSearch()
	}, 150)
}

async function performSearch() {
	if (searchQuery.value.length < 1) {
		searching.value = false
		return
	}

	try {
		const response = await call('pos_next.api.items.get_items', {
			pos_profile: props.posProfile,
			search_term: searchQuery.value,
			start: 0,
			limit: 15 // Show more results for better autocomplete
		})

		searchResults.value = response || []

		// Auto-select first result for quick enter
		if (searchResults.value.length > 0) {
			selectedResultIndex.value = 0
		}
	} catch (err) {
		console.error('Error searching items:', err)
		searchResults.value = []
	} finally {
		searching.value = false
	}
}

function navigateResults(direction) {
	if (searchResults.value.length === 0) return

	const newIndex = selectedResultIndex.value + direction

	if (newIndex >= 0 && newIndex < searchResults.value.length) {
		selectedResultIndex.value = newIndex

		// Scroll selected item into view
		nextTick(() => {
			const resultElements = document.querySelectorAll('[ref="resultRefs"]')
			if (resultElements[newIndex]) {
				resultElements[newIndex].scrollIntoView({ block: 'nearest' })
			}
		})
	}
}

function selectFirstResult() {
	if (searchResults.value.length > 0) {
		const index = selectedResultIndex.value >= 0 ? selectedResultIndex.value : 0
		selectItem(searchResults.value[index])
	}
}

async function selectItem(item) {
	// Set loading state before clearing search results
	loading.value = true

	selectedItemCode.value = item.item_code
	selectedItemName.value = item.item_name
	selectedItemImage.value = item.image || ''
	selectedUom.value = item.stock_uom || item.uom || 'Nos'
	selectedItemHasVariants.value = item.has_variants || false
	selectedItemUoms.value = item.item_uoms || []

	// Check if barcode_uoms has a single value different from default UOM
	const barcodeUoms = item.barcode_uoms ? item.barcode_uoms.split(',').map(u => u.trim()).filter(u => u) : []
	if (barcodeUoms.length === 1 && barcodeUoms[0] !== selectedUom.value) {
		selectedBarcodeUom.value = barcodeUoms[0]
	} else {
		selectedBarcodeUom.value = ''
	}

	searchQuery.value = ''
	searchResults.value = []
	showSearchResults.value = false
	selectedResultIndex.value = -1

	// Check if item has variants
	if (selectedItemHasVariants.value) {
		await loadVariants()
	} else {
		// No variants, directly load availability
		await loadAvailability()
	}
}

function handleEscape() {
	if (showSearchResults.value && searchResults.value.length > 0) {
		// First escape closes dropdown
		showSearchResults.value = false
	} else if (searchQuery.value) {
		// Second escape clears search
		clearSearch()
	} else {
		// Third escape closes dialog
		closeDialog()
	}
}

function clearSearch() {
	searchQuery.value = ''
	searchResults.value = []
	selectedResultIndex.value = -1
	showSearchResults.value = false
	focusSearch()
}

function clearSelectedItem() {
	selectedItemCode.value = ''
	selectedItemName.value = ''
	selectedItemImage.value = ''
	selectedUom.value = 'Nos'
	selectedItemHasVariants.value = false
	selectedBarcodeUom.value = ''
	selectedItemUoms.value = []
	variants.value = []
	selectedVariants.value = []
	showVariantSelection.value = false
	warehouses.value = []
	error.value = null
	nextTick(() => {
		focusSearch()
	})
}

/**
 * Convert quantity from stock UOM to barcode UOM
 * @param {number} qty - Quantity in stock UOM
 * @returns {number|null} Converted quantity or null if conversion not possible
 */
function convertToBarcodeUom(qty) {
	if (!selectedBarcodeUom.value || !selectedItemUoms.value.length) return null

	const uomData = selectedItemUoms.value.find(u => u.uom === selectedBarcodeUom.value)
	if (!uomData || !uomData.conversion_factor) return null

	// Convert: stock_qty / conversion_factor = barcode_uom_qty
	return qty / uomData.conversion_factor
}

async function loadVariants() {
	const templateItem = isSearchMode.value ? selectedItemCode.value : props.itemCode
	if (!templateItem || !props.posProfile) return

	loadingVariants.value = true
	variants.value = []
	selectedVariants.value = []
	showVariantSelection.value = true
	error.value = null

	try {
		const response = await call('pos_next.api.items.get_item_variants', {
			template_item: templateItem,
			pos_profile: props.posProfile
		})

		variants.value = response || []
		
		// If no variants found, load availability for the template item itself
		if (variants.value.length === 0) {
			showVariantSelection.value = false
			loadAvailability()
		}
	} catch (err) {
		console.error('Error loading variants:', err)
		error.value = err.message || __('Failed to load variants')
		showVariantSelection.value = false
	} finally {
		loadingVariants.value = false
	}
}

function toggleVariantSelection(variant) {
	const index = selectedVariants.value.findIndex(v => v.item_code === variant.item_code)
	if (index >= 0) {
		selectedVariants.value.splice(index, 1)
	} else {
		selectedVariants.value.push(variant)
	}
}

function isVariantSelected(variant) {
	return selectedVariants.value.some(v => v.item_code === variant.item_code)
}

function confirmVariantSelection() {
	if (selectedVariants.value.length === 0) {
		error.value = __('Please select at least one variant')
		return
	}
	showVariantSelection.value = false
	loadAvailability()
}

function selectAllVariants() {
	selectedVariants.value = [...variants.value]
}

function deselectAllVariants() {
	selectedVariants.value = []
}

async function loadAvailability() {
	const targetItemCode = isSearchMode.value ? selectedItemCode.value : props.itemCode

	if (!targetItemCode) return

	loading.value = true
	error.value = null
	warehouses.value = []

	try {
		// If variants are selected, use item_codes parameter
		if (selectedVariants.value.length > 0) {
			const itemCodes = selectedVariants.value.map(v => v.item_code)
			const response = await call('pos_next.api.items.get_item_warehouse_availability', {
				item_codes: JSON.stringify(itemCodes),
				company: props.company
			})
			warehouses.value = response || []
		} else {
			// Single item (backward compatible)
			const response = await call('pos_next.api.items.get_item_warehouse_availability', {
				item_code: targetItemCode,
				company: props.company
			})
			warehouses.value = response || []
		}
	} catch (err) {
		console.error('Error loading warehouse availability:', err)
		error.value = err.message || __('Failed to load warehouse availability')
	} finally {
		loading.value = false
	}
}

/**
 * Highlight matching text in search results
 * @param {string} text - Text to search in
 * @param {string} query - Search query to highlight
 * @returns {string} HTML with highlighted matches
 */
function highlightMatch(text, query) {
	if (!text || !query) return text

	const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
	const regex = new RegExp(`(${escapedQuery})`, 'gi')
	return text.replace(regex, '<mark class="bg-yellow-200 text-yellow-900 rounded px-0.5">$1</mark>')
}

/**
 * Format price with locale-aware formatting
 * @param {number} price - Price value
 * @returns {string} Formatted price
 */
function formatPrice(price) {
	if (!price) return ''
	const num = Number(price)
	if (isNaN(num)) return ''
	return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
/* RTL Support for Search Input */
.stock-search-input {
	text-align: start;
}

/* RTL mode - Right align text and placeholder */
:global([dir="rtl"]) .stock-search-input,
:global(.rtl) .stock-search-input {
	text-align: right;
	direction: rtl;
}

:global([dir="rtl"]) .stock-search-input::placeholder,
:global(.rtl) .stock-search-input::placeholder {
	text-align: right;
	direction: rtl;
}
</style>
