<template>
	<div class="flex flex-col h-full bg-gray-50">
		<!-- Item Groups Filter Tabs -->
		<div class="relative px-1.5 sm:px-3 py-1.5 bg-white border-b border-gray-200">
			<!-- Scroll back: fade edge plus button, shown only when categories are hidden on that side -->
			<div
				v-if="chipScroll.start"
				class="absolute inset-y-0 start-0 z-[1] flex items-center ps-1 pe-6 bg-gradient-to-r rtl:bg-gradient-to-l from-white via-white to-transparent"
			>
				<button
					type="button"
					class="pos-btn pos-btn-outline pos-btn-icon rounded-full shadow-sm"
					:aria-label="__('Show previous categories')"
					@click="scrollChips(-1)"
				>
					<svg class="w-4 h-4 rtl:-scale-x-100" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
					</svg>
				</button>
			</div>
			<div
				ref="chipStripRef"
				class="flex items-center gap-1.5 sm:gap-2 overflow-x-auto scrollbar-hide snap-x"
				@scroll.passive="updateChipScroll"
			>
				<button
					@click="handleAllFilterClick"
					:aria-pressed="!activeFilterValue"
					:class="[
						'flex items-center gap-1.5 min-h-target px-3 rounded-lg border text-pos-sm font-medium whitespace-nowrap transition-[background-color,border-color] duration-75 touch-manipulation snap-start flex-shrink-0 pos-focus',
						!activeFilterValue
							? 'bg-pos-action-soft text-pos-action border-pos-action font-semibold'
							: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100',
					]"
				>
					<svg
						class="w-4 h-4"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 6h16M4 12h16M4 18h16"
						/>
					</svg>
					<span>{{ isBrandSortActive ? __("All Brands") : __("All Items") }}</span>
				</button>
				<button
					v-for="option in activeFilterOptions"
					:key="option.value"
					@click="handleFilterClick(option.value)"
					:aria-pressed="activeFilterValue === option.value"
					dir="auto"
					:class="[
						'flex items-center min-h-target px-3 rounded-lg border text-pos-sm font-medium whitespace-nowrap transition-[background-color,border-color] duration-75 touch-manipulation snap-start flex-shrink-0 pos-focus',
						activeFilterValue === option.value
							? 'bg-pos-action-soft text-pos-action border-pos-action font-semibold'
							: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100',
					]"
				>
					<span>{{ __(option.label) }}</span>
				</button>
			</div>
			<!-- Scroll forward: the fade edge is the cue that more categories exist -->
			<div
				v-if="chipScroll.end"
				class="absolute inset-y-0 end-0 z-[1] flex items-center pe-1 ps-6 bg-gradient-to-l rtl:bg-gradient-to-r from-white via-white to-transparent"
			>
				<button
					type="button"
					class="pos-btn pos-btn-outline pos-btn-icon rounded-full shadow-sm"
					:aria-label="__('Show more categories')"
					@click="scrollChips(1)"
				>
					<svg class="w-4 h-4 rtl:-scale-x-100" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Cache Sync Indicator -->
		<div v-if="cacheSyncing" class="px-1.5 sm:px-3 py-1 bg-blue-50 border-b border-blue-200">
			<div
				class="flex items-center justify-center gap-2 text-[10px] sm:text-xs text-blue-700"
			>
				<div class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600"></div>
				<span>{{
					__("Syncing catalog in background... {0} items cached", [cacheStats.items])
				}}</span>
			</div>
		</div>

		<!-- Search Bar with Barcode Scanner and View Controls -->
		<div class="px-1.5 sm:px-3 py-1.5 bg-white border-b border-gray-200">
			<div class="flex items-center gap-1.5 sm:gap-2">
				<div class="flex-1 relative min-w-0">
					<!-- Search Icon -->
					<div
						class="absolute inset-y-0 start-0 ps-2 sm:ps-3 flex items-center pointer-events-none"
					>
						<svg
							class="h-4 w-4 text-gray-500"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
					</div>
					<!-- Search Input -->
					<input
						id="item-search"
						name="item-search"
						ref="searchInputRef"
						:value="searchTerm"
						@input="handleSearchInput"
						@keydown="handleKeyDown"
						@click="handleSearchClick"
						@focus="handleSearchClick"
						type="text"
						spellcheck="false"
						autocomplete="off"
						:placeholder="searchPlaceholder"
						:class="[
							'w-full min-h-target text-pos-sm text-pos-ink placeholder:text-gray-500 border rounded-lg px-2 sm:px-3 py-2 ps-8 sm:ps-10 focus:outline-none transition-all',
							searchTerm
								? 'pe-[calc(var(--pos-target)_*_3_+_0.75rem)]'
								: 'pe-[calc(var(--pos-target)_*_2_+_2.5rem)]',
							autoAddEnabled
								? 'border-blue-400 bg-blue-50 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
								: scannerEnabled
								? 'border-green-400 bg-green-50 focus:ring-2 focus:ring-green-500 focus:border-transparent'
								: 'border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent',
						]"
						:aria-label="__('Search items')"
					/>
					<!-- Clear, F4 hint, barcode scan icon and auto-add toggle -->
					<div class="absolute inset-y-0 end-0 pe-0.5 flex items-center gap-0.5">
						<button
							v-if="searchTerm"
							type="button"
							class="flex items-center justify-center min-h-target min-w-target rounded-md text-gray-500 hover:text-pos-ink hover:bg-gray-100 pos-focus"
							:title="__('Clear search')"
							:aria-label="__('Clear search')"
							@click="clearSearchAndResetInput"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
						<kbd
							v-else
							class="hidden sm:inline-block px-1.5 py-0.5 me-1 rounded border border-gray-300 bg-white text-xs font-medium text-gray-600 tabular-nums"
							dir="ltr"
							:title="__('Press F4 to focus search')"
							>F4</kbd
						>
						<button
							@click="toggleBarcodeScanner"
							:class="[
								'flex items-center justify-center min-h-target min-w-target rounded-md transition-[background-color] duration-75 touch-manipulation pos-focus',
								scannerEnabled
									? 'bg-green-100 hover:bg-green-200 active:bg-green-300 text-green-700'
									: 'hover:bg-gray-100 active:bg-gray-200 text-gray-600',
							]"
							:title="
								scannerEnabled
									? __('Barcode Scanner: ON (Click to disable)')
									: __('Barcode Scanner: OFF (Click to enable)')
							"
							:aria-label="
								scannerEnabled
									? __('Disable barcode scanner')
									: __('Enable barcode scanner')
							"
						>
							<svg
								class="w-[18px] h-[18px]"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"
								/>
							</svg>
						</button>
						<button
							@click="toggleAutoAdd"
							:class="[
								'flex items-center justify-center min-h-target min-w-target rounded-md transition-[background-color] duration-75 touch-manipulation pos-focus',
								autoAddEnabled
									? 'bg-blue-100 hover:bg-blue-200 active:bg-blue-300 text-blue-700'
									: 'hover:bg-gray-100 active:bg-gray-200 text-gray-600',
							]"
							:title="
								autoAddEnabled
									? __('Auto-Add: ON - Press Enter to add items to cart')
									: __(
											'Auto-Add: OFF - Click to enable automatic cart addition on Enter'
									  )
							"
							:aria-label="
								autoAddEnabled ? __('Disable auto-add') : __('Enable auto-add')
							"
						>
							<svg
								class="w-4 h-4"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M12 4v16m8-8H4"
								/>
							</svg>
						</button>
					</div>
				</div>
				<div class="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5 flex-shrink-0">
					<button
						@click="setViewMode('grid')"
						:aria-pressed="viewMode === 'grid'"
						:class="[
							'flex items-center justify-center min-h-target min-w-target rounded-md transition-[background-color,box-shadow] duration-75 touch-manipulation pos-focus',
							viewMode === 'grid'
								? 'bg-white shadow-sm'
								: 'hover:bg-gray-200 active:bg-gray-300',
						]"
						:title="__('Grid View')"
						:aria-label="__('Switch to grid view')"
					>
						<svg
							class="w-[18px] h-[18px]"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
							/>
						</svg>
					</button>
					<button
						@click="setViewMode('list')"
						:aria-pressed="viewMode === 'list'"
						:class="[
							'flex items-center justify-center min-h-target min-w-target rounded-md transition-[background-color,box-shadow] duration-75 touch-manipulation pos-focus',
							viewMode === 'list'
								? 'bg-white shadow-sm'
								: 'hover:bg-gray-200 active:bg-gray-300',
						]"
						:title="__('List View')"
						:aria-label="__('Switch to list view')"
					>
						<svg
							class="w-[18px] h-[18px]"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M4 6h16M4 12h16M4 18h16"
							/>
						</svg>
					</button>
				</div>

				<!-- Sort Dropdown -->
				<div class="relative z-50">
					<button
						@click="toggleSortDropdown"
						data-sort-button
						:class="[
							'flex items-center justify-center min-h-target min-w-target rounded-lg transition-[background-color,box-shadow] duration-75 touch-manipulation border pos-focus',
							sortBy
								? 'bg-blue-50 border-blue-400 text-blue-700 shadow-sm'
								: 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100',
						]"
						:title="
							sortBy
								? sortOrder === 'asc'
									? __('Sorted by {0} A-Z', [getSortLabel(sortBy)])
									: __('Sorted by {0} Z-A', [getSortLabel(sortBy)])
								: __('Sort items')
						"
						:aria-label="__('Sort items')"
					>
						<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
							/>
						</svg>
					</button>

					<!-- Dropdown Menu -->
					<div
						v-if="showSortDropdown"
						@click.stop
						class="absolute end-0 mt-1 w-56 bg-white rounded-lg shadow-xl border border-gray-200 z-[9999]"
						style="
							box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
								0 10px 10px -5px rgba(0, 0, 0, 0.04);
						"
					>
						<div class="py-2">
							<div
								class="px-3 py-2 text-xs font-semibold text-gray-600 border-b border-gray-100"
							>
								{{ __("Sort Items") }}
							</div>
							<div class="py-1">
								<!-- Clear Sort -->
								<button
									@click="handleSortToggle(null)"
									:class="[
										'w-full min-h-target px-3 py-2 text-sm transition-colors flex items-center justify-between group',
										!sortBy
											? 'bg-blue-50 text-blue-700'
											: 'text-gray-700 hover:bg-gray-50',
									]"
								>
									<span class="flex items-center gap-2.5">
										<svg
											class="w-4 h-4 text-gray-500 group-hover:text-gray-700"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M6 18L18 6M6 6l12 12"
											/>
										</svg>
										<span>{{ __("No Sorting") }}</span>
									</span>
								</button>

								<div class="h-px bg-gray-100 my-1"></div>

								<!-- Sort Options Loop -->
								<button
									v-for="option in sortOptions"
									:key="option.field"
									@click="handleSortToggle(option.field)"
									:class="[
										'w-full min-h-target px-3 py-2 text-sm transition-colors flex items-center justify-between group',
										sortBy === option.field
											? 'bg-blue-50 text-blue-700'
											: 'text-gray-700 hover:bg-gray-50',
									]"
								>
									<span class="flex items-center gap-2.5">
										<svg
											class="w-4 h-4 text-gray-500 group-hover:text-gray-700"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												:d="option.icon"
											/>
										</svg>
										<span>{{ option.label }}</span>
									</span>
									<!-- Sort direction icon -->
									<svg
										class="w-5 h-5"
										:class="
											sortBy === option.field
												? 'text-pos-action'
												: 'text-gray-400'
										"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											:d="SORT_ICONS[getSortIconState(option.field)]"
										/>
									</svg>
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Initial Loading State - Show spinner while fetching items -->
		<div
			v-if="loading && (!filteredItems || filteredItems.length === 0)"
			class="flex-1 flex items-center justify-center p-3"
		>
			<div class="text-center py-8">
				<div
					class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"
				></div>
				<p class="mt-3 text-xs text-gray-500">{{ __("Loading items...") }}</p>
			</div>
		</div>

		<!-- Empty State - Only show when NOT loading and truly no items -->
		<div
			v-else-if="!loading && (!filteredItems || filteredItems.length === 0)"
			class="flex-1 flex items-center justify-center p-3"
		>
			<div class="text-center py-8">
				<svg
					class="mx-auto h-8 w-8 text-gray-400"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
					/>
				</svg>
				<p
					v-if="searchTerm || selectedFilterLabel"
					class="mt-2 text-xs font-medium text-gray-700"
				>
					<span v-if="searchTerm && selectedFilterLabel">{{
						__("No results for {0} in {1}", [searchTerm, selectedFilterLabel])
					}}</span>
					<span v-else-if="selectedFilterLabel">{{
						__("No results in {0}", [selectedFilterLabel])
					}}</span>
					<span v-else>{{ __("No results for {0}", [searchTerm]) }}</span>
				</p>
				<p v-else class="mt-2 text-xs text-gray-500">{{ __("No items available") }}</p>
			</div>
		</div>

		<!-- Grid View -->
		<div
			v-if="viewMode === 'grid'"
			key="grid"
			class="flex-1 flex flex-col overflow-hidden min-h-0"
		>
			<div
				ref="gridScrollContainer"
				class="flex-1 overflow-y-auto p-2 sm:p-3"
				style="min-height: 0"
			>
				<!-- Columns follow the pane's own width (auto-fill), not the viewport -->
				<div class="pos-item-grid grid gap-2 sm:gap-2.5">
					<div
						v-for="item in displayedItems"
						:key="item.item_code"
						role="button"
						tabindex="0"
						:data-item-code="item.item_code"
						:aria-label="item.item_name"
						@touchstart.passive="getOptimizedClickHandler(item).touchstart"
						@touchmove.passive="getOptimizedClickHandler(item).touchmove"
						@touchend.passive="getOptimizedClickHandler(item).touchend"
						@click="getOptimizedClickHandler(item).click"
						@keydown.enter.prevent="selectItem(item)"
						@keydown.space.prevent="selectItem(item)"
						:class="[
							'group relative flex flex-col bg-white border rounded-lg p-2 sm:p-2.5 touch-manipulation transition-[border-color,box-shadow] duration-100 cursor-pointer hover:border-pos-action hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pos-action focus-visible:ring-offset-1',
							activeHighlightCode === item.item_code
								? 'border-pos-action ring-2 ring-pos-action ring-offset-1'
								: 'border-gray-200',
						]"
					>
						<!-- Stock Badge -->
						<div
							v-if="(item.is_stock_item || item.is_bundle) && !item.has_variants"
							:class="[
								'absolute -top-1.5 -end-1.5 rounded-md shadow-sm z-10 border-2 border-white select-none pointer-events-none',
								'min-w-[1.75rem] px-1.5 py-0.5 text-xs font-semibold text-center tabular-nums',
								getItemStockStatus(item).color,
								getItemStockStatus(item).textColor,
							]"
							:title="getItemStockStatus(item).label"
						>
							{{ Math.floor(item.actual_qty ?? item.stock_qty ?? 0) }}
						</div>

						<!-- Item Image -->
						<div
							class="relative aspect-square bg-pos-panel rounded-md mb-2 overflow-hidden"
						>
							<div
								:class="[
									'w-full h-full',
									isOutOfStock(item) ? 'grayscale opacity-60' : '',
								]"
							>
								<LazyImage
									v-if="item.image"
									:src="item.image"
									:alt="item.item_name"
									container-class="relative w-full h-full"
									img-class="w-full h-full object-cover"
									root-margin="100px"
								>
									<template #error>
										<svg
											class="h-8 w-8 sm:h-10 sm:w-10 text-gray-300"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
											/>
										</svg>
									</template>
								</LazyImage>
								<div v-else class="w-full h-full flex items-center justify-center">
									<svg
										class="h-8 w-8 sm:h-10 sm:w-10 text-gray-300"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
										/>
									</svg>
								</div>
							</div>

							<!-- Out of stock: always visible, no hover needed -->
							<div
								v-if="isOutOfStock(item)"
								class="absolute inset-x-0 bottom-0 bg-red-700 text-white text-xs font-semibold text-center py-1"
							>
								{{ getItemStockStatus(item).label }}
							</div>
						</div>

						<!-- Item Details -->
						<div class="min-w-0 flex flex-col flex-1">
							<h3
								dir="auto"
								class="text-pos-sm font-medium text-pos-ink line-clamp-2 leading-snug min-h-[2.75em]"
								:title="item.item_name"
							>
								{{ item.item_name }}
							</h3>
							<p
								v-if="item.attributes"
								dir="auto"
								class="text-xs text-gray-600 truncate leading-tight mt-0.5"
							>
								{{ Object.values(item.attributes).join(" / ") }}
							</p>
							<div class="mt-auto pt-1 flex items-center justify-between gap-1 min-h-target">
								<p class="min-w-0 truncate leading-tight">
									<span class="text-[14px] font-semibold text-pos-ink tabular-nums">{{
										formatCurrency(item.rate || item.price_list_rate || 0)
									}}</span>
									<span v-if="isNonDefaultUom(item)" class="text-xs text-gray-500">
										/ {{ item.uom }}</span
									>
								</p>
								<!-- Other warehouses: visible affordance (was a hidden long-press) -->
								<button
									v-if="(item.is_stock_item || item.is_bundle) && !isOutOfStock(item)"
									type="button"
									class="flex-shrink-0 flex items-center justify-center min-h-target min-w-target -me-1.5 rounded-md text-gray-500 hover:text-pos-action hover:bg-pos-action-soft pos-focus"
									:title="__('Check availability in other warehouses')"
									:aria-label="__('Check availability in other warehouses')"
									@touchstart.stop
									@touchend.stop
									@click.stop="showWarehouseAvailability(item)"
									@keydown.enter.stop
									@keydown.space.stop
								>
									<svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
								</button>
							</div>
							<!-- Out of stock: offer the other warehouses as a labelled action -->
							<button
								v-if="isOutOfStock(item)"
								type="button"
								class="pos-btn pos-btn-outline w-full mt-1 text-pos-action"
								@touchstart.stop
								@touchend.stop
								@click.stop="showWarehouseAvailability(item)"
								@keydown.enter.stop
								@keydown.space.stop
							>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
								</svg>
								{{ __("Other warehouses") }}
							</button>
						</div>
					</div>
				</div>

				<!-- Loading More Indicator for Grid View -->
				<div v-if="loadingMore" class="flex justify-center items-center py-4">
					<div
						class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"
					></div>
					<p class="ms-2 text-xs text-gray-500">{{ __("Loading more items...") }}</p>
				</div>

				<!-- End of Results Indicator - Show on last page when no more data -->
				<div
					v-else-if="
						filteredItems.length > 0 &&
						!searchTerm &&
						currentPage === totalPages &&
						totalPages >= 1
					"
					class="flex justify-center items-center py-3"
				>
					<p class="text-xs text-gray-500">{{ __("All items loaded") }}</p>
				</div>

				<!-- Search Results Count -->
				<div
					v-else-if="searchTerm && filteredItems.length > 0"
					class="flex justify-center items-center py-3"
				>
					<p class="text-xs text-gray-500">
						{{ __("{0} items found", [filteredItems.length]) }}
					</p>
				</div>
			</div>

			<!-- Pagination Controls for Grid View -->
			<ItemsPagination
				v-if="totalPages > 1"
				:current-page="currentPage"
				:total-pages="totalPages"
				:items-per-page="itemsPerPage"
				:total="paginationTotal"
				@go="goToPage"
			/>
		</div>

		<!-- Table View -->
		<div
			v-if="viewMode === 'list'"
			key="list"
			class="flex-1 flex flex-col overflow-hidden min-h-0"
		>
			<div
				ref="listScrollContainer"
				class="flex-1 overflow-x-auto overflow-y-auto"
				style="min-height: 0"
			>
				<table
					v-if="displayedItems.length > 0"
					class="min-w-full divide-y divide-gray-200"
				>
					<thead class="bg-gray-50 sticky top-0 z-10">
						<tr>
							<th
								scope="col"
								class="px-2 sm:px-3 py-2 sm:py-2.5 text-start text-xs font-semibold text-gray-700 bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[50px] sm:w-[60px]"
							>
								{{ __("Image") }}
							</th>
							<th
								scope="col"
								class="px-2 sm:px-3 py-2 sm:py-2.5 text-start text-xs font-semibold text-gray-700 bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 max-w-[120px] sm:max-w-[180px] md:max-w-[200px]"
							>
								{{ __("Name") }}
							</th>
							<th
								v-if="settingsStore.displayItemCode"
								scope="col"
								class="hidden sm:table-cell px-2 sm:px-3 py-2 sm:py-2.5 text-start text-xs font-semibold text-gray-700 bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 sm:max-w-[150px]"
							>
								{{ __("Code") }}
							</th>
							<th
								scope="col"
								class="px-2 sm:px-3 py-2 sm:py-2.5 text-start text-xs font-semibold text-gray-700 bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[70px] sm:w-[100px]"
							>
								{{ __("Rate") }}
							</th>
							<th
								scope="col"
								class="px-2 sm:px-3 py-2 sm:py-2.5 text-start text-xs font-semibold text-gray-700 bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[70px] sm:w-[100px]"
							>
								{{ __("Qty") }}
							</th>
						</tr>
					</thead>
					<tbody class="bg-white divide-y divide-gray-200">
						<tr
							v-for="item in displayedItems"
							:key="item.item_code"
							@touchstart.passive="getOptimizedClickHandler(item).touchstart"
							@touchmove.passive="getOptimizedClickHandler(item).touchmove"
							@touchend.passive="getOptimizedClickHandler(item).touchend"
							@click="getOptimizedClickHandler(item).click"
							tabindex="0"
							:data-item-code="item.item_code"
							@keydown.enter.prevent="selectItem(item)"
							@keydown.space.prevent="selectItem(item)"
							:class="activeHighlightCode === item.item_code ? 'bg-pos-action-soft ring-2 ring-inset ring-pos-action' : ''"
							class="group cursor-pointer focus-visible:outline-none focus-visible:bg-pos-action-soft focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-pos-action hover:bg-blue-50 hover:shadow-md transition-[background-color,box-shadow] duration-100 touch-manipulation active:bg-blue-100"
						>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[50px] sm:w-[60px]">
								<div
									class="w-8 h-8 sm:w-10 sm:h-10 bg-gray-100 rounded flex items-center justify-center overflow-hidden"
								>
									<LazyImage
										v-if="item.image"
										:src="item.image"
										:alt="item.item_name"
										container-class="relative w-full h-full"
										img-class="w-full h-full object-cover"
										root-margin="100px"
									>
										<template #error>
											<svg
												class="h-4 w-4 sm:h-5 sm:w-5 text-gray-300"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
												/>
											</svg>
										</template>
									</LazyImage>
									<svg
										v-else
										class="h-4 w-4 sm:h-5 sm:w-5 text-gray-300"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
										/>
									</svg>
								</div>
							</td>
							<td
								class="px-2 sm:px-3 py-2 max-w-[120px] sm:max-w-[180px] md:max-w-[200px]"
							>
								<div
									dir="auto"
									class="text-pos-sm font-medium text-pos-ink truncate"
									:title="item.item_name"
								>
									{{ item.item_name }}
								</div>
								<div
									v-if="item.attributes"
									dir="auto"
									class="text-xs text-gray-600 truncate leading-tight"
								>
									{{ Object.values(item.attributes).join(" / ") }}
								</div>
							</td>
							<td
								v-if="settingsStore.displayItemCode"
								class="hidden sm:table-cell px-2 sm:px-3 py-2 whitespace-nowrap sm:max-w-[150px]"
							>
								<div
									dir="ltr"
									class="text-pos-sm text-gray-600 truncate tabular-nums"
									:title="item.item_code"
								>
									{{ item.item_code }}
								</div>
							</td>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[70px] sm:w-[100px]">
								<div class="text-pos-sm font-semibold text-pos-ink tabular-nums">
									{{ formatCurrency(item.rate || item.price_list_rate || 0) }}
								</div>
								<!-- Unit merged into the rate cell; only shown when not the stock unit -->
								<div v-if="isNonDefaultUom(item)" class="text-xs text-gray-500">
									/ {{ item.uom }}
								</div>
							</td>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[70px] sm:w-[100px]">
								<div
									v-if="
										(item.is_stock_item || item.is_bundle) &&
										!item.has_variants
									"
									class="flex items-center gap-0.5"
								>
									<span
										:class="[
											'inline-block min-w-[2rem] px-2 py-1 rounded-md text-pos-sm font-semibold text-center tabular-nums select-none',
											getItemStockStatus(item).color,
											getItemStockStatus(item).textColor,
										]"
										:title="getItemStockStatus(item).label"
									>
										{{ Math.floor(item.actual_qty ?? item.stock_qty ?? 0) }}
									</span>
									<button
										type="button"
										class="flex items-center justify-center min-h-target min-w-target rounded-md text-gray-500 hover:text-pos-action hover:bg-pos-action-soft pos-focus"
										:title="__('Check availability in other warehouses')"
										:aria-label="__('Check availability in other warehouses')"
										@touchstart.stop
										@touchend.stop
										@click.stop="showWarehouseAvailability(item)"
										@keydown.enter.stop
										@keydown.space.stop
									>
										<svg class="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
										</svg>
									</button>
								</div>
								<!-- Template stock is per variant; the list payload carries no sum -->
								<span
									v-else-if="item.has_variants"
									class="text-pos-sm text-gray-600"
									:title="__('Stock varies by variant')"
								>
									{{ __("variants") }}
								</span>
								<span v-else class="text-pos-sm text-gray-500">
									{{ __("N/A") }}
								</span>
							</td>
						</tr>
						<!-- Loading More Indicator Row -->
						<tr v-if="loadingMore">
							<td colspan="5" class="px-2 sm:px-3 py-4 text-center bg-white">
								<div class="flex justify-center items-center">
									<div
										class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"
									></div>
									<p class="ms-2 text-xs text-gray-500">
										{{ __("Loading more items...") }}
									</p>
								</div>
							</td>
						</tr>

						<!-- End of Results Indicator Row - Show on last page when no more data -->
						<tr
							v-else-if="
								filteredItems.length > 0 &&
								!searchTerm &&
								currentPage === totalPages &&
								totalPages >= 1
							"
						>
							<td colspan="5" class="px-2 sm:px-3 py-3 text-center bg-white">
								<p class="text-xs text-gray-400">{{ __("All items loaded") }}</p>
							</td>
						</tr>

						<!-- Search Results Count Row -->
						<tr v-else-if="searchTerm && filteredItems.length > 0">
							<td colspan="5" class="px-2 sm:px-3 py-3 text-center bg-white">
								<p class="text-xs text-gray-500">
									{{ __("{0} items found", [filteredItems.length]) }}
								</p>
							</td>
						</tr>
					</tbody>
				</table>
			</div>

			<!-- Pagination Controls for List View -->
			<ItemsPagination
				v-if="totalPages > 1"
				:current-page="currentPage"
				:total-pages="totalPages"
				:items-per-page="itemsPerPage"
				:total="paginationTotal"
				@go="goToPage"
			/>
		</div>
	</div>

	<!-- Warehouse Availability Dialog -->
	<WarehouseAvailabilityDialog
		v-if="warehouseDialogItem"
		v-model="showWarehouseDialog"
		:item-code="warehouseDialogItem.itemCode"
		:item-name="warehouseDialogItem.itemName"
		:uom="warehouseDialogItem.uom"
		:company="warehouseDialogItem.company"
	/>
