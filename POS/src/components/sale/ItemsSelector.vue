<template>
	<div class="flex flex-col h-full bg-gray-50">
		<!-- Item Groups Filter Tabs -->
		<div class="px-1.5 sm:px-3 pt-1.5 sm:pt-3 pb-1.5 sm:pb-2 bg-white border-b border-gray-200">
			<div class="flex items-center space-x-1 sm:space-x-2 overflow-x-auto pb-1 scrollbar-hide snap-x snap-mandatory">
				<button
					@click="itemStore.setSelectedItemGroup(null)"
					:class="[
						'flex items-center space-x-1 sm:space-x-1.5 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg text-[10px] sm:text-xs font-medium whitespace-nowrap transition-[background-color,border-color] duration-75 touch-manipulation snap-start flex-shrink-0',
						!selectedItemGroup
							? 'bg-blue-50 text-blue-600 border-2 border-blue-500 shadow-sm'
							: 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 active:bg-gray-100',
					]"
				>
					<svg class="w-3.5 h-3.5 sm:w-4 sm:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
					</svg>
					<span>All Items</span>
				</button>
				<button
					v-for="group in itemGroups"
					:key="group.item_group"
					@click="itemStore.setSelectedItemGroup(group.item_group)"
					:class="[
						'flex items-center space-x-1 sm:space-x-1.5 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg text-[10px] sm:text-xs font-medium whitespace-nowrap transition-[background-color,border-color] duration-75 touch-manipulation snap-start flex-shrink-0',
						selectedItemGroup === group.item_group
							? 'bg-blue-50 text-blue-600 border-2 border-blue-500 shadow-sm'
							: 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 active:bg-gray-100',
					]"
				>
					<span>{{ group.item_group }}</span>
				</button>
			</div>
		</div>

		<!-- Cache Sync Indicator -->
		<div v-if="cacheSyncing" class="px-1.5 sm:px-3 py-1 bg-blue-50 border-b border-blue-200">
			<div class="flex items-center justify-center space-x-2 text-[10px] sm:text-xs text-blue-700">
				<div class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600"></div>
				<span>Syncing catalog in background... {{ cacheStats.items }} items cached</span>
			</div>
		</div>

		<!-- Search Bar with Barcode Scanner and View Controls -->
		<div class="px-1.5 sm:px-3 py-1.5 sm:py-2 bg-white border-b border-gray-200">
			<div class="flex items-center space-x-1 sm:space-x-2">
				<div class="flex-1 relative min-w-0">
					<!-- Search Icon -->
					<div class="absolute inset-y-0 left-0 pl-2 sm:pl-3 flex items-center pointer-events-none">
						<svg
							class="h-3.5 w-3.5 sm:h-4 sm:w-4 text-gray-400"
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
						type="text"
						:placeholder="searchPlaceholder"
						:class="[
							'w-full text-[11px] sm:text-sm border rounded-lg px-2 sm:px-3 py-2 pl-7 sm:pl-10 pr-16 sm:pr-24 focus:outline-none transition-all',
							autoAddEnabled
								? 'border-blue-400 bg-blue-50 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
								: scannerEnabled
								? 'border-green-400 bg-green-50 focus:ring-2 focus:ring-green-500 focus:border-transparent'
								: 'border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent'
						]"
						aria-label="Search items"
					/>
					<!-- Barcode Scan Icon and Auto-Add Toggle -->
					<div class="absolute inset-y-0 right-0 pr-1 sm:pr-2 flex items-center gap-0.5">
						<button
							@click="toggleBarcodeScanner"
							:class="[
								'p-1 sm:p-1.5 rounded transition-[background-color] duration-75 touch-manipulation',
								scannerEnabled
									? 'bg-green-100 hover:bg-green-200 active:bg-green-300 text-green-700'
									: 'hover:bg-gray-100 active:bg-gray-200 text-gray-600'
							]"
							:title="scannerEnabled ? 'Barcode Scanner: ON (Click to disable)' : 'Barcode Scanner: OFF (Click to enable)'"
							:aria-label="scannerEnabled ? 'Disable barcode scanner' : 'Enable barcode scanner'"
						>
							<svg class="w-3.5 h-3.5 sm:w-4 sm:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"/>
							</svg>
						</button>
						<button
							@click="toggleAutoAdd"
							:class="[
								'p-1 sm:p-1.5 rounded transition-[background-color] duration-75 flex items-center gap-0.5 text-[9px] sm:text-xs font-medium px-1 sm:px-2 touch-manipulation',
								autoAddEnabled
									? 'bg-blue-100 hover:bg-blue-200 active:bg-blue-300 text-blue-700'
									: 'hover:bg-gray-100 active:bg-gray-200 text-gray-600'
							]"
							:title="autoAddEnabled ? 'Auto-Add: ON - Press Enter to add items to cart' : 'Auto-Add: OFF - Click to enable automatic cart addition on Enter'"
							:aria-label="autoAddEnabled ? 'Disable auto-add' : 'Enable auto-add'"
						>
							<svg class="w-3 h-3 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
							</svg>
							<span class="hidden xs:inline">Auto</span>
						</button>
					</div>
				</div>
				<div class="flex items-center space-x-0.5 bg-gray-100 rounded-lg p-0.5 flex-shrink-0">
					<button
						@click="setViewMode('grid')"
						:class="[
							'p-1.5 sm:p-2 rounded transition-[background-color,box-shadow] duration-75 touch-manipulation',
							viewMode === 'grid' ? 'bg-white shadow-sm' : 'hover:bg-gray-200 active:bg-gray-300'
						]"
						title="Grid View"
						:aria-label="'Switch to grid view'"
					>
						<svg class="w-4 h-4 sm:w-4.5 sm:h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/>
						</svg>
					</button>
					<button
						@click="setViewMode('list')"
						:class="[
							'p-1.5 sm:p-2 rounded transition-[background-color,box-shadow] duration-75 touch-manipulation',
							viewMode === 'list' ? 'bg-white shadow-sm' : 'hover:bg-gray-200 active:bg-gray-300'
						]"
						title="List View"
						:aria-label="'Switch to list view'"
					>
						<svg class="w-4 h-4 sm:w-4.5 sm:h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
						</svg>
					</button>
				</div>

				<!-- Sort Dropdown -->
				<div class="relative z-50">
					<button
						@click="toggleSortDropdown"
						:class="[
							'p-1.5 sm:p-2 rounded-lg transition-[background-color,box-shadow] duration-75 touch-manipulation border',
							sortBy
								? 'bg-blue-50 border-blue-400 text-blue-700 shadow-sm'
								: 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100'
						]"
						:title="sortBy ? `Sorted by ${getSortLabel(sortBy)} (${sortOrder === 'asc' ? 'A-Z' : 'Z-A'})` : 'Sort items'"
						:aria-label="'Sort items'"
					>
						<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/>
						</svg>
					</button>

					<!-- Dropdown Menu -->
					<div
						v-if="showSortDropdown"
						@click.stop
						class="absolute right-0 mt-1 w-56 bg-white rounded-lg shadow-xl border border-gray-200 z-[9999]"
						style="box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);"
					>
						<div class="py-2">
							<div class="px-3 py-2 text-xs font-semibold text-gray-500 uppercase border-b border-gray-100">
								Sort Items
							</div>
							<div class="py-1">
								<!-- Clear Sort -->
								<button
									@click="handleSortToggle(null)"
									:class="[
										'w-full px-3 py-2 text-sm transition-colors flex items-center justify-between group',
										!sortBy ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-50'
									]"
								>
									<span class="flex items-center gap-2.5">
										<svg class="w-4 h-4 text-gray-400 group-hover:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
										</svg>
										<span>No Sorting</span>
									</span>
								</button>

								<div class="h-px bg-gray-100 my-1"></div>

								<!-- Sort Options Loop -->
								<button
									v-for="option in SORT_OPTIONS"
									:key="option.field"
									@click="handleSortToggle(option.field)"
									:class="[
										'w-full px-3 py-2 text-sm transition-colors flex items-center justify-between group',
										sortBy === option.field ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-50'
									]"
								>
									<span class="flex items-center gap-2.5">
										<svg class="w-4 h-4 text-gray-400 group-hover:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="option.icon"/>
										</svg>
										<span>{{ option.label }}</span>
									</span>
									<!-- Sort direction icon -->
									<svg
										class="w-5 h-5"
										:class="sortBy === option.field ? 'text-blue-600' : 'text-gray-300'"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="SORT_ICONS[getSortIconState(option.field)]"/>
									</svg>
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Initial Loading State - Only for first load -->
		<div v-if="loading && !filteredItems" class="flex-1 flex items-center justify-center p-3">
			<div class="text-center py-8">
				<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
				<p class="mt-3 text-xs text-gray-500">Loading items...</p>
			</div>
		</div>

		<!-- Empty State - Simple, no animation -->
		<div
			v-else-if="(!filteredItems || filteredItems.length === 0)"
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
				<p v-if="searchTerm || selectedItemGroup" class="mt-2 text-xs font-medium text-gray-700">
					No results for <span v-if="searchTerm">"{{ searchTerm }}"</span><span v-if="searchTerm && selectedItemGroup"> in </span><span v-if="selectedItemGroup">{{ selectedItemGroup }}</span>
				</p>
				<p v-else class="mt-2 text-xs text-gray-500">No items available</p>
			</div>
		</div>

		<!-- Grid View -->
		<div v-if="viewMode === 'grid'" key="grid" class="flex-1 flex flex-col overflow-hidden min-h-0">
			<div
				ref="gridScrollContainer"
				class="flex-1 overflow-y-auto p-1.5 sm:p-3"
				style="min-height: 0;"
			>
				<div class="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-1.5 sm:gap-2.5">
					<div
						v-for="item in paginatedItems"
						:key="item.item_code"
						@touchstart.passive="getOptimizedClickHandler(item).touchstart"
						@touchmove.passive="getOptimizedClickHandler(item).touchmove"
						@touchend.passive="getOptimizedClickHandler(item).touchend"
						@click="getOptimizedClickHandler(item).click"
						:class="[
							'relative bg-white border border-gray-200 rounded-lg p-1.5 sm:p-2.5 touch-manipulation transition-[border-color,box-shadow] duration-100 cursor-pointer hover:border-blue-400 hover:shadow-md',
						]"
					>
						<!-- Stock Badge - Positioned at top right of card -->
						<!-- Show for stock items and bundles (bundles now have calculated actual_qty) -->
						<div
							v-if="item.is_stock_item || item.is_bundle"
							:class="[
								'absolute -top-1.5 -right-1.5 sm:-top-2 sm:-right-2 rounded-md shadow-lg z-10',
								'px-2 sm:px-2.5 py-1 sm:py-1',
								'text-[10px] sm:text-xs font-bold',
								'border-2 border-white',
								getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).color,
								getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).textColor
							]"
							:title="`${getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).label}: ${Math.floor(item.actual_qty ?? item.stock_qty ?? 0)} ${item.is_bundle ? 'Bundles' : (item.uom || item.stock_uom || 'Nos')}`"
						>
							{{ Math.floor(item.actual_qty ?? item.stock_qty ?? 0) }}
						</div>

						<!-- Item Image -->
						<div class="relative aspect-square bg-gray-100 rounded-md mb-1.5 sm:mb-2 overflow-hidden">
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

						<!-- Item Details -->
						<div class="min-w-0">
							<h3 class="text-[10px] sm:text-xs font-semibold text-gray-900 truncate mb-0.5 leading-tight">
								{{ item.item_name }}
							</h3>
                                                        <p class="text-[9px] sm:text-[10px] text-gray-500 leading-tight">
                                                                <span class="font-semibold text-blue-600">{{ formatCurrency(item.rate || item.price_list_rate || 0) }}</span>
                                                                <span class="text-gray-400">/ {{ item.uom || item.stock_uom || 'Nos' }}</span>
                                                        </p>
						</div>
					</div>
				</div>

				<!-- Loading More Indicator for Grid View -->
				<div v-if="loadingMore" class="flex justify-center items-center py-4">
					<div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
					<p class="ml-2 text-xs text-gray-500">Loading more items...</p>
				</div>

				<!-- End of Results Indicator - Only show on last page or when all items fit in one page -->
				<div v-else-if="!hasMore && filteredItems.length > 0 && !searchTerm && (currentPage === totalPages || totalPages === 1)" class="flex justify-center items-center py-3">
					<p class="text-xs text-gray-400">All items loaded</p>
				</div>

				<!-- Search Results Count -->
				<div v-else-if="searchTerm && filteredItems.length > 0" class="flex justify-center items-center py-3">
					<p class="text-xs text-gray-500">{{ filteredItems.length }} items found</p>
				</div>
			</div>

			<!-- Pagination Controls for Grid View -->
			<div v-if="totalPages > 1" class="px-2 sm:px-3 py-2 bg-white border-t border-gray-200">
				<div class="flex flex-col sm:flex-row items-center justify-between gap-2">
					<div class="text-[10px] sm:text-xs text-gray-600 order-2 sm:order-1">
						{{ ((currentPage - 1) * itemsPerPage) + 1 }}-{{ Math.min(currentPage * itemsPerPage, filteredItems.length) }} of {{ filteredItems.length }}
					</div>
					<div class="flex items-center space-x-1 order-1 sm:order-2">
						<button
							@click="goToPage(1)"
							:disabled="currentPage === 1"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === 1
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to first page'"
						>
							<span class="hidden xs:inline">First</span>
							<span class="xs:hidden">«</span>
						</button>
						<button
							@click="previousPage"
							:disabled="currentPage === 1"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === 1
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to previous page'"
						>
							<span class="hidden xs:inline">Previous</span>
							<span class="xs:hidden">‹</span>
						</button>
						<div class="flex items-center space-x-0.5 sm:space-x-1">
							<button
								v-for="page in getPaginationRange()"
								:key="page"
								@click="goToPage(page)"
								:class="[
									'min-w-[28px] sm:min-w-[32px] px-1.5 sm:px-2.5 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color,border-color] duration-75 touch-manipulation',
									currentPage === page
										? 'bg-blue-600 text-white border-blue-600'
										: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
								]"
								:aria-label="'Go to page ' + page"
							>
								{{ page }}
							</button>
						</div>
						<button
							@click="nextPage"
							:disabled="currentPage === totalPages"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === totalPages
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to next page'"
						>
							<span class="hidden xs:inline">Next</span>
							<span class="xs:hidden">›</span>
						</button>
						<button
							@click="goToPage(totalPages)"
							:disabled="currentPage === totalPages"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === totalPages
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to last page'"
						>
							<span class="hidden xs:inline">Last</span>
							<span class="xs:hidden">»</span>
						</button>
					</div>
				</div>
			</div>
		</div>

		<!-- Table View -->
		<div v-if="viewMode === 'list'" key="list" class="flex-1 flex flex-col overflow-hidden min-h-0">
			<div
				ref="listScrollContainer"
				class="flex-1 overflow-x-auto overflow-y-auto"
				style="min-height: 0;"
			>
				<table v-if="paginatedItems.length > 0" class="min-w-full divide-y divide-gray-200">
					<thead class="bg-gray-50 sticky top-0 z-10">
						<tr>
							<th scope="col" class="px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[50px] sm:w-[60px]">Image</th>
							<th scope="col" class="px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 max-w-[120px] sm:max-w-[180px] md:max-w-[200px]">Name</th>
							<th scope="col" class="hidden sm:table-cell px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 sm:max-w-[150px]">Code</th>
							<th scope="col" class="px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[70px] sm:w-[100px]">Rate</th>
							<th scope="col" class="px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 w-[70px] sm:w-[100px]">Qty</th>
							<th scope="col" class="hidden md:table-cell px-2 sm:px-3 py-2 sm:py-2.5 text-left text-[10px] sm:text-xs font-semibold text-gray-700 uppercase tracking-wider bg-gray-50 border-b-2 border-gray-200 sticky top-0 z-10 md:w-[80px]">UOM</th>
						</tr>
					</thead>
					<tbody class="bg-white divide-y divide-gray-200">
						<tr
							v-for="item in paginatedItems"
							:key="item.item_code"
							@touchstart.passive="getOptimizedClickHandler(item).touchstart"
							@touchmove.passive="getOptimizedClickHandler(item).touchmove"
							@touchend.passive="getOptimizedClickHandler(item).touchend"
							@click="getOptimizedClickHandler(item).click"
							class="cursor-pointer hover:bg-blue-50 hover:shadow-md transition-[background-color,box-shadow] duration-100 touch-manipulation active:bg-blue-100"
						>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[50px] sm:w-[60px]">
								<div class="w-8 h-8 sm:w-10 sm:h-10 bg-gray-100 rounded flex items-center justify-center overflow-hidden">
									<LazyImage
										v-if="item.image"
										:src="item.image"
										:alt="item.item_name"
										container-class="relative w-full h-full"
										img-class="w-full h-full object-cover"
										root-margin="100px"
									>
										<template #error>
											<svg class="h-4 w-4 sm:h-5 sm:w-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
											</svg>
										</template>
									</LazyImage>
									<svg v-else class="h-4 w-4 sm:h-5 sm:w-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
									</svg>
								</div>
							</td>
							<td class="px-2 sm:px-3 py-2 max-w-[120px] sm:max-w-[180px] md:max-w-[200px]">
								<div class="text-xs sm:text-sm font-medium text-gray-900 truncate" :title="item.item_name">
									{{ item.item_name }}
								</div>
							</td>
							<td class="hidden sm:table-cell px-2 sm:px-3 py-2 whitespace-nowrap sm:max-w-[150px]">
								<div class="text-xs sm:text-sm text-gray-500 truncate" :title="item.item_code">{{ item.item_code }}</div>
							</td>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[70px] sm:w-[100px]">
								<div class="text-xs sm:text-sm font-semibold text-blue-600">{{ formatCurrency(item.rate || item.price_list_rate || 0) }}</div>
							</td>
							<td class="px-2 sm:px-3 py-2 whitespace-nowrap w-[70px] sm:w-[100px]">
								<span
									v-if="item.is_stock_item || item.is_bundle"
									:class="[
										'inline-block px-1.5 sm:px-3 py-0.5 sm:py-1.5 rounded-md shadow-sm',
										'text-[10px] sm:text-sm font-bold',
										getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).color,
										getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).textColor
									]"
									:title="`${getStockStatus(item.actual_qty ?? item.stock_qty ?? 0).label}: ${Math.floor(item.actual_qty ?? item.stock_qty ?? 0)} ${item.is_bundle ? 'Bundles' : (item.uom || item.stock_uom || 'Nos')}`"
								>
									{{ Math.floor(item.actual_qty ?? item.stock_qty ?? 0) }}
								</span>
								<span
									v-else
									class="text-xs sm:text-sm text-gray-400 italic"
								>
									N/A
								</span>
							</td>
							<td class="hidden md:table-cell px-2 sm:px-3 py-2 whitespace-nowrap md:w-[80px]">
								<div class="text-xs sm:text-sm text-gray-500">{{ item.uom || item.stock_uom || 'Nos' }}</div>
							</td>
						</tr>
						<!-- Loading More Indicator Row -->
						<tr v-if="loadingMore">
							<td colspan="6" class="px-2 sm:px-3 py-4 text-center bg-white">
								<div class="flex justify-center items-center">
									<div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
									<p class="ml-2 text-xs text-gray-500">Loading more items...</p>
								</div>
							</td>
						</tr>

						<!-- End of Results Indicator Row - Only show on last page or when all items fit in one page -->
						<tr v-else-if="!hasMore && filteredItems.length > 0 && !searchTerm && (currentPage === totalPages || totalPages === 1)">
							<td colspan="6" class="px-2 sm:px-3 py-3 text-center bg-white">
								<p class="text-xs text-gray-400">All items loaded</p>
							</td>
						</tr>

						<!-- Search Results Count Row -->
						<tr v-else-if="searchTerm && filteredItems.length > 0">
							<td colspan="6" class="px-2 sm:px-3 py-3 text-center bg-white">
								<p class="text-xs text-gray-500">{{ filteredItems.length }} items found</p>
							</td>
						</tr>
					</tbody>
				</table>
			</div>

			<!-- Pagination Controls for List View -->
			<div v-if="totalPages > 1" class="px-2 sm:px-3 py-2 bg-white border-t border-gray-200">
				<div class="flex flex-col sm:flex-row items-center justify-between gap-2">
					<div class="text-[10px] sm:text-xs text-gray-600 order-2 sm:order-1">
						{{ ((currentPage - 1) * itemsPerPage) + 1 }}-{{ Math.min(currentPage * itemsPerPage, filteredItems.length) }} of {{ filteredItems.length }}
					</div>
					<div class="flex items-center space-x-1 order-1 sm:order-2">
						<button
							@click="goToPage(1)"
							:disabled="currentPage === 1"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === 1
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to first page'"
						>
							<span class="hidden xs:inline">First</span>
							<span class="xs:hidden">«</span>
						</button>
						<button
							@click="previousPage"
							:disabled="currentPage === 1"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === 1
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to previous page'"
						>
							<span class="hidden xs:inline">Previous</span>
							<span class="xs:hidden">‹</span>
						</button>
						<div class="flex items-center space-x-0.5 sm:space-x-1">
							<button
								v-for="page in getPaginationRange()"
								:key="page"
								@click="goToPage(page)"
								:class="[
									'min-w-[28px] sm:min-w-[32px] px-1.5 sm:px-2.5 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color,border-color] duration-75 touch-manipulation',
									currentPage === page
										? 'bg-blue-600 text-white border-blue-600'
										: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
								]"
								:aria-label="'Go to page ' + page"
							>
								{{ page }}
							</button>
						</div>
						<button
							@click="nextPage"
							:disabled="currentPage === totalPages"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === totalPages
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to next page'"
						>
							<span class="hidden xs:inline">Next</span>
							<span class="xs:hidden">›</span>
						</button>
						<button
							@click="goToPage(totalPages)"
							:disabled="currentPage === totalPages"
							:class="[
								'px-2 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium rounded-lg border transition-[background-color] duration-75 touch-manipulation',
								currentPage === totalPages
									? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
									: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 active:bg-gray-100'
							]"
							:aria-label="'Go to last page'"
						>
							<span class="hidden xs:inline">Last</span>
							<span class="xs:hidden">»</span>
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import LazyImage from "@/components/common/LazyImage.vue"
import { useItemSearchStore } from "@/stores/itemSearch"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { useStock } from "@/composables/useStock"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { useToast } from "@/composables/useToast"
import { storeToRefs } from "pinia"
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import {
	createOptimizedClickHandler,
	throttleRAF,
	addPassiveListener,
	runWhenIdle
} from "@/utils/lowEndOptimizations"

