<!--
  InvoiceCart.vue - Shopping Cart Component for POS System

  ============================================================================
  OVERVIEW
  ============================================================================
  This component displays the shopping cart in the POS interface, including:
  - Customer selection/search with instant in-memory filtering
  - Cart items list with quantity controls, UOM selection, and pricing
  - Offers and coupon application buttons
  - Order totals (subtotal, discount, tax, grand total)
  - Checkout and Hold order actions
  - Quick action buttons when cart is empty

  ============================================================================
  COMPONENT STRUCTURE
  ============================================================================

  1. HEADER SECTION (Customer Selection)
     - Shows selected customer info with edit/remove options
     - Search input with instant filtering from cached customer list
     - Dropdown with search results and "Create New Customer" option
     - Works offline using cached customer data

  2. ACTION BUTTONS SECTION (Offers & Coupons)
     - "Offers" button - Shows available promotional offers
     - "Coupon" button - Apply coupon/gift card codes
     - Badge indicators show count of available/applied offers

  3. CART ITEMS SECTION
     - Scrollable list of cart items
     - Each item shows: thumbnail, name, badges (free/discount), price, quantity controls
     - Quantity controls: increment/decrement buttons + manual input
     - UOM (Unit of Measure) dropdown selector
     - Serial item support with edit dialog
     - Empty cart state with quick action buttons

  4. TOTALS SECTION
     - Total Quantity
     - Subtotal
     - Discount (highlighted when applied)
     - Tax
     - Grand Total (emphasized)

  5. ACTION BUTTONS
     - Checkout - Proceed to payment
     - Hold - Save as draft order

  ============================================================================
  FEATURES
  ============================================================================

  - Offline Support: Customer search works offline using cached data
  - Instant Search: In-memory customer filtering for zero-latency results
  - Smart Quantity Steps: Automatically detects decimal precision for +/- buttons
  - UOM Conversion: Change units with automatic price recalculation
  - Serial Number Support: Special handling for serialized inventory items
  - Responsive Design: Adapts to mobile and desktop layouts
  - Touch Optimized: Large tap targets and touch feedback
  - RTL Support: Fully supports right-to-left languages

  ============================================================================
