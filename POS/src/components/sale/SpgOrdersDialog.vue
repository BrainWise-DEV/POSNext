<template>
	<Dialog v-model="show" :options="{ title: __('Pesanan Saya'), size: 'lg' }">
		<template #body-content>
			<div class="flex flex-col gap-3">
				<div v-if="loading" class="text-center py-6 text-sm text-gray-500">
					{{ __("Memuat pesanan...") }}
				</div>

				<div v-else-if="orders.length === 0" class="text-center py-6">
					<p class="text-sm font-medium text-gray-900">
						{{ __("Tidak ada pesanan yang menunggu pembayaran") }}
					</p>
				</div>

				<div v-else class="flex flex-col gap-2 max-h-96 overflow-y-auto">
					<div
						v-for="order in orders"
						:key="order.name"
						class="bg-white border border-gray-200 rounded-lg p-3"
					>
						<div class="flex items-start justify-between gap-2">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2 flex-wrap">
									<span class="text-sm font-semibold text-gray-900">
										{{ order.name }}
									</span>
									<span
										v-if="order.dikirim"
										class="text-[10px] font-medium bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded"
									>
										{{ __("Dikirim") }}
									</span>
								</div>
								<div class="text-xs text-gray-500 mt-0.5">
									{{ order.total_qty }} {{ __("item") }} ·
									{{ formatCurrency(order.grand_total, currency) }}
								</div>
								<div class="text-xs text-gray-400 mt-0.5">
									{{ String(order.creation || "").slice(0, 16) }}
								</div>
							</div>
							<div class="flex items-center gap-1 shrink-0">
								<Button
									size="sm"
									:disabled="Boolean(busy)"
									@click="emit('edit-order', order.name)"
								>
									{{ __("Ubah") }}
								</Button>
								<Button
									size="sm"
									:loading="busy === order.name + ':print'"
									@click="reprint(order.name)"
								>
									{{ __("Cetak") }}
								</Button>
								<Button
									size="sm"
									theme="red"
									:loading="busy === order.name + ':cancel'"
									@click="cancel(order.name)"
								>
									{{ __("Batal") }}
								</Button>
							</div>
						</div>
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
import { openSpgOrderSlipWindow, printSpgOrderSlip } from "@/utils/printSpgOrder";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: Boolean,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
});

const emit = defineEmits(["update:modelValue", "edit-order", "orders-changed"]);

const { showSuccess, showError } = useToast();

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

const orders = ref([]);
const loading = ref(false);
const busy = ref(null);

function errorMessage(error, fallback) {
	return error?.messages?.[0] || error?.message || fallback;
}

async function loadOrders() {
	loading.value = true;
	try {
		orders.value = (await call("nextend.pos_order.get_my_orders")) || [];
		emit("orders-changed", orders.value);
	} catch (error) {
		showError(errorMessage(error, __("Gagal memuat pesanan")));
	} finally {
		loading.value = false;
	}
}

async function reprint(name) {
	busy.value = `${name}:print`;
	// Opened before awaiting the server, or the browser blocks it as a popup
	const printWindow = openSpgOrderSlipWindow();
	try {
		const order = await call("nextend.pos_order.get_order", { name });
		printSpgOrderSlip(order, props.currency, printWindow);
	} catch (error) {
		printWindow?.close();
		showError(errorMessage(error, __("Gagal mencetak pesanan")));
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
	if (value) loadOrders();
});

defineExpose({ loadOrders });
</script>
