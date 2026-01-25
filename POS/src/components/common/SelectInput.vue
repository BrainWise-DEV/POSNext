<template>
	<div class="relative" ref="containerRef">
		<!-- Trigger Button -->
		<button
			type="button"
			ref="triggerRef"
			@click="toggle"
			@keydown.enter.prevent="toggle"
			@keydown.space.prevent="toggle"
			@keydown.escape="close"
			@keydown.down.prevent="openAndFocusFirst"
			:disabled="disabled"
			class="w-full h-7 border border-gray-100 rounded bg-gray-100 hover:border-gray-200 hover:bg-gray-200 px-2 pe-8 text-base text-start transition-colors focus:border-gray-500 focus:outline-none focus:bg-white focus:shadow-sm flex items-center"
			:class="[selectClass, disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer']"
		>
			<span class="truncate" :class="selectedLabel ? 'text-gray-900' : 'text-gray-500'">{{ selectedLabel || placeholder }}</span>
		</button>

		<!-- Chevron Icon -->
		<FeatherIcon
			name="chevron-down"
			class="absolute top-1/2 end-2 -translate-y-1/2 w-4 h-4 text-gray-600 pointer-events-none transition-transform"
			:class="{ 'rotate-180': isOpen }"
		/>

		<!-- Dropdown Options - Teleported to body for proper overlay -->
		<Teleport to="body">
			<Transition
				enter-active-class="transition ease-out duration-100"
				enter-from-class="opacity-0 scale-95"
				enter-to-class="opacity-100 scale-100"
				leave-active-class="transition ease-in duration-75"
				leave-from-class="opacity-100 scale-100"
				leave-to-class="opacity-0 scale-95"
			>
				<div
					v-if="isOpen"
					ref="dropdownRef"
					class="fixed bg-white border border-gray-100 rounded-lg shadow-lg flex flex-col dropdown-z-index"
					:style="dropdownStyle"
					:class="searchable ? 'max-h-80' : 'max-h-60'"
					role="listbox"
				>
					<!-- Search Input (when searchable) -->
					<div v-if="searchable" class="p-2 border-b border-gray-100 sticky top-0 bg-white">
						<div class="relative">
							<FeatherIcon
								name="search"
								class="absolute start-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
							/>
							<input
								ref="searchInputRef"
								v-model="searchQuery"
								type="text"
								:placeholder="searchPlaceholder"
								class="w-full h-8 ps-8 pe-2 text-sm border border-gray-200 rounded bg-gray-50 focus:outline-none focus:border-gray-400 focus:bg-white"
								@keydown.escape="close"
								@keydown.down.prevent="focusFirstOption"
							/>
						</div>
					</div>

					<!-- Options List -->
					<div class="overflow-auto py-1.5 flex-1">
						<div
							v-if="filteredOptions.length === 0"
							class="px-3 py-2 text-sm text-gray-500 text-center"
						>
							{{ noResultsText }}
						</div>
						<div
							v-for="(option, index) in filteredOptions"
							:key="option.value"
							@click="selectOption(option)"
							@keydown.enter.prevent="selectOption(option)"
							@keydown.escape="close"
							@keydown.down.prevent="focusNext(index)"
							@keydown.up.prevent="focusPrev(index)"
							:ref="el => optionRefs[index] = el"
							tabindex="0"
							role="option"
							:aria-selected="option.value === modelValue"
							class="px-2 py-1.5 text-base cursor-pointer text-start transition-colors focus:outline-none"
							:class="option.value === modelValue
								? 'bg-blue-50 text-blue-700'
								: 'text-gray-800 hover:bg-gray-100 focus:bg-gray-100'"
						>
							<div v-if="option.subtitle" class="flex flex-col">
								<span class="text-sm font-medium">{{ option.label }}</span>
								<span class="text-xs text-gray-500">{{ option.subtitle }}</span>
							</div>
							<span v-else>{{ option.label }}</span>
						</div>
					</div>
				</div>
			</Transition>
		</Teleport>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { computed, ref, onMounted, onBeforeUnmount, nextTick, watch } from "vue"

defineOptions({
	inheritAttrs: false,
})

const props = defineProps({
	modelValue: {
		type: [String, Number],
		default: "",
	},
	options: {
		type: Array, // [{ value: '', label: '', subtitle?: '' }]
		default: () => [],
	},
	placeholder: {
		type: String,
		default: "",
	},
	disabled: {
		type: Boolean,
		default: false,
	},
	selectClass: {
		type: String,
		default: "",
	},
	searchable: {
		type: Boolean,
		default: false,
	},
	searchPlaceholder: {
		type: String,
		default: "Search...",
	},
	noResultsText: {
		type: String,
		default: "No results found",
	},
	maxDisplayed: {
		type: Number,
		default: 50, // Limit displayed options for performance
	},
})

