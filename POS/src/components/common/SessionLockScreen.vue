<template>
	<Teleport to="body">
		<Transition name="lock-overlay">
			<div
				v-if="isLocked"
				class="fixed inset-0 z-[10000] flex items-center justify-center"
			>
				<!-- Backdrop -->
				<div class="absolute inset-0 bg-black/70 backdrop-blur-md"></div>

				<!-- Lock Card -->
				<div class="relative z-10 w-full max-w-sm mx-4">
					<div class="bg-white rounded-2xl shadow-2xl p-8">
						<!-- Lock Icon -->
						<div class="flex justify-center mb-5">
							<div class="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center">
								<svg
									class="w-8 h-8 text-amber-600"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
									/>
								</svg>
							</div>
						</div>

						<!-- User Info -->
						<div class="text-center mb-6">
							<!-- Avatar -->
							<div class="flex justify-center mb-3">
								<img
									v-if="lockedUser?.image"
									:src="lockedUser.image"
									:alt="lockedUser.name"
									class="w-14 h-14 rounded-full object-cover border-2 border-gray-200"
								/>
								<div
									v-else
									class="w-14 h-14 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-lg border-2 border-blue-500"
								>
									{{ lockedUser?.initials || '??' }}
								</div>
							</div>
							<h3 class="text-lg font-bold text-gray-900">
								{{ lockedUser?.name || __('User') }}
							</h3>
							<p class="text-sm text-gray-500 mt-1">
								{{ __('Session Locked') }}
							</p>
						</div>

						<!-- Password Form -->
						<form @submit.prevent="handleUnlock" class="space-y-4">
							<div>
								<label class="block text-sm font-medium text-gray-700 mb-1.5">
									{{ __('Password') }}
								</label>
								<div class="relative">
									<input
										ref="passwordInputRef"
										v-model="password"
										:type="showPassword ? 'text' : 'password'"
										:placeholder="__('Enter your password')"
										:disabled="isVerifying"
										class="block w-full rounded-lg border px-3 py-2.5 pe-10 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
										:class="verifyError ? 'border-red-400 bg-red-50' : 'border-gray-300'"
										autocomplete="current-password"
									/>
									<button
										type="button"
										@click="showPassword = !showPassword"
										class="absolute inset-y-0 end-0 flex items-center pe-3 text-gray-500 hover:text-gray-700 transition-colors focus:outline-none"
										:disabled="isVerifying"
										tabindex="-1"
										:aria-label="showPassword ? __('Hide password') : __('Show password')"
									>
										<svg
											v-if="!showPassword"
											class="w-4.5 h-4.5"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
										</svg>
										<svg
											v-else
											class="w-4.5 h-4.5"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
										>
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
										</svg>
									</button>
								</div>
								<!-- Error Message -->
								<p v-if="verifyError" class="mt-1.5 text-sm text-red-600">
									{{ verifyError }}
								</p>
							</div>

							<!-- Unlock Button -->
							<button
								type="submit"
								:disabled="!password || isVerifying"
								class="w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm rounded-lg shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
							>
								<span v-if="isVerifying" class="flex items-center justify-center gap-2">
									<svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
									</svg>
									{{ __('Verifying...') }}
								</span>
								<span v-else>{{ __('Unlock') }}</span>
							</button>
						</form>

						<!-- Divider -->
						<div class="relative my-5">
							<div class="absolute inset-0 flex items-center">
								<div class="w-full border-t border-gray-200"></div>
							</div>
							<div class="relative flex justify-center text-xs">
								<span class="bg-white px-3 text-gray-400">{{ __('or') }}</span>
							</div>
						</div>

						<!-- Sign Out Button -->
						<button
							@click="handleSignOut"
							:disabled="isVerifying"
							class="w-full px-4 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium text-sm rounded-lg transition-colors disabled:opacity-50"
						>
							{{ __('Sign Out') }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from "vue"
import { useSessionLock } from "@/composables/useSessionLock"
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSUIStore } from "@/stores/posUI"
import { session } from "@/data/session"

const { isLocked, isVerifying, verifyError, lockedUser, unlock } = useSessionLock()

const password = ref("")
const showPassword = ref(false)
const passwordInputRef = ref(null)

const cartStore = usePOSCartStore()
const uiStore = usePOSUIStore()

// Auto-focus password input when locked
watch(isLocked, async (locked) => {
	if (locked) {
		password.value = ""
		showPassword.value = false
		await nextTick()
		passwordInputRef.value?.focus()
	}
})

async function handleUnlock() {
	if (!password.value || isVerifying.value) return

	const result = await unlock(password.value)

	if (result.sessionExpired) {
		// Session expired — full logout
		cartStore.clearCart()
		uiStore.resetAllDialogs()
		session.logout.submit()
		return
	}

	if (!result.success) {
		// Wrong password — clear and re-focus
		password.value = ""
		await nextTick()
		passwordInputRef.value?.focus()
	}
}

function handleSignOut() {
	cartStore.clearCart()
	uiStore.resetAllDialogs()
	session.logout.submit()
}
</script>

<style scoped>
.lock-overlay-enter-active,
.lock-overlay-leave-active {
	transition: opacity 0.3s ease;
}

.lock-overlay-enter-from,
.lock-overlay-leave-to {
	opacity: 0;
}
</style>
