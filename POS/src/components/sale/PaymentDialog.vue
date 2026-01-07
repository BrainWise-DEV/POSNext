<template>
	<Dialog v-model="show" :options="{ title: isSalesOrder ? __('Complete Sales Order') : __('Complete Payment'), size: dynamicDialogSize }">
		<template #body-content>
			<!-- Two Column Layout - auto-sized on mobile, constrained on desktop -->
			<div
				:class="[
					'grid grid-cols-1 lg:grid-cols-5 items-stretch',
					dynamicGap,
					isMobileView ? '' : 'overflow-hidden'
				]"
				:style="isMobileView ? {} : { maxHeight: dialogContentMaxHeight }"
			>
				<!-- Left Column (2/5): Sales Person + Invoice Summary -->
				<div
					:class="[
						'lg:col-span-2 flex flex-col min-h-0',
						isSmallMobile ? 'gap-1' : 'gap-1.5',
						isMobileView ? 'overflow-visible' : 'overflow-hidden'
					]"
					:style="{ maxHeight: isMobileView ? 'none' : dynamicLeftColumnHeight }"
				>
					<!-- Delivery Date for Sales Orders -->
					<div v-if="isSalesOrder" class="bg-orange-50 border border-orange-200 rounded-lg p-2">
						<div class="flex items-center gap-2">
							<svg class="w-4 h-4 text-orange-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
							</svg>
							<label class="text-xs font-medium text-orange-700 flex-shrink-0">{{ __("Delivery Date") }}</label>
							<input
								type="date"
								v-model="deliveryDate"
								:min="today"
								class="flex-1 h-8 border border-orange-300 rounded-lg px-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent bg-white"
							/>
						</div>
					</div>

					<!-- Sales Person Selection (Compact) -->
					<div v-if="settingsStore.enableSalesPersons" class="bg-purple-50 border border-purple-200 rounded-lg p-2">
						<!-- Search Input with inline selected badge -->
						<div class="relative">
							<input
								v-model="salesPersonSearch"
								type="text"
								:placeholder="selectedSalesPersons.length > 0
									? selectedSalesPersons[0].sales_person_name || selectedSalesPersons[0].sales_person
									: __('Search sales person...')"
								class="w-full px-3 py-2 ps-9 pe-20 text-xs border border-purple-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent bg-white"
							/>
							<svg class="w-4 h-4 text-purple-500 absolute start-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
							</svg>
							<!-- Selected count badge -->
							<div v-if="selectedSalesPersons.length > 0" class="absolute end-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
								<span class="text-[10px] font-bold text-purple-600 bg-purple-100 px-1.5 py-0.5 rounded">
									{{ selectedSalesPersons.length }}
								</span>
								<button
									@click="clearSalesPersons"
									class="text-purple-500 hover:text-purple-700 p-0.5"
								>
									<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
									</svg>
								</button>
							</div>
						</div>

						<!-- Dropdown Results (only when searching) -->
						<div v-if="salesPersonSearch && filteredSalesPersons.length > 0" class="mt-1 max-h-32 overflow-y-auto border border-purple-200 rounded-lg bg-white">
							<div
								v-for="person in filteredSalesPersons"
								:key="person.name"
								@click="addSalesPerson(person)"
								class="flex items-center gap-2 p-2 hover:bg-purple-50 cursor-pointer border-b border-purple-100 last:border-b-0 text-xs"
							>
								<svg class="w-3.5 h-3.5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
								</svg>
								<span class="font-medium text-gray-900">{{ person.sales_person_name || person.name }}</span>
							</div>
						</div>

						<!-- No Results -->
						<div v-if="salesPersonSearch && filteredSalesPersons.length === 0 && !loadingSalesPersons" class="mt-1 text-center py-2 text-xs text-gray-500">
							{{ __('No sales persons found') }}
						</div>

						<!-- Selected Sales Persons (compact chips) -->
						<div v-if="selectedSalesPersons.length > 0 && !salesPersonSearch" class="mt-2 flex flex-wrap gap-1">
							<div
								v-for="person in selectedSalesPersons"
								:key="person.sales_person"
								class="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 border border-purple-300 rounded text-xs"
							>
								<span class="font-medium text-gray-900 truncate max-w-[100px]">
									{{ person.sales_person_name || person.sales_person }}
								</span>
								<span v-if="settingsStore.isMultipleSalesPersons" class="text-purple-600 font-semibold">
									{{ person.allocated_percentage }}%
								</span>
								<button
									@click="removeSalesPerson(person.sales_person)"
									class="text-purple-500 hover:text-purple-700"
								>
									<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
									</svg>
								</button>
							</div>
						</div>
					</div>

					<!-- Outstanding Balance Row (full width, two columns) -->
					<div v-if="allowCreditSale && totalAvailableCredit !== 0" :class="[
						'rounded-lg border p-2 flex items-center justify-between',
						totalAvailableCredit < 0
							? 'bg-red-50 border-red-200'
							: 'bg-emerald-50 border-emerald-200'
					]">
						<span :class="[
							'text-xs font-semibold',
							totalAvailableCredit < 0 ? 'text-red-700' : 'text-emerald-700'
						]">
							{{ totalAvailableCredit < 0 ? __('Outstanding Balance') : __('Credit Balance') }}
						</span>
						<!-- Show remaining credit (after used amount is deducted) for positive balance -->
						<span :class="[
							'text-base font-bold',
							totalAvailableCredit < 0 ? 'text-red-600' : 'text-emerald-600'
						]">
							{{ totalAvailableCredit < 0 ? formatCurrency(Math.abs(totalAvailableCredit)) : formatCurrency(remainingAvailableCredit) }}
						</span>
					</div>

					<!-- Invoice Summary -->
					<div class="bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col flex-1 min-h-0">
						<!-- Header -->
						<div :class="['px-3 border-b border-gray-200 bg-gray-50', isCompactMode ? 'py-1.5' : 'py-2']">
							<div class="flex items-center justify-between">
								<h3 :class="['text-gray-900 font-semibold text-start', dynamicTextSize.header]">{{ __('Invoice Summary') }}</h3>
								<span class="text-gray-500 text-xs text-end">{{ items.length === 1 ? __('1 item') : __('{0} items', [items.length]) }}</span>
							</div>
							<div v-if="customer" class="text-gray-600 text-xs mt-0.5 text-start">
								{{ customer?.customer_name || customer?.name || customer }}
							</div>
						</div>

						<!-- Items List (scrollable, takes available space) -->
						<div v-if="items.length > 0" class="flex-1 overflow-y-auto divide-y divide-gray-100 min-h-0">
							<div
								v-for="(item, index) in items"
								:key="index"
								class="px-3 py-2 hover:bg-gray-50"
							>
								<div class="flex items-start justify-between gap-2">
									<div class="flex-1 min-w-0 text-start">
										<div class="font-medium text-sm text-gray-900 truncate">{{ item.item_name || item.item_code }}</div>
										<div class="text-xs text-gray-500 mt-0.5">
											{{ formatCurrency(item.rate || item.price_list_rate) }} × {{ item.qty || item.quantity }}
										</div>
									</div>
									<div class="text-sm font-semibold text-gray-900 text-end">
										{{ formatCurrency(item.amount || ((item.qty || item.quantity) * (item.rate || item.price_list_rate))) }}
									</div>
								</div>
							</div>
						</div>
						<div v-else class="flex-1 px-3 py-4 text-center text-gray-400 text-sm flex items-center justify-center">
							{{ __('No items') }}
						</div>

						<!-- Amounts Breakdown -->
						<div class="border-t border-gray-200 bg-gray-50 px-3 py-2 space-y-1">
							<!-- Additional Discount Row -->
							<div v-if="settingsStore.allowAdditionalDiscount" class="pb-1.5 mb-1 border-b border-dashed border-orange-200">
								<!-- Label with calculated amount -->
								<div class="flex items-center justify-between gap-2 mb-1.5">
									<div class="flex items-center gap-1.5 min-w-0">
										<svg class="w-3.5 h-3.5 text-orange-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"/>
										</svg>
										<span class="text-xs font-medium text-orange-700">{{ __('Additional Discount') }}</span>
									</div>
									<span v-if="localAdditionalDiscount > 0" class="text-xs font-bold text-red-600">
										-{{ formatCurrency(calculatedAdditionalDiscount) }}
									</span>
								</div>
								<!-- Grid: 1/2 Counter Input, 1/4 Percentage, 1/4 Amount -->
								<div class="grid grid-cols-4 gap-1.5">
									<!-- Counter Input (2/4 = 1/2) -->
									<div class="col-span-2 flex items-center border border-orange-300 rounded-lg bg-white overflow-hidden">
										<!-- Decrement Button -->
										<button
											@click="decrementDiscount"
											:disabled="localAdditionalDiscount <= 0"
											class="h-9 w-9 flex items-center justify-center text-orange-600 hover:bg-orange-50 disabled:text-gray-300 disabled:hover:bg-transparent transition-colors flex-shrink-0"
										>
											<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
											</svg>
										</button>
										<!-- Input -->
										<input
											type="number"
											v-model.number="localAdditionalDiscount"
											@input="handleAdditionalDiscountChange"
											:placeholder="additionalDiscountType === 'percentage' ? '0' : '0.00'"
											min="0"
											:max="additionalDiscountType === 'percentage' ? 100 : subtotal"
											step="1"
											class="flex-1 h-9 px-1 text-sm font-semibold text-center bg-transparent border-none focus:outline-none focus:ring-0 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
										/>
										<!-- Increment Button -->
										<button
											@click="incrementDiscount"
											class="h-9 w-9 flex items-center justify-center text-orange-600 hover:bg-orange-50 transition-colors flex-shrink-0"
										>
											<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
											</svg>
										</button>
									</div>
									<!-- Percentage Button (1/4) -->
									<button
										@click="additionalDiscountType = 'percentage'; handleAdditionalDiscountTypeChange()"
										:class="[
											'h-9 rounded-lg text-sm font-bold transition-colors',
											additionalDiscountType === 'percentage'
												? 'bg-orange-500 text-white'
												: 'bg-white text-orange-600 border border-orange-300 hover:bg-orange-50'
										]"
									>
										%
									</button>
									<!-- Amount Button (1/4) -->
									<button
										@click="additionalDiscountType = 'amount'; handleAdditionalDiscountTypeChange()"
										:class="[
											'h-9 rounded-lg text-sm font-bold transition-colors',
											additionalDiscountType === 'amount'
												? 'bg-orange-500 text-white'
												: 'bg-white text-orange-600 border border-orange-300 hover:bg-orange-50'
										]"
									>
										{{ currencySymbol }}
									</button>
								</div>
							</div>
							<!-- Subtotal -->
							<div class="flex items-center justify-between text-sm">
								<span class="text-gray-600 text-start">{{ __('Subtotal') }}</span>
								<span class="font-medium text-gray-900 text-end">{{ formatCurrency(subtotal) }}</span>
							</div>
							<!-- Tax -->
							<div v-if="taxAmount > 0" class="flex items-center justify-between text-sm">
								<span class="text-gray-600 text-start">{{ __('Tax') }}</span>
								<span class="font-medium text-gray-900 text-end">{{ formatCurrency(taxAmount) }}</span>
							</div>
							<!-- Discount (shows the calculated additional discount amount) -->
							<div v-if="discountAmount > 0" class="flex items-center justify-between text-sm">
								<span class="text-gray-600 text-start">{{ __('Discount') }}</span>
								<span class="font-medium text-red-600 text-end">-{{ formatCurrency(discountAmount) }}</span>
							</div>
							<!-- Grand Total -->
							<div class="flex items-center justify-between pt-2 mt-1 border-t border-gray-300">
								<span :class="['font-bold text-gray-900 text-start', isCompactMode ? 'text-sm' : 'text-base']">{{ __('Grand Total') }}</span>
								<span :class="['font-bold text-gray-900 text-end', dynamicTextSize.grandTotal]">{{ formatCurrency(grandTotal) }}</span>
							</div>
						</div>

						<!-- Payment Status - Two Equal Halves -->
						<div class="border-t border-gray-200">
							<div class="grid grid-cols-2 divide-x divide-gray-200">
								<!-- Paid (Left Half) -->
								<div :class="['bg-blue-50 text-center', isCompactMode ? 'p-2' : 'p-3']">
									<div class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{{ __('Paid') }}</div>
									<div :class="['font-bold text-blue-600', dynamicTextSize.amount]">{{ formatCurrency(totalPaid) }}</div>
								</div>
								<!-- Remaining / Change (Right Half) -->
								<div v-if="remainingAmount > 0" :class="['bg-orange-50 text-center', isCompactMode ? 'p-2' : 'p-3']">
									<div class="text-xs font-medium text-orange-600 uppercase tracking-wide mb-1">{{ __('Remaining') }}</div>
									<div :class="['font-bold text-orange-600', dynamicTextSize.amount]">{{ formatCurrency(remainingAmount) }}</div>
								</div>
								<div v-else-if="changeAmount > 0" :class="['bg-green-50 text-center', isCompactMode ? 'p-2' : 'p-3']">
									<div class="text-xs font-medium text-green-600 uppercase tracking-wide mb-1">{{ __('Change Due') }}</div>
									<div :class="['font-bold text-green-600', dynamicTextSize.amount]">{{ formatCurrency(changeAmount) }}</div>
								</div>
								<div v-else :class="['bg-green-50 flex flex-col items-center justify-center', isCompactMode ? 'p-2' : 'p-3']">
									<svg class="w-5 h-5 text-green-600 mb-1" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
									</svg>
									<span :class="['font-bold text-green-600', dynamicTextSize.body]">{{ __('Fully Paid') }}</span>
								</div>
							</div>
						</div>
					</div>
				</div>
				<!-- End Left Column -->

				<!-- Right Column (3/5): Payment Methods + Quick Amounts + Numpad -->
				<div
					ref="rightColumnRef"
					:class="[
						'lg:col-span-3 bg-gray-50 rounded-lg border border-gray-200 flex flex-col',
						isSmallMobile ? 'p-1.5' : 'p-2 lg:p-3'
					]"
					:style="isMobileView ? {} : { minHeight: rightColumnMinHeight }"
				>
					<!-- Payment Methods -->
					<div :class="isSmallMobile ? 'mb-1' : 'mb-1.5 lg:mb-3'">
						<div :class="['flex items-center justify-between', isSmallMobile ? 'mb-0.5' : 'mb-1 lg:mb-2']">
							<div :class="['text-start font-semibold text-gray-500 uppercase tracking-wide', isSmallMobile ? 'text-[10px]' : 'text-xs']">{{ __('Payment Method') }}</div>
							<!-- Clear All Payments Button -->
							<button
								v-if="paymentEntries.length > 0"
								@click="clearAll"
								:class="['text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors', isSmallMobile ? 'p-1' : 'p-1.5']"
								:title="__('Clear all payments')"
							>
								<svg :class="isSmallMobile ? 'w-4 h-4' : 'w-5 h-5'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
								</svg>
							</button>
						</div>
						<div v-if="loadingPaymentMethods" class="flex items-center gap-2">
							<div :class="['animate-spin rounded-full border-b-2 border-blue-500', isSmallMobile ? 'h-4 w-4' : 'h-5 w-5']"></div>
							<span :class="['text-gray-500', isSmallMobile ? 'text-xs' : 'text-sm']">{{ __('Loading...') }}</span>
						</div>
						<div v-else-if="filteredPaymentMethods.length > 0" :class="['flex flex-wrap', isSmallMobile ? 'gap-1' : 'gap-1.5 lg:gap-2']">
							<button
								v-for="method in filteredPaymentMethods"
								:key="method.mode_of_payment"
								@pointerdown="onPaymentMethodDown(method, $event)"
								@pointerup="onPaymentMethodUp(method)"
								@pointerleave="onPaymentMethodCancel"
								@pointercancel="onPaymentMethodCancel"
								:disabled="isWalletPaymentMethod(method.mode_of_payment) && availableWalletBalance <= 0 && getMethodTotal(method.mode_of_payment) === 0"
								:class="[
									'inline-flex items-center rounded-lg border-2 transition-all font-medium select-none touch-none',
									isSmallMobile ? 'gap-0.5 px-1.5 h-7 text-[10px]' : 'gap-1 lg:gap-2 px-2.5 lg:px-4 h-8 text-xs lg:h-11 lg:text-sm',
									lastSelectedMethod?.mode_of_payment === method.mode_of_payment
										? isWalletPaymentMethod(method.mode_of_payment)
											? 'border-amber-500 bg-amber-50 text-amber-700'
											: 'border-blue-500 bg-blue-50 text-blue-700'
										: isWalletPaymentMethod(method.mode_of_payment)
											? availableWalletBalance > 0
												? 'border-amber-300 bg-amber-50 hover:border-amber-500 hover:bg-amber-100 text-amber-700'
												: 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed opacity-60'
											: 'border-gray-200 bg-white hover:border-blue-400 hover:bg-blue-50 text-gray-700'
								]"
							>
								<span :class="isSmallMobile ? 'text-xs' : 'text-sm lg:text-lg'">{{ isWalletPaymentMethod(method.mode_of_payment) ? '🎁' : getPaymentIcon(method.type) }}</span>
								<span class="truncate max-w-[80px] lg:max-w-none">{{ __(method.mode_of_payment) }}</span>
								<!-- Wallet Balance Badge -->
								<span v-if="isWalletPaymentMethod(method.mode_of_payment) && walletInfo.wallet_enabled"
									:class="['font-bold rounded', isSmallMobile ? 'text-[8px] px-1 py-0.5' : 'text-[10px] px-1.5 py-0.5', availableWalletBalance > 0 ? 'text-amber-700 bg-amber-100' : 'text-gray-500 bg-gray-200']">
									{{ formatCurrency(availableWalletBalance) }}
								</span>
								<!-- Payment Amount Badge -->
								<span v-if="getMethodTotal(method.mode_of_payment) > 0"
									:class="['font-bold rounded', isSmallMobile ? 'text-[8px] px-0.5 py-0.5' : 'text-xs px-1 py-0.5', isWalletPaymentMethod(method.mode_of_payment) ? 'text-amber-600 bg-amber-200' : 'text-blue-600 bg-blue-100']">
									{{ formatCurrency(getMethodTotal(method.mode_of_payment)) }}
								</span>
							</button>
							<!-- Credit Balance as Payment Method -->
							<button
								v-if="allowCreditSale && (remainingAvailableCredit > 0 || getMethodTotal('Customer Credit') > 0)"
								@click="applyCustomerCredit"
								:disabled="remainingAmount === 0 || remainingAvailableCredit === 0"
								:class="[
									'inline-flex items-center rounded-lg border-2 transition-all font-medium',
									isSmallMobile ? 'gap-0.5 px-1.5 h-7 text-[10px]' : 'gap-1 lg:gap-2 px-2.5 lg:px-4 h-8 text-xs lg:h-11 lg:text-sm',
									remainingAmount === 0 || remainingAvailableCredit === 0 ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
									getMethodTotal('Customer Credit') > 0
										? 'border-emerald-500 bg-emerald-50 text-emerald-700'
										: 'border-emerald-300 bg-emerald-50 hover:border-emerald-500 hover:bg-emerald-100 text-emerald-700'
								]"
							>
								<span :class="isSmallMobile ? 'text-xs' : 'text-sm lg:text-lg'">💳</span>
								<span class="truncate">{{ __('Credit Balance') }}</span>
								<span v-if="getMethodTotal('Customer Credit') > 0"
									:class="['font-bold text-emerald-600 bg-emerald-100 rounded', isSmallMobile ? 'text-[8px] px-0.5 py-0.5' : 'text-xs px-1 py-0.5']">
									{{ formatCurrency(getMethodTotal('Customer Credit')) }}
								</span>
							</button>
						</div>
						<div v-else :class="['text-gray-500', isSmallMobile ? 'text-xs' : 'text-sm']">{{ __('No payment methods available') }}</div>
					</div>

					<!-- Quick Amounts Area (Desktop) -->
					<div v-if="lastSelectedMethod && remainingAmount > 0" class="hidden lg:block" :class="isCompactMode ? 'mb-2' : 'mb-3'">
						<div class="text-start text-xs font-medium text-gray-600 mb-1.5">
							{{ __('Quick amounts for {0}', [__(lastSelectedMethod.mode_of_payment)]) }}
						</div>
						<div class="grid grid-cols-4 gap-1.5">
							<button
								v-for="amount in quickAmounts"
								:key="amount"
								@click="addCustomPayment(lastSelectedMethod, amount)"
								:class="[
									'font-semibold rounded-lg bg-white border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-700 hover:text-blue-600 transition-all',
									isCompactMode ? 'px-2 py-2 text-sm' : 'px-2 py-2 text-sm'
								]"
							>
								{{ formatCurrency(amount) }}
							</button>
						</div>
					</div>
					<div v-else-if="!lastSelectedMethod && remainingAmount > 0" class="hidden lg:block" :class="['bg-blue-50 rounded-lg text-center', isCompactMode ? 'mb-2 p-2' : 'mb-3 p-3 lg:p-2']">
						<p class="text-xs text-blue-600">{{ __('Select a payment method to start') }}</p>
					</div>

					<!-- Mobile Payment Section - Dynamic & Responsive -->
					<div class="lg:hidden flex flex-col" :class="isSmallMobile ? 'gap-1' : 'gap-1.5'">
						<!-- Mobile Quick Amounts + Custom Input -->
						<div v-if="lastSelectedMethod && remainingAmount > 0" :class="['space-y-1 flex-shrink-0', isSmallMobile ? 'mb-1' : 'mb-1.5']">
							<!-- Quick Amounts Row (4 columns, responsive sizing) -->
							<div class="grid grid-cols-4" :class="isSmallMobile ? 'gap-0.5' : 'gap-1'">
								<button
									v-for="amount in quickAmounts"
									:key="amount"
									@click="addCustomPayment(lastSelectedMethod, amount)"
									:class="[
										'font-semibold rounded bg-white border border-gray-200 text-gray-700 active:bg-blue-50 active:border-blue-400 transition-colors',
										isSmallMobile ? 'py-1 text-[10px]' : 'py-1.5 text-xs'
									]"
								>
									{{ formatCurrency(amount) }}
								</button>
							</div>

							<!-- Custom Amount Row -->
							<div :class="['flex', isSmallMobile ? 'gap-0.5' : 'gap-1']">
								<div class="relative flex-1">
									<span :class="[
										'absolute start-2 top-1/2 -translate-y-1/2 text-gray-400',
										isSmallMobile ? 'text-[10px]' : 'text-xs'
									]">{{ currencySymbol }}</span>
									<input
										v-model="mobileCustomAmount"
										type="number"
										inputmode="decimal"
										:placeholder="__('Custom')"
										min="0"
										step="0.01"
										:class="[
											'w-full border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white font-semibold',
											isSmallMobile ? 'h-7 ps-5 pe-1.5 text-xs' : 'h-8 ps-6 pe-2 text-sm'
										]"
									/>
								</div>
								<button
									@click="addMobileCustomPayment"
									:disabled="!mobileCustomAmount || mobileCustomAmount <= 0"
									:class="[
										'font-semibold rounded transition-all flex-shrink-0',
										isSmallMobile ? 'h-7 px-2 text-[10px]' : 'h-8 px-3 text-xs',
										!mobileCustomAmount || mobileCustomAmount <= 0
											? 'bg-gray-100 text-gray-400'
											: 'bg-blue-500 text-white active:bg-blue-600'
									]"
								>
									{{ __('Add') }}
								</button>
							</div>
						</div>

						<!-- Mobile: Select payment method prompt -->
						<div v-else-if="!lastSelectedMethod && remainingAmount > 0"
							:class="['bg-blue-50 rounded text-center', isSmallMobile ? 'p-1.5 mb-1' : 'p-2 mb-1.5']">
							<p :class="isSmallMobile ? 'text-[10px]' : 'text-xs'" class="text-blue-600">{{ __('Select a payment method') }}</p>
						</div>

						<!-- Mobile Action Buttons - Always visible at bottom -->
						<div :class="['flex-shrink-0', isSmallMobile ? 'space-y-1' : 'space-y-1.5']">
							<!-- Two buttons side by side when both needed -->
							<div v-if="lastSelectedMethod && remainingAmount > 0 && allowCreditSale && paymentEntries.length === 0"
								class="grid grid-cols-2" :class="isSmallMobile ? 'gap-1' : 'gap-1.5'">
								<!-- Pay Full Amount Button -->
								<button
									@click="addCustomPayment(lastSelectedMethod, remainingAmount)"
									:class="[
										'font-bold rounded-lg bg-green-500 text-white active:bg-green-600 flex items-center justify-center',
										mobileButtonSize.height, mobileButtonSize.text, mobileButtonSize.gap
									]"
								>
									<svg :class="mobileButtonSize.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
									</svg>
									<span class="truncate">{{ formatCurrency(remainingAmount) }}</span>
								</button>
								<!-- Pay on Account Button -->
								<button
									@click="addCreditAccountPayment"
									:disabled="isSubmitting"
									:class="[
										'font-semibold rounded-lg flex items-center justify-center',
										isSubmitting
											? 'bg-orange-300 text-white cursor-not-allowed'
											: 'bg-orange-500 text-white active:bg-orange-600',
										mobileButtonSize.height, mobileButtonSize.text, mobileButtonSize.gap
									]"
								>
									<svg v-if="isSubmitting" :class="mobileButtonSize.icon" class="animate-spin" fill="none" viewBox="0 0 24 24">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
									</svg>
									<svg v-else :class="mobileButtonSize.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
									</svg>
									<span class="truncate">{{ isSubmitting ? __('Processing...') : __('On Account') }}</span>
								</button>
							</div>

							<!-- Single Pay button (when no credit sale option) -->
							<button
								v-else-if="lastSelectedMethod && remainingAmount > 0"
								@click="addCustomPayment(lastSelectedMethod, remainingAmount)"
								:disabled="isSubmitting"
								:class="[
									'w-full font-bold rounded-lg flex items-center justify-center',
									isSubmitting
										? 'bg-green-300 text-white cursor-not-allowed'
										: 'bg-green-500 text-white active:bg-green-600',
									mobileButtonSize.height, mobileButtonSize.text, mobileButtonSize.gap
								]"
							>
								<svg :class="mobileButtonSize.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
								</svg>
								<span>{{ __('Pay') }} {{ formatCurrency(remainingAmount) }}</span>
							</button>

							<!-- Complete Payment Button -->
							<button
								v-if="remainingAmount === 0 && totalPaid > 0"
								@click="completePayment"
								:disabled="isSubmitting"
								:class="[
									'w-full font-bold rounded-lg flex items-center justify-center',
									isSubmitting
										? 'bg-blue-300 text-white cursor-not-allowed'
										: 'bg-blue-500 text-white active:bg-blue-600',
									mobileButtonSize.height, mobileButtonSize.text, mobileButtonSize.gap
								]"
							>
								<svg v-if="isSubmitting" :class="mobileButtonSize.icon" class="animate-spin" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								<svg v-else :class="mobileButtonSize.icon" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
								</svg>
								<span>{{ isSubmitting ? __('Processing...') : __('Complete Payment') }}</span>
							</button>
						</div>
					</div>
					<!-- End Mobile Payment Section -->

					<!-- Numeric Keypad (Desktop only) -->
					<div :class="['hidden lg:block bg-white rounded-lg border border-gray-200', isCompactMode ? 'p-2' : 'p-3']">
						<!-- Amount Display -->
						<div :class="['bg-gray-100 rounded-lg', isCompactMode ? 'p-2 mb-2' : 'p-3 mb-3']">
							<div dir="ltr" :class="['font-bold text-gray-900 text-center flex items-center justify-center gap-2', isCompactMode ? 'text-xl' : 'text-2xl']">
								<span>{{ currencySymbol }}</span>
								<span class="font-mono tracking-wider">{{ numpadDisplay || '0.00' }}</span>
							</div>
						</div>

						<!-- Keypad Grid (4 columns) -->
						<div :class="['grid grid-cols-4', isCompactMode ? 'gap-1' : 'gap-1.5']">
							<!-- Row 1: 7, 8, 9, Backspace -->
							<button
								v-for="num in ['7', '8', '9']"
								:key="num"
								@click="numpadInput(num)"
								:class="[dynamicNumpadSize.key, 'text-xl font-semibold rounded-lg bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800 transition-all active:scale-95']"
							>
								{{ num }}
							</button>
							<button
								@click="numpadBackspace"
								:class="[dynamicNumpadSize.key, 'text-lg font-semibold rounded-lg bg-red-50 border-2 border-red-200 hover:border-red-400 hover:bg-red-100 text-red-600 transition-all active:scale-95 flex items-center justify-center']"
							>
								<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M3 12l6.414 6.414a2 2 0 001.414.586H19a2 2 0 002-2V7a2 2 0 00-2-2h-8.172a2 2 0 00-1.414.586L3 12z"/>
								</svg>
							</button>

							<!-- Row 2: 4, 5, 6, Clear -->
							<button
								v-for="num in ['4', '5', '6']"
								:key="num"
								@click="numpadInput(num)"
								:class="[dynamicNumpadSize.key, 'text-xl font-semibold rounded-lg bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800 transition-all active:scale-95']"
							>
								{{ num }}
							</button>
							<button
								@click="numpadClear"
								:class="[dynamicNumpadSize.key, 'text-lg font-semibold rounded-lg bg-orange-50 border-2 border-orange-200 hover:border-orange-400 hover:bg-orange-100 text-orange-600 transition-all active:scale-95']"
							>
								C
							</button>

							<!-- Row 3: 1, 2, 3, Add (spans 2 rows) -->
							<button
								v-for="num in ['1', '2', '3']"
								:key="num"
								@click="numpadInput(num)"
								:class="[dynamicNumpadSize.key, 'text-xl font-semibold rounded-lg bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800 transition-all active:scale-95']"
							>
								{{ num }}
							</button>
							<button
								@click="numpadAddPayment"
								:disabled="!numpadValue || numpadValue <= 0 || !lastSelectedMethod"
								:class="[
									dynamicNumpadSize.addBtn, 'row-span-2 text-xl font-bold rounded-xl transition-all active:scale-95',
									!numpadValue || numpadValue <= 0 || !lastSelectedMethod
										? 'bg-gray-100 border-2 border-gray-200 text-gray-400 cursor-not-allowed'
										: 'bg-blue-600 border-2 border-blue-600 hover:bg-blue-700 text-white'
								]"
							>
								{{ __('Add') }}
							</button>

							<!-- Row 4: 00, 0, . -->
							<button
								@click="numpadInput('00')"
								:class="[isCompactMode ? 'h-12' : 'h-16', 'text-2xl font-semibold rounded-xl bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800 transition-all active:scale-95']"
							>
								00
							</button>
							<button
								@click="numpadInput('0')"
								:class="[isCompactMode ? 'h-12' : 'h-16', 'text-2xl font-semibold rounded-xl bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800 transition-all active:scale-95']"
							>
								0
							</button>
							<button
								@click="numpadInput('.')"
								:disabled="numpadDisplay.includes('.')"
								:class="[
									isCompactMode ? 'h-12' : 'h-16', 'text-2xl font-semibold rounded-xl transition-all active:scale-95',
									numpadDisplay.includes('.')
										? 'bg-gray-100 border-2 border-gray-200 text-gray-400 cursor-not-allowed'
										: 'bg-gray-50 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-gray-800'
								]"
							>
								.
							</button>
							</div>
						</div>

					<!-- Action Buttons - Below Keypad (Desktop only) -->
					<div :class="['hidden lg:flex items-center gap-2', isCompactMode ? 'mt-2' : 'mt-4']">
						<!-- Pay on Account Button (if credit sales enabled) -->
						<button
							v-if="allowCreditSale"
							@click="addCreditAccountPayment"
							:disabled="paymentEntries.length > 0 || isSubmitting"
							:class="[
								'flex-1 inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
								dynamicButtonHeight, 'text-sm font-semibold px-4 rounded-lg',
								paymentEntries.length > 0 || isSubmitting
									? 'bg-orange-300 text-white cursor-not-allowed'
									: 'bg-orange-500 text-white hover:bg-orange-600 active:bg-orange-700 focus-visible:ring-2 focus-visible:ring-orange-400'
							]"
						>
							<svg v-if="isSubmitting" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
							</svg>
							<svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
							</svg>
							<span>{{ isSubmitting ? __('Processing...') : __('Pay on Account') }}</span>
						</button>

						<!-- Complete/Partial Payment Button -->
						<button
							@click="completePayment"
							:disabled="!canComplete || isSubmitting"
							:class="[
								'flex-1 inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
								dynamicButtonHeight, 'text-sm font-semibold px-5 rounded-lg',
								!canComplete || isSubmitting
									? 'bg-blue-300 text-white cursor-not-allowed'
									: 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-400'
							]"
						>
							<svg v-if="isSubmitting" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
							</svg>
							<svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
								<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
							</svg>
							<span>{{ isSubmitting ? __('Processing...') : paymentButtonText }}</span>
						</button>
					</div>
				</div>
				<!-- End Right Column -->
			</div>
			<!-- End Two Column Layout -->
		</template>
	</Dialog>
