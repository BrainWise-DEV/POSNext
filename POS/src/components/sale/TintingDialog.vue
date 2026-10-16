<template>
	<Dialog v-model="show" :options="{ title: __('Tinta'), size: 'lg' }">
		<template #body-content>
			<div v-if="item" class="flex flex-col gap-3">
				<div class="text-sm text-gray-700 text-start">
					<span class="font-bold">{{ item.item_name }}</span>
					<span class="text-gray-500"> · {{ item.warehouse }}</span>
				</div>

				<label class="flex flex-col gap-1 text-sm text-start">
					<span class="font-medium text-gray-700">{{ __("No. Job Mesin") }}</span>
					<input
						v-model="job"
						type="text"
						class="h-9 border border-gray-300 rounded px-2"
						data-test="tinting-job"
					/>
				</label>

				<label class="flex flex-col gap-1 text-sm text-start">
					<span class="font-medium text-gray-700">{{ __("Harga Jual") }}</span>
					<input
						:value="rate"
						type="text"
						inputmode="decimal"
						:readonly="!canEditRate"
						class="h-9 text-end font-semibold border border-gray-300 rounded px-2"
						:class="canEditRate ? 'bg-white' : 'bg-gray-100 cursor-not-allowed'"
						data-test="tinting-rate"
						@input="setRate"
					/>
					<span v-if="!canEditRate" class="text-xs text-gray-500">{{
						__("Harga jual item ini tidak bisa diubah (bukan item open price).")
					}}</span>
				</label>

				<p class="text-xs text-gray-500 text-start">
					{{
						__(
							"Isi HPP tinta dari layar mesin. HPP tidak menambah harga jual dan tidak dicetak di struk; kosong atau 0 tidak disimpan."
						)
					}}
				</p>

				<div
					v-if="groups.length || items.length"
					class="max-h-80 overflow-y-auto border border-gray-200 rounded divide-y divide-gray-100"
				>
					<!-- Gelondongan: one HPP for every tinta of the group, or per tinta below it -->
					<div v-for="group in groups" :key="group.addon_group">
						<div class="flex items-center gap-2 px-2 py-1.5 bg-gray-50">
							<span class="flex-1 min-w-0 text-sm font-semibold text-start truncate">
								{{ group.addon_group }}
								<span class="text-xs font-normal text-gray-400">{{
									__("Gelondongan")
								}}</span>
							</span>
							<input
								:value="headerLocked(group) ? '' : group.amount"
								type="text"
								inputmode="decimal"
								:disabled="headerLocked(group)"
								:aria-label="__('HPP tinta')"
								class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2 disabled:bg-gray-100"
								@input="setAmount(group, $event)"
							/>
						</div>
						<div
							v-for="row in group.members"
							:key="row.item_code"
							class="flex items-center gap-2 ps-6 pe-2 py-1.5"
						>
							<span class="flex-1 min-w-0 text-sm text-start truncate">
								{{ row.item_name }}
								<span class="text-xs text-gray-400">{{ row.item_code }}</span>
							</span>
							<input
								:value="row.amount"
								type="text"
								inputmode="decimal"
								:disabled="amountOf(group) > 0"
								:aria-label="__('HPP tinta')"
								class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2 disabled:bg-gray-100"
								@input="setAmount(row, $event)"
							/>
						</div>
					</div>

					<div
						v-for="row in items"
						:key="row.item_code"
						class="flex items-center gap-2 px-2 py-1.5"
					>
						<span class="flex-1 min-w-0 text-sm text-start truncate">
							{{ row.item_name }}
							<span class="text-xs text-gray-400">{{ row.item_code }}</span>
						</span>
						<input
							:value="row.amount"
							type="text"
							inputmode="decimal"
							:aria-label="__('HPP tinta')"
							class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2"
							@input="setAmount(row, $event)"
						/>
					</div>
				</div>
				<p v-else class="text-sm text-gray-500 text-start">
					{{ __("No add on available for this item in this warehouse.") }}
				</p>

				<div class="flex items-center justify-between text-sm">
					<span class="text-gray-600">{{ __("Total HPP tinta") }}</span>
					<span class="font-bold" data-test="tinting-total">{{
						formatCurrency(selectedTotal)
					}}</span>
				</div>
				<p v-if="error" class="text-xs text-red-600 text-start" data-test="tinting-error">
					{{ error }}
				</p>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-between gap-2">
				<Button v-if="item?.tinting" variant="subtle" theme="red" @click="remove">
					{{ __("Hapus Tinta") }}
				</Button>
				<div class="flex gap-2 ms-auto">
					<Button variant="subtle" @click="show = false">{{ __("Cancel") }}</Button>
					<Button theme="blue" variant="solid" @click="save">{{ __("Save") }}</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { formatAmountInput, parseAmountInput } from "@/utils/amountInput";
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { JENIS_TINTA, addonKey, getAvailableAddons, isOpenPriceItem } from "@/utils/itemAddons";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

