<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4">
				<div class="w-full h-full max-w-[95vw] max-h-[95vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-5 border-b bg-gradient-to-r from-indigo-50 to-purple-50">
						<div class="flex items-center gap-3">
							<div class="p-2 bg-indigo-100 rounded-lg">
								<svg class="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">{{ __('Invoice Management') }}</h2>
								<p class="text-sm text-gray-600 flex items-center mt-0.5">
									{{ __('Manage all your invoices in one place') }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button
								@click="refreshCurrentTab"
								:loading="loading"
								variant="ghost"
								size="sm"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
									</svg>
								</template>
								{{ __('Refresh') }}
							</Button>
							<button
								@click="handleClose"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors"
							>
								<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Tabs Navigation -->
					<div class="border-b border-gray-200 bg-gray-50">
						<nav class="flex gap-2 px-6" :aria-label="__('Tabs')">
							<button
								v-for="tab in tabs"
								:key="tab.id"
								@click="activeTab = tab.id"
								:class="[
									'px-4 py-3 text-sm font-semibold transition-all border-b-2 relative',
									activeTab === tab.id
										? getTabActiveClass(tab.id)
										: 'text-gray-600 border-transparent hover:text-gray-800 hover:border-gray-300'
								]"
							>
								<div class="flex items-center gap-2">
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="tab.icon"/>
									</svg>
									<span>{{ tab.label }}</span>
									<span
										v-if="tab.badge && tab.badge() > 0"
										:class="[
											'ms-1 px-2 py-0.5 text-xs font-bold rounded-full',
											activeTab === tab.id ? getBadgeActiveClass(tab.id) : getBadgeInactiveClass(tab.id)
										]"
									>
										{{ tab.badge() }}
									</span>
								</div>
							</button>
						</nav>
					</div>

					<!-- Tab Content -->
					<div class="flex-1 overflow-y-auto bg-gray-50">
						<!-- Loading State -->
						<div v-if="loading && activeTab === 'partial'" class="flex flex-col items-center justify-center py-16">
							<div class="animate-spin rounded-full h-12 w-12 border-b-3 border-indigo-500 mb-4"></div>
							<p class="text-sm font-medium text-gray-600">{{ __('Loading {0}...', [currentTabLabel]) }}</p>
						</div>

						<!-- Tab Content -->
						<div class="p-6">
							<!-- Unpaid Tab -->
							<div v-if="activeTab === 'partial'" class="flex flex-col gap-4">
								<!-- Filter Buttons -->
								<div class="flex items-center gap-2 mb-4 flex-wrap gap-2">
									<button
										@click="unpaidFilter = 'all'"
										:class="[
											'px-4 py-2 rounded-lg font-medium text-sm transition-all',
											unpaidFilter === 'all'
												? 'bg-orange-500 text-white shadow-md'
												: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
										]"
									>
										{{ __('All ({0})', [unpaidInvoices.length]) }}
									</button>
									<button
										@click="unpaidFilter = 'partial'"
										:class="[
											'px-4 py-2 rounded-lg font-medium text-sm transition-all',
											unpaidFilter === 'partial'
												? 'bg-orange-500 text-white shadow-md'
												: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
										]"
									>
										{{ __('Partially Paid ({0})', [unpaidInvoices.filter(inv => inv.status === 'Partly Paid').length]) }}
									</button>
									<button
										@click="unpaidFilter = 'unpaid'"
										:class="[
											'px-4 py-2 rounded-lg font-medium text-sm transition-all',
											unpaidFilter === 'unpaid'
												? 'bg-orange-500 text-white shadow-md'
												: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
										]"
									>
										{{ __('Unpaid ({0})', [unpaidInvoices.filter(inv => inv.status === 'Unpaid').length]) }}
									</button>
									<button
										@click="unpaidFilter = 'overdue'"
										:class="[
											'px-4 py-2 rounded-lg font-medium text-sm transition-all',
											unpaidFilter === 'overdue'
												? 'bg-red-500 text-white shadow-md'
												: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
										]"
									>
										{{ __('Overdue ({0})', [unpaidInvoices.filter(inv => inv.status === 'Overdue').length]) }}
									</button>
								</div>

								<!-- Summary -->
								<div v-if="filteredUnpaidSummary.count > 0" class="bg-gradient-to-r from-orange-50 to-amber-50 border border-orange-200 rounded-lg p-4">
									<div class="flex items-center justify-between">
										<div>
											<div class="text-sm text-orange-600 font-medium">{{ __('Outstanding Payments') }}</div>
											<div class="text-2xl font-bold text-gray-900 mt-1">{{ formatCurrency(filteredUnpaidSummary.total_outstanding) }}</div>
										</div>
										<div class="text-end">
											<div class="text-xs text-gray-600">{{ __('{0} invoices', [filteredUnpaidSummary.count]) }}</div>
											<div class="text-sm text-gray-800 font-semibold mt-1">{{ __('{0} paid', [formatCurrency(filteredUnpaidSummary.total_paid)]) }}</div>
										</div>
									</div>
								</div>

								<!-- Offline Warning -->
								<div v-if="isOffline()" class="bg-yellow-50 border border-yellow-300 rounded-lg p-3 flex items-center gap-3">
									<svg class="w-5 h-5 text-yellow-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
									</svg>
									<div class="flex-1 text-start">
										<p class="text-sm font-medium text-yellow-800">{{ __('You are offline') }}</p>
										<p class="text-xs text-yellow-700">{{ __('Payments cannot be added while offline. Connect to the internet to add payments.') }}</p>
									</div>
								</div>

								<!-- Empty State -->
								<div v-if="filteredUnpaidInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
									</svg>
									<p class="text-gray-600 font-medium">{{ __('No Unpaid Invoices') }}</p>
									<p class="text-gray-500 text-sm mt-1">{{ __('All invoices are fully paid') }}</p>
								</div>

								<!-- Invoices List -->
								<div v-else class="flex flex-col gap-4">
									<div
										v-for="invoice in filteredUnpaidInvoices"
										:key="invoice.name"
										class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
									>
										<!-- Invoice Header -->
										<div class="p-4 border-b bg-gray-50">
											<div class="flex items-start justify-between">
												<div>
													<div class="flex items-center gap-2">
														<h3 class="text-lg font-bold text-gray-900">{{ invoice.name }}</h3>
														<span
															:class="[
																'px-2 py-0.5 text-xs font-semibold rounded-full',
																getInvoiceStatusColor(invoice)
															]"
														>
															{{ __(invoice.status) }}
														</span>
													</div>
													<div class="flex items-center gap-4 mt-1 text-sm text-gray-600">
														<div class="flex items-center">
															<svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
															</svg>
															{{ invoice.customer_name || invoice.customer }}
														</div>
														<div class="flex items-center">
															<svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
															</svg>
															{{ formatDate(invoice.posting_date) }} {{ formatTime(invoice.posting_time) }}
														</div>
													</div>
												</div>
												<button
													@click="selectInvoiceForPayment(invoice)"
													:disabled="loadingInvoiceDetails || isOffline()"
													:title="isOffline() ? __('Payments cannot be added while offline') : ''"
													class="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
												>
													<LoadingIndicator v-if="loadingInvoiceDetails" class="w-4 h-4" />
													{{ __('Add Payment') }}
												</button>
											</div>
										</div>

										<!-- Payment Summary -->
										<div class="p-4">
											<div class="grid grid-cols-3 gap-4 mb-4">
												<div class="text-center p-3 bg-blue-50 rounded-lg border border-blue-100">
													<div class="text-xs text-gray-600 mb-1">{{ __('Total Amount') }}</div>
													<div class="text-lg font-bold text-gray-900">{{ formatCurrency(invoice.grand_total) }}</div>
												</div>
												<div class="text-center p-3 bg-green-50 rounded-lg border border-green-100">
													<div class="text-xs text-gray-600 mb-1">{{ __('Paid') }}</div>
													<div class="text-lg font-bold text-green-600">{{ formatCurrency(invoice.paid_amount) }}</div>
												</div>
												<div class="text-center p-3 bg-orange-50 rounded-lg border border-orange-100">
													<div class="text-xs text-gray-600 mb-1">{{ __('Outstanding') }}</div>
													<div class="text-lg font-bold text-orange-600">{{ formatCurrency(invoice.outstanding_amount) }}</div>
												</div>
											</div>

											<!-- Payment Progress Bar -->
											<div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden mb-3">
												<div
													class="h-full bg-gradient-to-r from-green-500 to-green-600 transition-all duration-300"
													:style="{ width: `${(invoice.paid_amount / invoice.grand_total) * 100}%` }"
												></div>
											</div>

											<!-- Payment Methods -->
											<div v-if="invoice.payments && invoice.payments.length > 0" class="mt-3">
												<div class="text-xs font-medium text-gray-600 mb-2">{{ __('Payment History') }}</div>
												<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
													<div
														v-for="(payment, idx) in invoice.payments"
														:key="idx"
														:class="[
															'flex flex-col p-2 rounded-lg border text-sm',
															payment.source === 'Payment Entry'
																? 'bg-blue-50 border-blue-200'
																: 'bg-gray-50 border-gray-200'
														]"
													>
														<div class="flex items-center justify-between mb-1">
															<span class="text-gray-700 font-medium">{{ payment.mode_of_payment || __('N/A') }}</span>
															<span class="font-semibold text-gray-900">{{ formatCurrency(payment.amount) }}</span>
														</div>
														<div class="flex items-center justify-between">
															<span
																v-if="payment.posting_date"
																class="text-[9px] text-gray-500"
															>
																{{ formatDate(payment.posting_date) }}
															</span>
															<span
																:class="[
																	'text-[9px] font-semibold',
																	payment.source === 'Payment Entry' ? 'text-blue-600' : 'text-gray-500'
																]"
															>
																{{ getPaymentSourceLabel(payment.source) }}
															</span>
														</div>
													</div>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Invoice History Tab -->
							<div v-if="activeTab === 'history'">
								<!-- Filters Component -->
								<div class="mb-6">
									<InvoiceFilters
										:unique-customers="invoiceFilters.uniqueCustomers.value"
										:unique-products="invoiceFilters.uniqueProducts.value"
										:filter-stats="invoiceFilters.filterStats.value"
									/>
								</div>

								<!-- Empty State -->
								<div v-if="filteredHistoryInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
									</svg>
									<p class="text-gray-600 font-medium">{{ __('No invoices found') }}</p>
								</div>

								<!-- Invoices Grid - 2 columns on large screens -->
								<div v-else class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
									<div
										v-for="invoice in filteredHistoryInvoices"
										:key="invoice.name"
										class="bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-lg transition-all overflow-hidden"
									>
										<!-- Card Header with gradient -->
										<div class="bg-gradient-to-r from-indigo-50 to-blue-50 px-5 py-4 border-b border-gray-200">
											<div class="flex items-start justify-between mb-2">
												<div class="flex-1">
													<h3 class="text-base font-bold text-gray-900">{{ invoice.name }}</h3>
													<div class="flex items-center gap-2 mt-1">
														<span
															:class="[
																'text-xs px-2.5 py-1 rounded-full font-semibold',
																getInvoiceStatusColor(invoice)
															]"
														>
															{{ __(invoice.status) }}
														</span>
													</div>
												</div>
												<div class="text-end ms-3">
													<div class="text-xs text-gray-500 mb-1">{{ __('Total') }}</div>
													<div class="text-lg font-bold text-indigo-600">
														{{ formatCurrency(invoice.grand_total) }}
													</div>
												</div>
											</div>
										</div>

										<!-- Card Body -->
										<div class="px-5 py-4 flex flex-col gap-3">
											<!-- Customer Info -->
											<div class="flex items-start">
												<svg class="w-5 h-5 text-gray-400 me-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
												</svg>
												<div class="flex-1">
													<div class="text-xs text-gray-500">{{ __('Customer') }}</div>
													<div class="text-sm font-semibold text-gray-900">{{ invoice.customer_name || invoice.customer }}</div>
												</div>
											</div>

											<!-- Date & Time -->
											<div class="flex items-start">
												<svg class="w-5 h-5 text-gray-400 me-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
												</svg>
												<div class="flex-1">
													<div class="text-xs text-gray-500">{{ __('Date & Time') }}</div>
													<div class="text-sm font-medium text-gray-900">{{ formatDate(invoice.posting_date) }} {{ formatTime(invoice.posting_time) }}</div>
												</div>
											</div>

											<!-- Payment Details -->
											<div class="grid grid-cols-2 gap-3 pt-2 border-t border-gray-100">
												<div>
													<div class="text-xs text-gray-500 mb-1">{{ __('Paid Amount') }}</div>
													<div class="text-sm font-semibold text-green-600">{{ formatCurrency(invoice.paid_amount || 0) }}</div>
												</div>
												<div>
													<div class="text-xs text-gray-500 mb-1">{{ __('Outstanding') }}</div>
													<div class="text-sm font-semibold text-orange-600">{{ formatCurrency(invoice.outstanding_amount || 0) }}</div>
												</div>
											</div>
										</div>

										<!-- Card Footer with Actions -->
										<div class="px-5 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-end gap-2">
											<button
												@click="$emit('view-invoice', invoice)"
												class="px-3 py-2 text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors flex items-center gap-1"
												:title="__('View Details')"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
												</svg>
												<span>{{ __('View') }}</span>
											</button>
											<button
												@click="$emit('print-invoice', invoice)"
												class="px-3 py-2 text-xs font-semibold text-green-600 bg-green-50 hover:bg-green-100 rounded-lg transition-colors flex items-center gap-1"
												:title="__('Print')"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
												</svg>
												<span>{{ __('Print') }}</span>
											</button>
										</div>
									</div>
								</div>
							</div>

							<!-- Draft Invoices Tab -->
							<div v-if="activeTab === 'drafts'">
								<!-- Empty State -->
								<div v-if="draftInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
									</svg>
									<p class="text-gray-600 font-medium">{{ __('No draft invoices') }}</p>
									<p class="text-gray-500 text-sm mt-1">{{ __('Save invoices as drafts to continue later') }}</p>
								</div>

								<!-- Drafts Grid -->
								<div v-else class="grid gap-4">
									<div
										v-for="draft in draftInvoices"
										:key="draft.draft_id"
										class="bg-white border-2 border-gray-200 rounded-lg p-4 hover:border-purple-400 transition-all cursor-pointer"
										@click="$emit('load-draft', draft)"
									>
										<div class="flex items-start justify-between mb-2">
											<div class="flex-1">
												<h4 class="text-sm font-semibold text-gray-900">{{ draft.draft_id }}</h4>
												<p v-if="draft.customer" class="text-xs text-gray-500 mt-0.5">
													{{ __('Customer: {0}', [(draft.customer?.customer_name || draft.customer?.name || draft.customer)]) }}
												</p>
												<p class="text-xs text-gray-400 mt-0.5">{{ formatDateTime(draft.created_at) }}</p>
											</div>
											<button
												@click.stop="$emit('delete-draft', draft.draft_id)"
												class="text-gray-400 hover:text-red-600 transition-colors p-1"
												:title="__('Delete draft')"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
												</svg>
											</button>
										</div>

										<div class="flex items-center justify-between text-xs">
											<span class="text-gray-600">{{ __('{0} item(s)', [draft.items?.length || 0]) }}</span>
											<span class="font-bold text-purple-600">{{ formatCurrency(calculateDraftTotal(draft.items)) }}</span>
										</div>

										<!-- Items Preview -->
										<div v-if="draft.items && draft.items.length > 0" class="mt-2 pt-2 border-t border-gray-100">
											<div class="flex flex-wrap gap-1">
												<span
													v-for="(item, idx) in draft.items.slice(0, 3)"
													:key="idx"
													class="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded"
												>
													{{ item.item_name }} ({{ item.quantity || item.qty }})
												</span>
												<span v-if="draft.items.length > 3" class="text-[10px] text-gray-500 px-1.5 py-0.5">
													{{ __('+{0} more', [draft.items.length - 3]) }}
												</span>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Return Invoices Tab -->
							<div v-if="activeTab === 'returns'">
								<!-- Empty State -->
								<div v-if="returnInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/>
									</svg>
									<p class="text-gray-600 font-medium">{{ __('No return invoices') }}</p>
									<p class="text-gray-500 text-sm mt-1">{{ __('Return invoices will appear here') }}</p>
								</div>

								<!-- Returns Grid -->
								<div v-else class="grid gap-4">
									<div
										v-for="invoice in returnInvoices"
										:key="invoice.name"
										class="bg-white border border-red-200 rounded-lg p-4 hover:shadow-md transition-all"
									>
										<div class="flex items-start justify-between">
											<div class="flex-1">
												<div class="flex items-center gap-2 mb-1">
													<h4 class="text-sm font-semibold text-gray-900">{{ invoice.name }}</h4>
													<span class="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-800">
														{{ __('Return') }}
													</span>
												</div>
												<div class="flex items-center gap-4 text-xs text-gray-600">
													<span>{{ invoice.customer_name }}</span>
													<span>{{ formatDate(invoice.posting_date) }}</span>
													<span v-if="invoice.return_against">{{ __('Against: {0}', [invoice.return_against]) }}</span>
												</div>
											</div>

											<div class="text-end ms-4">
												<p class="text-sm font-bold text-red-600">
													-{{ formatCurrency(Math.abs(invoice.grand_total)) }}
												</p>
												<div class="flex items-center gap-1 mt-2">
													<button
														@click="$emit('view-invoice', invoice)"
														class="p-1.5 hover:bg-blue-50 rounded transition-colors"
														:title="__('View Details')"
													>
														<svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
														</svg>
													</button>
													<button
														@click="$emit('print-invoice', invoice)"
														class="p-1.5 hover:bg-green-50 rounded transition-colors"
														:title="__('Print')"
													>
														<svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
														</svg>
													</button>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>

	<!-- Payment Dialog -->
	<PaymentDialog
		v-model="showPaymentDialog"
		:grand-total="selectedInvoice?.outstanding_amount || 0"
		:subtotal="selectedInvoice?.grand_total || 0"
		:items="selectedInvoice?.items || []"
		:customer="selectedInvoice?.customer_name || selectedInvoice?.customer"
		:pos-profile="posProfile"
		:currency="currency"
		:is-offline="false"
		:allow-partial-payment="true"
		@payment-completed="handlePaymentCompleted"
	/>
