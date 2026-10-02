<template>
	<div
		class="relative h-screen w-screen overflow-hidden bg-gray-50 text-gray-900 select-none"
		:class="{ 'cursor-none': !controlsVisible }"
		@pointermove="revealControls"
		@pointerdown="revealControls"
	>
		<Transition name="cd-fade" mode="out-in">
			<!-- Welcome (idle) -->
			<div
				v-if="view === 'welcome'"
				key="welcome"
				class="h-full flex flex-col items-center justify-center gap-10 p-8 bg-gradient-to-br from-blue-50 via-white to-indigo-50"
			>
				<div
					class="w-28 h-28 sm:w-32 sm:h-32 rounded-3xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-xl flex items-center justify-center"
				>
					<svg class="w-16 h-16 sm:w-20 sm:h-20 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.75" :d="cartIcon" />
					</svg>
				</div>

				<div class="text-center">
					<h1 class="text-4xl sm:text-5xl font-bold text-gray-900">{{ __("Welcome") }}</h1>
					<p v-if="storeName" class="mt-3 text-xl sm:text-2xl text-gray-500">{{ storeName }}</p>
				</div>

				<div class="text-center">
					<div class="flex items-baseline justify-center gap-3 tabular-nums">
						<span class="text-7xl sm:text-8xl lg:text-9xl font-bold text-gray-900 leading-none">{{ clock.time }}</span>
						<span v-if="clock.period" class="text-3xl sm:text-4xl font-semibold text-gray-500">{{ clock.period }}</span>
					</div>
					<p class="mt-4 text-xl sm:text-2xl text-gray-500">{{ clock.date }}</p>
				</div>
			</div>

			<!-- Cart (items being purchased) -->
			<div v-else-if="view === 'cart'" key="cart" class="h-full flex flex-col">
				<header class="flex items-center justify-between gap-4 px-6 py-4 bg-white border-b border-gray-200 shadow-sm">
					<div class="flex items-center gap-3 min-w-0">
						<div
							class="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-md flex items-center justify-center flex-shrink-0"
						>
							<svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="cartIcon" />
							</svg>
						</div>
						<div class="min-w-0">
							<h1 class="text-xl sm:text-2xl font-bold truncate">{{ __("Your Order") }}</h1>
							<p v-if="storeName" class="text-sm text-gray-500 truncate">{{ storeName }}</p>
						</div>
					</div>
					<div class="text-xl sm:text-2xl font-semibold text-gray-700 tabular-nums whitespace-nowrap">
						{{ clock.time }} {{ clock.period }}
					</div>
				</header>

				<div class="flex-1 min-h-0 flex flex-col lg:flex-row">
					<!-- Items -->
					<ul ref="itemList" class="flex-1 min-h-0 overflow-y-auto bg-white divide-y divide-gray-100">
						<li
							v-for="item in cart.items"
							:key="item.key"
							class="flex items-start justify-between gap-4 px-6 py-4"
						>
							<div class="min-w-0">
								<p class="text-lg sm:text-xl font-semibold text-gray-900 truncate">{{ item.name }}</p>
								<p class="text-base text-gray-500 tabular-nums">
									{{ item.quantity }} {{ item.uom }}<template v-if="!item.isFree"> × {{ item.rate }}</template>
								</p>
								<p v-if="item.freeQuantity" class="text-sm font-semibold text-green-600">
									{{ __("+{0} FREE", [item.freeQuantity]) }}
								</p>
								<p v-if="item.discount" class="text-sm font-semibold text-green-600">
									{{ __("You save {0}", [item.discount]) }}
								</p>
							</div>
							<p v-if="item.isFree" class="text-lg sm:text-xl font-bold text-green-600 whitespace-nowrap">{{ __("FREE") }}</p>
							<p v-else class="text-lg sm:text-xl font-bold text-gray-900 tabular-nums whitespace-nowrap">{{ item.amount }}</p>
						</li>
					</ul>

					<!-- Totals -->
					<aside
						class="lg:w-[420px] flex-shrink-0 flex flex-col justify-end gap-3 p-6 bg-gray-50 border-t lg:border-t-0 lg:border-s border-gray-200 text-lg"
					>
						<div class="flex items-center justify-between text-gray-600">
							<span>{{ __("Total Quantity") }}</span>
							<span class="font-semibold text-gray-900 tabular-nums">{{ cart.totalQuantity }}</span>
						</div>
						<div class="flex items-center justify-between text-gray-600">
							<span>{{ __("Subtotal") }}</span>
							<span class="font-semibold text-gray-900 tabular-nums">{{ cart.subtotal }}</span>
						</div>
						<div v-if="cart.discount" class="flex items-center justify-between text-green-700">
							<span>{{ __("Discount") }}</span>
							<span class="font-semibold tabular-nums">-{{ cart.discount }}</span>
						</div>
						<div v-if="cart.tax" class="flex items-center justify-between text-gray-600">
							<span>{{ __("Tax") }}</span>
							<span class="font-semibold text-gray-900 tabular-nums">{{ cart.tax }}</span>
						</div>
						<div class="mt-2 rounded-2xl bg-gradient-to-r from-blue-500 to-blue-600 p-5 text-white shadow-lg">
							<p class="text-lg font-medium opacity-90">{{ __("Grand Total") }}</p>
							<p class="text-4xl sm:text-5xl font-bold tabular-nums break-all">{{ cart.grandTotal }}</p>
						</div>
					</aside>
				</div>
			</div>

			<!-- Payment complete -->
			<div
				v-else
				key="complete"
				class="h-full flex flex-col items-center justify-center gap-6 p-8 text-center bg-gradient-to-br from-green-50 via-white to-emerald-50"
			>
				<div class="cd-pop w-28 h-28 sm:w-32 sm:h-32 rounded-full bg-green-500 shadow-xl flex items-center justify-center">
					<svg class="w-16 h-16 sm:w-20 sm:h-20 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
					</svg>
				</div>

				<h1 class="text-6xl sm:text-7xl font-extrabold text-green-600">{{ __("Thank You!") }}</h1>
				<p class="text-2xl sm:text-3xl font-medium text-gray-700">{{ __("Your Purchase is Complete") }}</p>

				<div class="mt-4 min-w-[320px] rounded-2xl bg-white px-10 py-6 shadow-lg border border-green-100">
					<p class="text-lg font-medium uppercase tracking-wide text-gray-500">{{ __("Amount Paid") }}</p>
					<p class="mt-1 text-5xl sm:text-6xl font-bold text-gray-900 tabular-nums">{{ payment.paidAmount }}</p>

					<div class="mt-5 pt-4 border-t border-gray-100 flex flex-wrap justify-center gap-x-8 gap-y-2 text-lg sm:text-xl text-gray-600">
						<span>
							{{ __("Grand Total") }}:
							<strong class="text-gray-900 tabular-nums">{{ payment.grandTotal }}</strong>
						</span>
						<span v-if="payment.changeAmount">
							{{ __("Change Due") }}:
							<strong class="text-green-600 tabular-nums">{{ payment.changeAmount }}</strong>
						</span>
						<span v-if="payment.outstandingAmount">
							{{ __("Balance Due") }}:
							<strong class="text-orange-600 tabular-nums">{{ payment.outstandingAmount }}</strong>
						</span>
					</div>
				</div>
			</div>
		</Transition>

		<!-- Fullscreen toggle (browsers only allow fullscreen from a click) -->
		<button
			type="button"
			class="fixed bottom-4 end-4 p-3 rounded-full bg-white/90 text-gray-600 shadow-md transition-opacity"
			:class="controlsVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'"
			:title="isFullscreen ? __('Exit Fullscreen') : __('Enter Fullscreen')"
			:aria-label="isFullscreen ? __('Exit Fullscreen') : __('Enter Fullscreen')"
			@click="toggleFullscreen"
		>
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					:d="isFullscreen ? exitFullscreenIcon : enterFullscreenIcon"
				/>
			</svg>
		</button>
	</div>
