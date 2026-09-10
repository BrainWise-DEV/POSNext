<template>
	<Dialog v-model="open" :options="{ title: __('POS Expense'), size: 'md' }">
		<template #body-content>
			<div v-if="dialogLoading || (dialogDataResource.loading && !isOffline)" class="text-center py-8">
				<div class="inline-block animate-spin rounded-full h-10 w-10 border-b-4 border-blue-600"></div>
				<p class="mt-3 text-sm text-gray-600">{{ __("Loading expense data...") }}</p>
			</div>

			<div v-else class="pos-expense-dialog-fields flex flex-col gap-5">
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
									"Expenses are saved locally and will sync when you reconnect. Cancel of submitted expenses requires online.",
								)
							}}
						</p>
					</div>
				</div>

				<div
					v-if="pendingAttachJournalEntry"
					class="bg-amber-50 border border-amber-200 rounded-lg p-4 text-start"
				>
					<p class="text-sm font-medium text-amber-900">
						{{
							__("Expense {0} was recorded, but attachments failed.", {
								0: pendingAttachJournalEntry,
							})
						}}
					</p>
					<p class="text-xs text-amber-700 mt-1">
						{{ __("Fix or keep the files below, then retry attach. Do not submit again.") }}
					</p>
					<div class="mt-3 flex flex-wrap gap-2">
						<Button
							variant="solid"
							size="sm"
							:loading="isBusy"
							:disabled="isOffline || !selectedFiles.length || isBusy"
							@click="retryAttach"
						>
							{{ __("Retry Attach") }}
						</Button>
						<Button
							variant="subtle"
							size="sm"
							:disabled="isBusy"
							@click="discardPendingAttach"
						>
							{{ __("Continue without attachments") }}
						</Button>
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
						icon="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
						required
						@search="handleExpenseAccountSearch"
					/>
					<p
						v-if="expenseAccountOptions.length === 0 && !accountSearchLoading"
						class="mt-1 text-xs text-amber-700 text-start"
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
						{{ __("Amount") }} <span class="text-red-500">*</span>
						<span v-if="currency" class="text-gray-500 font-normal">
							({{ currency }})
						</span>
					</label>
					<Input
						v-model="form.amount"
						type="number"
						min="0"
						step="0.01"
						:placeholder="amountPlaceholder"
						:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
					/>
					<p
						v-if="maximumExpenseAmount > 0"
						class="mt-1 text-xs text-gray-500 text-start"
					>
						{{ shiftExpenseLimitSummary }}
					</p>
				</div>

				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Mode of Payment") }} <span class="text-red-500">*</span>
					</label>
					<AutocompleteSelect
						v-model="form.mode_of_payment"
						:options="paymentMethodOptions"
						:placeholder="__('Search cash payment method...')"
						icon="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
						required
					/>
					<p class="mt-1 text-xs text-gray-500 text-start">
						{{ __("Only cash drawer modes are allowed for POS expenses.") }}
					</p>
				</div>

				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Employee") }}
					</label>
					<AutocompleteSelect
						v-model="form.employee"
						:options="employeeOptions"
						:placeholder="__('Search employee...')"
						icon="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
					/>
				</div>

				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Remarks") }} <span class="text-red-500">*</span>
					</label>
					<textarea
						v-model="form.remarks"
						rows="3"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-start disabled:bg-gray-50"
						:placeholder="__('Enter remarks for this expense')"
						:disabled="Boolean(pendingAttachJournalEntry) || isBusy"
					></textarea>
				</div>

				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Attachments") }}
					</label>
					<input
						ref="fileInput"
						type="file"
						multiple
						:accept="fileAccept"
						class="block w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
						:disabled="isBusy"
						@change="onFilesSelected"
					/>
					<ul v-if="selectedFiles.length" class="mt-2 space-y-1 text-start">
						<li
							v-for="(file, index) in selectedFiles"
							:key="`${file.name}-${index}`"
							class="flex items-center justify-between gap-2 text-xs text-gray-600"
						>
							<span class="truncate">{{ file.name }}</span>
							<button
								type="button"
								class="shrink-0 text-red-600 hover:text-red-700"
								:disabled="isBusy"
								@click="removeSelectedFile(index)"
							>
								{{ __("Remove") }}
							</button>
						</li>
					</ul>
					<p class="mt-1 text-xs text-gray-500 text-start">
						{{ attachmentHelpText }}
					</p>
				</div>

				<div
					v-if="pendingExpenses.length"
					class="rounded-lg border border-amber-200 overflow-hidden"
				>
					<div class="px-3 py-2 bg-amber-50 border-b border-amber-200 text-start">
						<p class="text-sm font-medium text-amber-900">
							{{ __("Pending sync") }}
							<span class="text-xs font-normal text-amber-700">
								({{ pendingExpenses.length }})
							</span>
						</p>
					</div>
					<ul class="divide-y divide-amber-100">
						<li
							v-for="row in pendingExpenses"
							:key="row.offline_id || row.id"
							class="flex items-start justify-between gap-3 px-3 py-2 text-start"
						>
							<div class="min-w-0 flex-1">
								<p class="text-sm font-medium text-gray-900 truncate">
									{{ row.data?.expense_account }}
								</p>
								<p class="text-xs text-gray-500">
									{{ formatCurrency(row.data?.amount) }}
									<span v-if="row.data?.mode_of_payment">
										· {{ row.data.mode_of_payment }}
									</span>
									<span v-if="row.attachments?.length">
										· {{ __("{0} file(s)", { 0: row.attachments.length }) }}
									</span>
								</p>
								<p v-if="row.data?.remarks" class="text-xs text-gray-400 truncate">
									{{ row.data.remarks }}
								</p>
								<p v-if="row.error" class="text-xs text-red-600 mt-0.5">
									{{ row.error }}
								</p>
								<p
									v-else-if="row.server_journal_entry"
									class="text-xs text-amber-700 mt-0.5"
								>
									{{
										__("JE {0} created; attachments pending", {
											0: row.server_journal_entry,
										})
									}}
								</p>
							</div>
							<Button
								v-if="!row.server_journal_entry"
								variant="subtle"
								size="sm"
								:disabled="isBusy || row.synced"
								@click="deletePendingExpense(row)"
							>
								{{ __("Delete") }}
							</Button>
							<Button
								v-else
								variant="subtle"
								size="sm"
								:disabled="isBusy"
								@click="discardPendingAttachments(row)"
							>
								{{ __("Discard files") }}
							</Button>
						</li>
					</ul>
				</div>

				<div
					v-if="recordedExpenses.length"
					class="rounded-lg border border-gray-200 overflow-hidden"
				>
					<div class="px-3 py-2 bg-gray-50 border-b border-gray-200 text-start">
						<p class="text-sm font-medium text-gray-800">
							{{ __("Expenses this shift") }}
						</p>
					</div>
					<ul class="divide-y divide-gray-100">
						<li
							v-for="expense in recordedExpenses"
							:key="expense.journal_entry"
							class="flex items-start justify-between gap-3 px-3 py-2 text-start"
						>
							<div class="min-w-0 flex-1">
								<p class="text-sm font-medium text-gray-900 truncate">
									{{ expense.expense_account }}
								</p>
								<p class="text-xs text-gray-500">
									{{ formatCurrency(expense.amount) }}
									<span v-if="expense.mode_of_payment">
										· {{ expense.mode_of_payment }}
									</span>
								</p>
								<p v-if="expense.remarks" class="text-xs text-gray-400 truncate">
									{{ expense.remarks }}
								</p>
							</div>
							<Button
								v-if="canCancelExpense"
								variant="subtle"
								size="sm"
								:loading="cancellingExpense === expense.journal_entry"
								:disabled="isOffline || isBusy"
								@click="cancelExpense(expense)"
							>
								{{ __("Cancel") }}
							</Button>
						</li>
					</ul>
				</div>

				<div
					v-if="validationError"
					class="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 text-start"
				>
					{{ validationError }}
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex justify-end gap-2 w-full">
				<Button
					variant="subtle"
					:disabled="isBusy"
					@click="open = false"
				>
					{{ __("Close") }}
				</Button>
				<Button
					v-if="!pendingAttachJournalEntry"
					variant="solid"
					:loading="isBusy"
					:disabled="dialogLoading || isBusy || !hasDialogData"
					@click="submitExpense"
				>
					{{ __("Submit") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import AutocompleteSelect from "@/components/common/AutocompleteSelect.vue"
import { useOfflineStatus } from "@/composables/useOfflineStatus"
import { useToast } from "@/composables/useToast"
import { usePOSShiftStore } from "@/stores/posShift"
import { usePOSSyncStore } from "@/stores/posSync"
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { parseError } from "@/utils/errorHandler"
import { cacheExpenseDialogData, getExpenseDialogCache } from "@/utils/offline"
import { Button, Dialog, FeatherIcon, Input, createResource } from "frappe-ui"
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

/** Prefer dialog API company_currency; then prop / shiftStore (Company.default_currency); never profile selling currency alone. */
const currency = computed(
	() =>
		dialogPayload.value?.company_currency ||
		props.currency ||
		shiftStore.companyCurrency ||
		DEFAULT_CURRENCY,
)

const amountPlaceholder = computed(() =>
	currency.value
		? __("Enter amount in {0}", { 0: currency.value })
		: __("Enter amount"),
)

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), currency.value)
}