</template>

<script setup>
import InvoiceFilters from "@/components/invoices/InvoiceFilters.vue"
import PaymentDialog from "@/components/sale/PaymentDialog.vue"
import { useInvoiceFilters } from "@/composables/useInvoiceFilters"
import { useInvoiceFiltersStore } from "@/stores/invoiceFilters"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { getInvoiceStatusColor } from "@/utils/invoice"
import { useFormatters } from "@/composables/useFormatters"
import { useToast } from "@/composables/useToast"
import { Button, call, LoadingIndicator } from "frappe-ui"
import { computed, onMounted, ref, watch } from "vue"
import { isOffline } from "@/utils/offline/offlineState"
import {
	cacheUnpaidInvoices,
	getCachedUnpaidInvoices,
	cacheUnpaidSummary,
	getCachedUnpaidSummary,
} from "@/utils/offline/sync"
import { logger } from "@/utils/logger"

const log = logger.create("InvoiceManagement")
const { showSuccess, showError } = useToast()
const { formatDate, formatDateTime, formatTime } = useFormatters()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	currency: {
		type: String,
		default: "USD",
	},
	// Pass in data from parent stores
	historyInvoices: {
		type: Array,
		default: () => [],
	},
	draftInvoices: {
		type: Array,
		default: () => [],
	},
})

