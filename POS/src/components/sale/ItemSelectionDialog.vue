<template>
	<Dialog v-model="isOpen" :options="{ title: dialogTitle, size: 'md' }">
		<template #body-content>
			<div class="py-4">
				<div v-if="item" class="mb-4">
					<div class="flex items-center gap-3 mb-3">
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
					<p class="text-xs text-gray-600 mb-3 text-start">{{ dialogDescription }}</p>
				</div>

				<div v-if="loading" class="flex items-center justify-center py-8">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
					<p class="ms-3 text-sm text-gray-500">{{ __('Loading options...') }}</p>
				</div>

				<div v-else-if="mode === 'variant' && options.length > 0" class="flex flex-col gap-4">
					<div class="flex items-center justify-center mb-4">
						<img
							v-if="matchedVariant?.data?.image || item?.image"
							:src="matchedVariant?.data?.image || item.image"
							loading="lazy"
							:alt="matchedVariant?.label || item.item_name"
							class="w-32 h-32 object-contain rounded-lg transition-opacity duration-300"
						/>
					</div>

					<div v-for="(values, attrName) in variantAttributesMap" :key="attrName" class="flex flex-col gap-2">
						<label class="text-sm font-semibold text-gray-900 text-start block">{{ attrName }}</label>
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

					<div v-if="matchedVariant" class="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-semibold text-gray-900">{{ matchedVariant.label }}</p>
								<p class="text-xs text-gray-500">{{ matchedVariant.description }}</p>
							</div>
							<div class="text-end">
								<p class="text-sm font-bold text-blue-600">{{ formatCurrency(matchedVariant.rate || 0) }}</p>
								<p class="text-xs" :class="(matchedVariant.stock ?? matchedVariant.data?.actual_qty ?? 0) > 0 ? 'text-green-600' : 'text-red-600'">
									{{ __('Stock: {0}', [(matchedVariant.stock ?? matchedVariant.data?.actual_qty ?? 0)]) }}
								</p>
							</div>
						</div>
					</div>

					<div v-else-if="allAttributesSelected" class="mt-4 p-3 bg-orange-50 border border-orange-200 rounded-lg">
						<p class="text-xs text-orange-700">{{ __('This combination is not available') }}</p>
					</div>
				</div>

				<div v-else-if="mode === 'uom' && options.length > 0" class="flex flex-col gap-4">
					<div>
						<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Unit of Measure') }}</label>
						<div class="grid gap-2" :class="options.length <= 2 ? 'grid-cols-2' : 'grid-cols-3'">
							<button
								v-for="option in options"
								:key="option.key"
								@click="selectOption(option)"
								:class="[
									'px-4 py-3 rounded-xl font-bold text-base transition-all touch-manipulation flex flex-col items-center justify-center min-h-[60px]',
									isSelectedOption(option)
										? 'bg-blue-600 text-white shadow-lg ring-2 ring-blue-300'
										: 'bg-gray-100 text-gray-700 hover:bg-gray-200 active:bg-gray-300'
								]"
							>
								<span>{{ option.label }}</span>
								<span :class="['text-xs mt-0.5', isSelectedOption(option) ? 'text-blue-100' : 'text-gray-500']">
									{{ formatCurrency(option.rate || 0) }}
								</span>
							</button>
						</div>
					</div>

					<div>
						<label class="block text-sm font-medium text-gray-700 mb-2 text-start">{{ __('Quantity') }}</label>
						<div class="w-full h-10 border border-gray-300 rounded-lg bg-white flex items-center overflow-hidden">
							<button
								type="button"
								@click="decrementQuantity"
								class="w-[40px] h-[40px] min-w-[40px] bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border-e border-gray-300 touch-manipulation"
								style="flex: 0 0 40px;"
							>
								−
							</button>
							<div class="flex-1 h-full flex items-center justify-center px-3">
								<input
									ref="quantityInput"
									v-model.number="quantity"
									type="number"
									min="1"
									step="1"
									inputmode="numeric"
									class="w-full text-center border-0 text-sm font-semibold focus:outline-none focus:ring-0 bg-transparent [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
									@blur="validateQuantity"
									@keydown.enter="confirm"
								/>
							</div>
							<button
								type="button"
								@click="incrementQuantity"
								class="w-[40px] h-[40px] min-w-[40px] bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border-s border-gray-300 touch-manipulation"
								style="flex: 0 0 40px;"
							>
								+
							</button>
						</div>

						<div class="flex gap-2 mt-3">
							<button
								v-for="qty in [1, 5, 10, 20]"
								:key="qty"
								@click="quantity = qty"
								:class="[
									'flex-1 py-3 rounded-xl text-sm font-bold transition-all touch-manipulation',
									quantity === qty
										? 'bg-blue-600 text-white shadow-md'
										: 'bg-gray-100 text-gray-600 hover:bg-gray-200 active:bg-gray-300'
								]"
							>
								{{ qty }}
							</button>
						</div>
					</div>

					<div class="bg-blue-50 rounded-xl p-4 flex items-center justify-between">
						<div>
							<p class="text-sm text-gray-600">{{ __('Total') }}</p>
							<p class="text-xs text-gray-500">
								{{ quantity }} × {{ formatCurrency(selectedRate) }}
							</p>
							<p class="text-xs text-gray-500 mt-1">
								{{ selectedOptionLabel }}
							</p>
						</div>
						<p class="text-2xl font-bold text-blue-600">
							{{ formatCurrency(selectedRate * quantity) }}
						</p>
					</div>

					<div
						v-if="stockPanel"
						:class="[
							'rounded-lg p-3 text-xs border',
							stockPanel.blocked
								? 'bg-orange-50 text-orange-700 border-orange-200'
								: 'bg-yellow-50 text-yellow-700 border-yellow-200'
						]"
					>
						<div class="font-semibold mb-1">{{ stockPanel.title }}</div>
						<div>{{ __('Available: {0} {1}', [formatStockNumber(stockPanel.available), stockPanel.stock_uom]) }}</div>
						<div>{{ __('Required: {0} {1}', [formatStockNumber(stockPanel.required), stockPanel.stock_uom]) }}</div>
						<div v-if="!stockPanel.blocked" class="mt-1">{{ __('Selling allowed (negative stock enabled)') }}</div>
					</div>
				</div>

				<div v-else class="text-center py-8">
					<div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-orange-100 mb-3">
						<svg class="h-6 w-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
						</svg>
					</div>
					<p class="text-sm font-medium text-gray-900">
						{{ mode === 'variant'
							? __('No Variants Available')
							: __('No Options Available')
						}}
					</p>
					<p v-if="mode === 'variant'" class="text-xs text-gray-500 mt-2">
						<TranslatedHTML
							:inner="__('This item template &lt;strong&gt;{0}&lt;strong&gt; has no variants created yet.', [item?.item_name])"
						/>
					</p>
					<p v-else class="text-xs text-gray-500 mt-2">
						{{ __('No additional units of measurement configured for this item.') }}
					</p>
					<div v-if="mode === 'variant'" class="mt-4">
						<p class="text-xs text-gray-600 mb-2">{{ __('To create variants:') }}</p>
						<ol class="text-xs text-gray-600 text-start max-w-xs mx-auto flex flex-col gap-1">
							<TranslatedHTML
								:tag="'li'"
								:inner="__('1. Go to &lt;strong&gt;Item Master&lt;strong&gt; → &lt;strong&gt;{0}&lt;strong&gt;', [item?.item_code])"
							/>
							<TranslatedHTML
								:tag="'li'"
								:inner="__('2. Click &lt;strong&gt;&quot;Make Variants&quot;&lt;strong&gt; button')"
							/>
							<li>{{ __('3. Select attribute combinations') }}</li>
							<TranslatedHTML
								:tag="'li'"
								:inner="__('4. Click &lt;strong&gt;&quot;Create&quot;&lt;strong&gt;')"
							/>
						</ol>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex gap-2 w-full">
				<Button class="flex-1" variant="subtle" @click="cancel">
					{{ __('Cancel') }}
				</Button>
				<Button class="flex-1" variant="solid" theme="blue" @click="confirm" :disabled="!selectedOption">
					{{ confirmButtonText }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Button, Dialog } from "frappe-ui"
