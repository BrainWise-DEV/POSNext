<template>
	<div class="flex flex-col h-full bg-white">
                <!-- Header with Customer -->
                <div class="px-2 sm:px-3 py-2 sm:py-2.5 border-b border-gray-200">
                        <!-- Inline Customer Search/Selection -->
                        <div ref="customerSearchContainer" class="relative mb-2 sm:mb-3">
                                <div v-if="customer" class="flex items-center justify-between bg-blue-50 rounded-lg p-1.5 sm:p-2">
                                        <div class="flex items-center space-x-2">
                                                <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                                                        <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<p class="text-xs font-semibold text-gray-900 truncate">
								{{ customer.customer_name || customer.name }}
							</p>
							<p v-if="customer.mobile_no" class="text-[10px] text-gray-600 truncate">
								{{ customer.mobile_no }}
							</p>
						</div>
					</div>
					<button
						type="button"
						@click="clearCustomer"
						class="text-sm text-red-600 hover:text-red-700 flex-shrink-0 p-1 touch-manipulation"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
					</button>
				</div>
				<div v-else>
					<!-- Search Icon Prefix -->
					<div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
						<svg v-if="customersLoaded" class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
						</svg>
						<div v-else class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-500"></div>
					</div>

					<!-- Native Input for Instant Search -->
					<input
						id="cart-customer-search"
						name="cart-customer-search"
						:value="customerSearch"
						@input="handleSearchInput"
						type="text"
						placeholder="Search customer by name or mobile"
						class="w-full pl-8 sm:pl-10 text-[11px] sm:text-xs border border-gray-300 rounded-md px-2 sm:px-3 py-1.5 sm:py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						:disabled="!customersLoaded"
						@keydown="handleKeydown"
						aria-label="Search customer in cart"
					/>

					<!-- Customer Dropdown -->
					<div
						v-if="customerSearch.trim().length >= 2"
						class="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-hidden"
					>
						<!-- Customer Results -->
						<div v-if="customerResults.length > 0" class="max-h-64 overflow-y-auto">
							<button
								type="button"
								v-for="(cust, index) in customerResults"
								:key="cust.name"
								@click="selectCustomer(cust)"
								:class="[
									'w-full text-left px-3 py-2.5 flex items-center space-x-2 border-b border-gray-100 last:border-0 transition-colors duration-75',
									index === selectedIndex ? 'bg-blue-100' : 'hover:bg-blue-50'
								]"
							>
								<div class="w-7 h-7 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
									<span class="text-[11px] font-bold text-blue-600">{{ getInitials(cust.customer_name) }}</span>
								</div>
								<div class="flex-1 min-w-0">
									<p class="text-xs font-semibold text-gray-900 truncate">{{ cust.customer_name }}</p>
									<p v-if="cust.mobile_no" class="text-[10px] text-gray-600">{{ cust.mobile_no }}</p>
								</div>
							</button>
						</div>

						<!-- No Results + Create New Option -->
						<div v-else-if="customerSearch.trim().length >= 2">
							<div class="px-3 py-2 text-center text-xs font-medium text-gray-700 border-b border-gray-100">
								No results for "{{ customerSearch }}"
							</div>
						</div>

						<!-- Create New Customer Option -->
						<button
							type="button"
							v-if="customerSearch.trim().length >= 2"
							@click="createNewCustomer"
							class="w-full text-left px-3 py-2.5 hover:bg-green-50 flex items-center space-x-2 transition-colors border-t border-gray-200"
						>
							<div class="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
								<svg class="w-3.5 h-3.5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
								</svg>
							</div>
							<div class="flex-1">
								<p class="text-xs font-medium text-green-700">Create New Customer</p>
								<p class="text-[10px] text-green-600">"{{ customerSearch }}"</p>
							</div>
						</button>
                                        </div>
                                </div>
                        </div>
                        <div class="flex items-center justify-between">
                                <h2 class="text-xs sm:text-sm font-semibold text-gray-900">Item Cart</h2>
                                <button
                                        v-if="items.length > 0"
                                        @click="$emit('clear-cart')"
                                        class="inline-flex items-center gap-1 sm:gap-1.5 rounded-full px-2 sm:px-2.5 py-0.5 sm:py-1 text-[10px] sm:text-xs font-semibold text-red-600 transition-colors hover:text-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-200 touch-manipulation"
                                        type="button"
                                        title="Clear all items from the cart"
                                        aria-label="Clear all items from the cart"
                                >
                                        <svg class="w-3 h-3 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V5a2 2 0 00-2-2h-2a2 2 0 00-2 2v2M4 7h16"/>
                                        </svg>
                                        <span class="hidden sm:inline">Clear Cart</span>
                                        <span class="sm:hidden">Clear</span>
                                </button>
                        </div>
                </div>

		<!-- Cart Items -->
		<div class="flex-1 overflow-y-auto p-1 sm:p-2.5 bg-gray-50">
			<div v-if="items.length === 0" class="text-center py-8 sm:py-12">
				<div class="w-12 h-12 sm:w-16 sm:h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-2 sm:mb-3">
					<svg
						class="h-6 w-6 sm:h-8 sm:w-8 text-gray-400"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
						/>
					</svg>
				</div>
				<p class="text-[11px] sm:text-xs font-medium text-gray-900">Your cart is empty</p>
				<p class="text-[10px] text-gray-500 mt-1">
					Select items to start
				</p>
			</div>

			<div v-else class="space-y-1 sm:space-y-2">
				<div
					v-for="(item, index) in items"
					:key="index"
					@click="openEditDialog(item)"
					class="bg-white border-2 border-gray-200 rounded-lg p-1.5 sm:p-2 hover:border-blue-300 hover:shadow-lg transition-all duration-200 active:scale-[0.99] cursor-pointer group"
				>
					<div class="flex gap-1.5 sm:gap-2">
						<!-- Item Image Thumbnail -->
						<div class="w-10 h-10 sm:w-12 sm:h-12 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center overflow-hidden border border-gray-200">
							<img
								v-if="item.image"
								:src="item.image"
								:alt="item.item_name"
								loading="lazy"
								width="48"
								height="48"
								decoding="async"
								class="w-full h-full object-cover"
							/>
							<svg
								v-else
								class="h-5 w-5 sm:h-6 sm:w-6 text-gray-400"
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

						<!-- Item Content -->
						<div class="flex-1 min-w-0 flex flex-col">
							<!-- Header: Item Name & Delete -->
							<div class="flex items-start justify-between gap-1 mb-1">
								<div class="flex items-center gap-1.5 flex-1 min-w-0">
									<h4 class="text-[11px] sm:text-xs font-bold text-gray-900 truncate leading-tight">
										{{ item.item_name }}
									</h4>
									<!-- Free Item Badge -->
									<span
										v-if="item.free_qty && item.free_qty > 0"
										class="inline-flex items-center px-1.5 py-0.5 bg-green-600 text-white rounded-full text-[9px] font-bold flex-shrink-0"
										:title="`${item.free_qty} free item(s) included`"
									>
										<svg class="w-2.5 h-2.5 mr-0.5" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/>
										</svg>
										+{{ item.free_qty }} FREE
									</span>
								</div>
								<button
									type="button"
									@click.stop="$emit('remove-item', item.item_code)"
									class="text-gray-400 hover:text-red-600 active:text-red-700 transition-colors flex-shrink-0 p-0.5 -m-0.5 touch-manipulation active:scale-90"
									:aria-label="'Remove ' + item.item_name"
									title="Remove item"
								>
									<svg class="h-4 w-4 sm:h-4.5 sm:w-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
									</svg>
								</button>
							</div>

							<!-- Price & UOM Row -->
							<div class="flex items-center flex-wrap gap-1.5 mb-1.5">
								<div class="flex items-center gap-1">
									<span class="text-[11px] sm:text-xs font-bold text-gray-900">
										{{ formatCurrency(item.rate) }}
									</span>
									<span class="text-[10px] text-gray-500">/</span>
									<span class="inline-flex items-center px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-[10px] sm:text-xs font-semibold">
										{{ item.uom || item.stock_uom || 'Nos' }}
									</span>
								</div>

								<!-- Discount Badge if any -->
								<div
									v-if="item.discount_amount && item.discount_amount > 0"
									class="inline-flex items-center px-1.5 py-0.5 bg-gradient-to-r from-red-50 to-orange-50 text-red-700 rounded-full text-[9px] font-bold border border-red-200"
								>
									<svg class="w-2 h-2 mr-0.5" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z" clip-rule="evenodd"/>
									</svg>
									{{ Number(item.discount_percentage).toFixed(2) }}% OFF
								</div>
							</div>

							<!-- Bottom Row: Quantity Controls, UOM Selector & Total -->
							<div class="flex items-center justify-between gap-1.5">
								<div class="flex items-center gap-1.5" @click.stop>
									<!-- Quantity Counter -->
									<div class="flex items-center bg-gray-50 border-2 border-gray-200 rounded-lg overflow-hidden">
										<button
											type="button"
											@click="decrementQuantity(item)"
											class="w-7 h-7 sm:w-8 sm:h-8 bg-white hover:bg-gray-100 active:bg-gray-200 flex items-center justify-center font-bold text-gray-700 transition-colors touch-manipulation border-r-2 border-gray-200"
											:aria-label="'Decrease quantity'"
											title="Decrease quantity"
										>
											<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M20 12H4"/>
											</svg>
										</button>
										<input
											:value="item.quantity"
											@input="updateQuantity(item, $event.target.value)"
											@blur="handleQuantityBlur(item)"
											@keydown.enter="$event.target.blur()"
											type="number"
											min="0.0001"
											step="any"
											inputmode="decimal"
											class="w-16 sm:w-20 text-center bg-white border-0 text-sm sm:text-base font-bold text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
											:aria-label="'Quantity'"
										/>
										<button
											type="button"
											@click="incrementQuantity(item)"
											class="w-7 h-7 sm:w-8 sm:h-8 bg-white hover:bg-gray-100 active:bg-gray-200 flex items-center justify-center font-bold text-gray-700 transition-colors touch-manipulation border-l-2 border-gray-200"
											:aria-label="'Increase quantity'"
											title="Increase quantity"
										>
											<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M12 4v16m8-8H4"/>
											</svg>
										</button>
									</div>

									<!-- UOM Selector Dropdown (Custom) -->
									<div class="relative group/uom">
										<!-- Dropdown Button -->
										<button
											type="button"
											@click="toggleUomDropdown(item.item_code)"
											:disabled="!item.item_uoms || item.item_uoms.length === 0"
											:class="[
												'h-7 sm:h-8 text-[10px] sm:text-xs font-bold rounded-lg pl-2.5 pr-7 transition-all touch-manipulation shadow-sm flex items-center justify-center min-w-[60px]',
												item.item_uoms && item.item_uoms.length > 0
													? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white border-2 border-blue-400 hover:from-blue-600 hover:to-blue-700 hover:border-blue-500 hover:shadow-md active:scale-95 cursor-pointer'
													: 'bg-gray-100 text-gray-500 border-2 border-gray-200 cursor-not-allowed opacity-60'
											]"
											:title="item.item_uoms && item.item_uoms.length > 0 ? 'Click to change unit' : 'Only one unit available'"
										>
											{{ item.uom || item.stock_uom || 'Nos' }}
										</button>

										<!-- Dropdown Arrow Icon -->
										<svg
											:class="[
												'absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none transition-transform',
												openUomDropdown === item.item_code ? 'rotate-180' : '',
												item.item_uoms && item.item_uoms.length > 0 ? 'text-white' : 'text-gray-400'
											]"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"/>
										</svg>

										<!-- Dropdown Menu -->
										<div
											v-if="openUomDropdown === item.item_code && item.item_uoms && item.item_uoms.length > 0"
											class="absolute top-full left-0 mt-1 bg-white border-2 border-blue-300 rounded-lg shadow-xl z-50 min-w-full overflow-hidden"
										>
											<!-- Stock UOM Option -->
											<button
												type="button"
												@click="selectUom(item, item.stock_uom)"
												:class="[
													'w-full text-left px-3 py-2 text-[10px] sm:text-xs font-semibold transition-colors border-b border-gray-100',
													(item.uom || item.stock_uom) === item.stock_uom
														? 'bg-blue-50 text-blue-700'
														: 'text-gray-700 hover:bg-blue-50 hover:text-blue-600'
												]"
											>
												<div class="flex items-center justify-between">
													<span>{{ item.stock_uom || 'Nos' }}</span>
													<svg
														v-if="(item.uom || item.stock_uom) === item.stock_uom"
														class="w-4 h-4 text-blue-600"
														fill="currentColor"
														viewBox="0 0 20 20"
													>
														<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
													</svg>
												</div>
											</button>

											<!-- Other UOM Options -->
											<button
												v-for="uomData in item.item_uoms"
												:key="uomData.uom"
												type="button"
												@click="selectUom(item, uomData.uom)"
												:class="[
													'w-full text-left px-3 py-2 text-[10px] sm:text-xs font-semibold transition-colors border-b border-gray-100 last:border-0',
													(item.uom || item.stock_uom) === uomData.uom
														? 'bg-blue-50 text-blue-700'
														: 'text-gray-700 hover:bg-blue-50 hover:text-blue-600'
												]"
											>
												<div class="flex items-center justify-between">
													<span>{{ uomData.uom }}</span>
													<svg
														v-if="(item.uom || item.stock_uom) === uomData.uom"
														class="w-4 h-4 text-blue-600"
														fill="currentColor"
														viewBox="0 0 20 20"
													>
														<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
													</svg>
												</div>
											</button>
										</div>
									</div>
								</div>

								<!-- Item Total Price -->
								<div class="text-right">
									<div class="text-[9px] text-gray-500 leading-none mb-0.5">Total</div>
									<div class="text-xs sm:text-sm font-bold text-blue-600 leading-none">
										{{ formatCurrency(item.amount || item.rate * item.quantity) }}
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Coupons, Offers & Discount Section -->
		<div v-if="items.length > 0" class="px-1.5 sm:px-2.5 pt-1.5 sm:pt-2.5 pb-1 bg-gray-50 space-y-2">
			<div class="flex gap-1.5 sm:gap-2">
				<!-- View All Offers Button -->
				<button
					type="button"
					@click="$emit('show-offers')"
					class="relative flex-1 flex items-center justify-between px-2 sm:px-2.5 py-2 sm:py-2.5 rounded-lg bg-white border-2 border-green-300 hover:border-green-500 active:border-green-600 hover:bg-green-50 active:bg-green-100 transition-all group min-w-0 touch-manipulation active:scale-95"
					:aria-label="'View all available offers'"
				>
					<div class="flex items-center space-x-1.5 min-w-0 flex-1">
						<div class="w-7 h-7 rounded-full bg-green-100 flex items-center justify-center group-hover:bg-green-200 transition-colors flex-shrink-0">
							<svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"/>
							</svg>
						</div>
						<span class="text-xs font-semibold text-gray-900 truncate">Offers</span>
					</div>
					<div class="flex items-center space-x-1 flex-shrink-0 ml-1">
						<span
							v-if="appliedOfferCount > 0"
							class="bg-green-700 text-white text-[9px] font-bold rounded-full px-2 py-0.5 flex items-center"
						>
							{{ appliedOfferCount }} Applied
						</span>
						<span
							v-if="offersStore.autoEligibleCount > 0"
							class="bg-green-600 text-white text-[9px] font-bold rounded-full px-1.5 py-0.5 min-w-[18px] text-center"
						>
							{{ offersStore.autoEligibleCount }}
						</span>
					</div>
				</button>

				<!-- Enter Coupon Code Button -->
				<button
					type="button"
					@click="$emit('apply-coupon')"
					class="relative flex-1 flex items-center px-2 sm:px-2.5 py-2 sm:py-2.5 rounded-lg bg-white border-2 border-purple-300 hover:border-purple-500 active:border-purple-600 hover:bg-purple-50 active:bg-purple-100 transition-all group min-w-0 touch-manipulation active:scale-95"
					:aria-label="'Apply coupon code'"
				>
					<div class="flex items-center space-x-1 min-w-0 flex-1">
						<div class="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center group-hover:bg-purple-200 transition-colors flex-shrink-0">
							<svg class="w-3.5 h-3.5 text-purple-600" fill="currentColor" viewBox="0 0 20 20">
								<path fill-rule="evenodd" d="M4 2a2 2 0 00-2 2v11a3 3 0 106 0V4a2 2 0 00-2-2H4zm1 14a1 1 0 100-2 1 1 0 000 2zm5-1.757l4.9-4.9a2 2 0 000-2.828L13.485 5.1a2 2 0 00-2.828 0L10 5.757v8.486zM16 18H9.071l6-6H16a2 2 0 012 2v2a2 2 0 01-2 2z" clip-rule="evenodd"/>
							</svg>
						</div>
						<span class="text-xs font-semibold text-gray-900 truncate">Coupon</span>
					</div>
					<span v-if="availableGiftCards.length > 0" class="bg-purple-600 text-white text-[9px] font-bold rounded-full px-1.5 py-0.5 min-w-[18px] text-center flex-shrink-0 ml-1">
						{{ availableGiftCards.length }}
					</span>
				</button>
			</div>
		</div>

		<!-- Totals Summary -->
		<div class="p-2 sm:p-2.5 bg-white border-t border-gray-200">
			<!-- Summary Details -->
			<div v-if="items.length > 0" class="mb-2.5">
				<div class="flex items-center justify-between text-[10px] text-gray-600 mb-1">
					<span>Total Quantity</span>
					<span class="font-medium text-gray-900">{{ formatQuantity(totalQuantity) }}</span>
				</div>
				<div class="flex items-center justify-between text-[10px] text-gray-600 mb-2">
					<span>Subtotal</span>
					<span class="font-medium text-gray-900">{{ formatCurrency(subtotal) }}</span>
				</div>
			</div>

			<!-- Summary Details (continued) -->
			<div v-if="items.length > 0" class="mb-2.5">
				<!-- Discount Display - Highlighted -->
				<div v-if="discountAmount > 0" class="flex items-center justify-between mb-1 bg-red-50 rounded px-1.5 py-1 -mx-0.5">
					<div class="flex items-center space-x-1">
						<svg class="w-3 h-3 text-red-600" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z" clip-rule="evenodd"/>
						</svg>
						<span class="text-[10px] font-semibold text-red-700">Discount</span>
					</div>
					<span class="text-xs font-bold text-red-600">{{ formatCurrency(discountAmount) }}</span>
				</div>

				<div class="flex items-center justify-between text-[10px] text-gray-600 mb-2">
					<div class="flex items-center space-x-1">
						<svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
						</svg>
						<span>Tax</span>
					</div>
					<span class="font-medium text-gray-900">{{ formatCurrency(taxAmount) }}</span>
				</div>
			</div>

			<!-- Grand Total -->
			<div class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-2.5 mb-2.5">
				<div class="flex items-center justify-between">
					<span class="text-sm font-bold text-gray-900">Grand Total</span>
					<span class="text-lg font-bold text-blue-600">
						{{ formatCurrency(grandTotal) }}
					</span>
				</div>
			</div>

			<!-- Action Buttons -->
			<div class="space-y-1.5 sm:space-y-2">
				<button
					type="button"
					@click="$emit('proceed-to-payment')"
					:disabled="items.length === 0"
					:class="[
						'w-full py-3 sm:py-3.5 px-4 rounded-xl font-bold text-sm sm:text-base text-white transition-all flex items-center justify-center touch-manipulation',
						items.length === 0
							? 'bg-gray-300 cursor-not-allowed'
							: 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800 shadow-lg hover:shadow-xl active:scale-95'
					]"
					:aria-label="'Proceed to payment'"
				>
					<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/>
					</svg>
					<span>Checkout</span>
				</button>
				<button
					type="button"
					v-if="items.length > 0"
					@click="$emit('save-draft')"
					class="w-full py-2 sm:py-2.5 px-3 rounded-lg font-semibold text-xs sm:text-sm text-orange-700 bg-orange-50 hover:bg-orange-100 active:bg-orange-200 transition-all touch-manipulation active:scale-95"
					:aria-label="'Hold order as draft'"
				>
					<svg class="w-4 h-4 inline mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/>
					</svg>
					Hold Order
				</button>
			</div>
		</div>

		<!-- Edit Item Dialog -->
		<EditItemDialog
			v-model="showEditDialog"
			:item="selectedItem"
			:warehouses="warehouses"
			:currency="currency"
			@update-item="handleUpdateItem"
		/>
	</div>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSOffersStore } from "@/stores/posOffers"
