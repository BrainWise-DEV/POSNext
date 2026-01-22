<template>
	<Dialog v-model="show" :options="{ title: __('Complete Payment'), size: '4xl' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- INFORMATION SECTION (TOP) -->

				<!-- Payment Summary Card -->
				<div class="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
					<div class="flex justify-between items-start mb-3">
						<div>
							<div class="text-start text-xs font-medium text-gray-600 mb-1">{{ __('Total Amount') }}</div>
							<div class="text-start text-3xl font-bold text-gray-900">
								{{ formatCurrency(grandTotal) }}
							</div>
						</div>
						<div class="text-end">
							<div v-if="remainingAmount > 0" class="mb-2">
								<div class="text-start text-xs font-medium text-orange-600 mb-1">{{ __('Remaining') }}</div>
								<div class="text-start text-xl font-bold text-orange-600">
									{{ formatCurrency(remainingAmount) }}
								</div>
							</div>
							<div v-if="changeAmount > 0">
								<div class="text-start text-xs font-medium text-green-600 mb-1">{{ __('Change') }}</div>
								<div class="text-start text-xl font-bold text-green-600">
									{{ formatCurrency(changeAmount) }}
								</div>
							</div>
							<div v-if="totalPaid >= grandTotal && changeAmount === 0" class="flex items-center text-green-600">
								<svg class="w-5 h-5 me-1" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
								</svg>
								<span class="text-start text-xs font-semibold">{{ __('Paid in Full') }}</span>
							</div>
						</div>
					</div>

					<!-- Progress Bar -->
					<div class="w-full bg-white rounded-full h-2.5 overflow-hidden shadow-inner">
						<div
							:class="[
								'h-full transition-all duration-300',
								totalPaid >= grandTotal ? 'bg-green-500' : 'bg-blue-500'
							]"
							:style="{ width: `${grandTotal > 0 ? Math.min((totalPaid / grandTotal) * 100, 100) : 0}%` }"
						></div>
					</div>
					<div class="text-start text-xs text-gray-600 mt-1">
						{{ __('{0} paid of {1}', [formatCurrency(totalPaid), formatCurrency(grandTotal)]) }}
					</div>
				</div>

				<!-- Customer Credit Display -->
				<div
					v-if="allowCreditSale"
					:class="[
						'rounded-lg p-3 border-2',
						totalAvailableCredit > 0
							? 'bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200'
							: totalAvailableCredit < 0
							? 'bg-gradient-to-br from-red-50 to-rose-50 border-red-300'
							: 'bg-gradient-to-br from-gray-50 to-slate-50 border-gray-200'
					]"
				>
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-2">
							<div
								:class="[
									'w-8 h-8 rounded-full flex items-center justify-center',
									totalAvailableCredit > 0
										? 'bg-emerald-200'
										: totalAvailableCredit < 0
										? 'bg-red-200'
										: 'bg-gray-200'
								]"
							>
								<svg
									:class="[
										'w-5 h-5',
										totalAvailableCredit > 0
											? 'text-emerald-700'
											: totalAvailableCredit < 0
											? 'text-red-700'
											: 'text-gray-700'
									]"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										v-if="totalAvailableCredit >= 0"
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
									/>
									<path
										v-else
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
									/>
								</svg>
							</div>
							<div>
								<div class="text-start text-xs font-semibold text-gray-800">
									{{ totalAvailableCredit >= 0 ? __('Customer Credit Available') : __('Customer Outstanding Balance') }}
								</div>
								<div v-if="totalAvailableCredit > 0" class="text-start text-xs text-emerald-700">
									{{ __('Credit can be applied to invoice') }}
								</div>
								<div v-else-if="totalAvailableCredit < 0" class="text-start text-xs text-red-700">
									{{ __('Amount owed by customer') }}
								</div>
								<div v-else class="text-start text-xs text-gray-600">
									{{ __('No outstanding balance') }}
								</div>
							</div>
						</div>
						<div class="text-end">
							<div
								:class="[
									'text-start text-xs font-medium',
									totalAvailableCredit > 0
										? 'text-emerald-700'
										: totalAvailableCredit < 0
										? 'text-red-700'
										: 'text-gray-700'
								]"
							>
								{{ totalAvailableCredit >= 0 ? __('Available') : __('Outstanding') }}
							</div>
							<div
								:class="[
									'text-start text-2xl font-bold',
									totalAvailableCredit > 0
										? 'text-emerald-700'
										: totalAvailableCredit < 0
										? 'text-red-700'
										: 'text-gray-700'
								]"
							>
								{{ formatCurrency(Math.abs(totalAvailableCredit)) }}
							</div>
						</div>
					</div>
				</div>

					<!-- Additional Discount Section (Compact) -->
				<div v-if="settingsStore.allowAdditionalDiscount" class="bg-gradient-to-r from-orange-50 to-red-50 border border-orange-300 rounded-lg p-2">
					<div class="flex items-center justify-between mb-1.5">
						<div class="flex items-center gap-1.5">
							<div class="w-5 h-5 rounded-full bg-orange-200 flex items-center justify-center">
								<svg class="w-3 h-3 text-orange-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
								</svg>
							</div>
							<span class="text-[11px] font-bold text-orange-900">{{ __('Additional Discount') }}</span>
							<span v-if="localAdditionalDiscount > 0" class="text-[10px] font-bold text-red-600 bg-red-100 px-1.5 py-0.5 rounded">
								-{{ formatCurrency(additionalDiscountType === 'percentage' ? (subtotal * localAdditionalDiscount / 100) : localAdditionalDiscount) }}
							</span>
						</div>
						<button
							v-if="localAdditionalDiscount > 0"
							@click="clearAdditionalDiscount"
							class="text-[10px] text-orange-700 hover:text-orange-900 font-semibold px-1.5 py-0.5 bg-orange-100 hover:bg-orange-200 rounded transition-colors"
						>
							{{ __('Clear') }}
						</button>
					</div>
					<div class="grid grid-cols-[100px_1fr] gap-1.5">
						<!-- Discount Type Selector (Compact) -->
						<select
							v-model="additionalDiscountType"
							@change="handleAdditionalDiscountTypeChange"
							class="w-full px-1.5 py-1.5 text-[11px] font-medium border border-orange-300 rounded focus:outline-none focus:ring-1 focus:ring-orange-500 focus:border-transparent bg-white"
						>
							<option value="percentage">{{ __('% Percent') }}</option>
							<option value="amount">{{ __('{0} Amount', [currencySymbol]) }}</option>
						</select>
						<!-- Discount Value Input (Compact) -->
						<div class="relative">
							<span v-if="additionalDiscountType === 'amount'" class="absolute start-2 top-1/2 -translate-y-1/2 text-gray-600 text-[11px] font-medium">{{ currencySymbol }}</span>
							<input
								type="number"
								v-model.number="localAdditionalDiscount"
								@input="handleAdditionalDiscountChange"
								placeholder="0.00"
								min="0"
								:max="additionalDiscountType === 'percentage' ? 100 : subtotal"
								step="0.01"
								:class="[
									'w-full py-1.5 text-[11px] font-semibold border border-orange-300 rounded focus:outline-none focus:ring-1 focus:ring-orange-500 focus:border-transparent bg-white placeholder-gray-400',
									additionalDiscountType === 'amount' ? 'ps-9 pe-2' : 'px-2 pe-6'
								]"
							/>
							<span v-if="additionalDiscountType === 'percentage'" class="absolute end-2 top-1/2 -translate-y-1/2 text-gray-600 text-[11px] font-medium">%</span>
						</div>
					</div>
				</div>

				<!-- Finance Lender Payments Section -->
				<div class="text-start mb-3">
					<div class="flex items-center justify-between mb-3">
						<div>
							<h3 class="text-sm font-semibold text-gray-700 flex items-center gap-2">
								<svg class="w-4 h-4 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/>
								</svg>
								{{ __('Finance Lender Payments') }}
							</h3>
						</div>
						<Button
							variant="solid"
							theme="blue"
							size="sm"
							@click="addFinanceLenderRow"
							:disabled="remainingAmount === 0"
							class="shadow-sm"
						>
							<svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
							</svg>
							{{ __('Add Entry') }}
						</Button>
					</div>

					<!-- Loading State -->
					<div v-if="loadingFinanceLenders" class="flex items-center justify-center py-4 bg-gray-50 rounded-lg">
						<div class="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
						<span class="ms-2 text-sm text-gray-500">{{ __('Loading...') }}</span>
					</div>

					<!-- Finance Lender Payment Rows -->
					<div v-else class="space-y-2">
						<!-- Single Line Payment Entry Rows -->
						<div
							v-for="(row, index) in financeLenderPayments"
							:key="index"
							class="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg p-2"
						>
							<!-- Mode Selector -->
							<select
								v-model="row.mode"
								@change="handleModeChange(index)"
								class="w-24 flex-shrink-0 px-2 py-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white"
							>
								<option value="">{{ __('Mode') }}</option>
								<option value="Account">{{ __('Account') }}</option>
								<option value="Customer">{{ __('Customer') }}</option>
							</select>

							<!-- Finance Lender Selector -->
							<div class="relative flex-1 min-w-0">
								<input
									v-model="row.finance_lender_search"
									type="text"
									:placeholder="row.mode === 'Account' ? __('Search account...') : row.mode === 'Customer' ? __('Search customer...') : __('Select mode')"
									:disabled="!row.mode"
									class="w-full px-2 py-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white disabled:bg-gray-100 disabled:cursor-not-allowed"
									@focus="showLenderDropdown(index)"
									@input="searchFinanceLender(index)"
								/>
								<!-- Selected Lender Display Chip -->
								<div v-if="row.finance_lender && !row.showDropdown" class="absolute inset-0 flex items-center">
									<div class="flex items-center gap-1 mx-1 px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs flex-1 min-w-0">
										<span class="truncate">{{ row.finance_lender }}</span>
										<button
											@click.stop="clearFinanceLender(index)"
											class="flex-shrink-0 text-purple-500 hover:text-purple-700"
										>
											<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
												<path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
											</svg>
										</button>
									</div>
								</div>
								<!-- Dropdown Results -->
								<div
									v-if="row.showDropdown && row.lenderOptions.length > 0"
									class="absolute left-0 right-0 top-full mt-1 z-[9999] bg-white border border-gray-200 rounded-lg shadow-xl max-h-40 overflow-y-auto"
								>
									<div
										v-for="option in row.lenderOptions"
										:key="option.name"
										@click="selectFinanceLender(index, option)"
										class="px-3 py-2 hover:bg-purple-50 cursor-pointer border-b border-gray-100 last:border-b-0 transition-colors"
									>
										<div class="font-medium text-xs text-gray-900">{{ option.name }}</div>
										<div v-if="option.label" class="text-[10px] text-gray-500">{{ option.label }}</div>
									</div>
								</div>
								<!-- No Results -->
								<div
									v-if="row.showDropdown && row.lenderOptions.length === 0 && row.finance_lender_search"
									class="absolute left-0 right-0 top-full mt-1 z-[9999] bg-white border border-gray-200 rounded-lg shadow-xl p-2"
								>
									<div class="text-xs text-gray-500 text-center">{{ __('No results') }}</div>
								</div>
							</div>

							<!-- Amount Input -->
							<div class="relative w-28 flex-shrink-0">
								<span class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">{{ currencySymbol }}</span>
								<input
									v-model.number="row.amount"
									type="number"
									step="0.01"
									min="0"
									placeholder="0.00"
									class="w-full ps-6 pe-2 py-1.5 text-xs font-semibold border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white text-end"
									@input="recalculateFinanceLenderTotals"
								/>
							</div>

							<!-- Reference No Input -->
							<input
								v-model="row.reference_no"
								type="text"
								:placeholder="__('Ref No.')"
								class="w-24 flex-shrink-0 px-2 py-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white"
							/>

							<!-- Delete Button -->
							<button
								@click="removeFinanceLenderRow(index)"
								class="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-all flex-shrink-0"
								:title="__('Remove')"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>

						<!-- Empty State -->
						<div v-if="financeLenderPayments.length === 0" class="text-center py-6 bg-gray-50 border border-dashed border-gray-200 rounded-lg">
							<p class="text-xs text-gray-500">{{ __('Click "Add Entry" to add a finance lender payment') }}</p>
						</div>

						<!-- Total Summary -->
						<div v-if="financeLenderPayments.length > 0" class="bg-purple-50 border border-purple-200 rounded-lg p-3 mt-2">
							<div class="flex items-center justify-between">
								<span class="text-sm font-semibold text-gray-700">{{ __('Total Finance Lender Payments') }}</span>
								<span class="text-lg font-bold text-purple-600">{{ formatCurrency(financeLenderTotal) }}</span>
							</div>
						</div>
					</div>
				</div>

				<!-- Sales Persons Selection (Moved below Finance Lender Payments) -->
				<div v-if="settingsStore.enableSalesPersons" class="bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-200 rounded-lg p-3">
					<div class="flex items-center justify-between mb-2">
						<div class="flex items-center gap-2">
							<div class="w-6 h-6 rounded-full bg-purple-200 flex items-center justify-center">
								<svg class="w-4 h-4 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
								</svg>
							</div>
							<span class="text-xs font-bold text-purple-900">
								{{ settingsStore.isMultipleSalesPersons
									? __('Sales Persons')
									: __('Sales Person')
								}}
							</span>
							<span v-if="selectedSalesPersons.length > 0" class="text-xs font-bold text-purple-600 bg-purple-100 px-2 py-0.5 rounded">
								{{ settingsStore.isSingleSalesPerson
									? __('1 selected')
									: __('{0} selected', [selectedSalesPersons.length]) }}
							</span>
						</div>
						<button
							v-if="selectedSalesPersons.length > 0"
							@click="clearSalesPersons"
							class="text-xs text-purple-700 hover:text-purple-900 font-semibold px-2 py-1 bg-purple-100 hover:bg-purple-200 rounded transition-colors"
						>
							{{ settingsStore.isSingleSalesPerson ? __('Clear') : __('Clear All') }}
						</button>
					</div>

					<!-- Search Input -->
					<div class="relative mb-2">
						<input
							v-model="salesPersonSearch"
							type="text"
							:placeholder="__('Search sales person...')"
							class="w-full px-3 py-2 ps-9 text-xs border border-purple-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent bg-white"
						/>
						<svg class="w-4 h-4 text-gray-400 absolute start-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
					</div>

					<!-- Selected Sales Persons (Chips) -->
					<div v-if="selectedSalesPersons.length > 0" class="mb-2 flex flex-col gap-1.5">
						<div class="text-[10px] font-semibold text-purple-700 uppercase tracking-wide mb-1">{{ __('Selected:') }}</div>
						<div
							v-for="person in selectedSalesPersons"
							:key="person.sales_person"
							class="flex items-center justify-between p-2 bg-purple-100 border border-purple-300 rounded-lg"
						>
							<div class="flex items-center gap-2 flex-1">
								<button
									@click="removeSalesPerson(person.sales_person)"
									class="text-purple-600 hover:text-purple-800 hover:bg-purple-200 rounded p-0.5 transition-colors"
								>
									<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
									</svg>
								</button>
								<span class="text-xs font-medium text-gray-900 flex-1">
									{{ person.sales_person_name || person.sales_person }}
								</span>
							</div>
							<!-- Only show allocation input for Multiple mode -->
							<div v-if="settingsStore.isMultipleSalesPersons" class="flex items-center gap-1">
								<input
									type="number"
									:value="person.allocated_percentage"
									@input="updateSalesPersonAllocation(person.sales_person, $event.target.value)"
									placeholder="%"
									min="0"
									max="100"
									step="1"
									class="w-14 px-1.5 py-1 text-xs font-semibold text-end border border-purple-300 rounded focus:outline-none focus:ring-1 focus:ring-purple-500 bg-white"
								/>
								<span class="text-xs text-gray-600 font-medium">%</span>
							</div>
							<!-- Show 100% badge for Single mode -->
							<div v-else class="text-xs font-semibold text-purple-700 bg-purple-200 px-2 py-1 rounded">
								100%
							</div>
						</div>

						<!-- Total Allocation Warning (only for Multiple mode) -->
						<div v-if="settingsStore.isMultipleSalesPersons && totalAllocation !== 100" class="flex items-center gap-2 p-2 bg-yellow-50 border border-yellow-300 rounded mt-2">
							<svg class="w-4 h-4 text-yellow-600 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
								<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
							</svg>
							<span class="text-xs font-medium text-yellow-800">
								{{ __('Total: {0}% (should be 100%)', [totalAllocation]) }}
							</span>
						</div>
					</div>

					<!-- Available Sales Persons Dropdown -->
					<div v-if="filteredSalesPersons.length > 0 && salesPersonSearch" class="max-h-48 overflow-y-auto border border-purple-200 rounded-lg bg-white">
						<div
							v-for="person in filteredSalesPersons"
							:key="person.name"
							@click="addSalesPerson(person)"
							class="flex items-center justify-between p-2 hover:bg-purple-50 cursor-pointer border-b border-purple-100 last:border-b-0 transition-colors"
						>
							<div class="flex items-center gap-2">
								<svg class="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
								</svg>
								<div>
									<div class="text-xs font-medium text-gray-900">
										{{ person.sales_person_name || person.name }}
									</div>
									<div v-if="person.commission_rate" class="text-[10px] text-gray-500">
										{{ __('Commission: {0}%', [person.commission_rate]) }}
									</div>
								</div>
							</div>
						</div>
					</div>

					<!-- Empty State -->
					<div v-else-if="!salesPersonSearch && selectedSalesPersons.length === 0 && !loadingSalesPersons" class="text-center py-3">
						<svg class="w-8 h-8 text-gray-300 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
						<div class="text-xs text-gray-500">{{ __('Search to add sales persons') }}</div>
					</div>

					<!-- Loading State -->
					<div v-if="loadingSalesPersons" class="text-center py-3">
						<div class="text-xs text-gray-500">{{ __('Loading sales persons...') }}</div>
					</div>

					<!-- No Results -->
					<div v-if="salesPersonSearch && filteredSalesPersons.length === 0 && !loadingSalesPersons" class="text-center py-3">
						<div class="text-xs text-gray-500">{{ __('No sales persons found') }}</div>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<!-- Mobile Layout: Stacked buttons -->
			<div class="flex flex-col w-full gap-2 sm:hidden">
				<!-- Complete/Partial Payment Button -->
				<button
					@click="completePayment"
					:disabled="!canComplete"
					:class="[
						'w-full inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
						'h-12 text-base font-semibold px-4 rounded-lg touch-manipulation',
						!canComplete
							? 'bg-blue-300 text-white cursor-not-allowed'
							: 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-400'
					]"
				>
					<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
						<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
					</svg>
					<span>{{ paymentButtonText }}</span>
				</button>

				<!-- Pay on Account Button (if credit sales enabled) -->
				<button
					v-if="allowCreditSale"
					@click="addCreditAccountPayment"
					:disabled="paymentEntries.length > 0"
					:class="[
						'w-full inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
						'h-12 text-base font-semibold px-4 rounded-lg touch-manipulation',
						paymentEntries.length > 0
							? 'bg-orange-300 text-white cursor-not-allowed'
							: 'bg-orange-500 text-white hover:bg-orange-600 active:bg-orange-700 focus-visible:ring-2 focus-visible:ring-orange-400'
					]"
				>
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
					</svg>
					<span>{{ __('Pay on Account') }}</span>
				</button>

				<!-- Apply Credit Button (if available) - full width on mobile -->
				<button
					v-if="allowCreditSale && totalAvailableCredit > 0 && remainingAmount > 0"
					@click="applyCustomerCredit"
					class="w-full inline-flex items-center justify-center gap-2 h-11 px-4 text-sm font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 active:bg-emerald-200 rounded-lg transition-colors touch-manipulation"
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
					</svg>
					<span>{{ __('Apply Credit') }}</span>
				</button>

				<!-- Secondary row: Clear and Cancel - equal width side by side -->
				<div class="flex items-center gap-2 mt-1">
					<button
						@click="clearAll"
						:disabled="paymentEntries.length === 0"
						:class="[
							'flex-1 inline-flex items-center justify-center gap-1.5 h-11 px-3 text-sm font-medium rounded-lg transition-colors touch-manipulation',
							paymentEntries.length === 0
								? 'text-gray-400 bg-gray-50 cursor-not-allowed'
								: 'text-red-600 bg-red-50 hover:bg-red-100 active:bg-red-200'
						]"
					>
						<svg class="w-4 h-4 rtl:scale-x-[-1]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
						</svg>
						<span>{{ __('Clear') }}</span>
					</button>

					<button
						@click="show = false"
						class="flex-1 inline-flex items-center justify-center gap-1.5 h-11 px-3 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 active:bg-gray-300 rounded-lg transition-colors touch-manipulation"
					>
						<span>{{ __('Cancel') }}</span>
					</button>
				</div>
			</div>

			<!-- Desktop Layout: Single row with proper alignment -->
			<div class="hidden sm:flex items-center justify-between w-full gap-3">
				<!-- Start: Secondary actions -->
				<div class="flex items-center gap-2">
					<!-- Clear Button -->
					<button
						v-if="paymentEntries.length > 0"
						@click="clearAll"
						class="inline-flex items-center justify-center gap-1.5 h-9 px-3 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 active:bg-red-200 rounded-lg transition-colors"
					>
						<svg class="w-4 h-4 rtl:scale-x-[-1]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
						</svg>
						<span>{{ __('Clear All') }}</span>
					</button>

					<!-- Apply Credit Button (if available) -->
					<button
						v-if="allowCreditSale && totalAvailableCredit > 0 && remainingAmount > 0"
						@click="applyCustomerCredit"
						class="inline-flex items-center justify-center gap-1.5 h-9 px-3 text-sm font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 active:bg-emerald-200 rounded-lg transition-colors"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
						</svg>
						<span>{{ __('Apply Credit') }}</span>
					</button>
				</div>

				<!-- End: Primary actions -->
				<div class="flex items-center gap-2">
					<!-- Cancel Button -->
					<button
						@click="show = false"
						class="inline-flex items-center justify-center h-9 px-4 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 active:bg-gray-300 rounded-lg transition-colors"
					>
						{{ __('Cancel') }}
					</button>

					<!-- Pay on Account Button (if credit sales enabled) -->
					<button
						v-if="allowCreditSale"
						@click="addCreditAccountPayment"
						:disabled="paymentEntries.length > 0"
						:class="[
							'inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
							'h-9 text-sm font-semibold px-4 rounded-lg',
							paymentEntries.length > 0
								? 'bg-orange-300 text-white cursor-not-allowed'
								: 'bg-orange-500 text-white hover:bg-orange-600 active:bg-orange-700 focus-visible:ring-2 focus-visible:ring-orange-400'
						]"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
						</svg>
						<span>{{ __('Pay on Account') }}</span>
					</button>

					<!-- Complete/Partial Payment Button -->
					<button
						@click="completePayment"
						:disabled="!canComplete"
						:class="[
							'inline-flex items-center justify-center gap-2 transition-colors focus:outline-none',
							'h-9 text-sm font-semibold px-5 rounded-lg',
							!canComplete
								? 'bg-blue-300 text-white cursor-not-allowed'
								: 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 focus-visible:ring-2 focus-visible:ring-blue-400'
						]"
					>
						<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
						</svg>
						<span>{{ paymentButtonText }}</span>
					</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { usePOSSettingsStore } from "@/stores/posSettings"
