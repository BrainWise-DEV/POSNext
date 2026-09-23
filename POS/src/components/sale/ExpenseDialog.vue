<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="open"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4" @click.self="!isBusy && (open = false)">
				<div
					class="w-full max-w-[95vw] max-h-[95vh] bg-white rounded-lg shadow-2xl flex flex-col overflow-hidden"
				>
					<!-- Header -->
					<div
						class="flex items-center justify-between px-6 py-5 border-b rounded-t-lg bg-gradient-to-r from-amber-50 to-orange-50"
					>
						<div class="flex items-center gap-3">
							<div class="p-2 bg-amber-100 rounded-lg">
								<FeatherIcon name="file-text" class="w-6 h-6 text-amber-600" />
							</div>
							<div class="text-start">
								<h2 class="text-xl font-bold text-gray-900">
									{{ __("Cash Expense") }}
								</h2>
								<p class="text-sm text-gray-600 mt-0.5">
									{{ __("Record money paid from the cash drawer during this shift.") }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button
								variant="ghost"
								size="sm"
								icon-left="refresh-cw"
								:loading="dialogDataResource.loading"
								:disabled="isOffline || isBusy"
								@click="refreshDialog"
							>
								{{ __("Refresh") }}
							</Button>
							<button
								type="button"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors disabled:opacity-50"
								:disabled="isBusy"
								:aria-label="__('Close')"
								@click="open = false"
							>
								<FeatherIcon name="x" class="w-5 h-5 text-gray-600" />
							</button>
						</div>
					</div>

					<!-- Body -->
					<div class="flex-1 min-h-0 overflow-y-auto p-6">
			<div v-if="dialogLoading || (dialogDataResource.loading && !isOffline)" class="text-center py-8">
				<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
				<p class="mt-3 text-xs text-gray-500">{{ __("Loading expense data...") }}</p>
			</div>

			<div v-else class="pos-expense-dialog-fields flex flex-col gap-4">
				<div
					v-if="isOffline"
					class="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3"
				>
					<div class="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
						<FeatherIcon name="wifi-off" class="w-5 h-5 text-amber-600" />
					</div>
					<div class="flex-1 min-w-0 text-start">
						<h4 class="text-sm font-bold text-amber-900">{{ __("Offline Mode") }}</h4>
						<p class="text-xs text-amber-700 mt-1">
							{{
								__(
									"Saved locally; syncs when you reconnect. Cancel of submitted expenses requires online.",
								)
							}}
						</p>
					</div>
				</div>

				<div
					v-if="pendingAttachJournalEntry"
					class="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3"
				>
					<div class="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
						<FeatherIcon name="paperclip" class="w-5 h-5 text-amber-600" />
					</div>
					<div class="flex-1 min-w-0 text-start">
						<h4 class="text-sm font-bold text-amber-900">
							{{
								__("Expense {0} was recorded, but attachments failed.", {
									0: pendingAttachJournalEntry,
								})
							}}
						</h4>
						<p class="text-xs text-amber-700 mt-1">
							{{ __("Retry attach below — do not submit again.") }}
						</p>
						<div class="mt-3 flex flex-wrap gap-2">
							<Button
								size="sm"
								variant="solid"
								theme="blue"
								:disabled="isOffline || !selectedFiles.length || isBusy"
								@click="retryAttach"
							>
								{{ __("Retry Attach") }}
							</Button>
							<Button size="sm" variant="subtle" :disabled="isBusy" @click="discardPendingAttach">
								{{ __("Continue without attachments") }}
							</Button>
						</div>
					</div>
				</div>

				<div class="grid grid-cols-1 lg:grid-cols-5 gap-5 items-stretch">
					<!-- Form card -->
					<div class="lg:col-span-2 flex flex-col min-w-0 bg-white rounded-xl shadow-sm border border-gray-200">
						<div class="flex items-center gap-2 px-5 py-4 border-b bg-gray-50 rounded-t-xl">
							<FeatherIcon name="plus-circle" class="w-5 h-5 text-blue-600" />
							<h3 class="text-base font-bold text-gray-900">{{ __("Add Expense") }}</h3>
						</div>

						<div class="flex flex-col flex-1 gap-4 p-5">
							<div>
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">
									{{ __("Amount") }}
									<span v-if="currency" class="text-gray-500">({{ currency }})</span>
									<span class="text-red-500">*</span>
								</label>
								<input
									v-model="form.amount"
									type="number"
									min="0"
									step="0.01"
									inputmode="decimal"
									class="w-full h-14 px-4 border rounded-lg text-2xl font-bold text-gray-900 placeholder:text-base placeholder:font-normal placeholder:text-gray-400 focus:outline-none focus:ring-2 text-start disabled:bg-gray-100 disabled:cursor-not-allowed"
									:class="
										exceedsRemaining
											? 'border-red-400 focus:ring-red-500'
											: 'border-gray-300 focus:ring-blue-500 focus:border-blue-500'
									"
									:placeholder="amountPlaceholder"
									:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
								/>


								<!-- Shift limit meter: spent + this expense against the limit -->
								<div v-if="maximumExpenseAmount > 0" class="mt-3 text-start">
									<div class="flex h-2 rounded-full bg-gray-100 overflow-hidden">
										<div class="bg-blue-500 transition-all" :style="{ width: `${spentPercent}%` }"></div>
										<div
											class="transition-all"
											:class="exceedsRemaining ? 'bg-red-500' : 'bg-amber-400'"
											:style="{ width: `${enteredPercent}%` }"
										></div>
									</div>
									<p v-if="exceedsRemaining" class="mt-1.5 text-xs font-semibold text-red-600">
										{{
											__("Over limit by {0}", {
												0: formatCurrency(enteredAmount - remainingExpenseAmount),
											})
										}}
									</p>
									<p v-else-if="enteredAmount > 0" class="mt-1.5 text-xs font-semibold text-gray-600">
										{{
											__("{0} left", {
												0: formatCurrency(remainingExpenseAmount - enteredAmount),
											})
										}}
									</p>
								</div>
							</div>

							<div>
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">
									{{ __("Expense Account") }} <span class="text-red-500">*</span>
								</label>
								<AutocompleteSelect
									v-model="form.expense_account"
									:options="expenseAccountOptions"
									:loading="accountSearchLoading"
									:placeholder="__('Search expense account...')"
									:min-search-length="0"
									icon="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
									required
									@search="handleExpenseAccountSearch"
								/>
								<p
									v-if="expenseAccountOptions.length === 0 && !accountSearchLoading"
									class="mt-1.5 text-xs text-amber-700 text-start"
								>
									{{
										isOffline && !hasDialogData
											? __(
													"Open expenses once while online to cache accounts and limits before recording offline.",
												)
											: __("No expense accounts found. Try a different search.")
									}}
								</p>
							</div>

							<div>
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">
									{{ __("Expense Description") }} <span class="text-red-500">*</span>
								</label>
								<input
									v-model="form.remarks"
									type="text"
									class="w-full px-4 py-3 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-start disabled:bg-gray-100 disabled:cursor-not-allowed"
									:placeholder="__('Enter a short description')"
									:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
								/>
							</div>

							<div>
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">
									{{ __("Mode of Payment") }} <span class="text-red-500">*</span>
								</label>
								<AutocompleteSelect
									v-model="form.mode_of_payment"
									:options="paymentMethodOptions"
									:placeholder="__('Search cash payment method...')"
									icon="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
									required
								/>
							</div>

							<div>
								<label class="block text-start text-sm font-medium text-gray-700 mb-2">
									{{ __("Receipt") }}
									<span class="text-gray-400 font-normal">({{ __("optional") }})</span>
								</label>
								<input
									ref="fileInput"
									type="file"
									multiple
									:accept="fileAccept"
									class="hidden"
									:disabled="isBusy"
									@change="onFilesSelected"
								/>
								<button
									type="button"
									class="w-full flex items-center gap-4 rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 px-5 py-5 text-start hover:border-blue-400 hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
									:disabled="isBusy"
									:title="attachmentHelpText"
									@click="fileInput?.click()"
								>
									<div class="p-3 bg-blue-100 rounded-xl shrink-0">
										<FeatherIcon name="upload" class="w-5 h-5 text-blue-600" />
									</div>
									<div class="min-w-0 flex flex-col gap-1">
										<p class="text-sm font-semibold text-gray-900">{{ __("Upload Receipt") }}</p>
										<p class="text-xs text-gray-500 truncate">{{ attachmentUploadHint }}</p>
									</div>
								</button>
								<div v-if="selectedFiles.length" class="mt-2 flex flex-wrap gap-2">
									<span
										v-for="(file, index) in selectedFiles"
										:key="`${file.name}-${index}`"
										class="inline-flex items-center gap-1.5 max-w-full rounded-lg bg-blue-50 border border-blue-100 ps-2.5 pe-1 py-1 text-xs font-medium text-blue-800"
									>
										<FeatherIcon name="file" class="w-3.5 h-3.5 shrink-0" />
										<span class="truncate max-w-[12rem]" :title="file.name">{{ file.name }}</span>
										<button
											type="button"
											class="shrink-0 rounded p-0.5 hover:bg-blue-100 disabled:opacity-50"
											:disabled="isBusy"
											:aria-label="__('Remove')"
											@click="removeSelectedFile(index)"
										>
											<FeatherIcon name="x" class="w-3.5 h-3.5" />
										</button>
									</span>
								</div>
							</div>

							<div
								v-if="validationError"
								class="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700 text-start"
							>
								<FeatherIcon name="alert-circle" class="w-4 h-4 mt-0.5 shrink-0" />
								<span>{{ validationError }}</span>
							</div>

							<div v-if="!pendingAttachJournalEntry" class="mt-auto pt-2">
								<Button
									class="w-full"
									size="lg"
									variant="solid"
									theme="blue"
									icon-left="check"
									:loading="isBusy && !cancellingExpense"
									:disabled="dialogLoading || isBusy || !hasDialogData"
									@click="submitExpense"
								>
									{{ __("Record Expense") }}
								</Button>
							</div>
						</div>
					</div>

					<!-- Expenses card -->
					<div
						class="lg:col-span-3 flex flex-col min-w-0 min-h-[320px] bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden"
					>
						<div class="flex items-center justify-between gap-3 px-5 py-4 border-b bg-gray-50">
							<div class="flex items-center gap-2">
								<FeatherIcon name="list" class="w-5 h-5 text-amber-600" />
								<h3 class="text-base font-bold text-gray-900">{{ __("Expenses This Shift") }}</h3>
								<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-gray-200 text-gray-700">
									{{ pendingExpenses.length + recordedExpenses.length }}
								</span>
							</div>
						</div>

						<!-- Shift summary -->
						<div class="grid grid-cols-3 gap-4 p-5 border-b">
							<div class="text-center p-3 bg-blue-50 rounded-lg border border-blue-100">
								<div class="text-xs text-gray-600 mb-1">{{ __("Shift Limit") }}</div>
								<div class="text-lg font-bold text-gray-900">
									{{ maximumExpenseAmount > 0 ? formatCurrency(maximumExpenseAmount) : "—" }}
								</div>
							</div>
							<div class="text-center p-3 bg-amber-50 rounded-lg border border-amber-100">
								<div class="text-xs text-gray-600 mb-1">{{ __("Already Spent") }}</div>
								<div class="text-lg font-bold text-amber-700">
									{{ formatCurrency(expensesThisShiftTotal) }}
								</div>
							</div>
							<div class="text-center p-3 bg-green-50 rounded-lg border border-green-100">
								<div class="text-xs text-gray-600 mb-1">{{ __("Remaining") }}</div>
								<div class="text-lg font-bold text-green-700">
									{{ maximumExpenseAmount > 0 ? formatCurrency(remainingExpenseAmount) : "—" }}
								</div>
							</div>
							<p v-if="pendingLocalTotal > 0" class="col-span-3 -mt-2 text-xs text-amber-700 text-start">
								{{ __("Includes {0} pending local", { 0: formatCurrency(pendingLocalTotal) }) }}
							</p>
						</div>

						<div class="min-h-0 flex-1 max-h-[50vh] overflow-auto">
							<table class="w-full table-fixed text-start text-sm border-collapse min-w-[520px]">
								<thead class="bg-gray-50 border-b border-gray-100 sticky top-0 z-10">
									<tr class="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
										<th class="px-5 py-3 text-start">{{ __("Expense") }}</th>
										<th class="w-28 px-5 py-3 text-start">{{ __("Cashier") }}</th>
										<th class="w-28 px-5 py-3 text-start">{{ __("Status") }}</th>
										<th class="w-32 px-5 py-3 text-end">{{ __("Amount") }}</th>
										<th class="w-28 px-5 py-3 text-end">{{ __("Actions") }}</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-gray-100 bg-white">
									<tr
										v-for="row in pendingExpenses"
										:key="row.offline_id || row.id"
										class="bg-amber-50/40 hover:bg-amber-50 transition-colors"
									>
										<td class="px-5 py-4">
											<p class="truncate font-semibold text-gray-900" :title="row.data?.expense_account">
												{{ row.data?.expense_account || "—" }}
											</p>
											<p v-if="row.error" class="truncate text-xs text-red-600" :title="row.error">
												{{ row.error }}
											</p>
											<p v-else-if="row.server_journal_entry" class="truncate text-xs text-amber-700">
												{{ __("JE {0}; files pending", { 0: row.server_journal_entry }) }}
											</p>
											<p v-else-if="row.data?.remarks" class="truncate text-xs text-gray-500" :title="row.data.remarks">
												{{ row.data.remarks }}
											</p>
										</td>
										<td class="px-5 py-4 text-gray-500">
											<p class="truncate" :title="pendingCashierLabel(row)">{{ pendingCashierLabel(row) }}</p>
										</td>
										<td class="px-5 py-4">
											<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-800">
												{{ __("Pending") }}
											</span>
										</td>
										<td class="px-5 py-4 text-end whitespace-nowrap font-bold tabular-nums text-gray-900">
											{{ formatCurrency(row.data?.amount) }}
										</td>
										<td class="px-5 py-4 text-end">
											<button
												v-if="!row.server_journal_entry"
												type="button"
												class="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-lg bg-red-600 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-red-700 active:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-red-600"
												:disabled="isBusy || row.synced"
												@click="deletePendingExpense(row)"
											>
												<FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
												{{ __("Delete") }}
											</button>
											<button
												v-else
												type="button"
												class="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-600 shadow-sm transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed"
												:disabled="isBusy"
												:title="__('Discard files')"
												@click="discardPendingAttachments(row)"
											>
												<FeatherIcon name="file-minus" class="w-3.5 h-3.5" />
												{{ __("Discard") }}
											</button>
										</td>
									</tr>

									<tr
										v-for="expense in recordedExpenses"
										:key="expense.journal_entry"
										class="hover:bg-blue-50/50 transition-colors"
										:class="{ 'opacity-50': cancellingExpense === expense.journal_entry }"
									>
										<td class="px-5 py-4">
											<p class="truncate font-semibold text-gray-900" :title="expense.expense_account">
												{{ expense.expense_account || "—" }}
											</p>
											<p v-if="expense.remarks" class="truncate text-xs text-gray-500" :title="expense.remarks">
												{{ expense.remarks }}
											</p>
										</td>
										<td class="px-5 py-4 text-gray-500">
											<p class="truncate" :title="expense.cashier || expense.owner">
												{{ expense.cashier || expense.owner || "—" }}
											</p>
										</td>
										<td class="px-5 py-4">
											<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-700">
												{{ __("Recorded") }}
											</span>
										</td>
										<td class="px-5 py-4 text-end whitespace-nowrap font-bold tabular-nums text-gray-900">
											{{ formatCurrency(expense.amount) }}
										</td>
										<td class="px-5 py-4 text-end">
											<button
												v-if="canCancelExpense"
												type="button"
												class="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-lg bg-red-600 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-red-700 active:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-red-600"
												:disabled="isOffline || isBusy || cancellingExpense === expense.journal_entry"
												:title="isOffline ? __('Voiding requires a connection') : __('Void this expense')"
												@click="cancelExpense(expense)"
											>
												<LoadingIndicator v-if="cancellingExpense === expense.journal_entry" class="w-3.5 h-3.5" />
												<FeatherIcon v-else name="x-circle" class="w-3.5 h-3.5" />
												{{ __("Void") }}
											</button>
										</td>
									</tr>

									<tr v-if="!pendingExpenses.length && !recordedExpenses.length">
										<td colspan="5" class="px-5 py-16 text-center">
											<div class="w-14 h-14 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
												<FeatherIcon name="file-text" class="w-7 h-7 text-gray-400" />
											</div>
											<p class="text-gray-600 font-medium">{{ __("No expenses yet") }}</p>
											<p class="text-gray-500 text-sm mt-1">
												{{ __("Expenses you record this shift will appear here") }}
											</p>
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
					</div>

				</div>
			</div>
		</div>
	</Transition>

	<!-- In-app confirmation (replaces window.confirm) -->
	<Dialog v-model="confirmVisible" :options="{ size: 'xs' }">
		<template #body>
			<div class="p-5">
				<div class="flex items-start gap-3 mb-4">
					<div
						class="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 bg-amber-50 border border-amber-200"
					>
						<svg
							class="w-5 h-5 text-amber-500"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
							/>
						</svg>
					</div>
					<div class="min-w-0">
						<h3 class="text-sm font-semibold text-gray-900">
							{{ confirmTitle }}
						</h3>
						<p class="text-sm text-gray-500 mt-1 leading-relaxed">
							{{ confirmMessage }}
						</p>
					</div>
				</div>
				<div class="flex gap-2.5 justify-end">
					<Button variant="subtle" @click="resolveConfirm(false)">
						{{ __("Cancel") }}
					</Button>
					<Button variant="solid" theme="red" @click="resolveConfirm(true)">
						{{ confirmActionLabel }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import AutocompleteSelect from "@/components/common/AutocompleteSelect.vue"
import { useAuthorization } from "@/composables/useAuthorization"
import { useOfflineStatus } from "@/composables/useOfflineStatus"
import { useToast } from "@/composables/useToast"
import { userData } from "@/data/user"
import { usePOSShiftStore } from "@/stores/posShift"
import { usePOSSyncStore } from "@/stores/posSync"
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { parseError } from "@/utils/errorHandler"
import {
	cacheExpenseDialogData,
	generateOfflineExpenseId,
	getExpenseDialogCache,
} from "@/utils/offline"
import { translationVersion } from "@/utils/translation"
import { Button, Dialog, FeatherIcon, LoadingIndicator, createResource } from "frappe-ui"
import { computed, onUnmounted, reactive, ref, watch } from "vue"

const DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_EXTENSIONS = [
	".jpg",
	".jpeg",
	".png",
	".gif",
	".pdf",
	".txt",
	".csv",
	".doc",
	".docx",
	".xls",
	".xlsx",
	".odt",
	".ods",
]
const fileAccept = ALLOWED_EXTENSIONS.join(",")

const shiftStore = usePOSShiftStore()

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	posOpeningShift: String,
	/**
	 * Company.default_currency for the shift's company.
	 * Must match the JE booking basis — not POS Profile.currency.
	 */
	currency: String,
	maximumExpenseAmount: {
		type: Number,
		default: 0,
	},
})

