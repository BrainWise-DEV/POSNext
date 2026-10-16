<template>
	<Dialog v-model="show" :options="{ title: doc ? doc.title : __('Panduan'), size: '4xl' }">
		<template #body-content>
			<div class="text-start">
				<div v-if="error" class="text-sm text-red-600 mb-2">{{ error }}</div>

				<template v-if="doc">
					<button
						class="text-sm text-blue-600 hover:underline mb-3"
						@click="doc = null"
					>
						← {{ __("Daftar panduan") }}
					</button>
					<!-- Written by a System Manager in nextend's Nextend Doc; may contain <video> -->
					<div class="panduan-article" @click="followLink" v-html="doc.html"></div>
				</template>

				<template v-else>
					<div v-if="loading" class="text-sm text-gray-500">{{ __("Memuat...") }}</div>
					<div v-else-if="loadError" class="text-sm text-red-600">{{ loadError }}</div>
					<div v-else-if="!categories.length" class="text-sm text-gray-500">
						{{ __("Belum ada panduan.") }}
					</div>
					<div v-for="category in categories" :key="category.label" class="mb-4">
						<div class="text-xs font-semibold uppercase text-gray-500 mb-1">
							{{ category.label }}
						</div>
						<button
							v-for="entry in category.entries"
							:key="entry.name"
							class="w-full text-start px-3 py-2 text-sm rounded hover:bg-gray-100 border-b border-gray-100"
							@click="open(entry.name)"
						>
							{{ entry.title }}
						</button>
					</div>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";

// Docs listed for POS by nextend.panduan (Nextend Doc with "Tampil di POS")
const props = defineProps({
	modelValue: Boolean,
	categories: { type: Array, default: () => [] },
	loading: Boolean,
	loadError: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});
const doc = ref(null);
const error = ref("");

watch(show, (open) => {
	if (open) {
		doc.value = null;
		error.value = "";
	}
});

async function open(name) {
	error.value = "";
	try {
		doc.value = await call("nextend.panduan.read_doc", { name });
	} catch (e) {
		error.value = e?.message || __("Panduan tidak bisa dibuka.");
	}
}

// Links to other docs (/nextend/docs/<slug>, or the old .../<category>/<file>.md)
// open inside the dialog instead of leaving the POS
function followLink(event) {
	const a = event.target.closest("a");
	const path = a && new URL(a.href, window.location.origin).pathname;
	if (!path || !path.startsWith("/nextend/docs/")) return;
	event.preventDefault();
	open(decodeURIComponent(path.split("/").pop().replace(/\.md$/, "")));
}
</script>

<style scoped>
.panduan-article {
	font-size: 0.9rem;
	line-height: 1.6;
	color: #1f2937;
}
.panduan-article :deep(h2) {
	font-size: 1.1rem;
	font-weight: 600;
	margin: 1.2rem 0 0.4rem;
}
.panduan-article :deep(h3) {
	font-weight: 600;
	margin: 1rem 0 0.4rem;
}
.panduan-article :deep(p),
.panduan-article :deep(ul),
.panduan-article :deep(ol),
.panduan-article :deep(table) {
	margin-bottom: 0.75rem;
}
.panduan-article :deep(ul) {
	list-style: disc;
	padding-inline-start: 1.25rem;
}
.panduan-article :deep(ol) {
	list-style: decimal;
	padding-inline-start: 1.25rem;
}
.panduan-article :deep(a) {
	color: #2563eb;
	text-decoration: underline;
}
.panduan-article :deep(code) {
	background: #f3f4f6;
	padding: 0.1em 0.3em;
	border-radius: 4px;
}
.panduan-article :deep(video),
.panduan-article :deep(img) {
	max-width: 100%;
	height: auto;
	border-radius: 8px;
}
.panduan-article :deep(.ql-ui) {
	display: none;
}
.panduan-article :deep(li[data-list="bullet"]) {
	list-style-type: disc;
}
.panduan-article :deep(.ql-indent-1) {
	margin-inline-start: 1.5rem;
}
.panduan-article :deep(.ql-indent-2) {
	margin-inline-start: 3rem;
}
.panduan-article :deep(.ql-align-center) {
	text-align: center;
}
.panduan-article :deep(video),
.panduan-article :deep(iframe.ql-video) {
	display: block;
	width: 100%;
	aspect-ratio: 16 / 9;
	border: 0;
	border-radius: 8px;
}
.panduan-article :deep(table) {
	display: block;
	overflow-x: auto;
	border-collapse: collapse;
	font-size: 0.8rem;
}
.panduan-article :deep(th),
.panduan-article :deep(td) {
	border: 1px solid #e5e7eb;
	padding: 4px 8px;
	vertical-align: top;
}
</style>