const props = defineProps({
	posProfile: String,
	cartItems: {
		type: Array,
		default: () => [],
	},
	currency: {
		type: String,
		default: "USD",
	},
})

const emit = defineEmits(["item-selected"])

// Use composables
const { getStockStatus } = useStock()
const settingsStore = usePOSSettingsStore()
const { showError, showWarning } = useToast()

// Use Pinia store
const itemStore = useItemSearchStore()
const {
	filteredItems,
	searchTerm,
	selectedItemGroup,
	itemGroups,
	loading,
	loadingMore,
	searching,
	hasMore,
	cacheSyncing,
	cacheStats,
	sortBy,
	sortOrder,
} = storeToRefs(itemStore)

// Local state
const viewMode = ref("grid")
const lastKeyTime = ref(0)
const barcodeBuffer = ref("")
const searchInputRef = ref(null)
const scannerEnabled = ref(false)
const autoAddEnabled = ref(false)
const itemThreshold = ref(50) // Threshold for auto-switching to list view
const userManuallySetView = ref(false) // Track if user manually changed view mode
const scannerInputDetected = ref(false) // Track if current input is from scanner
const autoSearchTimer = ref(null) // Timer for auto-search when typing stops
const lastAutoSwitchCount = ref(0)
const lastFilterSignature = ref("")
const showSortDropdown = ref(false) // Sort dropdown visibility

