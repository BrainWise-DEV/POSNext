<template>
	<div class="flex gap-2 w-full">
		<button
			type="button"
			class="flex-1 h-11 rounded-lg bg-gray-100 text-gray-800 text-sm font-medium hover:bg-gray-200 active:bg-gray-300 transition-colors touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0b63ce] focus-visible:ring-offset-1"
			@click="$emit('cancel')"
		>
			{{ __("Cancel") }}
		</button>
		<button
			type="button"
			class="flex-1 h-11 rounded-lg bg-[#0b63ce] text-white text-sm font-semibold hover:bg-[#0a56b3] active:bg-[#094a9a] disabled:opacity-40 disabled:cursor-not-allowed transition-colors touch-manipulation inline-flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0b63ce] focus-visible:ring-offset-2"
			:disabled="disabled"
			@click="$emit('confirm')"
		>
			{{ confirmText || __("Confirm") }}
			<kbd
				class="hidden sm:inline-flex items-center rounded border border-white/40 px-1 text-[11px] font-normal leading-4 text-white/80"
				aria-hidden="true"
			>↵</kbd>
		</button>
	</div>
</template>

<script setup>
/** Shared Cancel / Confirm footer for the unit, variant, batch and serial pickers. */
defineProps({
	disabled: Boolean,
	confirmText: String,
});

defineEmits(["cancel", "confirm"]);
</script>
