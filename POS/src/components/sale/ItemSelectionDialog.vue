<template>
	<Dialog v-model="isOpen" :options="{ title: dialogTitle, size: 'md' }">
		<template #body-content>
			<div class="py-4">
				<div v-if="item" class="mb-4">
					<div class="flex items-center space-x-3 mb-3">
						<div class="w-12 h-12 bg-gray-100 rounded flex items-center justify-center overflow-hidden flex-shrink-0">
							<img v-if="item.image" :src="item.image" loading="lazy" :alt="item.item_name" class="w-full h-full object-cover" />
							<svg v-else class="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
							</svg>
						</div>
						<div class="flex-1">
							<h3 class="text-sm font-semibold text-gray-900">{{ item.item_name }}</h3>
							<p class="text-xs text-gray-500">{{ item.item_code }}</p>
						</div>
					</div>
					<p class="text-xs text-gray-600 mb-3">{{ dialogDescription }}</p>
				</div>

				<!-- Loading State -->
				<div v-if="loading" class="flex items-center justify-center py-8">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
					<p class="ml-3 text-sm text-gray-500">Loading options...</p>
				</div>

				<!-- Variant Options with Attribute Selection -->
				<div v-else-if="mode === 'variant' && options.length > 0" class="space-y-4">
					<!-- Display item image and info -->
					<div class="flex items-center justify-center mb-4">
						<img v-if="item?.image" :src="item.image" loading="lazy" :alt="item.item_name" class="w-32 h-32 object-contain rounded-lg" />
					</div>

					<!-- Group variants by attributes -->
					<div v-for="(values, attrName) in variantAttributesMap" :key="attrName" class="space-y-2">
						<label class="text-sm font-semibold text-gray-900">{{ attrName }}</label>
						<div class="flex flex-wrap gap-2">
							<button
								v-for="value in values"
								:key="value"
								@click="selectAttribute(attrName, value)"
								:class="[
									'px-4 py-2 rounded-lg border-2 text-sm font-medium transition-all',
									selectedAttributes[attrName] === value
										? 'border-blue-500 bg-blue-500 text-white'
										: 'border-gray-300 bg-white text-gray-700 hover:border-blue-300'
								]"
							>
								{{ value }}
							</button>
						</div>
					</div>

					<!-- Show selected variant info -->
					<div v-if="matchedVariant" class="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-semibold text-gray-900">{{ matchedVariant.label }}</p>
								<p class="text-xs text-gray-500">{{ matchedVariant.description }}</p>
							</div>
							<div class="text-right">
								<p class="text-sm font-bold text-blue-600">{{ formatCurrency(matchedVariant.rate || 0) }}</p>
								<p class="text-xs" :class="matchedVariant.stock > 0 ? 'text-green-600' : 'text-red-600'">
									Stock: {{ matchedVariant.stock }}
								</p>
							</div>
						</div>
					</div>

					<!-- Warning if combination not found -->
					<div v-else-if="allAttributesSelected" class="mt-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
						<p class="text-xs text-orange-700">This combination is not available</p>
					</div>
				</div>

				<!-- UOM Options (List format) -->
				<div v-else-if="mode === 'uom' && options.length > 0" class="space-y-2 max-h-96 overflow-y-auto">
					<button
						v-for="(option, index) in options"
						:key="index"
						@click="selectOption(option)"
						:class="[
							'w-full text-left p-3 rounded-lg border-2 transition-all',
							selectedOption === option
								? 'border-blue-500 bg-blue-50'
								: 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
						]"
					>
						<div class="flex items-center justify-between">
							<div class="flex-1">
								<p class="text-sm font-semibold text-gray-900">{{ option.label }}</p>
								<p class="text-xs text-gray-500">{{ option.description }}</p>
							</div>
							<div class="text-right ml-3">
								<p class="text-sm font-bold text-blue-600">
									{{ formatCurrency(option.rate || 0) }}
								</p>
								<p class="text-xs text-gray-500">{{ option.priceLabel }}</p>
							</div>
						</div>
					</button>
				</div>

				<!-- No Options -->
				<div v-else class="text-center py-8">
					<div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-orange-100 mb-3">
						<svg class="h-6 w-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
						</svg>
					</div>
					<p class="text-sm font-medium text-gray-900">No {{ mode === 'variant' ? 'Variants' : 'Options' }} Available</p>
					<p v-if="mode === 'variant'" class="text-xs text-gray-500 mt-2">
						This item template <strong>{{ item?.item_name }}</strong> has no variants created yet.
					</p>
					<p v-else class="text-xs text-gray-500 mt-2">
						No additional unit of measures configured for this item.
					</p>
					<div v-if="mode === 'variant'" class="mt-4">
						<p class="text-xs text-gray-600 mb-2">To create variants:</p>
						<ol class="text-xs text-gray-600 text-left max-w-xs mx-auto space-y-1">
							<li>1. Go to <strong>Item Master</strong> → <strong>{{ item?.item_code }}</strong></li>
							<li>2. Click <strong>"Make Variants"</strong> button</li>
							<li>3. Select attribute combinations</li>
							<li>4. Click <strong>"Create"</strong></li>
						</ol>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex space-x-2 w-full">
				<Button class="flex-1" variant="subtle" @click="cancel">
					Cancel
				</Button>
				<Button class="flex-1" variant="solid" theme="blue" @click="confirm" :disabled="!selectedOption">
					{{ confirmButtonText }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Dialog, Button } from 'frappe-ui'
