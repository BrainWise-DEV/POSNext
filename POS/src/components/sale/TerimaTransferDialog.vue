<template>
	<Dialog v-model="show" :options="{ title: __('Terima transfer untuk nota dan pesanan'), size: '4xl' }">
		<template #body-content>
			<div class="flex flex-col gap-3 text-start">
				<p class="text-xs text-gray-600">
					{{
						__(
							"Untuk customer yang membayar beberapa tagihan sekaligus dengan satu transfer, termasuk nota COD dan pesanan yang dibuat di luar kasir."
						)
					}}
				</p>

				<!-- Selesai -->
				<div v-if="done" class="rounded-lg bg-green-50 border border-green-200 p-3 flex flex-col gap-2">
					<div class="text-sm font-semibold text-green-800">
						{{ __("Transfer {0} tercatat.", [formatCurrency(done.nominal)]) }}
					</div>
					<div class="text-xs text-green-800">
						{{ __("Treasury mengeceknya di aplikasi bank hari ini.") }}
						<template v-if="done.uang_muka > 0">
							{{ __("Kelebihan {0} disimpan sebagai uang muka customer.", [formatCurrency(done.uang_muka)]) }}
						</template>
					</div>
					<div class="flex flex-wrap gap-2">
						<Button v-for="name in done.invoices" :key="name" variant="subtle" @click="emit('print-invoice', name)">
							{{ __("Cetak {0}", [name]) }}
						</Button>
						<Button variant="solid" @click="reset">{{ __("Transfer lain") }}</Button>
					</div>
				</div>

				<template v-else>
					<!-- Customer -->
					<div class="flex flex-col gap-1">
						<label class="text-xs font-semibold text-gray-700" for="tt-customer">{{ __("Customer") }}</label>
						<div v-if="customer" class="flex items-center justify-between gap-2 rounded border border-gray-300 px-3 h-10">
							<span class="text-sm font-medium truncate">{{ customer.customer_name }}</span>
							<button type="button" class="text-xs text-blue-600 hover:underline" @click="clearCustomer">
								{{ __("Ganti") }}
							</button>
						</div>
						<template v-else>
							<input
								id="tt-customer"
								v-model="search"
								type="search"
								class="h-10 text-sm border border-gray-300 rounded px-3"
								:placeholder="__('Nama atau no. HP customer')"
								@input="searchSoon"
							/>
							<div v-if="results.length" class="border border-gray-200 rounded divide-y max-h-56 overflow-y-auto">
								<button
									v-for="c in results"
									:key="c.name"
									type="button"
									class="w-full text-start px-3 py-2 text-sm hover:bg-blue-50"
									@click="pickCustomer(c)"
								>
									<span class="font-medium">{{ c.customer_name }}</span>
									<span class="text-xs text-gray-500 ms-2">{{ c.mobile_no || c.name }}</span>
								</button>
							</div>
						</template>
					</div>

					<div v-if="customer" class="grid grid-cols-1 lg:grid-cols-5 gap-3">
						<!-- Tagihan -->
						<section class="lg:col-span-3 flex flex-col gap-2">
							<h3 class="text-sm font-semibold text-gray-900">{{ __("Tagihan yang bisa dibayar di kasir") }}</h3>
							<p v-if="loadingBills" class="text-xs text-gray-500">{{ __("Memuat…") }}</p>
							<p v-else-if="!bills.length" class="text-xs text-gray-500">
								{{ __("Tidak ada nota COD yang bersisa atau pesanan yang belum lunas.") }}
							</p>
							<div
								v-for="b in bills"
								:key="b.name"
								:class="[
									'rounded-lg p-2.5 flex flex-wrap items-end gap-x-3 gap-y-2',
									b.checked ? 'border-2 border-blue-500 bg-blue-50' : 'border border-gray-200 bg-white',
								]"
							>
								<label class="flex gap-2 items-start flex-1 min-w-[12rem] cursor-pointer">
									<input v-model="b.checked" type="checkbox" class="mt-0.5 w-5 h-5" @change="toggle(b)" />
									<span class="flex flex-col gap-0.5 min-w-0">
										<span class="flex flex-wrap items-center gap-1.5">
											<span class="font-mono text-xs font-semibold">{{ b.name }}</span>
											<span
												:class="[
													'text-[11px] font-bold rounded-full px-2',
													b.doctype === 'Sales Order' ? 'bg-indigo-100 text-indigo-800' : 'bg-amber-100 text-amber-800',
												]"
											>
												{{ b.doctype === "Sales Order" ? __("Pesanan") : __("Nota") }}
											</span>
											<span class="text-[11px] font-bold rounded-full px-2 bg-gray-100 text-gray-700">{{ b.company }}</span>
										</span>
										<span class="text-xs text-gray-500">
											{{ b.tanggal }} ·
											<template v-if="b.doctype === 'Sales Order'">
												{{ __("total {0}", [formatCurrency(b.total)]) }}
												<template v-if="b.dp"> · {{ __("DP {0}", [formatCurrency(b.dp)]) }}</template> ·
												{{ __("dibayar jadi uang muka pesanan") }}
											</template>
											<template v-else>{{ __("sisa {0}", [formatCurrency(b.sisa)]) }}</template>
										</span>
									</span>
								</label>
								<label class="flex flex-col gap-0.5 text-xs text-gray-600 w-40">
									{{ __("Bayar") }}
									<input
										v-model.number="b.amount"
										type="number"
										min="0"
										:max="b.sisa"
										:disabled="!b.checked"
										class="h-10 text-sm font-semibold text-end border border-gray-300 rounded px-2 disabled:bg-gray-100"
										@wheel="$event.target.blur()"
									/>
								</label>
							</div>
							<p class="text-xs text-gray-500 bg-gray-50 rounded p-2">
								{{ __("Nota hutang (customer Boleh Cicilan) tidak tampil di sini: pembayarannya diterima Petugas Piutang.") }}
							</p>
						</section>

						<!-- Data transfer -->
						<section class="lg:col-span-2 flex flex-col gap-2 rounded-lg border border-gray-200 p-3">
							<h3 class="text-sm font-semibold text-gray-900">{{ __("Data transfer") }}</h3>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Nominal transfer") }}
								<input
									v-model.number="nominal"
									type="number"
									min="0"
									class="h-11 text-lg font-bold border border-gray-300 rounded px-2"
									@input="nominalTouched = true"
									@wheel="$event.target.blur()"
								/>
							</label>
							<label v-if="setup.modes.length > 1" class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Metode bayar") }}
								<select v-model="mode" class="h-10 text-sm border border-gray-300 rounded px-2">
									<option v-for="m in setup.modes" :key="m" :value="m">{{ m }}</option>
								</select>
							</label>
							<div v-if="rekening" class="rounded bg-gray-50 border border-gray-200 px-2 py-1.5 text-xs text-gray-600">
								{{ __("Ke rekening") }} · {{ __("sesuai metode bayar") }}
								<div class="text-sm font-semibold text-gray-900">
									{{ rekening.bank }} {{ rekening.nomor }}
									<template v-if="rekening.atas_nama">· {{ rekening.atas_nama }}</template>
								</div>
							</div>
							<p v-else-if="mode" class="rounded bg-amber-50 border border-amber-200 px-2 py-1.5 text-xs text-amber-800">
								{{ __("Rekening {0} belum diatur. Hubungi accounting.", [mode]) }}
							</p>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Nama pengirim") }}
								<input v-model="pengirim" type="text" class="h-10 text-sm border border-gray-300 rounded px-2" />
							</label>
							<div class="grid grid-cols-2 gap-2">
								<label class="flex flex-col gap-0.5 text-xs text-gray-600">
									{{ __("Tanggal") }}
									<input v-model="tanggal" type="date" class="h-10 text-sm border border-gray-300 rounded px-2" />
								</label>
								<label class="flex flex-col gap-0.5 text-xs text-gray-600">
									{{ __("No. referensi") }}
									<input v-model="referensi" type="text" class="h-10 text-sm border border-gray-300 rounded px-2" />
								</label>
							</div>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Foto bukti (opsional)") }}
								<input type="file" accept="image/*,application/pdf" class="text-xs" :disabled="uploading" @change="uploadBukti" />
								<span v-if="uploading" class="text-gray-500">{{ __("Mengunggah…") }}</span>
								<span v-else-if="bukti" class="text-green-700">{{ __("Bukti terlampir") }}</span>
							</label>

							<div class="border-t border-gray-200 pt-2 flex flex-col gap-1 text-sm">
								<div class="flex justify-between"><span class="text-gray-600">{{ __("Tagihan dipilih") }}</span><span class="font-semibold">{{ formatCurrency(allocated) }}</span></div>
								<div class="flex justify-between"><span class="text-gray-600">{{ __("Nominal transfer") }}</span><span class="font-semibold">{{ formatCurrency(nominal || 0) }}</span></div>
								<div :class="['rounded px-2 py-1.5 flex flex-col', diffClass]">
									<span class="font-semibold">{{ diffTitle }}</span>
									<span class="text-xs">{{ diffNote }}</span>
								</div>
							</div>
							<Button
								variant="solid"
								size="lg"
								:loading="saving"
								:disabled="!canSave"
								@click="save"
							>
								{{ __("Simpan pembayaran") }}
							</Button>
						</section>
					</div>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { useToast } from "@/composables/useToast";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