import { createResource } from "frappe-ui"
import { computed, nextTick, ref, watch } from "vue"
import TranslatedHTML from "../common/TranslatedHTML.vue"
import { offlineState } from "@/utils/offline/offlineState"
import { getCachedVariants, cacheItems } from "@/utils/offline/items"
import { getUOMPolicy } from "@/utils/pos_connector/uomPolicyAdapter"

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	mode: {
		type: String,
		default: "uom",
	},
	posProfile: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
})

const emit = defineEmits(["update:modelValue", "option-selected"])

const isOpen = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const loading = ref(false)
const options = ref([])
const selectedOption = ref(null)
const quantity = ref(1)
const selectedAttributes = ref({})
const quantityInput = ref(null)

const dialogTitle = computed(() => {
	return props.mode === "variant"
		? __("Select Item Variant")
		: __("Select Unit of Measure")
})

const dialogDescription = computed(() => {
	return props.mode === "variant"
		? __("Choose a variant of this item:")
		: __("Select the unit of measure for this item:")
})

const confirmButtonText = computed(() => {
	return __("Add to Cart")
})

const currentItem = computed(() => props.item || {})

const uomPolicy = computed(() => {
	return getUOMPolicy(currentItem.value, {})
})

const selectedRate = computed(() => {
	return Number(selectedOption.value?.rate || 0)
})