-->
<template>
	<div class="flex flex-col h-full bg-white">
		<!-- Header with Customer -->
		<div class="px-2.5 py-2 border-b border-gray-200 bg-gray-50">
			<!-- Inline Customer Search/Selection -->
			<div ref="customerSearchContainer" class="relative">
				<div v-if="customer">
					<!-- Two Cards Layout: Customer Card + Document Type Card -->
					<div class="flex items-stretch gap-2">
						<!-- Customer Card -->
						<div class="flex-1 flex items-center gap-1.5 bg-white border border-gray-200 rounded-xl p-1.5 shadow-sm min-w-0">
							<!-- Customer Avatar & Info -->
							<div class="flex items-center gap-2 min-w-0 flex-1 px-1.5 py-1">
								<div class="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
									<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
									</svg>
								</div>
								<div class="min-w-0 flex-1">
									<p class="text-xs font-semibold text-gray-900 truncate leading-tight">
										{{ customer.customer_name || customer.name }}
									</p>
									<p v-if="customer.mobile_no" class="text-[10px] text-gray-500 truncate leading-tight">
										{{ customer.mobile_no }}
									</p>
								</div>
							</div>

							<!-- Action Buttons -->
							<div class="flex items-center gap-0.5 flex-shrink-0" @click.stop>
								<button
									type="button"
									@click.stop="$emit('edit-customer', customer)"
									class="w-7 h-7 flex items-center justify-center text-blue-500 hover:bg-blue-50 active:bg-blue-100 rounded-lg transition-colors touch-manipulation"
									:title="__('Edit customer details')"
								>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
										<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
									</svg>
								</button>
								<button
									type="button"
									@click.stop="$emit('create-customer', '')"
									class="w-7 h-7 flex items-center justify-center text-green-600 hover:bg-green-50 active:bg-green-100 rounded-lg transition-colors touch-manipulation"
									:title="__('Create new customer')"
								>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
										<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
									</svg>
								</button>
								<button
									type="button"
									@click.stop="removeCustomer"
									class="w-7 h-7 flex items-center justify-center text-red-500 hover:bg-red-50 active:bg-red-100 rounded-lg transition-colors touch-manipulation"
									:title="__('Remove customer')"
								>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
										<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							</div>
						</div>

						<!-- Document Type Card -->
						<div
							v-if="settingsStore.allowSalesOrder"
							class="flex items-center bg-white border border-gray-200 rounded-xl p-1.5 shadow-sm flex-shrink-0"
						>
							<div class="flex items-center bg-gray-100 rounded-lg p-0.5">
								<button
									type="button"
									@click="selectDocType('Sales Invoice')"
									class="px-2.5 py-1.5 text-[11px] font-semibold rounded-md transition-all duration-200 flex items-center gap-1"
									:class="cartStore.targetDoctype === 'Sales Invoice'
										? 'bg-white text-blue-600 shadow-sm'
										: 'text-gray-500 hover:text-gray-700'"
									:title="__('Sales Invoice')"
								>
									<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
									</svg>
									<span>{{ __("Invoice") }}</span>
								</button>
								<button
									type="button"
									@click="selectDocType('Sales Order')"
									class="px-2.5 py-1.5 text-[11px] font-semibold rounded-md transition-all duration-200 flex items-center gap-1"
									:class="cartStore.targetDoctype === 'Sales Order'
										? 'bg-white text-orange-600 shadow-sm'
										: 'text-gray-500 hover:text-gray-700'"
									:title="__('Sales Order')"
								>
									<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
									</svg>
									<span>{{ __("Order") }}</span>
								</button>
							</div>
						</div>
					</div>
				</div>
				<div v-else>
					<div class="flex gap-1.5">
						<!-- Search Input -->
						<div class="relative flex-1">
							<!-- Search Icon Prefix -->
							<div
								class="absolute inset-y-0 start-0 ps-3 flex items-center pointer-events-none"
							>
								<svg
									v-if="customersLoaded"
									class="w-4 h-4 text-gray-400"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
									/>
								</svg>
								<div
									v-else
									class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-blue-500"
								></div>
							</div>

							<!-- Native Input for Instant Search -->
							<input
								id="cart-customer-search"
								name="cart-customer-search"
								:value="customerSearch"
								@input="handleSearchInput"
								@focus="handleSearchFocus"
								@blur="handleSearchBlur"
								type="text"
								:placeholder="__('Search or add customer...')"
								class="w-full h-10 ps-9 pe-3 text-xs border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent shadow-sm transition-shadow"
								:disabled="!customersLoaded"
								@keydown="handleKeydown"
								autocomplete="off"
								:aria-label="__('Search customer in cart')"
							/>
						</div>

						<!-- Quick Create Customer Button -->
						<button
							type="button"
							@click="createNewCustomer"
							class="flex items-center justify-center w-10 h-10 bg-green-500 hover:bg-green-600 active:bg-green-700 rounded-xl text-white transition-colors shadow-sm hover:shadow touch-manipulation flex-shrink-0"
							:title="__('Create new customer')"
							:aria-label="__('Create new customer')"
						>
							<svg
								class="w-5 h-5"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
								stroke-width="2"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
								/>
							</svg>
						</button>

						<!-- Document Type Toggle (Sales Invoice / Sales Order) -->
						<div
							v-if="settingsStore.allowSalesOrder"
							class="flex items-center bg-gray-100 rounded-xl p-0.5 h-10"
						>
							<button
								type="button"
								@click="selectDocType('Sales Invoice')"
								class="h-full px-2.5 text-xs font-semibold rounded-lg transition-all duration-200 flex items-center gap-1.5"
								:class="cartStore.targetDoctype === 'Sales Invoice'
									? 'bg-white text-blue-600 shadow-sm'
									: 'text-gray-500 hover:text-gray-700'"
								:title="__('Sales Invoice')"
							>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
								<span class="hidden sm:inline">{{ __("Invoice") }}</span>
							</button>
							<button
								type="button"
								@click="selectDocType('Sales Order')"
								class="h-full px-2.5 text-xs font-semibold rounded-lg transition-all duration-200 flex items-center gap-1.5"
								:class="cartStore.targetDoctype === 'Sales Order'
									? 'bg-white text-orange-600 shadow-sm'
									: 'text-gray-500 hover:text-gray-700'"
								:title="__('Sales Order')"
							>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
								</svg>
								<span class="hidden sm:inline">{{ __("Order") }}</span>
							</button>
						</div>
					</div>
				</div>

				<!-- Customer Dropdown -->
				<div
					v-if="customerSearchFocused || customerSearch.trim().length >= 2"
					class="absolute z-50 mt-0.5 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-hidden will-change-transform"
				>
					<!-- Frequent Customers Header (when showing suggestions) -->
					<div
						v-if="customerSearchFocused && customerSearch.trim().length < 2 && customerResults.length > 0"
						class="px-2 py-1 bg-gray-50 border-b border-gray-200"
					>
						<span class="text-[10px] font-medium text-gray-500 uppercase tracking-wide">
							{{ __('Frequent Customers') }}
						</span>
					</div>

					<!-- Customer Results -->
					<div v-if="customerResults.length > 0" class="max-h-48 overflow-y-auto overscroll-contain">
						<button
							type="button"
							v-for="(cust, index) in customerResults"
							:key="cust.name"
							@mousedown.prevent="selectCustomer(cust)"
							:class="[
								'w-full text-start px-2 py-1.5 flex items-center gap-1.5 border-b border-gray-100 last:border-0 touch-manipulation select-none cursor-pointer active:bg-blue-200',
								index === selectedIndex ? 'bg-blue-100' : 'hover:bg-blue-50 active:bg-blue-100',
							]"
						>
							<div
								class="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0 pointer-events-none"
							>
								<span class="text-[10px] font-bold text-blue-600">{{
									getInitials(cust.customer_name)
								}}</span>
							</div>
							<div class="flex-1 min-w-0 pointer-events-none">
								<p class="text-[11px] font-semibold text-gray-900 truncate">
									{{ cust.customer_name }}
								</p>
								<p v-if="cust.mobile_no" class="text-[9px] text-gray-600">
									{{ cust.mobile_no }}
								</p>
							</div>
						</button>
					</div>

					<!-- No Results + Create New Option -->
					<div v-else-if="customerSearch.trim().length >= 2">
						<div
							class="px-2 py-1.5 text-center text-[11px] font-medium text-gray-700 border-b border-gray-100"
						>
							{{ __('No results for "{0}"', [customerSearch]) }}
						</div>
					</div>

					<!-- Create New Customer Option -->
					<button
						type="button"
						v-if="customerSearch.trim().length >= 2"
						@mousedown.prevent="createNewCustomer"
						class="w-full text-start px-2 py-1.5 hover:bg-green-50 active:bg-green-100 flex items-center gap-1.5 border-t border-gray-200 touch-manipulation select-none cursor-pointer"
					>
						<div
							class="w-5 h-5 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 pointer-events-none"
						>
							<svg
								class="w-3 h-3 text-green-600"
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
						</div>
						<div class="flex-1 pointer-events-none">
							<p class="text-[11px] font-medium text-green-700">
								{{ __("Create New Customer") }}
							</p>
							<p class="text-[9px] text-green-600">"{{ customerSearch }}"</p>
						</div>
					</button>
				</div>
			</div>
		</div>

		<!-- Action Buttons Section -->
		<div v-if="items.length > 0" class="px-2 py-2 border-b border-gray-200 bg-white">
			<div class="flex items-center justify-between mb-1.5">
				<h2 class="text-xs font-bold text-gray-900">{{ __("Cart Items") }}</h2>
				<button
					@click="$emit('clear-cart')"
					class="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 transition-colors touch-manipulation"
					type="button"
					:title="__('Clear all items')"
				>
					<svg
						class="w-4 h-4"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V5a2 2 0 00-2-2h-2a2 2 0 00-2 2v2M4 7h16"
						/>
					</svg>
					<span>{{ __("Clear") }}</span>
				</button>
			</div>

			<!-- Offers & Coupon Buttons -->
			<div class="flex gap-2">
				<!-- View All Offers Button -->
				<button
					type="button"
					@click="$emit('show-offers')"
					class="relative flex-1 flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 hover:border-green-400 hover:from-green-100 hover:to-emerald-100 hover:shadow-sm transition-all min-w-0 touch-manipulation active:scale-[0.98]"
					:aria-label="__('View all available offers')"
				>
					<svg
						class="w-3.5 h-3.5 text-green-600 flex-shrink-0"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
						/>
					</svg>
					<span class="text-[11px] font-bold text-green-700">{{ __("Offers") }}</span>
					<!-- Badge shows ONLY applied offers count - NOT eligible/pending offers -->
					<!-- This prevents confusion where offers show as "applied" before backend validation -->
					<span
						v-if="appliedOfferCount > 0"
						class="bg-green-600 text-white text-[9px] font-bold rounded-full px-1.5 py-0.5 flex-shrink-0 min-w-[16px] text-center"
					>
						{{ appliedOfferCount }}
					</span>
				</button>

				<!-- Enter Coupon Code Button -->
				<button
					type="button"
					@click="$emit('apply-coupon')"
					class="relative flex-1 flex items-center justify-center gap-1.5 px-2.5 py-2 rounded-lg bg-gradient-to-r from-purple-50 to-violet-50 border border-purple-200 hover:border-purple-400 hover:from-purple-100 hover:to-violet-100 hover:shadow-sm transition-all min-w-0 touch-manipulation active:scale-[0.98]"
					:aria-label="__('Apply coupon code')"
				>
					<svg
						class="w-3.5 h-3.5 text-purple-600 flex-shrink-0"
						fill="currentColor"
						viewBox="0 0 20 20"
					>
						<path
							fill-rule="evenodd"
							d="M4 2a2 2 0 00-2 2v11a3 3 0 106 0V4a2 2 0 00-2-2H4zm1 14a1 1 0 100-2 1 1 0 000 2zm5-1.757l4.9-4.9a2 2 0 000-2.828L13.485 5.1a2 2 0 00-2.828 0L10 5.757v8.486zM16 18H9.071l6-6H16a2 2 0 012 2v2a2 2 0 01-2 2z"
							clip-rule="evenodd"
						/>
					</svg>
					<span class="text-[11px] font-bold text-purple-700">{{ __("Coupon") }}</span>
					<span
						v-if="availableGiftCards.length > 0"
						class="bg-purple-600 text-white text-[9px] font-bold rounded-full px-1.5 py-0.5 flex-shrink-0 min-w-[16px] text-center"
					>
						{{ availableGiftCards.length }}
					</span>
				</button>
			</div>
		</div>

		<!-- Cart Items -->
		<div class="flex-1 overflow-y-auto p-0.5 sm:p-1.5 bg-gray-50">
			<div
				v-if="items.length === 0"
				class="flex flex-col items-center justify-center h-full px-3 sm:px-4 py-6"
			>
				<!-- Empty Cart Icon & Message -->
				<div
					class="w-14 h-14 sm:w-16 sm:h-16 bg-gray-100 rounded-full flex items-center justify-center mb-3"
				>
					<svg
						class="h-7 w-7 sm:h-8 sm:w-8 text-gray-400"
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
				<p class="text-xs sm:text-sm font-semibold text-gray-900 mb-1">
					{{ __("Your cart is empty") }}
				</p>
				<p class="text-[10px] sm:text-xs text-gray-500 mb-5 sm:mb-6">
					{{ __("Select items to start or choose a quick action") }}
				</p>

				<!-- Quick Actions Grid -->
				<div class="grid grid-cols-2 gap-2 sm:gap-2.5 w-full max-w-lg">
					<!-- View Shift -->
					<button
						type="button"
						@click="$emit('view-shift')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 active:bg-blue-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('View current shift details')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-blue-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-blue-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-blue-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
								/>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("View Shift")
						}}</span>
					</button>

					<!-- Draft Invoices -->
					<button
						type="button"
						@click="$emit('show-drafts')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-purple-300 hover:bg-purple-50 active:bg-purple-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('View draft invoices')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-purple-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-purple-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-purple-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("Draft Invoices")
						}}</span>
					</button>

					<!-- Invoice History -->
					<button
						type="button"
						@click="$emit('show-history')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-gray-300 hover:bg-gray-50 active:bg-gray-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('View invoice history')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-gray-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-gray-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-gray-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("Invoice History")
						}}</span>
					</button>

					<!-- Return Invoice -->
					<button
						type="button"
						@click="$emit('show-return')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-red-300 hover:bg-red-50 active:bg-red-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('Process return invoice')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-red-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-red-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-red-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("Return Invoice")
						}}</span>
					</button>

					<!-- Close Shift -->
					<button
						type="button"
						@click="$emit('close-shift')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-orange-300 hover:bg-orange-50 active:bg-orange-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('Close current shift')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-orange-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-orange-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-orange-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("Close Shift")
						}}</span>
					</button>

					<!-- Create Customer -->
					<button
						type="button"
						@click="$emit('create-customer', '')"
						class="flex flex-col items-center justify-center p-3 sm:p-4 bg-white border border-gray-200 rounded-lg hover:border-green-300 hover:bg-green-50 active:bg-green-100 transition-colors shadow-sm hover:shadow touch-manipulation group"
						:title="__('Create new customer')"
					>
						<div
							class="w-9 h-9 sm:w-10 sm:h-10 bg-green-50 rounded-full flex items-center justify-center mb-2 group-hover:bg-green-100 transition-colors"
						>
							<svg
								class="w-5 h-5 text-green-600"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
								/>
							</svg>
						</div>
						<span class="text-[11px] sm:text-xs font-semibold text-gray-700">{{
							__("Create Customer")
						}}</span>
					</button>
				</div>
			</div>

			<div v-else class="flex flex-col gap-0.5 sm:gap-1">
				<div
					v-for="(item, index) in items"
					:key="index"
					@click="openEditDialog(item)"
					class="bg-white border border-gray-200 rounded-md p-1.5 sm:p-2 hover:border-blue-300 hover:shadow-md transition-all duration-200 active:scale-[0.99] cursor-pointer group"
				>
					<div class="flex gap-1.5 sm:gap-2">
						<!-- Item Image Thumbnail -->
						<div
							class="w-10 h-10 sm:w-12 sm:h-12 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center overflow-hidden border border-gray-200"
						>
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
						<div class="flex-1 min-w-0 flex flex-col justify-center">
							<!-- Header: Item Name, Badges & Delete -->
							<div class="flex items-start justify-between gap-0.5 mb-0.5">
								<div class="flex items-center gap-1.5 flex-1 min-w-0">
									<h4
										class="text-xs sm:text-sm font-extrabold text-gray-900 truncate leading-tight"
									>
										{{ item.item_name }}
									</h4>
									<!-- Free Item Badge -->
									<span
										v-if="item.free_qty && item.free_qty > 0"
										class="inline-flex items-center px-1.5 py-0.5 bg-green-600 text-white rounded-full text-[9px] font-bold flex-shrink-0"
										:title="__('{0} free item(s) included', [item.free_qty])"
									>
										<svg
											class="w-2.5 h-2.5 me-0.5"
											fill="currentColor"
											viewBox="0 0 20 20"
										>
											<path
												fill-rule="evenodd"
												d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"
												clip-rule="evenodd"
											/>
										</svg>
										{{ __("+{0} FREE", [item.free_qty]) }}
									</span>
									<!-- Discount Badge -->
									<div
										v-if="item.discount_amount && item.discount_amount > 0"
										class="inline-flex items-center px-1.5 py-0.5 bg-gradient-to-r from-red-50 to-orange-50 text-red-700 rounded-full text-[9px] font-bold border border-red-200 flex-shrink-0"
									>
										<svg
											class="w-2.5 h-2.5 me-0.5"
											fill="currentColor"
											viewBox="0 0 20 20"
										>
											<path
												fill-rule="evenodd"
												d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
												clip-rule="evenodd"
											/>
										</svg>
										{{
											__("{0}%", [
												Number(item.discount_percentage).toFixed(0),
											])
										}}
									</div>
								</div>
								<button
									type="button"
									@click.stop="$emit('remove-item', item.item_code, item.uom)"
									class="text-gray-400 hover:text-red-600 active:text-red-700 transition-colors flex-shrink-0 p-0.5 -m-0.5 touch-manipulation active:scale-90"
									:aria-label="__('Remove {0}', [item.item_name])"
									:title="__('Remove item')"
								>
									<svg
										class="h-4 w-4"
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
								</button>
							</div>

							<!-- Single Row: Quantity Counter, UOM, Price & Total -->
							<div class="flex items-center justify-between gap-1.5">
								<div class="flex items-center gap-1.5">
									<!-- Quantity Counter -->
									<!-- For serial items, show serial badge with edit button -->
									<div
										v-if="item.has_serial_no && item.serial_no"
										class="flex items-center gap-1"
										@click.stop
									>
										<!-- Serial count badge -->
										<div
											class="flex items-center bg-blue-50 border border-blue-200 rounded px-1.5 h-6 sm:h-7"
										>
											<FeatherIcon
												name="hash"
												class="w-3 h-3 text-blue-500 me-0.5"
											/>
											<span
												class="text-xs sm:text-sm font-bold text-blue-700"
												>{{ item.quantity }}</span
											>
										</div>
										<!-- Edit button -->
										<button
											type="button"
											@click="openEditDialog(item)"
											class="flex items-center justify-center w-6 h-6 sm:w-7 sm:h-7 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white rounded transition-colors shadow-sm"
											:title="__('Edit serials')"
										>
											<FeatherIcon name="edit-2" class="w-3 h-3" />
										</button>
									</div>
									<!-- For non-serial items, show normal quantity controls -->
									<div
										v-else
										:class="[
											'flex items-center bg-gray-50 border rounded overflow-hidden',
											item.is_resolved_barcode ? 'border-amber-300 bg-amber-50' : 'border-gray-200'
										]"
									>
										<button
											type="button"
											@click="decrementQuantity(item)"
											:disabled="item.is_resolved_barcode"
											:class="[
												'w-6 h-6 sm:w-7 sm:h-7 flex items-center justify-center font-bold transition-colors touch-manipulation border-e',
												item.is_resolved_barcode
													? 'bg-gray-100 text-gray-400 cursor-not-allowed border-amber-300'
													: 'bg-white hover:bg-gray-100 active:bg-gray-200 text-gray-700 border-gray-200'
											]"
											:aria-label="__('Decrease quantity')"
											:title="item.is_resolved_barcode ? __('Quantity locked (barcode item)') : __('Decrease quantity')"
										>
											<svg
												class="w-3 h-3"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="3"
													d="M20 12H4"
												/>
											</svg>
										</button>
										<input
											:value="formatQuantity(item.quantity)"
											@input="updateQuantity(item, $event.target.value)"
											@blur="handleQuantityBlur(item)"
											@keydown.enter="$event.target.blur()"
											type="text"
											inputmode="decimal"
											:disabled="item.is_resolved_barcode"
											:class="[
												'w-14 sm:w-16 h-6 sm:h-7 text-center border-0 text-xs sm:text-sm font-bold focus:outline-none',
												item.is_resolved_barcode
													? 'bg-amber-50 text-amber-700 cursor-not-allowed'
													: 'bg-white text-gray-900 focus:ring-2 focus:ring-blue-500'
											]"
											:aria-label="__('Quantity')"
											:title="item.is_resolved_barcode ? __('Quantity locked (barcode item)') : ''"
										/>
										<button
											type="button"
											@click="incrementQuantity(item)"
											:disabled="item.is_resolved_barcode"
											:class="[
												'w-6 h-6 sm:w-7 sm:h-7 flex items-center justify-center font-bold transition-colors touch-manipulation border-s',
												item.is_resolved_barcode
													? 'bg-gray-100 text-gray-400 cursor-not-allowed border-amber-300'
													: 'bg-white hover:bg-gray-100 active:bg-gray-200 text-gray-700 border-gray-200'
											]"
											:aria-label="__('Increase quantity')"
											:title="item.is_resolved_barcode ? __('Quantity locked (barcode item)') : __('Increase quantity')"
										>
											<svg
												class="w-3 h-3"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="3"
													d="M12 4v16m8-8H4"
												/>
											</svg>
										</button>
									</div>

									<!-- UOM Selector Dropdown -->
									<div class="relative group/uom" @click.stop>
										<button
											type="button"
											@click="toggleUomDropdown(item.item_code, item.uom)"
											:disabled="
												item.is_resolved_barcode || !item.item_uoms || item.item_uoms.length === 0
											"
											:class="[
												'h-6 sm:h-7 text-[10px] sm:text-xs font-bold rounded ps-2 pe-5 transition-all touch-manipulation flex items-center justify-center min-w-[45px]',
												item.is_resolved_barcode
													? 'bg-amber-100 text-amber-700 border border-amber-300 cursor-not-allowed'
													: item.item_uoms && item.item_uoms.length > 0
														? 'bg-blue-500 text-white border border-blue-400 hover:bg-blue-600 active:scale-95 cursor-pointer'
														: 'bg-gray-100 text-gray-500 border border-gray-200 cursor-not-allowed opacity-60',
											]"
											:title="
												item.is_resolved_barcode
													? __('UOM locked (barcode item)')
													: item.item_uoms && item.item_uoms.length > 0
														? __('Click to change unit')
														: __('Only one unit available')
											"
										>
											{{
												item.uom ||
												item.stock_uom ||
												__("Nos", null, "UOM")
											}}
										</button>
										<svg
											:class="[
												'absolute end-1.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 pointer-events-none transition-transform',
												openUomDropdown === `${item.item_code}-${item.uom}`
													? 'rotate-180'
													: '',
												item.is_resolved_barcode
													? 'text-amber-600'
													: item.item_uoms && item.item_uoms.length > 0
														? 'text-white'
														: 'text-gray-400',
											]"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2.5"
												d="M19 9l-7 7-7-7"
											/>
										</svg>
										<div
											v-if="
												openUomDropdown ===
													`${item.item_code}-${item.uom}` &&
												item.item_uoms &&
												item.item_uoms.length > 0
											"
											class="absolute top-full start-0 mt-0.5 bg-white border border-blue-300 rounded shadow-xl z-50 min-w-full overflow-hidden"
										>
											<button
												type="button"
												@click="selectUom(item, item.stock_uom)"
												:class="[
													'w-full text-start px-2 py-1.5 text-[10px] sm:text-xs font-semibold transition-colors border-b border-gray-100',
													(item.uom || item.stock_uom) === item.stock_uom
														? 'bg-blue-50 text-blue-700'
														: 'text-gray-700 hover:bg-blue-50',
												]"
											>
												{{ item.stock_uom || __("Nos", null, "UOM") }}
											</button>
											<button
												v-for="uomData in item.item_uoms"
												:key="uomData.uom"
												type="button"
												@click="selectUom(item, uomData.uom)"
												:class="[
													'w-full text-start px-2 py-1.5 text-[10px] sm:text-xs font-semibold transition-colors border-b border-gray-100 last:border-0',
													(item.uom || item.stock_uom) === uomData.uom
														? 'bg-blue-50 text-blue-700'
														: 'text-gray-700 hover:bg-blue-50',
												]"
											>
												{{ uomData.uom }}
											</button>
										</div>
									</div>

									<!-- Price -->
									<span class="text-[10px] sm:text-xs font-bold text-gray-700">
										{{ formatCurrency(item.rate) }}
									</span>
								</div>

								<!-- Item Total -->
								<div class="text-end flex-shrink-0">
									<div
										class="text-xs sm:text-sm font-bold text-blue-600 leading-none"
									>
										{{
											formatCurrency(
												item.amount || item.rate * item.quantity
											)
										}}
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Totals Summary -->
		<div class="p-1.5 sm:p-2 bg-white border-t border-gray-200">
			<!-- Summary Details -->
			<div v-if="items.length > 0" class="mb-1.5">
				<div class="flex items-center justify-between text-xs text-gray-600 mb-0.5">
					<span class="font-medium">{{ __("Total Quantity") }}</span>
					<span class="font-bold text-gray-900 text-center min-w-[60px]">{{
						formatQuantity(totalQuantity)
					}}</span>
				</div>
				<div class="flex items-center justify-between text-xs text-gray-600">
					<span class="font-medium">{{ __("Subtotal") }}</span>
					<span class="font-bold text-gray-900 text-center min-w-[60px]">{{
						formatCurrency(displaySubtotal)
					}}</span>
				</div>
			</div>

			<!-- Summary Details (continued) -->
			<div v-if="items.length > 0" class="mb-1.5">
				<!-- Discount Display - Highlighted -->
				<div
					v-if="discountAmount > 0"
					class="flex items-center justify-between mb-0.5 bg-red-50 rounded px-1.5 py-1 -mx-0.5"
				>
					<div class="flex items-center gap-1">
						<svg
							class="w-3.5 h-3.5 text-red-600"
							fill="currentColor"
							viewBox="0 0 20 20"
						>
							<path
								fill-rule="evenodd"
								d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
								clip-rule="evenodd"
							/>
						</svg>
						<span class="text-xs font-bold text-red-700">{{ __("Discount") }}</span>
					</div>
					<span class="text-sm font-extrabold text-red-600 text-center min-w-[60px]">{{
						formatCurrency(discountAmount)
					}}</span>
				</div>

				<div class="flex items-center justify-between text-xs text-gray-600">
					<div class="flex items-center gap-1">
						<svg
							class="w-3.5 h-3.5 text-gray-500"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
							/>
						</svg>
						<span class="font-medium">{{ __("Tax") }}</span>
					</div>
					<span class="font-bold text-gray-900 text-center min-w-[60px]">{{
						formatCurrency(taxAmount)
					}}</span>
				</div>
			</div>

			<!-- Grand Total -->
			<div class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-2.5 mb-1.5">
				<div class="flex items-center justify-between">
					<span class="text-sm font-extrabold text-gray-900">{{
						__("Grand Total")
					}}</span>
					<span
						class="text-lg sm:text-xl font-extrabold text-blue-600 text-center min-w-[60px]"
					>
						{{ formatCurrency(displayGrandTotal) }}
					</span>
				</div>
			</div>

			<!-- Action Buttons -->
			<div class="flex gap-1.5">
				<!-- Checkout Button (Primary - 50% width) -->
				<button
					type="button"
					@click="handleProceedToPayment"
					:disabled="items.length === 0"
					:class="[
						'flex-1 py-2.5 px-3 rounded-lg font-bold text-xs text-white transition-all flex items-center justify-center touch-manipulation',
						items.length === 0
							? 'bg-gray-300 cursor-not-allowed'
							: 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800 shadow-lg hover:shadow-xl active:scale-[0.98]',
					]"
					:aria-label="__('Proceed to payment')"
				>
					<svg
						class="w-4 h-4 me-1.5"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"
						/>
					</svg>
					<span>{{ __("Checkout") }}</span>
				</button>

				<!-- Hold Order Button (Secondary - 50% width) -->
				<button
					type="button"
					v-if="items.length > 0"
					@click="$emit('save-draft')"
					class="flex-1 py-2.5 px-2 rounded-lg font-semibold text-xs text-orange-700 bg-orange-50 hover:bg-orange-100 active:bg-orange-200 transition-all touch-manipulation active:scale-[0.98] flex items-center justify-center"
					:aria-label="__('Hold order as draft')"
				>
					<svg
						class="w-4 h-4 me-1.5"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
						/>
					</svg>
					<span>{{ __("Hold", null, "order") }}</span>
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
/**
 * ============================================================================
 * IMPORTS
 * ============================================================================
 */
