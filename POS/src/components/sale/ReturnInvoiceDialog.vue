<template>
	<Dialog
        v-model="show"
        :options="{ title: __('Create Return Invoice'), size: '5xl' }"
    >
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Recent Invoices List -->
				<div>
					<label class="block text-sm text-start font-medium text-gray-700 mb-3">
						{{ __('Select Invoice to Return') }}
					</label>

					<!-- Search/Filter Input -->
					<div class="mb-3 flex gap-2">
						<Input
							v-model="invoiceListFilter"
							type="text"
							:placeholder="__('Search by invoice number or customer name...')"
							class="flex-1"
						/>
						<Button
							variant="subtle"
							@click="loadInvoicesResource.reload()"
							:loading="loadInvoicesResource.loading"
							:title="__('Refresh')"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
							</svg>
						</Button>
					</div>

					<!-- Loading State -->
					<div v-if="loadInvoicesResource.loading" class="text-center py-8">
						<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
						<p class="mt-2 text-xs text-gray-500">{{ __('Loading invoices...') }}</p>
					</div>

					<!-- Invoice List -->
					<div v-else class="max-h-96 overflow-y-auto flex flex-col gap-2 pe-2">
						<div
							v-for="invoice in filteredInvoiceList"
							:key="invoice.name"
							@click="openReturnModal(invoice)"
							class="bg-white border border-gray-200 rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50/30 cursor-pointer transition-all"
						>
							<div class="flex items-start justify-between gap-3">
								<!-- Invoice Info (Start Side) -->
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 flex-wrap">
										<h4 class="text-sm font-bold text-gray-900">{{ invoice.name }}</h4>
										<span :class="['px-2 py-0.5 text-xs font-semibold rounded-full whitespace-nowrap', getInvoiceStatusColor(invoice)]">
											{{ __(invoice.status) }}
										</span>
									</div>
									<p class="text-xs text-gray-600 mt-1 text-start">{{ invoice.customer_name }}</p>
									<p class="text-xs text-gray-500 text-start">{{ formatDate(invoice.posting_date) }}</p>
								</div>
								<!-- Amount (End Side) -->
								<div class="text-end flex-shrink-0">
									<p class="text-sm font-bold text-gray-900">{{ formatCurrency(invoice.grand_total) }}</p>
								</div>
							</div>
						</div>
						<p v-if="!loadInvoicesResource.loading && filteredInvoiceList.length === 0" class="text-center py-8 text-gray-500 text-sm">
							{{ __('No invoices found') }}
						</p>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="show = false">
				{{ __('Close') }}
			</Button>
		</template>
	</Dialog>

	<!-- Return Process Modal -->
	<Dialog
		v-model="returnModal.visible"
		:options="{ title: __('Process Return'), size: '5xl' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Invoice Details -->
				<div v-if="originalInvoice" class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 sm:p-5 border border-blue-100 shadow-sm">
					<!-- Mobile Layout -->
					<div class="sm:hidden flex flex-col gap-3">
						<div class="flex items-start gap-2">
							<svg class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
							</svg>
							<div class="flex-1 min-w-0">
								<h3 class="text-base font-bold text-gray-900">
									{{ originalInvoice.name }}
								</h3>
								<span :class="['inline-block mt-1 px-2 py-0.5 text-xs font-semibold rounded-full', getInvoiceStatusColor(originalInvoice)]">
									{{ __(originalInvoice.status) }}
								</span>
							</div>
						</div>
						<div class="flex flex-col gap-2">
							<div class="text-start">
								<p class="text-xs text-gray-500">{{ __('Customer') }}</p>
								<p class="text-sm font-semibold text-gray-900">{{ originalInvoice.customer_name }}</p>
							</div>
							<div class="flex items-center justify-between">
								<div class="text-start">
									<p class="text-xs text-gray-500">{{ __('Date') }}</p>
									<p class="text-sm font-semibold text-gray-900">{{ formatDate(originalInvoice.posting_date) }}</p>
								</div>
								<div class="text-end">
									<p class="text-xs text-gray-500 mb-1">{{ __('Total') }}</p>
									<p class="text-xl font-bold text-gray-900">
										{{ formatCurrency(originalInvoice.grand_total) }}
									</p>
								</div>
							</div>
						</div>
					</div>

					<!-- Desktop Layout -->
					<div class="hidden sm:flex items-start justify-between">
						<div class="flex-1">
							<div class="flex items-center gap-2">
								<svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
								</svg>
								<h3 class="text-base font-bold text-gray-900">
									{{ originalInvoice.name }}
								</h3>
								<span :class="['px-2 py-0.5 text-xs font-semibold rounded-full', getInvoiceStatusColor(originalInvoice)]">
									{{ __(originalInvoice.status) }}
								</span>
							</div>
							<div class="mt-3 grid grid-cols-2 gap-6">
								<div class="text-start">
									<p class="text-xs text-gray-500 mb-1">{{ __('Customer') }}</p>
									<p class="text-sm font-semibold text-gray-900">{{ originalInvoice.customer_name }}</p>
								</div>
								<div class="text-start">
									<p class="text-xs text-gray-500 mb-1">{{ __('Date') }}</p>
									<p class="text-sm font-semibold text-gray-900">{{ formatDate(originalInvoice.posting_date) }}</p>
								</div>
							</div>
						</div>
						<div class="text-end ms-4">
							<p class="text-xs text-gray-500 mb-1">{{ __('Total Amount') }}</p>
							<p class="text-2xl font-bold text-gray-900">
								{{ formatCurrency(originalInvoice.grand_total) }}
							</p>
						</div>
					</div>
				</div>

				<!-- Return Items -->
				<div v-if="originalInvoice">
								<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2">
									<label class="text-sm font-medium text-gray-700 text-start">
										{{ __('Select Items to Return') }}
									</label>
									<div class="flex gap-2 self-end sm:self-auto">
										<Button size="sm" variant="subtle" @click="selectAllFilteredItems">
											<span class="text-xs whitespace-nowrap">{{ __('Select All') }}</span>
										</Button>
										<Button size="sm" variant="subtle" @click="deselectAllItems">
											<span class="text-xs whitespace-nowrap">{{ __('Clear All') }}</span>
										</Button>
									</div>
								</div>

								<!-- Search bar for items (shown when more than 7 items) -->
								<div v-if="returnItems.length > 7" class="mb-3 relative">
									<input
										v-model="itemSearchFilter"
										type="text"
										:placeholder="__('Search items by name or code...')"
										class="w-full px-4 py-2.5 ps-10 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
									/>
									<svg class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
									</svg>
								</div>

								<div class="flex flex-col gap-2 max-h-96 overflow-y-auto pe-2">
									<div
										v-for="(item, index) in filteredReturnItems"
										:key="index"
										@click="toggleItemSelection(item)"
										:class="[
											'bg-white border rounded-xl p-4 transition-all duration-200 cursor-pointer',
											item.selected
												? 'border-blue-400 shadow-md bg-blue-50/30'
												: 'border-gray-200 hover:border-gray-300 hover:shadow-sm'
										]"
									>
										<!-- Desktop Layout -->
										<div class="hidden sm:flex items-center gap-4">
											<!-- Checkbox -->
											<input
												type="checkbox"
												v-model="item.selected"
												@click.stop
												class="h-5 w-5 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
											/>

											<!-- Item Info -->
											<div class="flex-1 min-w-0 text-start">
												<h4 class="text-sm font-bold text-gray-900 truncate">
													{{ item.item_name }}
												</h4>
												<p class="text-xs text-gray-500 mt-0.5">
													{{ item.item_code }}
												</p>
												<p v-if="item.already_returned > 0" class="text-xs text-amber-600 mt-1">
													{{ __('⚠️ {0} already returned', [item.already_returned]) }}
												</p>
											</div>

											<!-- Quantity Controls -->
											<div class="flex items-center gap-3 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200" @click.stop>
												<span class="text-xs font-medium text-gray-600">{{ __('Return Qty:') }}</span>
												<div class="flex items-center gap-2">
													<button
														@click="decrementReturnQuantity(item)"
														:disabled="!item.selected || item.return_qty <= 1"
														class="w-6 h-6 rounded-full bg-white border border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
													>
														<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
														</svg>
													</button>
													<input
														v-model.number="item.return_qty"
														:max="item.quantity"
														:disabled="!item.selected"
														type="number"
														min="1"
														step="1"
														@change="normalizeItemQuantity(item)"
														@blur="normalizeItemQuantity(item)"
														class="w-14 px-2 py-1 border border-gray-300 rounded-lg text-sm text-center font-semibold focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
													/>
													<button
														@click="incrementReturnQuantity(item)"
														:disabled="!item.selected || item.return_qty >= item.quantity"
														class="w-6 h-6 rounded-full bg-white border border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
													>
														<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
														</svg>
													</button>
												</div>
												<span class="text-xs font-semibold text-gray-700">{{ __('of {0}', [item.quantity], "item qty") }}</span>
											</div>

											<!-- Rate & Amount -->
											<div class="text-start min-w-[100px]">
												<p class="text-sm font-bold text-gray-900">
													{{ formatCurrency(item.rate * item.return_qty) }}
												</p>
												<p class="text-xs text-gray-500 mt-0.5">@ {{ formatCurrency(item.rate) }}/{{ item.uom }}</p>
											</div>
										</div>

										<!-- Mobile Layout -->
										<div class="sm:hidden flex flex-col gap-3">
											<!-- Item Header with Checkbox and Name -->
											<div class="flex items-start gap-3">
												<input
													type="checkbox"
													v-model="item.selected"
													@click.stop
													class="h-5 w-5 mt-1 text-blue-600 rounded-md focus:ring-2 focus:ring-blue-500 cursor-pointer flex-shrink-0"
												/>
												<div class="flex-1 min-w-0 text-start">
													<h4 class="text-sm font-semibold text-gray-900 leading-tight">
														{{ item.item_name }}
													</h4>
													<p class="text-xs text-gray-500 mt-1">
														{{ item.item_code }}
													</p>
													<p v-if="item.already_returned > 0" class="text-xs text-amber-600 mt-1">
														{{ __('⚠️ {0} already returned', [item.already_returned]) }}
													</p>
												</div>
											</div>

											<!-- Quantity Controls -->
											<div class="flex flex-col gap-2" @click.stop>
												<div class="flex items-center justify-between">
													<span class="text-xs font-medium text-gray-600 text-start">{{ __('Return Qty:') }}</span>
													<span class="text-xs text-gray-500 text-end">{{ __('of {0}', [item.quantity], "item qty") }}</span>
												</div>
												<div class="flex items-center gap-2">
													<button
														@click="decrementReturnQuantity(item)"
														:disabled="!item.selected || item.return_qty <= 1"
														class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
													>
														−
													</button>
													<input
														v-model.number="item.return_qty"
														:max="item.quantity"
														:disabled="!item.selected"
														type="number"
														min="1"
														step="1"
														@change="normalizeItemQuantity(item)"
														@blur="normalizeItemQuantity(item)"
														class="w-16 h-10 px-2 border-2 border-gray-300 rounded-lg text-lg text-center font-bold focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
													/>
													<button
														@click="incrementReturnQuantity(item)"
														:disabled="!item.selected || item.return_qty >= item.quantity"
														class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
													>
														+
													</button>
												</div>
											</div>

											<!-- Price -->
											<div class="flex items-center justify-between px-1 pt-2 border-t border-gray-100">
												<span class="text-xs text-gray-600 text-start">{{ __('Amount:') }}</span>
												<div class="text-end">
													<p class="text-base font-bold text-gray-900">
														{{ formatCurrency(item.rate * item.return_qty) }}
													</p>
													<p class="text-xs text-gray-500">@ {{ formatCurrency(item.rate) }}/{{ item.uom }}</p>
												</div>
											</div>
										</div>
									</div>
								</div>
								<p v-if="returnItems.length === 0" class="text-center py-8 text-gray-500">
									{{ __('No items available for return') }}
								</p>
							</div>

							<!-- Payment Methods Selection -->
							<div v-if="selectedItems.length > 0">
								<!-- Credit Sale Return Notice -->
								<div v-if="isOriginalCreditSale" class="bg-amber-50 rounded-xl p-4 border border-amber-200 mb-4 text-start">
									<h4 class="text-sm font-bold text-amber-900 mb-1">{{ __('Credit Sale Return') }}</h4>
									<p class="text-xs text-amber-800">
										{{ __('This invoice was paid on account (credit sale). The return will reverse the accounts receivable balance. No cash refund will be processed.') }}
									</p>
								</div>

								<!-- Partially Paid Invoice Notice -->
								<div v-if="isPartiallyPaid && !isOriginalCreditSale" class="bg-blue-50 rounded-xl p-4 border border-blue-200 mb-4 text-start">
									<h4 class="text-sm font-bold text-blue-900 mb-1">{{ __('Partially Paid Invoice') }}</h4>
									<p class="text-xs text-blue-800 mb-2">
										{{ __('This invoice was partially paid. The refund will be split proportionally.') }}
									</p>
									<div class="flex flex-col gap-1 text-xs">
										<div class="flex justify-between items-center">
											<span class="text-blue-700">{{ __('Cash Refund:') }}</span>
											<span class="font-bold text-blue-900">{{ formatCurrency(maxRefundableAmount) }}</span>
										</div>
										<div v-if="creditAdjustmentAmount > 0" class="flex justify-between items-center">
											<span class="text-blue-700">{{ __('Credit Adjustment:') }}</span>
											<span class="font-bold text-blue-900">{{ formatCurrency(creditAdjustmentAmount) }}</span>
										</div>
									</div>
								</div>

								<!-- Regular Payment Methods (only for non-credit sales) -->
								<div v-if="!isOriginalCreditSale">
								<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2">
									<label class="text-sm font-medium text-gray-700 text-start">
										{{ __('Refund Payment Methods') }}
									</label>
									<Button size="sm" variant="subtle" @click="addPaymentRow" class="self-end sm:self-auto">
										<span class="text-xs">{{ __('+ Add Payment') }}</span>
									</Button>
								</div>

								<div class="flex flex-col gap-3">
									<div
										v-for="(payment, index) in refundPayments"
										:key="index"
										class="bg-white border border-gray-200 rounded-xl p-3 shadow-sm"
									>
										<!-- Desktop: Single Row | Mobile: Two Rows -->
										<div class="flex flex-col sm:flex-row sm:items-center gap-3">
											<!-- Payment Method -->
											<div class="flex items-center gap-2 flex-1">
												<div class="flex-shrink-0 w-10 h-10 rounded-lg bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center text-xl border border-blue-200">
													{{ payment.mode_of_payment ? getPaymentIcon(payment.mode_of_payment) : '💰' }}
												</div>
												<select
													v-model="payment.mode_of_payment"
													:style="paymentSelectStyle"
													class="payment-select flex-1 py-2.5 border border-gray-300 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white appearance-none cursor-pointer hover:border-gray-400 transition-colors ps-3 pe-10"
												>
													<option value="">{{ __('Select method...') }}</option>
													<option v-for="method in paymentMethods" :key="method.mode_of_payment" :value="method.mode_of_payment">
														{{ method.mode_of_payment }}
													</option>
												</select>
											</div>
											<!-- Amount with Counter -->
											<div class="flex items-center gap-2 flex-1">
												<button
													@click="payment.amount = Math.max(0, (payment.amount || 0) - 1)"
													type="button"
													class="flex-shrink-0 w-10 h-10 sm:w-9 sm:h-9 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-xl transition-colors flex items-center justify-center border border-gray-300"
												>−</button>
												<input
													:value="payment.amount"
													@input="payment.amount = parseFloat($event.target.value) || 0"
													@focus="$event.target.select()"
													type="text"
													inputmode="decimal"
													:placeholder="__('Amount')"
													class="flex-1 min-w-0 px-3 py-2.5 text-base font-bold text-center border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 hover:border-gray-400 transition-colors"
												/>
												<button
													@click="payment.amount = (payment.amount || 0) + 1"
													type="button"
													class="flex-shrink-0 w-10 h-10 sm:w-9 sm:h-9 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-xl transition-colors flex items-center justify-center border border-gray-300"
												>+</button>
											</div>
											<!-- Delete Button -->
											<button
												v-if="refundPayments.length > 1"
												@click="removePaymentRow(index)"
												class="hidden sm:flex flex-shrink-0 w-9 h-9 items-center justify-center text-red-500 hover:text-red-700 hover:bg-red-50 active:bg-red-100 rounded-lg transition-colors"
												:title="__('Remove')"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
												</svg>
											</button>
										</div>
										<!-- Mobile Delete Button -->
										<button
											v-if="refundPayments.length > 1"
											@click="removePaymentRow(index)"
											class="sm:hidden mt-2 w-full py-2 text-sm text-red-600 hover:bg-red-50 active:bg-red-100 rounded-lg transition-colors flex items-center justify-center gap-1"
										>
											<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
											</svg>
											{{ __('Remove') }}
										</button>
									</div>
								</div>

								<!-- Payment Summary -->
								<div class="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
									<div class="flex items-center justify-between text-sm">
										<span class="text-gray-600">{{ isPartiallyPaid ? __('Refundable Amount:') : __('Total Refund:') }}</span>
										<span class="font-bold text-gray-900">{{ formatCurrency(isPartiallyPaid ? maxRefundableAmount : returnTotal) }}</span>
									</div>
									<div class="flex items-center justify-between text-sm mt-1">
										<span class="text-gray-600">{{ __('Payment Total:') }}</span>
										<span :class="[
											'font-bold',
											Math.abs(totalPaymentAmount - (isPartiallyPaid ? maxRefundableAmount : returnTotal)) < 0.01 ? 'text-green-600' : 'text-red-600'
										]">
											{{ formatCurrency(totalPaymentAmount) }}
										</span>
									</div>
									<p v-if="Math.abs(totalPaymentAmount - (isPartiallyPaid ? maxRefundableAmount : returnTotal)) >= 0.01" class="mt-2 text-xs text-amber-600 text-start">
										{{ isPartiallyPaid ? __('⚠️ Payment total must equal refundable amount') : __('⚠️ Payment total must equal refund amount') }}
									</p>
								</div>
								</div>
							</div>

							<!-- Return Summary -->
							<div v-if="selectedItems.length > 0" class="bg-gradient-to-br from-red-50 to-orange-50 rounded-xl p-4 sm:p-5 border border-red-200 shadow-sm">
								<div class="flex items-center gap-2 mb-3">
									<svg class="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2zM10 8.5a.5.5 0 11-1 0 .5.5 0 011 0zm5 5a.5.5 0 11-1 0 .5.5 0 011 0z"/>
									</svg>
									<h3 class="text-sm font-bold text-gray-900">{{ __('Return Summary') }}</h3>
								</div>
								<div class="flex flex-col gap-2">
									<div class="flex justify-between items-center">
										<span class="text-sm text-gray-600">{{ __('Items to Return:') }}</span>
										<span class="px-2 py-1 bg-white rounded-lg text-sm font-bold text-gray-900 border border-red-200">{{ selectedItems.length }}</span>
									</div>
									<!-- Breakdown for partially paid invoices -->
									<template v-if="showPartialBreakdown">
										<div class="flex justify-between items-center text-sm pt-2 border-t border-red-200">
											<span class="text-gray-600">{{ __('Return Value:') }}</span>
											<span class="font-medium text-gray-700">{{ formatCurrency(returnTotal) }}</span>
										</div>
										<div class="flex justify-between items-center text-sm">
											<span class="text-gray-600">{{ __('Credit Adjustment:') }}</span>
											<span class="font-medium text-gray-700">-{{ formatCurrency(creditAdjustmentAmount) }}</span>
										</div>
									</template>
									<!-- Final refund amount -->
									<div class="flex justify-between items-center pt-2 border-t border-red-200">
										<span class="text-sm sm:text-base font-semibold text-gray-700">{{ __(summaryRefundLabel) }}</span>
										<span class="text-xl sm:text-2xl font-bold text-red-600">{{ formatCurrency(summaryRefundAmount) }}</span>
									</div>
								</div>
							</div>

							<!-- Return Reason -->
							<div v-if="selectedItems.length > 0">
								<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
									{{ __('Return Reason') }} <span class="text-gray-400">({{ __('optional') }})</span>
								</label>
								<textarea
									v-model="returnReason"
									rows="3"
									:placeholder="__('Enter reason for return (e.g., defective product, wrong item, customer request)...')"
									class="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
								></textarea>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex flex-col w-full gap-2">
				<p v-if="submitError" class="text-xs text-red-600">{{ submitError }}</p>
				<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between w-full gap-2 sm:gap-3">
					<p v-if="selectedItems.length > 0" class="text-xs text-gray-500 flex-shrink-0 order-2 sm:order-1">
						{{ __('{0} item(s) selected', [selectedItems.length]) }}
					</p>
					<div class="flex gap-2 w-full sm:w-auto sm:ms-auto flex-shrink-0 order-1 sm:order-2">
						<Button variant="subtle" @click="closeReturnModal" class="flex-1 sm:flex-initial">
							<span class="text-sm">{{ __('Cancel') }}</span>
						</Button>
						<Button
							variant="solid"
							theme="red"
							@click="handleCreateReturn"
							:disabled="!canCreateReturn || isSubmitting"
							:loading="isSubmitting"
							class="flex-1 sm:flex-initial"
						>
							<span class="text-sm whitespace-nowrap">{{ __('Create Return') }}</span>
						</Button>
					</div>
				</div>
			</div>
		</template>
	</Dialog>

	<!-- Error Dialog -->
	<Dialog
		v-model="errorDialog.visible"
		:options="{ title: errorDialog.title, size: 'sm' }"
	>
		<template #body-content>
			<div class="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
				<svg class="h-5 w-5 flex-shrink-0 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L4.34 16c-.77 1.333.192 3 1.732 3z" />
				</svg>
				<div>
					<p class="text-sm font-semibold text-red-700">{{ errorDialog.title }}</p>
					<p class="mt-1 text-sm text-red-600 whitespace-pre-line">{{ errorDialog.message }}</p>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end w-full">
				<Button variant="solid" theme="red" @click="closeErrorDialog">{{ __('OK') }}</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { getPaymentIcon } from "@/utils/payment"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { getInvoiceStatusColor } from "@/utils/invoice"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue"