import { usePOSSettingsStore } from "@/stores/posSettings"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { useFormatters } from "@/composables/useFormatters"
import { isOffline } from "@/utils/offline"
import { offlineWorker } from "@/utils/offline/workerClient"
import { createResource } from "frappe-ui"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import EditItemDialog from "./EditItemDialog.vue"

// Use Pinia store
const cartStore = usePOSCartStore()
const offersStore = usePOSOffersStore()
const settingsStore = usePOSSettingsStore()

// Use formatters
const { formatQuantity } = useFormatters()

const props = defineProps({
	items: {
		type: Array,
		default: () => [],
	},
	customer: Object,
	subtotal: {
		type: Number,
		default: 0,
	},
	taxAmount: {
		type: Number,
		default: 0,
	},
	discountAmount: {
		type: Number,
		default: 0,
	},
	grandTotal: {
		type: Number,
		default: 0,
	},
	posProfile: String,
	currency: {
		type: String,
		default: "USD",
	},
	appliedOffers: {
		type: Array,
		default: () => [],
	},
	warehouses: {
		type: Array,
		default: () => [],
	},
})

const emit = defineEmits([
	"update-quantity",
	"remove-item",
	"select-customer",
	"create-customer",
	"proceed-to-payment",
	"clear-cart",
	"save-draft",
	"apply-coupon",
	"show-coupons",
	"show-offers",
	"remove-offer",
	"update-uom",
	"edit-item",
])