// Infinite scroll refs
const gridScrollContainer = ref(null)
const listScrollContainer = ref(null)

// Store scroll listener cleanup functions
const scrollCleanupFns = ref([])

// Pagination state (for client-side display)
const currentPage = ref(1)
const itemsPerPage = ref(20)

// Computed paginated items
// filteredItems is already reactive and includes live stock from stockStore
const paginatedItems = computed(() => {
	if (!filteredItems.value) return []
	const start = (currentPage.value - 1) * itemsPerPage.value
	const end = start + itemsPerPage.value
	return filteredItems.value.slice(start, end)
})

const totalPages = computed(() => {
	if (!filteredItems.value) return 0
	return Math.ceil(filteredItems.value.length / itemsPerPage.value)
})

const SEARCH_PLACEHOLDERS = Object.freeze({
	auto: "Auto-Add ON - Type or scan barcode",
	scanner: "Scanner ON - Enable Auto for automatic addition",
	default: "Search by item code, name or scan barcode",
})

// Sort configuration
const SORT_OPTIONS = Object.freeze([
	{
		field: 'name',
		label: 'Name',
		icon: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z'
	},
	{
		field: 'quantity',
		label: 'Quantity',
		icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4'
	},
	{
		field: 'item_group',
		label: 'Item Group',
		icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10'
	},
	{
		field: 'price',
		label: 'Price',
		icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
	},
	{
		field: 'item_code',
		label: 'Item Code',
		icon: 'M7 20l4-16m2 16l4-16M6 9h14M4 15h14'
	}
])

