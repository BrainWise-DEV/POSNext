<template>
	<Dialog v-model="show" :options="{ title: __('Antrian Pesanan SPG'), size: 'xl' }">
		<template #body-content>
			<div class="flex flex-col gap-3">
				<div class="flex items-center justify-between gap-2">
					<p class="text-xs text-gray-500">
						{{ __("Pesanan menunggu pembayaran di cabang ini, terlama di atas.") }}
					</p>
					<div class="flex items-center gap-1 shrink-0">
						<Button size="sm" variant="subtle" @click="emit('open-camera')">
							{{ __("Scan QR (Kamera)") }}
						</Button>
						<Button
							size="sm"
							:loading="loading"
							:disabled="offline"
							@click="loadOrders"
						>
							{{ __("Muat Ulang") }}
						</Button>
					</div>
				</div>

				<div v-if="offline" class="text-center py-6 text-sm text-gray-500">
					{{ __("Sedang offline - scan QR di struk pesanan untuk memprosesnya.") }}
				</div>

				<div
					v-else-if="loading && orders.length === 0"
					class="text-center py-6 text-sm text-gray-500"
				>
					{{ __("Memuat antrian...") }}
				</div>

				<div v-else-if="orders.length === 0" class="text-center py-6">
					<p class="text-sm font-medium text-gray-900">
						{{ __("Tidak ada pesanan SPG yang menunggu pembayaran") }}
					</p>
				</div>

				<div v-else class="flex flex-col gap-2 max-h-[28rem] overflow-y-auto">
					<div
						v-for="order in orders"
						:key="order.name"
						class="bg-white border border-gray-200 rounded-lg p-3"
					>
						<div class="flex flex-wrap items-start justify-between gap-2">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-semibold text-gray-900">{{
										order.name
									}}</span>
									<span
										v-if="order.is_own_shift"
										class="text-[10px] font-medium bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded"
									>
										{{ __("Shift saya") }}
									</span>
									<span v-else class="text-[10px] text-gray-500">
										{{ __("Kasir: {0}", [order.cashier_name]) }}
									</span>
									<span
										v-if="order.dikirim"
										class="text-[10px] font-medium bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded"
									>
										{{ __("Dikirim") }}
									</span>
								</div>
								<div class="text-xs text-gray-600 mt-0.5">
									{{ __("SPG: {0}", [order.spg_name]) }}
									<template v-if="order.customer">
										· {{ order.customer }}</template
									>
								</div>
								<div class="text-xs text-gray-500 mt-0.5">
									{{ order.total_qty }} {{ __("item") }} ·
									{{ formatCurrency(order.grand_total, currency) }} ·
									{{ String(order.creation || "").slice(11, 16) }}
								</div>
							</div>
							<div class="flex items-center gap-1 shrink-0">
								<Button
									size="sm"
									:loading="busy === order.name + ':detail'"
									@click="toggleDetail(order.name)"
								>
									{{ details[order.name] ? __("Tutup") : __("Detail") }}
								</Button>
								<Button
									size="sm"
									theme="red"
									:loading="busy === order.name + ':cancel'"
									@click="cancel(order.name)"
								>
									{{ __("Batal") }}
								</Button>
								<Button
									size="sm"
									variant="solid"
									@click="emit('load-order', order.name)"
								>
									{{ __("Proses") }}
								</Button>
							</div>
						</div>

						<table
							v-if="details[order.name]"
							class="w-full mt-2 text-xs border-t border-gray-100"
						>
							<tbody>
								<tr
									v-for="item in details[order.name]"
									:key="item.name"
									class="border-b border-gray-50 last:border-0"
								>
									<td
										class="py-1 pe-2 text-gray-900"
										:class="{ 'ps-3 text-gray-600': item.addon_parent_key }"
									>
										<template v-if="item.addon_parent_key">+ </template>
										{{ item.item_name || item.addon_item || item.item_code }}
										<div class="text-[10px] text-gray-400">
											{{ item.warehouse }}
										</div>
									</td>
									<td class="py-1 pe-2 text-gray-600 whitespace-nowrap">
										{{ item.qty }} {{ item.uom }} ×
										{{ formatCurrency(item.rate || 0, currency) }}
									</td>
									<td class="py-1 text-end text-gray-900 whitespace-nowrap">
										{{ formatCurrency(item.amount || 0, currency) }}
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { useToast } from "@/composables/useToast";
import { call } from "@/utils/apiWrapper";
import { DEFAULT_CURRENCY, formatCurrency } from "@/utils/currency";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

/**
 * Cashier: Pending SPG orders (nextend POS Order) of the shift's Warehouse
 * Group, including orders an SPG addressed to another cashier there.
 * "Proses" hands the order to the same loader as a scanned QR slip.
 */
const props = defineProps({
	modelValue: Boolean,
	shiftName: String,
	offline: Boolean,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
});

const emit = defineEmits(["update:modelValue", "load-order", "queue-changed", "open-camera"]);

const { showSuccess, showError } = useToast();

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

const orders = ref([]);
const details = ref({});
const loading = ref(false);
const busy = ref(null);

function errorMessage(error, fallback) {
	return error?.messages?.[0] || error?.message || fallback;
}

async function loadOrders() {
	if (!props.shiftName || props.offline) return;
	loading.value = true;
	try {
		const queue = await call("nextend.pos_order.get_queue_orders", {
			pos_opening_shift: props.shiftName,
		});
		orders.value = queue?.orders || [];
		emit("queue-changed", orders.value.length);
	} catch (error) {
		showError(errorMessage(error, __("Gagal memuat antrian pesanan")));
	} finally {
		loading.value = false;
	}
}

async function toggleDetail(name) {
	if (details.value[name]) {
		delete details.value[name];
		return;
	}
	busy.value = `${name}:detail`;
	try {
		const order = await call("nextend.pos_order.get_order", { name });
		details.value[name] = order.items || [];
	} catch (error) {
		showError(errorMessage(error, __("Gagal memuat detail pesanan")));
	} finally {
		busy.value = null;
	}
}

async function cancel(name) {
	if (!window.confirm(__("Batalkan pesanan {0}? Stok yang dikunci akan dilepas.", [name]))) {
		return;
	}
	busy.value = `${name}:cancel`;
	try {
		await call("nextend.pos_order.cancel_order", { name });
		showSuccess(__("Pesanan {0} dibatalkan", [name]));
		await loadOrders();
	} catch (error) {
		showError(errorMessage(error, __("Gagal membatalkan pesanan")));
	} finally {
		busy.value = null;
	}
}

watch(show, (value) => {
	if (value) {
		details.value = {};
		loadOrders();
	}
});

defineExpose({ loadOrders });
</script>