const customerSearch = ref("")
const customerSearchContainer = ref(null)
const allCustomers = ref([])
const customersLoaded = ref(false)
const selectedIndex = ref(-1)
const availableGiftCards = ref([])

// Edit item dialog state
const showEditDialog = ref(false)
const selectedItem = ref(null)

// UOM dropdown state - tracks which item's UOM dropdown is open
const openUomDropdown = ref(null)

// Load customers into memory on mount for instant filtering
// Load customers resource
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const customersResource = createResource({
	url: "pos_next.api.customers.get_customers",
	makeParams() {
		return {
			search_term: "", // Empty to get all customers
			pos_profile: props.posProfile,
			limit: 9999, // Get all customers
		}
	},
	auto: false, // Don't auto-load - check offline status first
	async onSuccess(data) {
		const customers = data?.message || data || []
		allCustomers.value = customers
		customersLoaded.value = true

		// Also cache in worker for offline support
		await offlineWorker.cacheCustomers(customers)
	},
	onError(error) {
		console.error("Error loading customers:", error)
	},
})

// Load customers from cache first (instant), then from server if online
;(async () => {
	try {
		// Always try cache first for instant load
		const cachedCustomers = await offlineWorker.searchCachedCustomers("", 9999)
		if (cachedCustomers && cachedCustomers.length > 0) {
			allCustomers.value = cachedCustomers
			customersLoaded.value = true
		}
	} catch (error) {
		console.error("Error loading customers from cache:", error)
	}

	// Only fetch from server if online (to refresh cache)
	if (!isOffline()) {
		customersResource.reload()
	}
})()