import { formatCurrency as formatCurrencyUtil, getCurrencySymbol } from "@/utils/currency"
import { getPaymentIcon } from "@/utils/payment"
import { offlineWorker } from "@/utils/offline/workerClient"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import { useToast } from "@/composables/useToast"

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
	company: {
		type: String,
		default: "",
	},
	additionalDiscount: {
		type: Number,
		default: 0,
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

// Finance Lender Payments state
const financeLenderPayments = ref([])
const loadingFinanceLenders = ref(false)

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
	},
})

const customerCreditResource = createResource({
	url: "pos_next.api.credit_sales.get_available_credit",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		console.log('[PaymentDialog] Fetching credit for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		console.log('[PaymentDialog] Customer credit loaded:', data)
		customerCredit.value = data || []
		loadingCredit.value = false
		console.log('[PaymentDialog] Total available credit:', totalAvailableCredit.value)
	},
	onError(error) {
		console.error("[PaymentDialog] Error loading customer credit:", error)
		customerCredit.value = []
		loadingCredit.value = false
	},
})

const customerBalanceResource = createResource({
	url: "pos_next.api.credit_sales.get_customer_balance",
	makeParams() {
		const customerName = props.customer?.name || props.customer
		console.log('[PaymentDialog] Fetching balance for customer:', customerName)
		return {
			customer: customerName,
			company: props.company,
		}
	},
	auto: false,
	onSuccess(data) {
		console.log('[PaymentDialog] Customer balance loaded:', data)
		customerBalance.value = data || { total_outstanding: 0, total_credit: 0, net_balance: 0 }
		console.log('[PaymentDialog] Net balance:', customerBalance.value.net_balance)
	},
	onError(error) {
		console.error("[PaymentDialog] Error loading customer balance:", error)
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }
	},
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
		console.log('[PaymentDialog] Sales persons loaded:', data)
		salesPersons.value = data?.message || data || []
		loadingSalesPersons.value = false
	},
	onError(error) {
		console.error("[PaymentDialog] Error loading sales persons:", error)
		salesPersons.value = []
		loadingSalesPersons.value = false
	},
})

