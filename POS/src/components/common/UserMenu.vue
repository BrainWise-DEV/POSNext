<template>
	<div ref="menuRef" class="relative">
		<button
			@click="isOpen = !isOpen"
			class="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 rounded-lg transition-colors"
		>
			<div class="text-end mx-1 hidden sm:block">
				<p class="text-sm font-semibold text-gray-900">{{ userName }}</p>
			</div>
			<Avatar :image="profileImage" :name="userName" :initials="userInitials" size="sm" />
			<svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
			</svg>
		</button>

		<!-- Dropdown Menu -->
		<div
			v-if="isOpen"
			@click="handleMenuItemClick"
			class="absolute end-0 mt-2 w-60 bg-white rounded-xl shadow-xl border border-gray-200 py-2 z-[250]"
		>
			<!-- User Info Header -->
			<div class="px-4 py-3 border-b border-gray-100 flex items-center">
				<Avatar :image="profileImage" :name="userName" :initials="userInitials" size="md" />
				<div class="flex-1 mx-2 min-w-0">
					<p class="text-sm font-semibold text-gray-900 truncate">{{ userName }}</p>
					<p v-if="profileName" class="text-xs text-gray-500 mt-0.5 truncate">{{ profileName }}</p>
				</div>
			</div>

			<!-- Menu Items -->
			<div class="py-1">
				<slot name="menu-items"></slot>
			</div>

			<!-- Divider -->
			<hr v-if="showDivider" class="my-2 border-gray-100">

			<!-- Additional Actions -->
			<slot name="additional-actions"></slot>

			<!-- Language Switcher - Mobile Only -->
			<div class="md:hidden">
				<hr class="my-2 border-gray-100">
				<button
					@click.stop="showLanguageDropdown = !showLanguageDropdown"
					class="w-full text-start px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3 transition-colors"
				>
					<svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"/>
					</svg>
					<span class="flex-1">{{ __('Language') }}</span>
					<div class="flex items-center gap-2">
						<img
							:src="supportedLocales[locale]?.flagUrlSvg"
							:alt="supportedLocales[locale]?.name"
							class="w-5 h-3.5 object-cover rounded-sm shadow-sm"
						/>
						<svg
							class="w-4 h-4 text-gray-400 transition-transform"
							:class="{ 'rotate-180': showLanguageDropdown }"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
						</svg>
					</div>
				</button>

				<!-- Language Dropdown -->
				<div
					v-if="showLanguageDropdown"
					class="bg-gray-50 border-t border-gray-100"
				>
					<button
						v-for="(config, code) in supportedLocales"
						:key="code"
						@click.stop="handleLanguageChange(code)"
						class="w-full text-start px-4 py-2.5 text-sm flex items-center gap-3 transition-colors"
						:class="locale === code
							? 'bg-blue-50 text-blue-700'
							: 'text-gray-600 hover:bg-gray-100'"
					>
						<img
							:src="config.flagUrlSvg"
							:alt="config.name"
							class="w-5 h-3.5 object-cover rounded-sm shadow-sm ms-6"
						/>
						<span class="flex-1">{{ config.nativeName }}</span>
						<svg
							v-if="locale === code"
							class="w-4 h-4 text-blue-600"
							fill="currentColor"
							viewBox="0 0 20 20"
						>
							<path
								fill-rule="evenodd"
								d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
								clip-rule="evenodd"
							/>
						</svg>
					</button>
				</div>
			</div>

			<!-- Divider -->
			<hr v-if="showLogout" class="my-2 border-gray-100">

			<!-- Logout -->
			<button
				v-if="showLogout"
				@click="handleLogout"
				class="w-full text-start px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center gap-3 transition-colors"
			>
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
				</svg>
				<span class="mx-4">{{ __('Logout') }}</span>
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, h, onMounted, onUnmounted, ref, watch } from "vue"
import { useLocale } from "@/composables/useLocale"

// Avatar Sub-component
const Avatar = (props) => {
	const sizeClass = props.size === 'sm' ? 'w-9 h-9' : 'w-10 h-10'
	const bgClass = props.image ? 'bg-gray-200' : 'bg-gradient-to-br from-blue-500 to-blue-600'

	return h('div', {
		class: `${sizeClass} rounded-full flex items-center justify-center shadow-md overflow-hidden flex-shrink-0 ${bgClass}`
	}, [
		props.image
			? h('img', { src: props.image, alt: props.name, class: 'w-full h-full object-cover' })
			: h('span', { class: 'text-sm font-bold text-white' }, props.initials)
	])
}

const { locale, supportedLocales, changeLocale } = useLocale()

const props = defineProps({
	userName: {
		type: String,
		required: true,
	},
	profileName: {
		type: String,
		default: null,
	},
	profileImage: {
		type: String,
		default: null,
	},
	showLogout: {
		type: Boolean,
		default: true,
	},
	showDivider: {
		type: Boolean,
		default: true,
	},
})

const emit = defineEmits(["logout", "menu-opened", "menu-closed"])

const menuRef = ref(null)
const isOpen = ref(false)
const showLanguageDropdown = ref(false)

const userInitials = computed(() => {
	const parts = (props.userName || "").split(" ").filter(Boolean)
	if (parts.length >= 2) {
		return (parts[0][0] + parts[1][0]).toUpperCase()
	}
	return (props.userName || "U").substring(0, 2).toUpperCase() || "U"
})

// Watch isOpen and emit events
watch(isOpen, (newValue) => {
	if (newValue) {
		emit("menu-opened")
	} else {
		emit("menu-closed")
		showLanguageDropdown.value = false
	}
})

function handleMenuItemClick() {
	isOpen.value = false
}

function handleLogout() {
	isOpen.value = false
	emit("logout")
}

async function handleLanguageChange(code) {
	if (code === locale.value) {
		return
	}
	isOpen.value = false
	await changeLocale(code)
}

function handleClickOutside(event) {
	if (isOpen.value && menuRef.value && !menuRef.value.contains(event.target)) {
		isOpen.value = false
	}
}

onMounted(() => {
	document.addEventListener("click", handleClickOutside)
})

onUnmounted(() => {
	document.removeEventListener("click", handleClickOutside)
})
</script>
