<template>
	<div class="language-switcher" ref="switcherRef">
		<button
			@click="toggleDropdown"
			:disabled="isChanging"
			class="switcher-button"
			:class="{ 'changing': isChanging, 'open': isOpen }"
		>
			<component :is="getFlagIcon(selectedLanguage)" class="flag-icon" />
			<span class="current-lang">{{ currentLangName }}</span>
			<svg class="chevron-icon" :class="{ 'rotate': isOpen }" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
			</svg>
		</button>

		<transition name="dropdown">
			<div v-if="isOpen" class="dropdown-menu">
				<div class="dropdown-header">
					<span>Select Language</span>
				</div>
				<button
					v-for="lang in availableLanguages"
					:key="lang.code"
					@click="selectLanguage(lang.code)"
					class="dropdown-item"
					:class="{ 'active': selectedLanguage === lang.code }"
				>
					<div class="lang-info">
						<component :is="getFlagIcon(lang.code)" class="flag-icon-dropdown" />
						<span class="lang-name">{{ lang.name }}</span>
					</div>
					<div v-if="selectedLanguage === lang.code" class="check-wrapper">
						<svg class="check-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
						</svg>
					</div>
				</button>
			</div>
		</transition>
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, h } from "vue"

// State
const selectedLanguage = ref(localStorage.getItem("guestLanguage") || "en")
const availableLanguages = ref([])
const isChanging = ref(false)
const isOpen = ref(false)
const switcherRef = ref(null)

// Flag Icon Components
const FlagUK = () => h('svg', {
	viewBox: '0 0 32 32',
	xmlns: 'http://www.w3.org/2000/svg'
}, [
	h('rect', { x: 0, y: 0, width: 32, height: 32, fill: '#012169' }),
	h('path', { d: 'M0 0 L32 32 M32 0 L0 32', stroke: '#fff', 'stroke-width': 6 }),
	h('path', { d: 'M0 0 L32 32 M32 0 L0 32', stroke: '#C8102E', 'stroke-width': 4 }),
	h('path', { d: 'M16 0 L16 32 M0 16 L32 16', stroke: '#fff', 'stroke-width': 10 }),
	h('path', { d: 'M16 0 L16 32 M0 16 L32 16', stroke: '#C8102E', 'stroke-width': 6 })
])

const FlagSA = () => h('svg', {
	viewBox: '0 0 32 32',
	xmlns: 'http://www.w3.org/2000/svg'
}, [
	h('rect', { x: 0, y: 0, width: 32, height: 32, fill: '#006C35', rx: 2 }),
	h('g', { transform: 'translate(8, 10)' }, [
		h('text', {
			x: 8,
			y: 8,
			fill: '#fff',
			'font-size': '10',
			'font-weight': 'bold',
			'text-anchor': 'middle'
		}, 'AR'),
		h('path', {
			d: 'M2 12 L14 12',
			stroke: '#fff',
			'stroke-width': 2,
			'stroke-linecap': 'round'
		})
	])
])

const FlagSpain = () => h('svg', {
	viewBox: '0 0 32 32',
	xmlns: 'http://www.w3.org/2000/svg'
}, [
	h('rect', { x: 0, y: 0, width: 32, height: 10, fill: '#C60B1E' }),
	h('rect', { x: 0, y: 10, width: 32, height: 12, fill: '#FFC400' }),
	h('rect', { x: 0, y: 22, width: 32, height: 10, fill: '#C60B1E' })
])

const FlagDefault = () => h('svg', {
	viewBox: '0 0 24 24',
	fill: 'none',
	xmlns: 'http://www.w3.org/2000/svg',
	stroke: 'currentColor'
}, [
	h('path', {
		'stroke-linecap': 'round',
		'stroke-linejoin': 'round',
		'stroke-width': 2,
		d: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9'
	})
])

// Flag mapping
const flagIcons = {
	'en': FlagUK,
	'ar': FlagSA,
	'es': FlagSpain
}

// Computed properties for better performance
const currentLangName = computed(() => {
	const lang = availableLanguages.value.find(l => l.code === selectedLanguage.value)
	return lang?.name || 'English'
})

// Lifecycle
onMounted(() => {
	loadLanguages()
	document.addEventListener('click', handleClickOutside, { passive: true })
})

onBeforeUnmount(() => {
	document.removeEventListener('click', handleClickOutside)
})

// Methods
function getFlagIcon(code) {
	return flagIcons[code] || FlagDefault
}

function handleClickOutside(event) {
	if (isOpen.value && switcherRef.value && !switcherRef.value.contains(event.target)) {
		isOpen.value = false
	}
}

function toggleDropdown() {
	if (!isChanging.value) {
		isOpen.value = !isOpen.value
	}
}