const { showSuccess, showError, showWarning } = useToast()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	posOpeningShift: String,
	currency: { type: String, default: "USD" },
})

const emit = defineEmits(["update:modelValue", "return-created"])

// State
const show = ref(props.modelValue)
const originalInvoice = ref(null)
const returnItems = ref([])
const returnReason = ref("")
const paymentMethods = ref([])
const refundPayments = ref([])
const invoiceList = ref([])
const invoiceListFilter = ref("")
const itemSearchFilter = ref("")
const submitError = ref("")
const isSubmitting = ref(false)

// Invoice payment tracking
const isOriginalCreditSale = ref(false)
const isPartiallyPaid = ref(false)
const originalPaidAmount = ref(0)
const originalOutstandingAmount = ref(0)

// UI state
const errorDialog = reactive({ visible: false, title: __("Validation Error"), message: "" })
const returnModal = reactive({ visible: false })

// Resource for loading recent invoices (only those with items available for return)
const loadInvoicesResource = createResource({
	url: "pos_next.api.invoices.get_returnable_invoices",
	makeParams() {
		return {
			limit: 50,
		}
	},
	auto: false,
	onSuccess(data) {
		if (data) {
			invoiceList.value = data
		}
	},
	onError(error) {
		console.error("Error loading invoices:", error)
		showError(__("Failed to load recent invoices"))
	},
})