import { usePOSCartStore } from "@/stores/posCart";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { usePOSOffersStore } from "@/stores/posOffers";
import { useCustomerSearchStore } from "@/stores/customerSearch";
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { useFormatters } from "@/composables/useFormatters";
import { isOffline } from "@/utils/offline";
import { offlineWorker } from "@/utils/offline/workerClient";
import { logger } from "@/utils/logger";
import { FeatherIcon } from "frappe-ui";

const log = logger.create("InvoiceCart");
import { createResource } from "frappe-ui";
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import EditItemDialog from "./EditItemDialog.vue";

/**
 * ============================================================================
 * STORES & COMPOSABLES
 * ============================================================================
 */
const cartStore = usePOSCartStore(); // Pinia store for cart state management
const settingsStore = usePOSSettingsStore(); // Pinia store for POS settings
const offersStore = usePOSOffersStore(); // Pinia store for offers/promotions
const customerSearchStore = useCustomerSearchStore(); // Pinia store for customer search
const { formatQuantity } = useFormatters(); // Quantity formatting utilities

function handleProceedToPayment() {
	emit("proceed-to-payment");
}

/**
 * ============================================================================
 * PROPS
 * ============================================================================
 * @prop {Array} items - Cart items array with item details (item_code, quantity, rate, etc.)
 * @prop {Object} customer - Selected customer object (name, customer_name, mobile_no)
 * @prop {Number} subtotal - Cart subtotal before tax and discounts
 * @prop {Number} taxAmount - Total tax amount
 * @prop {Number} discountAmount - Total discount amount applied
 * @prop {Number} grandTotal - Final total (subtotal - discount + tax)
 * @prop {String} posProfile - Current POS Profile name
 * @prop {String} currency - Currency code for formatting (e.g., "USD", "EUR")
 * @prop {Array} appliedOffers - List of currently applied promotional offers
 * @prop {Array} warehouses - Available warehouses for item selection
 */
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
});

