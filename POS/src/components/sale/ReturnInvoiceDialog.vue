<template>
	<Dialog
		v-model="show"
		:options="{ title: 'Create Return Invoice', size: '3xl' }"
	>
		<template #body-content>
			<div class="space-y-4">
				<!-- Recent Invoices List -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-3">
						Select Invoice to Return
					</label>

					<!-- Search/Filter Input -->
					<div class="mb-3">
									<Input
										v-model="invoiceListFilter"
										type="text"
										placeholder="Search by invoice number or customer name..."
										class="w-full"
									/>
								</div>

								<!-- Loading State -->
								<div v-if="loadInvoicesResource.loading" class="text-center py-8">
									<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
									<p class="mt-2 text-xs text-gray-500">Loading invoices...</p>
								</div>

								<!-- Invoice List -->
								<div v-else class="max-h-96 overflow-y-auto space-y-2 pr-2">
									<div
										v-for="invoice in filteredInvoiceList"
										:key="invoice.name"
										@click="openReturnModal(invoice)"
										class="bg-white border border-gray-200 rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50/30 cursor-pointer transition-all"
									>
										<div class="flex items-center justify-between">
											<div class="flex-1">
												<h4 class="text-sm font-bold text-gray-900">{{ invoice.name }}</h4>
												<p class="text-xs text-gray-600 mt-1">{{ invoice.customer_name }}</p>
												<p class="text-xs text-gray-500">{{ formatDate(invoice.posting_date) }}</p>
											</div>
											<div class="text-right">
												<p class="text-sm font-bold text-gray-900">{{ formatCurrency(invoice.grand_total) }}</p>
												<span class="inline-block px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 mt-1">
													{{ invoice.status }}
												</span>
											</div>
										</div>
									</div>
									<p v-if="!loadInvoicesResource.loading && filteredInvoiceList.length === 0" class="text-center py-8 text-gray-500 text-sm">
										No invoices found
									</p>
								</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="show = false">
				Close
			</Button>
		</template>
	</Dialog>

	<!-- Return Process Modal -->
	<Dialog
		v-model="returnModal.visible"
		:options="{ title: 'Process Return', size: 'full' }"
	>
		<template #body-content>
			<div class="space-y-4">
				<!-- Invoice Details -->
				<div v-if="originalInvoice" class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 sm:p-5 border border-blue-100 shadow-sm">
					<!-- Mobile Layout -->
					<div class="sm:hidden space-y-3">
						<div class="flex items-center justify-between">
							<div class="flex items-center gap-2">
								<svg class="w-5 h-5 text-blue-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
								</svg>
								<h3 class="text-base font-bold text-gray-900 truncate">
									{{ originalInvoice.name }}
								</h3>
							</div>
							<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 flex-shrink-0">
								{{ originalInvoice.status }}
							</span>
						</div>
						<div class="space-y-2">
							<div>
								<p class="text-xs text-gray-500">Customer</p>
								<p class="text-sm font-semibold text-gray-900">{{ originalInvoice.customer_name }}</p>
							</div>
							<div class="flex items-center justify-between">
								<div>
									<p class="text-xs text-gray-500">Date</p>
									<p class="text-sm font-semibold text-gray-900">{{ formatDate(originalInvoice.posting_date) }}</p>
								</div>
								<div class="text-right">
									<p class="text-xs text-gray-500 mb-1">Total</p>
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
							<div class="flex items-center space-x-2">
								<svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
								</svg>
								<h3 class="text-base font-bold text-gray-900">
									{{ originalInvoice.name }}
								</h3>
								<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800">
									{{ originalInvoice.status }}
								</span>
							</div>
							<div class="mt-3 grid grid-cols-2 gap-3">
								<div>
									<p class="text-xs text-gray-500">Customer</p>
									<p class="text-sm font-semibold text-gray-900">{{ originalInvoice.customer_name }}</p>
								</div>
								<div>
									<p class="text-xs text-gray-500">Date</p>
									<p class="text-sm font-semibold text-gray-900">{{ formatDate(originalInvoice.posting_date) }}</p>
								</div>
							</div>
						</div>
						<div class="text-right ml-4">
							<p class="text-xs text-gray-500 mb-1">Total Amount</p>
							<p class="text-2xl font-bold text-gray-900">
								{{ formatCurrency(originalInvoice.grand_total) }}
							</p>
						</div>
					</div>
				</div>

				<!-- Return Items -->
				<div v-if="originalInvoice">
								<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2">
									<label class="text-sm font-medium text-gray-700">
										Select Items to Return
									</label>
									<div class="flex gap-2 self-start sm:self-auto">
										<Button size="sm" variant="subtle" @click="selectAllItems">
											<span class="text-xs whitespace-nowrap">Select All</span>
										</Button>
										<Button size="sm" variant="subtle" @click="deselectAllItems">
											<span class="text-xs whitespace-nowrap">Clear All</span>
										</Button>
									</div>
								</div>
								<div class="space-y-2 max-h-96 overflow-y-auto pr-2">
									<div
										v-for="(item, index) in returnItems"
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
										<div class="hidden sm:flex items-center space-x-4">
											<!-- Checkbox -->
											<input
												type="checkbox"
												v-model="item.selected"
												@click.stop
												class="h-5 w-5 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
											/>

											<!-- Item Info -->
											<div class="flex-1 min-w-0">
												<div class="flex items-start justify-between">
													<div class="flex-1">
														<h4 class="text-sm font-bold text-gray-900 truncate">
															{{ item.item_name }}
														</h4>
														<p class="text-xs text-gray-500 mt-0.5">
															{{ item.item_code }}
														</p>
														<p v-if="item.already_returned > 0" class="text-xs text-amber-600 mt-1">
															⚠️ {{ item.already_returned }} already returned
														</p>
													</div>
												</div>
											</div>

											<!-- Quantity Controls -->
											<div class="flex items-center space-x-3 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200" @click.stop>
												<span class="text-xs font-medium text-gray-600">Return Qty:</span>
												<div class="flex items-center space-x-2">
													<button
														@click="decrementQty(item)"
														:disabled="!item.selected || item.return_qty <= 1"
														class="w-6 h-6 rounded-full bg-white border border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
													>
														<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
														</svg>
													</button>
													<input
														v-model.number="item.return_qty"
														:max="item.qty"
														:disabled="!item.selected"
														type="number"
														min="1"
														step="1"
														@change="normalizeItemQty(item)"
														@blur="normalizeItemQty(item)"
														class="w-14 px-2 py-1 border border-gray-300 rounded-lg text-sm text-center font-semibold focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
													/>
													<button
														@click="incrementQty(item)"
														:disabled="!item.selected || item.return_qty >= item.qty"
														class="w-6 h-6 rounded-full bg-white border border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
													>
														<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
														</svg>
													</button>
												</div>
												<span class="text-xs font-semibold text-gray-700">of {{ item.qty }}</span>
											</div>

											<!-- Rate & Amount -->
											<div class="text-right min-w-[100px]">
												<p class="text-sm font-bold text-gray-900">
													{{ formatCurrency(item.rate * item.return_qty) }}
												</p>
												<p class="text-xs text-gray-500 mt-0.5">@ {{ formatCurrency(item.rate) }}/{{ item.uom }}</p>
											</div>
										</div>

										<!-- Mobile Layout -->
										<div class="sm:hidden space-y-3">
											<!-- Item Header with Checkbox and Name -->
											<div class="flex items-start gap-3">
												<input
													type="checkbox"
													v-model="item.selected"
													@click.stop
													class="h-5 w-5 mt-1 text-blue-600 rounded-md focus:ring-2 focus:ring-blue-500 cursor-pointer flex-shrink-0"
												/>
												<div class="flex-1 min-w-0">
													<h4 class="text-sm font-semibold text-gray-900 leading-tight">
														{{ item.item_name }}
													</h4>
													<p class="text-xs text-gray-500 mt-1">
														{{ item.item_code }}
													</p>
													<p v-if="item.already_returned > 0" class="text-xs text-amber-600 mt-1">
														⚠️ {{ item.already_returned }} already returned
													</p>
												</div>
											</div>

											<!-- Quantity Controls -->
											<div class="space-y-2" @click.stop>
												<div class="flex items-center justify-between">
													<span class="text-xs font-medium text-gray-600">Return Qty:</span>
													<span class="text-xs text-gray-500">of {{ item.qty }}</span>
												</div>
												<div class="flex items-center gap-2">
													<button
														@click="decrementQty(item)"
														:disabled="!item.selected || item.return_qty <= 1"
														class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
													>
														−
													</button>
													<input
														v-model.number="item.return_qty"
														:max="item.qty"
														:disabled="!item.selected"
														type="number"
														min="1"
														step="1"
														@change="normalizeItemQty(item)"
														@blur="normalizeItemQty(item)"
														class="w-16 h-10 px-2 border-2 border-gray-300 rounded-lg text-lg text-center font-bold focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
													/>
													<button
														@click="incrementQty(item)"
														:disabled="!item.selected || item.return_qty >= item.qty"
														class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
													>
														+
													</button>
												</div>
											</div>

											<!-- Price -->
											<div class="flex items-center justify-between px-1 pt-2 border-t border-gray-100">
												<span class="text-xs text-gray-600">Amount:</span>
												<div class="text-right">
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
									No items available for return
								</p>
							</div>

							<!-- Payment Methods Selection -->
							<div v-if="selectedItems.length > 0">
								<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2">
									<label class="text-sm font-medium text-gray-700">
										Refund Payment Methods
									</label>
									<Button size="sm" variant="subtle" @click="addPaymentRow" class="self-start sm:self-auto">
										<span class="text-xs">+ Add Payment</span>
									</Button>
								</div>

								<div class="space-y-2">
									<div
										v-for="(payment, index) in refundPayments"
										:key="index"
										class="bg-white border border-gray-200 rounded-lg p-3"
									>
										<!-- Mobile Layout -->
										<div class="sm:hidden space-y-3">
											<!-- Payment Method Row -->
											<div class="flex items-center gap-3">
												<div class="flex-shrink-0 text-3xl">
													{{ payment.mode_of_payment ? getPaymentIcon(payment.mode_of_payment) : '💰' }}
												</div>
												<select
													v-model="payment.mode_of_payment"
													class="flex-1 px-3 py-3 border-2 border-gray-300 rounded-lg text-base font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
												>
													<option value="">Select method...</option>
													<option v-for="method in paymentMethods" :key="method.mode_of_payment" :value="method.mode_of_payment">
														{{ method.mode_of_payment }}
													</option>
												</select>
												<button
													v-if="refundPayments.length > 1"
													@click="removePaymentRow(index)"
													class="p-2.5 text-red-600 active:bg-red-50 rounded-lg transition-colors flex-shrink-0"
												>
													<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
													</svg>
												</button>
											</div>

											<!-- Amount Input Row -->
											<div class="flex items-center gap-3 pl-1">
												<label class="text-sm font-medium text-gray-600 w-20">Amount:</label>
												<input
													v-model.number="payment.amount"
													type="number"
													step="1"
													min="0"
													:max="returnTotal"
													placeholder="0.00"
													class="flex-1 px-4 py-3 border-2 border-gray-300 rounded-lg text-lg text-right font-bold focus:outline-none focus:ring-2 focus:ring-blue-500"
												/>
											</div>
										</div>

										<!-- Desktop Layout -->
										<div class="hidden sm:flex items-center gap-3">
											<!-- Payment Icon -->
											<div class="flex-shrink-0 text-2xl">
												{{ payment.mode_of_payment ? getPaymentIcon(payment.mode_of_payment) : '💰' }}
											</div>
											<!-- Payment Method Dropdown -->
											<div class="flex-1 min-w-0">
												<select
													v-model="payment.mode_of_payment"
													class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
												>
													<option value="">Select payment method...</option>
													<option v-for="method in paymentMethods" :key="method.mode_of_payment" :value="method.mode_of_payment">
														{{ method.mode_of_payment }}
													</option>
												</select>
											</div>
											<!-- Amount Input -->
											<div class="flex-1 min-w-0">
												<input
													v-model.number="payment.amount"
													type="number"
													step="1"
													min="0"
													:max="returnTotal"
													placeholder="Amount"
													class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
												/>
											</div>
											<button
												v-if="refundPayments.length > 1"
												@click="removePaymentRow(index)"
												class="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors flex-shrink-0"
											>
												<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
												</svg>
											</button>
										</div>
									</div>
								</div>

								<!-- Payment Summary -->
								<div class="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
									<div class="flex items-center justify-between text-sm">
										<span class="text-gray-600">Total Refund:</span>
										<span class="font-bold text-gray-900">{{ formatCurrency(returnTotal) }}</span>
									</div>
									<div class="flex items-center justify-between text-sm mt-1">
										<span class="text-gray-600">Payment Total:</span>
										<span :class="[
											'font-bold',
											totalPaymentAmount === returnTotal ? 'text-green-600' : 'text-red-600'
										]">
											{{ formatCurrency(totalPaymentAmount) }}
										</span>
									</div>
									<p v-if="totalPaymentAmount !== returnTotal" class="mt-2 text-xs text-amber-600">
										⚠️ Payment total must equal refund amount
									</p>
								</div>
							</div>

							<!-- Return Summary -->
							<div v-if="selectedItems.length > 0" class="bg-gradient-to-br from-red-50 to-orange-50 rounded-xl p-4 sm:p-5 border border-red-200 shadow-sm">
								<div class="flex items-center space-x-2 mb-3">
									<svg class="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2zM10 8.5a.5.5 0 11-1 0 .5.5 0 011 0zm5 5a.5.5 0 11-1 0 .5.5 0 011 0z"/>
									</svg>
									<h3 class="text-sm font-bold text-gray-900">Return Summary</h3>
								</div>
								<div class="space-y-3">
									<div class="flex justify-between items-center">
										<span class="text-sm text-gray-600">Items to Return:</span>
										<span class="px-2 py-1 bg-white rounded-lg text-sm font-bold text-gray-900 border border-red-200">
											{{ selectedItems.length }}
										</span>
									</div>
									<div class="flex justify-between items-center pt-2 border-t border-red-200">
										<span class="text-sm sm:text-base font-semibold text-gray-700">Refund Amount:</span>
										<span class="text-xl sm:text-2xl font-bold text-red-600">
											{{ formatCurrency(returnTotal) }}
										</span>
									</div>
								</div>
							</div>

							<!-- Return Reason -->
							<div v-if="selectedItems.length > 0">
								<label class="block text-sm font-medium text-gray-700 mb-2">
									Return Reason <span class="text-gray-400">(optional)</span>
								</label>
								<textarea
									v-model="returnReason"
									rows="3"
									placeholder="Enter reason for return (e.g., defective product, wrong item, customer request)..."
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
						{{ selectedItems.length }} item(s) selected
					</p>
					<div class="flex gap-2 w-full sm:w-auto sm:ml-auto flex-shrink-0 order-1 sm:order-2">
						<Button variant="subtle" @click="closeReturnModal" class="flex-1 sm:flex-initial">
							<span class="text-sm">Cancel</span>
						</Button>
						<Button
							variant="solid"
							theme="red"
							@click="handleCreateReturn"
							:disabled="!canCreateReturn || isSubmitting"
							:loading="isSubmitting"
							class="flex-1 sm:flex-initial"
						>
							<span class="text-sm whitespace-nowrap">Create Return</span>
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
			<div class="flex items-start space-x-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
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
				<Button variant="solid" theme="red" @click="closeErrorDialog">OK</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { useToast } from "@/composables/useToast"
