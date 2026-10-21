<template>
	<Dialog
		v-model="show"
		:options="{ title: __('Return Without Invoice'), size: '4xl' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<div
					class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-start"
				>
					<p class="text-sm font-semibold text-amber-900">
						{{ __("Return Without Invoice") }}
					</p>
					<p class="mt-1 text-xs leading-relaxed text-amber-800">
						{{
							__(
								"Items are credited using the current POS selling price. The submitted credit note remains outstanding on the customer's account."
							)
						}}
					</p>
				</div>

				<div
					class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-start"
				>
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<p class="text-xs text-gray-500">
								{{ __("Customer") }}
							</p>
							<p
								class="mt-1 truncate text-sm font-semibold text-gray-900"
							>
								{{
									customerDisplay ||
									__("No customer selected")
								}}
							</p>
						</div>

						<Button
							size="sm"
							variant="subtle"
							type="button"
							@click="showCustomerPicker = true"
						>
							{{
								customerName
									? __("Change")
									: __("Select Customer")
							}}
						</Button>
					</div>

					<p
						v-if="!customerName"
						class="mt-1 text-xs text-red-600"
					>
						{{
							__(
								"Select a customer before creating this return."
							)
						}}
					</p>
				</div>

				<div class="rounded-xl border border-gray-200 p-3">
					<label
						class="mb-1 block text-xs font-medium text-gray-600"
					>
						{{ __("Search Return Items") }}
					</label>

					<div class="flex gap-2">
						<input
							v-model="searchTerm"
							type="text"
							autocomplete="off"
							class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
							:placeholder="
								__(
									'Search by item code, name or barcode'
								)
							"
							@keydown.enter.prevent="searchItems"
						/>

						<Button
							variant="subtle"
							:loading="searching"
							:disabled="searchTerm.trim().length < 2"
							@click="searchItems"
						>
							{{ __("Search") }}
						</Button>
					</div>

					<div
						v-if="searchResults.length"
						class="mt-2 max-h-48 overflow-y-auto rounded-lg border border-gray-200 bg-white"
					>
						<button
							v-for="row in searchResults"
							:key="`${row.item_code}:${row.stock_uom || ''}`"
							type="button"
							class="flex w-full items-center justify-between gap-3 border-b border-gray-100 px-3 py-2 text-start last:border-b-0 hover:bg-blue-50"
							@click="addSearchResult(row)"
						>
							<div class="min-w-0">
								<p
									class="truncate text-sm font-medium text-gray-900"
								>
									{{ row.item_name || row.item_code }}
								</p>
								<p class="text-xs text-gray-500">
									{{ row.item_code }}
								</p>
							</div>

							<span
								v-if="row.stock_uom"
								class="shrink-0 text-xs text-gray-400"
							>
								{{ row.stock_uom }}
							</span>
						</button>
					</div>
				</div>

				<div class="rounded-xl border border-gray-200 p-3">
					<div
						class="mb-2 flex items-center justify-between gap-3"
					>
						<p class="text-sm font-semibold text-gray-900">
							{{ __("Return Items") }}
						</p>
						<span class="text-xs text-gray-500">
							{{ __("{0} item(s)", [items.length]) }}
						</span>
					</div>

					<div
						v-if="items.length === 0"
						class="py-5 text-center text-sm text-gray-500"
					>
						{{ __("No return items selected") }}
					</div>

					<div
						v-for="(item, index) in items"
						:key="itemKey(item)"
						class="mb-2 grid grid-cols-12 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-2 last:mb-0"
					>
						<div class="col-span-12 min-w-0 md:col-span-5">
							<p
								class="truncate text-sm font-medium text-gray-900"
							>
								{{ item.item_name || item.item_code }}
							</p>
							<p class="text-xs text-gray-500">
								{{ item.item_code }}
							</p>
						</div>

						<div class="col-span-4 md:col-span-2">
							<label class="block text-[11px] text-gray-500">
								{{ __("Qty") }}
							</label>
							<input
								v-model.number="item.qty"
								type="number"
								min="0.001"
								step="1"
								class="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm"
								@change="normalizeQty(item)"
							/>
						</div>

						<div class="col-span-4 md:col-span-2">
							<p class="text-[11px] text-gray-500">
								{{ __("Rate") }}
							</p>
							<p class="text-sm font-medium text-gray-800">
								{{ formatCurrency(item.rate) }}
							</p>
						</div>

						<div class="col-span-3 md:col-span-2">
							<p class="text-[11px] text-gray-500">
								{{ __("Total") }}
							</p>
							<p class="text-sm font-semibold text-gray-900">
								{{
									formatCurrency(
										Number(item.qty || 0) *
											Number(item.rate || 0)
									)
								}}
							</p>
						</div>

						<div
							class="col-span-1 flex justify-end md:col-span-1"
						>
							<button
								type="button"
								class="rounded p-1 text-red-500 hover:bg-red-50"
								:title="__('Remove')"
								@click="items.splice(index, 1)"
							>
								×
							</button>
						</div>
					</div>
				</div>

				<div>
					<label
						class="mb-1 block text-xs font-medium text-gray-600"
					>
						{{ __("Return Reason") }}
					</label>
					<textarea
						v-model="reason"
						rows="3"
						class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
						:placeholder="
							__(
								'Enter the reason for this no-invoice return'
							)
						"
					></textarea>
				</div>

				<div
					class="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 p-3"
				>
					<div>
						<p class="text-xs text-emerald-700">
							{{ __("Estimated Customer Credit") }}
						</p>
						<p class="text-xs text-emerald-600">
							{{
								__(
									"Final amount is recalculated by the server before authorization."
								)
							}}
						</p>
					</div>

					<p class="text-lg font-bold text-emerald-900">
						{{ formatCurrency(estimatedTotal) }}
					</p>
				</div>

				<div
					v-if="errorMessage"
					class="whitespace-pre-line rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
				>
					{{ errorMessage }}
				</div>

				<div
					class="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end"
				>
					<Button
						variant="subtle"
						:disabled="submitting"
						@click="show = false"
					>
						{{ __("Cancel") }}
					</Button>

					<Button
						variant="solid"
						:loading="submitting"
						:disabled="!canSubmit"
						@click="submitReturn"
					>
						{{ __("Create Return") }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>

	<CustomerDialog
		v-model="showCustomerPicker"
		:pos-profile="posProfile"
		@customer-selected="handleCustomerSelected"
	/>
</template>

<script setup>
import CustomerDialog from "@/components/sale/CustomerDialog.vue";
import { useAuthorization } from "@/composables/useAuthorization";
import { useToast } from "@/composables/useToast";
import { call } from "@/utils/apiWrapper";
import { isAuthorizationError } from "@/utils/authorizationError";
import {
	DEFAULT_CURRENCY,
	formatCurrency as formatCurrencyUtil,
} from "@/utils/currency";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, required: true },
	posOpeningShift: { type: String, required: true },
	currency: { type: String, default: DEFAULT_CURRENCY },
	customer: { type: [String, Object], default: null },
});