const emit = defineEmits(["update:modelValue", "expense-created", "expense-cancelled"])

const { showSuccess, showWarning, showError } = useToast()
const { isOffline } = useOfflineStatus()
const offlineStore = usePOSSyncStore()
const { requireAuthorization } = useAuthorization()

const confirmVisible = ref(false)
const confirmTitle = ref("")
const confirmMessage = ref("")
const confirmActionLabel = ref(__("Confirm"))
let confirmResolve = null

function showConfirm({ title, message, actionLabel }) {
	return new Promise((resolve) => {
		confirmTitle.value = title
		confirmMessage.value = message
		confirmActionLabel.value = actionLabel || __("Confirm")
		confirmResolve = resolve
		confirmVisible.value = true
	})
}

function resolveConfirm(result) {
	const resolve = confirmResolve
	confirmResolve = null
	confirmVisible.value = false
	if (resolve) resolve(result)
}

watch(confirmVisible, (visible) => {
	if (!visible && confirmResolve) {
		const resolve = confirmResolve
		confirmResolve = null
		resolve(false)
	}
})

/** Prefer dialog API company_currency; then prop / shiftStore (Company.default_currency); never profile selling currency alone. */
const currency = computed(
	() =>
		dialogPayload.value?.company_currency ||
		props.currency ||
		shiftStore.companyCurrency ||
		DEFAULT_CURRENCY,
)