import { getPaymentIcon } from "@/utils/payment"
import { Button, Dialog, Input, createResource } from "frappe-ui"
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue"

const { showSuccess, showError, showWarning } = useToast()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
})

const emit = defineEmits(["update:modelValue", "return-created"])

const show = ref(props.modelValue)
const originalInvoice = ref(null)
const returnItems = ref([])
const returnReason = ref("")
const paymentMethods = ref([])
const refundPayments = ref([])
const invoiceList = ref([])
const invoiceListFilter = ref("")
const submitError = ref("")
const isSubmitting = ref(false)
const errorDialog = reactive({
	visible: false,
	title: "Validation Error",
	message: "",
})
const returnModal = reactive({
	visible: false,
})

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
		showError("Failed to load recent invoices")
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
				showWarning("Invoice must be submitted to create a return")
				return
			}
			if (data.is_return === 1) {
				showWarning("Cannot create return against a return invoice")
				return
			}

			// Check if all items have been fully returned
			const availableItems = data.items.filter((item) => item.qty > 0)

			if (availableItems.length === 0) {
				showWarning("All items from this invoice have already been returned")
				originalInvoice.value = null
				returnItems.value = []
				return
			}

			originalInvoice.value = data
			returnItems.value = availableItems.map((item) => ({
				...item,
				selected: false,
				return_qty: item.qty, // This will be the remaining qty after previous returns
				original_qty: item.original_qty || item.qty, // Track original quantity
			}))
			returnItems.value.forEach(normalizeItemQty)

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
		showError("Failed to load invoice details")
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
				returnReason.value || `Return against ${originalInvoice.value.name}`,
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
		showSuccess(`Return invoice ${data.name} created successfully`)
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
	// Add keyboard shortcut listener
	document.addEventListener('keydown', handleKeyboardShortcuts)
})

