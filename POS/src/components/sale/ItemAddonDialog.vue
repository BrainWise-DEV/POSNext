<template>
	<Dialog v-model="show" :options="{ title: __('Add On'), size: 'lg' }">
		<template #body-content>
			<div v-if="item" class="flex flex-col gap-3">
				<div class="text-sm text-gray-700 text-start">
					<span class="font-bold">{{ item.item_name }}</span>
					<span class="text-gray-500"> · {{ item.warehouse }}</span>
				</div>

				<Input
					v-model="search"
					type="text"
					:placeholder="__('Search add on...')"
					class="w-full"
				/>

				<p class="text-xs text-gray-500 text-start">
					{{ __("Isi harga untuk add on yang dipilih. Harga kosong atau 0 tidak disimpan.") }}
				</p>

				<div
					v-if="filteredGroups.length || filteredItems.length"
					class="max-h-80 overflow-y-auto border border-gray-200 rounded divide-y divide-gray-100"
				>
					<!-- Gelondongan: one price for every tinta of the group, or per tinta below it -->
					<div
						v-for="{ group, members } in filteredGroups"
						:key="group.addon_group"
					>
						<div class="flex items-center gap-2 px-2 py-1.5 bg-gray-50">
							<span class="flex-1 min-w-0 text-sm font-semibold text-start truncate">
								{{ group.addon_group }}
								<span class="text-xs font-normal text-gray-400">{{
									__("Gelondongan")
								}}</span>
							</span>
							<input
								:value="headerLocked(group) ? 0 : group.amount"
								type="number"
								min="0"
								inputmode="decimal"
								:disabled="headerLocked(group)"
								:aria-label="__('Add on price')"
								class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2 disabled:bg-gray-100"
								@input="group.amount = $event.target.value"
							/>
						</div>
						<div
							v-for="row in members"
							:key="row.item_code"
							class="flex items-center gap-2 ps-6 pe-2 py-1.5"
						>
							<span class="flex-1 min-w-0 text-sm text-start truncate">
								{{ row.item_name }}
								<span class="text-xs text-gray-400">{{ row.item_code }}</span>
							</span>
							<input
								v-model="row.amount"
								type="number"
								min="0"
								inputmode="decimal"
								:disabled="amountOf(group) > 0"
								:aria-label="__('Add on price')"
								class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2 disabled:bg-gray-100"
							/>
						</div>
					</div>

					<div
						v-for="row in filteredItems"
						:key="row.item_code"
						class="flex items-center gap-2 px-2 py-1.5"
					>
						<span class="flex-1 min-w-0 text-sm text-start truncate">
							{{ row.item_name }}
							<span class="text-xs text-gray-400">{{ row.item_code }}</span>
						</span>
						<input
							v-model="row.amount"
							type="number"
							min="0"
							inputmode="decimal"
							:aria-label="__('Add on price')"
							class="w-28 h-8 text-end text-sm border border-gray-300 rounded px-2"
						/>
					</div>
				</div>
				<p v-else class="text-sm text-gray-500 text-start">
					{{ __("No add on available for this item in this warehouse.") }}
				</p>

				<div class="flex items-center justify-between text-sm">
					<span class="text-gray-600">{{ __("Add on total") }}</span>
					<span class="font-bold">{{ formatCurrency(selectedTotal) }}</span>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button variant="subtle" @click="show = false">{{ __("Cancel") }}</Button>
				<Button theme="blue" variant="solid" @click="save">{{ __("Save") }}</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { JENIS_JUAL, addonKey, getAvailableAddons } from "@/utils/itemAddons";
import { Button, Dialog, Input } from "frappe-ui";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	item: { type: Object, default: null },
	currency: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue", "save"]);

const show = ref(props.modelValue);
const search = ref("");
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

function amountOf(row) {
	return Number.parseFloat(row.amount) || 0;
}

/** A group price is replaced by its members' prices once any of them is filled. */
function headerLocked(group) {
	return group.members.some((row) => amountOf(row) > 0);
}

function loadRows() {
	search.value = "";
	const current = new Map((props.item?.addons || []).map((a) => [addonKey(a), a.amount]));
	// Add On Jual: services charged to the customer (tinta goes through TintingDialog)
	const available = getAvailableAddons(props.item, JENIS_JUAL);
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
}

function matches(text, term) {
	return (text || "").toLowerCase().includes(term);
}

function rowMatches(row, term) {
	return amountOf(row) > 0 || matches(row.item_name, term) || matches(row.item_code, term);
}

const filteredGroups = computed(() => {
	const term = search.value.trim().toLowerCase();
	return groups.value
		.map((group) => {
			const groupHit = !term || amountOf(group) > 0 || matches(group.addon_group, term);
			const members = groupHit
				? group.members
				: group.members.filter((row) => rowMatches(row, term));
			return { group, members, visible: groupHit || members.length > 0 };
		})
		.filter((entry) => entry.visible);
});

const filteredItems = computed(() => {
	const term = search.value.trim().toLowerCase();
	if (!term) return items.value;
	return items.value.filter((row) => rowMatches(row, term));
});

function selectedAddons() {
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

const selectedTotal = computed(() => selectedAddons().reduce((sum, row) => sum + row.amount, 0));

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

function save() {
	emit("save", selectedAddons());
	show.value = false;
}
</script>