</template>

<script setup>
import { DEFAULT_LOCALE } from "@/utils/currency"
import {
	DisplayMessage,
	PAYMENT_COMPLETE_DURATION_MS,
	openCustomerDisplayChannel,
} from "@/utils/customerDisplay"
import { logger } from "@/utils/logger"
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"

const log = logger.create("CustomerDisplayPage")

const cart = ref(null)
const payment = ref(null)
const showingPaymentComplete = ref(false)
const itemList = ref(null)
const isFullscreen = ref(false)
const controlsVisible = ref(false)
const now = ref(new Date())

let channel = null
let clockTimer = null
let paymentCompleteTimer = null
let paidCartCleared = true
let controlsTimer = null

const CONTROLS_IDLE_MS = 3000

const hasItems = computed(() => cart.value?.items?.length > 0)
const storeName = computed(() => cart.value?.storeName || "")

const view = computed(() => {
	if (showingPaymentComplete.value) return "complete"
	if (hasItems.value) return "cart"
	return "welcome"
})

// =============================================================================
// Clock
// =============================================================================

const timeFormatter = new Intl.DateTimeFormat(DEFAULT_LOCALE, {
	hour: "numeric",
	minute: "2-digit",
})
const dateFormatter = new Intl.DateTimeFormat(DEFAULT_LOCALE, {
	weekday: "long",
	year: "numeric",
	month: "long",
	day: "numeric",
})