</template>

<script setup>
import LazyImage from "@/components/common/LazyImage.vue";
import ItemsPagination from "@/components/sale/ItemsPagination.vue";
import WarehouseAvailabilityDialog from "@/components/sale/WarehouseAvailabilityDialog.vue";
import { useItemSearchStore } from "@/stores/itemSearch";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { useStock } from "@/composables/useStock";
import { useItemsViewMode } from "@/composables/useItemsViewMode";
import { session } from "@/data/session";
import { useDialogState } from "@/composables/useDialogState";
import { useSearchInput } from "@/composables/useSearchInput";
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { useToast } from "@/composables/useToast";
import { storeToRefs } from "pinia";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
	createOptimizedClickHandler,
	throttleRAF,
	addPassiveListener,
	runWhenIdle,
} from "@/utils/lowEndOptimizations";
import { performanceConfig } from "@/utils/performanceConfig";
import { shouldValidateItemStock } from "@/utils/stockValidator";

const props = defineProps({
	posProfile: String,
	cartItems: {
		type: Array,
		default: () => [],
	},
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	// Item code of the keyboard-highlighted result (ring on that card/row)
	highlightedCode: {
		type: String,
		default: null,
	},
});

const emit = defineEmits(["item-selected"]);

// Use composables
const { getItemStockStatus } = useStock();
const settingsStore = usePOSSettingsStore();
const { showError, showWarning } = useToast();
const { isAnyDialogOpen } = useDialogState();

