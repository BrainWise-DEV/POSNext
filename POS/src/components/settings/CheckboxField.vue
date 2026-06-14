<template>
	<div class="flex items-start gap-2.5 p-2 rounded hover:bg-gray-50 transition-colors">
		<div class="flex items-center h-5">
			<input
				:id="fieldId"
				type="checkbox"
				:checked="modelValue"
				@change="$emit('update:modelValue', $event.target.checked ? 1 : 0)"
				class="w-4 h-4 text-blue-600 bg-white border-gray-300 rounded focus:ring-blue-500 focus:ring-1 cursor-pointer"
			/>
		</div>
		<div class="flex-1 min-w-0">
			<label :for="fieldId" class="block text-sm font-medium text-gray-900 cursor-pointer">
				{{ label }}
			</label>
			<p v-if="description" class="text-xs text-gray-500 mt-0.5 leading-tight">
				{{ description }}
			</p>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	modelValue: {
		type: [Number, Boolean],
		default: 0,
	},
	label: {
		type: String,
		required: true,
	},
	description: {
		type: String,
		default: "",
	},
})

defineEmits(["update:modelValue"])

const fieldId = computed(
	() => `checkbox-${Math.random().toString(36).substr(2, 9)}`,
)
</script>