// nextend Treasury: one transfer for several COD notes and Sales Orders.
// nextend.treasury.transfer makes one Payment Entry per document (down
// payment for an order), keeps any excess as the customer's advance, and one
// Transfer Pelanggan for treasury to check in the bank app.
const METHOD = "nextend.treasury.transfer";

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, default: "" },
	currency: { type: String, default: "IDR" },
	initialCustomer: { type: [Object, String], default: null },
});
const emit = defineEmits(["update:modelValue", "print-invoice"]);
const show = computed({
	get: () => props.modelValue,
	set: (v) => emit("update:modelValue", v),
});
const { showError, showSuccess } = useToast();

const setup = ref({ modes: [], rekening_mode: {}, today: "" });
const customer = ref(null);
const search = ref("");
const results = ref([]);
const bills = ref([]);
const loadingBills = ref(false);
const nominal = ref(null);
const nominalTouched = ref(false);
const mode = ref("");
const pengirim = ref("");
const tanggal = ref("");
const referensi = ref("");
const bukti = ref("");
const uploading = ref(false);
const saving = ref(false);
const done = ref(null);

const rekening = computed(() => setup.value.rekening_mode?.[mode.value] || null);
const formatCurrency = (v) => formatCurrencyUtil(Number(v || 0), props.currency);
const round = (v) => Math.round(Number(v || 0) * 100) / 100;

