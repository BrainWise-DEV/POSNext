<template>
	<span :title="title" class="inline-flex">
		<button
			type="button"
			:disabled="disabled"
			:class="buttonClass"
			@click="$emit('click')"
		>
			<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
				/>
			</svg>
		</button>
	</span>
</template>

<script setup>
defineProps({
	disabled: { type: Boolean, default: false },
	buttonClass: { type: String, required: true },
	title: { type: String, default: "" },
});

defineEmits(["click"]);
</script>