const amountPlaceholder = computed(() => {
	void translationVersion.value
	return currency.value
		? __("Enter amount in {0}", { 0: currency.value })
		: __("Enter amount")
})

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), currency.value)
}

const form = reactive({
	expense_account: "",
	amount: "",
	mode_of_payment: "",
	remarks: "",
})

const validationError = ref("")
const searchedAccounts = ref(null)
const accountSearchLoading = ref(false)
const cancellingExpense = ref("")
const selectedFiles = ref([])
const isBusy = ref(false)
const pendingAttachJournalEntry = ref("")
const fileInput = ref(null)
const offlineDialogCache = ref(null)
const pendingExpenses = ref([])
const dialogLoading = ref(false)
/** Idempotency key for online submit; reminted only when the form is cleared for a new fill. */
const currentOfflineId = ref(generateOfflineExpenseId())
let accountSearchTimer = null

const open = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const dialogPayload = computed(() => {
	// Prefer IndexedDB cache while offline so a stale/empty resource response
	// from a failed online fetch cannot hide cached accounts.
	if (isOffline.value) {
		return offlineDialogCache.value || dialogDataResource.data || null
	}
	return dialogDataResource.data || offlineDialogCache.value || null
})

const hasDialogData = computed(() => {
	const data = dialogPayload.value
	if (!data) return false
	return Array.isArray(data.expense_accounts) || Array.isArray(data.payment_methods)
})

