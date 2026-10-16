<!--
nextend Pengiriman: where a delivered sale goes - the address, the customer's
other addresses to pick from, and a note for the driver. Shared by the
cashier's payment dialog and the SPG's save-order dialog; shown only once
Dikirim is ticked, so mounting it is what looks the addresses up.
-->
<template>
	<div>
		<textarea
			:value="alamat"
			rows="2"
			:aria-label="__('Alamat kirim')"
			:placeholder="__('Alamat kirim (wajib diisi)')"
			class="w-full border border-gray-300 rounded-lg px-2 py-1 text-sm bg-white resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
			@input="emit('update:alamat', $event.target.value)"
		></textarea>
		<!-- The customer's other addresses (nextend.pengiriman) -->
		<div v-if="pilihan.length > 1" class="mb-1 flex flex-wrap gap-1">
			<!-- blur(): a focused button would swallow the numpad's keyboard keys -->
			<button
				v-for="item in pilihan"
				:key="item.label"
				type="button"
				:title="item.alamat"
				:class="[
					'rounded-full border px-2 py-0.5 text-xs font-medium',
					alamat.trim() === item.alamat
						? 'bg-blue-600 border-blue-600 text-white'
						: 'bg-white border-gray-300 text-gray-700 hover:bg-gray-100',
				]"
				@click="
					emit('update:alamat', item.alamat);
					$event.currentTarget.blur();
				"
			>
				{{ item.label }}
			</button>
		</div>
		<input
			:value="catatan"
			type="text"
			:aria-label="__('Catatan untuk sopir')"
			:placeholder="__('Catatan untuk sopir (boleh kosong)')"
			class="mt-1 w-full h-8 border border-gray-300 rounded-lg px-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
			@input="emit('update:catatan', $event.target.value)"
		/>
	</div>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { onMounted, ref } from "vue";

const props = defineProps({
	alamat: { type: String, default: "" },
	catatan: { type: String, default: "" },
	/** Customer whose last delivery and saved addresses are offered; none for a walk-in */
	customer: { type: String, default: "" },
});
const emit = defineEmits(["update:alamat", "update:catatan"]);

const pilihan = ref([]);

// Offer where this customer's last delivery went and their saved addresses:
// the first is filled in, the user may pick another or overwrite it.
onMounted(async () => {
	if (!props.customer) return;
	try {
		const found = await call("nextend.pengiriman.get_delivery_addresses", {
			customer: props.customer,
		});
		if (!found?.length) return;
		pilihan.value = found;
		if (!props.alamat.trim()) emit("update:alamat", found[0].alamat);
	} catch {
		// Offline or no access to the customer: the address is typed by hand
	}
});
</script>
