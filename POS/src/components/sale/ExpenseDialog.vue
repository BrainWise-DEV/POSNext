<template>
	<Dialog v-model="open" :options="{ title: __('POS Expense'), size: 'md' }">
		<template #body-content>
			<div v-if="dialogDataResource.loading" class="text-center py-8">
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
							{{ __("POS expenses cannot be recorded while offline. Please connect to the internet and try again.") }}
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
						:placeholder="__('Search expense account...')"
						icon="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
						required
					/>
					<p
						v-if="expenseAccountOptions.length === 0"
						class="mt-1 text-xs text-amber-700 text-start"
					>
						{{ __("No expense accounts found for this company.") }}
					</p>
				</div>

				<div>
					<label class="block text-start text-sm font-medium text-gray-700 mb-2">
						{{ __("Amount") }} <span class="text-red-500">*</span>
					</label>
					<Input
						v-model="form.amount"
						type="number"
						min="0"
						step="0.01"
						:placeholder="__('Enter amount')"
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
						:placeholder="__('Search payment method...')"
						icon="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
						required
					/>
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
						{{ __("Remarks") }}
					</label>
					<textarea
						v-model="form.remarks"
						rows="3"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-start"
						:placeholder="__('Optional remarks')"
					></textarea>
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
					:disabled="submitResource.loading"
					@click="open = false"
				>
					{{ __("Cancel") }}
				</Button>
				<Button
					variant="solid"
					:loading="submitResource.loading"
					:disabled="dialogDataResource.loading || isOffline"
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
import { useFormatters } from "@/composables/useFormatters"
import { useOfflineStatus } from "@/composables/useOfflineStatus"
import { useToast } from "@/composables/useToast"
import { parseError } from "@/utils/errorHandler"
import { Button, Dialog, FeatherIcon, Input, createResource } from "frappe-ui"
import { computed, reactive, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	posOpeningShift: String,
	currency: {
		type: String,
		default: "USD",
	},
	maximumExpenseAmount: {
		type: Number,
		default: 0,
	},
})

const emit = defineEmits(["update:modelValue", "expense-created"])

const { formatCurrency } = useFormatters()
const { showSuccess } = useToast()
const { isOffline } = useOfflineStatus()

const form = reactive({
	expense_account: "",
	amount: "",
	mode_of_payment: "",
	employee: "",
	remarks: "",
})

const validationError = ref("")

const open = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const maximumExpenseAmount = computed(
	() =>
		Number.parseFloat(props.maximumExpenseAmount) ||
		Number.parseFloat(dialogDataResource.data?.maximum_expense_amount) ||
		0,
)

const shiftExpenseTotal = computed(
	() => Number.parseFloat(dialogDataResource.data?.shift_expense_total) || 0,
)

const remainingExpenseAmount = computed(() => {
	if (maximumExpenseAmount.value <= 0) {
		return 0
	}

	const remaining = Number.parseFloat(dialogDataResource.data?.remaining_expense_amount)
	if (Number.isFinite(remaining)) {
		return Math.max(0, remaining)
	}

	return Math.max(0, maximumExpenseAmount.value - shiftExpenseTotal.value)
})

const shiftExpenseLimitSummary = computed(() => {
	if (maximumExpenseAmount.value <= 0) {
		return ""
	}

	return [
		__("Shift limit: {0}", { 0: formatCurrency(maximumExpenseAmount.value) }),
		__("Recorded: {0}", { 0: formatCurrency(shiftExpenseTotal.value) }),
		__("Remaining: {0}", { 0: formatCurrency(remainingExpenseAmount.value) }),
	].join(" | ")
})

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
			remarks: form.remarks || null,
		}
	},
	auto: false,
	onSuccess(data) {
		showSuccess(data?.message || __("POS Expense recorded successfully"))
		emit("expense-created", data)
		open.value = false
		resetForm()
	},
	onError(error) {
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

const expenseAccountOptions = computed(() =>
	(dialogDataResource.data?.expense_accounts || []).map((account) => ({
		label: account.account_name || account.name,
		subtitle: account.account_name ? account.name : "",
		value: account.name,
	})),
)

const paymentMethodOptions = computed(() =>
	(dialogDataResource.data?.payment_methods || []).map((method) => ({
		label: method.mode_of_payment,
		value: method.mode_of_payment,
	})),
)

const employeeOptions = computed(() =>
	(dialogDataResource.data?.employees || []).map((employee) => ({
		label: employee.employee_name || employee.name,
		subtitle: employee.employee_name ? employee.name : "",
		value: employee.name,
	})),
)

watch(open, async (isOpen) => {
	if (!isOpen) {
		validationError.value = ""
		return
	}

	if (!props.posProfile || !props.posOpeningShift) {
		validationError.value = __("An active POS shift is required")
		return
	}

	resetForm()
	await dialogDataResource.submit()
})

function resetForm() {
	form.expense_account = ""
	form.amount = ""
	form.mode_of_payment = ""
	form.employee = ""
	form.remarks = ""
	validationError.value = ""
}

function validateForm() {
	if (!form.expense_account) {
		return __("Expense Account is required")
	}

	const amount = Number.parseFloat(form.amount)
	if (!Number.isFinite(amount) || amount <= 0) {
		return __("Amount must be greater than zero")
	}

	if (maximumExpenseAmount.value > 0 && amount > remainingExpenseAmount.value) {
		return __("Amount exceeds the remaining shift expense allowance of {0}", {
			0: formatCurrency(remainingExpenseAmount.value),
		})
	}

	if (!form.mode_of_payment) {
		return __("Mode of Payment is required")
	}

	return ""
}

async function submitExpense() {
	if (isOffline.value) {
		validationError.value = __(
			"POS expenses cannot be recorded while offline. Please connect to the internet and try again.",
		)
		return
	}

	validationError.value = validateForm()
	if (validationError.value) {
		return
	}

	try {
		await submitResource.submit()
	} catch (error) {
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
