<template>
	<Dialog v-model="show" :options="{ title: dialogTitle, size: '4xl' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<div class="rounded-xl border border-amber-200 bg-amber-50 p-3 sm:p-4 text-start">
					<div class="flex items-start gap-3">
						<FeatherIcon name="shield" class="w-5 h-5 text-amber-700 mt-0.5" />
						<div>
							<p class="text-sm font-bold text-amber-900">
								{{ managerRequired ? __("Manager PIN required") : __("Return authorization") }}
							</p>
							<p class="text-xs text-amber-800 mt-1 leading-relaxed">
								{{
									__(
										"No-invoice returns use the current POS Profile Selling Price List. Customer Credit is the default; cash is limited to Cash payment modes from this POS Profile."
									)
								}}
							</p>
							<p v-if="sellingPriceList" class="text-[11px] text-amber-700 mt-1">
								{{ __("Price List: {0}", [sellingPriceList]) }}
							</p>
						</div>
					</div>
				</div>

				<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
					<div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-start">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<p class="text-xs text-gray-500">{{ __("Customer") }}</p>
								<p class="text-sm font-bold text-gray-900 mt-1 truncate">
									{{ customerDisplay || __("No customer selected") }}
								</p>
							</div>
							<Button size="sm" variant="subtle" type="button" @click="showCustomerPicker = true">
								{{ customerName ? __("Change") : __("Select Customer") }}
							</Button>
						</div>
						<p v-if="!customerName" class="text-xs text-red-600 mt-1">
							{{ __("Select a customer here before creating this return.") }}
						</p>
					</div>
					<div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-start">
						<p class="text-xs text-gray-500">{{ __("Estimated Return Value") }}</p>
						<p class="text-xl font-bold text-gray-900 mt-1">{{ formatCurrency(estimatedTotal) }}</p>
						<p class="text-[11px] text-gray-500 mt-1">
							{{ __("ERPNext recalculates tax and rounding before final submission.") }}
						</p>
					</div>
				</div>

				<RetailItemPicker
					ref="itemPickerRef"
					:pos-profile="posProfile"
					:customer="selectedCustomer"
					:title="__('Return Items')"
					@item-added="addReturnItem"
				/>

				<div v-if="items.length" class="rounded-xl border border-gray-200 overflow-hidden">
					<div class="px-3 py-2 bg-gray-50 border-b border-gray-200 text-start">
						<p class="text-sm font-bold text-gray-800">{{ __("Items to Return") }}</p>
					</div>
					<div class="divide-y divide-gray-100 max-h-72 overflow-y-auto">
						<div v-for="item in items" :key="item.key" class="p-3 flex items-center gap-3">
							<div class="flex-1 min-w-0 text-start">
								<p class="text-sm font-semibold text-gray-900 truncate">{{ item.item_name }}</p>
								<p class="text-xs text-gray-500">{{ item.item_code }} · {{ item.uom }}</p>
								<div v-if="allowRateEdit" class="mt-1 flex items-center gap-2 flex-wrap">
									<label class="text-[11px] text-gray-500">{{ __("Return Rate") }}</label>
									<input
										v-model.number="item.rate"
										type="number"
										min="0"
										step="0.001"
										class="w-28 h-8 rounded-lg border border-gray-300 px-2 text-sm font-semibold"
										@change="normalizeRate(item)"
									/>
									<span class="text-[11px] text-gray-500">{{ __("POS Price") }}: {{ formatCurrency(item.original_rate) }}</span>
									<span v-if="isRateOverridden(item)" class="text-[11px] font-semibold text-amber-700">{{ __("Override") }}</span>
								</div>
								<p v-else class="text-xs text-gray-500 mt-1">{{ formatCurrency(item.rate) }}/{{ item.uom }}</p>
							</div>
							<div class="flex items-center gap-1.5">
								<button type="button" class="w-8 h-8 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 font-bold" @click="changeQty(item, -1)">−</button>
								<input v-model.number="item.qty" type="number" min="0.001" step="1" class="w-16 h-8 rounded-lg border border-gray-300 text-center text-sm font-semibold" @change="normalizeQty(item)" />
								<button type="button" class="w-8 h-8 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 font-bold" @click="changeQty(item, 1)">+</button>
							</div>
							<div class="w-24 text-end">
								<p class="text-sm font-bold text-gray-900">{{ formatCurrency(item.qty * item.rate) }}</p>
								<button type="button" class="text-xs text-red-600 hover:text-red-700" @click="removeItem(item)">{{ __("Remove") }}</button>
							</div>
						</div>
					</div>
				</div>

				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1 text-start">{{ __("Reason") }} <span class="text-red-500">*</span></label>
					<textarea v-model="reason" rows="2" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" :placeholder="__('Required: explain why this return is accepted without an invoice')"></textarea>
				</div>

				<div v-if="!isExchangeCredit" class="rounded-xl border border-gray-200 p-3 sm:p-4">
					<p class="text-sm font-bold text-gray-800 mb-2 text-start">{{ __("Settlement") }}</p>
					<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
						<button type="button" :class="settlementClass('credit')" @click="refundType = 'credit'">
							<div class="text-start"><p class="text-sm font-bold">{{ __("Customer Credit") }}</p><p class="text-xs opacity-80 mt-0.5">{{ __("Recommended for no-invoice returns") }}</p></div>
						</button>
						<button type="button" :class="settlementClass('cash')" @click="refundType = 'cash'">
							<div class="text-start"><p class="text-sm font-bold">{{ __("Cash Refund") }}</p><p class="text-xs opacity-80 mt-0.5">{{ __("Cash mode from this POS Profile") }}</p></div>
						</button>
					</div>
					<div v-if="refundType === 'cash'" class="mt-3">
						<label class="block text-xs font-medium text-gray-600 mb-1 text-start">{{ __("Cash Mode of Payment") }}</label>
						<select v-model="cashMode" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white">
							<option value="">{{ __("Select cash mode") }}</option>
							<option v-for="mode in cashModes" :key="mode" :value="mode">{{ mode }}</option>
						</select>
					</div>
				</div>

				<div v-else class="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-start">
					<p class="text-sm font-bold text-emerald-900">{{ __("Exchange Credit") }}</p>
					<p class="text-xs text-emerald-700 mt-1">{{ __("This return will stay as Customer Credit and will be applied to the replacement sale. No provider refund is sent.") }}</p>
				</div>

				<div v-if="managerRequired" class="rounded-xl border border-violet-200 bg-violet-50 p-3 sm:p-4">
					<p class="text-sm font-bold text-violet-900 mb-1 text-start">{{ __("Manager Authorization") }}</p>
					<p class="text-xs text-violet-700 mb-2 text-start">{{ managerReason }}</p>
					<input
						v-model="managerPin"
						type="password"
						inputmode="numeric"
						autocomplete="off"
						maxlength="6"
						class="w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-sm tracking-[0.35em] text-center"
						:placeholder="__('Enter Manager POS PIN')"
						@input="managerPin = managerPin.replace(/\D/g, '').slice(0, 6)"
						@keydown.enter.prevent="submit"
					/>
				</div>
				<div v-else class="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-start">
					<p class="text-sm font-bold text-emerald-900">{{ __("Manager PIN not required") }}</p>
					<p class="text-xs text-emerald-700 mt-1">{{ __("This POS Profile is configured to allow this return without manager PIN authorization.") }}</p>
				</div>

				<div v-if="errorMessage" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 text-start whitespace-pre-line">{{ errorMessage }}</div>

				<div class="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-1">
					<Button variant="subtle" :disabled="submitting" @click="show = false">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="submitting" :disabled="!canSubmit" @click="submit">
						{{ isExchangeCredit ? __("Create Exchange Credit") : __("Create Return") }}
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
import RetailItemPicker from "@/components/sale/RetailItemPicker.vue";
import { useToast } from "@/composables/useToast";
import { call } from "@/utils/apiWrapper";
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil, roundCurrency } from "@/utils/currency";
import { Button, Dialog, FeatherIcon } from "frappe-ui";
import { computed, nextTick, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, required: true },
	posOpeningShift: { type: String, required: true },
	currency: { type: String, default: DEFAULT_CURRENCY },
	customer: { type: [String, Object], default: null },
	settlementMode: { type: String, default: "refund" },
});

