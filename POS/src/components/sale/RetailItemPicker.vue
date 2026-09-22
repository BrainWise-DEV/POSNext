<template>
	<div class="rounded-xl border border-gray-200 bg-white p-3 sm:p-4">
		<div class="flex items-center justify-between gap-3 mb-3">
			<div class="text-start">
				<h4 class="text-sm font-bold text-gray-900">{{ title }}</h4>
				<p class="text-xs text-gray-500 mt-0.5">
					{{ __("Scan a barcode or search by item code/name") }}
				</p>
			</div>
			<span
				v-if="status.message"
				:class="[
					'text-[11px] font-semibold px-2 py-1 rounded-full max-w-[50%] truncate',
					status.type === 'error'
						? 'bg-red-50 text-red-700'
						: status.type === 'success'
						? 'bg-emerald-50 text-emerald-700'
						: 'bg-blue-50 text-blue-700',
				]"
			>
				{{ status.message }}
			</span>
		</div>

		<div class="relative">
			<FeatherIcon
				name="maximize"
				class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
			/>
			<input
				ref="inputRef"
				v-model="query"
				type="text"
				autocomplete="off"
				:placeholder="placeholder"
				class="w-full ps-10 pe-10 py-2.5 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
				@input="onInput"
				@keydown.enter.prevent="scanExact"
				@keydown.escape.prevent="clearSearch"
			/>
			<FeatherIcon
				v-if="busy"
				name="loader"
				class="absolute end-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500 animate-spin"
			/>
			<button
				v-else-if="query"
				type="button"
				class="absolute end-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
				@click="clearSearch"
			>
				<FeatherIcon name="x" class="w-4 h-4" />
			</button>
		</div>

		<div
			v-if="results.length > 0"
			class="mt-2 max-h-56 overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-100"
		>
			<button
				v-for="row in results"
				:key="row.item_code"
				type="button"
				class="w-full px-3 py-2.5 text-start hover:bg-blue-50 transition-colors flex items-center justify-between gap-3"
				@click="selectSearchResult(row)"
			>
				<div class="min-w-0">
					<p class="text-sm font-semibold text-gray-900 truncate">{{ row.item_name }}</p>
					<p class="text-xs text-gray-500 truncate">{{ row.item_code }}</p>
				</div>
				<span class="text-xs text-blue-600 font-semibold">{{ __("Add") }}</span>
			</button>
		</div>

		<div v-if="query.trim().length >= 2 && !busy && searched && results.length === 0" class="mt-2 text-xs text-gray-500 text-start">
			{{ __("No matching items") }}
		</div>
	</div>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { QueuedMutex } from "@/utils/mutex";
import { FeatherIcon } from "frappe-ui";
import { nextTick, onUnmounted, reactive, ref, watch } from "vue";

const props = defineProps({
	posProfile: { type: String, required: true },
	customer: { type: [String, Object], default: null },
	title: { type: String, default: () => __("Add Item") },
	placeholder: {
		type: String,
		default: () => __("Scan barcode or type item code/name..."),
	},
	autoFocus: { type: Boolean, default: true },
});

const emit = defineEmits(["item-added"]);

const inputRef = ref(null);
const query = ref("");
const results = ref([]);
const busy = ref(false);
const searched = ref(false);
const status = reactive({ type: "", message: "" });
const scanQueue = new QueuedMutex({ timeout: 10000, name: "RetailReturnItemPicker" });
let searchTimer = null;
let statusTimer = null;
let searchGeneration = 0;

const customerName = () => props.customer?.name || props.customer || null;

function focusInput() {
	if (!props.autoFocus) return;
	nextTick(() => inputRef.value?.focus());
}

function setStatus(type, message) {
	status.type = type;
	status.message = message;
	if (statusTimer) clearTimeout(statusTimer);
	statusTimer = setTimeout(() => {
		status.message = "";
		status.type = "";
	}, 2500);
}

function clearSearch() {
	if (searchTimer) clearTimeout(searchTimer);
	query.value = "";
	results.value = [];
	searched.value = false;
	focusInput();
}