/**
 * ============================================================================
 * EMITS
 * ============================================================================
 * Events emitted to parent component for cart operations
 */
const emit = defineEmits([
	"update-quantity", // (itemCode, newQty, uom?) - Update item quantity
	"remove-item", // (itemCode, uom?) - Remove item from cart
	"select-customer", // (customer) - Select/change customer
	"edit-customer", // (customer) - Open edit customer dialog
	"create-customer", // (searchText) - Open create customer dialog
	"proceed-to-payment", // () - Navigate to payment screen
	"clear-cart", // () - Clear all items from cart
	"save-draft", // () - Save current cart as draft/hold order
	"apply-coupon", // () - Open coupon application dialog
	"show-coupons", // () - Show available coupons
	"show-offers", // () - Show available offers dialog
	"remove-offer", // (offerId) - Remove applied offer
	"update-uom", // (itemCode, newUom) - Change item's unit of measure
	"edit-item", // (item) - Open item edit dialog
	"view-shift", // () - View current shift details
	"show-drafts", // () - Show draft/held orders
	"show-history", // () - Show invoice history
	"show-return", // () - Open return invoice dialog
	"close-shift", // () - Close current shift
	// "create-sales-order", // () - Create Sales Order // Removed as per instruction
]);

/**
 * ============================================================================
 * REACTIVE STATE
 * ============================================================================
 */