const emit = defineEmits(["update:modelValue", "return-created"]);
const { showSuccess } = useToast();

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});
const isExchangeCredit = computed(() => props.settlementMode === "exchange-credit");
const dialogTitle = computed(() => isExchangeCredit.value ? __("Exchange — Return Without Invoice") : __("Return Without Invoice"));
const selectedCustomer = ref(props.customer || null);
const customerName = computed(() => selectedCustomer.value?.name || selectedCustomer.value || "");
const customerDisplay = computed(
	() => selectedCustomer.value?.customer_name || selectedCustomer.value?.name || selectedCustomer.value || ""
);

const itemPickerRef = ref(null);
const showCustomerPicker = ref(false);
const items = ref([]);
const reason = ref("");
const refundType = ref("credit");
const cashMode = ref("");
const cashModes = ref([]);
const managerPin = ref("");
const submitting = ref(false);
const errorMessage = ref("");
const sellingPriceList = ref("");
const allowRateEdit = ref(false);
const requireManagerPinNoInvoice = ref(true);
const requireManagerPinCash = ref(true);
const requireManagerPinRateOverride = ref(true);

const estimatedTotal = computed(() => roundCurrency(items.value.reduce((sum, item) => sum + Number(item.qty || 0) * Number(item.rate || 0), 0)));
const hasRateOverride = computed(() => items.value.some((item) => isRateOverridden(item)));
const managerRequired = computed(() => {
	if (requireManagerPinNoInvoice.value) return true;
	if (!isExchangeCredit.value && refundType.value === "cash" && requireManagerPinCash.value) return true;
	if (hasRateOverride.value && requireManagerPinRateOverride.value) return true;
	return false;
});
const managerReason = computed(() => {
	const reasons = [];
	if (requireManagerPinNoInvoice.value) reasons.push(__("no-invoice return"));
	if (!isExchangeCredit.value && refundType.value === "cash" && requireManagerPinCash.value) reasons.push(__("cash refund"));
	if (hasRateOverride.value && requireManagerPinRateOverride.value) reasons.push(__("rate override"));
	return reasons.length
		? __("Manager POS PIN required for: {0}", [reasons.join(", ")])
		: __("Manager POS PIN is required by this POS Profile.");
});
const canSubmit = computed(() => {
	if (submitting.value || !customerName.value || items.value.length === 0 || !reason.value.trim()) return false;
	if (!isExchangeCredit.value && refundType.value === "cash" && !cashMode.value) return false;
	if (managerRequired.value && managerPin.value.length < 4) return false;
	return true;
});