function normalizeItem(detail) {
	return {
		...detail,
		item_code: detail.item_code,
		item_name: detail.item_name || detail.item_code,
		uom: detail.uom || detail.stock_uom,
		warehouse: detail.warehouse,
		rate: Number(detail.rate ?? detail.price_list_rate ?? 0),
		price_list_rate: Number(detail.price_list_rate ?? detail.rate ?? 0),
		conversion_factor: Number(detail.conversion_factor || 1),
		actual_qty: Number(detail.actual_qty ?? detail.stock_qty ?? 0),
	};
}

async function addExactBarcode(barcode) {
	// First resolve barcode / item code using the normal POS barcode engine so
	// weighted barcodes and barcode-specific UOMs keep working. Then fetch the
	// authoritative current POS selling price through the return API.
	const resolved = await call("pos_next.api.items.search_by_barcode", {
		barcode,
		pos_profile: props.posProfile,
	});
	if (!resolved?.item_code) throw new Error(__("Item not found"));

	const resolvedQty = Number(resolved.resolved_qty || 1);
	const detail = await call("pos_next.api.retail_returns.get_return_item_details", {
		item_code: resolved.item_code,
		pos_profile: props.posProfile,
		customer: customerName(),
		qty: resolvedQty,
		uom: resolved.uom || resolved.stock_uom || null,
	});

	const item = normalizeItem({ ...resolved, ...detail });
	emit("item-added", item, resolvedQty);
	setStatus("success", __("Added {0} · {1}", [item.item_code, formatRate(item.rate)]));
}

function formatRate(rate) {
	const value = Number(rate || 0);
	return Number.isFinite(value) ? value.toFixed(3) : "0.000";
}

function scanExact() {
	const barcode = query.value.trim();
	if (!barcode) return;
	query.value = "";
	results.value = [];
	searched.value = false;
	focusInput();

	scanQueue.withLock(async () => {
		busy.value = true;
		try {
			await addExactBarcode(barcode);
		} catch (error) {
			console.error("Retail item scan failed:", error);
			setStatus("error", __("Item not found: {0}", [barcode]));
		} finally {
			busy.value = false;
			focusInput();
		}
	});
}

async function runSearch(value, generation) {
	busy.value = true;
	try {
		const rows = await call("pos_next.api.retail_returns.search_return_items", {
			search_term: value,
			pos_profile: props.posProfile,
			limit: 20,
		});
		if (generation !== searchGeneration) return;
		results.value = Array.isArray(rows) ? rows : [];
		searched.value = true;
	} catch (error) {
		console.error("Return item search failed:", error);
		if (generation === searchGeneration) {
			results.value = [];
			searched.value = true;
			setStatus("error", __("Item search failed"));
		}
	} finally {
		if (generation === searchGeneration) busy.value = false;
	}
}

function onInput() {
	if (searchTimer) clearTimeout(searchTimer);
	const value = query.value.trim();
	searchGeneration += 1;
	const generation = searchGeneration;
	if (value.length < 2) {
		results.value = [];
		searched.value = false;
		busy.value = false;
		return;
	}
	searchTimer = setTimeout(() => runSearch(value, generation), 250);
}

async function selectSearchResult(row) {
	if (!row?.item_code || busy.value) return;
	busy.value = true;
	try {
		const detail = await call("pos_next.api.retail_returns.get_return_item_details", {
			item_code: row.item_code,
			pos_profile: props.posProfile,
			customer: customerName(),
			qty: 1,
		});
		const item = normalizeItem(detail || row);
		emit("item-added", item, 1);
		setStatus("success", __("Added {0}", [item.item_code]));
		clearSearch();
	} catch (error) {
		console.error("Return item details failed:", error);
		setStatus("error", __("Could not add {0}", [row.item_code]));
	} finally {
		busy.value = false;
		focusInput();
	}
}

watch(
	() => props.posProfile,
	() => clearSearch()
);

onUnmounted(() => {
	if (searchTimer) clearTimeout(searchTimer);
	if (statusTimer) clearTimeout(statusTimer);
});

defineExpose({ focusInput, clearSearch });
</script>