// Customer search state
const customerSearch = ref(""); // Current search query
const customerSearchContainer = ref(null); // Ref to search container for click-outside detection
const customerSearchFocused = ref(false); // Track if search input is focused
// Use Pinia store for allCustomers (shared with CustomerDialog, synced on customer creation)
const allCustomers = computed(() => customerSearchStore.allCustomers);
const customersLoaded = computed(() => customerSearchStore.allCustomers.length > 0);
const selectedIndex = ref(-1); // Keyboard navigation index for search results
const availableGiftCards = ref([]); // Available gift cards for current customer
const previousCustomer = ref(null); // Store previous customer for restore on blur

// Edit item dialog state
const showEditDialog = ref(false); // Controls edit dialog visibility
const selectedItem = ref(null); // Item being edited

// UOM dropdown state - tracks which item's UOM dropdown is open (by item_code)
const openUomDropdown = ref(null);

/**
 * ============================================================================
 * API RESOURCES
 * ============================================================================
 * These resources handle data fetching from the server with offline support.
 * Data is cached in the service worker for offline access.
 */

/**
 * Customer Loading
 *
 * Uses the shared customerSearchStore for customer data.
 * This ensures customers are synced across all components (InvoiceCart, CustomerDialog).
 * New customers are immediately available after creation without page refresh.
 */