// Use Pinia store
const itemStore = useItemSearchStore();
const {
	filteredItems,
	searchTerm,
	selectedItemGroup,
	selectedBrand,
	itemGroups,
	brands,
	loading,
	loadingMore,
	hasMore,
	cacheSyncing,
	cacheStats,
	sortBy,
	sortOrder,
	totalServerItems,
} = storeToRefs(itemStore);

// Search input composable — owns search/scanner state, timers, concurrency
const {
	searchInputRef,
	scannerEnabled,
	autoAddEnabled,
	handleSearchInput,
	handleKeyDown,
	handleSearchClick,
	toggleBarcodeScanner,
	toggleAutoAdd,
	focusSearchInput,
	clearSearchAndResetInput,
	highlightedCode: searchHighlightedCode = ref(null),
	cleanup: cleanupSearchInput,
} = useSearchInput({
	itemStore,
	onItemFound: selectItem,
	showWarning,
	isAnyDialogOpen,
});

// Keyboard-highlighted result: the parent's prop wins, else the search composable's
const activeHighlightCode = computed(
	() => props.highlightedCode ?? searchHighlightedCode.value ?? null
);

// Local state
// Grid/list choice, remembered per user
const { viewMode, userManuallySetView, setViewMode } = useItemsViewMode(session.user);
const itemThreshold = ref(50); // Threshold for auto-switching to list view
const lastAutoSwitchCount = ref(0);
const showSortDropdown = ref(false); // Sort dropdown visibility
const skipPageReset = ref(false); // Skip page reset when navigating via pagination

