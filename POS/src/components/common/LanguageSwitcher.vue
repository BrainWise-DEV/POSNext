<template>
	<div ref="dropdownRef" class="relative">
		<button
			@click="toggleDropdown"
			class="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 sm:py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors disabled:opacity-60 disabled:cursor-wait"
			:class="{ 'flex-row-reverse': isRTL }"
			:disabled="isChanging"
			:title="localeConfig.nativeName"
		>
			<template v-if="isChanging">
				<LoadingIndicator class="w-4 h-4" />
			</template>
			<template v-else>
				<img
					:src="localeConfig.flagUrlSvg"
					:alt="localeConfig.name"
					class="w-5 h-3.5 sm:w-6 sm:h-4 object-cover rounded-sm shadow-sm"
				/>
				<span class="hidden sm:inline text-xs sm:text-sm">{{ localeConfig.nativeName }}</span>
				<FeatherIcon
					name="chevron-down"
					class="w-3 h-3 sm:w-4 sm:h-4 transition-transform text-gray-500"
					:class="{ 'rotate-180': isOpen }"
				/>
			</template>
		</button>

		<Transition
			enter-active-class="transition ease-out duration-150"
			enter-from-class="opacity-0 scale-95"
			enter-to-class="opacity-100 scale-100"
			leave-active-class="transition ease-in duration-100"
			leave-from-class="opacity-100 scale-100"
			leave-to-class="opacity-0 scale-95"
		>
			<div
				v-if="isOpen"
				class="absolute z-50 mt-2 w-36 rounded-lg bg-white shadow-lg ring-1 ring-black/5"
				:class="isRTL ? 'start-0' : 'end-0'"
				role="menu"
			>
				<div class="py-1">
					<button
						v-for="(config, code) in supportedLocales"
						:key="code"
						@click="selectLanguage(code)"
						class="flex items-center w-full px-4 py-2 text-sm transition-colors"
						:class="[
							locale === code ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-100',
							config.dir === 'rtl' ? 'flex-row-reverse' : ''
						]"
						role="menuitem"
					>
						<img
							:src="config.flagUrlSvg"
							:alt="config.name"
							class="w-6 h-4 object-cover rounded-sm shadow-sm"
							:class="config.dir === 'rtl' ? 'ms-3' : 'me-3'"
						/>
						<span class="flex-1" :class="config.dir === 'rtl' ? 'text-end' : 'text-start'">
							{{ config.nativeName }}
						</span>
						<FeatherIcon
							v-if="locale === code"
							name="check"
							class="w-4 h-4 text-blue-600"
						/>
					</button>
				</div>
			</div>
		</Transition>
	</div>
</template>

<script setup>
/**
 * @component LanguageSwitcher
 * @description Dropdown component for switching application locale.
 *
 * Features:
 * - Displays current locale with flag and native name
 * - Animated dropdown with available locales
 * - RTL-aware layout (adapts direction based on locale)
 * - Loading state during language change
 * - Click-outside to close dropdown
 *
 * @example
 * <LanguageSwitcher />
 */
import { ref, onMounted, onUnmounted } from "vue"
import { FeatherIcon, LoadingIndicator } from "frappe-ui"
import { useLocale } from "@/composables/useLocale"

// Locale state from composable
const { locale, localeConfig, isRTL, supportedLocales, changeLocale } = useLocale()

// Component state
const isOpen = ref(false)        // Dropdown visibility
const isChanging = ref(false)    // Language change in progress
const dropdownRef = ref(null)    // DOM ref for click-outside detection

/** Toggles dropdown (disabled while changing language) */
const toggleDropdown = () => !isChanging.value && (isOpen.value = !isOpen.value)

/**
 * Handles language selection from dropdown.
 * Closes dropdown immediately, then loads new translations.
 * @param {string} code - Locale code to switch to
 */
const selectLanguage = async (code) => {
	isOpen.value = false
	if (code === locale.value || isChanging.value) return

	isChanging.value = true
	try {
		await changeLocale(code)
	} finally {
		isChanging.value = false
	}
}

/** Closes dropdown when clicking outside the component */
const handleClickOutside = (e) => dropdownRef.value?.contains(e.target) || (isOpen.value = false)

// Event listener lifecycle
onMounted(() => document.addEventListener("click", handleClickOutside))
onUnmounted(() => document.removeEventListener("click", handleClickOutside))
</script>
