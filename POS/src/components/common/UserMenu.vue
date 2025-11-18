<template>
	<div class="relative">
		<button
			@click="isOpen = !isOpen"
			class="flex items-center space-x-3 px-3 py-2 hover:bg-gray-50 rounded-lg transition-colors"
		>
			<div class="text-right hidden sm:block">
				<p class="text-sm font-semibold text-gray-900">{{ userName }}</p>
			</div>
			<div class="w-9 h-9 rounded-full flex items-center justify-center shadow-md overflow-hidden" :class="profileImage ? 'bg-gray-200' : 'bg-gradient-to-br from-blue-500 to-blue-600'">
				<img
					v-if="profileImage"
					:src="profileImage"
					:alt="userName"
					class="w-full h-full object-cover"
				/>
				<span v-else class="text-sm font-bold text-white">{{ userInitials }}</span>
			</div>
			<svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
			</svg>
		</button>

		<!-- Dropdown Menu -->
		<div
			v-if="isOpen"
			@click="handleMenuItemClick"
			class="absolute right-0 mt-2 w-60 bg-white rounded-xl shadow-xl border border-gray-200 py-2 z-[250]"
		>
			<!-- User Info Header -->
			<div class="px-4 py-3 border-b border-gray-100 flex items-center space-x-3">
				<div class="w-10 h-10 rounded-full flex items-center justify-center shadow-md overflow-hidden flex-shrink-0" :class="profileImage ? 'bg-gray-200' : 'bg-gradient-to-br from-blue-500 to-blue-600'">
					<img
						v-if="profileImage"
						:src="profileImage"
						:alt="userName"
						class="w-full h-full object-cover"
					/>
					<span v-else class="text-sm font-bold text-white">{{ userInitials }}</span>
				</div>
				<div class="flex-1 min-w-0">
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

			<!-- Divider -->
			<hr v-if="showLogout" class="my-2 border-gray-100">

			<!-- Logout -->
			<button
				v-if="showLogout"
				@click="handleLogout"
				class="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center space-x-3 transition-colors"
			>
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
				</svg>
				<span>Logout</span>
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue"

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

const isOpen = ref(false)

const userInitials = computed(() => {
	const parts = props.userName.split(" ")
	if (parts.length >= 2) {
		return (parts[0][0] + parts[1][0]).toUpperCase()
	}
	return props.userName.substring(0, 2).toUpperCase()
})

// Watch isOpen and emit events
watch(isOpen, (newValue) => {
	if (newValue) {
		emit("menu-opened")
	} else {
		emit("menu-closed")
	}
})

function handleMenuItemClick() {
	isOpen.value = false
}

function handleLogout() {
	isOpen.value = false
	emit("logout")
}

function handleClickOutside(event) {
	const userMenuButton = event.target.closest("button")
	const userMenu = event.target.closest(".absolute.right-0.mt-2")

	if (isOpen.value && !userMenuButton && !userMenu) {
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