// Warehouse availability dialog state
const showWarehouseDialog = ref(false);
const warehouseDialogItem = ref(null);

// Infinite scroll refs
const gridScrollContainer = ref(null);
const listScrollContainer = ref(null);

// Store scroll listener cleanup functions
const scrollCleanupFns = ref([]);

// Pagination state (for client-side display)
const currentPage = ref(1);
const itemsPerPage = ref(performanceConfig.get("itemsPerPage") || 100);
const lastFilterSignature = ref("");

// Computed paginated items — server fetches one page at a time,
// so filteredItems already contains only the current page's items.
const displayedItems = computed(() => {
	if (!filteredItems.value) return [];
	return filteredItems.value;
});

// Total item count for pagination display
const paginationTotal = computed(() => {
	if (searchTerm.value?.trim()) return filteredItems.value?.length || 0;
	return totalServerItems.value || filteredItems.value?.length || 0;
});

// Total pages is based on server-side total count (not local array length).
// During search, fall back to local results since server count is for browsing.
const totalPages = computed(() => {
	if (searchTerm.value?.trim()) {
		// During search, we don't paginate server-side — show all results
		return 1;
	}
	if (totalServerItems.value > 0) {
		return Math.ceil(totalServerItems.value / itemsPerPage.value);
	}
	if (!filteredItems.value) return 0;
	return Math.ceil(filteredItems.value.length / itemsPerPage.value);
});