const selectedOptionLabel = computed(() => {
	if (!selectedOption.value) return ""
	const uom = selectedOption.value.uom || ""
	const cf = Number(selectedOption.value.conversion_factor || 1)
	return cf > 1
		? `${uom} x ${formatStockNumber(cf)}`
		: uom
})

const stockPanel = computed(() => {
	if (props.mode !== "uom" || !selectedOption.value || !props.item) return null

	const available = extractAvailableStock(props.item, selectedOption.value)
	if (available === null) return null

	const required = Number(quantity.value || 0) * Number(selectedOption.value.conversion_factor || 1)
	if (required <= available) return null

	return {
		blocked: false,
		title: __("Low stock"),
		available,
		required,
		stock_uom: props.item.stock_uom || selectedOption.value.uom || "",
	}
})

function formatStockNumber(value) {
	const num = Number(value)
	if (!Number.isFinite(num)) return "0"
	if (Math.abs(num - Math.round(num)) < 0.0001) {
		return String(Math.round(num))
	}
	return String(Math.round(num * 10000) / 10000)
}

function extractAvailableStock(item = {}, option = {}) {
	const candidates = [
		item.actual_qty,
		item.stock_qty,
		option.actual_qty,
		option.stock_qty,
	]
	for (const value of candidates) {
		const num = Number(value)
		if (Number.isFinite(num)) return num
	}
	return null
}

function validateQuantity() {
	if (!quantity.value || isNaN(quantity.value) || quantity.value < 1) {
		quantity.value = 1
	} else {
		quantity.value = Math.max(1, Math.round(quantity.value))
	}
}

function incrementQuantity() {
	quantity.value = Math.max(1, Number(quantity.value || 1) + 1)
}

function decrementQuantity() {
	if (quantity.value > 1) {
		quantity.value = Number(quantity.value) - 1
	}
}