const cachedExpenseAccounts = computed(() => dialogPayload.value?.expense_accounts || [])

const maximumExpenseAmount = computed(
	() =>
		Number.parseFloat(dialogPayload.value?.maximum_expense_amount) ||
		Number.parseFloat(props.maximumExpenseAmount) ||
		0,
)

const maxFileSize = computed(() => {
	const fromDialog = Number.parseInt(dialogPayload.value?.max_file_size, 10)
	return Number.isFinite(fromDialog) && fromDialog > 0 ? fromDialog : DEFAULT_MAX_FILE_SIZE
})

const attachmentHelpText = computed(() => {
	void translationVersion.value
	const mb = Math.max(1, Math.round(maxFileSize.value / (1024 * 1024)))
	if (isOffline.value) {
		return __(
			"Optional. JPG, PNG, GIF, PDF, TXT, CSV, or Office docs. Max {0} MB each. Files sync after reconnect.",
			{ 0: mb },
		)
	}
	return __(
		"Optional. JPG, PNG, GIF, PDF, TXT, CSV, or Office docs. Max {0} MB each. Attached after submit.",
		{ 0: mb },
	)
})

const attachmentUploadHint = computed(() => {
	void translationVersion.value
	const mb = Math.max(1, Math.round(maxFileSize.value / (1024 * 1024)))
	return __("JPG, PNG or PDF, maximum {0} MB", { 0: mb })
})

