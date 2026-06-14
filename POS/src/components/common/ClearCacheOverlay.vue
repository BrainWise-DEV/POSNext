<template>
	<Teleport to="body">
		<Transition name="overlay">
			<div
				v-if="show"
				class="fixed inset-0 z-[9999] flex items-center justify-center"
			>
				<!-- Backdrop -->
				<div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>

				<!-- Content Card -->
				<div class="relative z-10">
					<Transition name="card" mode="out-in">
						<div
							v-if="!isClearing"
							key="confirm"
							class="bg-white rounded-2xl shadow-2xl p-8 max-w-md mx-4 transform"
						>
							<!-- Icon -->
							<div class="flex justify-center mb-6">
								<div class="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center">
									<svg
										class="w-10 h-10 text-red-600"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
										/>
									</svg>
								</div>
							</div>

							<!-- Title & Message -->
							<h3 class="text-2xl font-bold text-gray-900 text-center mb-3">
								{{ __('Clear Cache?') }}
							</h3>
							<p class="text-gray-600 text-center mb-8 leading-relaxed">
								{{ __('This will clear all cached items, customers, and stock data. Invoices and drafts will be preserved.') }}
							</p>

							<!-- Buttons -->
							<div class="flex gap-3">
								<button
									@click="$emit('cancel')"
									class="flex-1 px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-xl transition-all active:scale-95"
								>
									{{ __('Cancel') }}
								</button>
								<button
									@click="handleConfirm"
									class="flex-1 px-6 py-3 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-all active:scale-95 shadow-lg shadow-red-500/30"
								>
									{{ __('Clear Cache') }}
								</button>
							</div>
						</div>

						<!-- Clearing Animation -->
						<div
							v-else
							key="clearing"
							class="bg-white rounded-2xl shadow-2xl p-12 max-w-md mx-4 transform"
						>
							<div class="flex flex-col items-center">
								<!-- Animated Icon Container -->
								<div class="relative mb-6">
									<!-- Outer spinning ring -->
									<div class="w-24 h-24 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin"></div>

									<!-- Inner icon -->
									<div class="absolute inset-0 flex items-center justify-center">
										<svg
											class="w-10 h-10 text-blue-600 animate-pulse"
											fill="currentColor"
											viewBox="0 0 24 24"
										>
											<path d="M12 2C8.13 2 5 3.12 5 4.5V7c0 1.38 3.13 2.5 7 2.5S19 8.38 19 7V4.5C19 3.12 15.87 2 12 2zM5 9v3c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V9c0 1.38-3.13 2.5-7 2.5S5 10.38 5 9zm0 5v3c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5v-3c0 1.38-3.13 2.5-7 2.5S5 15.38 5 14z"/>
										</svg>
									</div>
								</div>

								<!-- Text -->
								<h3 class="text-xl font-bold text-gray-900 mb-2">
									{{ __('Clearing Cache...') }}
								</h3>
								<p class="text-gray-500 text-center">
									{{ __('Please wait while we clear your cached data') }}
								</p>

								<!-- Progress dots animation -->
								<div class="flex gap-2 mt-6">
									<div class="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
									<div class="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
									<div class="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
								</div>
							</div>
						</div>
					</Transition>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
	show: {
		type: Boolean,
		default: false
	}
})

const emit = defineEmits(['cancel', 'confirm'])

const isClearing = ref(false)

function handleConfirm() {
	isClearing.value = true
	emit('confirm')
}

// Reset state when overlay is closed
function reset() {
	isClearing.value = false
}

// Expose reset method to parent
defineExpose({ reset })
</script>

<style scoped>
/* Overlay transitions */
.overlay-enter-active,
.overlay-leave-active {
	transition: opacity 0.3s ease;
}

.overlay-enter-from,
.overlay-leave-to {
	opacity: 0;
}

.overlay-enter-active .absolute:first-child {
	transition: backdrop-filter 0.3s ease;
}

/* Card transitions */
.card-enter-active,
.card-leave-active {
	transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.card-enter-from {
	opacity: 0;
	transform: scale(0.9) translateY(-20px);
}

.card-leave-to {
	opacity: 0;
	transform: scale(0.9) translateY(20px);
}

/* Bounce animation for dots */
@keyframes bounce {
	0%, 100% {
		transform: translateY(0);
	}
	50% {
		transform: translateY(-10px);
	}
}

.animate-bounce {
	animation: bounce 0.6s ease-in-out infinite;
}
</style>
