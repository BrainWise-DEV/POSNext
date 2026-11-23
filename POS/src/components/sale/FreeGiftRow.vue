<template>
	<!-- One card for every free gift (same-item BXGY, GWP, free item, cart-total gift, Gift Pool):
	     full width, no quantity controls. A gift earned by a cart line names that line. -->
	<div
		data-testid="free-gift-row"
		:data-gift-of="item._giftOf || undefined"
		class="flex w-full items-center gap-2 rounded-md border border-[#0f7a4a]/30 bg-[#e9f5ef] p-2"
	>
		<div
			class="w-10 h-10 sm:w-12 sm:h-12 flex-shrink-0 rounded-lg overflow-hidden bg-white border border-[#0f7a4a]/20 flex items-center justify-center"
		>
			<img v-if="image" :src="image" :alt="item.item_name" loading="lazy" class="w-full h-full object-cover" />
			<FeatherIcon v-else name="gift" class="w-5 h-5 text-[#0f7a4a]" />
		</div>
		<div class="flex-1 min-w-0">
			<span
				class="inline-flex items-center gap-1 rounded-full bg-[#0f7a4a] px-2 py-0.5 text-[11px] font-bold text-white"
			>
				<FeatherIcon name="gift" class="w-3 h-3" />{{ __("Free gift") }}
			</span>
			<div dir="auto" class="mt-0.5 text-sm font-semibold text-[#1d2433] leading-snug line-clamp-2">
				{{ item.item_name }}
			</div>
			<div
				v-if="item._giftFor"
				data-testid="free-gift-for"
				class="text-[11px] text-[#0f7a4a] truncate"
			>
				{{ __("For {0}", [item._giftFor]) }}
			</div>
		</div>
		<div class="flex-shrink-0 text-end tabular-nums">
			<div class="text-sm font-bold text-[#0f7a4a]">{{ __("Free of charge") }}</div>
			<div v-if="valueText" class="text-xs text-gray-500 line-through">
				<bdi>{{ valueText }}</bdi>
			</div>
			<div class="text-xs text-gray-600 inline-flex items-center gap-1">
				<bdi>{{ quantityText }}</bdi><span aria-hidden="true">×</span>
			</div>
		</div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui";

defineProps({
	// The free row (nestFreeRows sets _giftOf / _giftFor when a cart line earned it)
	item: { type: Object, required: true },
	image: { type: String, default: null },
	// What the gift would normally cost, formatted; empty when unknown
	valueText: { type: String, default: "" },
	quantityText: { type: String, required: true },
});
</script>
