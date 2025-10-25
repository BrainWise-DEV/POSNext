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
						<div class="flex items-center space-x-3">
							<div class="p-2 bg-indigo-100 rounded-lg">
								<svg class="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">Invoice Management</h2>
								<p class="text-sm text-gray-600 flex items-center mt-0.5">
									Manage all your invoices in one place
								</p>
							</div>
						</div>
						<div class="flex items-center space-x-2">
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
								Refresh
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
						<nav class="flex space-x-2 px-6" aria-label="Tabs">
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
								<div class="flex items-center space-x-2">
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="tab.icon"/>
									</svg>
									<span>{{ tab.label }}</span>
									<span
										v-if="tab.badge && tab.badge() > 0"
										:class="[
											'ml-1 px-2 py-0.5 text-xs font-bold rounded-full',
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
							<p class="text-sm font-medium text-gray-600">Loading {{ currentTabLabel }}...</p>
						</div>

						<!-- Tab Content -->
						<div class="p-6">
							<!-- Partial Payments Tab -->
							<div v-if="activeTab === 'partial'" class="space-y-4">
								<!-- Summary -->
								<div v-if="partialSummary.count > 0" class="bg-gradient-to-r from-orange-50 to-amber-50 border border-orange-200 rounded-lg p-4">
									<div class="flex items-center justify-between">
										<div>
											<div class="text-sm text-orange-600 font-medium">Outstanding Payments</div>
											<div class="text-2xl font-bold text-gray-900 mt-1">{{ formatCurrency(partialSummary.total_outstanding) }}</div>
										</div>
										<div class="text-right">
											<div class="text-xs text-gray-600">{{ partialSummary.count }} invoices</div>
											<div class="text-sm text-gray-800 font-semibold mt-1">{{ formatCurrency(partialSummary.total_paid) }} paid</div>
										</div>
									</div>
								</div>

								<!-- Empty State -->
								<div v-if="partialInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
									</svg>
									<p class="text-gray-600 font-medium">No Partial Payments</p>
									<p class="text-gray-500 text-sm mt-1">All invoices are either fully paid or unpaid</p>
								</div>

								<!-- Invoices List -->
								<div v-else class="space-y-4">
									<div
										v-for="invoice in partialInvoices"
										:key="invoice.name"
										class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
									>
										<!-- Invoice Header -->
										<div class="p-4 border-b bg-gray-50">
											<div class="flex items-start justify-between">
												<div>
													<div class="flex items-center space-x-2">
														<h3 class="text-lg font-bold text-gray-900">{{ invoice.name }}</h3>
														<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-orange-100 text-orange-700">
															Partial
														</span>
													</div>
													<div class="flex items-center space-x-4 mt-1 text-sm text-gray-600">
														<div class="flex items-center">
															<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
															</svg>
															{{ invoice.customer_name || invoice.customer }}
														</div>
														<div class="flex items-center">
															<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
															</svg>
															{{ formatDate(invoice.posting_date) }} {{ invoice.posting_time }}
														</div>
													</div>
												</div>
												<button
													@click="selectInvoiceForPayment(invoice)"
													class="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors text-sm font-semibold"
												>
													Add Payment
												</button>
											</div>
										</div>

										<!-- Payment Summary -->
										<div class="p-4">
											<div class="grid grid-cols-3 gap-4 mb-4">
												<div class="text-center p-3 bg-blue-50 rounded-lg border border-blue-100">
													<div class="text-xs text-gray-600 mb-1">Total Amount</div>
													<div class="text-lg font-bold text-gray-900">{{ formatCurrency(invoice.grand_total) }}</div>
												</div>
												<div class="text-center p-3 bg-green-50 rounded-lg border border-green-100">
													<div class="text-xs text-gray-600 mb-1">Paid</div>
													<div class="text-lg font-bold text-green-600">{{ formatCurrency(invoice.paid_amount) }}</div>
												</div>
												<div class="text-center p-3 bg-orange-50 rounded-lg border border-orange-100">
													<div class="text-xs text-gray-600 mb-1">Outstanding</div>
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
												<div class="text-xs font-medium text-gray-600 mb-2">Previous Payments</div>
												<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
													<div
														v-for="(payment, idx) in invoice.payments"
														:key="idx"
														class="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-gray-200 text-sm"
													>
														<span class="text-gray-700">{{ payment.mode_of_payment }}</span>
														<span class="font-semibold text-gray-900">{{ formatCurrency(payment.amount) }}</span>
													</div>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Invoice History Tab -->
							<div v-if="activeTab === 'history'">
								<!-- Search Bar -->
								<div class="mb-6">
									<Input
										v-model="searchTerm"
										type="text"
										placeholder="Search by invoice number or customer..."
									>
										<template #prefix>
											<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
											</svg>
										</template>
									</Input>
								</div>

								<!-- Empty State -->
								<div v-if="filteredHistoryInvoices.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
									<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
									</svg>
									<p class="text-gray-600 font-medium">No invoices found</p>
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
													<div class="flex items-center space-x-2 mt-1">
														<span
															:class="[
																'text-xs px-2.5 py-1 rounded-full font-semibold',
																invoice.status === 'Paid'
																	? 'bg-green-100 text-green-700 border border-green-200'
																	: invoice.status === 'Partly Paid'
																	? 'bg-orange-100 text-orange-700 border border-orange-200'
																	: invoice.status === 'Unpaid'
																	? 'bg-red-100 text-red-700 border border-red-200'
																	: 'bg-gray-100 text-gray-700 border border-gray-200'
															]"
														>
															{{ invoice.status }}
														</span>
													</div>
												</div>
												<div class="text-right ml-3">
													<div class="text-xs text-gray-500 mb-1">Total</div>
													<div class="text-lg font-bold text-indigo-600">
														{{ formatCurrency(invoice.grand_total) }}
													</div>
												</div>
											</div>
										</div>

										<!-- Card Body -->
										<div class="px-5 py-4 space-y-3">
											<!-- Customer Info -->
											<div class="flex items-start">
												<svg class="w-5 h-5 text-gray-400 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
												</svg>
												<div class="flex-1">
													<div class="text-xs text-gray-500">Customer</div>
													<div class="text-sm font-semibold text-gray-900">{{ invoice.customer_name || invoice.customer }}</div>
												</div>
											</div>

											<!-- Date & Time -->
											<div class="flex items-start">
												<svg class="w-5 h-5 text-gray-400 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
												</svg>
												<div class="flex-1">
													<div class="text-xs text-gray-500">Date & Time</div>
													<div class="text-sm font-medium text-gray-900">{{ formatDate(invoice.posting_date) }} {{ invoice.posting_time }}</div>
												</div>
											</div>

											<!-- Payment Details -->
											<div class="grid grid-cols-2 gap-3 pt-2 border-t border-gray-100">
												<div>
													<div class="text-xs text-gray-500 mb-1">Paid Amount</div>
													<div class="text-sm font-semibold text-green-600">{{ formatCurrency(invoice.paid_amount || 0) }}</div>
												</div>
												<div>
													<div class="text-xs text-gray-500 mb-1">Outstanding</div>
													<div class="text-sm font-semibold text-orange-600">{{ formatCurrency(invoice.outstanding_amount || 0) }}</div>
												</div>
											</div>
										</div>

										<!-- Card Footer with Actions -->
										<div class="px-5 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-end space-x-2">
											<button
												@click="$emit('view-invoice', invoice)"
												class="px-3 py-2 text-xs font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors flex items-center space-x-1"
												title="View Details"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
												</svg>
												<span>View</span>
											</button>
											<button
												@click="$emit('print-invoice', invoice)"
												class="px-3 py-2 text-xs font-semibold text-green-600 bg-green-50 hover:bg-green-100 rounded-lg transition-colors flex items-center space-x-1"
												title="Print"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/>
												</svg>
												<span>Print</span>
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
									<p class="text-gray-600 font-medium">No draft invoices</p>
									<p class="text-gray-500 text-sm mt-1">Save invoices as drafts to continue later</p>
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
													Customer: {{ draft.customer?.customer_name || draft.customer?.name || draft.customer }}
												</p>
												<p class="text-xs text-gray-400 mt-0.5">{{ formatDateTime(draft.created_at) }}</p>
											</div>
											<button
												@click.stop="$emit('delete-draft', draft.draft_id)"
												class="text-gray-400 hover:text-red-600 transition-colors p-1"
												title="Delete draft"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
												</svg>
											</button>
										</div>

										<div class="flex items-center justify-between text-xs">
											<span class="text-gray-600">{{ draft.items?.length || 0 }} item(s)</span>
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
													+{{ draft.items.length - 3 }} more
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
									<p class="text-gray-600 font-medium">No return invoices</p>
									<p class="text-gray-500 text-sm mt-1">Return invoices will appear here</p>
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
												<div class="flex items-center space-x-2 mb-1">
													<h4 class="text-sm font-semibold text-gray-900">{{ invoice.name }}</h4>
													<span class="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-800">
														Return
													</span>
												</div>
												<div class="flex items-center space-x-4 text-xs text-gray-600">
													<span>{{ invoice.customer_name }}</span>
													<span>{{ formatDate(invoice.posting_date) }}</span>
													<span v-if="invoice.return_against">Against: {{ invoice.return_against }}</span>
												</div>
											</div>

											<div class="text-right ml-4">
												<p class="text-sm font-bold text-red-600">
													-{{ formatCurrency(Math.abs(invoice.grand_total)) }}
												</p>
												<div class="flex items-center space-x-1 mt-2">
													<button
														@click="$emit('view-invoice', invoice)"
														class="p-1.5 hover:bg-blue-50 rounded transition-colors"
														title="View Details"
													>
														<svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
														</svg>
													</button>
													<button
														@click="$emit('print-invoice', invoice)"
														class="p-1.5 hover:bg-green-50 rounded transition-colors"
														title="Print"
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
		:pos-profile="posProfile"
		:currency="currency"
		:is-offline="false"
		:allow-partial-payment="true"
		@payment-completed="handlePaymentCompleted"
	/>
