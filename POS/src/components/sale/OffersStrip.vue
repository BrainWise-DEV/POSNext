<!--
  OffersStrip.vue - the cashier's offer coach above the cart totals.
  Applied offers are quiet chips; an offer just lost shows struck through;
  near-miss offers say what to add and what the customer gets, with a
  one-tap top-up of the line that counts toward them.
-->
<template>
	<div v-if="chips.length || coaching.length" class="flex flex-col gap-1.5 mb-1.5" aria-live="polite">
		<!-- Applied and just-removed offers -->
		<div v-if="chips.length" class="flex flex-wrap gap-1">
			<button
				v-for="chip in chips"
				:key="chip.key"
				type="button"
				@click="$emit('show-offers')"
				:class="[
					'inline-flex items-center gap-1 max-w-full rounded-full px-2.5 min-h-[28px] text-xs font-semibold',
					chip.state === 'applied'
						? 'bg-[#e9f5ef] text-[#0f7a4a]'
						: 'bg-gray-100 text-gray-500 line-through',
				]"
				:title="chip.title"
			>
				<FeatherIcon
					:name="chip.state === 'applied' ? 'check' : 'x'"
					class="w-3.5 h-3.5 flex-shrink-0"
				/>
				<span class="truncate" dir="auto">{{ chip.text }}</span>
			</button>
		</div>

		<!-- Near-miss offers: what to add, and what the customer gets -->
		<div
			v-for="coach in coaching"
			:key="coach.key"
			class="flex items-center gap-2 rounded-lg bg-[#fdf4e7] ps-2.5 pe-1.5 py-2"
		>
			<FeatherIcon name="gift" class="w-5 h-5 text-[#b45309] flex-shrink-0" />
			<button
				type="button"
				@click="$emit('show-offers')"
				class="flex-1 min-w-0 text-start"
			>
				<span dir="auto" class="block text-sm font-semibold text-[#1d2433] leading-snug">
					{{ coach.say }}
				</span>
				<span class="flex items-center gap-2 mt-1">
					<!-- One dot per unit the offer needs; a bar for amounts or long counts -->
					<span
						v-if="coach.dots"
						class="flex items-center gap-1"
						dir="ltr"
						role="img"
						:aria-label="__('{0} of {1}', [coach.have, coach.need])"
					>
						<span
							v-for="n in coach.need"
							:key="n"
							:class="[
								'w-2 h-2 rounded-full',
								n <= coach.have ? 'bg-[#b45309]' : 'bg-white ring-1 ring-inset ring-[#b45309]/50',
							]"
						></span>
					</span>
					<span v-else class="block h-1.5 w-20 rounded-full bg-white overflow-hidden" dir="ltr">
						<span
							class="block h-full rounded-full bg-[#b45309]"
							:style="{ width: `${coach.percent}%` }"
						></span>
					</span>
					<span dir="auto" class="min-w-0 truncate text-xs text-gray-600">{{ coach.offerName }}</span>
				</span>
			</button>
			<button
				v-if="coach.line"
				type="button"
				@click="topUp(coach)"
				class="flex-shrink-0 min-w-[44px] h-10 px-2.5 rounded-md bg-[#b45309] text-white text-sm font-bold tabular-nums hover:bg-[#92400e] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-[#b45309]"
				:aria-label="__('Add {0}', [coach.missing])"
				dir="ltr"
			>
				+{{ coach.missing }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart";
import { useItemSearchStore } from "@/stores/itemSearch";
import { usePOSOffersStore } from "@/stores/posOffers";
import { offerBenefit, offerLine, offerProgress } from "@/utils/offerProgress";
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
const itemSearchStore = useItemSearchStore();

// Counts this long or shorter read as dots; longer ones as a bar
const MAX_DOTS = 8;

function itemName(code) {
	return itemSearchStore.allItems?.find((item) => item.item_code === code)?.item_name || code;
}

function benefit(offer) {
	return offerBenefit(offer, props.formatCurrency, itemName);
}

const chips = computed(() => [
	...props.appliedOffers.map((entry) => ({
		key: `applied-${entry.code}`,
		state: "applied",
		text: benefit(entry.offer || entry),
		title: entry.name,
	})),
	...(cartStore.removedOfferNotices || []).map((name) => ({
		key: `removed-${name}`,
		state: "removed",
		text: name,
		title: __("{0}: removed, the cart no longer qualifies", [name]),
	})),
]);

// Closest first, only offers the cart is at least halfway to
const coaching = computed(() => {
	const appliedCodes = new Set(props.appliedOffers.map((o) => o.code));
	return offersStore.availableOffers
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
		.map(({ offer, progress }) => {
			const line = progress.kind === "qty" ? offerLine(offer, cartStore.invoiceItems) : null;
			const subject =
				line?.item_name || offer.eligible_item_groups?.[0] || offer.eligible_brands?.[0] || "";
			return {
				key: `near-${offer.name}`,
				offerName: offer.title || offer.name,
				line,
				missing: progress.missing,
				have: progress.have,
				need: progress.need,
				percent: progress.percent,
				dots: progress.kind === "qty" && progress.need <= MAX_DOTS,
				say:
					progress.kind === "qty"
						? __("Add {0} {1} and the customer gets {2}", [progress.missing, subject, benefit(offer)])
						: __("Add {0} more and the customer gets {1}", [
								props.formatCurrency(progress.missing),
								benefit(offer),
							]),
			};
		});
});

// Tops up the counted line by the missing units; the cart re-checks offers itself
function topUp(coach) {
	const quantity = (Number.parseFloat(coach.line.quantity) || 0) + coach.missing;
	cartStore.updateItemQuantity(coach.line.item_code, quantity, coach.line.uom);
}
</script>