import { createResource } from 'frappe-ui'
import { formatCurrency as formatCurrencyUtil } from '@/utils/currency'

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	mode: {
		type: String, // 'uom' or 'variant'
		default: 'uom'
	},
	posProfile: String,
	currency: {
		type: String,
		default: 'USD'
	}
})

const emit = defineEmits(['update:modelValue', 'option-selected'])

const isOpen = computed({
	get: () => props.modelValue,
	set: (value) => emit('update:modelValue', value)
})

const loading = ref(false)
const options = ref([])
const selectedOption = ref(null)
const selectedAttributes = ref({}) // For variant attribute selection

// Computed properties for dialog customization
const dialogTitle = computed(() => {
	return props.mode === 'variant' ? 'Select Item Variant' : 'Select Unit of Measure'
})

const dialogDescription = computed(() => {
	return props.mode === 'variant'
		? 'Choose a variant of this item:'
		: 'Select the unit of measure for this item:'
})

const confirmButtonText = computed(() => {
	return props.mode === 'variant' ? 'Add to Cart' : 'Add to Cart'
})

// Computed: Build a map of all available attribute values
const variantAttributesMap = computed(() => {
	if (props.mode !== 'variant' || options.value.length === 0) return {}

	const attrMap = {}
	options.value.forEach(option => {
		Object.entries(option.attributes || {}).forEach(([key, value]) => {
			if (!attrMap[key]) {
				attrMap[key] = new Set()
			}
			attrMap[key].add(value)
		})
	})

	// Convert Sets to sorted Arrays
	const result = {}
	Object.keys(attrMap).forEach(key => {
		result[key] = Array.from(attrMap[key]).sort()
	})

	return result
})

// Computed: Check if all attributes are selected
const allAttributesSelected = computed(() => {
	const attrKeys = Object.keys(variantAttributesMap.value)
	return attrKeys.length > 0 && attrKeys.every(key => selectedAttributes.value[key])
})

// Computed: Find variant that matches selected attributes
const matchedVariant = computed(() => {
	if (!allAttributesSelected.value) return null

	return options.value.find(option => {
		return Object.entries(selectedAttributes.value).every(([key, value]) => {
			return option.attributes[key] === value
		})
	})
})

// Resource for fetching variants
const variantsResource = createResource({
	url: 'pos_next.api.items.get_item_variants',
	makeParams() {
		return {
			template_item: props.item?.item_code,
			pos_profile: props.posProfile
		}
	},
	auto: false,
	onSuccess(data) {
		const variants = data?.message || data || []
		options.value = variants.map(v => ({
			type: 'variant',
			item_code: v.item_code,
			label: v.item_name,
			description: v.item_code,
			attributes: v.attributes || {},
			rate: v.rate || 0,
			priceLabel: `per ${v.stock_uom}`,
			stock: v.actual_qty,
			data: v // Full variant data
		}))
		loading.value = false
	},
	onError(error) {
		console.error('Error loading variants:', error)
		loading.value = false
	}
})

// Load options when dialog opens
watch(() => props.modelValue, (isOpen) => {
	if (isOpen && props.item) {
		loadOptions()
	}
})

// Watch mode and item changes to reload options
watch([() => props.mode, () => props.item], ([newMode, newItem]) => {
	if (props.modelValue && newItem) {
		loadOptions()
	}
})

function loadOptions() {
	selectedOption.value = null
	selectedAttributes.value = {} // Reset attribute selection

	if (props.mode === 'variant') {
		// Load variants from API
		loading.value = true
		variantsResource.reload()
	} else {
		// Load UOM options
		options.value = buildUomOptions()
		loading.value = false
	}
}

// Watch matched variant and auto-select it
watch(matchedVariant, (variant) => {
	if (variant) {
		selectedOption.value = variant
	} else {
		selectedOption.value = null
	}
})

function buildUomOptions() {
	if (!props.item) return []

	const uomOptions = []

	// Stock UOM option
	uomOptions.push({
		type: 'uom',
		uom: props.item.stock_uom,
		conversion_factor: 1,
		label: props.item.stock_uom,
		description: 'Stock unit',
		rate: getUomPrice(props.item.stock_uom),
		priceLabel: `per ${props.item.stock_uom}`
	})

	// Additional UOMs
	if (props.item.item_uoms && props.item.item_uoms.length > 0) {
		props.item.item_uoms.forEach(uomData => {
			uomOptions.push({
				type: 'uom',
				uom: uomData.uom,
				conversion_factor: uomData.conversion_factor,
				label: uomData.uom,
				description: `1 ${uomData.uom} = ${uomData.conversion_factor} ${props.item.stock_uom}`,
				rate: getUomPrice(uomData.uom),
				priceLabel: `per ${uomData.uom}`
			})
		})
	}

	return uomOptions
}

function getUomPrice(uom) {
	if (!props.item) return 0

	// Check if we have UOM-specific prices
	if (props.item.uom_prices && props.item.uom_prices[uom]) {
		return props.item.uom_prices[uom]
	}

	// Fallback to base rate
	return props.item.rate || 0
}

function selectAttribute(attributeName, value) {
	selectedAttributes.value[attributeName] = value
	// Force reactivity
	selectedAttributes.value = { ...selectedAttributes.value }
}

function selectOption(option) {
	selectedOption.value = option
}

function confirm() {
	if (selectedOption.value) {
		// Emit first, let parent decide if dialog should close
		// Parent can keep dialog open by switching mode (variant → UOM)
		emit('option-selected', selectedOption.value)
	}
}

function cancel() {
	selectedOption.value = null
	selectedAttributes.value = {}
	isOpen.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(parseFloat(amount || 0), props.currency)
}
</script>
