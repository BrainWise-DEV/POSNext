<template>
	<!-- Step 1: choose how the returned item is identified. -->
	<Dialog v-model="sourceDialogOpen" :options="{ title: __('Exchange — Return Source'), size: 'lg' }">
		<template #body-content>
			<div class="flex flex-col gap-3">
				<div class="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-start">
					<p class="text-sm font-bold text-emerald-900">{{ __('Two-stage exchange') }}</p>
					<p class="text-xs text-emerald-700 mt-1 leading-relaxed">
						{{ __('First create the return as Customer Credit. Then add replacement items and use the normal POS checkout. Payment Hub is only used for any final amount the customer still has to pay.') }}
					</p>
				</div>

				<button type="button" class="rounded-xl border-2 border-gray-200 bg-white p-4 text-start hover:border-blue-400 hover:bg-blue-50 transition-colors" @click="chooseSource('invoice')">
					<div class="flex items-start gap-3">
						<div class="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center"><FeatherIcon name="file-text" class="w-5 h-5" /></div>
						<div><p class="text-sm font-bold text-gray-900">{{ __('With Invoice') }}</p><p class="text-xs text-gray-500 mt-1">{{ __('Use the original invoice, remaining-returnable quantity, and invoice barcode validation.') }}</p></div>
					</div>
				</button>

				<button v-if="allowWithoutInvoice" type="button" class="rounded-xl border-2 border-gray-200 bg-white p-4 text-start hover:border-amber-400 hover:bg-amber-50 transition-colors" @click="chooseSource('no-invoice')">
					<div class="flex items-start gap-3">
						<div class="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center"><FeatherIcon name="shield" class="w-5 h-5" /></div>
						<div><p class="text-sm font-bold text-gray-900">{{ __('Without Invoice') }}</p><p class="text-xs text-gray-500 mt-1">{{ __('The return is valued using the current POS price list; manager PIN follows POS Settings.') }}</p></div>
					</div>
				</button>

				<div class="flex justify-end pt-1">
					<Button variant="subtle" @click="closeAll">{{ __('Cancel') }}</Button>
				</div>
			</div>
		</template>
	</Dialog>

	<ReturnInvoiceDialog
		v-model="withInvoiceOpen"
		:pos-profile="posProfile"
		:pos-opening-shift="posOpeningShift"
		:currency="currency"
		settlement-mode="exchange-credit"
		@return-created="handleReturnCreated"
	/>

	<NoInvoiceReturnDialog
		v-model="withoutInvoiceOpen"
		:pos-profile="posProfile"
		:pos-opening-shift="posOpeningShift"
		:currency="currency"
		:customer="customer"
		settlement-mode="exchange-credit"
		@return-created="handleReturnCreated"
	/>

	<!-- Step 2: replacement items. The actual invoice is created by the normal POS checkout. -->
	<Dialog v-model="replacementDialogOpen" :options="{ title: __('Exchange — Replacement Items'), size: '4xl' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
					<div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-start">
						<p class="text-xs text-gray-500">{{ __('Return Credit') }}</p>
						<p class="text-lg font-bold text-emerald-700 mt-1">{{ formatCurrency(returnCredit) }}</p>
						<p class="text-[11px] text-gray-500 mt-1 truncate">{{ returnResult?.name }}</p>
					</div>
					<div class="rounded-xl border border-gray-200 bg-gray-50 p-3 text-start">
						<p class="text-xs text-gray-500">{{ __('Replacement Estimate') }}</p>
						<p class="text-lg font-bold text-gray-900 mt-1">{{ formatCurrency(replacementTotal) }}</p>
						<p class="text-[11px] text-gray-500 mt-1">{{ __('Before final tax / offers recalculation') }}</p>
					</div>
					<div :class="netCardClass">
						<p class="text-xs opacity-75">{{ netLabel }}</p>
						<p class="text-lg font-bold mt-1">{{ formatCurrency(Math.abs(netEstimate)) }}</p>
						<p class="text-[11px] opacity-75 mt-1">{{ netHint }}</p>
					</div>
				</div>

				<div class="rounded-xl border border-blue-200 bg-blue-50 p-3 text-start">
					<p class="text-xs text-blue-800 leading-relaxed">
						{{ __('The return credit already exists. Replacement items below will be moved into the normal POS cart. Final pricing, promotions, tax, Customer Credit allocation, and any Payment Hub payment happen in normal checkout.') }}
					</p>
				</div>

				<RetailItemPicker
					ref="replacementPickerRef"
					:pos-profile="posProfile"
					:customer="returnCustomer"
					:title="__('Replacement Items')"
					@item-added="addReplacementItem"
				/>

				<div v-if="replacementItems.length" class="rounded-xl border border-gray-200 overflow-hidden">
					<div class="px-3 py-2 bg-gray-50 border-b border-gray-200 text-start">
						<p class="text-sm font-bold text-gray-800">{{ __('New Items') }}</p>
					</div>
					<div class="divide-y divide-gray-100 max-h-64 overflow-y-auto">
						<div v-for="item in replacementItems" :key="item.key" class="p-3 flex items-center gap-3">
							<div class="flex-1 min-w-0 text-start">
								<p class="text-sm font-semibold text-gray-900 truncate">{{ item.item_name }}</p>
								<p class="text-xs text-gray-500">{{ item.item_code }} · {{ formatCurrency(item.rate) }}/{{ item.uom }}</p>
							</div>
							<div class="flex items-center gap-1.5">
								<button type="button" class="w-8 h-8 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 font-bold" @click="changeQty(item, -1)">−</button>
								<input v-model.number="item.qty" type="number" min="0.001" step="1" class="w-16 h-8 rounded-lg border border-gray-300 text-center text-sm font-semibold" @change="normalizeQty(item)" />
								<button type="button" class="w-8 h-8 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 font-bold" @click="changeQty(item, 1)">+</button>
							</div>
							<div class="w-24 text-end">
								<p class="text-sm font-bold text-gray-900">{{ formatCurrency(item.qty * item.rate) }}</p>
								<button type="button" class="text-xs text-red-600 hover:text-red-700" @click="removeItem(item)">{{ __('Remove') }}</button>
							</div>
						</div>
					</div>
				</div>

				<div v-if="errorMessage" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 text-start">{{ errorMessage }}</div>

				<div class="flex flex-col-reverse sm:flex-row sm:justify-between gap-2 pt-1">
					<Button variant="subtle" @click="closeAfterCredit">{{ __('Close — Keep Credit') }}</Button>
					<Button variant="solid" :disabled="replacementItems.length === 0" @click="continueToCheckout">
						{{ __('Continue to POS Checkout') }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import NoInvoiceReturnDialog from "@/components/sale/NoInvoiceReturnDialog.vue";
import RetailItemPicker from "@/components/sale/RetailItemPicker.vue";
import ReturnInvoiceDialog from "@/components/sale/ReturnInvoiceDialog.vue";
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil, roundCurrency } from "@/utils/currency";
import { Button, Dialog, FeatherIcon } from "frappe-ui";
import { computed, nextTick, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, required: true },
	posOpeningShift: { type: String, required: true },
	currency: { type: String, default: DEFAULT_CURRENCY },
	customer: { type: [String, Object], default: null },
	allowWithoutInvoice: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "exchange-ready", "return-created"]);

