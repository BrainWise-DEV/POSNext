<template>
	<div class="p-2 rounded hover:bg-gray-50 transition-colors">
		<label :for="fieldId" class="block text-sm font-medium text-gray-900 mb-1">
			{{ label }}
		</label>
		<select
			:id="fieldId"
			:value="modelValue"
			@change="$emit('update:modelValue', $event.target.value)"
			class="w-full px-2.5 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-transparent bg-white cursor-pointer"
		>
			<option value="">{{ __('-- Select --') }}</option>
			<option
				v-for="option in options"
				:key="option.value"
				:value="option.value"
			>
				{{ option.label }}
			</option>
		</select>
		<p v-if="description" class="text-xs text-gray-500 mt-0.5 leading-tight">
			{{ description }}
		</p>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	modelValue: {
		type: [String, Number],
		default: "",
	},
	label: {
		type: String,
		required: true,
	},
	description: {
		type: String,
		default: "",
	},
	options: {
		type: Array,
		default: () => [],
	},
})

defineEmits(["update:modelValue"])

const fieldId = computed(
	() => `select-${Math.random().toString(36).substr(2, 9)}`,
)
</script>