</template>

<script setup>
import { usePOSSettingsStore } from "@/stores/posSettings"
import { formatCurrency as formatCurrencyUtil, getCurrencySymbol } from "@/utils/currency"
import { getPaymentIcon } from "@/utils/payment"
import { offlineWorker } from "@/utils/offline/workerClient"
import { logger } from "@/utils/logger"
import { Dialog, createResource, call } from "frappe-ui"
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from "vue"
import { useToast } from "@/composables/useToast"
import { useLongPress } from "@/composables/useLongPress"

const log = logger.create('PaymentDialog')
const settingsStore = usePOSSettingsStore()
const { showWarning } = useToast()

const props = defineProps({
	modelValue: Boolean,
	grandTotal: {
		type: Number,
		default: 0,
	},
	subtotal: {
		type: Number,
		default: 0,
	},
	posProfile: String,
	currency: {
		type: String,
		default: "USD",
	},
	isOffline: {
		type: Boolean,
		default: false,
	},
	allowPartialPayment: {
		type: Boolean,
		default: false,
	},
	allowCreditSale: {
		type: Boolean,
		default: false,
	},
	customer: {
		type: [String, Object],
		default: null,
	},
	items: {
		type: Array,
		default: () => [],
	},
	taxAmount: {
		type: Number,
		default: 0,
	},
	discountAmount: {
		type: Number,
		default: 0,
	},
	company: {
		type: String,
		default: "",
	},
	additionalDiscount: {
		type: Number,
		default: 0,
	},
	targetDoctype: {
		type: String,
		default: "Sales Invoice",
	},
	isSubmitting: {
		type: Boolean,
		default: false,
	},
})