const shiftExpenseTotal = computed(
	() => Number.parseFloat(dialogPayload.value?.shift_expense_total) || 0,
)

const pendingLocalTotal = computed(() =>
	pendingExpenses.value.reduce((sum, row) => {
		if (row.data?.pos_opening_shift !== props.posOpeningShift) return sum
		if (row.cache_counted) return sum
		return sum + (Number.parseFloat(row.data?.amount) || 0)
	}, 0),
)

const alreadySpentAmount = computed(
	() => shiftExpenseTotal.value + pendingLocalTotal.value,
)

const remainingExpenseAmount = computed(() => {
	if (maximumExpenseAmount.value <= 0) {
		return 0
	}

	if (isOffline.value || pendingLocalTotal.value > 0) {
		return Math.max(
			0,
			maximumExpenseAmount.value - shiftExpenseTotal.value - pendingLocalTotal.value,
		)
	}

	const remaining = Number.parseFloat(dialogPayload.value?.remaining_expense_amount)
	if (Number.isFinite(remaining)) {
		return Math.max(0, remaining)
	}

	return Math.max(0, maximumExpenseAmount.value - shiftExpenseTotal.value)
})

const enteredAmount = computed(() =>
	Math.max(0, Number.parseFloat(form.amount) || 0),
)

const exceedsRemaining = computed(
	() =>
		maximumExpenseAmount.value > 0 &&
		enteredAmount.value > remainingExpenseAmount.value,
)

// Limit meter widths (%): spent so far, then the amount being entered
const spentPercent = computed(() =>
	Math.min(100, (1 - remainingExpenseAmount.value / maximumExpenseAmount.value) * 100 || 0),
)

const enteredPercent = computed(() =>
	Math.min(
		100 - spentPercent.value,
		(enteredAmount.value / maximumExpenseAmount.value) * 100 || 0,
	),
)

function refreshDialog() {
	dialogDataResource.reload()
	refreshPendingExpenses()
}

const canCancelExpense = computed(
	() =>
		Number(dialogPayload.value?.allow_cancel || 0) === 1 &&
		Number(dialogPayload.value?.can_cancel || 0) === 1,
)

const dialogDataResource = createResource({
	url: "pos_next.api.expenses.get_expense_dialog_data",
	makeParams() {
		return {
			pos_profile: props.posProfile,
			pos_opening_shift: props.posOpeningShift,
		}
	},
	auto: false,
	onError(error) {
		validationError.value =
			error?.messages?.[0] || error?.message || __("Unable to load expense data")
	},
})

const accountSearchQuery = ref("")

const accountSearchResource = createResource({
	url: "pos_next.api.expenses.search_expense_accounts",
	makeParams() {
		return {
			pos_profile: props.posProfile,
			pos_opening_shift: props.posOpeningShift,
			txt: accountSearchQuery.value || "",
		}
	},
	auto: false,
	onSuccess(data) {
		searchedAccounts.value = data || []
		accountSearchLoading.value = false
	},
	onError() {
		accountSearchLoading.value = false
	},
})

const submitResource = createResource({
	url: "pos_next.api.expenses.create_pos_expense",
	makeParams() {
		return {
			pos_opening_shift: props.posOpeningShift,
			pos_profile: props.posProfile,
			expense_account: form.expense_account,
			amount: Number.parseFloat(form.amount),
			mode_of_payment: form.mode_of_payment,
			employee: null,
			remarks: (form.remarks || "").trim() || null,
			offline_id: currentOfflineId.value,
		}
	},
	auto: false,
	async onSuccess(data) {
		const journalEntry = data?.journal_entry || data?.name
		const filesToAttach = [...selectedFiles.value]

		// Cash already moved — clear money fields immediately so Submit cannot double-post.
		clearExpenseFields()
		emit("expense-created", data)
		searchedAccounts.value = null

		try {
			if (journalEntry && filesToAttach.length) {
				try {
					await uploadExpenseAttachments(journalEntry, filesToAttach)
					showSuccess(data?.message || __("POS Expense recorded successfully"))
					clearSelectedFiles()
					pendingAttachJournalEntry.value = ""
					validationError.value = ""
				} catch (error) {
					const parsed = parseError(normalizeSubmitError(error))
					pendingAttachJournalEntry.value = journalEntry
					selectedFiles.value = error?.remainingFiles || filesToAttach
					validationError.value = parsed.message
					showWarning(
						__(
							"Expense {0} recorded, but attachments failed. Retry attach below.",
							{ 0: journalEntry },
						),
					)
				}
			} else {
				showSuccess(data?.message || __("POS Expense recorded successfully"))
				clearSelectedFiles()
				pendingAttachJournalEntry.value = ""
				validationError.value = ""
			}

			await dialogDataResource.reload()
			if (dialogDataResource.data) {
				await cacheExpenseDialogData(
					props.posProfile,
					props.posOpeningShift,
					JSON.parse(JSON.stringify(dialogDataResource.data)),
				)
			}
			await refreshPendingExpenses()
		} finally {
			isBusy.value = false
		}
	},
	onError(error) {
		isBusy.value = false
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	},
})