const variantAttributesMap = computed(() => {
	if (props.mode !== "variant" || options.value.length === 0) return {}

	const attrMap = {}
	options.value.forEach((option) => {
		Object.entries(option.attributes || {}).forEach(([key, value]) => {
			if (!attrMap[key]) {
				attrMap[key] = new Set()
			}
			attrMap[key].add(value)
		})
	})

	const result = {}
	Object.keys(attrMap).forEach((key) => {
		result[key] = Array.from(attrMap[key]).sort()
	})

	return result
})

const allAttributesSelected = computed(() => {
	const attrKeys = Object.keys(variantAttributesMap.value)
	return (
		attrKeys.length > 0 &&
		attrKeys.every((key) => selectedAttributes.value[key])
	)
})

const matchedVariant = computed(() => {
	if (!allAttributesSelected.value) return null

	return options.value.find((option) => {
		return Object.entries(selectedAttributes.value).every(([key, value]) => {
			return option.attributes[key] === value
		})
	})
})

function mapVariantsToOptions(variants) {
	return variants.map((v) => ({
		type: "variant",
		item_code: v.item_code,
		label: v.item_name,
		description: v.item_code,
		attributes: v.attributes || {},
		rate: v.rate || v.price_list_rate || 0,
		priceLabel: __('per {0}', [v.stock_uom]),
		stock: v.actual_qty ?? 0,
		data: v,
	}))
}

async function loadVariantsFromCache() {
	try {
		const cachedVariants = await getCachedVariants(props.item?.item_code)
		options.value = cachedVariants?.length > 0 ? mapVariantsToOptions(cachedVariants) : []
	} catch (error) {
		console.error("Error loading variants from cache:", error)
		options.value = []
	} finally {
		loading.value = false
	}
}

