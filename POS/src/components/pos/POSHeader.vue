<template>
	<div
		class="bg-white shadow-sm sticky top-0 z-[200]"
	>
		<div class="flex py-2 sm:py-3">
			<!-- POS Icon - Aligned with Management Sidebar (64px) -->
			<div class="w-16 flex-shrink-0 flex items-center justify-center">
				<button
					class="w-10 h-10 bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg flex items-center justify-center shadow-md flex-shrink-0 hover:from-blue-600 hover:to-blue-700 active:scale-95 transition-all"
					:aria-label="'POS Next'"
					:title="__('POS Next')"
				>
					<svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
						<path d="M20 7h-4V4c0-1.1-.9-2-2-2h-4c-1.1 0-2 .9-2 2v3H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zM10 4h4v3h-4V4zm10 16H4V9h16v11z"/>
					</svg>
				</button>
			</div>

			<!-- Main Header Content -->
			<div class="flex-1 flex justify-between items-center gap-1 sm:gap-2 px-2 sm:px-4 md:px-6">
				<!-- Left Side: Brand Info -->
				<div class="flex items-center gap-1 sm:gap-4 min-w-0 flex-1 overflow-hidden">
					<div class="min-w-0 flex-shrink overflow-hidden">
						<div class="flex items-center gap-1 sm:gap-2">
							<h1 class="text-xs sm:text-base font-bold text-gray-900 truncate flex-shrink">{{ 'POS Next' }}</h1>
							<span class="hidden sm:inline-flex relative items-center px-1 sm:px-2 py-0.5 text-[8px] sm:text-[10px] font-bold bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-md shadow-sm hover:shadow-md transition-shadow flex-shrink-0">
								<span class="absolute inset-0 bg-white/20 rounded-md animate-pulse"></span>
								<span class="relative">v{{ appVersion }}</span>
							</span>
						</div>
						<p v-if="profileName" class="text-[9px] sm:text-xs text-gray-500 truncate hidden sm:block mt-0.5">{{ profileName }}</p>
					</div>

					<!-- Time and Shift Duration - Compact on mobile -->
					<div class="hidden lg:flex items-center gap-4 ms-6 flex-shrink-0">
						<!-- Current Time -->
						<StatusBadge
							variant="blue"
							size="sm"
							:icon="timeIcon"
							:text="currentTime"
						/>

						<!-- Shift Duration -->
						<StatusBadge
							v-if="hasOpenShift && shiftDuration"
							variant="green"
							size="xs"
							:icon="shiftIcon"
							:label="__('Shift Open:')"
							:value="shiftDuration"
						/>
					</div>

					<!-- Mobile Time Display - Very compact -->
					<div class="flex lg:hidden items-center text-[10px] text-gray-600 font-medium flex-shrink-0 ms-1">
						<span class="hidden xs:inline whitespace-nowrap">{{ currentTime }}</span>
					</div>
				</div>

				<!-- Right Side: Controls -->
				<div class="flex items-center gap-0.5 sm:gap-1 md:gap-2 flex-shrink-0">
					<!-- WiFi/Offline Status -->
					<button
						@click="$emit('sync-click')"
						:class="[
							'p-1.5 sm:p-2 hover:bg-gray-100 active:bg-gray-200 rounded-lg transition-colors relative group touch-manipulation',
							isSyncing ? 'animate-pulse' : ''
						]"
						:title="isOffline ? __('Offline ({0} pending)', [pendingInvoicesCount]) : __('Online - Click to sync')"
						:aria-label="isOffline ? __('Offline mode active') : __('Online mode active')"
					>
						<svg
							v-if="!isOffline"
							class="w-4 h-4 sm:w-5 sm:h-5 text-green-600"
							fill="currentColor"
							viewBox="0 0 24 24"
						>
							<path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/>
						</svg>
						<svg
							v-else
							class="w-4 h-4 sm:w-5 sm:h-5 text-orange-600"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414"/>
						</svg>
						<span
							v-if="pendingInvoicesCount > 0"
							class="absolute -top-1 -end-1 bg-orange-600 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center shadow-md"
						>
							{{ pendingInvoicesCount }}
						</span>
					</button>

					<!-- Cache Status Indicator -->
					<div class="relative">
						<button
							@click="showCacheTooltip = !showCacheTooltip"
							@blur="handleBlur"
							class="p-1.5 sm:p-2 hover:bg-gray-100 active:bg-gray-200 rounded-lg transition-colors relative touch-manipulation"
							:aria-label="getCacheAriaLabel()"
						>
							<svg
								class="w-4 h-4 sm:w-5 sm:h-5 transition-colors"
								:class="getCacheIconColor()"
								fill="currentColor"
								viewBox="0 0 24 24"
							>
								<path d="M12 2C8.13 2 5 3.12 5 4.5V7c0 1.38 3.13 2.5 7 2.5S19 8.38 19 7V4.5C19 3.12 15.87 2 12 2zM5 9v3c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V9c0 1.38-3.13 2.5-7 2.5S5 10.38 5 9zm0 5v3c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5v-3c0 1.38-3.13 2.5-7 2.5S5 15.38 5 14z"/>
							</svg>
							<svg
								v-if="cacheSyncing || isRefreshing"
								class="w-4 h-4 sm:w-5 sm:h-5 absolute top-2 start-2 animate-spin opacity-70"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
								:class="getCacheIconColor()"
							>
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
							</svg>
						</button>

						<!-- Tooltip -->
						<div
							v-if="showCacheTooltip"
							@mousedown.prevent
							class="absolute top-full mt-2 z-[999] w-[90vw] max-w-[240px] sm:max-w-[260px]"
							:style="{ left: '50%', transform: 'translateX(-50%)' }"
						>
							<div class="bg-gray-900 text-white text-xs rounded-lg shadow-xl py-2 px-2.5 sm:px-3">
								<!-- Arrow -->
								<div class="absolute bottom-full mb-px left-1/2 -translate-x-1/2"
								>
									<div class="border-[5px] sm:border-4 border-transparent border-b-gray-900"></div>
								</div>

								<!-- Header -->
								<div class="flex items-center justify-between mb-1.5 sm:mb-2 pb-1.5 sm:pb-2 border-b border-gray-700">
									<span class="font-semibold text-[11px] sm:text-xs">{{ __('Cache') }}</span>
									<span class="px-1.5 sm:px-2 py-0.5 rounded text-[9px] sm:text-[10px] font-bold uppercase" :class="getCacheStatusBadgeClass()">
										{{ getCacheStatus() }}
									</span>
								</div>

								<!-- Stats -->
								<div class="flex flex-col gap-1 sm:gap-1.5 text-[10px] sm:text-xs">
									<div class="flex items-center justify-between">
										<span class="text-gray-400">{{ __('Items:') }}</span>
										<span class="font-semibold">{{ cacheStats?.items || 0 }}</span>
									</div>
									<div v-if="cacheStats?.lastSync" class="flex items-center justify-between">
										<span class="text-gray-400">{{ __('Last Sync:') }}</span>
										<span class="font-semibold text-[9px] sm:text-[10px]">{{ formatLastSync() }}</span>
									</div>
									<div v-if="cacheSyncing" class="flex items-center justify-between">
										<span class="text-gray-400">{{ __('Status:') }}</span>
										<span class="text-orange-400 font-semibold flex items-center gap-1">
											<svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 animate-spin" fill="none" viewBox="0 0 24 24">
												<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
												<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
											</svg>
											{{ __('Syncing...') }}
										</span>
									</div>
									<div v-if="stockSyncActive" class="flex items-center justify-between">
										<span class="text-gray-400">{{ __('Auto-Sync:') }}</span>
										<span class="text-green-400 font-semibold flex items-center gap-1">
											<div class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div>
											{{ __('Active') }}
										</span>
									</div>
								</div>

								<!-- Clear Cache Button -->
								<div class="mt-1.5 sm:mt-2 pt-1.5 sm:pt-2 border-t border-gray-700">
									<button
										@click="handleClearCacheClick"
										:disabled="isOffline"
										:class="[
											'w-full px-2 py-1.5 sm:py-2 rounded transition-colors font-semibold text-[10px] sm:text-[11px] flex items-center justify-center gap-1.5',
											isOffline
												? 'bg-gray-500/20 text-gray-500 cursor-not-allowed'
												: 'bg-red-500/20 hover:bg-red-500/30 text-red-300 hover:text-red-200 active:scale-95'
										]"
										:title="isOffline ? __('Cannot clear cache while offline') : __('Clear all cached data')"
									>
										<svg class="w-2.5 h-2.5 sm:w-3 sm:h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
										</svg>
										{{ __('Clear Cache') }}
									</button>
								</div>
							</div>
						</div>
					</div>

					<!-- Printer - Hidden on small screens -->
					<div class="hidden md:block">
						<ActionButton
							:icon="printerIcon"
							:title="__('Print Invoice')"
							@click="$emit('printer-click')"
						/>
					</div>

					<!-- Refresh -->
					<ActionButton
						:icon="refreshIcon"
						:title="isRefreshing ? __('Refreshing...') : __('Refresh Items')"
						@click="$emit('refresh-click')"
						:class="[
							'touch-manipulation p-1 sm:p-2',
							isRefreshing ? 'animate-spin' : ''
						]"
						:aria-label="isRefreshing ? __('Refreshing items...') : __('Refresh items list')"
					/>

					<div class="w-px h-4 sm:h-6 bg-gray-200 hidden md:block"></div>

					<!-- Language Switcher - Hidden on mobile, shown in UserMenu instead -->
					<div class="hidden md:block">
						<LanguageSwitcher />
					</div>

					<div class="w-px h-4 sm:h-6 bg-gray-200"></div>

					<!-- User Menu -->
					<UserMenu
						:user-name="userName"
						:profile-name="profileName"
						:profile-image="userImage"
						@logout="$emit('logout')"
						@menu-opened="$emit('menu-opened')"
						@menu-closed="$emit('menu-closed')"
					>
						<template #menu-items>
							<slot name="menu-items"></slot>
						</template>
						<template #additional-actions>
							<slot name="additional-actions"></slot>
						</template>
					</UserMenu>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import ActionButton from "@/components/common/ActionButton.vue"
