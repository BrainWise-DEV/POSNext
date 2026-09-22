<template>
	<Dialog v-model="show" :options="{ title: __('Return / Exchange'), size: 'lg' }">
		<template #body-content>
			<div class="grid grid-cols-1 gap-3">
				<button type="button" class="rounded-xl border-2 border-gray-200 bg-white p-4 text-start hover:border-blue-400 hover:bg-blue-50 transition-colors" @click="choose('with-invoice')">
					<div class="flex items-start gap-3">
						<div class="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center"><FeatherIcon name="file-text" class="w-5 h-5" /></div>
						<div><p class="text-sm font-bold text-gray-900">{{ __('Return With Invoice') }}</p><p class="text-xs text-gray-500 mt-1">{{ __('Invoice-linked return with remaining-quantity control and original-payment refund handling.') }}</p></div>
					</div>
				</button>
				<button v-if="allowWithoutInvoice" type="button" class="rounded-xl border-2 border-gray-200 bg-white p-4 text-start hover:border-amber-400 hover:bg-amber-50 transition-colors" @click="choose('without-invoice')">
					<div class="flex items-start gap-3">
						<div class="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center"><FeatherIcon name="shield" class="w-5 h-5" /></div>
						<div><p class="text-sm font-bold text-gray-900">{{ __('Return Without Invoice') }}</p><p class="text-xs text-gray-500 mt-1">{{ __('Return using the current POS price and controlled credit/cash settlement; manager PIN follows POS Settings.') }}</p></div>
					</div>
				</button>
				<button v-if="allowExchange" type="button" class="rounded-xl border-2 border-gray-200 bg-white p-4 text-start hover:border-emerald-400 hover:bg-emerald-50 transition-colors" @click="choose('exchange')">
					<div class="flex items-start gap-3">
						<div class="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center"><FeatherIcon name="repeat" class="w-5 h-5" /></div>
						<div><p class="text-sm font-bold text-gray-900">{{ __('Exchange') }}</p><p class="text-xs text-gray-500 mt-1">{{ __('Create return credit, add replacement items, then settle only the difference through normal POS payment.') }}</p></div>
					</div>
				</button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Dialog, FeatherIcon } from "frappe-ui";
import { computed } from "vue";

const props = defineProps({
	modelValue: Boolean,
	allowWithoutInvoice: { type: Boolean, default: false },
	allowExchange: { type: Boolean, default: true },
});
const emit = defineEmits(["update:modelValue", "select"]);
const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});
function choose(mode) {
	show.value = false;
	emit("select", mode);
}
</script>
