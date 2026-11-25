<template>
	<div
		class="flex items-center gap-3 rounded-xl border px-3 py-3 sm:px-4"
		:class="toneClasses.frame"
		data-testid="customer-identity"
	>
		<div
			class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-pos-md font-semibold"
			:class="toneClasses.avatar"
			aria-hidden="true"
		>
			<template v-if="initials">{{ initials }}</template>
			<svg v-else class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
				<circle cx="12" cy="8" r="4" />
				<path d="M4 21c0-4 4-6 8-6s8 2 8 6" stroke-linecap="round" />
			</svg>
		</div>
		<div class="min-w-0 flex-1">
			<p v-if="name" class="line-clamp-2 break-words text-pos-lg font-semibold leading-snug text-pos-ink" :title="name">{{ name }}</p>
			<p v-else class="truncate text-pos-lg text-gray-400">{{ placeholder }}</p>
			<p class="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-pos-sm text-pos-muted">
				<span v-if="phone" dir="ltr" class="whitespace-nowrap tabular-nums">{{ phone }}</span>
				<span v-if="id" dir="ltr" class="whitespace-nowrap tabular-nums">{{ id }}</span>
			</p>
			<!-- Narrow screens: the badge sits under the name so the name keeps its width -->
			<span
				v-if="badge"
				class="mt-1.5 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium sm:hidden"
				:class="badge.classes"
			>
				<svg v-if="badge.check" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M5 12l5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
				</svg>
				{{ badge.label }}
			</span>
		</div>
		<span
			v-if="badge"
			class="hidden flex-shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex"
			:class="badge.classes"
		>
			<svg v-if="badge.check" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
				<path d="M5 12l5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
			{{ badge.label }}
		</span>
	</div>
</template>

<script setup>
/**
 * CustomerIdentityStrip - the customer as the cart will show them: initials, name,
 * mobile and ID, with an optional status badge. Used for the customer being edited,
 * the one being created, and an existing customer found as a duplicate.
 */
import { computed } from "vue";

const props = defineProps({
	name: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	phone: { type: String, default: "" },
	id: { type: String, default: "" },
	/** "verified" | "unverified" | "" */
	status: { type: String, default: "" },
	/** "default" | "caution" | "success" */
	tone: { type: String, default: "default" },
});

const initials = computed(() => {
	const parts = (props.name || "").trim().split(/\s+/).filter(Boolean);
	return parts
		.slice(0, 2)
		.map((p) => Array.from(p)[0])
		.join("")
		.toUpperCase();
});

const toneClasses = computed(() => {
	if (props.tone === "caution") {
		return { frame: "border-amber-300 bg-amber-50", avatar: "bg-amber-100 text-pos-caution" };
	}
	if (props.tone === "success") {
		return { frame: "border-green-200 bg-green-50", avatar: "bg-green-100 text-pos-saving" };
	}
	return { frame: "border-pos-line bg-pos-surface", avatar: "bg-pos-action-soft text-pos-action" };
});

const badge = computed(() => {
	if (props.status === "verified") {
		return { label: __("Email verified"), classes: "bg-green-50 text-pos-saving", check: true };
	}
	if (props.status === "unverified") {
		return { label: __("Email not verified"), classes: "bg-pos-panel text-pos-muted" };
	}
	return null;
});
</script>
