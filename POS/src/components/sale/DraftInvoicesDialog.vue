<template>
	<!-- Main Dialog -->
	<Dialog v-model="show" :options="{ title: __('Draft Invoices'), size: 'lg' }">
		<template #body-content>
			<div class="flex flex-col gap-3">
				<!-- Empty State -->
				<div v-if="drafts.length === 0" class="text-center py-8">
					<div
						class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3"
					>
						<svg
							class="h-8 w-8 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
							/>
						</svg>
					</div>
					<p class="text-sm font-medium text-gray-900">{{ __("No held invoices") }}</p>
					<p class="text-xs text-gray-500 mt-1">
						{{ __("Hold an invoice to finish it later") }}
					</p>
				</div>

				<!-- Drafts List -->
				<div v-else class="flex flex-col gap-2 max-h-96 overflow-y-auto">
					<div
						v-for="draft in drafts"
						:key="draft.draft_id"
						:class="[
							'bg-white border rounded-lg p-3 transition-all',
							isOpen(draft)
								? 'border-blue-300 bg-blue-50 cursor-default'
								: 'border-gray-200 hover:border-blue-400 cursor-pointer',
						]"
						:aria-disabled="isOpen(draft)"
						@click="!isOpen(draft) && $emit('load-draft', draft)"
					>
						<div class="flex items-start justify-between gap-2 mb-2">
							<!-- Customer · time · total -->
							<div class="flex-1 min-w-0">
								<h4 class="text-sm font-semibold text-gray-900 flex flex-wrap gap-x-1.5">
									<span dir="auto" class="truncate">{{ draftCustomer(draft) }}</span>
									<span class="text-gray-400">·</span>
									<span dir="ltr">{{ formatDateTime(draft.created_at) }}</span>
									<span class="text-gray-400">·</span>
									<span class="text-blue-700 tabular-nums">{{
										formatCurrency(calculateTotal(draft.items))
									}}</span>
								</h4>
								<p
									v-if="isOpen(draft)"
									class="text-xs font-semibold text-blue-700 mt-0.5"
								>
									{{ __("Open in the cart now") }}
								</p>
							</div>
							<div class="flex items-center gap-1 flex-shrink-0">
								<button
									v-if="props.allowPrintDraftInvoices"
									@click.stop="handlePrintDraft(draft)"
									class="w-10 h-10 flex items-center justify-center rounded-md text-gray-500 hover:text-blue-700 hover:bg-blue-50"
									:title="__('Print draft')"
									:aria-label="__('Print draft')"
								>
									<FeatherIcon name="printer" class="w-4 h-4" />
								</button>
								<button
									@click.stop="handleDeleteDraft(draft.draft_id)"
									class="w-10 h-10 flex items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:text-red-700 hover:border-red-300 hover:bg-red-50"
									:title="__('Delete held invoice')"
									:aria-label="__('Delete held invoice')"
								>
									<FeatherIcon name="trash-2" class="w-4 h-4" />
								</button>
							</div>
						</div>

						<!-- Items Preview -->
						<div class="flex items-center justify-between text-xs">
							<span class="text-gray-600">
								{{
									draft.items?.length === 1
										? __("1 item")
										: __("{0} items", [draft.items?.length || 0])
								}}
							</span>
						</div>

						<!-- Items List (condensed) -->
						<div
							v-if="draft.items && draft.items.length > 0"
							class="mt-2 pt-2 border-t border-gray-100"
						>
							<div class="flex flex-wrap gap-1">
								<span
									v-for="(item, idx) in draft.items.slice(0, 3)"
									:key="idx"
									dir="auto"
									class="text-[11px] bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded"
								>
									{{ item.item_name }} ({{ item.quantity || item.qty }})
								</span>
								<span
									v-if="draft.items.length > 3"
									class="text-[10px] text-gray-500 px-1.5 py-0.5"
								>
									{{ __("+{0} more", [draft.items.length - 3]) }}
								</span>
							</div>
						</div>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-between items-center w-full">
				<Button
					v-if="drafts.length > 0"
					variant="subtle"
					theme="red"
					@click="showClearAllDialog = true"
				>
					{{ __("Clear All") }}
				</Button>
				<Button variant="subtle" @click="show = false">
					{{ __("Close") }}
				</Button>
			</div>
		</template>
	</Dialog>

	<!-- Delete Single Draft Confirmation -->
	<Dialog v-model="showDeleteDialog" :options="{ title: __('Delete held invoice?'), size: 'xs' }">
		<template #body-content>
			<div class="py-3">
				<p class="text-sm text-gray-600">
					{{ __("Permanently delete this held invoice?") }}
				</p>
			</div>
		</template>
		<template #actions>
			<div class="flex gap-2 w-full">
				<Button class="flex-1" variant="subtle" @click="showDeleteDialog = false">
					{{ __("Cancel") }}
				</Button>
				<Button class="flex-1" variant="solid" theme="red" @click="confirmDeleteDraft">
					{{ __("Delete") }}
				</Button>
			</div>
		</template>
	</Dialog>

	<!-- Clear All Drafts Confirmation -->
	<Dialog v-model="showClearAllDialog" :options="{ title: __('Clear All Drafts?'), size: 'xs' }">
		<template #body-content>
			<div class="py-3">
				<p class="text-sm text-gray-600">
					{{ __("Permanently delete all {0} draft invoices?", [drafts.length]) }}
				</p>
			</div>
		</template>
		<template #actions>
			<div class="flex gap-2 w-full">
				<Button class="flex-1" variant="subtle" @click="showClearAllDialog = false">
					{{ __("Cancel") }}
				</Button>
				<Button class="flex-1" variant="solid" theme="red" @click="confirmClearAll">
					{{ __("Clear All") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import {
	DEFAULT_CURRENCY,
	DEFAULT_LOCALE,
	formatCurrency as formatCurrencyUtil,
	roundCurrency,
} from "@/utils/currency";
import { clearAllDrafts, deleteDraft, getAllDrafts } from "@/utils/draftManager";
import { printInvoiceCustom } from "@/utils/printInvoice";
import { useToast } from "@/composables/useToast";
import { usePOSShiftStore } from "@/stores/posShift";
import { usePOSCartStore } from "@/stores/posCart";
import { usePOSDraftsStore } from "@/stores/posDrafts";
import { Button, Dialog, FeatherIcon } from "frappe-ui";
import { onMounted, ref, watch } from "vue";

const { showSuccess, showError } = useToast();
const shiftStore = usePOSShiftStore();
const cartStore = usePOSCartStore();
const draftsStore = usePOSDraftsStore();

const props = defineProps({
	modelValue: Boolean,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	allowPrintDraftInvoices: {
		type: Boolean,
		default: false,
	},
});

const emit = defineEmits(["update:modelValue", "load-draft", "drafts-updated"]);

const show = ref(props.modelValue);
const drafts = ref([]);
const showDeleteDialog = ref(false);
const showClearAllDialog = ref(false);
const draftToDelete = ref(null);

watch(
	() => props.modelValue,
	(val) => {
		show.value = val;
		if (val) {
			loadDrafts();
		}
	}
);

watch(show, (val) => {
	emit("update:modelValue", val);
});

onMounted(() => {
	loadDrafts();
});

async function loadDrafts() {
	try {
		drafts.value = await getAllDrafts();
	} catch (error) {
		console.error("Error loading drafts:", error);
		showError(__("Failed to load draft invoices"));
	}
}

// The held invoice loaded in the cart can't be loaded a second time
function isOpen(draft) {
	return draft.draft_id === cartStore.currentDraftId;
}

function draftCustomer(draft) {
	return draft.customer?.customer_name || draft.customer?.name || draft.customer || __("Walk-in");
}

function handlePrintDraft(draft) {
	if (!props.allowPrintDraftInvoices) {
		return;
	}

	try {
		const invoiceData = {
			name: draft.draft_id,
			company: shiftStore.profileCompany,
			items: draft.items,
			payments: [],
			grand_total: calculateTotal(draft.items),
			posting_date: draft.created_at,
			customer_name: draft.customer?.customer_name || draft.customer?.name || draft.customer,
			status: "Draft",
			header: "Draft",
			footer: "الفاتورة لم يتم تسجيلها في حسابات الجهة، وبالتالي لا يُعتد بها، ولا تتحمل الجهة أي مسؤولية عن أي أضرار قد تنتج عنها.",
		};
		printInvoiceCustom(invoiceData);
	} catch (error) {
		console.error("Error printing draft:", error);
		showError(__("Failed to print draft"));
	}
}

function handleDeleteDraft(draftId) {
	draftToDelete.value = draftId;
	showDeleteDialog.value = true;
}

async function confirmDeleteDraft() {
	try {
		const draft = drafts.value.find((d) => d.draft_id === draftToDelete.value);
		await deleteDraft(draftToDelete.value);
		// The draft loaded in the cart keeps its serials in the cart
		if (draft?.draft_id !== cartStore.currentDraftId) draftsStore.returnDraftSerials(draft);
		await loadDrafts();
		showDeleteDialog.value = false;
		draftToDelete.value = null;

		// Notify parent to update count
		emit("drafts-updated");

		showSuccess(__("Draft invoice deleted"));
	} catch (error) {
		console.error("Error deleting draft:", error);
		showError(__("Failed to delete draft"));
	}
}

async function confirmClearAll() {
	try {
		await clearAllDrafts();
		drafts.value
			.filter((d) => d.draft_id !== cartStore.currentDraftId)
			.forEach((d) => draftsStore.returnDraftSerials(d));
		await loadDrafts();
		showClearAllDialog.value = false;

		// Notify parent to update count
		emit("drafts-updated");

		showSuccess(__("All draft invoices deleted"));
	} catch (error) {
		console.error("Error clearing drafts:", error);
		showError(__("Failed to clear drafts"));
	}
}

function formatDateTime(dateStr) {
	const date = new Date(dateStr);
	return date.toLocaleString(DEFAULT_LOCALE, {
		month: "short",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

function calculateTotal(items) {
	if (!items || items.length === 0) return 0;
	return roundCurrency(
		items.reduce((sum, item) => {
			// A held line's amount is its net total after offers and coupons; older drafts lack it
			if (typeof item.amount === "number") return sum + roundCurrency(item.amount);
			const qty = item.quantity || item.qty || 1;
			const rate = item.rate || 0;
			return sum + roundCurrency(qty * roundCurrency(rate));
		}, 0)
	);
}
</script>
