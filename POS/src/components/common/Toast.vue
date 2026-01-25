<template>
	<Teleport to="body">
		<Transition :name="isRTL ? 'toast-slide-rtl' : 'toast-slide-ltr'">
			<div
				v-if="showToast && toastNotification"
				class="fixed top-4 end-4 z-[9999] max-w-md"
			>
				<div
					:class="[
						'rounded-lg shadow-xl p-4 flex items-start gap-3',
						toastStyles.container
					]"
				>
					<div class="flex-shrink-0">
						<FeatherIcon
							:name="toastStyles.icon"
							:class="['w-5 h-5', toastStyles.iconColor]"
						/>
					</div>
					<div class="flex-1 min-w-0">
						<p :class="['text-sm font-semibold', toastStyles.titleColor]">
							{{ toastNotification.title }}
						</p>
						<p :class="['text-sm mt-1', toastStyles.messageColor]">
							{{ toastNotification.message }}
						</p>
					</div>
					<button
						@click="hideToast"
						class="flex-shrink-0"
					>
						<FeatherIcon
							name="x"
							:class="['w-4 h-4', toastStyles.closeColor]"
						/>
					</button>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { computed } from "vue"
import { useToast } from "@/composables/useToast"
import { useLocale } from "@/composables/useLocale"
import { FeatherIcon } from "frappe-ui"

const { toastNotification, showToast, hideToast } = useToast()
const { isRTL } = useLocale()

// Toast type to style mapping
const TOAST_TYPE_STYLES = {
	success: {
		container: "bg-green-50 border-s-4 border-green-500",
		icon: "check-circle",
		iconColor: "text-green-600",
		titleColor: "text-green-900",
		messageColor: "text-green-700",
		closeColor: "text-green-600 hover:text-green-900",
	},
	error: {
		container: "bg-red-50 border-s-4 border-red-500",
		icon: "x-circle",
		iconColor: "text-red-600",
		titleColor: "text-red-900",
		messageColor: "text-red-700",
		closeColor: "text-red-600 hover:text-red-900",
	},
	warning: {
		container: "bg-orange-50 border-s-4 border-orange-500",
		icon: "alert-circle",
		iconColor: "text-orange-600",
		titleColor: "text-orange-900",
		messageColor: "text-orange-700",
		closeColor: "text-orange-600 hover:text-orange-900",
	},
	info: {
		container: "bg-blue-50 border-s-4 border-blue-500",
		icon: "info",
		iconColor: "text-blue-600",
		titleColor: "text-blue-900",
		messageColor: "text-blue-700",
		closeColor: "text-blue-600 hover:text-blue-900",
	},
}

// Default styles fallback
const DEFAULT_STYLES = TOAST_TYPE_STYLES.info

const toastStyles = computed(() => {
	if (!toastNotification.value) return DEFAULT_STYLES
	return TOAST_TYPE_STYLES[toastNotification.value.type] || DEFAULT_STYLES
})
</script>

<style scoped>
/* Common transition timing */
.toast-slide-ltr-enter-active,
.toast-slide-ltr-leave-active,
.toast-slide-rtl-enter-active,
.toast-slide-rtl-leave-active {
	transition: all 0.3s ease;
}

/* LTR: slide from right (end side) */
.toast-slide-ltr-enter-from,
.toast-slide-ltr-leave-to {
	opacity: 0;
	transform: translateX(100%);
}

/* RTL: slide from left (end side in RTL) */
.toast-slide-rtl-enter-from,
.toast-slide-rtl-leave-to {
	opacity: 0;
	transform: translateX(-100%);
}
</style>