const SEARCH_PLACEHOLDERS = Object.freeze({
	auto: __("Auto-Add ON - Type or scan barcode"),
	scanner: __("Scanner ON - Enable Auto for automatic addition"),
	default: __("Search by item code, name, item group or scan barcode"),
});

// Sort configuration
const BASE_SORT_OPTIONS = Object.freeze([
	{
		field: "name",
		label: __("Name"),
		icon: "M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z",
	},
	{
		field: "quantity",
		label: __("Quantity"),
		icon: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
	},
	{
		field: "price",
		label: __("Price"),
		icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
	},
	{
		field: "item_code",
		label: __("Item Code"),
		icon: "M7 20l4-16m2 16l4-16M6 9h14M4 15h14",
	},
]);

const CONTEXT_SORT_OPTIONS = Object.freeze({
	brand: {
		field: "brand",
		label: __("Brand"),
		icon: "M20 13V7a2 2 0 00-2-2h-4V3H10v2H6a2 2 0 00-2 2v6M8 21h8a2 2 0 002-2v-5H6v5a2 2 0 002 2z",
	},
	item_group: {
		field: "item_group",
		label: __("Item Group"),
		icon: "M9 12l2 2 4-4m5.586 1.414l-6.172 6.172a2 2 0 01-2.828 0L3.414 9.414a2 2 0 010-2.828l6.172-6.172a2 2 0 012.828 0l8.172 8.172a2 2 0 010 2.828z",
	},
});

