<template>
	<Dialog v-model="show" :options="{ title: __('Pemakaian Tinta'), size: '3xl' }">
		<template #body-content>
			<div class="flex flex-col gap-3 text-start">
				<div class="flex items-center gap-2">
					<select
						v-model="warehouse"
						class="flex-1 h-8 text-sm border border-gray-300 rounded px-2"
						:aria-label="__('Gudang')"
					>
						<option v-for="wh in warehouses" :key="wh" :value="wh">{{ wh }}</option>
					</select>
					<Button variant="subtle" :loading="loadingList" @click="loadUploads">
						{{ __("Refresh") }}
					</Button>
				</div>

				<!-- New upload -->
				<div class="border border-gray-200 rounded-lg p-3 flex flex-col gap-2">
					<div class="text-sm font-semibold text-gray-900">{{ __("Upload Baru") }}</div>
					<div class="flex flex-wrap items-end gap-2">
						<label class="text-xs text-gray-600 flex flex-col gap-1">
							{{ __("Periode Dari") }}
							<input
								v-model="periodeDari"
								type="date"
								class="h-8 text-sm border border-gray-300 rounded px-2"
							/>
						</label>
						<label class="text-xs text-gray-600 flex flex-col gap-1">
							{{ __("Periode Sampai") }}
							<input
								v-model="periodeSampai"
								type="date"
								class="h-8 text-sm border border-gray-300 rounded px-2"
							/>
						</label>
						<a
							:href="templateUrl"
							class="h-8 inline-flex items-center px-3 text-sm rounded bg-gray-100 hover:bg-gray-200 text-gray-800"
						>
							{{ __("Download Template") }}
						</a>
						<input
							ref="fileInput"
							type="file"
							accept=".xlsx,.csv"
							class="text-sm"
							@change="onFileChosen"
						/>
					</div>
					<p class="text-xs text-gray-500">
						{{
							__(
								"Isi kolom Qty Keluar dengan total pemakaian periode ini dalam satuan di template. Baris kosong dianggap tidak dipakai."
							)
						}}
					</p>
					<p v-if="error" class="text-sm text-red-600">{{ error }}</p>
					<div v-if="previewing" class="text-sm text-gray-500">{{ __("Membaca file...") }}</div>
				</div>

				<!-- Preview -->
				<div v-if="preview" class="border border-gray-200 rounded-lg p-3 flex flex-col gap-2">
					<div class="flex flex-wrap items-center gap-3 text-sm">
						<span class="font-semibold">{{ __("Preview") }}</span>
						<span class="text-green-700">✓ {{ preview.summary.ok }} OK</span>
						<span class="text-yellow-700">⚠ {{ preview.summary.warning }} {{ __("peringatan") }}</span>
						<span class="text-red-700">✗ {{ preview.summary.error }} error</span>
					</div>
					<ul v-if="preview.errors.length" class="text-sm text-red-600 list-disc ps-5">
						<li v-for="message in preview.errors" :key="message">{{ message }}</li>
					</ul>
					<div v-if="preview.rows.length" class="max-h-72 overflow-y-auto">
						<table class="w-full text-xs">
							<thead class="text-gray-500 border-b border-gray-200">
								<tr>
									<th class="py-1 pe-2 text-start">{{ __("Baris") }}</th>
									<th class="py-1 pe-2 text-start">{{ __("Item") }}</th>
									<th class="py-1 pe-2 text-end">{{ __("Qty") }}</th>
									<th class="py-1 text-start">{{ __("Status") }}</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="row in preview.rows"
									:key="row.row_no"
									class="border-b border-gray-50 align-top"
									:class="ROW_CLASS[row.status]"
								>
									<td class="py-1 pe-2">{{ row.row_no }}</td>
									<td class="py-1 pe-2">
										<div class="font-medium text-gray-900">{{ row.item_code || "-" }}</div>
										<div class="text-gray-500">{{ row.item_name || "" }}</div>
									</td>
									<td class="py-1 pe-2 text-end whitespace-nowrap">
										{{ row.qty === false ? "?" : row.qty }} {{ row.stock_uom || "" }}
									</td>
									<td class="py-1">
										<span v-if="row.status === 'ok'">✓</span>
										<div v-for="message in row.messages" :key="message">
											{{ row.status === "error" ? "✗" : "⚠" }} {{ message }}
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div class="flex justify-end gap-2">
						<Button variant="subtle" @click="resetUpload">{{ __("Batal") }}</Button>
						<Button
							theme="blue"
							variant="solid"
							:disabled="!preview.can_submit"
							:loading="submitting"
							@click="submitUpload"
						>
							{{ __("Ajukan") }}
						</Button>
					</div>
					<p v-if="!preview.can_submit" class="text-xs text-red-600">
						{{ __("Perbaiki error di file lalu upload ulang.") }}
					</p>
				</div>

				<!-- History -->
				<div class="flex flex-col gap-2">
					<div class="text-sm font-semibold text-gray-900">{{ __("Riwayat Upload") }}</div>
					<div v-if="!uploads.length" class="text-sm text-gray-500">
						{{ __("Belum ada upload untuk gudang ini.") }}
					</div>
					<div
						v-for="upload in uploads"
						:key="upload.name"
						class="border border-gray-200 rounded-lg p-2 flex items-start justify-between gap-2"
					>
						<div class="min-w-0">
							<div class="text-sm font-semibold text-gray-900">{{ upload.name }}</div>
							<div class="text-xs text-gray-500">
								{{ upload.periode_dari }} – {{ upload.periode_sampai }} ·
								{{ __("{0} tinta", [upload.rows]) }}
								<template v-if="upload.pending">
									· {{ __("{0} pending", [upload.pending]) }}
								</template>
							</div>
							<div v-if="upload.alasan_tolak" class="text-xs text-red-600">
								{{ upload.alasan_tolak }}
							</div>
						</div>
						<span
							class="text-[11px] font-semibold px-2 py-0.5 rounded whitespace-nowrap"
							:class="STATUS_CLASS[upload.status] || 'bg-gray-100 text-gray-700'"
						>
							{{ upload.status }}
						</span>
					</div>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

