<script setup>
/**
 * GiftCardCreatedDialog.vue
 *
 * Dialog to display gift card information after creation via item sale.
 * Shows code, value, and validity of newly created gift cards.
 */

import { computed } from 'vue'

const props = defineProps({
	open: {
		type: Boolean,
		default: false,
	},
	giftCards: {
		type: Array,
		default: () => [],
	},
	currency: {
		type: String,
		default: 'CHF',
	},
})

const emit = defineEmits(['close', 'print'])

const hasGiftCards = computed(() => props.giftCards.length > 0)

function formatDate(dateStr) {
	if (!dateStr) return __('No expiry')
	const date = new Date(dateStr)
	return date.toLocaleDateString()
}

function formatAmount(amount) {
	return new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: props.currency,
	}).format(amount || 0)
}

function handleClose() {
	emit('close')
}

function handlePrint(giftCard) {
	emit('print', giftCard)
}

function copyToClipboard(code) {
	navigator.clipboard.writeText(code).catch((err) => {
		console.error('Failed to copy:', err)
	})
}
</script>

<template>
	<Teleport to="body">
		<Transition name="modal">
			<div
				v-if="open && hasGiftCards"
				class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
				@click.self="handleClose"
			>
				<div
					class="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden"
				>
					<!-- Header -->
					<div class="bg-gradient-to-r from-emerald-500 to-teal-600 px-6 py-4 text-white">
						<div class="flex items-center justify-between">
							<div class="flex items-center gap-3">
								<div class="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
									<svg
										class="w-5 h-5"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"
										/>
									</svg>
								</div>
								<div>
									<h2 class="text-lg font-semibold">
										{{ __('Gift Card Created') }}
									</h2>
									<p class="text-sm text-white/80">
										{{ giftCards.length === 1
											? __('A gift card has been created')
											: __('%s gift cards have been created', [giftCards.length])
										}}
									</p>
								</div>
							</div>
							<button
								class="text-white/80 hover:text-white transition-colors"
								@click="handleClose"
							>
								<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						</div>
					</div>

					<!-- Content -->
					<div class="px-6 py-4 max-h-[60vh] overflow-y-auto">
						<div
							v-for="(giftCard, index) in giftCards"
							:key="giftCard.coupon_code"
							:class="[
								'rounded-xl border-2 border-dashed border-emerald-200 bg-emerald-50/50 p-4',
								index > 0 ? 'mt-4' : ''
							]"
						>
							<!-- Code Display -->
							<div class="text-center mb-4">
								<p class="text-xs text-gray-500 uppercase tracking-wider mb-1">
									{{ __('Code') }}
								</p>
								<div class="flex items-center justify-center gap-2">
									<span class="text-2xl font-mono font-bold text-emerald-700 tracking-wider">
										{{ giftCard.coupon_code }}
									</span>
									<button
										class="p-1.5 rounded-md hover:bg-emerald-100 transition-colors"
										:title="__('Copy to clipboard')"
										@click="copyToClipboard(giftCard.coupon_code)"
									>
										<svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
										</svg>
									</button>
								</div>
							</div>

							<!-- Details Grid -->
							<div class="grid grid-cols-2 gap-3">
								<!-- Value -->
								<div class="bg-white rounded-lg p-3 text-center shadow-sm">
									<p class="text-xs text-gray-500 mb-1">{{ __('Value') }}</p>
									<p class="text-lg font-semibold text-gray-800">
										{{ formatAmount(giftCard.gift_card_amount || giftCard.original_gift_card_amount) }}
									</p>
								</div>

								<!-- Valid Until -->
								<div class="bg-white rounded-lg p-3 text-center shadow-sm">
									<p class="text-xs text-gray-500 mb-1">{{ __('Valid Until') }}</p>
									<p class="text-lg font-semibold text-gray-800">
										{{ formatDate(giftCard.valid_upto) }}
									</p>
								</div>
							</div>
						</div>
					</div>

					<!-- Footer -->
					<div class="px-6 py-4 bg-gray-50 border-t border-gray-100 flex justify-end gap-3">
						<button
							class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
							@click="handleClose"
						>
							{{ __('Close') }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
	transition: opacity 0.2s ease;
}

.modal-enter-active .bg-white,
.modal-leave-active .bg-white {
	transition: transform 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
	opacity: 0;
}

.modal-enter-from .bg-white,
.modal-leave-to .bg-white {
	transform: scale(0.95);
}
</style>