// Load offers resource and set them in store
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const offersResource = createResource({
	url: "pos_next.api.offers.get_offers",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	auto: false, // Don't auto-load - check offline status first
	onSuccess(data) {
		const offers = data?.message || data || []
		offersStore.setAvailableOffers(offers)
	},
	onError(error) {
		console.error("Error loading offers:", error)
	},
})

// Load offers only when online (offers not cached for offline use)
if (!isOffline()) {
	offersResource.reload()
}

// Load gift cards resource
const giftCardsResource = createResource({
	url: "pos_next.api.offers.get_active_coupons",
	makeParams() {
		return {
			customer: props.customer?.name || props.customer,
			company: props.posProfile, // Will get company from profile
		}
	},
	auto: false,
	onSuccess(data) {
		availableGiftCards.value = data?.message || data || []
	},
})

// Watch for customer changes to load their gift cards
watch(
	() => props.customer,
	(newCustomer) => {
		if (newCustomer && props.posProfile && !isOffline()) {
			giftCardsResource.reload()
		} else {
			availableGiftCards.value = []
		}
	},
)

// Use eligible offers from store (limited to 3 for display)
const availableOffers = computed(() =>
	offersStore.autoEligibleOffers.slice(0, 3),
)

const appliedOfferCount = computed(() => (props.appliedOffers || []).length)