const SORT_ICONS = Object.freeze({
	ascending: 'M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12',
	descending: 'M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4',
	inactive: 'M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4'
})

const searchMode = computed(() => {
	if (autoAddEnabled.value) {
		return "auto"
	}

	if (scannerEnabled.value) {
		return "scanner"
	}

	return "default"
})

const searchPlaceholder = computed(() => SEARCH_PLACEHOLDERS[searchMode.value])

// Watch for cart items and pos profile changes (optimized - uses length + hash instead of deep watch)
// Tracks: length, item_code, quantity, and amount to detect all cart changes including array replacements
watch(
	() =>
		`${props.cartItems.length}-${props.cartItems.map((i) => `${i.item_code}:${i.quantity || 0}:${i.amount || 0}`).join("|")}`,
	() => {
		itemStore.setCartItems(props.cartItems)
	},
	{ immediate: true, flush: 'sync' }, // Synchronous to ensure immediate stock updates
)

watch(
	() => props.posProfile,
	(newProfile) => {
		if (newProfile) {
			itemStore.setPosProfile(newProfile)
		}
	},
	{ immediate: true },
)

// Reset to page 1 when filtered items meaningfully change
watch(
	filteredItems,
	(newItems) => {
		if (!newItems) return

		const itemCount = newItems.length
		const firstCode = itemCount > 0 ? newItems[0]?.item_code || "" : ""
		const lastCode =
			itemCount > 0 ? newItems[itemCount - 1]?.item_code || "" : ""
		const middleIndex = itemCount > 2 ? Math.floor(itemCount / 2) : -1
		const middleCode =
			middleIndex >= 0 ? newItems[middleIndex]?.item_code || "" : ""
		const signature = `${itemCount}|${firstCode}|${middleCode}|${lastCode}`

		if (signature !== lastFilterSignature.value) {
			currentPage.value = 1
			lastFilterSignature.value = signature
		}

		// Only auto-switch if user hasn't manually set a preference
		// and we're in grid view with many items
		if (
			!userManuallySetView.value &&
			viewMode.value === "grid" &&
			itemCount > itemThreshold.value
		) {
			if (lastAutoSwitchCount.value !== itemCount) {
				viewMode.value = "list"
				lastAutoSwitchCount.value = itemCount
			}
		} else if (itemCount <= itemThreshold.value) {
			lastAutoSwitchCount.value = 0
		}
	},
	{ immediate: false },
)