const sourceDialogOpen = ref(false);
const withInvoiceOpen = ref(false);
const withoutInvoiceOpen = ref(false);
const replacementDialogOpen = ref(false);
const replacementPickerRef = ref(null);
const returnResult = ref(null);
const replacementItems = ref([]);
const errorMessage = ref("");
const closingAll = ref(false);
const returnHandoffInProgress = ref(false);

const returnCustomer = computed(
	() => returnResult.value?.customer || props.customer?.name || props.customer || null
);
const returnCredit = computed(() =>
	roundCurrency(
		Math.abs(
			Number(
				returnResult.value?.grand_total ??
					returnResult.value?.rounded_total ??
					returnResult.value?.return_total ??
					0
			)
		)
	)
);
const replacementTotal = computed(() =>
	roundCurrency(
		replacementItems.value.reduce(
			(sum, item) => sum + Number(item.qty || 0) * Number(item.rate || 0),
			0
		)
	)
);
const netEstimate = computed(() => roundCurrency(replacementTotal.value - returnCredit.value));
const netLabel = computed(() => {
	if (netEstimate.value > 0.0005) return __("Estimated Customer Pays");
	if (netEstimate.value < -0.0005) return __("Estimated Credit Remaining");
	return __("Estimated Even Exchange");
});
const netHint = computed(() => {
	if (netEstimate.value > 0.0005) return __("Final difference is settled at checkout");
	if (netEstimate.value < -0.0005) return __("Unused Customer Credit remains available");
	return __("Final tax / offers may still change the total");
});
const netCardClass = computed(() => [
	"rounded-xl border p-3 text-start",
	netEstimate.value > 0.0005
		? "border-blue-200 bg-blue-50 text-blue-900"
		: netEstimate.value < -0.0005
		? "border-emerald-200 bg-emerald-50 text-emerald-900"
		: "border-gray-200 bg-gray-50 text-gray-900",
]);