const METHOD = "nextend.pemakaian_tinta";
const ROW_CLASS = { error: "bg-red-50", warning: "bg-yellow-50", ok: "" };
const STATUS_CLASS = {
	Diajukan: "bg-blue-100 text-blue-700",
	Memproses: "bg-orange-100 text-orange-700",
	"Ada Pending": "bg-yellow-100 text-yellow-800",
	Selesai: "bg-green-100 text-green-700",
	Ditolak: "bg-red-100 text-red-700",
	Gagal: "bg-red-100 text-red-700",
};

const props = defineProps({
	modelValue: Boolean,
	warehouses: { type: Array, default: () => [] },
	defaultWarehouse: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const show = ref(props.modelValue);
const warehouse = ref("");
const periodeDari = ref("");
const periodeSampai = ref("");
const fileUrl = ref("");
const fileInput = ref(null);
const preview = ref(null);
const previewing = ref(false);
const submitting = ref(false);
const error = ref("");
const uploads = ref([]);
const loadingList = ref(false);

const templateUrl = computed(
	() => `/api/method/${METHOD}.download_template?warehouse=${encodeURIComponent(warehouse.value)}`
);

watch(
	() => props.modelValue,
	(value) => {
		show.value = value;
		if (value) {
			warehouse.value = props.warehouses.includes(props.defaultWarehouse)
				? props.defaultWarehouse
				: props.warehouses[0] || "";
			resetUpload();
			loadUploads();
		}
	}
);
watch(show, (value) => emit("update:modelValue", value));
watch(warehouse, () => {
	resetUpload();
	loadUploads();
});
watch([periodeDari, periodeSampai], () => {
	if (fileUrl.value) runPreview();
});

function messageOf(err) {
	return err?.messages?.join("\n") || err?.message || String(err);
}

async function loadUploads() {
	if (!warehouse.value) return;
	loadingList.value = true;
	try {
		uploads.value = (await call(`${METHOD}.list_uploads`, { warehouse: warehouse.value })) || [];
	} catch (err) {
		error.value = messageOf(err);
	} finally {
		loadingList.value = false;
	}
}

function resetUpload() {
	fileUrl.value = "";
	preview.value = null;
	error.value = "";
	if (fileInput.value) fileInput.value.value = "";
}

async function uploadFile(file) {
	const form = new FormData();
	form.append("file", file, file.name);
	form.append("is_private", "1");
	const response = await fetch("/api/method/upload_file", {
		method: "POST",
		body: form,
		headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
	});
	const data = await response.json();
	if (!response.ok) throw new Error(data?.exception || __("Upload gagal"));
	return data.message.file_url;
}

async function onFileChosen(event) {
	const file = event.target.files?.[0];
	preview.value = null;
	error.value = "";
	if (!file) return;
	if (!periodeDari.value || !periodeSampai.value) {
		error.value = __("Isi periode dulu sebelum memilih file.");
		event.target.value = "";
		return;
	}
	previewing.value = true;
	try {
		fileUrl.value = await uploadFile(file);
	} catch (err) {
		error.value = messageOf(err);
		previewing.value = false;
		return;
	}
	await runPreview();
}

async function runPreview() {
	previewing.value = true;
	error.value = "";
	try {
		preview.value = await call(`${METHOD}.preview_upload`, {
			warehouse: warehouse.value,
			periode_dari: periodeDari.value,
			periode_sampai: periodeSampai.value,
			file_url: fileUrl.value,
		});
	} catch (err) {
		preview.value = null;
		error.value = messageOf(err);
	} finally {
		previewing.value = false;
	}
}

async function submitUpload() {
	submitting.value = true;
	try {
		await call(`${METHOD}.submit_upload`, {
			warehouse: warehouse.value,
			periode_dari: periodeDari.value,
			periode_sampai: periodeSampai.value,
			file_url: fileUrl.value,
		});
		resetUpload();
		periodeDari.value = "";
		periodeSampai.value = "";
		await loadUploads();
	} catch (err) {
		error.value = messageOf(err);
	} finally {
		submitting.value = false;
	}
}
</script>