const cancelResource = createResource({
	url: "pos_next.api.expenses.cancel_pos_expense",
	auto: false,
	async onSuccess(data) {
		showSuccess(data?.message || __("POS Expense cancelled"))
		emit("expense-cancelled", data)
		const cancelled = data?.journal_entry || data?.name
		if (cancelled && cancelled === pendingAttachJournalEntry.value) {
			pendingAttachJournalEntry.value = ""
			clearSelectedFiles()
			validationError.value = ""
		}
		cancellingExpense.value = ""
		isBusy.value = false
		await dialogDataResource.reload()
		if (dialogDataResource.data) {
			await cacheExpenseDialogData(
				props.posProfile,
				props.posOpeningShift,
				JSON.parse(JSON.stringify(dialogDataResource.data)),
			)
		}
	},
	onError(error) {
		cancellingExpense.value = ""
		isBusy.value = false
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	},
})

function normalizeSubmitError(error) {
	if (error instanceof Error) {
		return {
			message: error.message,
			...(error.cause && typeof error.cause === "object" ? error.cause : {}),
		}
	}

	return error || {}
}

function extractAttachErrorMessage(responseData, fileName) {
	const serverMessages = responseData?._server_messages
	if (serverMessages) {
		try {
			const parsed = JSON.parse(serverMessages)
			const first = parsed?.[0]
			const messageObj = typeof first === "string" ? JSON.parse(first) : first
			if (messageObj?.message) {
				return messageObj.message
			}
		} catch {
			/* fall through to generic message */
		}
	}

	if (typeof responseData?.message === "string" && responseData.message) {
		return responseData.message
	}

	return __("Expense recorded, but attaching {0} failed", { 0: fileName })
}

const expenseAccountOptions = computed(() => {
	const accounts =
		searchedAccounts.value !== null
			? searchedAccounts.value
			: cachedExpenseAccounts.value

	return accounts.map((account) => ({
		label: account.account_name || account.name,
		subtitle: account.account_name ? account.name : "",
		value: account.name,
	}))
})

const paymentMethodOptions = computed(() =>
	(dialogPayload.value?.payment_methods || []).map((method) => ({
		label: method.mode_of_payment,
		value: method.mode_of_payment,
	})),
)

const currentCashierName = computed(() => userData.getDisplayName() || "—")

function pendingCashierLabel(row) {
	return row?.data?.cashier || currentCashierName.value || "—"
}

const recordedExpenses = computed(() => dialogPayload.value?.expenses || [])

const expensesThisShiftTotal = computed(() => {
	const recorded = recordedExpenses.value.reduce(
		(sum, expense) => sum + (Number.parseFloat(expense.amount) || 0),
		0,
	)
	return recorded + pendingLocalTotal.value
})

async function refreshPendingExpenses() {
	try {
		// Show all unsynced rows (any shift) so stranded expenses remain deletable.
		pendingExpenses.value = (await offlineStore.loadPendingExpenses()) || []
	} catch {
		pendingExpenses.value = []
	}
}

async function deletePendingExpense(row) {
	if (isBusy.value || !row?.id) return
	if (row.server_journal_entry) {
		validationError.value = __(
			"Journal Entry already created on the server. Discard remaining attachments instead of deleting.",
		)
		return
	}
	const confirmed = await showConfirm({
		title: __("Delete Offline Expense"),
		message: __(
			"Delete this unsynced offline expense? It will not be sent to the server.",
		),
		actionLabel: __("Delete"),
	})
	if (!confirmed) {
		return
	}
	isBusy.value = true
	try {
		await offlineStore.deleteOfflineExpense(row.id)
		await refreshPendingExpenses()
	} catch (error) {
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	} finally {
		isBusy.value = false
	}
}

async function discardPendingAttachments(row) {
	if (isBusy.value || !row?.id || !row.server_journal_entry) return
	const confirmed = await showConfirm({
		title: __("Discard Attachments"),
		message: __(
			"Keep Journal Entry {0} and discard remaining queued attachments?",
			{ 0: row.server_journal_entry },
		),
		actionLabel: __("Discard files"),
	})
	if (!confirmed) {
		return
	}
	isBusy.value = true
	try {
		await offlineStore.discardOfflineExpenseAttachments(row.id)
		await refreshPendingExpenses()
	} catch (error) {
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	} finally {
		isBusy.value = false
	}
}