const emit = defineEmits([
	"update:modelValue",
	"view-invoice",
	"print-invoice",
	"load-draft",
	"delete-draft",
	"refresh-history",
])

const show = ref(props.modelValue)
const loading = ref(false)
const activeTab = ref("partial")

// Initialize filter store and composable
const filterStore = useInvoiceFiltersStore()

// Create a computed ref for history invoices to use with filter composable
const historyInvoicesRef = computed(() => props.historyInvoices)
const invoiceFilters = useInvoiceFilters(historyInvoicesRef)

// Unpaid invoices data
const unpaidInvoices = ref([])
const unpaidFilter = ref("all") // "all", "partial", "unpaid"
const unpaidSummary = ref({
	count: 0,
	total_outstanding: 0,
	total_paid: 0,
})
const selectedInvoice = ref(null)
const showPaymentDialog = ref(false)

// Filtered unpaid invoices based on payment amounts
const filteredUnpaidInvoices = computed(() => {
	if (unpaidFilter.value === "partial") {
		// Partially paid: status is 'Partly Paid' only
		return unpaidInvoices.value.filter((inv) => inv.status === 'Partly Paid')
	}
	if (unpaidFilter.value === "unpaid") {
		// Totally unpaid: status is 'Unpaid'
		return unpaidInvoices.value.filter((inv) => inv.status === 'Unpaid')
	}
	if (unpaidFilter.value === "overdue") {
		// Overdue: invoice status is Overdue
		return unpaidInvoices.value.filter((inv) => inv.status === 'Overdue')
	}
	return unpaidInvoices.value // "all"
})