// Split AM/PM out so it can be rendered smaller than the digits
const clock = computed(() => {
	const parts = timeFormatter.formatToParts(now.value)
	return {
		time: parts
			.filter((part) => part.type !== "dayPeriod")
			.map((part) => part.value)
			.join("")
			.trim(),
		period: parts.find((part) => part.type === "dayPeriod")?.value || "",
		date: dateFormatter.format(now.value),
	}
})

// =============================================================================
// Messages from the POS window
// =============================================================================

function handleMessage({ type, payload }) {
	switch (type) {
		case DisplayMessage.POS_READY:
			channel.post(DisplayMessage.DISPLAY_READY)
			break
		case DisplayMessage.CART_UPDATED:
			cart.value = payload
			if (!hasItems.value) {
				paidCartCleared = true
			} else if (paidCartCleared) {
				// Cashier started the next sale - skip the rest of the thank-you screen
				dismissPaymentComplete()
			}
			break
		case DisplayMessage.PAYMENT_COMPLETED:
			showPaymentComplete(payload)
			break
	}
}

function showPaymentComplete(details) {
	payment.value = details
	showingPaymentComplete.value = true
	// Updates still carrying the paid items may arrive before the POS clears its cart
	paidCartCleared = false
	clearTimeout(paymentCompleteTimer)
	paymentCompleteTimer = setTimeout(
		dismissPaymentComplete,
		PAYMENT_COMPLETE_DURATION_MS,
	)
}

function dismissPaymentComplete() {
	clearTimeout(paymentCompleteTimer)
	showingPaymentComplete.value = false
}

// Keep the newest item in view as the cashier scans
watch(
	() => cart.value?.items?.length || 0,
	async (count, previousCount) => {
		if (count <= previousCount) return
		await nextTick()
		if (itemList.value) itemList.value.scrollTop = itemList.value.scrollHeight
	},
)

// =============================================================================
// Fullscreen
// =============================================================================

function toggleFullscreen() {
	if (document.fullscreenElement) {
		document.exitFullscreen()
	} else {
		document.documentElement.requestFullscreen?.().catch((error) => {
			log.warn("Fullscreen request failed", error)
		})
	}
}

function syncFullscreen() {
	isFullscreen.value = !!document.fullscreenElement
}

// Customer-facing screen: only show controls (and the cursor) while the mouse is in use
function revealControls() {
	controlsVisible.value = true
	clearTimeout(controlsTimer)
	controlsTimer = setTimeout(() => {
		controlsVisible.value = false
	}, CONTROLS_IDLE_MS)
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
	document.title = __("Customer Display")

	channel = openCustomerDisplayChannel(handleMessage)
	if (channel) {
		channel.post(DisplayMessage.DISPLAY_READY)
	} else {
		log.warn("BroadcastChannel not supported - customer display cannot connect")
	}

	clockTimer = setInterval(() => {
		now.value = new Date()
	}, 1000)

	document.addEventListener("fullscreenchange", syncFullscreen)
	// Show the fullscreen button briefly so the cashier can find it after opening
	revealControls()
})

onUnmounted(() => {
	channel?.close()
	clearInterval(clockTimer)
	clearTimeout(paymentCompleteTimer)
	clearTimeout(controlsTimer)
	document.removeEventListener("fullscreenchange", syncFullscreen)
})

// SVG Path Icons
const cartIcon =
	"M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
const enterFullscreenIcon = "M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4"
const exitFullscreenIcon = "M8 4v4H4M16 4v4h4M8 20v-4H4M16 20v-4h4"
</script>

<style scoped>
.cd-fade-enter-active,
.cd-fade-leave-active {
	transition: opacity 0.25s ease;
}

.cd-fade-enter-from,
.cd-fade-leave-to {
	opacity: 0;
}

.cd-pop {
	animation: cd-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes cd-pop {
	from {
		opacity: 0;
		transform: scale(0.4);
	}
	to {
		opacity: 1;
		transform: scale(1);
	}
}
</style>
