<template>
	<div class="autocomplete-select" ref="containerRef">
		<div class="select-input-wrapper">
			<svg v-if="icon" class="input-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icon"/>
			</svg>
			<input
				ref="inputRef"
				v-model="searchQuery"
				type="text"
				class="select-input"
				:class="{ 'has-icon': icon, 'has-value': modelValue }"
				:placeholder="placeholder"
				@focus="handleFocus"
				@input="handleInput"
				@keydown="handleKeydown"
			/>
			<div class="input-actions">
				<button
					v-if="modelValue"
					@click="clearSelection"
					class="clear-btn"
					type="button"
				>
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
					</svg>
				</button>
				<button
					@click="toggleDropdown"
					class="dropdown-toggle"
					type="button"
				>
					<svg class="w-4 h-4" :class="{ 'rotate-180': showDropdown }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
					</svg>
				</button>
			</div>
		</div>

		<!-- Dropdown -->
		<Transition name="dropdown">
			<div v-if="showDropdown" class="dropdown-menu">
				<!-- Loading State -->
				<div v-if="loading" class="dropdown-loading">
					<div class="loading-spinner"></div>
					<span>{{ __('Searching...') }}</span>
				</div>

				<!-- No Results -->
				<div v-else-if="filteredOptions.length === 0" class="dropdown-empty">
					<svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
					</svg>
					<span>{{ searchQuery ? __('No results found') : __('No options available') }}</span>
				</div>

				<!-- Options List -->
				<div v-else class="dropdown-list">
					<!-- Clear Selection Option -->
					<button
						v-if="!required && modelValue"
						@click="clearSelection"
						class="dropdown-item clear-item"
						type="button"
					>
						<svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
						</svg>
						<span>{{ __('Clear selection') }}</span>
					</button>

					<!-- Options -->
					<button
						v-for="(option, index) in paginatedOptions"
						:key="option.value"
						@click="selectOption(option)"
						:class="['dropdown-item', {
							active: option.value === modelValue,
							highlighted: index === highlightedIndex
						}]"
						type="button"
					>
						<svg v-if="option.value === modelValue" class="item-icon check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
						</svg>
						<div class="item-content">
							<span class="item-label" v-html="highlightMatch(option.label)"></span>
							<span v-if="option.subtitle" class="item-subtitle">{{ option.subtitle }}</span>
						</div>
					</button>

					<!-- Load More -->
					<button
						v-if="hasMore"
						@click="loadMore"
						class="dropdown-item load-more"
						type="button"
					>
						<svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
						</svg>
						<span>{{ __('Load more ({0} remaining)', [(filteredOptions.length - displayLimit)]) }}</span>
					</button>
				</div>
			</div>
		</Transition>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue"

const props = defineProps({
	modelValue: {
		type: [String, Number],
		default: "",
	},
	options: {
		type: Array,
		default: () => [],
	},
	placeholder: {
		type: String,
		default: __("Search..."),
	},
	icon: {
		type: String,
		default: "",
	},
	required: {
		type: Boolean,
		default: false,
	},
	loading: {
		type: Boolean,
		default: false,
	},
	// For async search
	searchable: {
		type: Boolean,
		default: true,
	},
	minSearchLength: {
		type: Number,
		default: 0,
	},
})

const emit = defineEmits(["update:modelValue", "search"])

const containerRef = ref(null)
const inputRef = ref(null)
const searchQuery = ref("")
const showDropdown = ref(false)
const highlightedIndex = ref(-1)
const displayLimit = ref(50)

// Find selected option label
const selectedOption = computed(() => {
	return props.options.find((opt) => opt.value === props.modelValue)
})

// Update search query when selection changes
watch(
	() => props.modelValue,
	(newValue) => {
		if (newValue && selectedOption.value) {
			searchQuery.value = selectedOption.value.label
		} else if (!newValue) {
			searchQuery.value = ""
		}
	},
	{ immediate: true },
)

// Filter options based on search
const filteredOptions = computed(() => {
	if (!searchQuery.value || searchQuery.value === selectedOption.value?.label) {
		return props.options
	}

	const query = searchQuery.value.toLowerCase()
	return props.options.filter((option) => {
		const label = option.label.toLowerCase()
		const subtitle = option.subtitle?.toLowerCase() || ""
		return label.includes(query) || subtitle.includes(query)
	})
})