// Filtered summary based on selected filter
const filteredUnpaidSummary = computed(() => {
	const filtered = filteredUnpaidInvoices.value

	return {
		count: filtered.length,
		total_outstanding: filtered.reduce(
			(sum, inv) => sum + (inv.outstanding_amount || 0),
			0,
		),
		total_paid: filtered.reduce((sum, inv) => sum + (inv.paid_amount || 0), 0),
	}
})

// Return invoices (filtered from history)
const returnInvoices = computed(() => {
	const allInvoices = Array.isArray(props.historyInvoices)
		? props.historyInvoices
		: []
	return allInvoices.filter((inv) => inv.is_return)
})

// Filtered history using the composable (exclude returns, show in separate tab)
const filteredHistoryInvoices = computed(() => {
	// Filter out return invoices, then apply all filters from the store
	const allInvoices = Array.isArray(props.historyInvoices)
		? props.historyInvoices
		: []
	const nonReturnInvoices = allInvoices.filter((inv) => !inv.is_return)

	// Use the filter composable with non-return invoices
	const tempInvoicesRef = computed(() => nonReturnInvoices)
	const tempFilters = useInvoiceFilters(tempInvoicesRef)

	return tempFilters.filteredInvoices.value
})

// Tabs configuration
const tabs = computed(() => [
	{
		id: "partial",
		label: __("Unpaid"),
		icon: "M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z",
		color: "orange",
		activeClass: "text-orange-600",
		badge: () => unpaidInvoices.value.length,
	},
	{
		id: "history",
		label: __("Invoice History"),
		icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
		color: "indigo",
		activeClass: "text-indigo-600",
		badge: () => filteredHistoryInvoices.value.length,
	},
	{
		id: "drafts",
		label: __("Drafts"),
		icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
		color: "purple",
		activeClass: "text-purple-600",
		badge: () => props.draftInvoices.length,
	},
	{
		id: "returns",
		label: __("Returns"),
		icon: "M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6",
		color: "red",
		activeClass: "text-red-600",
		badge: () => returnInvoices.value.length,
	},
])