function formatCurrency(amount) {
	return formatCurrencyUtil(Number(amount || 0), props.currency);
}
function itemKey(item) {
	return `${item.item_code}::${item.uom || item.stock_uom || ""}`;
}
function roundQty(value) {
	return Math.round((Number(value) || 0) * 1000000) / 1000000;
}
function isRateOverridden(item) {
	return Math.abs(Number(item?.rate || 0) - Number(item?.original_rate || 0)) > 0.000001;
}
function normalizeRate(item) {
	const rate = Number(item.rate);
	item.rate = Number.isFinite(rate) && rate >= 0 ? rate : Number(item.original_rate || 0);
}

function addReturnItem(item, qty = 1) {
	if (item?.has_serial_no || item?.has_batch_no) {
		errorMessage.value = __("Serialized/batched items require Return With Invoice so the original stock identity is preserved.");
		return;
	}
	errorMessage.value = "";
	const key = itemKey(item);
	const found = items.value.find((row) => row.key === key);
	const addQty = Math.max(Number(qty || 1), 0.001);
	if (found) {
		found.qty = roundQty(Number(found.qty || 0) + addQty);
		return;
	}
	const resolvedRate = Number(item.rate ?? item.price_list_rate ?? 0);
	items.value.push({
		...item,
		key,
		qty: addQty,
		rate: resolvedRate,
		original_rate: resolvedRate,
		uom: item.uom || item.stock_uom,
	});
}

async function repriceSelectedItems() {
	if (!items.value.length) return;
	for (const item of items.value) {
		try {
			const detail = await call("pos_next.api.retail_returns.get_return_item_details", {
				item_code: item.item_code,
				pos_profile: props.posProfile,
				customer: customerName.value || null,
				qty: Number(item.qty || 1),
				uom: item.uom || null,
			});
			const currentRate = Number(detail?.rate ?? detail?.price_list_rate ?? 0);
			item.rate = currentRate;
			item.original_rate = currentRate;
			item.price_list_rate = currentRate;
		} catch (error) {
			console.error("Could not re-price return item:", item.item_code, error);
		}
	}
}

async function handleCustomerSelected(customer) {
	selectedCustomer.value = customer || null;
	showCustomerPicker.value = false;
	errorMessage.value = "";
	await repriceSelectedItems();
	nextTick(() => itemPickerRef.value?.focusInput?.());
}

