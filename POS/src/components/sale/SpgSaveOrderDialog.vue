<!--
SPG: last step before an order (nextend POS Order) is saved and its slip
printed - whether the goods are delivered, and where to. The cashier who takes
the payment still decides (and may change it); Bayar di Tempat is theirs alone.
-->
<template>
	<Dialog v-model="show" :options="{ title: __('Simpan Pesanan'), size: 'md' }">
		<template #body-content>
			<div class="flex flex-col gap-3">
				<p class="text-sm text-gray-600">
					{{ __("Pesanan disimpan dan struknya dicetak untuk dibawa ke kasir.") }}
				</p>
				<label
					class="flex items-center gap-2 text-sm font-semibold text-gray-900 cursor-pointer"
				>
					<input
						v-model="dikirim"
						type="checkbox"
						class="rounded border-gray-400 text-blue-600 focus:ring-blue-500"
					/>
					{{ __("Dikirim ke alamat customer") }}
				</label>
				<template v-if="dikirim">
					<DeliveryAddressFields
						v-model:alamat="alamat"
						v-model:catatan="catatan"
						:customer="customer"
					/>
					<p class="text-xs text-gray-500">
						{{
							__(
								"Kasir masih bisa mengubahnya saat pembayaran. Bayar di tempat (COD) diatur di kasir."
							)
						}}
					</p>
				</template>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button :disabled="saving" @click="show = false">{{ __("Batal") }}</Button>
				<Button
					variant="solid"
					:loading="saving"
					:disabled="dikirim && !alamat.trim()"
					@click="save"
				>
					{{ __("Simpan Pesanan") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import DeliveryAddressFields from "@/components/sale/DeliveryAddressFields.vue";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	/** Customer of the order; empty for a walk-in */
	customer: { type: String, default: "" },
	/** Delivery of the order being changed ({ alamat, catatan }), null for a new one */
	initial: { type: Object, default: null },
	saving: Boolean,
});

const emit = defineEmits(["update:modelValue", "save"]);

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

const dikirim = ref(false);
const alamat = ref("");
const catatan = ref("");

watch(show, (open) => {
	if (!open) return;
	dikirim.value = Boolean(props.initial);
	alamat.value = props.initial?.alamat || "";
	catatan.value = props.initial?.catatan || "";
});

/** POS Order fields of the delivery; all empty when the customer takes the goods along. */
function save() {
	emit("save", {
		dikirim: dikirim.value ? 1 : 0,
		alamat_kirim: dikirim.value ? alamat.value.trim() : "",
		catatan_kirim: dikirim.value ? catatan.value.trim() : "",
	});
}
</script>