// Resource for searching Bank/Cash accounts
const searchAccountsResource = createResource({
	url: "pos_next.api.finance_lender.search_accounts",
	makeParams({ search_term }) {
		return {
			search_term: search_term || '',
			company: props.company,
		}
	},
	auto: false,
})

// Resource for searching Finance Lender customers
const searchFinanceLendersResource = createResource({
	url: "pos_next.api.finance_lender.search_finance_lenders",
	makeParams({ search_term }) {
		return {
			search_term: search_term || '',
		}
	},
	auto: false,
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

// Computed for total allocation percentage
const totalAllocation = computed(() => {
	return selectedSalesPersons.value.reduce((sum, person) => {
		return sum + (person.allocated_percentage || 0)
	}, 0)
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

function updateSalesPersonAllocation(personName, value) {
	const person = selectedSalesPersons.value.find(p => p.sales_person === personName)
	if (person) {
		person.allocated_percentage = Number.parseFloat(value) || 0
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
		console.warn(
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
		console.error("Error loading payment methods:", error)
	} finally {
		loadingPaymentMethods.value = false
	}
}

// Currency symbol for display
const currencySymbol = computed(() => getCurrencySymbol(props.currency))

// Helper to round to 2 decimal places (handles floating-point precision)
const round2 = (val) => Number(Number(val).toFixed(2))

const totalPaid = computed(() => {
	// Use finance lender payments total instead of payment entries
	return round2(financeLenderTotal.value)
})

// Finance Lender Total
const financeLenderTotal = computed(() => {
	const sum = financeLenderPayments.value.reduce(
		(sum, row) => sum + (row.amount || 0),
		0,
	)
	return round2(sum)
})

const totalAvailableCredit = computed(() => {
	// Use net_balance: negative means customer has credit, positive means they owe
	// Return negative of net_balance so positive = credit available, negative = outstanding
	return round2(-customerBalance.value.net_balance)
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
	// Check if we have valid finance lender payments
	const hasValidPayments = financeLenderPayments.value.length > 0 &&
		financeLenderPayments.value.some(row => row.amount > 0 && row.mode && row.finance_lender)
	
	// If partial payment is allowed, can complete with any amount > 0
	if (props.allowPartialPayment) {
		return totalPaid.value > 0 && hasValidPayments
	}
	// Otherwise require full payment
	return remainingAmount.value === 0 && hasValidPayments
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
			console.log('[PaymentDialog] Preloading payment methods for profile:', newProfile)
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
		lastSelectedMethod.value = null
		customerCredit.value = []
		customerBalance.value = { total_outstanding: 0, total_credit: 0, net_balance: 0 }
		selectedSalesPersons.value = []
		salesPersonSearch.value = ''
		
		// Reset finance lender payments
		financeLenderPayments.value = []

		// Debug logging
		console.log('[PaymentDialog] Dialog opened with props:', {
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
			console.log('[PaymentDialog] Loading customer credit and balance...')
			loadingCredit.value = true
			customerCreditResource.fetch()
			customerBalanceResource.fetch()
		} else {
			console.log('[PaymentDialog] Not loading credit because:', {
				allowCreditSale: props.allowCreditSale,
				hasCustomer: !!props.customer,
				hasCompany: !!props.company
			})
		}
	}
})

// One-click payment - adds remaining amount with selected method
function quickAddPayment(method) {
	console.log('[PaymentDialog] Quick add payment:', {
		method: method.mode_of_payment,
		remainingAmount: remainingAmount.value,
		currentEntries: paymentEntries.value.length
	})

	if (remainingAmount.value === 0) return

	lastSelectedMethod.value = method

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: Number.parseFloat(remainingAmount.value.toFixed(2)),
		type: method.type || __('Cash'),
	})

	console.log('[PaymentDialog] Payment added, new entries:', paymentEntries.value)
	customAmount.value = ""
}

// Add custom amount for a method
function addCustomPayment(method, amount) {
	console.log('[PaymentDialog] Add custom payment:', {
		method: method.mode_of_payment,
		amount: amount,
		currentEntries: paymentEntries.value.length
	})

	const amt = Number.parseFloat(amount)
	if (!amt || amt <= 0) return

	paymentEntries.value.push({
		mode_of_payment: method.mode_of_payment,
		amount: amt,
		type: method.type || __('Cash'),
	})

	console.log('[PaymentDialog] Payment added, new entries:', paymentEntries.value)
	customAmount.value = ""
}

// Apply existing customer credit to payment
function applyCustomerCredit() {
	console.log('[PaymentDialog] Apply customer credit:', {
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

	console.log('[PaymentDialog] Existing credit applied, new entries:', paymentEntries.value)
}

// Add "Pay on Account" - Credit Sale (invoice with outstanding amount)
function addCreditAccountPayment() {
	console.log('[PaymentDialog] Add credit account payment (Pay Later):', {
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

	console.log('[PaymentDialog] Emitting credit sale payment-completed:', paymentData)
	emit("payment-completed", paymentData)
	show.value = false
}

function removePaymentEntry(index) {
	paymentEntries.value.splice(index, 1)
}

function updatePaymentEntry(index, value) {
	const amt = Number.parseFloat(value)
	if (amt && amt > 0) {
		paymentEntries.value[index].amount = amt
	}
}

function clearAll() {
	paymentEntries.value = []
	customAmount.value = ""
	financeLenderPayments.value = []
}

// ============================================
// Finance Lender Payment Methods
// ============================================

function addFinanceLenderRow() {
	financeLenderPayments.value.push({
		mode: '',
		finance_lender: '',
		finance_lender_search: '',
		amount: 0,
		reference_no: '',
		showDropdown: false,
		lenderOptions: []
	})
}

function removeFinanceLenderRow(index) {
	financeLenderPayments.value.splice(index, 1)
}

function handleModeChange(index) {
	const row = financeLenderPayments.value[index]
	// Clear the lender selection when mode changes
	row.finance_lender = ''
	row.finance_lender_search = ''
	row.lenderOptions = []
	row.showDropdown = false
}

function showLenderDropdown(index) {
	const row = financeLenderPayments.value[index]
	if (row.mode) {
		row.showDropdown = true
		// Trigger search with empty string to show initial options
		searchFinanceLender(index)
	}
}

async function searchFinanceLender(index) {
	const row = financeLenderPayments.value[index]
	if (!row.mode) return

	row.showDropdown = true
	const searchTerm = row.finance_lender_search || ''

	console.log('[PaymentDialog] searchFinanceLender:', {
		index,
		mode: row.mode,
		searchTerm,
		company: props.company
	})

	try {
		if (row.mode === 'Account') {
			// Search for Bank/Cash accounts
			console.log('[PaymentDialog] Searching accounts with company:', props.company)
			const result = await searchAccountsResource.submit({
				search_term: searchTerm
			})
			console.log('[PaymentDialog] Account search result:', result)
			row.lenderOptions = (result || []).map(acc => ({
				name: acc.name,
				label: acc.account_type || ''
			}))
		} else if (row.mode === 'Customer') {
			// Search for customers in Finance Lender group
			const result = await searchFinanceLendersResource.submit({
				search_term: searchTerm
			})
			console.log('[PaymentDialog] Customer search result:', result)
			row.lenderOptions = (result || []).map(cust => ({
				name: cust.name,
				label: cust.customer_name || ''
			}))
		}
	} catch (error) {
		console.error('Error searching finance lenders:', error)
		row.lenderOptions = []
	}
}

function selectFinanceLender(index, option) {
	const row = financeLenderPayments.value[index]
	row.finance_lender = option.name
	row.finance_lender_search = option.name
	row.showDropdown = false
	row.lenderOptions = []
}

function clearFinanceLender(index) {
	const row = financeLenderPayments.value[index]
	row.finance_lender = ''
	row.finance_lender_search = ''
	row.showDropdown = false
}

function recalculateFinanceLenderTotals() {
	// Totals are computed automatically via the computed property
	// This function is a placeholder for any additional logic if needed
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
	financeLenderPayments.value.forEach(row => {
		row.showDropdown = false
	})
}

// ============================================
// End Finance Lender Payment Methods
// ============================================

function completePayment() {
	console.log('[PaymentDialog] Complete payment called:', {
		canComplete: canComplete.value,
		totalPaid: totalPaid.value,
		grandTotal: props.grandTotal,
		allowPartialPayment: props.allowPartialPayment,
		financeLenderPayments: financeLenderPayments.value,
		salesPersons: selectedSalesPersons.value
	})

	if (!canComplete.value) {
		console.warn('[PaymentDialog] Cannot complete - validation failed')
		return
	}

	const isPartial = totalPaid.value < props.grandTotal

	// Convert finance lender payments to the format expected by backend
	// These will be saved to custom_finance_lender_payments child table
	const financeLenderPaymentsData = financeLenderPayments.value
		.filter(row => row.amount > 0 && row.mode && row.finance_lender)
		.map(row => ({
			mode: row.mode,
			finance_lender: row.finance_lender,
			amount: row.amount,
			reference_no: row.reference_no || ''
		}))

	const paymentData = {
		payments: paymentEntries.value,
		finance_lender_payments: financeLenderPaymentsData,
		change_amount: changeAmount.value,
		is_partial_payment: isPartial,
		paid_amount: totalPaid.value,
		outstanding_amount: isPartial ? remainingAmount.value : 0,
		sales_team: selectedSalesPersons.value.length > 0 ? selectedSalesPersons.value : null,
	}

	console.log('[PaymentDialog] Emitting payment-completed:', paymentData)

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

function clearAdditionalDiscount() {
	localAdditionalDiscount.value = 0
	emit("update-additional-discount", 0)
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
