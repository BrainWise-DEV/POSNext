<template>
	<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg border" :class="badgeClasses">
		<svg v-if="icon" class="w-4 h-4" :class="iconClasses" :fill="iconFill" stroke="currentColor" viewBox="0 0 24 24">
			<path :stroke-linecap="strokeLinecap" :stroke-linejoin="strokeLinejoin" :stroke-width="strokeWidth" :d="icon"/>
		</svg>
		<div v-if="label || value" :class="textSize">
			<span v-if="label" class="text-gray-600">{{ label }}</span>
			<span v-if="value" class="font-semibold text-gray-900" :class="{ 'ms-1': label }">{{ value }}</span>
		</div>
		<span v-else class="font-semibold text-gray-900" :class="textSize">{{ text }}</span>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	variant: {
		type: String,
		default: "blue", // blue, green, orange, red, gray
		validator: (value) =>
			["blue", "green", "orange", "red", "gray"].includes(value),
	},
	icon: {
		type: String,
		default: null,
	},
	iconFill: {
		type: String,
		default: "none",
	},
	strokeLinecap: {
		type: String,
		default: "round",
	},
	strokeLinejoin: {
		type: String,
		default: "round",
	},
	strokeWidth: {
		type: String,
		default: "2",
	},
	text: {
		type: String,
		default: "",
	},
	label: {
		type: String,
		default: null,
	},
	value: {
		type: String,
		default: null,
	},
	size: {
		type: String,
		default: "sm", // xs, sm, md
		validator: (value) => ["xs", "sm", "md"].includes(value),
	},
})

const badgeClasses = computed(() => {
	const variants = {
		blue: "bg-blue-50 border-blue-100",
		green: "bg-green-50 border-green-100",
		orange: "bg-orange-50 border-orange-100",
		red: "bg-red-50 border-red-100",
		gray: "bg-gray-50 border-gray-100",
	}
	return variants[props.variant] || variants.blue
})

const iconClasses = computed(() => {
	const variants = {
		blue: "text-blue-600",
		green: "text-green-600",
		orange: "text-orange-600",
		red: "text-red-600",
		gray: "text-gray-600",
	}
	return variants[props.variant] || variants.blue
})

const textSize = computed(() => {
	const sizes = {
		xs: "text-xs",
		sm: "text-sm",
		md: "text-base",
	}
	return sizes[props.size] || sizes.sm
})
</script>
