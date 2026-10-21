<template>
	<Dialog v-model="show" :options="{ title: __('Transfer shift ini'), size: '3xl' }">
		<template #body-content>
			<div class="flex flex-col gap-3 text-start">
				<p class="text-xs text-gray-600">
					{{
						__(
							"Customer membayar beberapa transaksi dengan satu transfer? Centang transaksinya lalu gabungkan, supaya treasury mengecek satu nominal yang sama dengan di aplikasi bank."
						)
					}}
				</p>

				<div class="flex items-center justify-between gap-2">
					<span class="text-xs text-gray-500">
						{{ loading ? __("Memuat…") : __("{0} transfer", [rows.length]) }}
					</span>
					<Button variant="subtle" :loading="loading" @click="load">{{ __("Muat ulang") }}</Button>
				</div>

				<p v-if="!loading && !rows.length" class="text-sm text-gray-500 rounded bg-gray-50 p-3">
					{{ __("Belum ada pembayaran transfer di shift ini.") }}
				</p>

				<div class="flex flex-col gap-2">
					<div
						v-for="r in rows"
						:key="r.name"
						:class="[
							'rounded-lg p-2.5 flex flex-col gap-1.5',
							picked[r.name] ? 'border-2 border-blue-500 bg-blue-50' : 'border border-gray-200 bg-white',
						]"
					>
						<label class="flex gap-2 items-start" :class="r.bisa_diubah ? 'cursor-pointer' : 'cursor-default'">
							<input
								v-model="picked[r.name]"
								type="checkbox"
								class="mt-0.5 w-5 h-5 shrink-0"
								:disabled="!r.bisa_diubah"
								:aria-label="__('Pilih {0}', [r.nama_pengirim])"
							/>
							<span class="flex flex-col gap-0.5 min-w-0 flex-1">
								<span class="flex flex-wrap items-baseline justify-between gap-x-3">
									<span class="text-sm font-semibold text-gray-900 truncate">{{ r.nama_pengirim }}</span>
									<span class="text-sm font-bold text-gray-900">{{ formatCurrency(r.total) }}</span>
								</span>
								<span class="text-xs text-gray-500">
									{{ rekeningText(r.rekening) }} · {{ r.tanggal_transfer }}
									<template v-if="r.customer_name && r.customer_name !== r.nama_pengirim">
										· {{ r.customer_name }}
									</template>
								</span>
								<span class="flex flex-wrap items-center gap-1">
									<span :class="['text-[11px] font-bold rounded-full px-2', statusClass(r)]">{{ statusText(r) }}</span>
									<span v-if="r.gabungan" class="text-[11px] font-bold rounded-full px-2 bg-indigo-100 text-indigo-800">
										{{ __("Gabungan") }}
									</span>
								</span>
							</span>
						</label>
						<ul class="ms-7 flex flex-col gap-0.5">
							<li v-for="d in r.dokumen" :key="d.reference_name" class="flex flex-wrap items-center gap-x-2 text-xs text-gray-600">
								<span class="font-mono">{{ d.keterangan || d.reference_name }}</span>
								<span class="text-[11px] font-bold rounded-full px-2 bg-gray-100 text-gray-700">{{ d.company }}</span>
								<span class="ms-auto">{{ formatCurrency(d.amount) }}</span>
							</li>
						</ul>
						<p v-if="r.status === 'Ditolak' && r.alasan_tolak" class="ms-7 text-xs text-red-700">
							{{ __("Alasan: {0}", [r.alasan_tolak]) }}
						</p>
						<div v-if="r.gabungan && r.bisa_diubah" class="ms-7">
							<Button variant="ghost" size="sm" :loading="splitting === r.name" @click="split(r)">
								{{ __("Pisahkan lagi") }}
							</Button>
						</div>
					</div>
				</div>

				<!-- Gabungkan -->
				<section
					v-if="chosen.length"
					class="sticky bottom-0 rounded-lg border border-gray-300 bg-white p-3 flex flex-col gap-2 shadow-sm"
				>
					<div class="flex flex-wrap items-baseline justify-between gap-2">
						<span class="text-sm font-semibold text-gray-900">
							{{ __("{0} transfer dipilih", [chosen.length]) }}
						</span>
						<span class="text-lg font-bold text-gray-900">{{ formatCurrency(chosenTotal) }}</span>
					</div>
					<p v-if="mixedAccounts" class="rounded bg-red-50 text-red-800 text-xs px-2 py-1.5">
						{{ __("Rekening tujuannya berbeda. Satu transfer hanya masuk ke satu rekening, jadi tidak bisa digabung.") }}
					</p>
					<template v-else-if="chosen.length > 1">
						<p class="text-xs text-gray-600">
							{{ __("Cocokkan dengan bukti transfer customer: nominalnya harus {0}.", [formatCurrency(chosenTotal)]) }}
						</p>
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Nama pengirim") }}
								<input v-model="pengirim" type="text" class="h-10 text-sm border border-gray-300 rounded px-2" />
							</label>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Tanggal transfer") }}
								<input v-model="tanggal" type="date" class="h-10 text-sm border border-gray-300 rounded px-2" />
							</label>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("No. referensi (opsional)") }}
								<input v-model="referensi" type="text" class="h-10 text-sm border border-gray-300 rounded px-2" />
							</label>
							<label class="flex flex-col gap-0.5 text-xs text-gray-600">
								{{ __("Foto bukti (opsional)") }}
								<input type="file" accept="image/*,application/pdf" class="text-xs" :disabled="uploading" @change="uploadBukti" />
								<span v-if="uploading" class="text-gray-500">{{ __("Mengunggah…") }}</span>
								<span v-else-if="bukti" class="text-green-700">{{ __("Bukti terlampir") }}</span>
							</label>
						</div>
					</template>
					<p v-else class="text-xs text-gray-600">{{ __("Pilih minimal dua transfer untuk digabung.") }}</p>
					<Button variant="solid" size="lg" :loading="merging" :disabled="!canMerge" @click="merge">
						{{ __("Gabungkan jadi satu transfer") }}
					</Button>
				</section>
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