const emit = defineEmits(["update:modelValue", "payment-completed", "update-additional-discount"])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
})

const paymentMethods = ref([])
const loadingPaymentMethods = ref(false)
const lastSelectedMethod = ref(null)
const customAmount = ref("")
const paymentEntries = ref([])
const customerCredit = ref([])
const customerBalance = ref({ total_outstanding: 0, total_credit: 0, net_balance: 0 })
const loadingCredit = ref(false)

// Wallet state
const walletInfo = ref({ wallet_enabled: false, wallet_exists: false, wallet_balance: 0, wallet_name: null })
const loadingWallet = ref(false)
const walletPaymentMethods = ref(new Set()) // Set of mode_of_payment names that are wallet payments

// Delivery date for Sales Orders
const deliveryDate = ref("")
const today = new Date().toISOString().split("T")[0]
const isSalesOrder = computed(() => props.targetDoctype === "Sales Order")

// Column refs for height matching
const rightColumnRef = ref(null)
const rightColumnMinHeight = ref('auto')

// Viewport dimension tracking for dynamic sizing
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1200)
const viewportHeight = ref(typeof window !== 'undefined' ? window.innerHeight : 800)

function updateViewportDimensions() {
	viewportWidth.value = window.innerWidth
	viewportHeight.value = window.innerHeight
}