// Paginated options for performance
const paginatedOptions = computed(() => {
	return filteredOptions.value.slice(0, displayLimit.value)
})

const hasMore = computed(() => {
	return filteredOptions.value.length > displayLimit.value
})

function handleFocus() {
	showDropdown.value = true
	highlightedIndex.value = -1
	// Select all text for easy replacement
	if (searchQuery.value) {
		inputRef.value?.select()
	}
}

function handleInput() {
	showDropdown.value = true
	highlightedIndex.value = -1
	displayLimit.value = 50 // Reset pagination

	// Emit search event for async searching
	if (props.searchable && searchQuery.value.length >= props.minSearchLength) {
		emit("search", searchQuery.value)
	}
}

function handleKeydown(e) {
	if (!showDropdown.value) {
		if (e.key === "ArrowDown" || e.key === "ArrowUp") {
			showDropdown.value = true
			e.preventDefault()
			return
		}
	}

	switch (e.key) {
		case "ArrowDown":
			e.preventDefault()
			highlightedIndex.value = Math.min(
				highlightedIndex.value + 1,
				paginatedOptions.value.length - 1,
			)
			scrollToHighlighted()
			break
		case "ArrowUp":
			e.preventDefault()
			highlightedIndex.value = Math.max(highlightedIndex.value - 1, -1)
			scrollToHighlighted()
			break
		case "Enter":
			e.preventDefault()
			if (highlightedIndex.value >= 0) {
				selectOption(paginatedOptions.value[highlightedIndex.value])
			}
			break
		case "Escape":
			e.preventDefault()
			closeDropdown()
			break
		case "Tab":
			closeDropdown()
			break
	}
}

function toggleDropdown() {
	showDropdown.value = !showDropdown.value
	if (showDropdown.value) {
		inputRef.value?.focus()
	}
}

function selectOption(option) {
	emit("update:modelValue", option.value)
	searchQuery.value = option.label
	closeDropdown()
	inputRef.value?.blur()
}

function clearSelection() {
	emit("update:modelValue", "")
	searchQuery.value = ""
	showDropdown.value = false
	inputRef.value?.focus()
}

function closeDropdown() {
	showDropdown.value = false
	highlightedIndex.value = -1
	// Restore selected option label if exists
	if (selectedOption.value) {
		searchQuery.value = selectedOption.value.label
	}
}

function loadMore() {
	displayLimit.value += 50
}

function scrollToHighlighted() {
	// Scroll highlighted item into view
	const dropdown = containerRef.value?.querySelector(".dropdown-list")
	const items = dropdown?.querySelectorAll(
		".dropdown-item:not(.clear-item):not(.load-more)",
	)
	if (items && highlightedIndex.value >= 0) {
		items[highlightedIndex.value]?.scrollIntoView({
			block: "nearest",
			behavior: "smooth",
		})
	}
}

function highlightMatch(text) {
	if (!searchQuery.value || searchQuery.value === selectedOption.value?.label) {
		return text
	}

	const query = searchQuery.value
	const regex = new RegExp(`(${query})`, "gi")
	return text.replace(regex, "<mark>$1</mark>")
}

// Click outside to close
function handleClickOutside(event) {
	if (containerRef.value && !containerRef.value.contains(event.target)) {
		closeDropdown()
	}
}

onMounted(() => {
	document.addEventListener("click", handleClickOutside)
})

onUnmounted(() => {
	document.removeEventListener("click", handleClickOutside)
})
</script>

<style scoped>
.autocomplete-select {
	position: relative;
	width: 100%;
}

.select-input-wrapper {
	position: relative;
	display: flex;
	align-items: center;
}

.input-icon {
	position: absolute;
	inset-inline-start: 0.75rem;
	width: 1rem;
	height: 1rem;
	color: #6b7280;
	pointer-events: none;
}

.select-input {
	width: 100%;
	padding: 0.625rem;
	padding-inline-start: 0.75rem;
	padding-inline-end: 5rem;
	border: 1px solid #d1d5db;
	border-radius: 8px;
	font-size: 0.875rem;
	color: #111827;
	background: white;
	transition: all 0.15s;
}