</template>

<script setup>
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import PaymentDialog from "@/components/sale/PaymentDialog.vue"
import { Button, call, Input, toast } from "frappe-ui"
import { computed, onMounted, ref, watch } from "vue"

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
const searchTerm = ref("")

// Partial payments data
const partialInvoices = ref([])
const partialSummary = ref({
	count: 0,
	total_outstanding: 0,
	total_paid: 0,
})
const selectedInvoice = ref(null)
const showPaymentDialog = ref(false)

// Return invoices (filtered from history)
const returnInvoices = computed(() => {
	const allInvoices = Array.isArray(props.historyInvoices) ? props.historyInvoices : []
	return allInvoices.filter(inv => inv.is_return)
})

// Filtered history (exclude returns, show in separate tab)
const filteredHistoryInvoices = computed(() => {
	// Ensure we have an array
	const allInvoices = Array.isArray(props.historyInvoices) ? props.historyInvoices : []
	let invoices = allInvoices.filter(inv => !inv.is_return)

	if (searchTerm.value) {
		const search = searchTerm.value.toLowerCase()
		invoices = invoices.filter(inv =>
			inv.name.toLowerCase().includes(search) ||
			(inv.customer_name || "").toLowerCase().includes(search) ||
			(inv.customer || "").toLowerCase().includes(search)
		)
	}

	return invoices
})

