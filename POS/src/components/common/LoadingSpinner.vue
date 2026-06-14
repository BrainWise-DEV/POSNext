<template>
	<div class="flex-1 flex items-center justify-center bg-gray-50">
		<div class="text-center">
			<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
			<p v-if="text" class="mt-4 text-sm text-gray-500">{{ text }}</p>
		</div>
	</div>
</template>

<script setup>
defineProps({
	text: {
		type: String,
		default: __("Loading..."),
	},
})
</script>
