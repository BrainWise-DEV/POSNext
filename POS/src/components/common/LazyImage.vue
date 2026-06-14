<template>
	<div ref="targetRef" :class="containerClasses">
		<!-- Placeholder while loading -->
		<div
			v-if="!isLoaded"
			:class="[
				'absolute inset-0 bg-gray-100 flex items-center justify-center',
				placeholderClass,
			]"
		>
			<slot name="placeholder">
				<!-- Default placeholder: animated gradient -->
				<div
					class="absolute inset-0 bg-gradient-to-r from-gray-100 via-gray-200 to-gray-100 animate-pulse"
				></div>
			</slot>
		</div>

		<!-- Actual image (only loads when visible) -->
		<img
			v-if="isVisible"
			:src="src"
			:alt="alt"
			:class="[
				'transition-opacity duration-300',
				isLoaded ? 'opacity-100' : 'opacity-0',
				imgClass,
			]"
			@load="handleLoad"
			@error="handleError"
			:loading="nativeLazy ? 'lazy' : 'eager'"
		/>

		<!-- Error state -->
		<div
			v-if="error"
			:class="['absolute inset-0 bg-gray-100 flex items-center justify-center', errorClass]"
		>
			<slot name="error">
				<!-- Default error icon -->
				<svg
					class="w-8 h-8 text-gray-400"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
					/>
				</svg>
			</slot>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { useLazyLoad } from "@/composables/useLazyLoad"

const props = defineProps({
	src: {
		type: String,
		required: true,
	},
	alt: {
		type: String,
		default: "",
	},
	containerClass: {
		type: String,
		default: "",
	},
	imgClass: {
		type: String,
		default: "w-full h-full object-cover",
	},
	placeholderClass: {
		type: String,
		default: "",
	},
	errorClass: {
		type: String,
		default: "",
	},
	rootMargin: {
		type: String,
		default: "50px",
	},
	threshold: {
		type: Number,
		default: 0.01,
	},
	// Use native loading="lazy" as fallback for browsers without Intersection Observer
	nativeLazy: {
		type: Boolean,
		default: true,
	},
})

const emit = defineEmits(["load", "error"])

const baseContainerClass = "relative overflow-hidden"
const containerClasses = computed(() => {
	const userClasses = props.containerClass?.trim()
	return userClasses
		? `${baseContainerClass} ${userClasses}`
		: baseContainerClass
})

const { targetRef, isVisible, isLoaded, error } = useLazyLoad({
	rootMargin: props.rootMargin,
	threshold: props.threshold,
})

function handleLoad(event) {
	error.value = null
	isLoaded.value = true
	emit("load", event)
}

function handleError(event) {
	error.value = event
	isLoaded.value = true
	emit("error", event)
}
</script>

<style scoped>
@keyframes shimmer {
	0% {
		background-position: -200% 0;
	}
	100% {
		background-position: 200% 0;
	}
}

.animate-pulse {
	animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>
