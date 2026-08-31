<template>
	<Dialog v-model="isOpen" :options="{ title: __('Choose Package Options'), size: '2xl' }">
		<template #body-content>
			<div v-if="pkg" class="py-2 flex flex-col gap-4">
				<!-- Package header -->
				<div class="flex items-start gap-3">
					<div
						class="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0"
					>
						<svg
							class="h-6 w-6 text-blue-600"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
							/>
						</svg>
					</div>
					<div class="flex-1 min-w-0">
						<h3 class="text-sm font-semibold text-gray-900">
							{{ pkg.package_name }}
						</h3>
						<p v-if="pkg.description" class="text-xs text-gray-500 mt-0.5">
							{{ pkg.description }}
						</p>
						<p class="text-xs text-gray-500 mt-0.5">
							{{ __("Base price") }}: {{ formatCurrency(pkg.base_price) }}
						</p>
					</div>
				</div>

				<!-- Always-included items -->
				<div v-if="pkg.items?.length" class="rounded-lg border border-gray-200 p-3">
					<p class="text-xs font-semibold text-gray-900 mb-2">
						{{ __("Included in this package") }}
					</p>
					<ul class="flex flex-col gap-1">
						<li
							v-for="row in pkg.items"
							:key="row.item_code"
							class="flex items-center gap-2 text-sm text-gray-700"
						>
							<svg
								class="w-4 h-4 text-green-600 flex-shrink-0"
								fill="currentColor"
								viewBox="0 0 20 20"
							>
								<path
									fill-rule="evenodd"
									d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
									clip-rule="evenodd"
								/>
							</svg>
							<span class="flex-1 truncate">{{ row.item_name || row.item_code }}</span>
							<span class="text-xs text-gray-500">x{{ row.qty }}</span>
						</li>
					</ul>
				</div>

				<!-- Choice groups -->
				<div v-for="group in pkg.groups" :key="group.group_key" class="rounded-lg border p-3"
					:class="groupState[group.group_key].satisfied
						? 'border-gray-200'
						: 'border-orange-300 bg-orange-50/40'"
				>
					<div class="flex items-start justify-between gap-2 mb-2">
						<div class="min-w-0">
							<p class="text-sm font-semibold text-gray-900">{{ group.label }}</p>
							<p v-if="group.description" class="text-xs text-gray-500">
								{{ group.description }}
							</p>
							<p class="text-xs text-gray-500 mt-0.5">
								{{ groupRule(group) }}
							</p>
						</div>
						<span
							class="text-xs font-bold px-2 py-1 rounded-md whitespace-nowrap"
							:class="groupState[group.group_key].satisfied
								? 'bg-green-100 text-green-700'
								: 'bg-orange-100 text-orange-700'"
						>
							{{ groupState[group.group_key].picked }} / {{ group.max_qty }}
						</span>
					</div>

					<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
						<div
							v-for="option in optionsForGroup(group.group_key)"
							:key="option.option_id"
							class="flex items-center gap-2 rounded-lg border-2 p-2 transition-colors"
							:class="picked(group.group_key, option.option_id) > 0
								? 'border-blue-500 bg-blue-50'
								: 'border-gray-200 bg-white'"
						>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-gray-900 truncate">
									{{ option.item_name || option.item_code }}
								</p>
								<p class="text-xs" :class="option.price_adjustment
									? 'text-blue-600 font-semibold'
									: 'text-gray-500'"
								>
									{{ priceAdjustmentLabel(option) }}
								</p>
							</div>

							<!-- Single-pick groups use a plain toggle; multi-pick groups use a stepper -->
							<Button
								v-if="isSinglePick(group)"
								:variant="picked(group.group_key, option.option_id) ? 'solid' : 'subtle'"
								theme="blue"
								size="sm"
								@click="togglePick(group, option)"
							>
								{{ picked(group.group_key, option.option_id) ? __("Chosen") : __("Choose") }}
							</Button>

							<div v-else class="flex items-center gap-1">
								<Button
									variant="subtle"
									size="sm"
									:disabled="picked(group.group_key, option.option_id) <= 0"
									:aria-label="__('Decrease')"
									@click="decrement(group, option)"
								>
									&minus;
								</Button>
								<span class="w-6 text-center text-sm font-semibold text-gray-900">
									{{ picked(group.group_key, option.option_id) }}
								</span>
								<Button
									variant="subtle"
									size="sm"
									:disabled="!canIncrement(group, option)"
									:aria-label="__('Increase')"
									@click="increment(group, option)"
								>
									+
								</Button>
							</div>
						</div>
					</div>
				</div>

				<!-- Validation feedback -->
				<p
					v-if="validationError"
					class="text-xs text-orange-700 flex items-center gap-1.5 bg-orange-50 rounded-lg p-2"
				>
					<svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
						/>
					</svg>
					{{ validationError }}
				</p>

				<!-- Running total -->
				<div
					class="flex items-center justify-between rounded-lg bg-gray-50 border border-gray-200 p-3"
				>
					<span class="text-sm font-medium text-gray-700">{{ __("Package Total") }}</span>
					<span class="text-lg font-bold text-blue-600">
						{{ formatCurrency(runningTotal) }}
					</span>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex gap-2 w-full">
				<Button class="flex-1" variant="subtle" @click="cancel">
					{{ __("Cancel") }}
				</Button>
				<Button
					class="flex-1"
					variant="solid"
					theme="blue"
					:loading="confirming"
					:disabled="!localQuote.valid || confirming"
					@click="confirm"
				>
					{{ __("Add to Cart") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { usePOSPackagesStore } from "@/stores/posPackages";
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { pickedQty, quotePackageLocally } from "@/utils/packageQuote";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	pkg: Object,
	posProfile: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
});