// Load customers via the shared Pinia store (if not already loaded)
if (props.posProfile) {
	customerSearchStore.loadAllCustomers(props.posProfile);
}

// Load offers on component init (uses shared store method to prevent duplicate fetches)
// ensureOffersFetched handles both online/offline cases and caching
if (props.posProfile) {
	offersStore.ensureOffersFetched(props.posProfile);
}

/**
 * Gift Cards Resource
 *
 * Fetches active coupon codes and gift cards for the selected customer.
 * - Only fetches when a customer is selected and online
 * - Reloads when customer changes (via watcher)
 * - Used for the "Coupon" button badge count
 *
 * @endpoint pos_next.api.offers.get_active_coupons
 */
const giftCardsResource = createResource({
	url: "pos_next.api.offers.get_active_coupons",
	makeParams() {
		return {
			customer: props.customer?.name || props.customer,
			company: props.posProfile, // Will get company from profile
		};
	},
	auto: false,
	onSuccess(data) {
		availableGiftCards.value = data?.message || data || [];
	},
});

/**
 * Watch for customer changes to load their gift cards.
 * Reloads gift cards resource when customer is selected (and online).
 * Clears gift cards when customer is removed or offline.
 */
watch(
	() => props.customer,
	(newCustomer) => {
		if (newCustomer && props.posProfile && !isOffline()) {
			giftCardsResource.reload();
		} else {
			availableGiftCards.value = [];
		}
	}
);

/**
 * ============================================================================
 * COMPUTED PROPERTIES
 * ============================================================================
 */

/**
 * Count of currently applied promotional offers.
 * Used for the badge on the "Offers" button.
 * @returns {Number} Count of applied offers
 */
const appliedOfferCount = computed(() => (props.appliedOffers || []).length);

/**
 * Pre-computed customer lookup map for O(1) access by ID.
 * Rebuilt when allCustomers changes.
 */
const customerMap = computed(() => {
	const map = new Map();
	for (const cust of allCustomers.value) {
		map.set(cust.name, cust);
	}
	return map;
});

/**
 * Instant customer search results with in-memory filtering.
 *
 * Performs zero-latency filtering on the cached customer list.
 * Searches across customer_name, mobile_no, and customer ID.
 * Returns max 20 results to keep dropdown performant.
 *
 * @returns {Array} Filtered customer objects matching search query
 */
const customerResults = computed(() => {
	const searchValue = customerSearch.value.trim().toLowerCase();

	// When focused with no/short search term, show frequent customers (top 5)
	if (searchValue.length < 2) {
		if (customerSearchFocused.value) {
			// Get frequent customer IDs from the store
			const frequentIds = customerSearchStore.frequentCustomers.slice(0, 5);
			if (frequentIds.length > 0) {
				// O(1) lookup using pre-computed map instead of O(n) find
				const frequentCustomers = [];
				for (const id of frequentIds) {
					const cust = customerMap.value.get(id);
					if (cust) frequentCustomers.push(cust);
				}
				return frequentCustomers;
			}
			// If no frequent customers, show first 5 from the list
			return allCustomers.value.slice(0, 5);
		}
		return [];
	}

	// Instant in-memory filter
	return allCustomers.value
		.filter((cust) => {
			const name = (cust.customer_name || "").toLowerCase();
			const mobile = (cust.mobile_no || "").toLowerCase();
			const id = (cust.name || "").toLowerCase();

			return (
				name.includes(searchValue) ||
				mobile.includes(searchValue) ||
				id.includes(searchValue)
			);
		})
		.slice(0, 20);
});