// Resource for loading payment methods from POS Profile
const loadPaymentMethodsResource = createResource({
	url: "frappe.client.get",
	makeParams() {
		return {
			doctype: "POS Profile",
			name: props.posProfile,
			fields: JSON.stringify(["name", "payments"]),
		}
	},
	auto: false,
	onSuccess(data) {
		if (data && data.payments) {
			paymentMethods.value = data.payments
		}
	},
	onError(error) {
		console.error("Error loading payment methods:", error)
	},
})

// Resource for fetching a specific invoice with return tracking
const fetchInvoiceResource = createResource({
	url: "pos_next.api.invoices.get_invoice_for_return",
	auto: false,
	onSuccess(data) {
		if (data) {
			// Validate that invoice can be returned
			if (data.docstatus !== 1) {
				showWarning(__("Invoice must be submitted to create a return"))
				return
			}
			if (data.is_return === 1) {
				showWarning(__("Cannot create return against a return invoice"))
				return
			}

			// Check if all items have been fully returned
			const availableItems = data.items.filter((item) => item.qty > 0)

			if (availableItems.length === 0) {
				showWarning(__("All items from this invoice have already been returned"))
				originalInvoice.value = null
				returnItems.value = []
				return
			}

			originalInvoice.value = data
			// Map server 'qty' to 'quantity' for internal consistency
			returnItems.value = availableItems.map((item) => ({
				...item,
				quantity: item.qty, // Standardize to 'quantity' from server's 'qty'
				selected: false,
				return_qty: item.qty, // This will be the remaining qty after previous returns
				original_qty: item.original_qty || item.qty, // Track original quantity
			}))
			returnItems.value.forEach(normalizeItemQuantity)

			// Track payment amounts from original invoice
			const totalPaidFromPayments = data.payments?.reduce((sum, p) => sum + Math.abs(p.amount || 0), 0) || 0
			originalPaidAmount.value = data.paid_amount || totalPaidFromPayments || 0
			originalOutstandingAmount.value = data.outstanding_amount || 0

			// Detect if original invoice was a credit sale (Pay on Account)
			// Credit sale indicators:
			// 1. No payments in the payments array, OR
			// 2. Outstanding amount equals grand total (nothing was paid)
			const hasNoPayments = !data.payments || data.payments.length === 0
			const isFullyUnpaid = Math.abs(data.outstanding_amount - data.grand_total) < 0.01
			isOriginalCreditSale.value = hasNoPayments || (totalPaidFromPayments < 0.01 && isFullyUnpaid)

			// Detect if invoice was partially paid (has both paid amount and outstanding)
			isPartiallyPaid.value = originalPaidAmount.value > 0 && originalOutstandingAmount.value > 0

			// Load payment methods if not already loaded
			if (paymentMethods.value.length === 0 && props.posProfile) {
				loadPaymentMethodsResource.reload()
			}

			// Initialize payment methods from invoice
			initializePaymentsFromInvoice()
		}
	},
	onError(error) {
		console.error("Error fetching invoice:", error)
		showError(__("Failed to load invoice details"))
	},
})