// Throttle scroll handler for better performance
let scrollTimeout = null

// Optimized scroll handler using RAF throttling
const handleScrollRAF = throttleRAF((event) => {
	const container = event.target
	const scrollPosition = container.scrollTop + container.clientHeight
	const scrollHeight = container.scrollHeight
	const threshold = 200

	const isSearching = searchTerm.value && searchTerm.value.trim().length > 0

	if (
		!isSearching &&
		scrollHeight - scrollPosition < threshold &&
		hasMore.value &&
		!loadingMore.value &&
		!loading.value
	) {
		// Use runWhenIdle to load more items without blocking scroll
		runWhenIdle(() => {
			itemStore.loadMoreItems()
		}, { timeout: 1000 })
	}
})

function handleScroll(event) {
	handleScrollRAF(event)
}

onMounted(() => {
	// Items are now loaded automatically by setPosProfile() in the watcher
	// This ensures item group filters are loaded BEFORE fetching items

	// Add passive scroll listeners for better performance
	// Only bind to the currently active view
	if (viewMode.value === 'grid' && gridScrollContainer.value) {
		const cleanup = addPassiveListener(
			gridScrollContainer.value,
			'scroll',
			handleScroll,
			{ passive: true }
		)
		scrollCleanupFns.value.push(cleanup)
	} else if (viewMode.value === 'list' && listScrollContainer.value) {
		const cleanup = addPassiveListener(
			listScrollContainer.value,
			'scroll',
			handleScroll,
			{ passive: true }
		)
		scrollCleanupFns.value.push(cleanup)
	}

	// Add click outside listener for sort dropdown
	document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
	// Cleanup background sync when component unmounts
	itemStore.cleanup()

	// Clear scroll timeout
	if (scrollTimeout) {
		clearTimeout(scrollTimeout)
		scrollTimeout = null
	}

	// Cleanup passive listeners
	scrollCleanupFns.value.forEach(cleanup => cleanup())
	scrollCleanupFns.value = []

	// Clear optimized click handlers
	optimizedClickHandlers.clear()

	// Remove click outside listener for sort dropdown
	document.removeEventListener('click', handleClickOutside)
})