onMounted(() => {
	updateViewportDimensions()
	window.addEventListener('resize', updateViewportDimensions)
})

onUnmounted(() => {
	window.removeEventListener('resize', updateViewportDimensions)
})

// Dynamic dialog size based on viewport
const dynamicDialogSize = computed(() => {
	const width = viewportWidth.value
	if (width < 640) return 'full' // Mobile: full screen
	if (width < 768) return 'full' // Small tablet: full screen for better usability
	if (width < 1024) return '4xl' // Tablet
	if (width < 1280) return '5xl' // Small desktop
	return '6xl' // Large desktop
})

// Check if we're on a mobile device (for mobile-specific behavior)
const isMobileView = computed(() => viewportWidth.value < 1024)

// Dynamic content max height based on viewport
const dialogContentMaxHeight = computed(() => {
	const height = viewportHeight.value
	const width = viewportWidth.value

	// On mobile, don't set max-height - let content determine size
	if (width < 1024) {
		return 'none'
	}
	// Desktop: use fixed pixel calculation
	const availableHeight = height - 100
	return `${Math.min(Math.max(500, availableHeight), height - 80)}px`
})

// Dynamic column heights based on viewport
const dynamicLeftColumnHeight = computed(() => {
	const height = viewportHeight.value
	if (viewportWidth.value < 1024) {
		// Mobile/tablet: auto height, will stack
		return 'auto'
	}
	// Desktop: calculate based on available space
	const availableHeight = height - 160 // Header + padding + action buttons
	return `${Math.max(400, Math.min(availableHeight, height - 120))}px`
})