const emit = defineEmits(["update:modelValue", "change"])

const isOpen = ref(false)
const containerRef = ref(null)
const triggerRef = ref(null)
const dropdownRef = ref(null)
const searchInputRef = ref(null)
const optionRefs = ref([])
const dropdownPosition = ref({ top: 0, left: 0, width: 0 })
const searchQuery = ref("")

const selectedLabel = computed(() => {
	const selected = props.options.find(opt => opt.value === props.modelValue)
	return selected?.label || ""
})

const filteredOptions = computed(() => {
	let result = props.options

	// Apply search filter if searchable and query exists
	if (props.searchable && searchQuery.value) {
		const query = searchQuery.value.toLowerCase()
		result = props.options.filter(opt =>
			opt.label?.toLowerCase().includes(query) ||
			opt.value?.toString().toLowerCase().includes(query) ||
			opt.subtitle?.toLowerCase().includes(query)
		)
	}

	// Limit displayed options for performance
	return result.slice(0, props.maxDisplayed)
})

const dropdownStyle = computed(() => ({
	top: `${dropdownPosition.value.top}px`,
	left: `${dropdownPosition.value.left}px`,
	width: `${dropdownPosition.value.width}px`,
}))

function updateDropdownPosition() {
	if (triggerRef.value) {
		const rect = triggerRef.value.getBoundingClientRect()
		dropdownPosition.value = {
			top: rect.bottom + 4, // 4px gap below the trigger
			left: rect.left,
			width: rect.width,
		}
	}
}

function toggle() {
	if (props.disabled) return
	if (!isOpen.value) {
		updateDropdownPosition()
		isOpen.value = true
		// Focus search input when opening if searchable
		if (props.searchable) {
			nextTick(() => {
				searchInputRef.value?.focus()
			})
		}
	} else {
		close()
	}
}

function close() {
	isOpen.value = false
	searchQuery.value = "" // Clear search on close
}

function openAndFocusFirst() {
	if (!isOpen.value) {
		updateDropdownPosition()
		isOpen.value = true
		nextTick(() => {
			if (optionRefs.value[0]) {
				optionRefs.value[0].focus()
			}
		})
	}
}

function selectOption(option) {
	emit("update:modelValue", option.value)
	emit("change", option.value)
	close()
}

function focusFirstOption() {
	nextTick(() => {
		if (optionRefs.value[0]) {
			optionRefs.value[0].focus()
		}
	})
}

function focusNext(currentIndex) {
	const nextIndex = currentIndex + 1
	if (nextIndex < filteredOptions.value.length && optionRefs.value[nextIndex]) {
		optionRefs.value[nextIndex].focus()
	}
}

function focusPrev(currentIndex) {
	const prevIndex = currentIndex - 1
	if (prevIndex >= 0 && optionRefs.value[prevIndex]) {
		optionRefs.value[prevIndex].focus()
	} else if (props.searchable && prevIndex < 0) {
		// Focus back to search input when going up from first option
		searchInputRef.value?.focus()
	}
}

// Close on click outside (check both container and teleported dropdown)
function handleClickOutside(event) {
	const clickedInContainer = containerRef.value && containerRef.value.contains(event.target)
	const clickedInDropdown = dropdownRef.value && dropdownRef.value.contains(event.target)

	if (!clickedInContainer && !clickedInDropdown) {
		close()
	}
}

// Close dropdown on scroll to prevent it from appearing detached
// But ignore scroll events from within the dropdown itself
function handleScroll(event) {
	if (isOpen.value) {
		// Don't close if scrolling inside the dropdown
		if (dropdownRef.value && dropdownRef.value.contains(event.target)) {
			return
		}
		close()
	}
}

// Add scroll listeners to all scrollable ancestors
function addScrollListeners() {
	let element = containerRef.value
	while (element) {
		element.addEventListener("scroll", handleScroll, true)
		element = element.parentElement
	}
	window.addEventListener("scroll", handleScroll, true)
}

function removeScrollListeners() {
	let element = containerRef.value
	while (element) {
		element.removeEventListener("scroll", handleScroll, true)
		element = element.parentElement
	}
	window.removeEventListener("scroll", handleScroll, true)
}

// Watch for dropdown open/close to manage scroll listeners
watch(isOpen, (newVal) => {
	if (newVal) {
		nextTick(() => {
			updateDropdownPosition()
			addScrollListeners()
		})
	} else {
		removeScrollListeners()
	}
})

onMounted(() => {
	document.addEventListener("click", handleClickOutside)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", handleClickOutside)
	removeScrollListeners()
})
</script>

<style scoped>
/* Use CSS custom property from index.css for consistent z-index layering */
.dropdown-z-index {
	z-index: var(--z-dropdown, 10000);
}
</style>