// Resource for creating return invoice
const createReturnResource = createResource({
	url: "pos_next.api.invoices.submit_invoice",
	makeParams() {
		// Build invoice data matching the API's expected format
		const invoiceData = {
			doctype: "Sales Invoice",
			pos_profile: props.posProfile,
			posa_pos_opening_shift: props.posOpeningShift,
			customer: originalInvoice.value.customer,
			company: originalInvoice.value.company,
			is_return: 1,
			return_against: originalInvoice.value.name,
			is_pos: 1,
			update_stock: 1,
			items: selectedItems.value.map((item) => ({
				item_code: item.item_code,
				item_name: item.item_name,
				qty: -Math.abs(item.return_qty), // Negative for returns
				rate: item.rate,
				warehouse: item.warehouse,
				uom: item.uom,
				conversion_factor: item.conversion_factor || 1,
				// Link to original invoice item for proper return tracking
				sales_invoice_item: item.name, // Reference to the original Sales Invoice Item
			})),
			payments: refundPayments.value.map(payment => ({
				mode_of_payment: payment.mode_of_payment,
				amount: -Math.abs(payment.amount), // Negative for refunds
			})),
			remarks:
				returnReason.value || __('Return against {0}', [originalInvoice.value.name]),
		}

		// Return in the correct format: invoice as JSON string
		return {
			invoice: JSON.stringify(invoiceData),
			data: JSON.stringify({}),
		}
	},
	auto: false,
	transform(data) {
		// Check if the response contains an error even on "success"
		if (data && data.exc) {
			throw data
		}
		return data
	},
	onSuccess(data) {
		submitError.value = ""
		isSubmitting.value = false
		emit("return-created", data)

		// Reload the invoice list to remove fully returned invoices
		loadInvoicesResource.reload()

		// Close return modal and go back to invoice list
		closeReturnModal()
		showSuccess(__('Return invoice {0} created successfully', [data.name]))
	},
	onError(error) {
		isSubmitting.value = false
		const errorMsg = extractErrorMessage(error)
		submitError.value = errorMsg
		console.error("Error creating return - full error object:", error)
		openErrorDialog(errorMsg)
	},
})