.select-input.has-icon {
	padding-inline-start: 2.5rem;
}

.select-input:focus {
	outline: none;
	border-color: #6366f1;
	box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.select-input.has-value {
	font-weight: 500;
	color: #6366f1;
}

.input-actions {
	position: absolute;
	inset-inline-end: 0.5rem;
	display: flex;
	align-items: center;
	gap: 0.25rem;
}

.clear-btn,
.dropdown-toggle {
	padding: 0.25rem;
	background: transparent;
	border: none;
	color: #6b7280;
	cursor: pointer;
	border-radius: 4px;
	transition: all 0.15s;
}

.clear-btn:hover,
.dropdown-toggle:hover {
	background: #f3f4f6;
	color: #374151;
}

.dropdown-toggle svg {
	transition: transform 0.2s;
}

.dropdown-toggle svg.rotate-180 {
	transform: rotate(180deg);
}

/* Dropdown Menu */
.dropdown-menu {
	position: absolute;
	top: calc(100% + 0.5rem);
	inset-inline-start: 0;
	inset-inline-end: 0;
	max-height: 320px;
	background: white;
	border: 1px solid #e5e7eb;
	border-radius: 10px;
	box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
	overflow: hidden;
	z-index: 50;
}

.dropdown-loading,
.dropdown-empty {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 2rem;
	gap: 0.75rem;
	color: #6b7280;
}

.loading-spinner {
	width: 1.5rem;
	height: 1.5rem;
	border: 2px solid #e5e7eb;
	border-top-color: #6366f1;
	border-radius: 50%;
	animation: spin 0.6s linear infinite;
}

@keyframes spin {
	to { transform: rotate(360deg); }
}

.empty-icon {
	width: 2rem;
	height: 2rem;
	color: #d1d5db;
}

.dropdown-list {
	max-height: 320px;
	overflow-y: auto;
	overscroll-behavior: contain;
}

/* Scrollbar */
.dropdown-list::-webkit-scrollbar {
	width: 6px;
}

.dropdown-list::-webkit-scrollbar-track {
	background: #f3f4f6;
}

.dropdown-list::-webkit-scrollbar-thumb {
	background: #d1d5db;
	border-radius: 3px;
}

.dropdown-list::-webkit-scrollbar-thumb:hover {
	background: #9ca3af;
}

.dropdown-item {
	width: 100%;
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 0.75rem 1rem;
	border: none;
	background: white;
	text-align: start;
	cursor: pointer;
	transition: all 0.15s;
	border-bottom: 1px solid #f3f4f6;
}

.dropdown-item:last-child {
	border-bottom: none;
}

.dropdown-item:hover,
.dropdown-item.highlighted {
	background: #f9fafb;
}

.dropdown-item.active {
	background: #eef2ff;
	color: #6366f1;
}

.dropdown-item.clear-item {
	color: #dc2626;
	border-bottom: 2px solid #fecaca;
}

.dropdown-item.clear-item:hover {
	background: #fef2f2;
}

.dropdown-item.load-more {
	color: #6366f1;
	font-weight: 500;
	justify-content: center;
	border-top: 2px solid #e0e7ff;
}

.dropdown-item.load-more:hover {
	background: #eef2ff;
}

.item-icon {
	width: 1rem;
	height: 1rem;
	flex-shrink: 0;
	color: #9ca3af;
}

.item-icon.check-icon {
	color: #10b981;
}

.item-content {
	flex: 1;
	display: flex;
	flex-direction: column;
	gap: 0.125rem;
	min-width: 0;
}

.item-label {
	font-size: 0.875rem;
	color: #111827;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.item-label :deep(mark) {
	background: #fef3c7;
	color: #92400e;
	font-weight: 600;
	padding: 0 0.125rem;
	border-radius: 2px;
}

.item-subtitle {
	font-size: 0.75rem;
	color: #6b7280;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

/* Transitions */
.dropdown-enter-active,
.dropdown-leave-active {
	transition: all 0.2s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
	opacity: 0;
	transform: translateY(-8px);
}
</style>