async function loadLanguages() {
	// Use cached data if available
	if (availableLanguages.value.length > 0) return

	try {
		const resource = window.$getAvailableLanguages()
		if (resource.data) {
			availableLanguages.value = resource.data
		} else {
			await resource.promise
			availableLanguages.value = resource.data || [{ code: "en", name: "English", is_rtl: false }]
		}
	} catch (error) {
		console.error("Failed to load languages:", error)
		availableLanguages.value = [{ code: "en", name: "English", is_rtl: false }]
	}
}

function selectLanguage(langCode) {
	if (langCode === selectedLanguage.value || isChanging.value) {
		isOpen.value = false
		return
	}

	isChanging.value = true
	isOpen.value = false

	// Update immediately in localStorage for instant reload
	localStorage.setItem("guestLanguage", langCode)

	// For logged-in users, save asynchronously without blocking
	if (window.frappe?.session?.user && window.frappe.session.user !== "Guest") {
		window.$changeLanguage(langCode).catch(console.error)
	}

	// Instant reload - no delays or animations
	window.location.reload()
}
</script>

<style scoped>
.language-switcher {
	position: relative;
	display: inline-block;
}

.switcher-button {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 10px 16px;
	background: white;
	border: 1px solid #e5e7eb;
	border-radius: 10px;
	cursor: pointer;
	transition: all 0.2s ease;
	font-size: 14px;
	font-weight: 500;
	color: #374151;
	min-width: 140px;
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.switcher-button:hover:not(:disabled) {
	border-color: #3b82f6;
	background: #fafbfc;
	box-shadow: 0 4px 16px rgba(59, 130, 246, 0.15);
	transform: translateY(-1px);
}

.switcher-button.open {
	border-color: #3b82f6;
	background: white;
	box-shadow: 0 4px 16px rgba(59, 130, 246, 0.2);
}

.switcher-button:disabled {
	opacity: 0.6;
	cursor: not-allowed;
}

.switcher-button.changing {
	background: #f3f4f6;
	pointer-events: none;
}

.flag-icon {
	width: 22px;
	height: 22px;
	border-radius: 4px;
	overflow: hidden;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.current-lang {
	flex: 1;
	text-align: left;
	font-weight: 500;
	white-space: nowrap;
}

.chevron-icon {
	width: 16px;
	height: 16px;
	color: #9ca3af;
	transition: transform 0.2s ease;
	flex-shrink: 0;
}

.chevron-icon.rotate {
	transform: rotate(180deg);
}

.dropdown-menu {
	position: absolute;
	top: calc(100% + 8px);
	right: 0;
	background: white;
	border: 1px solid #e5e7eb;
	border-radius: 10px;
	box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
	min-width: 180px;
	overflow: hidden;
	z-index: 1000;
}

.dropdown-header {
	padding: 12px 16px;
	background: #f9fafb;
	border-bottom: 1px solid #e5e7eb;
	font-size: 11px;
	font-weight: 600;
	color: #6b7280;
	text-transform: uppercase;
	letter-spacing: 0.8px;
}

.dropdown-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	width: 100%;
	padding: 12px 16px;
	background: white;
	border: none;
	cursor: pointer;
	transition: all 0.15s ease;
	font-size: 14px;
	color: #374151;
}

.dropdown-item:hover {
	background: #f0f9ff;
}

.dropdown-item.active {
	background: #eff6ff;
	color: #2563eb;
	font-weight: 500;
}

.dropdown-item + .dropdown-item {
	border-top: 1px solid #f3f4f6;
}

.lang-info {
	display: flex;
	align-items: center;
	gap: 12px;
}

.flag-icon-dropdown {
	width: 20px;
	height: 20px;
	border-radius: 3px;
	overflow: hidden;
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
	flex-shrink: 0;
}

.lang-name {
	font-weight: 500;
	flex: 1;
}

.check-wrapper {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 18px;
	height: 18px;
	background: #2563eb;
	border-radius: 50%;
	animation: checkPop 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

.check-icon {
	width: 11px;
	height: 11px;
	color: white;
	stroke-width: 3;
}

/* Animations */
@keyframes checkPop {
	0% {
		transform: scale(0);
	}
	50% {
		transform: scale(1.2);
	}
	100% {
		transform: scale(1);
	}
}

.dropdown-enter-active {
	animation: dropdownIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.dropdown-leave-active {
	animation: dropdownOut 0.2s ease-in;
}

@keyframes dropdownIn {
	from {
		opacity: 0;
		transform: translateY(-10px) scale(0.95);
	}
	to {
		opacity: 1;
		transform: translateY(0) scale(1);
	}
}

@keyframes dropdownOut {
	from {
		opacity: 1;
		transform: translateY(0) scale(1);
	}
	to {
		opacity: 0;
		transform: translateY(-10px) scale(0.95);
	}
}

/* RTL Support */
:global(.rtl) .current-lang {
	text-align: right;
}

:global(.rtl) .lang-info {
	flex-direction: row-reverse;
}
</style>