watch(open, async (isOpen) => {
	if (!isOpen) {
		validationError.value = ""
		searchedAccounts.value = null
		// Keep pendingAttachJournalEntry + selectedFiles so Retry Attach survives reopen.
		return
	}

	if (!props.posProfile || !props.posOpeningShift) {
		validationError.value = __("An active POS shift is required")
		return
	}

	const keepPending = pendingAttachJournalEntry.value
	const keepFiles = keepPending ? [...selectedFiles.value] : []
	const keepError = keepPending ? validationError.value : ""

	clearExpenseFields()
	if (!keepPending) {
		clearSelectedFiles()
		pendingAttachJournalEntry.value = ""
		validationError.value = ""
	} else {
		selectedFiles.value = keepFiles
		validationError.value = keepError
	}
	isBusy.value = false
	cancellingExpense.value = ""
	searchedAccounts.value = null
	dialogLoading.value = true

	try {
		if (isOffline.value) {
			const cached = await getExpenseDialogCache(props.posProfile, props.posOpeningShift)
			offlineDialogCache.value = cached
			// Always prefer cached list over any stale in-memory search result.
			searchedAccounts.value = null
			if (!cached?.expense_accounts?.length) {
				validationError.value = __(
					"Open expenses once while online to cache accounts and limits before recording offline.",
				)
			}
		} else {
			offlineDialogCache.value = null
			await dialogDataResource.submit()
			if (dialogDataResource.data) {
				const plain = JSON.parse(JSON.stringify(dialogDataResource.data))
				const ok = await cacheExpenseDialogData(
					props.posProfile,
					props.posOpeningShift,
					plain,
				)
				offlineDialogCache.value = plain
				if (!ok) {
					showWarning(
						__("Could not save expense data for offline use. Reconnect and reopen expenses."),
					)
				}
			}
			searchedAccounts.value = null

			if (pendingAttachJournalEntry.value) {
				const stillOpen = (dialogDataResource.data?.expenses || []).some(
					(expense) => expense.journal_entry === pendingAttachJournalEntry.value,
				)
				if (!stillOpen) {
					pendingAttachJournalEntry.value = ""
					clearSelectedFiles()
					validationError.value = ""
				}
			}
		}

		await refreshPendingExpenses()
	} finally {
		dialogLoading.value = false
	}
})

function clearExpenseFields() {
	form.expense_account = ""
	form.amount = ""
	form.mode_of_payment = ""
	form.remarks = ""
	// New form fill → new idempotency key (do not remint on submit error/retry).
	currentOfflineId.value = generateOfflineExpenseId()
}

function clearSelectedFiles() {
	selectedFiles.value = []
	if (fileInput.value) {
		fileInput.value.value = ""
	}
}

function resetForm() {
	clearExpenseFields()
	clearSelectedFiles()
	pendingAttachJournalEntry.value = ""
	validationError.value = ""
	isBusy.value = false
	cancellingExpense.value = ""
}

function discardPendingAttach() {
	pendingAttachJournalEntry.value = ""
	clearSelectedFiles()
	validationError.value = ""
}

function getFileExtension(filename) {
	const name = (filename || "").toLowerCase()
	const idx = name.lastIndexOf(".")
	return idx >= 0 ? name.slice(idx) : ""
}

function validateSelectedFile(file) {
	const ext = getFileExtension(file.name)
	if (!ALLOWED_EXTENSIONS.includes(ext)) {
		return __("File type not allowed: {0}", { 0: file.name })
	}
	if (file.size > maxFileSize.value) {
		const mb = Math.max(1, Math.round(maxFileSize.value / (1024 * 1024)))
		return __("File {0} exceeds the maximum size of {1} MB", {
			0: file.name,
			1: mb,
		})
	}
	return ""
}

function onFilesSelected(event) {
	const files = Array.from(event.target.files || [])
	if (!files.length) {
		return
	}

	const accepted = []
	for (const file of files) {
		const error = validateSelectedFile(file)
		if (error) {
			validationError.value = error
			showError(error)
			if (fileInput.value) {
				fileInput.value.value = ""
			}
			return
		}
		accepted.push(file)
	}

	selectedFiles.value = [...selectedFiles.value, ...accepted]
	validationError.value = ""
	if (fileInput.value) {
		fileInput.value.value = ""
	}
}

function removeSelectedFile(index) {
	selectedFiles.value = selectedFiles.value.filter((_, i) => i !== index)
}

async function uploadExpenseAttachments(journalEntry, files) {
	for (let index = 0; index < files.length; index++) {
		const file = files[index]
		const formData = new FormData()
		formData.append("file", file, file.name)
		formData.append("journal_entry", journalEntry)
		formData.append("pos_opening_shift", props.posOpeningShift)
		formData.append("pos_profile", props.posProfile)

		const response = await fetch(
			"/api/method/pos_next.api.expenses.attach_pos_expense_file",
			{
				method: "POST",
				headers: {
					"X-Frappe-CSRF-Token": window.csrf_token,
				},
				body: formData,
			},
		)
		const responseData = await response.json().catch(() => ({}))

		if (!response.ok || responseData.exc) {
			const error = new Error(extractAttachErrorMessage(responseData, file.name))
			error.remainingFiles = files.slice(index)
			throw error
		}

		if (!responseData.message?.file_url && !responseData.message?.name) {
			const error = new Error(
				__("Expense recorded, but file upload did not return a file"),
			)
			error.remainingFiles = files.slice(index)
			throw error
		}
	}
}

async function retryAttach() {
	if (isOffline.value) {
		validationError.value = __(
			"POS expenses cannot be recorded while offline. Please connect to the internet and try again.",
		)
		return
	}

	if (!pendingAttachJournalEntry.value || !selectedFiles.value.length || isBusy.value) {
		return
	}

	const fileError = selectedFiles.value.map(validateSelectedFile).find(Boolean)
	if (fileError) {
		validationError.value = fileError
		return
	}

	isBusy.value = true
	validationError.value = ""
	try {
		await uploadExpenseAttachments(pendingAttachJournalEntry.value, [...selectedFiles.value])
		showSuccess(
			__("Attachments added to expense {0}", { 0: pendingAttachJournalEntry.value }),
		)
		pendingAttachJournalEntry.value = ""
		clearSelectedFiles()
		validationError.value = ""
		await dialogDataResource.reload()
	} catch (error) {
		const parsed = parseError(normalizeSubmitError(error))
		if (error?.remainingFiles) {
			selectedFiles.value = error.remainingFiles
		}
		validationError.value = parsed.message
		showError(parsed.message)
	} finally {
		isBusy.value = false
	}
}