// nextend Treasury: every transfer payment already becomes a Transfer
// Pelanggan for treasury. When one bank transfer paid several sales (e.g. the
// customer's own note and a neighbour's), the cashier merges them here so
// treasury checks the one amount that shows in the bank app.
const METHOD = "nextend.treasury.transfer";

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, default: "" },
	currency: { type: String, default: "IDR" },
});
const emit = defineEmits(["update:modelValue"]);
const show = computed({
	get: () => props.modelValue,
	set: (v) => emit("update:modelValue", v),
});
const { showError, showSuccess } = useToast();

const rows = ref([]);
const loading = ref(false);
const picked = ref({});
const pengirim = ref("");
const tanggal = ref("");
const referensi = ref("");
const bukti = ref("");
const uploading = ref(false);
const merging = ref(false);
const splitting = ref("");

const formatCurrency = (v) => formatCurrencyUtil(Number(v || 0), props.currency);
const round = (v) => Math.round(Number(v || 0) * 100) / 100;

const chosen = computed(() => rows.value.filter((r) => picked.value[r.name]));
const chosenTotal = computed(() => round(chosen.value.reduce((s, r) => s + Number(r.total || 0), 0)));
const mixedAccounts = computed(() => new Set(chosen.value.map((r) => r.rekening_tujuan || "")).size > 1);
const canMerge = computed(
	() => chosen.value.length > 1 && !mixedAccounts.value && !merging.value && !uploading.value
);

// The sender defaults to the first picked transfer's; the cashier overwrites it
// with the name on the customer's transfer proof.
watch(
	() => chosen.value[0]?.name,
	() => {
		const first = chosen.value[0];
		pengirim.value = first?.nama_pengirim || "";
		tanggal.value = first?.tanggal_transfer || "";
	}
);

watch(show, (open) => {
	if (open) load();
});

async function load() {
	loading.value = true;
	try {
		const data = await call(`${METHOD}.list_shift_transfers`, { pos_profile: props.posProfile });
		rows.value = data.rows || [];
		picked.value = {};
		referensi.value = "";
		bukti.value = "";
	} catch (error) {
		showError(error.message || __("Transfer shift ini tidak bisa dimuat."));
	} finally {
		loading.value = false;
	}
}

function rekeningText(r) {
	return r ? [r.bank, r.nomor].filter(Boolean).join(" ") : __("Rekening belum diatur");
}

function statusText(r) {
	if (r.perlu_diperiksa) return __("Perlu diperiksa treasury");
	if (r.status === "Belum dicek" && (r.bank_transaction || r.kredit_serupa)) return __("Sedang dicocokkan treasury");
	return __(r.status);
}

function statusClass(r) {
	if (r.status === "Ditolak" || r.perlu_diperiksa) return "bg-red-100 text-red-800";
	if (r.status === "Diterima") return "bg-green-100 text-green-800";
	return "bg-amber-100 text-amber-800";
}

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
		showError(__("Bukti transfer gagal diunggah. Transfer tetap bisa digabung tanpa bukti."));
	} finally {
		uploading.value = false;
	}
}

async function merge() {
	merging.value = true;
	try {
		const result = await call(`${METHOD}.merge_transfers`, {
			names: chosen.value.map((r) => r.name),
			pos_profile: props.posProfile,
			pengirim: pengirim.value.trim(),
			tanggal: tanggal.value,
			referensi: referensi.value.trim(),
			bukti: bukti.value || null,
		});
		showSuccess(__("Digabung: satu transfer {0} untuk treasury.", [formatCurrency(result.total)]));
		await load();
	} catch (error) {
		showError(error.message || __("Transfer gagal digabung."));
	} finally {
		merging.value = false;
	}
}

async function split(r) {
	splitting.value = r.name;
	try {
		await call(`${METHOD}.split_transfer`, { name: r.name, pos_profile: props.posProfile });
		showSuccess(__("Transfer dipisah lagi per transaksi."));
		await load();
	} catch (error) {
		showError(error.message || __("Transfer gagal dipisah."));
	} finally {
		splitting.value = "";
	}
}
</script>