const SORT_ICONS = Object.freeze({
	ascending: "M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12",
	descending: "M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4",
	inactive: "M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4",
});

const searchMode = computed(() => {
	if (autoAddEnabled.value) {
		return "auto";
	}

	if (scannerEnabled.value) {
		return "scanner";
	}

	return "default";
});

const searchPlaceholder = computed(() => SEARCH_PLACEHOLDERS[searchMode.value]);
const isBrandSortActive = computed(() => sortBy.value === "brand");
const sortOptions = computed(() => {
	// Context switcher:
	// - In Item Group mode, offer Brand.
	// - In Brand mode, offer Item Group.
	const contextSort = isBrandSortActive.value
		? CONTEXT_SORT_OPTIONS.item_group
		: CONTEXT_SORT_OPTIONS.brand;

	return [
		BASE_SORT_OPTIONS[0],
		contextSort,
		BASE_SORT_OPTIONS[1],
		BASE_SORT_OPTIONS[2],
		BASE_SORT_OPTIONS[3],
	];
});
const activeFilterValue = computed(() =>
	isBrandSortActive.value ? selectedBrand.value : selectedItemGroup.value
);
const activeFilterOptions = computed(() =>
	isBrandSortActive.value
		? (brands.value || []).map((b) => ({ value: b.brand, label: b.brand }))
		: (itemGroups.value || []).map((g) => ({ value: g.item_group, label: g.item_group }))
);
const selectedFilterLabel = computed(() => selectedBrand.value || selectedItemGroup.value || null);

// Watch for cart items and pos profile changes (optimized - uses length + hash instead of deep watch)
// Tracks: length, item_code, quantity, and amount to detect all cart changes including array replacements
watch(
	() =>
		`${props.cartItems.length}-${props.cartItems
			.map((i) => `${i.item_code}:${i.quantity || 0}:${i.amount || 0}`)
			.join("|")}`,
	() => {
		itemStore.setCartItems(props.cartItems);
	},
	{ immediate: true, flush: "sync" } // Synchronous to ensure immediate stock updates
);

