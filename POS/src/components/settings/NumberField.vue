<template>
	<div class="p-2 rounded hover:bg-gray-50 transition-colors">
		<label :for="fieldId" class="block text-sm font-medium text-gray-900 mb-1">
			{{ label }}
		</label>
		<input
			:id="fieldId"
			type="number"
			:value="modelValue"
			:min="min"
			:max="max"
			:step="step"
			@input="$emit('update:modelValue', parseFloat($event.target.value) || 0)"
			class="w-full px-2.5 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-transparent bg-white"
		/>
		<p v-if="description" class="text-xs text-gray-500 mt-0.5 leading-tight">
			{{ description }}
		</p>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	modelValue: {
		type: Number,
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
	min: {
		type: Number,
		default: undefined,
	},
	max: {
		type: Number,
		default: undefined,
	},
	step: {
		type: Number,
		default: 1,
	},
})

defineEmits(["update:modelValue"])

const fieldId = computed(
	() => `number-${Math.random().toString(36).substr(2, 9)}`,
)
</script>