const allocated = computed(() => round(bills.value.filter((b) => b.checked).reduce((s, b) => s + Number(b.amount || 0), 0)));
const diff = computed(() => round(Number(nominal.value || 0) - allocated.value));
const overBill = computed(() => bills.value.some((b) => b.checked && Number(b.amount || 0) > b.sisa + 0.005));
const diffTitle = computed(() => {
	if (overBill.value) return __("Bayar melebihi sisa tagihan");
	if (diff.value === 0) return __("Pas");
	if (diff.value > 0) return __("Lebih {0} → uang muka customer", [formatCurrency(diff.value)]);
	return __("Kurang {0}", [formatCurrency(-diff.value)]);
});
const diffNote = computed(() => {
	if (overBill.value) return __("Turunkan nominal bayar tagihan yang melebihi sisanya.");
	if (diff.value === 0) return __("Seluruh transfer terbagi ke tagihan.");
	if (diff.value > 0)
		return __("Disimpan sebagai saldo customer di {0} dan bisa dipakai di belanja berikutnya.", [
			rekening.value?.company || "",
		]);
	return __("Kurangi nominal bayar salah satu tagihan sampai pas dengan transfer.");
});
const diffClass = computed(() =>
	overBill.value || diff.value < 0
		? "bg-red-50 text-red-800"
		: diff.value > 0
			? "bg-blue-50 text-blue-800"
			: "bg-green-50 text-green-800"
);
const canSave = computed(
	() =>
		!saving.value &&
		!uploading.value &&
		customer.value &&
		mode.value &&
		allocated.value > 0 &&
		Number(nominal.value || 0) > 0 &&
		diff.value >= 0 &&
		!overBill.value
);