const currentTabLabel = computed(() => {
	return tabs.value.find((t) => t.id === activeTab.value)?.label || ""
})

// Tab class helpers
function getTabActiveClass(tabId) {
	switch (tabId) {
		case "partial":
			return "text-orange-600 border-orange-500"
		case "history":
			return "text-indigo-600 border-indigo-500"
		case "drafts":
			return "text-purple-600 border-purple-500"
		case "returns":
			return "text-red-600 border-red-500"
		default:
			return "text-gray-600 border-gray-500"
	}
}

// Badge class helpers
function getBadgeActiveClass(tabId) {
	switch (tabId) {
		case "partial":
			return "bg-orange-100 text-orange-700"
		case "history":
			return "bg-indigo-100 text-indigo-700"
		case "drafts":
			return "bg-purple-100 text-purple-700"
		case "returns":
			return "bg-red-100 text-red-700"
		default:
			return "bg-gray-100 text-gray-700"
	}
}

function getBadgeInactiveClass(tabId) {
	switch (tabId) {
		case "partial":
			return "bg-gray-200 text-gray-600"
		case "history":
			return "bg-gray-200 text-gray-600"
		case "drafts":
			return "bg-gray-200 text-gray-600"
		case "returns":
			return "bg-gray-200 text-gray-600"
		default:
			return "bg-gray-200 text-gray-600"
	}
}

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			loadUnpaidInvoices()
			loadUnpaidSummary()
			// Also request history refresh if we don't have data
			if (props.historyInvoices.length === 0) {
				emit("refresh-history")
			}
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Watch for tab changes to emit refresh event for history/returns tabs
watch(activeTab, (newTab) => {
	// Always emit refresh event when switching to history or returns tabs
	// This ensures up-to-date outstanding amounts and invoice data
	if (newTab === "history" || newTab === "returns") {
		emit("refresh-history")
	} else if (newTab === "partial") {
		// Refresh unpaid invoices when switching to partial tab
		loadUnpaidInvoices()
		loadUnpaidSummary()
	}
})

