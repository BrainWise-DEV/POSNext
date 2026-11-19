<template>
	<Dialog v-model="show" :options="{ title: __('Available Offers'), size: 'lg' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Loading State -->
				<div v-if="loading" class="py-8 text-center">
					<div
						class="animate-spin rounded-full h-10 w-10 border-b-2 border-green-500 mx-auto"
					></div>
					<p class="mt-3 text-sm text-gray-500">{{ __("Loading offers...") }}</p>
				</div>

				<!-- Empty State -->
				<div v-else-if="eligibleOffers.length === 0" class="py-12 text-center">
					<div
						class="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-gray-100"
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
								d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
							/>
						</svg>
					</div>
					<h3 class="mt-4 text-sm font-medium text-gray-900">
						{{ __("No offers available") }}
					</h3>
					<p class="mt-2 text-xs text-gray-500">
						{{ __("Add items to your cart to see eligible offers") }}
					</p>
				</div>

				<!-- Offers List -->
				<div v-else>
					<div class="flex flex-col gap-3 max-h-[500px] overflow-y-auto pe-2">
						<div
							v-for="offer in eligibleOffers"
							:key="offer.name"
							:class="[
								'relative rounded-xl p-4 transition-all duration-200 border-2',
								isOfferApplied(offer)
									? 'bg-green-50 border-green-500 shadow-md'
									: 'bg-gradient-to-r from-green-50 to-emerald-50 border-green-200 hover:border-green-400 hover:shadow-lg cursor-pointer',
							]"
						>
							<!-- What the customer gets, with the offer type beside it -->
							<div class="flex items-start gap-2 mb-3">
								<div
									:class="[
										'flex-1 min-w-0 text-white px-3 py-2 rounded-lg transition-all',
										isOfferApplied(offer)
											? 'bg-green-700 ring-2 ring-green-600'
											: offer.offer === 'Give Product'
											? 'bg-purple-600'
											: offer.discount_percentage
											? 'bg-orange-600'
											: 'bg-green-600',
									]"
								>
									<div class="text-base font-bold leading-snug break-words" dir="auto">
										{{ offerBenefit(offer, formatCurrency, itemName) }}
									</div>
								</div>
								<!-- Source Badge (Pricing Rule vs Promotional Scheme) -->
								<div
									:class="[
										'flex-shrink-0 text-[10px] font-bold px-2 py-1 rounded-full',
										offer.source === 'Pricing Rule'
											? 'bg-blue-600 text-white'
											: 'bg-purple-600 text-white',
									]"
								>
									{{
										offer.source === "Pricing Rule"
											? __("PRICING RULE")
											: __("PROMO SCHEME")
									}}
								</div>
							</div>

							<!-- Offer Header -->
							<div class="mb-3">
								<h4 class="text-sm font-semibold text-gray-900 text-start" dir="auto">
									{{ offer.title || offer.name }}
								</h4>
								<p
									v-if="offer.description && offer.description !== (offer.title || offer.name)"
									class="text-xs text-gray-600 mt-1 text-start"
								>
									{{ offer.description }}
								</p>
							</div>

							<!-- Offer Details -->
							<div class="grid grid-cols-2 gap-3 mb-3">
								<!-- Min Amount -->
								<div v-if="offer.min_amt" class="flex items-center gap-2">
									<svg
										class="w-4 h-4 text-gray-500"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
										/>
									</svg>
									<div>
										<p class="text-[10px] text-gray-500">
											{{ __("Min Purchase") }}
										</p>
										<p class="text-xs font-semibold text-gray-900">
											{{ formatCurrency(offer.min_amt) }}
										</p>
									</div>
								</div>

								<!-- Min Quantity -->
								<div v-if="offer.min_qty" class="flex items-center gap-2">
									<svg
										class="w-4 h-4 text-gray-500"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
										/>
									</svg>
									<div>
										<p class="text-[10px] text-gray-500">
											{{ __("Min Quantity") }}
										</p>
										<p class="text-xs font-semibold text-gray-900">
											{{
												offer.min_qty === 1
													? __("1 item")
													: __("{0} items", [offer.min_qty])
											}}
										</p>
									</div>
								</div>

								<!-- Valid Until -->
								<div v-if="offer.valid_upto" class="flex items-center gap-2">
									<svg
										class="w-4 h-4 text-gray-500"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
										/>
									</svg>
									<div>
										<p class="text-[10px] text-gray-500">
											{{ __("Valid Until") }}
										</p>
										<p class="text-xs font-semibold text-gray-900">
											{{ formatDate(offer.valid_upto) }}
										</p>
									</div>
								</div>

								<!-- Offer Type -->
								<div class="flex items-center gap-2">
									<svg
										class="w-4 h-4 text-gray-500"
										fill="currentColor"
										viewBox="0 0 20 20"
									>
										<path
											fill-rule="evenodd"
											d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z"
											clip-rule="evenodd"
										/>
									</svg>
									<div>
										<p class="text-[10px] text-gray-500">{{ __("Type") }}</p>
										<p class="text-xs font-semibold text-gray-900">
											{{ offerTypeLabel(offer.offer) }}
										</p>
									</div>
								</div>
							</div>

							<!-- Progress toward the offer's minimum (only shown if not met) -->
							<div v-if="getProgress(offer)" class="mt-3">
								<div class="w-full bg-gray-200 rounded-full h-2">
									<div
										class="bg-green-700 h-2 rounded-full transition-all"
										:style="{ width: `${getProgress(offer).percent}%` }"
									></div>
								</div>
								<p class="text-xs text-amber-700 mt-1 font-medium">
									{{ formatProgress(offer) }}
								</p>
							</div>

							<!-- Offer Status - Auto-applied/removed based on cart -->
							<div class="mt-3">
								<div
									v-if="isOfferApplied(offer)"
									class="w-full py-2 px-4 rounded-lg font-semibold text-sm bg-green-100 text-green-800 border border-green-300 flex items-center justify-center gap-2"
								>
									<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
										<path
											fill-rule="evenodd"
											d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
											clip-rule="evenodd"
										/>
									</svg>
									{{ __("Applied") }}
								</div>
								<div
									v-else
									class="w-full py-2 px-4 rounded-lg font-semibold text-sm bg-blue-50 text-blue-700 border border-blue-200 flex items-center justify-center gap-2"
								>
									<svg
										class="w-4 h-4 animate-pulse"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
										/>
									</svg>
									{{ __("Will apply when eligible") }}
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end w-full">
				<Button variant="subtle" @click="show = false">
					{{ __("Close") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { usePOSOffersStore } from "@/stores/posOffers";
import { useItemSearchStore } from "@/stores/itemSearch";
import {
	DEFAULT_CURRENCY,
	DEFAULT_LOCALE,
	formatCurrency as formatCurrencyUtil,
} from "@/utils/currency";
import { offerBenefit, offerProgress, offerTypeLabel } from "@/utils/offerProgress";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

// Use Pinia stores
const offersStore = usePOSOffersStore();
const itemSearchStore = useItemSearchStore();

// Gift item name for an item code, falling back to the code
function itemName(code) {
	return itemSearchStore.allItems?.find((item) => item.item_code === code)?.item_name || code;
}

const props = defineProps({
	modelValue: Boolean,
	subtotal: {
		type: Number,
		required: true,
		note: __("Cart subtotal BEFORE tax - used for discount calculations"),
	},
	items: Array,
	posProfile: String,
	customer: String,
	company: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	appliedOffers: {
		type: Array,
		default: () => [],
	},
});

const emit = defineEmits(["update:modelValue"]);

const show = ref(props.modelValue);
const appliedOfferCodes = computed(() => {
	return new Set((props.appliedOffers || []).map((entry) => entry?.code).filter(Boolean));
});

// Use ALL eligible offers from store (includes both auto and manual offers),
// then near-miss offers the cart is on its way to
const eligibleOffers = computed(() => [
	...offersStore.allEligibleOffersSorted,
	...offersStore.availableOffers.filter(
		(o) => !o.coupon_based && !offersStore.allEligibleOffers.includes(o) && getProgress(o)
	),
]);

// Loading state - check if offers are being loaded
const loading = computed(() => {
	return !offersStore.hasFetched && eligibleOffers.value.length === 0;
});

watch(
	() => props.modelValue,
	(val) => {
		show.value = val;
		// No need to load offers - they're already in the store
	}
);

watch(show, (val) => {
	emit("update:modelValue", val);
});

function isOfferApplied(offer) {
	// Applied only while the cart still qualifies on the same basis the
	// eligibility gate uses; avoids an APPLIED badge on an offer that is
	// already being removed (stale badge in the offers-loop bug).
	if (!appliedOfferCodes.value.has(offer?.name)) return false;
	return offersStore.checkOfferEligibility(offer).eligible;
}

function getProgress(offer) {
	return offerProgress(offer, {
		qty: offersStore.getEligibleItemQuantity(offer),
		amount: offersStore.getEligibleItemAmount(offer),
	});
}

/** "Buy 1 more to get 1 free" / "Add E£50 more to get 20% off" */
function formatProgress(offer) {
	const progress = getProgress(offer);
	const benefit = offerBenefit(offer, formatCurrency, itemName);
	return progress.kind === "qty"
		? __("Buy {0} more to get {1}", [progress.missing, benefit])
		: __("Add {0} more and get {1}", [formatCurrency(progress.missing), benefit]);
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

function formatDate(dateStr) {
	if (!dateStr) return "";
	const date = new Date(dateStr);
	return date.toLocaleDateString(DEFAULT_LOCALE, {
		month: "short",
		day: "numeric",
		year: "numeric",
	});
}
</script>
