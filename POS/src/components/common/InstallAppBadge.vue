<template>
	<!-- Install App Banner - Native Browser Style -->
	<Transition
		enter-active-class="transition-all duration-300 ease-out"
		enter-from-class="opacity-0 -translate-y-full"
		enter-to-class="opacity-100 translate-y-0"
		leave-active-class="transition-all duration-200 ease-in"
		leave-from-class="opacity-100 translate-y-0"
		leave-to-class="opacity-0 -translate-y-full"
	>
		<div
			v-if="showBadge"
			class="lg:hidden fixed top-0 start-0 end-0 bg-white border-b border-gray-200 shadow-md z-[250]"
			role="dialog"
			aria-labelledby="install-banner-title"
		>
			<div class="px-3 py-2.5">
				<div class="flex items-center gap-2">
					<!-- App Icon -->
					<div class="flex-shrink-0">
						<div class="w-10 h-10 rounded-lg flex items-center justify-center shadow-sm" style="background-color: #4F46E5;">
							<svg class="w-6 h-6" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
								<path fill="#ffffff" d="M20 7h-4V4c0-1.1-.9-2-2-2h-4c-1.1 0-2 .9-2 2v3H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zM10 4h4v3h-4V4zm10 16H4V9h16v11z"/>
							</svg>
						</div>
					</div>

					<!-- Text Content -->
					<div class="flex-1 min-w-0 me-2">
						<h3 id="install-banner-title" class="text-xs font-semibold mb-0.5 leading-tight" style="color: #111827;">
							{{ __('Install POSNext') }}
						</h3>
						<p class="text-[10px] leading-tight mb-1" style="color: #4B5563;">
							{{ __('Faster access and offline support') }}
						</p>
						<button
							@click="handleSnooze"
							class="text-[10px] underline hover:no-underline transition-all"
							style="color: #6B7280;"
						>
							{{ __('Snooze for 7 days') }}
						</button>
					</div>

					<!-- Action Buttons -->
					<div class="flex items-center gap-1.5 flex-shrink-0">
						<button
							@click="handleInstall"
							class="px-3 py-1.5 text-xs font-medium rounded hover:opacity-90 active:opacity-80 transition-opacity touch-manipulation shadow-sm whitespace-nowrap"
							style="background-color: #4F46E5; color: #ffffff;"
						>
							{{  __('Install') }}
						</button>
						<button
							@click="handleDismiss"
							class="p-1.5 hover:bg-gray-100 rounded transition-colors touch-manipulation flex-shrink-0"
							style="color: #6B7280;"
							:aria-label="__('Close')"
							:title="__('Close (shows again next session)')"
						>
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
							</svg>
						</button>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { usePWAInstall } from "@/composables/usePWAInstall"
import { computed } from "vue"

const { showInstallBadge, promptInstall, dismissBadge, snoozeBadge } =
	usePWAInstall()

const showBadge = computed(() => showInstallBadge.value)

const handleInstall = async () => {
	await promptInstall()
}

const handleDismiss = () => {
	dismissBadge()
}

const handleSnooze = () => {
	snoozeBadge()
}
</script>