function normalizeQty(item) {
	const qty = Number(item.qty);
	item.qty = Number.isFinite(qty) && qty > 0 ? qty : 1;
}
function changeQty(item, delta) {
	item.qty = Math.max(0.001, roundQty(Number(item.qty || 1) + delta));
}
function removeItem(item) {
	items.value = items.value.filter((row) => row.key !== item.key);
}
function settlementClass(type) {
	const active = refundType.value === type;
	return [
		"rounded-xl border-2 p-3 transition-colors",
		active ? "border-blue-500 bg-blue-50 text-blue-800" : "border-gray-200 bg-white text-gray-700 hover:border-blue-300",
	];
}
function parseError(error) {
	if (!error) return __("Return failed");
	if (typeof error === "string") return error;
	if (error.message && typeof error.message === "string") return error.message;
	if (Array.isArray(error.messages) && error.messages.length) return error.messages.join("\n");
	return __("Return failed. Please review the details and try again.");
}

async function waitForCloseTeardown() {
	await nextTick();
	if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
		await new Promise((resolve) =>
			window.requestAnimationFrame(() => window.requestAnimationFrame(resolve))
		);
	}
}

async function loadOptions() {
	if (!props.posProfile) return;
	try {
		const data = await call("pos_next.api.retail_returns.get_no_invoice_return_options", { pos_profile: props.posProfile });
		cashModes.value = data?.cash_modes || [];
		if (cashModes.value.length === 1) cashMode.value = cashModes.value[0];
		sellingPriceList.value = data?.selling_price_list || "";
		allowRateEdit.value = Boolean(Number(data?.allow_user_to_edit_rate || 0));
		requireManagerPinNoInvoice.value = Boolean(Number(data?.require_manager_pin_no_invoice_return ?? 1));
		requireManagerPinCash.value = Boolean(Number(data?.require_manager_pin_cash_refund ?? 1));
		requireManagerPinRateOverride.value = Boolean(Number(data?.require_manager_pin_rate_override ?? 1));
	} catch (error) {
		console.error("Could not load no-invoice return options:", error);
		cashModes.value = [];
	}
}

async function submit() {
	if (!canSubmit.value) return;
	submitting.value = true;
	errorMessage.value = "";
	try {
		const payload = {
			pos_profile: props.posProfile,
			pos_opening_shift: props.posOpeningShift,
			customer: customerName.value,
			reason: reason.value.trim(),
			refund_type: isExchangeCredit.value ? "credit" : refundType.value,
			cash_mode: isExchangeCredit.value ? "" : cashMode.value,
			exchange_mode: isExchangeCredit.value ? 1 : 0,
			items: items.value.map((item) => ({
				item_code: item.item_code,
				qty: Number(item.qty),
				uom: item.uom,
				rate: Number(item.rate),
			})),
		};
		const result = await call("pos_next.api.retail_returns.create_no_invoice_return", {
			payload: JSON.stringify(payload),
			manager_pin: managerRequired.value ? managerPin.value : "",
		});

		// Close the completed return modal BEFORE notifying the parent. The parent
		// may immediately open the return print window, and leaving this frappe-ui
		// Dialog alive until after that handoff can strand its overlay/focus trap.
		// Emitting immediately after modelValue=false also lets ExchangeDialog mark
		// the return as completed before its close watcher can restore the source UI.
		show.value = false;
		// Let the standalone frappe-ui Dialog fully unmount before the parent opens
		// the return print. This fixes Customer Credit no-invoice returns leaving a
		// completed modal/overlay visible behind the print window.
		await waitForCloseTeardown();
		emit("return-created", result);
		showSuccess(__("Return {0} created successfully", [result?.name || ""]));
	} catch (error) {
		console.error("No-invoice return failed:", error);
		errorMessage.value = parseError(error);
	} finally {
		managerPin.value = "";
		submitting.value = false;
	}
}

function reset() {
	selectedCustomer.value = props.customer || null;
	showCustomerPicker.value = false;
	items.value = [];
	reason.value = "";
	refundType.value = "credit";
	cashMode.value = "";
	managerPin.value = "";
	errorMessage.value = "";
	sellingPriceList.value = "";
	allowRateEdit.value = false;
	requireManagerPinNoInvoice.value = true;
	requireManagerPinCash.value = true;
	requireManagerPinRateOverride.value = true;
}

watch(show, async (opened) => {
	if (!opened) return;
	reset();
	await loadOptions();
	nextTick(() => itemPickerRef.value?.focusInput?.());
});
watch(
	() => props.customer,
	(value) => {
		if (!show.value) selectedCustomer.value = value || null;
	}
);
</script>