const emit = defineEmits(["update:modelValue", "return-created"]);

const { showSuccess } = useToast();
const { requireAuthorization } = useAuthorization();

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

const selectedCustomer = ref(props.customer || null);
const showCustomerPicker = ref(false);

const customerName = computed(
	() => selectedCustomer.value?.name || selectedCustomer.value || ""
);

const customerDisplay = computed(
	() =>
		selectedCustomer.value?.customer_name ||
		selectedCustomer.value?.name ||
		selectedCustomer.value ||
		""
);

const searchTerm = ref("");
const searchResults = ref([]);
const searching = ref(false);
const items = ref([]);
const reason = ref("");
const submitting = ref(false);
const errorMessage = ref("");
const preparedDraftName = ref("");

const estimatedTotal = computed(() =>
	items.value.reduce(
		(sum, item) =>
			sum +
			Number(item.qty || 0) *
				Number(item.rate || 0),
		0
	)
);

const canSubmit = computed(
	() =>
		!submitting.value &&
		Boolean(props.posProfile) &&
		Boolean(props.posOpeningShift) &&
		Boolean(customerName.value) &&
		items.value.length > 0 &&
		Boolean(reason.value.trim())
);

function formatCurrency(amount) {
	return formatCurrencyUtil(
		Number(amount || 0),
		props.currency
	);
}

function itemKey(item) {
	return `${item.item_code}::${item.uom || item.stock_uom || ""}`;
}

function normalizeQty(item) {
	const qty = Math.abs(Number(item.qty || 0));
	item.qty = qty > 0 ? qty : 1;
}

function parseError(error) {
	if (!error) return __("Return failed");
	if (typeof error === "string") return error;
	if (typeof error.message === "string") return error.message;

	if (
		Array.isArray(error.messages) &&
		error.messages.length
	) {
		return error.messages.join("\n");
	}

	return __(
		"Return failed. Please review the details and try again."
	);
}

function handleCustomerSelected(customer) {
	selectedCustomer.value = customer;
	showCustomerPicker.value = false;
}