// Lifecycle hooks
onMounted(() => {
	if (props.posProfile) {
		loadPaymentMethodsResource.reload()
	}
	document.addEventListener('keydown', handleKeyboardShortcuts)
})

onUnmounted(() => {
	document.removeEventListener('keydown', handleKeyboardShortcuts)
})

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			// Auto-load invoices when dialog opens
			loadInvoicesResource.reload()
		} else {
			resetForm()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
	if (!val) {
		resetForm()
	}
})

// Computed properties
const selectedItems = computed(() =>
	returnItems.value.filter(item => item.selected && item.return_qty > 0)
)

const filteredReturnItems = computed(() => {
	if (!itemSearchFilter.value) return returnItems.value
	const searchTerm = itemSearchFilter.value.toLowerCase()
	return returnItems.value.filter(item =>
		item.item_name?.toLowerCase().includes(searchTerm) ||
		item.item_code?.toLowerCase().includes(searchTerm)
	)
})

const hasOpenShift = computed(() => Boolean(props.posOpeningShift))

const returnTotal = computed(() =>
	selectedItems.value.reduce((sum, item) => sum + item.return_qty * item.rate, 0)
)

const totalPaymentAmount = computed(() =>
	refundPayments.value.reduce((sum, payment) => sum + (Number(payment.amount) || 0), 0)
)