// Check if we're in compact mode (small screens)
const isCompactMode = computed(() => viewportHeight.value < 700 || viewportWidth.value < 1024)

// Check if we're on a very small mobile screen
const isSmallMobile = computed(() => viewportWidth.value < 360 || viewportHeight.value < 600)

// Dynamic gap and padding based on screen size
const dynamicGap = computed(() => {
	if (viewportWidth.value < 360) return 'gap-1' // Very small phones
	if (viewportWidth.value < 640) return 'gap-1.5'
	if (viewportWidth.value < 1024) return 'gap-2'
	return 'gap-3'
})

// Dynamic text sizes
const dynamicTextSize = computed(() => {
	const width = viewportWidth.value
	const height = viewportHeight.value

	// Very small phones
	if (width < 360 || height < 550) {
		return {
			header: 'text-[10px]',
			body: 'text-[10px]',
			amount: 'text-base',
			grandTotal: 'text-base',
		}
	}
	// Small phones
	if (width < 640) {
		return {
			header: 'text-xs',
			body: 'text-xs',
			amount: 'text-lg',
			grandTotal: 'text-lg',
		}
	}
	// Tablet and small height screens
	if (height < 700) {
		return {
			header: 'text-sm',
			body: 'text-sm',
			amount: 'text-lg',
			grandTotal: 'text-xl',
		}
	}
	// Default desktop
	return {
		header: 'text-sm',
		body: 'text-sm',
		amount: 'text-xl',
		grandTotal: 'text-2xl',
	}
})

// Dynamic button heights
const dynamicButtonHeight = computed(() => {
	const width = viewportWidth.value
	const height = viewportHeight.value

	// Very small phones - smaller buttons
	if (width < 360 || height < 550) return 'h-9'
	// Small phones
	if (width < 640) return 'h-10'
	// Short screens
	if (height < 700) return 'h-10'
	return 'h-12'
})

// Mobile action button sizing
const mobileButtonSize = computed(() => {
	const width = viewportWidth.value
	const height = viewportHeight.value

	if (width < 360 || height < 550) {
		return {
			height: 'h-9',
			text: 'text-xs',
			icon: 'w-3.5 h-3.5',
			gap: 'gap-1',
		}
	}
	if (width < 640) {
		return {
			height: 'h-10',
			text: 'text-sm',
			icon: 'w-4 h-4',
			gap: 'gap-1.5',
		}
	}
	return {
		height: 'h-11',
		text: 'text-sm',
		icon: 'w-4 h-4',
		gap: 'gap-2',
	}
})

// Dynamic numpad key size
const dynamicNumpadSize = computed(() => {
	if (viewportHeight.value < 600) return { key: 'h-10', addBtn: 'h-[6.5rem]' }
	if (viewportHeight.value < 700) return { key: 'h-10', addBtn: 'h-[7rem]' }
	return { key: 'h-12', addBtn: 'h-[8.5rem]' }
})

// Calculate and sync column heights when dialog opens
function syncColumnHeights() {
	nextTick(() => {
		if (rightColumnRef.value) {
			const rightHeight = rightColumnRef.value.offsetHeight
			// Preserve initial height to prevent shrinking when Quick Amounts is hidden
			rightColumnMinHeight.value = `${rightHeight}px`
		}
	})
}

// Watch for dialog open to sync heights
watch(() => props.modelValue, (isOpen) => {
	if (isOpen) {
		// Reset min height when dialog opens so we can measure fresh
		rightColumnMinHeight.value = 'auto'
		// Small delay to ensure DOM is rendered
		setTimeout(syncColumnHeights, 100)
	}
})

// Numpad state
const numpadDisplay = ref('')
const numpadValue = computed(() => {
	const val = Number.parseFloat(numpadDisplay.value)
	return Number.isNaN(val) ? 0 : val
})

// Mobile custom amount state
const mobileCustomAmount = ref('')

function addMobileCustomPayment() {
	const amount = Number.parseFloat(mobileCustomAmount.value)
	if (amount > 0 && lastSelectedMethod.value) {
		addCustomPayment(lastSelectedMethod.value, amount)
		mobileCustomAmount.value = ''
	}
}

// Numpad functions
function numpadInput(char) {
	// Prevent multiple decimal points
	if (char === '.' && numpadDisplay.value.includes('.')) {
		return
	}

	// Limit decimal places to 2
	if (numpadDisplay.value.includes('.')) {
		const [, decimal] = numpadDisplay.value.split('.')
		if (decimal && decimal.length >= 2) {
			return
		}
	}

	// Limit total length to reasonable amount
	if (numpadDisplay.value.length >= 10) {
		return
	}

	// Add the character
	numpadDisplay.value += char
}

