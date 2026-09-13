<template>
	<Dialog v-model="open" :options="{ size: '5xl' }">
		<template #body-title>
			<div class="text-start pe-8">
				<h3 class="text-xl font-bold text-slate-900 tracking-tight">
					{{ __("Cash Expense") }}
				</h3>
				<p class="mt-0.5 text-sm font-semibold text-gray-500">
					{{ __("Record money paid from the cash drawer during this shift.") }}
				</p>
			</div>
		</template>

		<template #body-content>
			<div v-if="dialogLoading || (dialogDataResource.loading && !isOffline)" class="text-center py-10">
				<div class="inline-block animate-spin rounded-full h-10 w-10 border-b-4 border-blue-600"></div>
				<p class="mt-2 text-sm font-semibold text-gray-500">{{ __("Loading expense data...") }}</p>
			</div>

			<div v-else class="pos-expense-dialog-fields flex flex-col gap-3">
				<div
					v-if="isOffline"
					class="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 flex items-center gap-2"
				>
					<FeatherIcon name="wifi-off" class="w-4 h-4 text-amber-600 shrink-0" />
					<p class="text-xs text-amber-800 text-start font-semibold">
						<span class="font-bold">{{ __("Offline Mode") }}:</span>
						{{
							__(
								"Saved locally; syncs when you reconnect. Cancel of submitted expenses requires online.",
							)
						}}
					</p>
				</div>

				<div
					v-if="pendingAttachJournalEntry"
					class="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-start"
				>
					<p class="text-xs text-amber-900 font-semibold">
						<span class="font-bold">
							{{
								__("Expense {0} was recorded, but attachments failed.", {
									0: pendingAttachJournalEntry,
								})
							}}
						</span>
						{{ __("Retry attach below — do not submit again.") }}
					</p>
					<div class="mt-2 flex flex-wrap gap-2">
						<button
							type="button"
							class="inline-flex items-center justify-center rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
							:disabled="isOffline || !selectedFiles.length || isBusy"
							@click="retryAttach"
						>
							{{ __("Retry Attach") }}
						</button>
						<button
							type="button"
							class="inline-flex items-center justify-center rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-bold text-gray-700 hover:bg-gray-200 disabled:opacity-50"
							:disabled="isBusy"
							@click="discardPendingAttach"
						>
							{{ __("Continue without attachments") }}
						</button>
					</div>
				</div>

				<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
					<!-- Form column -->
					<div
						class="flex flex-col gap-3.5 min-w-0 rounded-2xl border border-gray-200 bg-white p-4"
					>
						<p class="text-start text-sm font-bold text-slate-800">
							{{ __("New Expense") }}
						</p>

						<div class="flex flex-col gap-3">
							<div>
								<label class="block text-start text-xs font-bold text-slate-700 mb-1.5">
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
									class="mt-1 text-xs font-semibold text-amber-700 text-start"
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
								<label class="block text-start text-xs font-bold text-slate-700 mb-1.5">
									{{ __("Amount") }}
									<span v-if="currency">({{ currency }})</span>
									<span class="text-red-500">*</span>
								</label>
								<div class="relative">
									<span
										class="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-gray-400"
									>
										<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
											/>
										</svg>
									</span>
									<input
										v-model="form.amount"
										type="number"
										min="0"
										step="0.01"
										class="w-full h-10 ps-9 pe-3 border border-gray-300 rounded-xl text-sm font-semibold text-slate-800 placeholder:text-gray-400 placeholder:font-normal focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-start disabled:bg-gray-50 disabled:text-gray-500"
										:placeholder="amountPlaceholder"
										:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
									/>
								</div>
							</div>

							<div>
								<label class="block text-start text-xs font-bold text-slate-700 mb-1.5">
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
								<label class="block text-start text-xs font-bold text-slate-700 mb-1.5">
									{{ __("Expense Description") }} <span class="text-red-500">*</span>
								</label>
								<input
									v-model="form.remarks"
									type="text"
									class="w-full h-10 px-3 border border-gray-300 rounded-xl text-sm font-semibold text-slate-800 placeholder:text-gray-400 placeholder:font-normal focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-start disabled:bg-gray-50"
									:placeholder="__('Enter a short description')"
									:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
								/>
							</div>
						</div>

						<div
							v-if="maximumExpenseAmount > 0"
							class="rounded-xl bg-slate-50 border border-slate-100 px-3.5 py-3"
						>
							<div class="grid grid-cols-3 gap-2 text-start">
								<div>
									<p class="text-[11px] font-bold text-gray-500">{{ __("Shift Limit") }}</p>
									<p class="mt-0.5 text-xs font-bold text-slate-800">
										{{ formatCurrency(maximumExpenseAmount) }}
									</p>
								</div>
								<div>
									<p class="text-[11px] font-bold text-gray-500">{{ __("Already Spent") }}</p>
									<p class="mt-0.5 text-xs font-bold text-blue-600">
										{{ formatCurrency(alreadySpentAmount) }}
									</p>
								</div>
								<div>
									<p class="text-[11px] font-bold text-gray-500">{{ __("Remaining") }}</p>
									<p class="mt-0.5 text-xs font-bold text-emerald-600">
										{{ formatCurrency(remainingExpenseAmount) }}
									</p>
								</div>
							</div>
							<p
								v-if="pendingLocalTotal > 0"
								class="mt-2 text-[11px] font-semibold text-amber-700 text-start"
							>
								{{
									__("Includes {0} pending local", {
										0: formatCurrency(pendingLocalTotal),
									})
								}}
							</p>
						</div>

						<div>
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
								class="w-full rounded-xl border border-dashed border-gray-300 bg-white px-3 py-4 text-center hover:border-blue-400 hover:bg-blue-50/40 transition-colors disabled:opacity-50"
								:disabled="isBusy"
								@click="fileInput?.click()"
							>
								<svg
									class="mx-auto w-6 h-6 text-blue-500"
									fill="none"
									stroke="currentColor"
									stroke-width="1.8"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
									/>
								</svg>
								<p class="mt-1.5 text-sm font-bold text-slate-700">
									{{ __("Upload Receipt") }}
								</p>
								<p class="mt-0.5 text-xs font-semibold text-gray-500" :title="attachmentHelpText">
									{{ attachmentUploadHint }}
								</p>
							</button>
							<ul
								v-if="selectedFiles.length"
								class="mt-2 space-y-1 text-start max-h-16 overflow-y-auto"
							>
								<li
									v-for="(file, index) in selectedFiles"
									:key="`${file.name}-${index}`"
									class="flex items-center justify-between gap-2 text-xs font-semibold text-gray-600 px-1"
								>
									<span class="truncate">{{ file.name }}</span>
									<button
										type="button"
										class="shrink-0 font-bold text-red-600 hover:text-red-700"
										:disabled="isBusy"
										@click="removeSelectedFile(index)"
									>
										{{ __("Remove") }}
									</button>
								</li>
							</ul>
						</div>

						<div
							v-if="validationError"
							class="rounded-xl bg-red-50 border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 text-start"
						>
							{{ validationError }}
						</div>
					</div>

					<!-- Lists column -->
					<div
						class="flex flex-col gap-3 min-w-0 md:max-h-[min(64vh,560px)] md:min-h-[300px] rounded-2xl border border-gray-200 bg-white p-4"
					>
						<div class="flex items-center justify-between gap-3 shrink-0">
							<p class="text-sm font-bold text-slate-800 text-start">
								{{ __("Expenses This Shift") }}
							</p>
							<p class="text-sm font-bold text-blue-600 whitespace-nowrap">
								{{ __("Total") }}: {{ formatCurrency(expensesThisShiftTotal) }}
							</p>
						</div>

						<div class="min-h-0 flex-1 overflow-auto rounded-xl border border-gray-100">
							<table class="w-full text-start border-collapse min-w-[480px]">
								<thead class="sticky top-0 bg-gray-50 z-[1]">
									<tr class="text-[11px] font-bold text-gray-600">
										<th class="px-3 py-2.5 font-bold">{{ __("Category") }}</th>
										<th class="px-3 py-2.5 font-bold">{{ __("Cashier") }}</th>
										<th class="px-3 py-2.5 font-bold whitespace-nowrap">{{ __("Amount") }}</th>
										<th class="px-3 py-2.5 font-bold">{{ __("Status") }}</th>
										<th class="px-3 py-2.5 font-bold text-end">{{ __("Action") }}</th>
									</tr>
								</thead>
								<tbody>
									<tr
										v-for="row in pendingExpenses"
										:key="row.offline_id || row.id"
										class="border-t border-gray-100 text-xs text-slate-700"
									>
										<td class="px-3 py-2.5 max-w-[9rem]">
											<p class="truncate font-bold" :title="row.data?.expense_account">
												{{ row.data?.expense_account || "—" }}
											</p>
											<p
												v-if="row.error"
												class="mt-0.5 text-[10px] font-semibold text-red-600 truncate"
												:title="row.error"
											>
												{{ row.error }}
											</p>
											<p
												v-else-if="row.server_journal_entry"
												class="mt-0.5 text-[10px] font-semibold text-amber-700 truncate"
											>
												{{
													__("JE {0}; files pending", {
														0: row.server_journal_entry,
													})
												}}
											</p>
										</td>
										<td class="px-3 py-2.5 max-w-[7rem]">
											<p class="truncate font-semibold" :title="pendingCashierLabel(row)">
												{{ pendingCashierLabel(row) }}
											</p>
										</td>
										<td class="px-3 py-2.5 whitespace-nowrap font-bold text-slate-800">
											{{ formatCurrency(row.data?.amount) }}
										</td>
										<td class="px-3 py-2.5">
											<span
												class="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-800"
											>
												<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
												{{ __("Pending") }}
											</span>
										</td>
										<td class="px-3 py-2.5 text-end">
											<button
												v-if="!row.server_journal_entry"
												type="button"
												class="inline-flex items-center rounded-lg border border-red-300 px-2.5 py-1 text-[11px] font-bold text-red-600 hover:bg-red-50 disabled:opacity-50"
												:disabled="isBusy || row.synced"
												@click="deletePendingExpense(row)"
											>
												{{ __("Delete") }}
											</button>
											<button
												v-else
												type="button"
												class="inline-flex items-center rounded-lg border border-gray-300 px-2.5 py-1 text-[11px] font-bold text-gray-600 hover:bg-gray-50 disabled:opacity-50"
												:disabled="isBusy"
												@click="discardPendingAttachments(row)"
											>
												{{ __("Discard files") }}
											</button>
										</td>
									</tr>

									<tr
										v-for="expense in recordedExpenses"
										:key="expense.journal_entry"
										class="border-t border-gray-100 text-xs text-slate-700 hover:bg-slate-50/70"
									>
										<td class="px-3 py-2.5 max-w-[9rem]">
											<p class="truncate font-bold" :title="expense.expense_account">
												{{ expense.expense_account || "—" }}
											</p>
											<p
												v-if="expense.remarks"
												class="mt-0.5 text-[10px] font-semibold text-gray-400 truncate"
												:title="expense.remarks"
											>
												{{ expense.remarks }}
											</p>
										</td>
										<td class="px-3 py-2.5 max-w-[7rem]">
											<p class="truncate font-semibold" :title="expense.cashier || expense.owner">
												{{ expense.cashier || expense.owner || "—" }}
											</p>
										</td>
										<td class="px-3 py-2.5 whitespace-nowrap font-bold text-slate-800">
											{{ formatCurrency(expense.amount) }}
										</td>
										<td class="px-3 py-2.5">
											<span
												class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
											>
												<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
												{{ __("Recorded") }}
											</span>
										</td>
										<td class="px-3 py-2.5 text-end">
											<button
												v-if="canCancelExpense"
												type="button"
												class="inline-flex items-center rounded-lg border border-red-300 px-2.5 py-1 text-[11px] font-bold text-red-600 hover:bg-red-50 disabled:opacity-50"
												:disabled="isOffline || isBusy || cancellingExpense === expense.journal_entry"
												@click="cancelExpense(expense)"
											>
												{{
													cancellingExpense === expense.journal_entry
														? __("Voiding...")
														: __("Void")
												}}
											</button>
										</td>
									</tr>

									<tr v-if="!pendingExpenses.length && !recordedExpenses.length">
										<td colspan="5" class="px-3 py-12 text-center">
											<svg
												class="mx-auto w-8 h-8 text-gray-200"
												fill="none"
												stroke="currentColor"
												stroke-width="1.5"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M9 14l6-6m-5.5.5h.01m4.99 5h.01M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2z"
												/>
											</svg>
											<p class="mt-2 text-xs font-semibold text-gray-400">
												{{ __("No expenses recorded this shift yet.") }}
											</p>
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex justify-end gap-2.5 w-full">
				<button
					type="button"
					class="inline-flex items-center justify-center rounded-xl bg-gray-100 px-4 py-2 text-sm font-bold text-slate-700 hover:bg-gray-200 disabled:opacity-50 transition-colors"
					:disabled="isBusy"
					@click="open = false"
				>
					{{ __("Close") }}
				</button>
				<button
					v-if="!pendingAttachJournalEntry"
					type="button"
					class="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
					:disabled="dialogLoading || isBusy || !hasDialogData"
					@click="submitExpense"
				>
					{{
						isBusy && !cancellingExpense
							? __("Recording...")
							: __("Record Expense")
					}}
				</button>
			</div>
		</template>
	</Dialog>

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
					<button
						type="button"
						class="px-4 py-1.5 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 active:bg-gray-100 transition-colors"
						@click="resolveConfirm(false)"
					>
						{{ __("Cancel") }}
					</button>
					<button
						type="button"
						class="px-4 py-1.5 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 transition-colors"
						@click="resolveConfirm(true)"
					>
						{{ confirmActionLabel }}
					</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import AutocompleteSelect from "@/components/common/AutocompleteSelect.vue"
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
import { Dialog, FeatherIcon, createResource } from "frappe-ui"
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

	validationError.value = ""
	cancellingExpense.value = journalEntry
	isBusy.value = true

	try {
		await cancelResource.submit({
			journal_entry: journalEntry,
			pos_opening_shift: props.posOpeningShift,
			pos_profile: props.posProfile,
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
:global(.dialog-content:has(.pos-expense-dialog-fields)) {
	overflow: visible !important;
	width: min(96vw, 72rem) !important;
	max-width: min(96vw, 72rem) !important;
	max-height: min(94vh, 900px);
	margin-top: 1rem !important;
	margin-bottom: 1rem !important;
	border-radius: 1rem !important;
}

:global(.dialog-content:has(.pos-expense-dialog-fields) .mb-6) {
	margin-bottom: 0.5rem !important;
}

:global(.dialog-content:has(.pos-expense-dialog-fields) .pb-6) {
	padding-bottom: 0.75rem !important;
	padding-top: 0.75rem !important;
}

:global(.dialog-content:has(.pos-expense-dialog-fields) .pb-7) {
	padding-top: 0.75rem !important;
	padding-bottom: 1rem !important;
	border-top: 1px solid #e5e7eb;
}

.pos-expense-dialog-fields :deep(.dropdown-menu) {
	z-index: 1000;
}

.pos-expense-dialog-fields :deep(.select-input) {
	height: 2.5rem;
	border-radius: 0.75rem;
	border-color: #d1d5db;
}

.pos-expense-dialog-fields :deep(.select-input:focus) {
	border-color: #3b82f6;
	box-shadow: 0 0 0 3px rgb(59 130 246 / 0.2);
}
</style>