// Direct computed results - zero latency filtering!
const customerResults = computed(() => {
	const searchValue = customerSearch.value.trim().toLowerCase()

	if (searchValue.length < 2) {
		return []
	}

	// Instant in-memory filter
	return allCustomers.value
		.filter((cust) => {
			const name = (cust.customer_name || "").toLowerCase()
			const mobile = (cust.mobile_no || "").toLowerCase()
			const id = (cust.name || "").toLowerCase()

			return (
				name.includes(searchValue) ||
				mobile.includes(searchValue) ||
				id.includes(searchValue)
			)
		})
		.slice(0, 20)
})

// Reset selection when results change
watch(customerResults, () => {
	selectedIndex.value = -1
})

const totalQuantity = computed(() => {
	return props.items.reduce((sum, item) => {
		const qty = item.quantity || 0
		const freeQty = item.free_qty || 0
		return sum + qty + freeQty
	}, 0)
})

// Handle search input with instant reactivity
function handleSearchInput(event) {
	customerSearch.value = event.target.value
}

// Keyboard navigation
function handleKeydown(event) {
	if (customerResults.value.length === 0) return

	if (event.key === "ArrowDown") {
		event.preventDefault()
		selectedIndex.value = Math.min(
			selectedIndex.value + 1,
			customerResults.value.length - 1,
		)
	} else if (event.key === "ArrowUp") {
		event.preventDefault()
		selectedIndex.value = Math.max(selectedIndex.value - 1, -1)
	} else if (event.key === "Enter") {
		event.preventDefault()
		if (
			selectedIndex.value >= 0 &&
			selectedIndex.value < customerResults.value.length
		) {
			selectCustomer(customerResults.value[selectedIndex.value])
		} else if (customerResults.value.length === 1) {
			// Auto-select if only one result
			selectCustomer(customerResults.value[0])
		}
	} else if (event.key === "Escape") {
		customerSearch.value = ""
	}
}

