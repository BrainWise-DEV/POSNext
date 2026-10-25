<!--
  OffersStrip.vue - inline offer progress above the cart totals.
  Applied offers show what the customer got; near-miss quantity/amount offers
  show how much more unlocks them; an offer just removed shows here briefly
  instead of a toast.
-->
<template>
	<div v-if="rows.length" class="flex flex-col gap-1 mb-1.5" aria-live="polite">
		<button
			v-for="row in rows"
			:key="row.key"
			type="button"
			@click="$emit('show-offers')"
			:class="[
				'w-full text-start rounded-md px-2 py-1.5 text-sm border-s-2',
				row.state === 'applied'
					? 'bg-emerald-50 border-emerald-600 text-emerald-800'
					: row.state === 'removed'
						? 'bg-gray-50 border-gray-400 text-gray-600'
						: 'bg-white border-amber-600 text-gray-800',
			]"
		>
			<span class="flex items-center gap-1.5">
				<FeatherIcon
					:name="row.state === 'applied' ? 'check-circle' : row.state === 'removed' ? 'x-circle' : 'gift'"
					:class="[
						'w-4 h-4 flex-shrink-0',
						row.state === 'applied'
							? 'text-emerald-700'
							: row.state === 'removed'
								? 'text-gray-500'
								: 'text-amber-700',
					]"
				/>
				<span dir="auto" :class="['min-w-0 flex-1 truncate', row.state === 'removed' ? 'line-through' : '']">
					{{ row.text }}
				</span>
			</span>
			<span
				v-if="row.percent !== undefined"
				class="block mt-1 h-1.5 w-full rounded-full bg-gray-200 overflow-hidden"
			>
				<span
					class="block h-full rounded-full bg-amber-600 motion-safe:transition-all"
					:style="{ width: `${row.percent}%` }"
				></span>
			</span>
		</button>
	</div>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart";
import { usePOSOffersStore } from "@/stores/posOffers";
import { offerBenefit, offerProgress } from "@/utils/offerProgress";
import { FeatherIcon } from "frappe-ui";
import { computed } from "vue";

const props = defineProps({
	appliedOffers: {
		type: Array,
		default: () => [],
	},
	formatCurrency: {
		type: Function,
		required: true,
	},
	// Near-miss offers shown at once
	maxNearMiss: {
		type: Number,
		default: 2,
	},
});

defineEmits(["show-offers"]);

const cartStore = usePOSCartStore();
const offersStore = usePOSOffersStore();

const rows = computed(() => {
	const appliedCodes = new Set(props.appliedOffers.map((o) => o.code));
	const benefit = (offer) => offerBenefit(offer, props.formatCurrency);

	const applied = props.appliedOffers.map((entry) => ({
		key: `applied-${entry.code}`,
		state: "applied",
		text: __("{0}: {1} applied ✓", [entry.name, benefit(entry.offer || entry)]),
	}));

	const removed = (cartStore.removedOfferNotices || []).map((name) => ({
		key: `removed-${name}`,
		state: "removed",
		text: __("{0}: removed, the cart no longer qualifies", [name]),
	}));

	// Closest first, only offers the cart is at least halfway to
	const nearMiss = offersStore.availableOffers
		.filter((offer) => !offer.coupon_based && !appliedCodes.has(offer.name))
		.map((offer) => ({
			offer,
			progress: offerProgress(offer, {
				qty: offersStore.getEligibleItemQuantity(offer),
				amount: offersStore.getEligibleItemAmount(offer),
			}),
		}))
		.filter(({ progress }) => progress && progress.percent >= 50)
		.sort((a, b) => b.progress.percent - a.progress.percent)
		.slice(0, props.maxNearMiss)
		.map(({ offer, progress }) => ({
			key: `near-${offer.name}`,
			state: "near",
			percent: progress.percent,
			text:
				progress.kind === "qty"
					? __("Buy {0} more {1} and get {2}", [
							progress.missing,
							offer.title || offer.name,
							benefit(offer),
						])
					: __("Add {0} more and get {1}", [
							props.formatCurrency(progress.missing),
							benefit(offer),
						]),
		}));

	return [...applied, ...removed, ...nearMiss];
});
</script>