function handleExpenseAccountSearch(query) {
	if (accountSearchTimer) {
		clearTimeout(accountSearchTimer)
	}

	accountSearchTimer = setTimeout(async () => {
		if (!props.posProfile || !props.posOpeningShift) {
			return
		}

		accountSearchQuery.value = query || ""

		if (isOffline.value) {
			const accounts = cachedExpenseAccounts.value
			if (!accounts.length) {
				// Cache still loading or missing — don't lock options to [].
				searchedAccounts.value = null
				accountSearchLoading.value = false
				return
			}
			const q = (query || "").toLowerCase().trim()
			searchedAccounts.value = q
				? accounts.filter(
						(a) =>
							(a.name || "").toLowerCase().includes(q) ||
							(a.account_name || "").toLowerCase().includes(q),
					)
				: null
			accountSearchLoading.value = false
			return
		}

		accountSearchLoading.value = true
		try {
			await accountSearchResource.submit()
		} catch {
			accountSearchLoading.value = false
		}
	}, 250)
}

onUnmounted(() => clearTimeout(accountSearchTimer))

function validateForm() {
	if (!form.expense_account) {
		return __("Expense Account is required")
	}

	const amount = Number.parseFloat(form.amount)
	if (!Number.isFinite(amount) || amount <= 0) {
		return __("Amount must be greater than zero")
	}

	if (maximumExpenseAmount.value <= 0) {
		return __(
			"Maximum Expense Amount is not configured on this POS Profile. Set a positive limit before recording expenses.",
		)
	}

	if (amount > remainingExpenseAmount.value) {
		return __("Amount exceeds the remaining shift expense allowance of {0}", {
			0: formatCurrency(remainingExpenseAmount.value),
		})
	}

	if (!form.mode_of_payment) {
		return __("Mode of Payment is required")
	}

	if (!(form.remarks || "").trim()) {
		return __("Remarks are required")
	}

	for (const file of selectedFiles.value) {
		const fileError = validateSelectedFile(file)
		if (fileError) {
			return fileError
		}
	}

	return ""
}

async function submitExpense() {
	if (isBusy.value) {
		return
	}

	if (pendingAttachJournalEntry.value) {
		validationError.value = __(
			"Attachments are still pending for {0}. Use Retry Attach instead of Submit.",
			{ 0: pendingAttachJournalEntry.value },
		)
		return
	}

	if (!hasDialogData.value) {
		validationError.value = __(
			"Open expenses once while online to cache accounts and limits before recording offline.",
		)
		return
	}

	validationError.value = validateForm()
	if (validationError.value) {
		return
	}

	if (isOffline.value) {
		isBusy.value = true
		try {
			const attachments = selectedFiles.value.map((file) => ({
				name: file.name,
				type: file.type,
				size: file.size,
				blob: file,
			}))
			await offlineStore.saveExpenseOffline(
				{
					pos_opening_shift: props.posOpeningShift,
					pos_profile: props.posProfile,
					expense_account: form.expense_account,
					amount: Number.parseFloat(form.amount),
					mode_of_payment: form.mode_of_payment,
					employee: null,
					cashier: currentCashierName.value,
					remarks: (form.remarks || "").trim(),
					company_currency: currency.value,
				},
				attachments,
				{
					maximum_expense_amount: maximumExpenseAmount.value,
					shift_expense_total: shiftExpenseTotal.value,
					max_file_size: maxFileSize.value,
				},
			)
			showSuccess(__("Expense saved offline; will sync when you reconnect"))
			clearExpenseFields()
			clearSelectedFiles()
			validationError.value = ""
			await refreshPendingExpenses()
			emit("expense-created", { offline: true })
		} catch (error) {
			const parsed = parseError(normalizeSubmitError(error))
			validationError.value = parsed.message
			showError(parsed.message)
		} finally {
			isBusy.value = false
		}
		return
	}

	isBusy.value = true
	try {
		await submitResource.submit()
		// isBusy cleared in onSuccess/onError — createResource does not await onSuccess.
	} catch (error) {
		isBusy.value = false
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	}
}

async function cancelExpense(expense) {
	if (isBusy.value) {
		return
	}

	if (isOffline.value) {
		validationError.value = __(
			"POS expenses cannot be cancelled while offline. Please connect to the internet and try again.",
		)
		return
	}

	const journalEntry = expense?.journal_entry || expense
	const amountLabel = expense?.amount != null ? formatCurrency(expense.amount) : ""
	const message = amountLabel
		? __(
				"Cancel expense {0} ({1})? This reverses the journal entry and cannot be undone from POS.",
				{ 0: journalEntry, 1: amountLabel },
			)
		: __(
				"Cancel expense {0}? This reverses the journal entry and cannot be undone from POS.",
				{ 0: journalEntry },
			)

	const confirmed = await showConfirm({
		title: __("Cancel Expense"),
		message,
		actionLabel: __("Cancel Expense"),
	})
	if (!confirmed) {
		return
	}

	// Manager approval when a "Void POS Expense" rule applies; stub grant otherwise
	const grant = await requireAuthorization("Void POS Expense", {
		pos_profile: props.posProfile,
		journal_entry: journalEntry,
		amount: Number.parseFloat(expense?.amount) || 0,
		amountLabel: "Expense Amount",
		currency: currency.value,
	})
	if (!grant) {
		return
	}

	validationError.value = ""
	cancellingExpense.value = journalEntry
	isBusy.value = true

	try {
		await cancelResource.submit({
			journal_entry: journalEntry,
			pos_opening_shift: props.posOpeningShift,
			pos_profile: props.posProfile,
			authorization_token: grant.grant_token,
		})
	} catch (error) {
		cancellingExpense.value = ""
		isBusy.value = false
		const parsed = parseError(normalizeSubmitError(error))
		validationError.value = parsed.message
	}
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}

.pos-expense-dialog-fields :deep(.dropdown-menu) {
	z-index: 1000;
}
</style>