function selectCustomer(cust) {
	emit("select-customer", cust)
	customerSearch.value = ""
	selectedIndex.value = -1
}

function clearCustomer() {
	emit("select-customer", null)
}

function createNewCustomer() {
	// Emit event to open customer creation dialog
	emit("create-customer", customerSearch.value)
	customerSearch.value = ""
}

function getInitials(name) {
	if (!name) return "?"
	const parts = name.split(" ")
	if (parts.length >= 2) {
		return (parts[0][0] + parts[1][0]).toUpperCase()
	}
	return name.substring(0, 2).toUpperCase()
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

/**
 * Intelligently determine the step size based on current quantity
 * - Whole numbers (1, 2, 3): step by 1
 * - Multiples of 0.5 (1.5, 2.5): step by 0.5
 * - Multiples of 0.25 (0.25, 0.75): step by 0.25
 * - Multiples of 0.1 (0.1, 0.3): step by 0.1
 * - Other decimals: step by 0.01
 */
function getSmartStep(quantity) {
	// Check if it's a whole number
	if (quantity === Math.floor(quantity)) {
		return 1
	}

	// Round to 4 decimal places to avoid floating point errors
	const rounded = Math.round(quantity * 10000) / 10000

	// Check if it's a multiple of 0.5
	if (Math.abs((rounded % 0.5)) < 0.0001) {
		return 0.5
	}

	// Check if it's a multiple of 0.25
	if (Math.abs((rounded % 0.25)) < 0.0001) {
		return 0.25
	}

	// Check if it's a multiple of 0.1
	if (Math.abs((rounded % 0.1)) < 0.0001) {
		return 0.1
	}

	// For other decimals, use 0.01 for fine control
	return 0.01
}

function incrementQuantity(item) {
	const step = getSmartStep(item.quantity)
	const newQty = Math.round((item.quantity + step) * 10000) / 10000
	emit("update-quantity", item.item_code, newQty)
}

function decrementQuantity(item) {
	const step = getSmartStep(item.quantity)
	const newQty = Math.round((item.quantity - step) * 10000) / 10000

	if (newQty <= 0) {
		// If quantity would be 0 or negative, remove the item
		emit("remove-item", item.item_code)
	} else {
		emit("update-quantity", item.item_code, newQty)
	}
}

function updateQuantity(item, value) {
	const qty = Number.parseFloat(value)
	// Allow any positive number during typing (don't round yet)
	if (!isNaN(qty) && qty > 0) {
		emit("update-quantity", item.item_code, qty)
	}
}

function handleQuantityBlur(item) {
	// When user leaves the input field, round and validate
	if (!item.quantity || item.quantity <= 0) {
		// If quantity is 0 or invalid, remove the item
		emit("remove-item", item.item_code)
	} else {
		// Round to 4 decimal places for consistency
		const roundedQty = Math.round(item.quantity * 10000) / 10000
		if (roundedQty !== item.quantity) {
			emit("update-quantity", item.item_code, roundedQty)
		}
	}
}

async function handleUomChange(item, newUom) {
	await cartStore.changeItemUOM(item.item_code, newUom)
	openUomDropdown.value = null // Close dropdown after selection
	// Also emit for parent component compatibility
	emit("update-uom", item.item_code, newUom)
}

function toggleUomDropdown(itemCode) {
	openUomDropdown.value = openUomDropdown.value === itemCode ? null : itemCode
}

function selectUom(item, uom) {
	handleUomChange(item, uom)
}

function openEditDialog(item) {
	selectedItem.value = { ...item }
	showEditDialog.value = true
}

async function handleUpdateItem(updatedItem) {
	// Use store method to update item
	await cartStore.updateItemDetails(updatedItem.item_code, updatedItem)
	// Also emit for parent component compatibility
	emit("edit-item", updatedItem)
}

function handleOutsideClick(event) {
	const target = event.target

	// Close customer search if clicking outside
	if (
		customerSearchContainer.value &&
		target instanceof Node &&
		!customerSearchContainer.value.contains(target)
	) {
		customerSearch.value = ""
	}

	// Close UOM dropdown if clicking outside
	if (openUomDropdown.value !== null) {
		// Check if click is outside all UOM dropdowns
		const clickedInsideUomDropdown =
			target instanceof Element && target.closest(".group\\/uom")
		if (!clickedInsideUomDropdown) {
			openUomDropdown.value = null
		}
	}
}

onMounted(() => {
	if (typeof document === "undefined") return
	document.addEventListener("click", handleOutsideClick)
})

onBeforeUnmount(() => {
	if (typeof document === "undefined") return
	document.removeEventListener("click", handleOutsideClick)
})
</script>