// Handle keydown for barcode scanner detection
function handleKeyDown(event) {
	const currentTime = Date.now()
	const timeDiff = currentTime - lastKeyTime.value

	// If Enter/newline is pressed, trigger barcode search
	if (event.key === "Enter") {
		event.preventDefault()

		// Auto-add if Auto-Add mode is enabled (regardless of manual typing vs scanner)
		if (autoAddEnabled.value) {
			// Auto-add enabled - add item directly to cart
			handleBarcodeSearch(true) // Pass true to indicate auto-add
		} else {
			// Auto-add disabled - normal search behavior
			handleBarcodeSearch(false)
		}

		// Reset detection
		barcodeBuffer.value = ""
		scannerInputDetected.value = false

		// Clear auto-search timer since Enter was pressed
		if (autoSearchTimer.value) {
			clearTimeout(autoSearchTimer.value)
			autoSearchTimer.value = null
		}

		return
	}

	// Barcode scanners typically input very fast (< 50ms between characters)
	// If time between keystrokes is very short, it's likely a barcode scanner
	if (
		timeDiff < 50 &&
		event.key.length === 1 &&
		barcodeBuffer.value.length > 0
	) {
		barcodeBuffer.value += event.key
		scannerInputDetected.value = true // Mark as scanner input
	} else if (event.key.length === 1) {
		// Manual typing - reset buffer
		barcodeBuffer.value = event.key
		scannerInputDetected.value = false // Mark as manual input
	}

	lastKeyTime.value = currentTime
}