// Methods
function handleClose() {
	show.value = false
}

async function refreshCurrentTab() {
	if (activeTab.value === "partial") {
		await Promise.all([loadUnpaidInvoices(), loadUnpaidSummary()])
	} else if (activeTab.value === "history") {
		// Request parent to refresh history data
		emit("refresh-history")
	} else if (activeTab.value === "drafts") {
		// Drafts are passed from parent, emit event if needed
		emit("refresh-history")
	} else if (activeTab.value === "returns") {
		// Returns would also need a refresh
		emit("refresh-history")
	}
}

async function loadUnpaidInvoices() {
	if (!props.posProfile) return

	// Start loading immediately - show skeleton while fetching
	loading.value = true

	// Load cached data immediately for instant display
	try {
		const cachedInvoices = await getCachedUnpaidInvoices(props.posProfile, {
			limit: 100,
		})
		if (cachedInvoices && cachedInvoices.length > 0) {
			unpaidInvoices.value = cachedInvoices
			loading.value = false // Hide skeleton once we have cached data
			log.debug("Loaded", cachedInvoices.length, "unpaid invoices from cache (instant)")
		}
	} catch (cacheError) {
		log.debug("No cached unpaid invoices available")
	}

	// If offline, we're done - use only cached data
	if (isOffline()) {
		log.info("Offline mode - using cached unpaid invoices")
		loading.value = false
		return
	}

	// Fetch fresh data from server in background
	try {
		const result = await call(
			"pos_next.api.partial_payments.get_unpaid_invoices",
			{
				pos_profile: props.posProfile,
				limit: 100,
			},
		)

		unpaidInvoices.value = result || []

		// Cache for offline use
		if (result && result.length > 0) {
			cacheUnpaidInvoices(result, props.posProfile)
		}
	} catch (error) {
		log.error("Error loading unpaid invoices:", error)

		// If we already have cached data, don't show error
		if (unpaidInvoices.value.length === 0) {
			showError(error.message || __("Failed to load unpaid invoices"))
		}
	} finally {
		loading.value = false
	}
}