/**
 * Reset keyboard selection index when search results change.
 * Ensures the selection doesn't point to a non-existent result.
 */
watch(customerResults, () => {
	selectedIndex.value = -1;
});

/**
 * Total quantity of all items in cart (including free items).
 * Sums quantity + free_qty for each cart item.
 * @returns {Number} Total item quantity
 */
const totalQuantity = computed(() => {
	return props.items.reduce((sum, item) => {
		const qty = item.quantity || 0;
		const freeQty = item.free_qty || 0;
		return sum + qty + freeQty;
	}, 0);
});

/**
 * Display subtotal adjusted for tax-inclusive mode.
 *
 * When tax is inclusive, the raw subtotal from the store includes tax.
 * For clear cashier display, we show:
 * - Subtotal: Net amount (before tax) = gross - tax
 * - Tax: The extracted tax amount
 * - Grand Total: gross amount = Subtotal + Tax
 *
 * When tax is exclusive, subtotal is already net (before tax).
 *
 * @returns {Number} Subtotal amount to display (net amount before tax)
 */
const displaySubtotal = computed(() => {
	if (cartStore.taxInclusive) {
		// Tax inclusive: subtotal from store is gross (includes tax)
		// Display the net amount (before tax) for clarity
		return props.subtotal - props.taxAmount;
	}
	// Tax exclusive: subtotal is already net (before tax)
	return props.subtotal;
});

/**
 * Display grand total that visually equals Subtotal + Tax - Discount.
 *
 * This ensures the math is intuitive for cashiers:
 * Grand Total = displaySubtotal + Tax - Discount
 *
 * @returns {Number} Grand total amount to display
 */
const displayGrandTotal = computed(() => {
	// Always: displaySubtotal + tax - discount
	// This makes the display consistent and intuitive
	return displaySubtotal.value + props.taxAmount - props.discountAmount;
});

/**
 * ============================================================================
 * FUNCTIONS
 * ============================================================================
 */

// ─────────────────────────────────────────────────────────────────────────────
// Customer Search Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Handle customer search input with instant reactivity.
 * Updates the customerSearch ref which triggers computed filtering.
 * @param {Event} event - Input event from search field
 */
function handleSearchInput(event) {
	customerSearch.value = event.target.value;
}

// Track if customer history has been loaded this session
const customerHistoryLoaded = ref(false);

/**
 * Handle search input focus - shows frequent customers dropdown.
 */
function handleSearchFocus() {
	customerSearchFocused.value = true;
	// Load customer history only once per session for faster subsequent focuses
	if (!customerHistoryLoaded.value) {
		customerSearchStore.loadCustomerHistory();
		customerHistoryLoaded.value = true;
	}
}

/**
 * Handle search input blur - hides dropdown after a short delay.
 * Short delay as fallback for keyboard/tab navigation (mousedown.prevent handles click cases).
 */
function handleSearchBlur() {
	// Reduced delay - mousedown.prevent handles most cases, this is just for keyboard nav
	setTimeout(() => {
		customerSearchFocused.value = false;
	}, 100);
}

/**
 * Handle keyboard navigation in customer search dropdown.
 * Supports:
 * - ArrowDown/ArrowUp: Navigate through results
 * - Enter: Select current or auto-select single result
 * - Escape: Clear search
 *
 * @param {KeyboardEvent} event - Keyboard event from search input
 */
function handleKeydown(event) {
	if (customerResults.value.length === 0) return;

	if (event.key === "ArrowDown") {
		event.preventDefault();
		selectedIndex.value = Math.min(selectedIndex.value + 1, customerResults.value.length - 1);
	} else if (event.key === "ArrowUp") {
		event.preventDefault();
		selectedIndex.value = Math.max(selectedIndex.value - 1, -1);
	} else if (event.key === "Enter") {
		event.preventDefault();
		if (selectedIndex.value >= 0 && selectedIndex.value < customerResults.value.length) {
			selectCustomer(customerResults.value[selectedIndex.value]);
		} else if (customerResults.value.length === 1) {
			// Auto-select if only one result
			selectCustomer(customerResults.value[0]);
		}
	} else if (event.key === "Escape") {
		customerSearch.value = "";
	}
}

/**
 * Select a customer from search results.
 * Emits select-customer event and resets search state.
 * Tracks customer selection for frequency-based suggestions.
 * @param {Object} cust - Customer object to select
 */
function selectCustomer(cust) {
	// Track selection for frequent customers feature
	customerSearchStore.trackCustomerSelection(cust.name);
	emit("select-customer", cust);
	customerSearch.value = "";
	selectedIndex.value = -1;
	customerSearchFocused.value = false;
	previousCustomer.value = null;
}

/**
 * Remove the selected customer.
 * Clears the customer and focuses the search input.
 */
async function removeCustomer() {
	previousCustomer.value = null;
	await clearCustomer();
}

/**
 * Clear the currently selected customer.
 * Emits select-customer with null to deselect.
 */
async function clearCustomer() {
	emit("select-customer", null);
	await nextTick();
	const searchInput = document.getElementById("cart-customer-search");
	if (searchInput) {
		searchInput.focus();
	}
}

/**
 * Open customer creation dialog with current search text.
 * Pre-fills the new customer name with the search query.
 */