const maxRefundableAmount = computed(() => {
	if (!originalInvoice.value) return 0
	if (!isPartiallyPaid.value && !isOriginalCreditSale.value) return returnTotal.value

	const grandTotal = Math.abs(originalInvoice.value.grand_total) || 1
	const returnRatio = returnTotal.value / grandTotal
	return Math.min(returnTotal.value, originalPaidAmount.value * returnRatio)
})

const creditAdjustmentAmount = computed(() =>
	isPartiallyPaid.value ? Math.max(0, returnTotal.value - maxRefundableAmount.value) : 0
)

const showPartialBreakdown = computed(() => isPartiallyPaid.value && !isOriginalCreditSale.value)
const summaryRefundLabel = computed(() => showPartialBreakdown.value ? 'Cash Refund:' : 'Refund Amount:')
const summaryRefundAmount = computed(() => showPartialBreakdown.value ? maxRefundableAmount.value : returnTotal.value)

const paymentSelectStyle = computed(() => ({
	backgroundPosition: document.documentElement.dir === 'rtl' ? 'left 12px center' : 'right 12px center'
}))

const canCreateReturn = computed(() => {
	const hasSelectedItems = selectedItems.value.length > 0
	if (!hasSelectedItems || !hasOpenShift.value) return false
	if (isOriginalCreditSale.value) return true

	const payments = refundPayments.value
	if (isPartiallyPaid.value) {
		if (!payments.length) return true
		const hasValidPayments = payments.every(payment => payment.mode_of_payment && payment.amount >= 0)
		return hasValidPayments && Math.abs(totalPaymentAmount.value - maxRefundableAmount.value) < 0.01
	}

	if (!payments.length) return false
	const hasValidPayments = payments.every(payment => payment.mode_of_payment && payment.amount > 0)
	return hasValidPayments && Math.abs(totalPaymentAmount.value - returnTotal.value) < 0.01
})