async function loadUnpaidSummary() {
	if (!props.posProfile) return

	// Load cached summary immediately for instant display
	try {
		const cachedSummary = await getCachedUnpaidSummary(props.posProfile)
		if (cachedSummary && (cachedSummary.count > 0 || cachedSummary.total_outstanding > 0)) {
			unpaidSummary.value = cachedSummary
			log.debug("Loaded unpaid summary from cache (instant)")
		}
	} catch (cacheError) {
		log.debug("No cached unpaid summary available")
	}

	// If offline, we're done - use only cached data
	if (isOffline()) {
		log.info("Offline mode - using cached unpaid summary")
		return
	}

	// Fetch fresh summary from server in background
	try {
		const result = await call(
			"pos_next.api.partial_payments.get_unpaid_summary",
			{
				pos_profile: props.posProfile,
			},
		)

		unpaidSummary.value = result || {
			count: 0,
			total_outstanding: 0,
			total_paid: 0,
		}

		// Cache for offline use
		if (result) {
			cacheUnpaidSummary(result, props.posProfile)
		}
	} catch (error) {
		log.error("Error loading summary:", error)
		// If we already have cached data, don't show any error - silent fail
	}
}

const loadingInvoiceDetails = ref(false)

async function selectInvoiceForPayment(invoice) {
	loadingInvoiceDetails.value = true
	try {
		// Fetch full invoice details including items for the payment dialog
		const details = await call("pos_next.api.partial_payments.get_partial_payment_details", {
			invoice_name: invoice.name,
		})
		selectedInvoice.value = details
		showPaymentDialog.value = true
	} catch (error) {
		log.error("Error loading invoice details:", error)
		// Fallback to basic invoice data
		selectedInvoice.value = invoice
		showPaymentDialog.value = true
	} finally {
		loadingInvoiceDetails.value = false
	}
}