import StatusBadge from "@/components/common/StatusBadge.vue"
import UserMenu from "@/components/common/UserMenu.vue"
import LanguageSwitcher from "@/components/common/LanguageSwitcher.vue"
import { ref } from "vue"
import { version } from "../../../package.json"

const showCacheTooltip = ref(false)
const appVersion = version

const emit = defineEmits([
	"sync-click",
	"printer-click",
	"refresh-click",
	"menu-click",
	"logout",
	"menu-opened",
	"menu-closed",
	"clear-cache",
])

function handleClearCacheClick() {
	showCacheTooltip.value = false
	emit('clear-cache')
}

function handleBlur(event) {
	// Don't close if clicking inside the tooltip
	if (!event.relatedTarget || !event.currentTarget.parentElement.contains(event.relatedTarget)) {
		setTimeout(() => {
			showCacheTooltip.value = false
		}, 200)
	}
}

const props = defineProps({
	currentTime: {
		type: String,
		required: true,
	},
	shiftDuration: {
		type: String,
		default: null,
	},
	hasOpenShift: {
		type: Boolean,
		default: false,
	},
	profileName: {
		type: String,
		default: null,
	},
	userName: {
		type: String,
		required: true,
	},
	userImage: {
		type: String,
		default: null,
	},
	isOffline: {
		type: Boolean,
		default: false,
	},
	isSyncing: {
		type: Boolean,
		default: false,
	},
	pendingInvoicesCount: {
		type: Number,
		default: 0,
	},
	isAnyDialogOpen: {
		type: Boolean,
		default: false,
	},
	cacheSyncing: {
		type: Boolean,
		default: false,
	},
	cacheStats: {
		type: Object,
		default: () => ({ items: 0, lastSync: null }),
	},
	stockSyncActive: {
		type: Boolean,
		default: false,
	},
	isRefreshing: {
		type: Boolean,
		default: false,
	},
})