const variantsResource = createResource({
	url: "pos_next.api.items.get_item_variants",
	makeParams() {
		return {
			template_item: props.item?.item_code,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	async onSuccess(data) {
		const variants = data?.message || data || []
		options.value = mapVariantsToOptions(variants)
		loading.value = false

		if (variants.length > 0) {
			cacheItems(variants).catch((err) => console.error("Error caching variants:", err))
		}
	},
	async onError() {
		await loadVariantsFromCache()
	},
})

watch(
	() => props.modelValue,
	(opened) => {
		if (opened && props.item) {
			loadOptions()
		}
		if (opened && props.mode === "uom") {
			nextTick(() => {
				setTimeout(() => {
					quantityInput.value?.focus()
					quantityInput.value?.select()
				}, 100)
			})
		}
	},
)

watch([() => props.mode, () => props.item], ([, newItem]) => {
	if (props.modelValue && newItem) {
		loadOptions()
	}
})

watch(matchedVariant, (variant) => {
	if (variant) {
		selectedOption.value = variant
	} else if (props.mode === "variant") {
		selectedOption.value = null
	}
})

async function loadOptions() {
	selectedOption.value = null
	quantity.value = Number(props.item?.resolved_qty || 1)
	selectedAttributes.value = {}

	if (props.mode === "variant") {
		loading.value = true

		if (offlineState.isOffline) {
			await loadVariantsFromCache()
		} else {
			variantsResource.reload()
		}
		return
	}

	options.value = buildUomOptions()

	if (options.value.length > 0) {
		selectedOption.value = resolveInitialUomOption(options.value)
	}

	loading.value = false
}

function buildUomOptions() {
	if (!props.item) return []

	const item = props.item
	const policyOptions = Array.isArray(uomPolicy.value.allowed_uoms) ? uomPolicy.value.allowed_uoms : []
	const sourceRows = policyOptions.length > 0
		? policyOptions
		: [
			...(item.stock_uom ? [{ uom: item.stock_uom, conversion_factor: 1 }] : []),
			...(Array.isArray(item.item_uoms) ? item.item_uoms : []),
		]

	const seen = new Set()
	const built = []

	for (const row of sourceRows) {
		const uom = row?.uom || row?.value || row?.name || null
		if (!uom || seen.has(uom)) continue
		seen.add(uom)

		const conversionFactor = Number(row?.conversion_factor || (uom === item.stock_uom ? 1 : 1)) || 1
		const rate = getUomPrice(uom, conversionFactor)

		built.push({
			key: `${uom}::${conversionFactor}`,
			type: "uom",
			uom,
			conversion_factor: conversionFactor,
			label: conversionFactor > 1 ? `${uom} x ${formatStockNumber(conversionFactor)}` : uom,
			description:
				conversionFactor > 1
					? __('1 {0} = {1} {2}', [uom, formatStockNumber(conversionFactor), item.stock_uom])
					: __("Stock unit"),
			rate,
			price_list_rate: rate,
			priceLabel: __('per {0}', [uom]),
			stock_uom: item.stock_uom || uom,
			stock_qty: item.stock_qty,
			actual_qty: item.actual_qty,
		})
	}

	return built
}

function getUomPrice(uom, conversionFactor) {
	if (!props.item) return 0

	if (props.item.uom_prices && props.item.uom_prices[uom] != null) {
		return Number(props.item.uom_prices[uom]) || 0
	}

	const itemUomRow = Array.isArray(props.item.item_uoms)
		? props.item.item_uoms.find((row) => row?.uom === uom)
		: null

	if (itemUomRow?.price_list_rate != null) {
		return Number(itemUomRow.price_list_rate) || 0
	}

	if (itemUomRow?.rate != null) {
		return Number(itemUomRow.rate) || 0
	}

	const baseRate = Number(props.item.rate || props.item.price_list_rate || 0)
	return baseRate * Number(conversionFactor || 1)
}

function resolveInitialUomOption(uomOptions) {
	if (!Array.isArray(uomOptions) || !uomOptions.length) return null

	const barcodeUoms = props.item?.barcode_uoms
		? props.item.barcode_uoms.split(",").map((v) => v.trim()).filter(Boolean)
		: []

	const preferredUom =
		props.item?.resolved_uom ||
		props.item?.uom ||
		(barcodeUoms.length === 1 ? barcodeUoms[0] : null) ||
		uomPolicy.value.default_uom ||
		props.item?.stock_uom ||
		null

	if (preferredUom) {
		const matched = uomOptions.find((opt) => opt.uom === preferredUom)
		if (matched) return matched
	}

	return uomOptions[0]
}

function selectAttribute(attributeName, value) {
	selectedAttributes.value[attributeName] = value
	selectedAttributes.value = { ...selectedAttributes.value }
}

function selectOption(option) {
	selectedOption.value = option
}

function isSelectedOption(option) {
	if (!selectedOption.value || !option) return false
	return selectedOption.value.uom === option.uom
		&& Number(selectedOption.value.conversion_factor || 1) === Number(option.conversion_factor || 1)
}

function confirm() {
	if (!selectedOption.value) return

	const option = { ...selectedOption.value }

	if (props.mode === "uom") {
		const normalizedQuantity = Math.max(1, Math.round(Number(quantity.value || 1)))
		const conversionFactor = Number(option.conversion_factor || 1)
		const rate = Number(option.rate || 0)

		emit("option-selected", {
			...option,
			quantity: normalizedQuantity,
			qty: normalizedQuantity,
			uom: option.uom,
			conversion_factor: conversionFactor,
			rate,
			price_list_rate: Number(option.price_list_rate ?? rate),
			stock_uom: props.item?.stock_uom || option.stock_uom || option.uom,
			selected_uom_label: option.label,
			required_stock_qty: normalizedQuantity * conversionFactor,
			available_stock_qty: extractAvailableStock(props.item, option),
			item: props.item,
		})
		return
	}

	emit("option-selected", option)
}

function cancel() {
	selectedOption.value = null
	selectedAttributes.value = {}
	isOpen.value = false
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}
</script>