const filteredInvoiceList = computed(() => {
	if (!invoiceListFilter.value) return invoiceList.value
	const searchTerm = invoiceListFilter.value.toLowerCase()
	return invoiceList.value.filter(invoice =>
		invoice.name.toLowerCase().includes(searchTerm) ||
		invoice.customer_name.toLowerCase().includes(searchTerm)
	)
})

// Auto-populate payment amount when return total changes (single payment only)
watch(returnTotal, (newTotal) => {
	if (!returnModal.visible || !show.value || isOriginalCreditSale.value) return
	if (refundPayments.value.length !== 1 || newTotal <= 0) return

	refundPayments.value[0].amount = isPartiallyPaid.value
		? Number(maxRefundableAmount.value.toFixed(2))
		: newTotal
})

// Methods
function extractErrorMessage(error, fallbackMessage = __("Failed to create return invoice")) {
	if (!error) return fallbackMessage
	if (error.messages?.length) return error.messages.join(", ")

	if (error._server_messages) {
		try {
			const serverMessages = JSON.parse(error._server_messages)
			const firstMessage = serverMessages[0] && JSON.parse(serverMessages[0])
			if (firstMessage?.message) return firstMessage.message
		} catch (parseError) {
			// Ignore JSON parse errors, continue to other extraction methods
		}
	}

	if (typeof error.exc === "string") {
		const validationMatch = error.exc.match(/ValidationError: (.+?)\\n/)
		if (validationMatch) return validationMatch[1]
	}

	if (error.httpStatusText && error.httpStatusText !== "Expectation Failed") return error.httpStatusText
	if (error.message && error.message !== "ValidationError") return error.message
	return fallbackMessage
}

function openErrorDialog(message, title = __("Validation Error")) {
	Object.assign(errorDialog, { visible: true, title, message })
}

function closeErrorDialog() {
	errorDialog.visible = false
}

function normalizeItemQuantity(item) {
	const maxQuantity = Number(item.quantity) || 0
	const currentQuantity = Number(item.return_qty)
	const validQuantity = Number.isFinite(currentQuantity) ? currentQuantity : 1
	item.return_qty = Math.max(1, Math.min(validQuantity, maxQuantity || validQuantity))
}

function validateSelectedItems() {
	const invalidItems = selectedItems.value.filter(item => item.return_qty > item.quantity)
	if (!invalidItems.length) return true

	invalidItems.forEach(normalizeItemQuantity)
	const errorDetails = invalidItems.map(item => __('{0}: maximum {1}', [item.item_name || item.item_code, item.quantity])).join("\n")
	const errorMessage = __('Adjust return quantities before submitting.\n\n{0}', [errorDetails])
	submitError.value = errorMessage
	openErrorDialog(errorMessage)
	return false
}