// Cache status helpers
function getCacheIconColor() {
	if (!props.cacheStats || props.cacheStats.items === 0) {
		return "text-red-600" // Red: No cache
	}
	if (props.cacheSyncing) {
		return "text-orange-600" // Orange: Syncing in progress
	}
	return "text-green-600" // Green: Cache ready
}

function getCacheStatus() {
	if (!props.cacheStats || props.cacheStats.items === 0) {
		return __("Empty")
	}
	if (props.cacheSyncing) {
		return __("Syncing")
	}
	return __("Ready")
}

function getCacheStatusBadgeClass() {
	if (!props.cacheStats || props.cacheStats.items === 0) {
		return "bg-red-500/20 text-red-300"
	}
	if (props.cacheSyncing) {
		return "bg-orange-500/20 text-orange-300"
	}
	return "bg-green-500/20 text-green-300"
}

function formatLastSync() {
	if (!props.cacheStats?.lastSync) {
		return __("Never")
	}
	const date = new Date(props.cacheStats.lastSync)
	return date.toLocaleTimeString("en-US", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	})
}

function getCacheAriaLabel() {
	if (!props.cacheStats || props.cacheStats.items === 0) {
		return __("Cache empty")
	}
	if (props.cacheSyncing) {
		return __("Cache syncing")
	}
	return __("Cache ready")
}

// SVG Path Icons
const timeIcon = "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
const shiftIcon =
	"M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"
const printerIcon =
	"M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
const refreshIcon =
	"M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
</script>