// Handle search input with instant reactivity
function handleSearchInput(event) {
	const value = event.target.value
	itemStore.setSearchTerm(value)

	// Clear any existing timer
	if (autoSearchTimer.value) {
		clearTimeout(autoSearchTimer.value)
		autoSearchTimer.value = null
	}

	// If Auto-Add is enabled and user is typing, automatically trigger search after they stop
	if (autoAddEnabled.value && value.trim().length > 0) {
		// Wait 500ms after user stops typing, then auto-search and add
		autoSearchTimer.value = setTimeout(() => {
			handleBarcodeSearch(true) // Auto-add mode
		}, 500) // 500ms delay after typing stops
	}
}

// Create optimized click handlers for better touch response
const optimizedClickHandlers = new Map()

function getOptimizedClickHandler(item) {
	const key = item.item_code
	if (!optimizedClickHandlers.has(key)) {
		// Pass item_code instead of item reference to avoid closure issues
		const handler = createOptimizedClickHandler(() => {
			handleItemClick(item.item_code)
		}, {
			feedback: true
		})
		optimizedClickHandlers.set(key, handler)
	}
	return optimizedClickHandlers.get(key)
}

function handleItemClick(itemCode) {
	// Find the current item by code to get latest stock values
	const item = filteredItems.value.find(i => i.item_code === itemCode)
	if (!item) return

	// Check stock availability and show error if needed, but still emit the event
	// Skip validation for batch/serial items - they have their own validation in the dialog
	// Check stock for stock items AND Product Bundles (bundles now have calculated stock)
	const qty = Math.floor(item.actual_qty ?? item.stock_qty ?? 0)
	if ((item.is_stock_item || item.is_bundle) && !item.has_serial_no && !item.has_batch_no && qty <= 0 && settingsStore.shouldEnforceStockValidation()) {
		const itemType = item.is_bundle ? "Bundle" : "Item"
		showError(`"${item.item_name}" cannot be added to cart. ${itemType} is out of stock. Allow Negative Stock is disabled.`)
		return
	}

	emit("item-selected", item)
}

async function handleBarcodeSearch(forceAutoAdd = false) {
	const barcode = searchTerm.value.trim()

	if (!barcode) {
		return
	}

	// Auto-add if explicitly requested (from scanner newline detection)
	// OR if both scanner and auto-add modes are enabled
	const shouldAutoAdd =
		forceAutoAdd || (scannerEnabled.value && autoAddEnabled.value)

	try {
		// First try exact barcode lookup via API
		const item = await itemStore.searchByBarcode(barcode)

		if (item) {
			// Item found by barcode - add to cart immediately with auto-add flag
			emit("item-selected", item, shouldAutoAdd)
			itemStore.clearSearch()
			return
		}
	} catch (error) {
		console.error("Barcode API error:", error)
	}

	// Fallback: If only one item matches in filtered results, auto-select it
	if (filteredItems.value.length === 1) {
		emit("item-selected", filteredItems.value[0], shouldAutoAdd)
		itemStore.clearSearch()
	} else if (filteredItems.value.length === 0) {
		showWarning(`Item Not Found: No item found with barcode: ${barcode}`)

		// If scanner mode is enabled, clear search immediately for next scan
		if (shouldAutoAdd) {
			itemStore.clearSearch()
		}
	} else {
		if (shouldAutoAdd) {
			// In scanner mode, don't show manual selection - just notify
			showWarning(`Multiple Items Found: ${filteredItems.value.length} items match barcode. Please refine search.`)
		} else {
			showWarning(`Multiple Items Found: ${filteredItems.value.length} items match. Please select one.`)
		}
	}
}