async function handlePaymentCompleted(paymentData) {
	if (!selectedInvoice.value) return

	try {
		await call("pos_next.api.partial_payments.add_payment_to_partial_invoice", {
			invoice_name: selectedInvoice.value.name,
			payments: paymentData.payments,
		})

		showSuccess(__("Payment added successfully"))

		// Reload invoices and summary for partial tab
		await loadUnpaidInvoices()
		await loadUnpaidSummary()

		// Also refresh history data to show updated outstanding amounts
		emit("refresh-history")

		selectedInvoice.value = null
	} catch (error) {
		console.error("Error adding payment:", error)
		showError(error.message || __("Failed to add payment"))
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function getPaymentSourceLabel(source) {
	// Convert source to user-friendly label
	switch (source) {
		case 'POS':
			return 'POS'
		case 'POS Payment Entry':
			return 'POS'
		case 'Payment Entry':
			return 'Back Office'
		default:
			return source
	}
}


function calculateDraftTotal(items) {
	if (!items || items.length === 0) return 0
	return items.reduce(
		(sum, item) => sum + (item.quantity || item.qty || 0) * (item.rate || 0),
		0,
	)
}

// Lifecycle
onMounted(() => {
	// Load saved filter presets from localStorage
	filterStore.loadSavedFiltersFromStorage()

	if (show.value) {
		loadUnpaidInvoices()
		loadUnpaidSummary()
	}
})
</script>

<style scoped>
/* Fade transition for overlay */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}

/* Slide down transition for filter panel */
.slide-down-enter-active,
.slide-down-leave-active {
	transition: all 0.3s ease-in-out;
	max-height: 600px;
	overflow: hidden;
}

.slide-down-enter-from,
.slide-down-leave-to {
	max-height: 0;
	opacity: 0;
	transform: translateY(-10px);
}

.slide-down-enter-to,
.slide-down-leave-from {
	max-height: 600px;
	opacity: 1;
	transform: translateY(0);
}
</style>