function addPaymentRow() {
	refundPayments.value.push({ mode_of_payment: "", amount: 0 })
}

function removePaymentRow(paymentIndex) {
	refundPayments.value.splice(paymentIndex, 1)
}

function initializePaymentsFromInvoice() {
	if (isOriginalCreditSale.value) {
		refundPayments.value = []
		return
	}

	const invoicePayments = originalInvoice.value?.payments
	if (invoicePayments?.length) {
		refundPayments.value = invoicePayments.map(payment => ({
			mode_of_payment: payment.mode_of_payment,
			amount: isPartiallyPaid.value ? 0 : Math.abs(payment.amount)
		}))
	} else {
		refundPayments.value = [{
			mode_of_payment: paymentMethods.value[0]?.mode_of_payment || "",
			amount: 0
		}]
	}
}

function openReturnModal(invoice) {
	submitError.value = ""
	fetchInvoiceResource.fetch({ invoice_name: invoice.name })
	returnModal.visible = true
}

function closeReturnModal() {
	returnModal.visible = false
	originalInvoice.value = null
	returnItems.value = []
	returnReason.value = ""
	refundPayments.value = []
	submitError.value = ""
	itemSearchFilter.value = ""
	isOriginalCreditSale.value = false
	isPartiallyPaid.value = false
	originalPaidAmount.value = 0
	originalOutstandingAmount.value = 0
}

function selectAllItems() {
	returnItems.value.forEach(item => {
		item.selected = true
		item.return_qty = item.quantity
	})
}

function selectAllFilteredItems() {
	filteredReturnItems.value.forEach(item => {
		item.selected = true
		item.return_qty = item.quantity
	})
}

function deselectAllItems() {
	returnItems.value.forEach(item => { item.selected = false })
}

function toggleItemSelection(item) {
	item.selected = !item.selected
	if (item.selected && item.return_qty === 0) {
		item.return_qty = item.quantity
	}
}

function handleKeyboardShortcuts(event) {
	if (!returnModal.visible) return

	const isModifierPressed = event.ctrlKey || event.metaKey

	if (isModifierPressed && event.key === 'a') {
		event.preventDefault()
		selectAllItems()
	}
	if (isModifierPressed && event.key === 'Enter' && canCreateReturn.value && !isSubmitting.value) {
		event.preventDefault()
		handleCreateReturn()
	}
	if (event.key === 'Escape') closeReturnModal()
}

function incrementReturnQuantity(item) {
	if (item.return_qty < item.quantity) {
		item.return_qty++
	}
}

function decrementReturnQuantity(item) {
	if (item.return_qty > 1) {
		item.return_qty--
	}
}

async function handleCreateReturn() {
	if (!canCreateReturn.value || isSubmitting.value) return
	if (!hasOpenShift.value) {
		const message = __("Open a shift before creating a return invoice.")
		submitError.value = message
		openErrorDialog(message)
		return
	}

	if (!validateSelectedItems()) {
		return
	}

	submitError.value = ""
	isSubmitting.value = true

	try {
		const result = await createReturnResource.submit()

		// Check if result contains an error (HTTP 417 might return error in response body)
		if (result && result.exc) {
			throw result
		}
	} catch (error) {
		console.error("Caught error in handleCreateReturn:", error)
		if (!submitError.value) {
			const errorMsg = extractErrorMessage(error)
			submitError.value = errorMsg
			openErrorDialog(errorMsg)
		}
	} finally {
		isSubmitting.value = false
	}
}

function resetForm() {
	originalInvoice.value = null
	returnItems.value = []
	returnReason.value = ""
	refundPayments.value = []
	invoiceList.value = []
	invoiceListFilter.value = ""
	submitError.value = ""
	isSubmitting.value = false
	returnModal.visible = false
	errorDialog.visible = false
	errorDialog.message = ""
	isOriginalCreditSale.value = false
	isPartiallyPaid.value = false
	originalPaidAmount.value = 0
	originalOutstandingAmount.value = 0
}

function formatDate(dateStr) {
	if (!dateStr) return ""
	const date = new Date(dateStr)
	return date.toLocaleDateString("en-US", {
		year: "numeric",
		month: "short",
		day: "numeric",
	})
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}
</script>

<style scoped>
/* Custom scrollbar for items list */
.overflow-y-auto::-webkit-scrollbar {
	width: 8px;
}

.overflow-y-auto::-webkit-scrollbar-track {
	background: #f1f1f1;
	border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
	background: #cbd5e1;
	border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
	background: #94a3b8;
}

/* Smooth transitions */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
	opacity: 1;
}

/* Payment select dropdown - arrow icon via background-image, position handled by inline style */
.payment-select {
	background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236B7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
	background-repeat: no-repeat;
	background-size: 20px;
}
</style>