const form = reactive({
	expense_account: "",
	amount: "",
	mode_of_payment: "",
	employee: "",
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

const shiftExpenseLimitSummary = computed(() => {
	if (maximumExpenseAmount.value <= 0) {
		return ""
	}

	const parts = [
		__("Profile max: {0}", { 0: formatCurrency(maximumExpenseAmount.value) }),
		__("Recorded this shift: {0}", { 0: formatCurrency(shiftExpenseTotal.value) }),
	]
	if (pendingLocalTotal.value > 0) {
		parts.push(__("Pending local: {0}", { 0: formatCurrency(pendingLocalTotal.value) }))
	}
	parts.push(__("Remaining: {0}", { 0: formatCurrency(remainingExpenseAmount.value) }))
	return parts.join(" | ")
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
			employee: form.employee || null,
			remarks: (form.remarks || "").trim() || null,
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

const employeeOptions = computed(() =>
	(dialogPayload.value?.employees || []).map((employee) => ({
		label: employee.employee_name || employee.name,
		subtitle: employee.employee_name ? employee.name : "",
		value: employee.name,
	})),
)

const recordedExpenses = computed(() => dialogPayload.value?.expenses || [])

async function refreshPendingExpenses() {
	try {
		const rows = await offlineStore.loadPendingExpenses()
		pendingExpenses.value = (rows || []).filter(
			(row) =>
				!row.data?.pos_opening_shift ||
				row.data.pos_opening_shift === props.posOpeningShift,
		)
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
	if (!window.confirm(__("Delete this unsynced offline expense? It will not be sent to the server."))) {
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
	if (
		!window.confirm(
			__(
				"Keep Journal Entry {0} and discard remaining queued attachments?",
				{ 0: row.server_journal_entry },
			),
		)
	) {
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
	form.employee = ""
	form.remarks = ""
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
					employee: form.employee || null,
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
	const confirmMessage = amountLabel
		? __(
				"Cancel expense {0} ({1})? This reverses the journal entry and cannot be undone from POS.",
				{ 0: journalEntry, 1: amountLabel },
			)
		: __(
				"Cancel expense {0}? This reverses the journal entry and cannot be undone from POS.",
				{ 0: journalEntry },
			)

	if (!window.confirm(confirmMessage)) {
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
}

.pos-expense-dialog-fields :deep(.dropdown-menu) {
	z-index: 1000;
}
</style>