function numpadBackspace() {
	numpadDisplay.value = numpadDisplay.value.slice(0, -1)
}

function numpadClear() {
	numpadDisplay.value = ''
}

function numpadAddPayment() {
	if (numpadValue.value > 0 && lastSelectedMethod.value) {
		addCustomPayment(lastSelectedMethod.value, numpadValue.value)
		numpadClear()
	}
}

// Additional discount state
const localAdditionalDiscount = ref(0)
// Initialize discount type from settings (default to percentage if enabled, otherwise amount)
const additionalDiscountType = ref(
	settingsStore.usePercentageDiscount ? 'percentage' : 'amount'
)

const paymentMethodsResource = createResource({
	url: "pos_next.api.pos_profile.get_payment_methods",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		paymentMethods.value = data?.message || data || []
		// Set first method as last selected for quick amounts
		if (paymentMethods.value.length > 0) {
			const defaultMethod = paymentMethods.value.find((m) => m.default)
			lastSelectedMethod.value = defaultMethod || paymentMethods.value[0]
		}
		// Identify wallet payment methods
		identifyWalletPaymentMethods()
	},
})

const customerCreditResource = createResource({
	url: "pos_next.api.credit_sales.get_available_credit",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		log.debug('[PaymentDialog] Fetching credit for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		log.debug('[PaymentDialog] Customer credit loaded:', data)
		customerCredit.value = data || []
		loadingCredit.value = false
		log.debug('[PaymentDialog] Total available credit:', totalAvailableCredit.value)
	},
	onError(error) {
		log.error("[PaymentDialog] Error loading customer credit:", error)
		customerCredit.value = []
		loadingCredit.value = false
	},
})

const customerBalanceResource = createResource({
	url: "pos_next.api.credit_sales.get_customer_balance",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		log.debug('[PaymentDialog] Fetching balance for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
		}
	},
	auto: false,
	onSuccess(data) {
		log.debug('[PaymentDialog] Customer balance loaded:', data)
		customerBalance.value = data || { total_outstanding: 0, total_credit: 0, net_balance: 0 }
		log.debug('[PaymentDialog] Net balance:', customerBalance.value.net_balance)
	},
	onError(error) {
		log.error("[PaymentDialog] Error loading customer balance:", error)
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }
	},
})

// Wallet resource
const walletInfoResource = createResource({
	url: "pos_next.api.wallet.get_wallet_info",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		log.debug('[PaymentDialog] Fetching wallet info for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		log.debug('[PaymentDialog] Wallet info loaded:', data)
		walletInfo.value = data || { wallet_enabled: false, wallet_exists: false, wallet_balance: 0, wallet_name: null }
		loadingWallet.value = false
	},
	onError(error) {
		log.error("[PaymentDialog] Error loading wallet info:", error)
		walletInfo.value = { wallet_enabled: false, wallet_exists: false, wallet_balance: 0, wallet_name: null }
		loadingWallet.value = false
	},
})

// Identify which payment methods are wallet payments
async function identifyWalletPaymentMethods() {
	walletPaymentMethods.value = new Set()

	for (const method of paymentMethods.value) {
		try {
			// Check if the mode of payment has is_wallet_payment flag
			const result = await call('frappe.client.get_value', {
				doctype: 'Mode of Payment',
				filters: { name: method.mode_of_payment },
				fieldname: 'is_wallet_payment'
			})
			if (result?.is_wallet_payment) {
				walletPaymentMethods.value.add(method.mode_of_payment)
				log.debug('[PaymentDialog] Wallet payment method identified:', method.mode_of_payment)
			}
		} catch (error) {
			log.error('[PaymentDialog] Error checking wallet payment method:', error)
		}
	}
}

// Check if a payment method is a wallet payment
function isWalletPaymentMethod(methodName) {
	return walletPaymentMethods.value.has(methodName)
}

// Get available wallet balance for payment (considering already added wallet payments)
const availableWalletBalance = computed(() => {
	const totalWalletPayments = paymentEntries.value
		.filter(p => isWalletPaymentMethod(p.mode_of_payment))
		.reduce((sum, p) => sum + (p.amount || 0), 0)
	return Math.max(0, walletInfo.value.wallet_balance - totalWalletPayments)
})

// Filter payment methods - hide wallet methods when loyalty is not enabled
const filteredPaymentMethods = computed(() => {
	return paymentMethods.value.filter(method => {
		// If it's a wallet payment method, only show when loyalty/wallet is enabled
		if (isWalletPaymentMethod(method.mode_of_payment)) {
			return walletInfo.value.wallet_enabled
		}
		return true
	})
})

// Sales Persons state
const salesPersons = ref([])
const selectedSalesPersons = ref([])
const salesPersonSearch = ref('')
const loadingSalesPersons = ref(false)

const salesPersonsResource = createResource({
	url: "pos_next.api.pos_profile.get_sales_persons",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		log.debug('[PaymentDialog] Sales persons loaded:', data)
		salesPersons.value = data?.message || data || []
		loadingSalesPersons.value = false
	},
	onError(error) {
		log.error("[PaymentDialog] Error loading sales persons:", error)
		salesPersons.value = []
		loadingSalesPersons.value = false
	},
})

// Computed: Filter sales persons based on search and exclude already selected
const filteredSalesPersons = computed(() => {
	if (!salesPersonSearch.value) {
		return []
	}

	const searchLower = salesPersonSearch.value.toLowerCase()
	const selectedIds = selectedSalesPersons.value.map(p => p.sales_person)

	return salesPersons.value
		.filter(person => {
			// Exclude already selected
			if (selectedIds.includes(person.name)) {
				return false
			}
			// Filter by search term
			const name = (person.sales_person_name || person.name || '').toLowerCase()
			return name.includes(searchLower)
		})
		.slice(0, 10) // Limit to 10 results for performance
})

// Helper functions for sales persons
function addSalesPerson(person) {
	// For Single mode, replace the existing selection
	if (settingsStore.isSingleSalesPerson) {
		selectedSalesPersons.value = [{
			sales_person: person.name,
			sales_person_name: person.sales_person_name || person.name,
			allocated_percentage: 100, // Always 100% for single mode
			commission_rate: person.commission_rate,
		}]
	} else {
		// For Multiple mode, add to the list
		// Calculate default allocation
		const defaultAllocation = selectedSalesPersons.value.length === 0 ? 100 : 0

		selectedSalesPersons.value.push({
			sales_person: person.name,
			sales_person_name: person.sales_person_name || person.name,
			allocated_percentage: defaultAllocation,
			commission_rate: person.commission_rate,
		})
	}

	// Clear search after adding
	salesPersonSearch.value = ''
}

function removeSalesPerson(personName) {
	const index = selectedSalesPersons.value.findIndex(p => p.sales_person === personName)
	if (index > -1) {
		selectedSalesPersons.value.splice(index, 1)
	}
}

function clearSalesPersons() {
	selectedSalesPersons.value = []
	salesPersonSearch.value = ''
}

// Load payment methods - from cache if offline, from server if online
async function loadPaymentMethods() {
	// Guard: Don't load if posProfile is not set or already loading
	if (!props.posProfile) {
		log.warn(
			"PaymentDialog: Cannot load payment methods - posProfile is not set",
		)
		return
	}

	// Skip if already loading or already loaded for this profile
	if (loadingPaymentMethods.value) {
		return
	}

	loadingPaymentMethods.value = true

	try {
		if (props.isOffline) {
			// Load from cache when offline using worker
			const cached = await offlineWorker.getCachedPaymentMethods(props.posProfile)
			if (cached && cached.length > 0) {
				paymentMethods.value = cached
				if (paymentMethods.value.length > 0) {
					const defaultMethod = paymentMethods.value.find((m) => m.default)
					lastSelectedMethod.value = defaultMethod || paymentMethods.value[0]
				}
			}
		} else {
			// Load from server when online
			await paymentMethodsResource.fetch()
		}
	} catch (error) {
		log.error("Error loading payment methods:", error)
	} finally {
		loadingPaymentMethods.value = false
	}
}

// Currency symbol for display
const currencySymbol = computed(() => getCurrencySymbol(props.currency))

// Helper to round to 2 decimal places (handles floating-point precision)
const round2 = (val) => Number(Number(val).toFixed(2))

const totalPaid = computed(() => {
	const sum = paymentEntries.value.reduce(
		(sum, entry) => sum + (entry.amount || 0),
		0,
	)
	return round2(sum)
})

const totalAvailableCredit = computed(() => {
	// Use net_balance: negative means customer has credit, positive means they owe
	// Return negative of net_balance so positive = credit available, negative = outstanding
	return round2(-customerBalance.value.net_balance)
})