function createNewCustomer() {
	const searchValue = customerSearch.value;
	// Close dropdown immediately
	customerSearch.value = "";
	customerSearchFocused.value = false;
	// Emit event to open customer creation dialog
	emit("create-customer", searchValue);
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get initials from a customer name for avatar display.
 * Returns first letter of first two words, or first two letters if single word.
 *
 * @param {String} name - Customer name
 * @returns {String} 2-letter initials (uppercase)
 */
function getInitials(name) {
	if (!name) return "?";
	const parts = name.split(" ");
	if (parts.length >= 2) {
		return (parts[0][0] + parts[1][0]).toUpperCase();
	}
	return name.substring(0, 2).toUpperCase();
}

/**
 * Format a numeric amount as currency string.
 * Uses the component's currency prop for formatting.
 *
 * @param {Number} amount - Amount to format
 * @returns {String} Formatted currency string (e.g., "$1,234.56")
 */
function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

// ─────────────────────────────────────────────────────────────────────────────
// Quantity Control Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Intelligently determine the step size based on current quantity.
 * - Whole numbers (1, 2, 3): step by 1
 * - Multiples of 0.5 (1.5, 2.5): step by 0.5
 * - Multiples of 0.25 (0.25, 0.75): step by 0.25
 * - Multiples of 0.1 (0.1, 0.3): step by 0.1
 * - Other decimals: step by 0.01
 */
function getSmartStep(quantity) {
	// Check if it's a whole number
	if (quantity === Math.floor(quantity)) {
		return 1;
	}

	// Round to 4 decimal places to avoid floating point errors
	const rounded = Math.round(quantity * 10000) / 10000;

	// Check if it's a multiple of 0.5
	if (Math.abs(rounded % 0.5) < 0.0001) {
		return 0.5;
	}

	// Check if it's a multiple of 0.25
	if (Math.abs(rounded % 0.25) < 0.0001) {
		return 0.25;
	}

	// Check if it's a multiple of 0.1
	if (Math.abs(rounded % 0.1) < 0.0001) {
		return 0.1;
	}

	// For other decimals, use 0.01 for fine control
	return 0.01;
}

/**
 * Increment item quantity using smart step.
 * Uses getSmartStep to determine appropriate increment value.
 *
 * @param {Object} item - Cart item to increment
 */
function incrementQuantity(item) {
	// Prevent editing resolved barcode items
	if (item.is_resolved_barcode) return;

	const step = getSmartStep(item.quantity);
	const newQty = Math.round((item.quantity + step) * 10000) / 10000;
	emit("update-quantity", item.item_code, newQty, item.uom);
}

/**
 * Decrement item quantity using smart step.
 * Removes item if quantity would become zero or negative.
 *
 * @param {Object} item - Cart item to decrement
 */
function decrementQuantity(item) {
	// Prevent editing resolved barcode items
	if (item.is_resolved_barcode) return;

	const step = getSmartStep(item.quantity);
	const newQty = Math.round((item.quantity - step) * 10000) / 10000;

	if (newQty <= 0) {
		// If quantity would be 0 or negative, remove the item
		emit("remove-item", item.item_code, item.uom);
	} else {
		emit("update-quantity", item.item_code, newQty, item.uom);
	}
}

/**
 * Update quantity from direct input (manual typing).
 * Allows any positive number during typing without rounding.
 *
 * @param {Object} item - Cart item to update
 * @param {String} value - New quantity value from input
 */
  
function updateQuantity(item, value) {
	// Prevent editing resolved barcode items
	if (item.is_resolved_barcode) return;

	const qty = Number.parseFloat(value);

	// If the input isn't a valid number (e.g., user cleared the field), do nothing
	if (isNaN(qty)) return;

	// If quantity is zero or negative, remove the item from the cart
	if (qty <= 0) return emit("remove-item", item.item_code, item.uom);

	// For positive numbers, update quantity immediately (no rounding here while typing)
	emit("update-quantity", item.item_code, qty, item.uom);
}

/**
 * Handle quantity input blur - validate and round.
 * Called when user leaves the quantity input field.
 * - Removes item if quantity is 0 or invalid
 * - Rounds to 4 decimal places for consistency
 *
 * @param {Object} item - Cart item that lost focus
 */
function handleQuantityBlur(item) {
	// When user leaves the input field, round and validate
	if (!item.quantity || item.quantity <= 0) {
		// If quantity is 0 or invalid, remove the item
		emit("remove-item", item.item_code, item.uom);
	} else {
		// Round to 4 decimal places for consistency
		const roundedQty = Math.round(item.quantity * 10000) / 10000;
		if (roundedQty !== item.quantity) {
			emit("update-quantity", item.item_code, roundedQty, item.uom);
		}
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// UOM (Unit of Measure) Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Toggle UOM dropdown visibility for an item.
 * Uses unique key combining item_code + uom to handle same item with different UOMs.
 */
function toggleUomDropdown(itemCode, uom) {
	const key = `${itemCode}-${uom}`;
	openUomDropdown.value = openUomDropdown.value === key ? null : key;
}

/**
 * Select a UOM from dropdown - changes UOM and closes dropdown
 * Handles merging if target UOM already exists in cart
 */
async function selectUom(item, newUom) {
	if (item.uom === newUom) {
		openUomDropdown.value = null;
		return;
	}

	const currentUom = item.uom || item.stock_uom;
	await cartStore.changeItemUOM(item.item_code, newUom, currentUom);
	openUomDropdown.value = null;
	emit("update-uom", item.item_code, newUom);
}

// ─────────────────────────────────────────────────────────────────────────────
// Item Edit Dialog Functions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Open the edit item dialog for an item.
 * Creates a copy of the item to avoid mutating the original.
 * Used for serial number items and advanced editing.
 *
 * @param {Object} item - Cart item to edit
 */
function openEditDialog(item) {
	selectedItem.value = { ...item };
	showEditDialog.value = true;
}

/**
 * Handle item update from edit dialog.
 * Updates item via cart store and emits for parent compatibility.
 *
 * @param {Object} updatedItem - Updated item data from dialog
 */
async function handleUpdateItem(updatedItem) {
	// Get the original UOM from selectedItem (before any changes)
	const originalUom = selectedItem.value?.uom || selectedItem.value?.stock_uom;
	// Use store method to update item, passing original UOM to identify correct item
	await cartStore.updateItemDetails(updatedItem.item_code, updatedItem, originalUom);
	// Also emit for parent component compatibility
	emit("edit-item", updatedItem);
}

// ─────────────────────────────────────────────────────────────────────────────
// Event Handlers & Lifecycle
// ─────────────────────────────────────────────────────────────────────────────

function selectDocType(type) {
	cartStore.setTargetDoctype(type);
}

/**
 * Handle clicks outside interactive elements.
 * - Closes customer search dropdown when clicking outside
 * - Closes UOM dropdown when clicking outside
 *
 * @param {MouseEvent} event - Click event
 */
function handleOutsideClick(event) {
	const target = event.target;

	// Close customer search if clicking outside
	if (
		customerSearchContainer.value &&
		target instanceof Node &&
		!customerSearchContainer.value.contains(target)
	) {
		customerSearch.value = "";

		// Restore previous customer if set and no customer selected
		if (previousCustomer.value && !props.customer) {
			emit("select-customer", previousCustomer.value);
			previousCustomer.value = null;
		}
	}

	// Close UOM dropdown if clicking outside
	if (openUomDropdown.value !== null) {
		// Check if click is outside all UOM dropdowns
		const clickedInsideUomDropdown =
			target instanceof Element && target.closest(".group\\/uom");
		if (!clickedInsideUomDropdown) {
			openUomDropdown.value = null;
		}
	}
}

/**
 * Component mounted - register global click listener.
 * Used for click-outside detection on dropdowns.
 */
onMounted(() => {
	if (typeof document === "undefined") return;
	// Use mousedown instead of click to catch events before they are swallowed by other handlers
	document.addEventListener("mousedown", handleOutsideClick);
});

/**
 * Component unmounting - cleanup global click listener.
 * Prevents memory leaks by removing event listener.
 */
onBeforeUnmount(() => {
	if (typeof document === "undefined") return;
	document.removeEventListener("mousedown", handleOutsideClick);
});
</script>
```