async function searchItems() {
	const term = searchTerm.value.trim();

	if (term.length < 2) {
		searchResults.value = [];
		return;
	}

	searching.value = true;
	errorMessage.value = "";

	try {
		searchResults.value =
			(await call(
				"pos_next.api.no_invoice_returns.search_return_items",
				{
					search_term: term,
					pos_profile: props.posProfile,
					limit: 20,
				}
			)) || [];
	} catch (error) {
		searchResults.value = [];
		errorMessage.value = parseError(error);
	} finally {
		searching.value = false;
	}
}

async function addSearchResult(row) {
	errorMessage.value = "";

	try {
		const detail = await call(
			"pos_next.api.no_invoice_returns.get_return_item_details",
			{
				item_code: row.item_code,
				pos_profile: props.posProfile,
				qty: 1,
				uom: row.stock_uom || null,
			}
		);

		if (!detail?.item_code) {
			throw new Error(__("Item could not be loaded."));
		}

		if (detail.has_serial_no || detail.has_batch_no) {
			throw new Error(
				__(
					"Serialized or batched items require Return With Invoice."
				)
			);
		}

		const key = itemKey(detail);
		const existing = items.value.find(
			(item) => itemKey(item) === key
		);

		if (existing) {
			existing.qty =
				Number(existing.qty || 0) + 1;
		} else {
			items.value.push({
				...detail,
				qty: 1,
			});
		}

		searchTerm.value = "";
		searchResults.value = [];
	} catch (error) {
		errorMessage.value = parseError(error);
	}
}

async function discardPreparedDraft() {
	const name = preparedDraftName.value;
	if (!name) return;

	preparedDraftName.value = "";

	try {
		await call(
			"pos_next.api.no_invoice_returns.discard_no_invoice_return_draft",
			{ name }
		);
	} catch {
		// Best-effort cleanup. A submitted invoice must never be deleted here.
	}
}

async function submitPreparedReturn(draftName, token) {
	return await call(
		"pos_next.api.no_invoice_returns.submit_no_invoice_return",
		{
			name: draftName,
			authorization_token: token || null,
		}
	);
}

async function submitReturn() {
	if (!canSubmit.value) return;

	submitting.value = true;
	errorMessage.value = "";

	try {
		const draft = await call(
			"pos_next.api.no_invoice_returns.prepare_no_invoice_return",
			{
				payload: JSON.stringify({
					pos_profile: props.posProfile,
					pos_opening_shift: props.posOpeningShift,
					customer: customerName.value,
					reason: reason.value.trim(),
					items: items.value.map((item) => ({
						item_code: item.item_code,
						qty: Math.abs(Number(item.qty || 0)),
						uom: item.uom || item.stock_uom || null,
					})),
				}),
			}
		);

		if (!draft?.name) {
			throw new Error(
				__("Failed to prepare Return Without Invoice.")
			);
		}

		preparedDraftName.value = draft.name;

		const amount = Math.abs(
			Number(draft.grand_total || 0)
		);

		if (amount <= 0) {
			throw new Error(
				__(
					"The calculated return amount must be greater than zero."
				)
			);
		}

		const action = "Sales Return Without Invoice";
		const authContext = {
			pos_profile: props.posProfile,
			customer: customerName.value,
			amount,
		};

		let grant = await requireAuthorization(
			action,
			authContext
		);

		if (!grant) {
			await discardPreparedDraft();
			return;
		}

		let result;

		try {
			result = await submitPreparedReturn(
				draft.name,
				grant.grant_token || null
			);
		} catch (error) {
			// The authorization policy may have changed after POS bootstrap.
			if (
				isAuthorizationError(error) &&
				!grant.grant_token
			) {
				grant = await requireAuthorization(
					action,
					authContext,
					{ force: true }
				);

				if (!grant) {
					await discardPreparedDraft();
					return;
				}

				result = await submitPreparedReturn(
					draft.name,
					grant.grant_token || null
				);
			} else {
				throw error;
			}
		}

		preparedDraftName.value = "";

		show.value = false;
		emit("return-created", result);

		showSuccess(
			__(
				"Return {0} created successfully",
				[result?.name || draft.name]
			)
		);

		reset();
	} catch (error) {
		await discardPreparedDraft();
		errorMessage.value = parseError(error);
	} finally {
		submitting.value = false;
	}
}

function reset() {
	selectedCustomer.value = props.customer || null;
	showCustomerPicker.value = false;
	searchTerm.value = "";
	searchResults.value = [];
	items.value = [];
	reason.value = "";
	errorMessage.value = "";
	preparedDraftName.value = "";
}

watch(show, (opened) => {
	if (opened) {
		reset();
	}
});

watch(
	() => props.customer,
	(value) => {
		if (!show.value) {
			selectedCustomer.value = value || null;
		}
	}
);
</script>