watch(show, async (open) => {
	if (!open) return;
	try {
		setup.value = await call(`${METHOD}.get_kasir_setup`, { pos_profile: props.posProfile });
	} catch (error) {
		showError(error.message || __("Pengaturan transfer tidak bisa dimuat."));
	}
	reset();
	const initial = props.initialCustomer;
	if (initial && (initial.name || typeof initial === "string")) {
		pickCustomer(
			typeof initial === "string" ? { name: initial, customer_name: initial } : initial
		);
	}
});

function reset() {
	done.value = null;
	customer.value = null;
	bills.value = [];
	results.value = [];
	search.value = "";
	nominal.value = null;
	nominalTouched.value = false;
	mode.value = setup.value.modes[0] || "";
	pengirim.value = "";
	tanggal.value = setup.value.today || new Date().toISOString().slice(0, 10);
	referensi.value = "";
	bukti.value = "";
}

let searchTimer;
function searchSoon() {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(runSearch, 300);
}
async function runSearch() {
	const term = search.value.trim();
	if (term.length < 2) {
		results.value = [];
		return;
	}
	try {
		results.value = await call("pos_next.api.customers.get_customers", {
			search_term: term,
			pos_profile: props.posProfile,
			limit: 10,
		});
	} catch (error) {
		showError(error.message);
	}
}

async function pickCustomer(c) {
	customer.value = { name: c.name, customer_name: c.customer_name || c.name };
	results.value = [];
	pengirim.value = customer.value.customer_name;
	loadingBills.value = true;
	try {
		const data = await call(`${METHOD}.get_open_bills`, { customer: c.name, pos_profile: props.posProfile });
		customer.value.customer_name = data.customer_name || customer.value.customer_name;
		pengirim.value = customer.value.customer_name;
		bills.value = data.bills.map((b) => ({ ...b, checked: false, amount: null }));
	} catch (error) {
		showError(error.message);
	} finally {
		loadingBills.value = false;
	}
}
function clearCustomer() {
	customer.value = null;
	bills.value = [];
}

function toggle(b) {
	b.amount = b.checked ? b.sisa : null;
}
// The transfer amount follows the bills picked until the cashier types it.
watch(allocated, (total) => {
	if (!nominalTouched.value) nominal.value = total || null;
});

async function uploadBukti(event) {
	const file = event.target.files?.[0];
	if (!file) return;
	uploading.value = true;
	try {
		const form = new FormData();
		form.append("file", file, file.name);
		form.append("is_private", "1");
		const res = await fetch("/api/method/upload_file", {
			method: "POST",
			headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token },
			body: form,
		});
		const data = await res.json();
		if (!res.ok || !data.message?.file_url) throw new Error(data.exception || res.statusText);
		bukti.value = data.message.file_url;
	} catch {
		bukti.value = "";
		showError(__("Bukti transfer gagal diunggah. Pembayaran tetap bisa disimpan tanpa bukti."));
	} finally {
		uploading.value = false;
	}
}

async function save() {
	saving.value = true;
	try {
		const chosen = bills.value.filter((b) => b.checked && Number(b.amount) > 0);
		const result = await call(`${METHOD}.receive_transfer`, {
			customer: customer.value.name,
			pos_profile: props.posProfile,
			mode_of_payment: mode.value,
			nominal: Number(nominal.value),
			allocations: chosen.map((b) => ({ doctype: b.doctype, name: b.name, amount: Number(b.amount) })),
			pengirim: pengirim.value.trim(),
			tanggal: tanggal.value,
			referensi: referensi.value.trim(),
			bukti: bukti.value || null,
		});
		done.value = {
			...result,
			nominal: Number(nominal.value),
			invoices: chosen.filter((b) => b.doctype === "Sales Invoice").map((b) => b.name),
		};
		showSuccess(__("Pembayaran transfer tersimpan."));
	} catch (error) {
		showError(error.message || __("Pembayaran gagal disimpan."));
	} finally {
		saving.value = false;
	}
}
</script>