function toggleBarcodeScanner() {
	scannerEnabled.value = !scannerEnabled.value

	// Disable auto-add when scanner is disabled
	if (!scannerEnabled.value) {
		autoAddEnabled.value = false
	}

	// Focus on search input when enabling scanner
	if (scannerEnabled.value) {
		const input = searchInputRef.value || document.getElementById("item-search")
		if (input) {
			input.focus()
		}
	}
}

function toggleAutoAdd() {
	// Auto-add works independently - no need for scanner mode
	autoAddEnabled.value = !autoAddEnabled.value

	// Auto-enable scanner mode when auto-add is enabled
	if (autoAddEnabled.value && !scannerEnabled.value) {
		scannerEnabled.value = true
	}

	// Clear any pending timer when toggling off
	if (!autoAddEnabled.value && autoSearchTimer.value) {
		clearTimeout(autoSearchTimer.value)
		autoSearchTimer.value = null
	}

	if (autoAddEnabled.value) {
		// Focus on search input
		const input = searchInputRef.value || document.getElementById("item-search")
		if (input) {
			input.focus()
		}
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

// Expose methods for parent component
defineExpose({
	loadItems: () => itemStore.loadAllItems(props.posProfile),
	loadItemGroups: () => itemStore.loadItemGroups(),
	loadMoreItems: () => itemStore.loadMoreItems(),
})

// Watch for view mode changes and rebind scroll listeners
watch(viewMode, async () => {
	// Wait for DOM to update
	await nextTick()

	// Clean up existing listeners
	scrollCleanupFns.value.forEach(cleanup => cleanup())
	scrollCleanupFns.value = []

	// Rebind listeners to the new active container
	if (viewMode.value === 'grid' && gridScrollContainer.value) {
		const cleanup = addPassiveListener(
			gridScrollContainer.value,
			'scroll',
			handleScroll,
			{ passive: true }
		)
		scrollCleanupFns.value.push(cleanup)
	} else if (viewMode.value === 'list' && listScrollContainer.value) {
		const cleanup = addPassiveListener(
			listScrollContainer.value,
			'scroll',
			handleScroll,
			{ passive: true }
		)
		scrollCleanupFns.value.push(cleanup)
	}
})

// View mode functions
function setViewMode(mode) {
	viewMode.value = mode
	userManuallySetView.value = true
}

// Pagination functions
function goToPage(page) {
	if (page >= 1 && page <= totalPages.value) {
		currentPage.value = page
	}
}

function nextPage() {
	if (currentPage.value < totalPages.value) {
		currentPage.value++
	}
}

function previousPage() {
	if (currentPage.value > 1) {
		currentPage.value--
	}
}

function getPaginationRange() {
	const range = []
	const total = totalPages.value
	const current = currentPage.value
	const delta = 2 // Number of pages to show on each side of current page

	if (total <= 7) {
		// Show all pages if total is small
		for (let i = 1; i <= total; i++) {
			range.push(i)
		}
	} else {
		// Show smart range with ellipsis
		if (current <= 3) {
			for (let i = 1; i <= 5; i++) {
				range.push(i)
			}
		} else if (current >= total - 2) {
			for (let i = total - 4; i <= total; i++) {
				range.push(i)
			}
		} else {
			for (let i = current - delta; i <= current + delta; i++) {
				range.push(i)
			}
		}
	}

	return range
}

// Sort dropdown functions
function toggleSortDropdown() {
	showSortDropdown.value = !showSortDropdown.value
}

function handleSortToggle(field) {
	if (!field) {
		// Clear sorting
		itemStore.clearSortFilter()
		showSortDropdown.value = false
		return
	}

	// If clicking the same field, toggle between asc/desc
	if (sortBy.value === field) {
		const newOrder = sortOrder.value === 'asc' ? 'desc' : 'asc'
		itemStore.setSortFilter(field, newOrder)
	} else {
		// New field - start with ascending
		itemStore.setSortFilter(field, 'asc')
	}
}

function getSortLabel(sortByValue) {
	const option = SORT_OPTIONS.find(opt => opt.field === sortByValue)
	return option?.label || sortByValue
}

function getSortIconState(field) {
	if (sortBy.value !== field) return 'inactive'
	return sortOrder.value === 'asc' ? 'ascending' : 'descending'
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
	if (showSortDropdown.value) {
		const dropdown = event.target.closest('.relative')
		if (!dropdown || !dropdown.querySelector('button[aria-label="Sort items"]')?.contains(event.target)) {
			showSortDropdown.value = false
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
    -ms-overflow-style: none;  /* IE and Edge */
    scrollbar-width: none;  /* Firefox */
}

/* Performance optimizations for low-end devices */
[class*="grid-cols-"] > div {
	/* Tell browser which properties will change */
	will-change: opacity;
	/* Use GPU acceleration for transforms */
	transform: translateZ(0);
	/* Optimize for speed over quality */
	backface-visibility: hidden;
}

/* Optimize scroll containers */
.overflow-y-auto, .overflow-x-auto {
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