watch(
	() => props.posProfile,
	(newProfile) => {
		if (newProfile) {
			itemStore.setPosProfile(newProfile);
		}
	},
	{ immediate: true }
);

// Reset to page 1 when filtered items meaningfully change (group switch, search, etc.)
// Skip reset when the change is from pagination navigation (fetchPage)
watch(
	filteredItems,
	(newItems) => {
		if (!newItems) return;

		// Skip page reset for pagination-driven changes
		if (skipPageReset.value) {
			skipPageReset.value = false;
			return;
		}

		const itemCount = newItems.length;
		const firstCode = itemCount > 0 ? newItems[0]?.item_code || "" : "";
		const lastCode = itemCount > 0 ? newItems[itemCount - 1]?.item_code || "" : "";
		const middleIndex = itemCount > 2 ? Math.floor(itemCount / 2) : -1;
		const middleCode = middleIndex >= 0 ? newItems[middleIndex]?.item_code || "" : "";
		const signature = `${itemCount}|${firstCode}|${middleCode}|${lastCode}`;

		if (signature !== lastFilterSignature.value) {
			currentPage.value = 1;
			lastFilterSignature.value = signature;
		}

		// Only auto-switch if user hasn't manually set a preference
		// and we're in grid view with many items
		if (
			!userManuallySetView.value &&
			viewMode.value === "grid" &&
			itemCount > itemThreshold.value
		) {
			if (lastAutoSwitchCount.value !== itemCount) {
				viewMode.value = "list";
				lastAutoSwitchCount.value = itemCount;
			}
		} else if (itemCount <= itemThreshold.value) {
			lastAutoSwitchCount.value = 0;
		}
	},
	{ immediate: false }
);

// Throttle scroll handler for better performance
let scrollTimeout = null;

// Scroll handler — pagination controls handle page navigation now.
// Scroll is only used for scrolling within the current page.
const handleScrollRAF = throttleRAF(() => {
	// No-op: pagination handles page navigation via goToPage
});

function handleScroll(event) {
	handleScrollRAF(event);
}

onMounted(() => {
	// Items are now loaded automatically by setPosProfile() in the watcher
	// This ensures item group filters are loaded BEFORE fetching items

	// Add passive scroll listeners for better performance
	// Only bind to the currently active view
	if (viewMode.value === "grid" && gridScrollContainer.value) {
		const cleanup = addPassiveListener(gridScrollContainer.value, "scroll", handleScroll, {
			passive: true,
		});
		scrollCleanupFns.value.push(cleanup);
	} else if (viewMode.value === "list" && listScrollContainer.value) {
		const cleanup = addPassiveListener(listScrollContainer.value, "scroll", handleScroll, {
			passive: true,
		});
		scrollCleanupFns.value.push(cleanup);
	}

	// Add click outside listener for sort dropdown
	document.addEventListener("click", handleClickOutside);

	if (chipStripRef.value && typeof ResizeObserver !== "undefined") {
		chipResizeObserver = new ResizeObserver(updateChipScroll);
		chipResizeObserver.observe(chipStripRef.value);
	}
});

onUnmounted(() => {
	// Cleanup background sync when component unmounts
	itemStore.cleanup();

	// Clear scroll timeout
	if (scrollTimeout) {
		clearTimeout(scrollTimeout);
		scrollTimeout = null;
	}

	// Cleanup passive listeners
	scrollCleanupFns.value.forEach((cleanup) => cleanup());
	scrollCleanupFns.value = [];

	// Clear handlers and timers
	optimizedClickHandlers.clear();
	chipResizeObserver?.disconnect();
	cleanupSearchInput();

	// Remove click outside listener for sort dropdown
	document.removeEventListener("click", handleClickOutside);
});

// Create optimized click handlers for better touch response
const optimizedClickHandlers = new Map();

function getOptimizedClickHandler(item) {
	const key = item.item_code;
	if (!optimizedClickHandlers.has(key)) {
		const handler = createOptimizedClickHandler(
			() => {
				handleItemClick(item.item_code);
			},
			{
				feedback: true,
			}
		);
		optimizedClickHandlers.set(key, handler);
	}
	return optimizedClickHandlers.get(key);
}

/**
 * Validates stock and emits item-selected if valid
 * @param {Object} item - Item to select
 * @param {boolean} autoAdd - Auto-add flag for barcode scanning
 * @returns {boolean} - True if item was emitted, false if blocked
 */
function selectItem(item, autoAdd = false) {
	if (!item) return false;

	// Early out-of-stock guard — full qty validation happens in cartStore.addItem()
	if (
		!item.has_variants &&
		settingsStore.shouldEnforceStockValidation() &&
		shouldValidateItemStock(item)
	) {
		const qty = item.actual_qty ?? item.stock_qty ?? 0;
		if (qty <= 0) {
			showError(
				__('"{0}" is out of stock in warehouse "{1}".', [
					item.item_name,
					item.warehouse || "",
				])
			);
			return false;
		}
	}

	emit("item-selected", item, autoAdd);
	return true;
}

function handleItemClick(itemCode) {
	const item = filteredItems.value.find((i) => i.item_code === itemCode);
	selectItem(item);
}

function isOutOfStock(item) {
	return Boolean(
		(item.is_stock_item || item.is_bundle) &&
			!item.has_variants &&
			(item.actual_qty ?? item.stock_qty ?? 0) <= 0
	);
}

// The stock unit is the default, so only another unit is worth printing
function isNonDefaultUom(item) {
	return Boolean(item.uom && item.uom !== item.stock_uom);
}

// Category strip: which sides have hidden chips (drives the fade + scroll buttons)
const chipStripRef = ref(null);
const chipScroll = ref({ start: false, end: false });
let chipResizeObserver = null;