/**
 * Tinta of a tinted base: the machine's job number plus the HPP of the tinta it
 * used, per tinta or gelondongan per group as on the machine's screen. Only the
 * total reaches the invoice (custom_hpp_tinta); the per tinta detail comes from
 * the machine's own export later. The selling price of an open price base is
 * set here too, emitted as the second argument of "save" (null = unchanged).
 */
const props = defineProps({
	modelValue: Boolean,
	item: { type: Object, default: null },
	currency: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue", "save"]);

const show = ref(props.modelValue);
const rate = ref("");
const job = ref("");
const error = ref("");
const groups = ref([]);
const items = ref([]);

watch(
	() => props.modelValue,
	(value) => {
		show.value = value;
		if (value) loadRows();
	}
);
watch(show, (value) => emit("update:modelValue", value));

// Same rule as EditItemDialog for an open price item: locked while a promotion applies
const canEditRate = computed(() => {
	const item = props.item;
	if (!item || item.is_free_item || !isOpenPriceItem(item.item_code)) return false;
	const rules = item.pricing_rules;
	return !(Array.isArray(rules) ? rules.length : String(rules || "").trim());
});

function setRate(event) {
	rate.value = formatAmountInput(event.target.value);
	event.target.value = rate.value;
}

function amountOf(row) {
	return parseAmountInput(row.amount);
}

function setAmount(row, event) {
	row.amount = formatAmountInput(event.target.value);
	event.target.value = row.amount;
}

/** A group HPP is replaced by its members' HPP once any of them is filled. */
function headerLocked(group) {
	return group.members.some((row) => amountOf(row) > 0);
}

function loadRows() {
	error.value = "";
	rate.value = formatAmountInput(String(props.item?.rate ?? ""));
	const tinting = props.item?.tinting;
	job.value = tinting?.job || "";
	const current = new Map(
		(tinting?.tinta || []).map((a) => [addonKey(a), formatAmountInput(String(a.amount))])
	);
	const available = getAvailableAddons(props.item, JENIS_TINTA);
	const offered = new Set(available.groups);

	const rows = available.items.map((addon) => ({
		...addon,
		amount: current.get(addonKey(addon)) ?? "",
	}));
	groups.value = available.groups.map((group) => ({
		addon_group: group,
		amount: current.get(addonKey({ addon_group: group })) ?? "",
		members: rows.filter((row) => row.addon_group === group),
	}));
	items.value = rows.filter((row) => !offered.has(row.addon_group));

	// A line loaded back from an order or draft only kept the total
	if (tinting && !tinting.tinta?.length) {
		const first = groups.value[0] || items.value[0];
		if (first) first.amount = formatAmountInput(String(tinting.hpp_tinta));
	}
}

function selectedTinta() {
	const out = [];
	for (const group of groups.value) {
		if (headerLocked(group)) {
			for (const row of group.members) {
				if (amountOf(row) > 0) out.push(row);
			}
		} else if (amountOf(group) > 0) {
			out.push({
				item_code: null,
				addon_group: group.addon_group,
				item_name: group.addon_group,
				amount: group.amount,
			});
		}
	}
	for (const row of items.value) {
		if (amountOf(row) > 0) out.push(row);
	}
	return out.map((row) => ({
		item_code: row.item_code,
		addon_group: row.addon_group || null,
		item_name: row.item_name,
		amount: amountOf(row),
	}));
}

const selectedTotal = computed(() => selectedTinta().reduce((sum, row) => sum + row.amount, 0));

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

function save() {
	const code = String(job.value || "").trim();
	const tinta = selectedTinta();
	if (!code || !tinta.length) {
		error.value = __("No. job mesin dan HPP tinta (lebih dari 0) wajib diisi.");
		return;
	}
	const newRate = parseAmountInput(rate.value);
	if (canEditRate.value && newRate <= 0) {
		error.value = __("Harga jual harus lebih dari 0.");
		return;
	}
	const rateChanged = canEditRate.value && newRate !== Number(props.item.rate);
	emit("save", { job: code, hpp_tinta: selectedTotal.value, tinta }, rateChanged ? newRate : null);
	show.value = false;
}

function remove() {
	emit("save", null);
	show.value = false;
}
</script>