function formatCurrency(amount) {
	return formatCurrencyUtil(Number(amount || 0), props.currency);
}
function itemKey(item) {
	return `${item.item_code}::${item.uom || item.stock_uom || ""}::${item.warehouse || ""}`;
}
function roundQty(value) {
	return Math.round((Number(value) || 0) * 1000000) / 1000000;
}
function resetAll() {
	sourceDialogOpen.value = false;
	withInvoiceOpen.value = false;
	withoutInvoiceOpen.value = false;
	replacementDialogOpen.value = false;
	returnResult.value = null;
	replacementItems.value = [];
	errorMessage.value = "";
}
async function waitForDialogHandoff() {
	await nextTick();
	if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
		await new Promise((resolve) =>
			window.requestAnimationFrame(() => window.requestAnimationFrame(resolve))
		);
	}
}
function closeAll() {
	closingAll.value = true;
	resetAll();
	emit("update:modelValue", false);
	nextTick(() => {
		closingAll.value = false;
	});
}
async function chooseSource(source) {
	if (source === "no-invoice" && !props.allowWithoutInvoice) return;
	// Never close one frappe-ui Dialog and open the next in the same render tick.
	// Doing so can leave the new modal behind the previous overlay/focus trap.
	sourceDialogOpen.value = false;
	withInvoiceOpen.value = false;
	withoutInvoiceOpen.value = false;
	await waitForDialogHandoff();
	if (!props.modelValue || closingAll.value) return;
	if (source === "invoice") withInvoiceOpen.value = true;
	else withoutInvoiceOpen.value = true;
}
async function handleReturnCreated(result) {
	// Child return dialogs now close themselves before emitting success. Keep an
	// explicit handoff guard so their v-model close watcher cannot restore the
	// Return Source dialog while we are moving to replacement items / printing.
	returnHandoffInProgress.value = true;
	returnResult.value = result || {};

	// Tear down the return-source dialog BEFORE bubbling the success event to
	// POSSale. POSSale may immediately open the browser/silent print flow, and
	// browser printing can block JavaScript. Closing first prevents the completed
	// Return With/Without Invoice window and its overlay from remaining behind the
	// replacement-item/payment dialogs.
	withInvoiceOpen.value = false;
	withoutInvoiceOpen.value = false;
	sourceDialogOpen.value = false;
	await waitForDialogHandoff();
	if (!props.modelValue || closingAll.value) return;

	// Bubble only after the completed source modal is fully gone. The outer
	// ExchangeDialog stays alive so replacement items can be staged normally.
	emit("return-created", returnResult.value);

	if (!returnCustomer.value) {
		errorMessage.value = __("The return was created, but its customer could not be resolved. Keep the return credit and select the customer manually before using it.");
	}
	if (returnCredit.value <= 0) {
		errorMessage.value = __("The return was created, but its credit amount could not be read. Verify the return invoice before continuing.");
	}

	if (!props.modelValue || closingAll.value) {
		returnHandoffInProgress.value = false;
		return;
	}
	replacementDialogOpen.value = true;
	await nextTick();
	replacementPickerRef.value?.focusInput?.();
	returnHandoffInProgress.value = false;
}
function addReplacementItem(item, qty = 1) {
	if (item?.has_serial_no || item?.has_batch_no) {
		errorMessage.value = __(
			"Serialized/batched replacement items are not staged by this exchange screen in v1.0. Keep the return credit and add the replacement through the normal POS item flow."
		);
		return;
	}
	errorMessage.value = "";
	const key = itemKey(item);
	const found = replacementItems.value.find((row) => row.key === key);
	const addQty = Math.max(Number(qty || 1), 0.001);
	if (found) {
		found.qty = roundQty(Number(found.qty || 0) + addQty);
		return;
	}
	replacementItems.value.push({
		...item,
		key,
		qty: addQty,
		rate: Number(item.rate ?? item.price_list_rate ?? 0),
		uom: item.uom || item.stock_uom,
	});
}
function normalizeQty(item) {
	const qty = Number(item.qty);
	item.qty = Number.isFinite(qty) && qty > 0 ? qty : 1;
}
function changeQty(item, delta) {
	item.qty = Math.max(0.001, roundQty(Number(item.qty || 1) + delta));
}
function removeItem(item) {
	replacementItems.value = replacementItems.value.filter((row) => row.key !== item.key);
}
function closeAfterCredit() {
	// No rollback is attempted here: the return invoice is already a valid audit
	// document and its outstanding amount remains available as Customer Credit.
	closeAll();
}
function continueToCheckout() {
	if (!returnResult.value || replacementItems.value.length === 0) return;
	if (!returnCustomer.value) {
		errorMessage.value = __("Customer is required before exchange checkout.");
		return;
	}
	emit("exchange-ready", {
		customer: returnCustomer.value,
		customer_name: returnResult.value?.customer_name || returnCustomer.value,
		return_invoice: returnResult.value?.name,
		return_credit: returnCredit.value,
		items: replacementItems.value.map((item) => ({ ...item, quantity: Number(item.qty || 1) })),
		net_estimate: netEstimate.value,
	});
	closeAll();
}

watch(
	() => props.modelValue,
	async (opened) => {
		if (opened) {
			closingAll.value = false;
			resetAll();
			await waitForDialogHandoff();
			if (props.modelValue && !closingAll.value) sourceDialogOpen.value = true;
		} else {
			resetAll();
		}
	}
);

async function restoreSourceDialogIfNeeded() {
	if (
		closingAll.value ||
		returnHandoffInProgress.value ||
		!props.modelValue ||
		returnResult.value
	) return;
	await waitForDialogHandoff();
	if (
		!closingAll.value &&
		!returnHandoffInProgress.value &&
		props.modelValue &&
		!returnResult.value &&
		!withInvoiceOpen.value &&
		!withoutInvoiceOpen.value &&
		!replacementDialogOpen.value
	) {
		sourceDialogOpen.value = true;
	}
}

watch(withInvoiceOpen, (opened, wasOpen) => {
	if (!opened && wasOpen) restoreSourceDialogIfNeeded();
});
watch(withoutInvoiceOpen, (opened, wasOpen) => {
	if (!opened && wasOpen) restoreSourceDialogIfNeeded();
});
</script>