function updateChipScroll() {
	const el = chipStripRef.value;
	if (!el) return;
	// scrollLeft is negative in RTL, so measure the distance from the start edge
	const offset = Math.abs(el.scrollLeft);
	chipScroll.value = {
		start: offset > 2,
		end: offset < el.scrollWidth - el.clientWidth - 2,
	};
}

function scrollChips(direction) {
	const el = chipStripRef.value;
	if (!el) return;
	const rtl = getComputedStyle(el).direction === "rtl" ? -1 : 1;
	el.scrollBy({ left: direction * rtl * el.clientWidth * 0.8, behavior: "smooth" });
}

watch(activeFilterOptions, () => nextTick(updateChipScroll));

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

// Show warehouse availability dialog
function showWarehouseAvailability(item) {
	warehouseDialogItem.value = {
		itemCode: item.item_code,
		itemName: item.item_name,
		uom: item.uom || item.stock_uom || "Nos",
		company: settingsStore.company,
	};
	showWarehouseDialog.value = true;
}

// Expose methods for parent component
defineExpose({
	loadItems: () => itemStore.loadAllItems(props.posProfile),
	loadItemGroups: () => itemStore.loadItemGroups(),
	loadMoreItems: () => itemStore.loadMoreItems(),
	focusSearchInput,
});

// Watch for view mode changes and rebind scroll listeners
watch(viewMode, async () => {
	// Wait for DOM to update
	await nextTick();

	// Clean up existing listeners
	scrollCleanupFns.value.forEach((cleanup) => cleanup());
	scrollCleanupFns.value = [];

	// Rebind listeners to the new active container
	if (viewMode.value === "grid" && gridScrollContainer.value) {
		const cleanup = addPassiveListener(gridScrollContainer.value, "scroll", handleScroll, {
			passive: true,
		});
		scrollCleanupFns.value.push(cleanup);
	} else if (viewMode.value === "list" && listScrollContainer.value) {
		const cleanup = addPassiveListener(listScrollContainer.value, "scroll", handleScroll, {
			passive: true,
		});
		scrollCleanupFns.value.push(cleanup);
	}
});

function handleAllFilterClick() {
	if (isBrandSortActive.value) {
		itemStore.setSelectedBrand(null);
		return;
	}
	itemStore.setSelectedItemGroup(null);
}

function handleFilterClick(value) {
	if (isBrandSortActive.value) {
		itemStore.setSelectedBrand(value);
		return;
	}
	itemStore.setSelectedItemGroup(value);
}

// Pagination functions — each page fetches fresh data from server
function goToPage(page) {
	if (page >= 1 && page <= totalPages.value && page !== currentPage.value) {
		skipPageReset.value = true;
		currentPage.value = page;
		itemStore.fetchPage(page);
	}
}

// Sort dropdown functions
function toggleSortDropdown() {
	showSortDropdown.value = !showSortDropdown.value;
}

function handleSortToggle(field) {
	if (!field) {
		// Clear sorting
		itemStore.clearSortFilter();
		showSortDropdown.value = false;
		return;
	}

	// If clicking the same field, toggle between asc/desc
	if (sortBy.value === field) {
		const newOrder = sortOrder.value === "asc" ? "desc" : "asc";
		itemStore.setSortFilter(field, newOrder);
	} else {
		// New field - start with ascending
		itemStore.setSortFilter(field, "asc");
	}
}

watch(sortBy, async (newSortBy, oldSortBy) => {
	if (newSortBy === "brand") {
		await itemStore.loadBrands();
		if (selectedItemGroup.value) {
			await itemStore.setSelectedItemGroup(null);
		}
		return;
	}

	if (oldSortBy === "brand" && selectedBrand.value) {
		await itemStore.setSelectedBrand(null);
	}
});

function getSortLabel(sortByValue) {
	return (
		CONTEXT_SORT_OPTIONS[sortByValue]?.label ||
		BASE_SORT_OPTIONS.find((opt) => opt.field === sortByValue)?.label ||
		sortByValue
	);
}

function getSortIconState(field) {
	if (sortBy.value !== field) return "inactive";
	return sortOrder.value === "asc" ? "ascending" : "descending";
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
	if (showSortDropdown.value) {
		const dropdown = event.target.closest(".relative");
		if (
			!dropdown ||
			!dropdown.querySelector("button[data-sort-button]")?.contains(event.target)
		) {
			showSortDropdown.value = false;
		}
	}
}

// Check if an item can be added to cart based on stock
</script>

<style scoped>
/* Hide scrollbar for Chrome, Safari and Opera */
.scrollbar-hide::-webkit-scrollbar {
	display: none;
}

/* Hide scrollbar for IE, Edge and Firefox */
.scrollbar-hide {
	-ms-overflow-style: none; /* IE and Edge */
	scrollbar-width: none; /* Firefox */
}

/* Columns come from the product pane's width, not viewport breakpoints */
.pos-item-grid {
	grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
}

/* Performance optimizations for low-end devices */
.pos-item-grid > div {
	/* Tell browser which properties will change */
	will-change: opacity;
	/* Use GPU acceleration for transforms */
	transform: translateZ(0);
	/* Optimize for speed over quality */
	backface-visibility: hidden;
}

/* Optimize scroll containers */
.overflow-y-auto,
.overflow-x-auto {
	/* Enable smooth scrolling with GPU acceleration */
	-webkit-overflow-scrolling: touch;
	/* Create stacking context for better compositing */
	transform: translateZ(0);
	will-change: scroll-position;
}

/* Reduce paint areas */
.relative {
	/* Isolate paint regions */
	isolation: isolate;
}

/* Optimize images */
img {
	/* Use browser's image optimization */
	image-rendering: -webkit-optimize-contrast;
	image-rendering: crisp-edges;
}

/* Minimal transitions for performance */

/* Performance hints for list rows */
tbody tr {
	/* Optimize for compositing */
	will-change: opacity, background-color;
	/* Create rendering layer */
	contain: layout style paint;
}

/* Remove will-change when not hovering to save resources */
tbody tr:not(:hover):not(:active) {
	will-change: auto;
}
</style>