const emit = defineEmits(["update:modelValue", "package-selected"]);

const packagesStore = usePOSPackagesStore();

const isOpen = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

/** group_key -> option_id -> qty */
const selections = ref({});
const confirming = ref(false);

/** Live preview. The server re-quotes on confirm and again on invoice validate. */
const localQuote = computed(() => quotePackageLocally(props.pkg, selections.value));

const validationError = computed(() => (localQuote.value.valid ? null : localQuote.value.error));

/**
 * Price shown while choosing. Mirrors the quote formula but ignores validity, so
 * an incomplete selection still shows what has been picked so far instead of 0.
 */
const runningTotal = computed(() => {
	let total = Number(props.pkg?.base_price) || 0;

	for (const [, picks] of Object.entries(selections.value)) {
		for (const [optionId, qty] of Object.entries(picks || {})) {
			const option = (props.pkg?.options || []).find((o) => o.option_id === optionId);
			if (option) total += (Number(option.price_adjustment) || 0) * (Number(qty) || 0);
		}
	}

	return total;
});

const groupState = computed(() => {
	const state = {};
	for (const group of props.pkg?.groups || []) {
		const picks = selections.value[group.group_key] || {};
		const total = pickedQty(picks);
		state[group.group_key] = {
			picked: total,
			satisfied: total >= (group.min_qty || 0) && total <= group.max_qty,
		};
	}
	return state;
});

function optionsForGroup(groupKey) {
	return (props.pkg?.options || []).filter((o) => o.group_key === groupKey);
}

function isSinglePick(group) {
	return group.max_qty === 1;
}

function picked(groupKey, optionId) {
	return selections.value[groupKey]?.[optionId] || 0;
}

function setPick(groupKey, optionId, qty) {
	const groupPicks = { ...(selections.value[groupKey] || {}) };
	if (qty > 0) {
		groupPicks[optionId] = qty;
	} else {
		delete groupPicks[optionId];
	}
	selections.value = { ...selections.value, [groupKey]: groupPicks };
}

function togglePick(group, option) {
	const isChosen = picked(group.group_key, option.option_id) > 0;
	// Single-pick groups hold at most one option, so choosing replaces the previous.
	selections.value = {
		...selections.value,
		[group.group_key]: isChosen ? {} : { [option.option_id]: 1 },
	};
}

function canIncrement(group, option) {
	const groupPicks = selections.value[group.group_key] || {};
	if (pickedQty(groupPicks) >= group.max_qty) return false;

	const optionMax = option.max_qty || 0;
	return !optionMax || picked(group.group_key, option.option_id) < optionMax;
}

function increment(group, option) {
	if (!canIncrement(group, option)) return;
	setPick(group.group_key, option.option_id, picked(group.group_key, option.option_id) + 1);
}

function decrement(group, option) {
	setPick(group.group_key, option.option_id, picked(group.group_key, option.option_id) - 1);
}

function groupRule(group) {
	const min = group.min_qty || 0;
	const max = group.max_qty;

	if (min === max) return __("Choose exactly {0}", [max]);
	if (min === 0) return __("Choose up to {0} (optional)", [max]);
	return __("Choose {0} to {1}", [min, max]);
}

function priceAdjustmentLabel(option) {
	const adjustment = Number(option.price_adjustment) || 0;
	if (!adjustment) return __("Included");
	const sign = adjustment > 0 ? "+" : "-";
	return `${sign}${formatCurrency(Math.abs(adjustment))}`;
}

function formatCurrency(value) {
	return formatCurrencyUtil(value || 0, props.currency);
}

/** Pre-select mandatory single-option groups so the common case is one tap. */
function resetSelections() {
	const initial = {};
	for (const group of props.pkg?.groups || []) {
		const options = optionsForGroup(group.group_key);
		if (group.min_qty === group.max_qty && group.max_qty === 1 && options.length === 1) {
			initial[group.group_key] = { [options[0].option_id]: 1 };
		} else {
			initial[group.group_key] = {};
		}
	}
	selections.value = initial;
}

watch(
	() => [props.modelValue, props.pkg?.name],
	([open]) => {
		if (open) resetSelections();
	},
	{ immediate: true }
);

function cancel() {
	isOpen.value = false;
}

async function confirm() {
	if (!localQuote.value.valid || confirming.value) return;

	confirming.value = true;
	try {
		const quote = await packagesStore.quote(props.pkg, selections.value, props.posProfile);
		if (!quote.valid) return;

		emit("package-selected", { quote, pkg: props.pkg });
		isOpen.value = false;
	} finally {
		confirming.value = false;
	}
}
</script>