// Tabs configuration
const tabs = computed(() => [
	{
		id: "partial",
		label: "Partial Payments",
		icon: "M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z",
		color: "orange",
		activeClass: "text-orange-600",
		badge: () => partialSummary.value.count,
	},
	{
		id: "history",
		label: "Invoice History",
		icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
		color: "indigo",
		activeClass: "text-indigo-600",
		badge: () => filteredHistoryInvoices.value.length,
	},
	{
		id: "drafts",
		label: "Drafts",
		icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
		color: "purple",
		activeClass: "text-purple-600",
		badge: () => props.draftInvoices.length,
	},
	{
		id: "returns",
		label: "Returns",
		icon: "M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6",
		color: "red",
		activeClass: "text-red-600",
		badge: () => returnInvoices.value.length,
	},
])

const currentTabLabel = computed(() => {
	return tabs.value.find(t => t.id === activeTab.value)?.label || ""
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
			loadPartialInvoices()
			loadPartialSummary()
			// Also request history refresh if we don't have data
			if (props.historyInvoices.length === 0) {
				emit('refresh-history')
			}
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Watch for tab changes to emit refresh event for history/returns tabs
watch(activeTab, (newTab) => {
	// Emit refresh event when switching to history or returns tabs if data is empty
	if ((newTab === 'history' || newTab === 'returns') && props.historyInvoices.length === 0) {
		emit('refresh-history')
	}
})

// Methods
function handleClose() {
	show.value = false
}

async function refreshCurrentTab() {
	if (activeTab.value === "partial") {
		await Promise.all([loadPartialInvoices(), loadPartialSummary()])
	}
	// Other tabs use data from parent, so emit refresh event if needed
}

async function loadPartialInvoices() {
	if (!props.posProfile) return

	loading.value = true

	try {
		const result = await call("pos_next.api.partial_payments.get_partial_paid_invoices", {
			pos_profile: props.posProfile,
			limit: 50,
		})

		partialInvoices.value = result || []
	} catch (error) {
		console.error("Error loading partial payments:", error)
		toast.create({
			title: "Error",
			text: error.message || "Failed to load partial payments",
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
	} finally {
		loading.value = false
	}
}

async function loadPartialSummary() {
	if (!props.posProfile) return

	try {
		const result = await call("pos_next.api.partial_payments.get_partial_payment_summary", {
			pos_profile: props.posProfile,
		})

		partialSummary.value = result || { count: 0, total_outstanding: 0, total_paid: 0 }
	} catch (error) {
		console.error("Error loading summary:", error)
	}
}

function selectInvoiceForPayment(invoice) {
	selectedInvoice.value = invoice
	showPaymentDialog.value = true
}

async function handlePaymentCompleted(paymentData) {
	if (!selectedInvoice.value) return

	try {
		await call("pos_next.api.partial_payments.add_payment_to_partial_invoice", {
			invoice_name: selectedInvoice.value.name,
			payments: paymentData.payments,
		})

		toast.create({
			title: "Success",
			text: "Payment added successfully",
			icon: "check",
			iconClasses: "text-green-600",
		})

		// Reload invoices and summary
		await loadPartialInvoices()
		await loadPartialSummary()

		selectedInvoice.value = null
	} catch (error) {
		console.error("Error adding payment:", error)
		toast.create({
			title: "Error",
			text: error.message || "Failed to add payment",
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
	}
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}

function formatDate(date) {
	if (!date) return ""
	const d = new Date(date)
	return d.toLocaleDateString()
}

function formatDateTime(datetime) {
	if (!datetime) return ""
	const d = new Date(datetime)
	return d.toLocaleString()
}

function calculateDraftTotal(items) {
	if (!items || items.length === 0) return 0
	return items.reduce((sum, item) => sum + ((item.quantity || item.qty || 0) * (item.rate || 0)), 0)
}

// Lifecycle
onMounted(() => {
	if (show.value) {
		loadPartialInvoices()
		loadPartialSummary()
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
</style>