// Remaining credit after deducting what's already been applied as payment
const remainingAvailableCredit = computed(() => {
	const usedCredit = getMethodTotal('Customer Credit')
	const remaining = totalAvailableCredit.value - usedCredit
	return remaining > 0 ? round2(remaining) : 0
})

// Calculate the actual discount amount based on type (percentage or fixed amount)
const calculatedAdditionalDiscount = computed(() => {
	if (additionalDiscountType.value === 'percentage') {
		return round2((props.subtotal * localAdditionalDiscount.value) / 100)
	}
	return round2(localAdditionalDiscount.value)
})

const remainingAmount = computed(() => {
	const remaining = round2(props.grandTotal) - totalPaid.value
	return remaining > 0 ? round2(remaining) : 0
})

const changeAmount = computed(() => {
	const change = totalPaid.value - round2(props.grandTotal)
	return change > 0 ? round2(change) : 0
})

const canComplete = computed(() => {
	// If partial payment is allowed, can complete with any amount > 0
	if (props.allowPartialPayment) {
		return totalPaid.value > 0 && paymentEntries.value.length > 0
	}
	// Otherwise require full payment
	return remainingAmount.value === 0 && paymentEntries.value.length > 0
})

const paymentButtonText = computed(() => {
	if (remainingAmount.value === 0) {
		return __("Complete Payment")
	}
	if (props.allowPartialPayment && totalPaid.value > 0) {
		return __("Partial Payment")
	}
	return __("Complete Payment")
})

const quickAmounts = computed(() => {
	const remaining = remainingAmount.value
	if (remaining <= 0) {
		return [10, 20, 50, 100]
	}

	const amounts = new Set()
	const exactAmount = Math.ceil(remaining)

	// Always include exact amount first
	amounts.add(exactAmount)

	// Determine appropriate denominations based on amount size
	// For amounts < 50, use smaller denominations
	// For amounts >= 50, skip to larger denominations for meaningful differences
	let denominations
	if (remaining < 20) {
		denominations = [5, 10, 20, 50]
	} else if (remaining < 100) {
		denominations = [10, 20, 50, 100]
	} else if (remaining < 500) {
		denominations = [50, 100, 200, 500]
	} else if (remaining < 2000) {
		denominations = [100, 200, 500, 1000]
	} else {
		denominations = [500, 1000, 2000, 5000]
	}

	// Minimum gap between suggestions (at least 5% or 5, whichever is larger)
	const minGap = Math.max(5, exactAmount * 0.05)

	// Helper to check if amount is far enough from existing amounts
	const isFarEnough = (newAmt) => {
		for (const existing of amounts) {
			if (Math.abs(newAmt - existing) < minGap) return false
		}
		return true
	}

	// Add round-up amounts for each denomination
	for (const denom of denominations) {
		if (amounts.size >= 4) break

		// Round up to next multiple of this denomination
		const roundedUp = Math.ceil(remaining / denom) * denom

		// Add if it's meaningfully different from exact amount
		if (roundedUp > exactAmount && isFarEnough(roundedUp)) {
			amounts.add(roundedUp)
		}

		// Also add one step higher for convenience (e.g., 350 when remaining is 299)
		if (amounts.size < 4) {
			const oneStepUp = roundedUp + denom
			if (oneStepUp > exactAmount && isFarEnough(oneStepUp)) {
				amounts.add(oneStepUp)
			}
		}
	}

	// Convert to array, sort, and limit to 4
	return Array.from(amounts)
		.filter((amt) => amt > 0)
		.sort((a, b) => a - b)
		.slice(0, 4)
})

// Preload payment methods when posProfile is set (before dialog opens)
watch(
	() => props.posProfile,
	(newProfile) => {
		if (newProfile) {
			log.debug('[PaymentDialog] Preloading payment methods for profile:', newProfile)
			loadPaymentMethods()
			// Also preload sales persons if enabled
			if (settingsStore.enableSalesPersons && salesPersons.value.length === 0) {
				loadingSalesPersons.value = true
				salesPersonsResource.fetch()
			}
		}
	},
	{ immediate: true } // Load immediately if posProfile is already set
)

watch(show, (newVal) => {
	if (newVal) {
		// Reset state when dialog opens
		paymentEntries.value = []
		customAmount.value = ""
		numpadDisplay.value = ""
		mobileCustomAmount.value = ""
		lastSelectedMethod.value = null
		customerCredit.value = []
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }
		selectedSalesPersons.value = []
		salesPersonSearch.value = ''
		// Set default delivery date to today for Sales Orders
		deliveryDate.value = isSalesOrder.value ? today : ""

		// Debug logging
		log.debug('[PaymentDialog] Dialog opened with props:', {
			allowCreditSale: props.allowCreditSale,
			customer: props.customer,
			company: props.company,
			posProfile: props.posProfile
		})

		// Set default payment method if already loaded
		if (paymentMethods.value.length > 0 && !lastSelectedMethod.value) {
			const defaultMethod = paymentMethods.value.find((m) => m.default)
			lastSelectedMethod.value = defaultMethod || paymentMethods.value[0]
		}

		// Load customer credit and balance if enabled and customer is selected
		if (props.allowCreditSale && props.customer && props.company) {
			log.debug('[PaymentDialog] Loading customer credit and balance...')
			loadingCredit.value = true
			customerCreditResource.fetch()
			customerBalanceResource.fetch()
		} else {
			log.debug('[PaymentDialog] Not loading credit because:', {
				allowCreditSale: props.allowCreditSale,
				hasCustomer: !!props.customer,
				hasCompany: !!props.company
			})
		}

		// Load wallet info if customer is selected
		if (props.customer && props.company) {
			log.debug('[PaymentDialog] Loading wallet info...')
			loadingWallet.value = true
			walletInfoResource.fetch()
		} else {
			// Reset wallet info only if no customer
			walletInfo.value = { wallet_enabled: false, wallet_exists: false, wallet_balance: 0, wallet_name: null }
		}
	}
})

// ===========================================
// Payment Method Press Handler (Long Press Support)
// Uses composable for clean, reusable press handling
// ===========================================

// Select payment method (tap action)
function selectPaymentMethod(method) {
	lastSelectedMethod.value = method
	log.debug('[PaymentDialog] Selected payment method:', method.mode_of_payment)
}

// Helper to get default non-wallet payment method
function getDefaultNonWalletMethod() {
	// First try to find the default method that's not a wallet payment
	const defaultMethod = paymentMethods.value.find(m => m.default && !isWalletPaymentMethod(m.mode_of_payment))
	if (defaultMethod) return defaultMethod

	// Otherwise, find any non-wallet method (preferably Cash)
	const cashMethod = paymentMethods.value.find(m =>
		!isWalletPaymentMethod(m.mode_of_payment) &&
		(m.mode_of_payment.toLowerCase().includes('cash') || m.type?.toLowerCase() === 'cash')
	)
	if (cashMethod) return cashMethod

	// Fall back to first non-wallet method
	return paymentMethods.value.find(m => !isWalletPaymentMethod(m.mode_of_payment))
}

// Helper to switch to next payment method after partial wallet payment
function switchToNextPaymentMethod(partialAmount) {
	const nextMethod = getDefaultNonWalletMethod()
	if (nextMethod) {
		lastSelectedMethod.value = nextMethod
		// Pre-fill numpad with remaining amount for convenience
		const newRemaining = round2(remainingAmount.value)
		if (newRemaining > 0) {
			numpadDisplay.value = newRemaining.toFixed(2)
			// Also set mobile custom amount
			mobileCustomAmount.value = newRemaining.toFixed(2)
		}
		frappe.show_alert({
			message: __('Points applied: {0}. Please pay remaining {1} with {2}',
				[formatCurrency(partialAmount), formatCurrency(newRemaining), __(nextMethod.mode_of_payment)]),
			indicator: 'blue'
		})
	}
}

// Quick add payment (long press action)
function quickAddPayment(method) {
	if (remainingAmount.value <= 0) return

	lastSelectedMethod.value = method

	let amt = remainingAmount.value
	let isPartialWalletPayment = false

	// Wallet payment validation: limit to available balance
	if (isWalletPaymentMethod(method.mode_of_payment)) {
		const walletAvailable = availableWalletBalance.value
		if (walletAvailable <= 0) {
			frappe.show_alert({
				message: __('No redeemable points available'),
				indicator: 'orange'
			})
			return
		}
		if (amt > walletAvailable) {
			// Limit payment to available redeemable points
			amt = walletAvailable
			isPartialWalletPayment = true
		}
	}

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: Number.parseFloat(amt.toFixed(2)),
		type: method.type || __('Cash'),
		is_wallet_payment: isWalletPaymentMethod(method.mode_of_payment),
	})
	log.debug('[PaymentDialog] Long press payment added:', method.mode_of_payment)

	// If this was a partial wallet payment, switch to another payment method
	if (isPartialWalletPayment) {
		nextTick(() => {
			switchToNextPaymentMethod(amt)
		})
	}
}