onUnmounted(() => {
	// Remove keyboard shortcut listener
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
const selectedItems = computed(() => {
	if (!returnItems.value || !Array.isArray(returnItems.value)) {
		return []
	}
	return returnItems.value.filter(
		(item) => item.selected && item.return_qty > 0,
	)
})

const returnTotal = computed(() => {
	if (!selectedItems.value || !Array.isArray(selectedItems.value)) {
		return 0
	}
	return selectedItems.value.reduce((sum, item) => {
		return sum + item.return_qty * item.rate
	}, 0)
})

const totalPaymentAmount = computed(() => {
	if (!refundPayments.value || !Array.isArray(refundPayments.value)) {
		return 0
	}
	return refundPayments.value.reduce((sum, payment) => {
		return sum + (Number(payment.amount) || 0)
	}, 0)
})

const canCreateReturn = computed(() => {
	if (!selectedItems.value || !refundPayments.value) {
		return false
	}
	const hasSelectedItems = selectedItems.value.length > 0
	const hasValidPayments = refundPayments.value.length > 0 &&
		refundPayments.value.every(p => p.mode_of_payment && p.amount > 0)
	const paymentsMatch = Math.abs(totalPaymentAmount.value - returnTotal.value) < 0.01

	return hasSelectedItems && hasValidPayments && paymentsMatch
})

const filteredInvoiceList = computed(() => {
	if (!invoiceList.value || !Array.isArray(invoiceList.value)) {
		return []
	}
	if (!invoiceListFilter.value) return invoiceList.value

	const filter = invoiceListFilter.value.toLowerCase()
	return invoiceList.value.filter(
		(invoice) =>
			invoice.name.toLowerCase().includes(filter) ||
			invoice.customer_name.toLowerCase().includes(filter),
	)
})

// Watch returnTotal to auto-populate payment amount for single payment method
watch(returnTotal, (newTotal) => {
	// Only run if return modal is visible and component is active
	if (!returnModal.visible || !show.value) {
		return
	}

	// Safety checks: ensure refundPayments exists and has exactly one row
	if (refundPayments.value &&
		Array.isArray(refundPayments.value) &&
		refundPayments.value.length === 1 &&
		refundPayments.value[0] &&
		newTotal > 0) {
		refundPayments.value[0].amount = newTotal
	}
})

// Methods
function extractErrorMessage(
	error,
	fallback = "Failed to create return invoice",
) {
	if (!error) return fallback

	if (
		error.messages &&
		Array.isArray(error.messages) &&
		error.messages.length > 0
	) {
		return error.messages.join(", ")
	}

	if (error._server_messages) {
		try {
			const serverMsgs = JSON.parse(error._server_messages)
			if (Array.isArray(serverMsgs) && serverMsgs.length > 0) {
				const firstMsg = JSON.parse(serverMsgs[0])
				if (firstMsg?.message) {
					return firstMsg.message
				}
			}
		} catch (e) {
			console.error("Failed to parse server messages:", e)
		}
	}

	if (typeof error.exc === "string") {
		const match = error.exc.match(/ValidationError: (.+?)\\n/)
		if (match) {
			return match[1]
		}
	}

	if (error.httpStatusText && error.httpStatusText !== "Expectation Failed") {
		return error.httpStatusText
	}

	if (error.message && error.message !== "ValidationError") {
		return error.message
	}

	return fallback
}

function openErrorDialog(message, title = "Validation Error") {
	errorDialog.title = title
	errorDialog.message = message
	errorDialog.visible = true
}

function closeErrorDialog() {
	errorDialog.visible = false
}

function normalizeItemQty(item) {
	const maxQty = Number(item.qty) || 0
	const minQty = 1
	let qty = Number(item.return_qty)
	if (!Number.isFinite(qty)) {
		qty = minQty
	}
	if (maxQty > 0 && qty > maxQty) {
		qty = maxQty
	}
	if (qty < minQty) {
		qty = minQty
	}
	item.return_qty = qty
}

function validateSelectedItems() {
	const invalidItems = selectedItems.value.filter(
		(item) => item.return_qty > item.qty,
	)
	if (invalidItems.length === 0) {
		return true
	}
	invalidItems.forEach(normalizeItemQty)
	const details = invalidItems
		.map((item) => `${item.item_name || item.item_code}: maximum ${item.qty}`)
		.join("\n")
	const message = `Adjust return quantities before submitting.\n\n${details}`
	submitError.value = message
	openErrorDialog(message)
	return false
}

function addPaymentRow() {
	refundPayments.value.push({
		mode_of_payment: "",
		amount: 0
	})
}

function removePaymentRow(index) {
	refundPayments.value.splice(index, 1)
}

function initializePaymentsFromInvoice() {
	// Initialize refund payments from original invoice payments
	if (originalInvoice.value && originalInvoice.value.payments && originalInvoice.value.payments.length > 0) {
		refundPayments.value = originalInvoice.value.payments.map(payment => ({
			mode_of_payment: payment.mode_of_payment,
			amount: Math.abs(payment.amount) // Use absolute value in case it's already negative
		}))
	} else {
		// Default to one empty row if no payments in invoice
		refundPayments.value = [{
			mode_of_payment: paymentMethods.value.length > 0 ? paymentMethods.value[0].mode_of_payment : "",
			amount: 0
		}]
	}
}

function openReturnModal(invoice) {
	// Fetch the full invoice details with return tracking
	submitError.value = ""
	fetchInvoiceResource.fetch({
		invoice_name: invoice.name,
	})
	returnModal.visible = true
}

function closeReturnModal() {
	returnModal.visible = false
	// Reset return items when closing
	originalInvoice.value = null
	returnItems.value = []
	returnReason.value = ""
	refundPayments.value = []
	submitError.value = ""
}

function selectAllItems() {
	returnItems.value.forEach((item) => {
		item.selected = true
		item.return_qty = item.qty // Set to full quantity
	})
}

function deselectAllItems() {
	returnItems.value.forEach((item) => {
		item.selected = false
	})
}

function toggleItemSelection(item) {
	item.selected = !item.selected
	if (item.selected && item.return_qty === 0) {
		item.return_qty = item.qty // Auto-set to full qty on select
	}
}

function handleKeyboardShortcuts(e) {
	// Only handle shortcuts when return modal is visible
	if (!returnModal.visible) return

	// Ctrl+A or Cmd+A: Select all items
	if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
		e.preventDefault()
		selectAllItems()
	}

	// Ctrl+Enter or Cmd+Enter: Submit if valid
	if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
		e.preventDefault()
		if (canCreateReturn.value && !isSubmitting.value) {
			handleCreateReturn()
		}
	}

	// Escape: Close modal
	if (e.key === 'Escape') {
		closeReturnModal()
	}
}

function incrementQty(item) {
	if (item.return_qty < item.qty) {
		item.return_qty++
	}
}

function decrementQty(item) {
	if (item.return_qty > 1) {
		item.return_qty--
	}
}

async function handleCreateReturn() {
	if (!canCreateReturn.value || isSubmitting.value) return

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
	return new Intl.NumberFormat("en-US", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	}).format(Number.parseFloat(amount || 0))
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
</style>