// Initialize long press composable with callbacks
const {
	onPointerDown: handlePointerDown,
	onPointerUp: handlePointerUp,
	onPointerCancel: handlePointerCancel,
} = useLongPress({
	duration: 500,
	onTap: selectPaymentMethod,
	onLongPress: quickAddPayment,
})

// Wrapper handlers to pass method to composable
function onPaymentMethodDown(method, event) {
	handlePointerDown(event, method)
}

function onPaymentMethodUp(method) {
	handlePointerUp(method)
}

function onPaymentMethodCancel() {
	handlePointerCancel()
}

// Add custom amount for a method
function addCustomPayment(method, amount) {
	log.debug('[PaymentDialog] Add custom payment:', {
		method: method.mode_of_payment,
		amount: amount,
		currentEntries: paymentEntries.value.length
	})

	let amt = Number.parseFloat(amount)
	if (!amt || amt <= 0) return

	let isPartialWalletPayment = false

	// Wallet payment validation: limit to available balance
	if (isWalletPaymentMethod(method.mode_of_payment)) {
		const walletAvailable = availableWalletBalance.value
		if (walletAvailable <= 0) {
			frappe.show_alert({
				message: __('No redeemable points available'),
				indicator: 'orange'
			})
			return
		}
		if (amt > walletAvailable) {
			// Limit payment to available redeemable points
			amt = walletAvailable
			isPartialWalletPayment = true
		}
	}

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: amt,
		type: method.type || __('Cash'),
		is_wallet_payment: isWalletPaymentMethod(method.mode_of_payment),
	})

	log.debug('[PaymentDialog] Payment added, new entries:', paymentEntries.value)
	customAmount.value = ""

	// If this was a partial wallet payment, switch to another payment method
	if (isPartialWalletPayment) {
		nextTick(() => {
			switchToNextPaymentMethod(amt)
		})
	}
}

// Apply existing customer credit to payment
function applyCustomerCredit() {
	log.debug('[PaymentDialog] Apply customer credit:', {
		totalCredit: totalAvailableCredit.value,
		remainingAmount: remainingAmount.value,
		currentEntries: paymentEntries.value.length
	})

	if (remainingAmount.value === 0 || totalAvailableCredit.value === 0) return

	// Calculate how much credit to apply (min of remaining amount and available credit)
	const creditToApply = Math.min(remainingAmount.value, totalAvailableCredit.value)

	// Add credit as a payment entry
	paymentEntries.value.push({
		mode_of_payment: "Customer Credit",
		amount: Number.parseFloat(creditToApply.toFixed(2)),
		type: "Credit",
		is_customer_credit: true,
		credit_details: customerCredit.value.map(credit => ({
			...credit,
			credit_to_redeem: 0  // Will be calculated on backend
		}))
	})

	log.debug('[PaymentDialog] Existing credit applied, new entries:', paymentEntries.value)
}

// Add "Pay on Account" - Credit Sale (invoice with outstanding amount)
function addCreditAccountPayment() {
	log.debug('[PaymentDialog] Add credit account payment (Pay Later):', {
		grandTotal: props.grandTotal,
		currentPaid: totalPaid.value,
		remainingAmount: remainingAmount.value
	})

	// Close dialog and complete as credit sale (0 payment)
	// The backend will create an invoice with outstanding amount
	const paymentData = {
		payments: [],  // No payments - full amount on credit
		change_amount: 0,
		is_partial_payment: false,
		is_credit_sale: true,  // Mark as credit sale
		paid_amount: 0,
		outstanding_amount: props.grandTotal,
	}

	log.debug('[PaymentDialog] Emitting credit sale payment-completed:', paymentData)
	emit("payment-completed", paymentData)
	show.value = false
}

function clearAll() {
	paymentEntries.value = []
	customAmount.value = ""
}

function completePayment() {
	log.debug('[PaymentDialog] Complete payment called:', {
		canComplete: canComplete.value,
		totalPaid: totalPaid.value,
		grandTotal: props.grandTotal,
		allowPartialPayment: props.allowPartialPayment,
		paymentEntries: paymentEntries.value,
		salesPersons: selectedSalesPersons.value
	})

	if (!canComplete.value) {
		log.warn('[PaymentDialog] Cannot complete - validation failed')
		return
	}

	const isPartial = totalPaid.value < props.grandTotal

	const paymentData = {
		payments: paymentEntries.value,
		change_amount: changeAmount.value,
		is_partial_payment: isPartial,
		paid_amount: totalPaid.value,
		outstanding_amount: isPartial ? remainingAmount.value : 0,
		sales_team: selectedSalesPersons.value.length > 0 ? selectedSalesPersons.value : null,
		delivery_date: isSalesOrder.value ? deliveryDate.value : null,
	}

	log.debug('[PaymentDialog] Emitting payment-completed:', paymentData)

	emit("payment-completed", paymentData)

	show.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

// Get total amount for a specific payment method
function getMethodTotal(methodName) {
	return paymentEntries.value
		.filter((entry) => entry.mode_of_payment === methodName)
		.reduce((sum, entry) => sum + (entry.amount || 0), 0)
}


// Additional discount handlers
function handleAdditionalDiscountChange() {
	let discountValue = localAdditionalDiscount.value
	let discountAmount = 0

	// If percentage mode, calculate amount
	if (additionalDiscountType.value === 'percentage') {
		// Validate against max_discount_allowed if configured
		if (settingsStore.maxDiscountAllowed > 0 && discountValue > settingsStore.maxDiscountAllowed) {
			localAdditionalDiscount.value = settingsStore.maxDiscountAllowed
			discountValue = settingsStore.maxDiscountAllowed
			// Show warning toast
			showWarning(__('Maximum allowed discount is {0}%', [settingsStore.maxDiscountAllowed]))
		}

		// Ensure percentage is between 0-100
		if (discountValue > 100) {
			localAdditionalDiscount.value = 100
			discountValue = 100
		}

		// Convert percentage to amount
		discountAmount = (props.subtotal * discountValue) / 100
	} else {
		// Amount mode
		discountAmount = discountValue

		// For amount mode, check if it exceeds percentage limit when converted
		if (settingsStore.maxDiscountAllowed > 0 && props.subtotal > 0) {
			const percentageEquivalent = (discountAmount / props.subtotal) * 100
			if (percentageEquivalent > settingsStore.maxDiscountAllowed) {
				const maxAmount = (props.subtotal * settingsStore.maxDiscountAllowed) / 100
				localAdditionalDiscount.value = maxAmount
				discountAmount = maxAmount
				// Show warning toast
				showWarning(__('Maximum allowed discount is {0}% ({1} {2})',
				[settingsStore.maxDiscountAllowed, props.currency, maxAmount.toFixed(2)]))
			}
		}
	}

	// Ensure discount doesn't exceed subtotal
	if (discountAmount > props.subtotal) {
		if (additionalDiscountType.value === 'amount') {
			localAdditionalDiscount.value = props.subtotal
		}
		discountAmount = props.subtotal
	}

	// Ensure non-negative
	if (discountAmount < 0) {
		localAdditionalDiscount.value = 0
		discountAmount = 0
	}

	emit("update-additional-discount", discountAmount)
}

function handleAdditionalDiscountTypeChange() {
	// Don't reset - preserve last value when toggling type
	// Just recalculate to ensure it's within limits
	handleAdditionalDiscountChange()
}

function incrementDiscount() {
	const step = additionalDiscountType.value === 'percentage' ? 1 : 5
	localAdditionalDiscount.value = (localAdditionalDiscount.value || 0) + step
	handleAdditionalDiscountChange()
}

function decrementDiscount() {
	const step = additionalDiscountType.value === 'percentage' ? 1 : 5
	const newValue = (localAdditionalDiscount.value || 0) - step
	localAdditionalDiscount.value = newValue < 0 ? 0 : newValue
	handleAdditionalDiscountChange()
}

// Watch for dialog open to sync additional discount from parent
watch(
	() => props.modelValue,
	(isOpen) => {
		if (isOpen) {
			// Only sync when dialog opens, not continuously
			localAdditionalDiscount.value = props.additionalDiscount || 0
		}
	},
)
</script>
